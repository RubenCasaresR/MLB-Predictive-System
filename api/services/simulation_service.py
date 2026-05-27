# =============================================================================
# simulation_service.py
# Servicio de simulación - wrappea Monte Carlo para la API
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import asyncio
import json
import logging
from datetime import date, datetime
from typing import Dict, List, Optional

from api.models.pydantic_models import SimulationRequest, SimulationResponse

logger = logging.getLogger(__name__)


def _parse_game_id_date(game_id: str) -> date:
    s = game_id[-6:]
    return date(2000 + int(s[0:2]), int(s[2:4]), int(s[4:6]))


class SimulationService:
    def __init__(self):
        self.cache: dict[str, SimulationResponse] = {}
        logger.info("SimulationService initialized")

    async def run_simulation(self, request: SimulationRequest) -> SimulationResponse:
        from sqlalchemy import text

        from api.database import get_engine
        from prediction.monte_carlo_simulator import MonteCarloMLBSimulator
        from prediction.player_state_builder import (
            _build_placeholder_lineup,
            _fetch_pitcher_state,
            _fetch_team_lineup,
        )

        engine = get_engine()
        target_date = _parse_game_id_date(request.game_id)

        home_lineup = _fetch_team_lineup(engine, request.home_team_id, target_date)
        away_lineup = _fetch_team_lineup(engine, request.away_team_id, target_date)

        if len(home_lineup) < 9:
            home_lineup.extend(
                _build_placeholder_lineup(
                    request.home_team_id,
                    0.310,
                    9 - len(home_lineup),
                )
            )
        if len(away_lineup) < 9:
            away_lineup.extend(
                _build_placeholder_lineup(
                    request.away_team_id,
                    0.310,
                    9 - len(away_lineup),
                )
            )

        home_pitcher = _fetch_pitcher_state(
            engine, request.home_pitcher_id if request.home_pitcher_id else 0, target_date
        )
        away_pitcher = _fetch_pitcher_state(
            engine, request.away_pitcher_id if request.away_pitcher_id else 0, target_date
        )

        ctx = self._fetch_game_context(engine, request.game_id, request.home_team_id, request.away_team_id, target_date)

        def progress(current, total):
            if current % 1000 == 0:
                logger.info(f"Simulating {request.game_id}: {current}/{total}")

        loop = asyncio.get_event_loop()
        sim = MonteCarloMLBSimulator(seed=42)

        result = await loop.run_in_executor(
            None,
            lambda: sim.run_simulation(
                home_lineup=home_lineup,
                away_lineup=away_lineup,
                home_pitcher=home_pitcher,
                away_pitcher=away_pitcher,
                park_factor_hr=ctx["pf_hr"],
                park_factor_single=ctx["pf_woba"],
                park_factor_k=ctx["pf_k"],
                temperature_f=ctx["temperature"],
                wind_speed=ctx["wind_speed"],
                wind_direction=ctx["wind_direction"],
                umpire_cs_rate=ctx["umpire_cs_rate"],
                stadium_id=ctx["stadium_id"],
                umpire_id=ctx["umpire_id"],
                home_bullpen_fip_30d=ctx["home_bp_fip"],
                away_bullpen_fip_30d=ctx["away_bp_fip"],
                home_bullpen_era=ctx["home_bp_era"],
                away_bullpen_era=ctx["away_bp_era"],
                home_rest_days=ctx["home_rest_days"],
                away_rest_days=ctx["away_rest_days"],
                home_travel_miles=ctx.get("home_travel_miles", 0),
                away_travel_miles=ctx.get("away_travel_miles", 0),
                home_tz_crossings=ctx.get("home_tz_crossings", 0),
                away_tz_crossings=ctx.get("away_tz_crossings", 0),
                n_iterations=request.n_iterations,
                progress_callback=progress,
            ),
        )

        now = datetime.now()
        response = SimulationResponse(
            game_id=request.game_id,
            home_win_prob=result.home_win_prob,
            away_win_prob=result.away_win_prob,
            mean_home_runs=result.mean_home_runs,
            mean_away_runs=result.mean_away_runs,
            std_home_runs=result.std_home_runs,
            std_away_runs=result.std_away_runs,
            extra_innings_prob=result.extra_innings_prob,
            walkoff_prob=result.walkoff_prob,
            n_iterations=request.n_iterations,
            home_run_distribution={str(k): v for k, v in result.home_run_distribution.items()},
            away_run_distribution={str(k): v for k, v in result.away_run_distribution.items()},
            computed_at=now,
        )

        # Persist to DB
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO simulation_results
                        (game_id, home_win_prob, away_win_prob,
                         mean_home_runs, mean_away_runs,
                         std_home_runs, std_away_runs,
                         extra_innings_prob, walkoff_prob,
                         run_distribution, n_iterations, computed_at)
                    VALUES (:gid, :hwp, :awp,
                            :mhr, :mar,
                            :shrs, :sars,
                            :eip, :wp,
                            :rd, :ni, :ca)
                    ON CONFLICT (game_id) DO UPDATE SET
                        home_win_prob = EXCLUDED.home_win_prob,
                        away_win_prob = EXCLUDED.away_win_prob,
                        mean_home_runs = EXCLUDED.mean_home_runs,
                        mean_away_runs = EXCLUDED.mean_away_runs,
                        std_home_runs = EXCLUDED.std_home_runs,
                        std_away_runs = EXCLUDED.std_away_runs,
                        extra_innings_prob = EXCLUDED.extra_innings_prob,
                        walkoff_prob = EXCLUDED.walkoff_prob,
                        run_distribution = EXCLUDED.run_distribution,
                        n_iterations = EXCLUDED.n_iterations,
                        computed_at = EXCLUDED.computed_at
                """),
                {
                    "gid": request.game_id,
                    "hwp": result.home_win_prob,
                    "awp": result.away_win_prob,
                    "mhr": result.mean_home_runs,
                    "mar": result.mean_away_runs,
                    "shrs": result.std_home_runs,
                    "sars": result.std_away_runs,
                    "eip": result.extra_innings_prob,
                    "wp": result.walkoff_prob,
                    "rd": json.dumps(
                        {
                            "home": {str(k): v for k, v in result.home_run_distribution.items()},
                            "away": {str(k): v for k, v in result.away_run_distribution.items()},
                        }
                    ),
                    "ni": request.n_iterations,
                    "ca": now,
                },
            )

        self.cache[request.game_id] = response
        logger.info(
            f"Simulation complete for {request.game_id}: P(home)={result.home_win_prob:.3f}"
        )
        return response

    def _fetch_game_context(self, engine, game_id: str, home_team_id: str, away_team_id: str, game_date: date) -> dict:
        from sqlalchemy import text

        ctx: dict = {
            "pf_hr": 1.0,
            "pf_woba": 1.0,
            "pf_k": 1.0,
            "temperature": 70.0,
            "wind_speed": 0.0,
            "wind_direction": "NONE",
            "umpire_cs_rate": 0.0,
            "stadium_id": 0,
            "umpire_id": 0,
            "home_bp_era": 4.50,
            "home_bp_fip": 4.50,
            "away_bp_era": 4.50,
            "away_bp_fip": 4.50,
            "home_rest_days": 4,
            "away_rest_days": 4,
            "home_travel_miles": 0,
            "away_travel_miles": 0,
            "home_tz_crossings": 0,
            "away_tz_crossings": 0,
        }
        try:
            with engine.connect() as conn:
                f = conn.execute(
                    text("""
                        SELECT
                            park_hr_factor, park_woba_factor, park_k_factor,
                            temperature, wind_speed, wind_direction,
                            umpire_cs_rate,
                            home_rest_days, away_rest_days,
                            away_tz_crossings, away_travel_miles
                        FROM mv_game_features
                        WHERE game_id = :gid
                    """),
                    {"gid": game_id},
                ).fetchone()
                if f:
                    ctx.update({
                        "pf_hr": float(f.park_hr_factor) if f.park_hr_factor else 1.0,
                        "pf_woba": float(f.park_woba_factor) if f.park_woba_factor else 1.0,
                        "pf_k": float(f.park_k_factor) if f.park_k_factor else 1.0,
                        "temperature": float(f.temperature) if f.temperature is not None else 70.0,
                        "wind_speed": float(f.wind_speed) if f.wind_speed is not None else 0.0,
                        "wind_direction": str(f.wind_direction) if f.wind_direction else "NONE",
                        "umpire_cs_rate": float(f.umpire_cs_rate) if f.umpire_cs_rate else 0.0,
                        "home_rest_days": int(f.home_rest_days) if f.home_rest_days else 4,
                        "away_rest_days": int(f.away_rest_days) if f.away_rest_days else 4,
                        "away_tz_crossings": int(f.away_tz_crossings) if f.away_tz_crossings else 0,
                        "away_travel_miles": int(f.away_travel_miles) if f.away_travel_miles else 0,
                    })

                gi = conn.execute(
                    text("SELECT venue_id, home_plate_umpire_id FROM games WHERE game_id = :gid"),
                    {"gid": game_id},
                ).fetchone()
                if gi:
                    ctx["stadium_id"] = int(gi[0]) if gi[0] else 0
                    ctx["umpire_id"] = int(gi[1]) if gi[1] else 0

                for side, tid in [("home", home_team_id), ("away", away_team_id)]:
                    if tid:
                        bp = conn.execute(
                            text("""
                                SELECT bullpen_era_30d, bullpen_fip_30d
                                FROM team_rolling_stats
                                WHERE team_id = :tid AND as_of_date <= :gd
                                ORDER BY as_of_date DESC LIMIT 1
                            """),
                            {"tid": tid, "gd": game_date.isoformat()},
                        ).fetchone()
                        if bp:
                            ctx[f"{side}_bp_era"] = float(bp[0]) if bp[0] else 4.50
                            ctx[f"{side}_bp_fip"] = float(bp[1]) if bp[1] else 4.50
        except Exception as e:
            logger.warning("Could not fetch context for game %s: %s", game_id, e)
        return ctx

    def get_cached(self, game_id: str) -> SimulationResponse | None:
        return self.cache.get(game_id)
