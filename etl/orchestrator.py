# =============================================================================
# orchestrator.py
# Orquestador ETL - Pipeline diario de datos MLB
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Coordina la ejecución de todos los procesos ETL en el orden correcto:
#   1. Schedule: obtener juegos del día
#   2. Statcast: play-by-play de juegos finalizados
#   3. Weather: pronóstiñcos para juegos próximos
#   4. Market: líneas de apuestas (loop continuo en ventana pre-game)
#   5. Features: cómputo de estadísticas rolling
#   6. Predicción: ejecutar Monte Carlo para juegos próximos
# =============================================================================

import asyncio
import json
import logging
import logging.config
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Optional

from etl.retry import with_retry

logger = logging.getLogger(__name__)


class ETLOrchestrator:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.executor = ThreadPoolExecutor(max_workers=4)
        logger.info("ETLOrchestrator initialized")

    def _load_checkpoint(self, path: str) -> set:
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return set(json.load(f))
        except Exception as e:
            logger.warning("Failed to load checkpoint %s: %s", path, e)
        return set()

    def _save_checkpoint(self, path: str, completed: set):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(sorted(completed), f, indent=2)
        except Exception as e:
            logger.warning("Failed to save checkpoint %s: %s", path, e)

    def _clean_checkpoint(self, path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.debug("Removed checkpoint %s (all steps completed)", path)
        except Exception as e:
            logger.warning("Failed to remove checkpoint %s: %s", path, e)

    def run_daily_pipeline(self, target_date: date | None = None):
        if target_date is None:
            target_date = date.today()

        logger.info(f"=== Starting daily ETL pipeline for {target_date} ===")

        checkpoint_dir = os.getenv("MLB_LOGS_DIR", "logs")
        checkpoint_file = os.path.join(
            checkpoint_dir,
            f"daily_checkpoint_{target_date.isoformat()}.json",
        )
        completed = self._load_checkpoint(checkpoint_file)

        steps = [
            ("load_schedule", "Loading game schedule", self.load_schedule),
            ("ingest_statcast", "Ingesting Statcast play-by-play", self.ingest_statcast),
            ("ingest_weather", "Ingesting weather data", self.ingest_weather),
            ("ingest_market", "Ingesting market data", self.ingest_market),
            ("compute_features", "Computing rolling features", self.compute_features),
            ("run_predictions", "Running predictions", self.run_predictions),
        ]

        for i, (step_name, label, method) in enumerate(steps, 1):
            if step_name in completed:
                logger.info(f"[{i}/{len(steps)}] {label} — already completed, skipping")
                continue

            logger.info(f"[{i}/{len(steps)}] {label}...")
            try:
                with_retry()(method)(target_date)
                completed.add(step_name)
                self._save_checkpoint(checkpoint_file, completed)
            except Exception as e:
                logger.error(
                    f"[{i}/{len(steps)}] {label} FAILED after retries: {e}",
                    exc_info=True,
                )
                logger.info("Continuing to next step...")

        self._clean_checkpoint(checkpoint_file)
        logger.info(f"=== Pipeline complete for {target_date} ===")

    def load_schedule(self, target_date: date):
        from etl.ingestors.statcast_ingestor import StatcastIngestor

        ingestor = StatcastIngestor(self.db_url)
        games = ingestor.fetch_daily_games(target_date)

        if games.empty:
            logger.info(f"No games scheduled for {target_date}")
            return

        import math

        from sqlalchemy import create_engine, text

        engine = create_engine(self.db_url)
        with engine.begin() as conn:
            for _, game in games.iterrows():
                venue_id = conn.execute(
                    text("SELECT stadium_id FROM stadiums WHERE team_id = :tid"),
                    {"tid": game["home_team_id"]},
                ).scalar()

                def _safe_int(val):
                    if val is None:
                        return None
                    try:
                        v = int(val)
                        return v if v > 0 else None
                    except (ValueError, TypeError, OverflowError):
                        return None

                hpp = _safe_int(game.get("home_probable_pitcher"))
                app = _safe_int(game.get("away_probable_pitcher"))
                conn.execute(
                    text("""
                        INSERT INTO games (game_id, game_date, season,
                            home_team_id, away_team_id, status, venue_id, start_time_et,
                            home_probable_pitcher, away_probable_pitcher)
                        VALUES (:gid, :gd, :season, :home, :away, :status, :venue, :start,
                            :hpp, :app)
                        ON CONFLICT (game_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            start_time_et = EXCLUDED.start_time_et,
                            venue_id = COALESCE(EXCLUDED.venue_id, games.venue_id),
                            home_probable_pitcher = COALESCE(EXCLUDED.home_probable_pitcher, games.home_probable_pitcher),
                            away_probable_pitcher = COALESCE(EXCLUDED.away_probable_pitcher, games.away_probable_pitcher)
                    """),
                    {
                        "gid": game["game_id"],
                        "gd": game["game_date"],
                        "season": target_date.year,
                        "home": game["home_team_id"],
                        "away": game["away_team_id"],
                        "status": game["status"],
                        "venue": venue_id,
                        "start": game.get("start_time_et"),
                        "hpp": hpp,
                        "app": app,
                    },
                )
        logger.info(f"Loaded schedule: {len(games)} games")
        self._enrich_game_metadata(target_date)

    def _enrich_game_metadata(self, target_date: date):
        from sqlalchemy import create_engine, text

        engine = create_engine(self.db_url)

        from etl.ingestors.weather_ingestor import WeatherIngestor

        coords = WeatherIngestor.STADIUM_COORDS
        timezone_map = {
            "America/New_York": -5,
            "America/Chicago": -6,
            "America/Denver": -7,
            "America/Los_Angeles": -8,
            "America/Toronto": -5,
            "America/Phoenix": -7,
        }

        def haversine(lat1, lon1, lat2, lon2):
            R = 3959
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(math.radians(lat1))
                * math.cos(math.radians(lat2))
                * math.sin(dlon / 2) ** 2
            )
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        def get_tz_offset(tz_str):
            for k, v in timezone_map.items():
                if k in tz_str:
                    return v
            return -5

        coords_by_team = {}
        for sid, info in coords.items():
            for tid in [
                "NYY",
                "BOS",
                "CHC",
                "LAD",
                "HOU",
                "ATL",
                "SFG",
                "STL",
                "PHI",
                "SDP",
                "NYM",
                "WSN",
                "BAL",
                "TBR",
                "MIA",
                "TOR",
                "CLE",
                "DET",
                "KCR",
                "MIN",
                "CHW",
                "LAA",
                "OAK",
                "SEA",
                "TEX",
                "ARI",
                "COL",
                "PIT",
                "CIN",
                "MIL",
            ]:
                if tid in info["name"]:
                    coords_by_team[tid] = (info["lat"], info["lon"])

        with engine.begin() as conn:
            games_today = conn.execute(
                text("""
                    SELECT game_id, home_team_id, away_team_id, venue_id, start_time_et
                    FROM games WHERE game_date = :gd
                """),
                {"gd": target_date},
            ).fetchall()

            tz_cache = {}

            def get_tz(team_id):
                if team_id not in tz_cache:
                    tz_cache[team_id] = (
                        conn.execute(
                            text("SELECT timezone FROM teams WHERE team_id = :tid"),
                            {"tid": team_id},
                        ).scalar()
                        or "America/New_York"
                    )
                return tz_cache[team_id]

            for g in games_today:
                home_tz_str = get_tz(g.home_team_id)
                away_tz_str = get_tz(g.away_team_id)
                home_off = get_tz_offset(home_tz_str)
                away_off = get_tz_offset(away_tz_str)
                tz_crossings = abs(home_off - away_off)

                hc = coords_by_team.get(g.home_team_id)
                ac = coords_by_team.get(g.away_team_id)
                travel_miles = int(round(haversine(ac[0], ac[1], hc[0], hc[1]))) if hc and ac else 0

                gd_str = target_date.isoformat()
                rest_days_home = (
                    conn.execute(
                        text("""
                        SELECT COALESCE(MAX(CAST(:gd AS DATE) - game_date), 5)
                        FROM games
                        WHERE (home_team_id = :tid OR away_team_id = :tid)
                          AND game_date < CAST(:gd AS DATE) AND status = 'FINAL'
                    """),
                        {"tid": g.home_team_id, "gd": gd_str},
                    ).scalar()
                    or 5
                )

                rest_days_away = (
                    conn.execute(
                        text("""
                        SELECT COALESCE(MAX(CAST(:gd AS DATE) - game_date), 5)
                        FROM games
                        WHERE (home_team_id = :tid OR away_team_id = :tid)
                          AND game_date < CAST(:gd AS DATE) AND status = 'FINAL'
                    """),
                        {"tid": g.away_team_id, "gd": gd_str},
                    ).scalar()
                    or 5
                )

                day_game_after_night_home = False
                day_game_after_night_away = False
                if g.start_time_et and g.start_time_et.hour < 17:
                    prev_home = conn.execute(
                        text("""
                            SELECT start_time_et FROM games
                            WHERE (home_team_id = :tid OR away_team_id = :tid)
                              AND game_date < CAST(:gd AS DATE) AND status = 'FINAL'
                            ORDER BY game_date DESC LIMIT 1
                        """),
                        {"tid": g.home_team_id, "gd": gd_str},
                    ).scalar()
                    if prev_home and prev_home.hour >= 17:
                        day_game_after_night_home = True

                    prev_away = conn.execute(
                        text("""
                            SELECT start_time_et FROM games
                            WHERE (home_team_id = :tid OR away_team_id = :tid)
                              AND game_date < CAST(:gd AS DATE) AND status = 'FINAL'
                            ORDER BY game_date DESC LIMIT 1
                        """),
                        {"tid": g.away_team_id, "gd": gd_str},
                    ).scalar()
                    if prev_away and prev_away.hour >= 17:
                        day_game_after_night_away = True

                conn.execute(
                    text("""
                        UPDATE games SET
                            home_travel_miles = :htm,
                            away_travel_miles = :atm,
                            home_tz_crossings = :htz,
                            away_tz_crossings = :atz,
                            home_rest_days = :hrd,
                            away_rest_days = :ard,
                            home_day_game_after_night = :hdgn,
                            away_day_game_after_night = :adgn
                        WHERE game_id = :gid
                    """),
                    {
                        "gid": g.game_id,
                        "htm": 0,
                        "atm": travel_miles,
                        "htz": 0,
                        "atz": tz_crossings,
                        "hrd": rest_days_home,
                        "ard": rest_days_away,
                        "hdgn": day_game_after_night_home,
                        "adgn": day_game_after_night_away,
                    },
                )

        logger.info(f"Enriched metadata for {len(games_today)} games")

    def ingest_statcast(self, target_date: date):
        from etl.ingestors.statcast_ingestor import StatcastIngestor

        ingestor = StatcastIngestor(self.db_url)
        ingestor.ingest_date_range(target_date, target_date)

    def ingest_weather(self, target_date: date):
        from etl.ingestors.weather_ingestor import WeatherIngestor

        ingestor = WeatherIngestor(self.db_url)
        ingestor.ingest_team_games(target_date)

    def ingest_market(self, target_date: date):
        from etl.config import ODDS_API_KEY
        from etl.ingestors.market_ingestor import MarketIngestor

        ingestor = MarketIngestor(self.db_url, ODDS_API_KEY)
        raw = ingestor.fetch_mlb_odds()
        parsed = ingestor.parse_odds(raw)
        ingestor.load_to_db(parsed)

        logger.warning(
            "Public betting volume (ticket_pct / money_pct) not ingested: "
            "the Odds API does not expose these fields; they require a "
            "premium direct sportsbook API (e.g., Kambi, IFS). Skipping."
        )

    def compute_features(self, target_date: date):
        from prediction.feature_pipeline import FeaturePipeline

        pipeline = FeaturePipeline(self.db_url)
        pipeline.run_full_pipeline(target_date)

    def run_predictions(self, target_date: date):
        import numpy as np
        from sqlalchemy import create_engine, text

        from prediction.monte_carlo_simulator import MonteCarloMLBSimulator
        from prediction.player_state_builder import (
            IncompleteLineupError,
            build_player_states_from_db,
            fetch_league_avg_probs,
        )

        engine = create_engine(self.db_url)

        with engine.connect() as conn:
            upcoming = conn.execute(
                text("""
                    SELECT game_id, home_team_id, away_team_id,
                           COALESCE(home_probable_pitcher, 0) AS home_p,
                           COALESCE(away_probable_pitcher, 0) AS away_p
                    FROM games
                    WHERE game_date = :gd
                      AND status IN ('SCHEDULED', 'PREGAME')
                """),
                {"gd": target_date},
            ).fetchall()

        if not upcoming:
            logger.info(f"No upcoming games on {target_date} for prediction")
            return

        league_probs = fetch_league_avg_probs(engine)
        sim = MonteCarloMLBSimulator(seed=42, league_avg_probs=league_probs)

        for game_id, home_team, away_team, home_p_id, away_p_id in upcoming:
            logger.info(f"Simulating {home_team} vs {away_team} ({game_id})")

            try:
                home_lineup, away_lineup, home_pitcher, away_pitcher = build_player_states_from_db(
                    engine,
                    game_id,
                    home_team,
                    away_team,
                    home_p_id,
                    away_p_id,
                    target_date,
                )
            except IncompleteLineupError as e:
                logger.warning(f"Skipping {game_id}: {e}")
                continue

            # Read all game factors from the materialized view + direct queries
            with engine.connect() as conn:
                f = conn.execute(
                    text("""
                        SELECT
                            park_hr_factor, park_woba_factor, park_k_factor,
                            temperature, wind_speed, wind_direction,
                            umpire_cs_rate,
                            home_team_woba, away_team_woba,
                            home_rest_days, away_rest_days,
                            away_tz_crossings, away_travel_miles
                        FROM mv_game_features
                        WHERE game_id = :gid
                    """),
                    {"gid": game_id},
                ).fetchone()

                # Bullpen stats from team_rolling_stats (not in mv_game_features)
                hbp = conn.execute(
                    text("""
                        SELECT bullpen_era_30d FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :gd
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": home_team, "gd": target_date},
                ).scalar()
                abp = conn.execute(
                    text("""
                        SELECT bullpen_era_30d FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :gd
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": away_team, "gd": target_date},
                ).scalar()
                hbpf = conn.execute(
                    text("""
                        SELECT bullpen_fip_30d FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :gd
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": home_team, "gd": target_date},
                ).scalar()
                abpf = conn.execute(
                    text("""
                        SELECT bullpen_fip_30d FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :gd
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": away_team, "gd": target_date},
                ).scalar()
                game_info = conn.execute(
                    text("""
                        SELECT venue_id, home_plate_umpire_id
                        FROM games WHERE game_id = :gid
                    """),
                    {"gid": game_id},
                ).fetchone()

            pf_hr = float(f.park_hr_factor) if f and f.park_hr_factor else 1.0
            pf_single = float(f.park_woba_factor) if f and f.park_woba_factor else 1.0
            pf_k = float(f.park_k_factor) if f and f.park_k_factor else 1.0
            temp = float(f.temperature) if f and f.temperature is not None else 70.0
            wind_spd = float(f.wind_speed) if f and f.wind_speed is not None else 0.0
            wind_dir = str(f.wind_direction) if f and f.wind_direction else "NONE"
            ump_cs = float(f.umpire_cs_rate) if f and f.umpire_cs_rate else 0.0
            home_bp_era = float(hbp) if hbp else 4.50
            away_bp_era = float(abp) if abp else 4.50
            home_bp_fip = float(hbpf) if hbpf else 4.50
            away_bp_fip = float(abpf) if abpf else 4.50
            stadium_id = int(game_info[0]) if game_info and game_info[0] else 0
            umpire_id = int(game_info[1]) if game_info and game_info[1] else 0

            # Neutralizar clima si el estadio tiene domo o techo retráctil
            if stadium_id:
                with engine.connect() as roof_conn:
                    roof = roof_conn.execute(
                        text("SELECT roof_type FROM stadiums WHERE stadium_id = :sid"),
                        {"sid": stadium_id},
                    ).scalar()
                if roof in ("dome", "retractable"):
                    temp = 72.0
                    wind_spd = 0.0
                    wind_dir = "NONE"
                    logger.info(f"Neutralized weather for domed stadium (game {game_id})")

            home_rest = int(f.home_rest_days) if f and f.home_rest_days else 4
            away_rest = int(f.away_rest_days) if f and f.away_rest_days else 4
            away_tz = int(f.away_tz_crossings) if f and f.away_tz_crossings else 0
            away_tm = int(f.away_travel_miles) if f and f.away_travel_miles else 0
            # Home team has 0 travel/tz (away team travels to home)
            home_tz = 0
            home_tm = 0

            result = sim.run_simulation(
                home_lineup=home_lineup,
                away_lineup=away_lineup,
                home_pitcher=home_pitcher,
                away_pitcher=away_pitcher,
                park_factor_hr=pf_hr,
                park_factor_single=pf_single,
                park_factor_k=pf_k,
                temperature_f=temp,
                wind_speed=wind_spd,
                wind_direction=wind_dir,
                umpire_cs_rate=ump_cs,
                stadium_id=stadium_id,
                umpire_id=umpire_id,
                home_bullpen_fip_30d=home_bp_fip,
                away_bullpen_fip_30d=away_bp_fip,
                home_bullpen_era=home_bp_era,
                away_bullpen_era=away_bp_era,
                home_rest_days=home_rest,
                away_rest_days=away_rest,
                home_travel_miles=home_tm,
                away_travel_miles=away_tm,
                home_tz_crossings=home_tz,
                away_tz_crossings=away_tz,
                n_iterations=10000,
            )

            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO simulation_results
                            (game_id, home_win_prob, away_win_prob,
                             mean_home_runs, mean_away_runs,
                             std_home_runs, std_away_runs,
                             extra_innings_prob, walkoff_prob,
                             run_distribution, n_iterations, computed_at)
                        VALUES (:gid, :hw, :aw, :mh, :ma, :sh, :sa, :ei, :wo,
                                :rd_json, :n, NOW())
                        ON CONFLICT (game_id) DO UPDATE SET
                            home_win_prob = EXCLUDED.home_win_prob,
                            away_win_prob = EXCLUDED.away_win_prob,
                            computed_at = NOW()
                    """),
                    {
                        "gid": game_id,
                        "hw": round(result.home_win_prob, 4),
                        "aw": round(result.away_win_prob, 4),
                        "mh": round(result.mean_home_runs, 2),
                        "ma": round(result.mean_away_runs, 2),
                        "sh": round(result.std_home_runs, 2),
                        "sa": round(result.std_away_runs, 2),
                        "ei": round(result.extra_innings_prob, 4),
                        "wo": round(result.walkoff_prob, 4),
                        "rd_json": json.dumps(
                            {
                                "home": {
                                    str(k): int(v)
                                    for k, v in __import__("collections")
                                    .Counter(result.home_runs_array.tolist())
                                    .items()
                                },
                                "away": {
                                    str(k): int(v)
                                    for k, v in __import__("collections")
                                    .Counter(result.away_runs_array.tolist())
                                    .items()
                                },
                            }
                        ),
                        "n": 10000,
                    },
                )

            logger.info(
                f"  → Home win: {result.home_win_prob:.1%}, Away win: {result.away_win_prob:.1%}"
                f" (park_hr={pf_hr:.2f}, temp={temp:.0f}°F, wind={wind_spd:.0f}mph)"
            )

        logger.info(f"Simulations complete for {len(upcoming)} games on {target_date}")

    def run_loop(self, interval_hours: int = 24):
        import signal as _signal

        _shutdown = False

        def _handler(signum, frame):
            nonlocal _shutdown
            logger.info("Received signal %d — shutting down loop...", signum)
            _shutdown = True

        _signal.signal(_signal.SIGTERM, _handler)

        logger.info(f"Starting ETL loop (interval: {interval_hours}h)")
        while not _shutdown:
            try:
                self.run_daily_pipeline()
            except Exception as e:
                logger.error(f"Pipeline failed: {e}")

            if _shutdown:
                break

            logger.info(f"Sleeping for {interval_hours} hours...")
            for _ in range(interval_hours * 360):
                if _shutdown:
                    break
                time.sleep(10)

        logger.info("ETL loop exited gracefully")


# ============================================================================
# MODO LÍNEA DE COMANDOS
# ============================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    from etl.config import DATABASE_URL

    orch = ETLOrchestrator(DATABASE_URL)

    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        orch.run_loop(interval_hours=24)
    else:
        orch.run_daily_pipeline()
