import logging
import math
import os
import traceback
from datetime import date as date_mod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests as http_requests
from sqlalchemy import text

from api.database import get_engine
from api.models.pydantic_models import (
    BullpenAnalysis,
    DailyAnalysisResponse,
    FatigueAnalysis,
    GameAnalysis,
    MarketSignals,
    OffensiveAnalysis,
    ParkFactor,
    PitchingAnalysis,
    PropAnalysisItem,
    RecommendedBet,
    WeatherImpact,
)

logger = logging.getLogger(__name__)

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"

_SHORT_NAME_MAP = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Yankees": "NYY",
    "New York Mets": "NYM",
    "Oakland Athletics": "OAK",
    "Athletics": "OAK",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
}


def _short_team_name(name: str) -> str:
    return _SHORT_NAME_MAP.get(name, name.split()[-1][:3].upper())


def _make_game_id(away_name: str, home_name: str, date_str: str) -> str:
    yymmdd = date_str.replace("-", "")[2:]
    return f"{_short_team_name(away_name)}{_short_team_name(home_name)}{yymmdd}"


TEAM_NAMES = {
    "ARI": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CHW": "Chicago White Sox",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "OAK": "Oakland Athletics",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SEA": "Seattle Mariners",
    "SF": "San Francisco Giants",
    "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals",
}


def _team_name(code: str) -> str:
    return TEAM_NAMES.get(code, code)


def _vig_free_prob(over_odds: int, under_odds: int) -> tuple[float, float]:
    def to_prob(odds):
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return -odds / (-odds + 100)

    p_over = to_prob(over_odds)
    p_under = to_prob(under_odds)
    total = p_over + p_under
    return p_over / total, p_under / total if total else 0.5


def _normal_cdf(x, mean, std):
    return 0.5 * (1 + math.erf((x - mean) / (std * math.sqrt(2))))


def _american_to_implied(odds: int) -> float:
    if odds > 0:
        return 100.0 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def _kelly(prob: float, odds: int, fraction: float = 0.25) -> float:
    if odds > 0:
        decimal = (odds / 100.0) + 1
    else:
        decimal = (100.0 / abs(odds)) + 1
    b = decimal - 1
    if b <= 0:
        return 0.0
    k = (prob * (b + 1) - 1) / b
    return max(0.0, min(k * fraction, 0.05))


class DailyAnalysisService:
    def __init__(self):
        self.engine = get_engine()
        self.tz_name = os.getenv("TIMEZONE", "America/Mexico_City")
        self.target_tz = ZoneInfo(self.tz_name)

    def get_analysis(self, target_date: str | None = None) -> DailyAnalysisResponse:
        if target_date:
            game_date = target_date
        else:
            game_date = datetime.now(self.target_tz).strftime("%Y-%m-%d")

        logger.info(
            "get_analysis: target_date=%s resolved_date=%s tz=%s",
            target_date,
            game_date,
            self.tz_name,
        )

        games = self._get_games(game_date)
        if not games:
            logger.info("No games in DB for %s, trying live MLB API", game_date)
            games = self._fetch_live_games(game_date)
        analyses: list[GameAnalysis] = []

        for game in games:
            try:
                analysis = self._analyze_game(game)
                analyses.append(analysis)
            except Exception as e:
                logger.warning(f"Error analyzing game {game.get('game_id')}: {e}")

        analyses.sort(
            key=lambda g: (
                g.start_time or "",
                -(g.recommended_bet.edge_pct if g.recommended_bet else 0),
            )
        )

        return DailyAnalysisResponse(
            game_date=game_date,
            generated_at=datetime.now(self.target_tz),
            total_games=len(analyses),
            games=analyses,
        )

    def _get_games(self, game_date: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                SELECT g.game_id, g.game_date, g.home_team_id, g.away_team_id,
                       g.home_probable_pitcher, g.away_probable_pitcher,
                       g.status, g.start_time_et,
                       g.home_rest_days, g.away_rest_days,
                       g.home_travel_miles, g.away_travel_miles,
                       g.home_tz_crossings, g.away_tz_crossings,
                       g.home_day_game_after_night, g.away_day_game_after_night,
                       g.venue_id
                FROM games g
                WHERE g.game_date = :gd
                  AND (g.status IS NULL OR g.status NOT IN ('FINAL','Final','Postponed','Cancelled'))
                ORDER BY g.start_time_et
            """),
                {"gd": game_date},
            ).fetchall()

        return [
            {
                "game_id": r[0],
                "game_date": str(r[1]) if r[1] else "",
                "home_team_id": r[2] or "",
                "away_team_id": r[3] or "",
                "home_pitcher_id": r[4],
                "away_pitcher_id": r[5],
                "status": r[6] or "",
                "start_time": str(r[7]) if r[7] else "",
                "home_rest_days": r[8] if r[8] else 0,
                "away_rest_days": r[9] if r[9] else 0,
                "home_travel_miles": r[10] if r[10] else 0,
                "away_travel_miles": r[11] if r[11] else 0,
                "home_tz_crossings": r[12] if r[12] else 0,
                "away_tz_crossings": r[13] if r[13] else 0,
                "home_day_game_after_night": bool(r[14]) if r[14] else False,
                "away_day_game_after_night": bool(r[15]) if r[15] else False,
                "venue_id": r[16],
            }
            for r in rows
        ]

    def _fetch_live_games(self, game_date: str) -> list[dict]:
        try:
            resp = http_requests.get(
                MLB_SCHEDULE_URL,
                params={"sportId": 1, "date": game_date},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"MLB API schedule failed for {game_date}: {e}")
            logger.debug("MLB API failure traceback:\n%s", traceback.format_exc())
            return []

        games = []
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                parsed = self._parse_live_game(game, game_date)
                if parsed:
                    games.append(parsed)
        logger.info(f"Fetched {len(games)} games from live MLB API for {game_date}")
        return games

    def _parse_live_game(self, game: dict, game_date: str) -> dict | None:
        teams = game.get("teams", {})
        away = teams.get("away", {}).get("team", {})
        home = teams.get("home", {}).get("team", {})
        away_pitcher = teams.get("away", {}).get("probablePitcher", {}) or {}
        home_pitcher = teams.get("home", {}).get("probablePitcher", {}) or {}
        date_str = game.get("gameDate", "")[:10]
        home_name = home.get("name", "???")
        away_name = away.get("name", "???")
        home_short = _short_team_name(home_name)
        away_short = _short_team_name(away_name)
        venue = game.get("venue", {}) or {}

        return {
            "game_id": _make_game_id(away_name, home_name, date_str or game_date),
            "game_date": date_str or game_date,
            "home_team_id": home_short,
            "away_team_id": away_short,
            "home_pitcher_id": 0,
            "away_pitcher_id": 0,
            "status": game.get("status", {}).get("detailedState", "SCHEDULED"),
            "start_time": game.get("gameDate", ""),
            "venue_id": venue.get("id"),
            "home_rest_days": 0,
            "away_rest_days": 0,
            "home_travel_miles": 0,
            "away_travel_miles": 0,
            "home_tz_crossings": 0,
            "away_tz_crossings": 0,
            "home_day_game_after_night": False,
            "away_day_game_after_night": False,
            "home_pitcher_name": home_pitcher.get("fullName", ""),
            "away_pitcher_name": away_pitcher.get("fullName", ""),
            "is_live_source": True,
        }

    def _analyze_game(self, game: dict) -> GameAnalysis:
        gid = game["game_id"]
        home = game["home_team_id"]
        away = game["away_team_id"]

        sim = self._get_simulation(gid)
        market = self._get_market(gid)
        pitchers = self._get_pitcher_data(
            gid, home, away, game.get("home_pitcher_id"), game.get("away_pitcher_id")
        )
        teams_data = self._get_team_data(home, away)
        weather_data = self._get_weather(gid)
        park_data = self._get_park_factors(gid, game.get("venue_id"))
        home_batters = self._get_batter_data(gid, home)
        away_batters = self._get_batter_data(gid, away)

        home_win_prob = sim.get("home_win_prob", 0.5) if sim else 0.5
        away_win_prob = sim.get("away_win_prob", 0.5) if sim else 0.5
        mean_home_runs = sim.get("mean_home_runs", 0) if sim else 0
        mean_away_runs = sim.get("mean_away_runs", 0) if sim else 0

        favorite_id = home if home_win_prob >= away_win_prob else away
        underdog_id = away if home_win_prob >= away_win_prob else home

        pitch_home = self._build_pitching_analysis(pitchers.get("home", {}), home, away)
        pitch_away = self._build_pitching_analysis(pitchers.get("away", {}), away, home)
        off_home = self._build_offensive_analysis(teams_data.get("home", {}), home_batters, home)
        off_away = self._build_offensive_analysis(teams_data.get("away", {}), away_batters, away)
        bull_home = self._build_bullpen(teams_data.get("home", {}), home)
        bull_away = self._build_bullpen(teams_data.get("away", {}), away)
        weather = self._build_weather(weather_data)
        park = self._build_park(park_data)
        fat_home = self._build_fatigue(game, "home")
        fat_away = self._build_fatigue(game, "away")
        signals = self._build_market_signals(market, home, away)

        rec_bet = self._determine_recommended_bet(
            game,
            sim,
            market,
            pitchers,
            teams_data,
            weather_data,
            home_win_prob,
            away_win_prob,
            home,
            away,
        )
        props = self._evaluate_props(
            game, pitchers, home_batters, away_batters, home, away, weather_data, park_data
        )

        narrative = self._generate_narrative(
            game,
            home,
            away,
            home_win_prob,
            away_win_prob,
            mean_home_runs,
            mean_away_runs,
            pitch_home,
            pitch_away,
            off_home,
            off_away,
            bull_home,
            bull_away,
            weather,
            park,
            fat_home,
            fat_away,
            signals,
            rec_bet,
        )
        key_factors = self._generate_key_factors(
            home,
            away,
            home_win_prob,
            away_win_prob,
            sim,
            market,
            pitchers,
            teams_data,
            weather_data,
            signals,
        )

        return GameAnalysis(
            game_id=gid,
            game_date=game.get("game_date", ""),
            start_time=game.get("start_time", ""),
            status=game.get("status", ""),
            home_team_id=home,
            away_team_id=away,
            home_team_name=_team_name(home),
            away_team_name=_team_name(away),
            home_win_prob=round(home_win_prob, 4),
            away_win_prob=round(away_win_prob, 4),
            favorite_id=favorite_id,
            favorite_name=_team_name(favorite_id),
            underdog_id=underdog_id,
            underdog_name=_team_name(underdog_id),
            win_prob_gap=round(abs(home_win_prob - away_win_prob) * 100, 1),
            mean_home_runs=round(mean_home_runs, 2),
            mean_away_runs=round(mean_away_runs, 2),
            predicted_total=round(mean_home_runs + mean_away_runs, 2),
            pitching_home=pitch_home,
            pitching_away=pitch_away,
            offensive_home=off_home,
            offensive_away=off_away,
            bullpen_home=bull_home,
            bullpen_away=bull_away,
            weather=weather,
            park_factors=park,
            fatigue_home=fat_home,
            fatigue_away=fat_away,
            market_signals=signals,
            recommended_bet=rec_bet,
            props=props,
            analysis_narrative=narrative,
            key_factors=key_factors,
        )

    def _get_simulation(self, game_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                SELECT home_win_prob, away_win_prob,
                       mean_home_runs, mean_away_runs,
                       std_home_runs, std_away_runs,
                       extra_innings_prob, walkoff_prob, n_iterations
                FROM simulation_results
                WHERE game_id = :gid
            """),
                {"gid": game_id},
            ).fetchone()
        if not row:
            return None
        return {
            "home_win_prob": float(row[0]),
            "away_win_prob": float(row[1]),
            "mean_home_runs": float(row[2]) if row[2] else 0,
            "mean_away_runs": float(row[3]) if row[3] else 0,
            "std_home_runs": float(row[4]) if row[4] else 0,
            "std_away_runs": float(row[5]) if row[5] else 0,
            "extra_innings_prob": float(row[6]) if row[6] else 0,
            "walkoff_prob": float(row[7]) if row[7] else 0,
            "n_iterations": row[8] or 10000,
        }

    def _get_market(self, game_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                SELECT home_moneyline_close, away_moneyline_close,
                       total_close, total_over_odds_close, total_under_odds_close,
                       sharp_money_flag, rlm_flag,
                       home_ticket_pct, home_money_pct,
                       away_ticket_pct, away_money_pct
                FROM market_lines
                WHERE game_id = :gid
                ORDER BY recorded_at DESC
                LIMIT 1
            """),
                {"gid": game_id},
            ).fetchone()
        if not row:
            return None
        return {
            "home_moneyline": row[0],
            "away_moneyline": row[1],
            "total_close": float(row[2]) if row[2] else None,
            "total_over_odds": row[3],
            "total_under_odds": row[4],
            "sharp_money_flag": bool(row[5]) if row[5] else False,
            "rlm_flag": bool(row[6]) if row[6] else False,
            "home_ticket_pct": float(row[7]) if row[7] else None,
            "home_money_pct": float(row[8]) if row[8] else None,
            "away_ticket_pct": float(row[9]) if row[9] else None,
            "away_money_pct": float(row[10]) if row[10] else None,
        }

    def _get_pitcher_data(
        self, game_id: str, home_team: str, away_team: str, home_pitcher_id, away_pitcher_id
    ) -> dict:
        result = {"home": {"player_id": home_pitcher_id}, "away": {"player_id": away_pitcher_id}}
        for side, pid, team in [
            ("home", home_pitcher_id, home_team),
            ("away", away_pitcher_id, away_team),
        ]:
            if not pid:
                continue
            try:
                pid_int = int(pid)
            except (ValueError, TypeError):
                continue
            with self.engine.connect() as conn:
                row = conn.execute(
                    text("""
                    SELECT prs.fatigue_score, prs.fip_30d, prs.avg_velo_30d,
                           prs.k_per_9_30d, prs.whiff_pct_30d, prs.avg_spin_30d,
                           p.full_name, p.throws,
                           prs.bb_pct_pitch_30d, prs.hr_per_9_30d
                    FROM player_rolling_stats prs
                    JOIN players p ON p.player_id = prs.player_id
                    WHERE prs.player_id = :pid
                    ORDER BY prs.as_of_date DESC
                    LIMIT 1
                """),
                    {"pid": pid_int},
                ).fetchone()
            if row:
                result[side] = {
                    "player_id": pid_int,
                    "fatigue_score": float(row[0]) if row[0] else None,
                    "fip_30d": float(row[1]) if row[1] else None,
                    "avg_velo_30d": float(row[2]) if row[2] else None,
                    "k_per_9_30d": float(row[3]) if row[3] else None,
                    "whiff_pct_30d": float(row[4]) if row[4] else None,
                    "avg_spin_30d": float(row[5]) if row[5] else None,
                    "full_name": row[6] or "",
                    "throws": row[7] or "",
                    "bb_per_9_30d": float(row[8]) if row[8] else None,
                    "hr_per_9_30d": float(row[9]) if row[9] else None,
                }
        return result

    def _get_team_data(self, home_team: str, away_team: str) -> dict:
        result = {"home": {}, "away": {}}
        for side, team in [("home", home_team), ("away", away_team)]:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text("""
                    SELECT bullpen_era_30d, bullpen_fip_30d, record_last_10,
                           run_diff_30d, woba_30d, woba_vs_rhp_30d,
                           woba_vs_lhp_30d, k_pct_30d, bb_pct_30d,
                           barrel_pct_30d, hard_hit_pct_30d
                    FROM team_rolling_stats
                    WHERE team_id = :tid
                    ORDER BY as_of_date DESC
                    LIMIT 1
                """),
                    {"tid": team},
                ).fetchone()
            if row:
                result[side] = {
                    "bullpen_era_30d": float(row[0]) if row[0] else None,
                    "bullpen_fip_30d": float(row[1]) if row[1] else None,
                    "record_last_10": row[2] or "",
                    "run_diff_30d": float(row[3]) if row[3] else None,
                    "team_woba_30d": float(row[4]) if row[4] else None,
                    "team_woba_vs_rhp_30d": float(row[5]) if row[5] else None,
                    "team_woba_vs_lhp_30d": float(row[6]) if row[6] else None,
                    "team_k_pct_30d": float(row[7]) if row[7] else None,
                    "team_bb_pct_30d": float(row[8]) if row[8] else None,
                    "team_barrel_pct_30d": float(row[9]) if row[9] else None,
                    "team_hard_hit_pct_30d": float(row[10]) if row[10] else None,
                }
        return result

    def _get_weather(self, game_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                SELECT temperature, wind_speed, wind_direction,
                       precipitation_pct, condition
                FROM weather_hourly
                WHERE game_id = :gid
                ORDER BY forecast_hour
                LIMIT 1
            """),
                {"gid": game_id},
            ).fetchone()
        if not row:
            return None
        return {
            "temperature": float(row[0]) if row[0] else None,
            "wind_speed": float(row[1]) if row[1] else None,
            "wind_direction": row[2] or "",
            "precipitation_pct": float(row[3]) if row[3] else None,
            "condition": row[4] or "",
        }

    def _get_park_factors(self, game_id: str, venue_id) -> dict | None:
        if not venue_id:
            return None
        try:
            vid = int(venue_id)
        except (ValueError, TypeError):
            return None
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                SELECT pfm.pf_hr, pfm.pf_woba, pfm.pf_k,
                       s.name
                FROM park_factors_monthly pfm
                JOIN stadiums s ON s.stadium_id = pfm.stadium_id
                WHERE pfm.stadium_id = :vid
                ORDER BY pfm.month DESC
                LIMIT 1
            """),
                {"vid": vid},
            ).fetchone()
            if not row:
                row2 = conn.execute(
                    text("""
                    SELECT 1.0, 1.0, 1.0, s.name
                    FROM stadiums s
                    WHERE s.stadium_id = :vid
                """),
                    {"vid": vid},
                ).fetchone()
                if row2:
                    return {
                        "hr_factor": float(row2[0]),
                        "woba_factor": float(row2[1]),
                        "k_factor": float(row2[2]),
                        "stadium_name": row2[3] or "",
                    }
                return None
        return {
            "hr_factor": float(row[0]) if row[0] else 1.0,
            "woba_factor": float(row[1]) if row[1] else 1.0,
            "k_factor": float(row[2]) if row[2] else 1.0,
            "stadium_name": row[3] or "",
        }

    def _get_batter_data(self, game_id: str, team_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                SELECT p.full_name, brs.woba_30d, brs.k_pct_30d, brs.bb_pct_30d,
                       brs.hr_per_9_30d,
                       brs.groundball_pct_30d, brs.flyball_pct_30d,
                       p.player_id, p.bats
                FROM batter_rolling_stats brs
                JOIN players p ON p.player_id = brs.player_id
                WHERE p.team_id = :tid
                ORDER BY brs.woba_30d DESC NULLS LAST
                LIMIT 9
            """),
                {"tid": team_id},
            ).fetchall()
        return [
            {
                "player_id": r[7],
                "full_name": r[0] or "",
                "woba_30d": float(r[1]) if r[1] else None,
                "k_pct_30d": float(r[2]) if r[2] else None,
                "bb_pct_30d": float(r[3]) if r[3] else None,
                "hr_per_9_30d": float(r[4]) if r[4] else None,
                "groundball_pct_30d": float(r[5]) if r[5] else None,
                "flyball_pct_30d": float(r[6]) if r[6] else None,
                "bats": r[8] or "",
            }
            for r in rows
        ]

    def _build_pitching_analysis(self, data: dict, team_id: str, opp_id: str) -> PitchingAnalysis:
        name = data.get("full_name", f"Pitcher {team_id}")
        throws = data.get("throws", "")
        fatigue = data.get("fatigue_score")

        fatigue_str = ""
        if fatigue is not None:
            if fatigue >= 0.8:
                fatigue_str = "muy descansado"
            elif fatigue >= 0.6:
                fatigue_str = "descansado"
            elif fatigue >= 0.4:
                fatigue_str = "moderadamente fatigado"
            else:
                fatigue_str = "fatigado"

        parts = []
        fip = data.get("fip_30d")
        if fip:
            fip_label = (
                "excelente"
                if fip < 3.2
                else "bueno"
                if fip < 3.8
                else "regular"
                if fip < 4.5
                else "elevado"
            )
            parts.append(f"FIP {fip:.2f} ({fip_label})")

        k9 = data.get("k_per_9_30d")
        if k9:
            parts.append(f"K/9 {k9:.1f}")

        velo = data.get("avg_velo_30d")
        if velo:
            parts.append(f"velocidad {velo:.1f} mph")

        bb9 = data.get("bb_per_9_30d")
        if bb9:
            parts.append(f"BB/9 {bb9:.1f}")

        summary = f"{name} ({throws}): {' · '.join(parts)}" if parts else f"{name}"
        if fatigue_str:
            summary += f" | {fatigue_str}"

        platoon = False
        if data.get("throws"):
            opp_pitchers = {}
            opp_throws = opp_pitchers.get("throws", "")
            if throws == "R" and opp_throws == "L":
                platoon = True
            elif throws == "L" and opp_throws == "R":
                platoon = True

        return PitchingAnalysis(
            pitcher_name=name,
            throws=throws,
            fip_30d=fip,
            k_per_9_30d=k9,
            bb_per_9_30d=bb9,
            hr_per_9_30d=data.get("hr_per_9_30d"),
            avg_velo_30d=velo,
            whiff_pct_30d=data.get("whiff_pct_30d"),
            fatigue_score=fatigue,
            platoon_advantage=platoon,
            summary=summary,
        )

    def _build_offensive_analysis(
        self, data: dict, batters: list[dict], team_id: str
    ) -> OffensiveAnalysis:
        woba = data.get("team_woba_30d")
        woba_vs_rhp = data.get("team_woba_vs_rhp_30d")
        woba_vs_lhp = data.get("team_woba_vs_lhp_30d")
        barrel = data.get("team_barrel_pct_30d")
        hard_hit = data.get("team_hard_hit_pct_30d")
        k_pct = data.get("team_k_pct_30d")
        bb_pct = data.get("team_bb_pct_30d")
        run_diff = data.get("run_diff_30d")
        record = data.get("record_last_10", "")

        parts = []
        if woba:
            woba_label = (
                "excelente"
                if woba > 0.340
                else "bueno"
                if woba > 0.320
                else "promedio"
                if woba > 0.300
                else "bajo"
            )
            parts.append(f"wOBA {woba:.3f} ({woba_label})")
        if barrel:
            parts.append(f"Barrel% {barrel:.1f}%")
        if hard_hit:
            parts.append(f"Hard Hit% {hard_hit:.1f}%")
        if run_diff is not None:
            parts.append(f"Run Diff {run_diff:+.0f}")
        if record:
            parts.append(f"últimos 10: {record}")

        woba_vs_hand = woba_vs_rhp or woba_vs_lhp or woba
        summary = f"Ofensiva de {_team_name(team_id)}: {' · '.join(parts)}" if parts else ""

        return OffensiveAnalysis(
            woba_30d=woba,
            woba_vs_hand=woba_vs_hand,
            barrel_pct_30d=barrel,
            hard_hit_pct_30d=hard_hit,
            k_pct_30d=k_pct,
            bb_pct_30d=bb_pct,
            run_diff_30d=run_diff,
            record_last_10=record,
            summary=summary,
        )

    def _build_bullpen(self, data: dict, team_id: str) -> BullpenAnalysis:
        era = data.get("bullpen_era_30d")
        fip = data.get("bullpen_fip_30d")
        parts = []
        if era:
            era_label = (
                "excelente"
                if era < 3.5
                else "bueno"
                if era < 4.0
                else "regular"
                if era < 4.5
                else "débil"
            )
            parts.append(f"ERA {era:.2f} ({era_label})")
        if fip:
            parts.append(f"FIP {fip:.2f}")
        summary = f"Bullpen {_team_name(team_id)}: {' · '.join(parts)}" if parts else ""
        return BullpenAnalysis(
            bullpen_era_30d=era,
            bullpen_fip_30d=fip,
            summary=summary,
        )

    def _build_weather(self, data: dict | None) -> WeatherImpact:
        if not data:
            return WeatherImpact(summary="Sin datos climáticos")
        temp = data.get("temperature")
        wind = data.get("wind_speed")
        wdir = data.get("wind_direction", "")
        precip = data.get("precipitation_pct")

        wind_effect = ""
        if wind is not None and wdir:
            wdir_u = wdir.upper()
            if wdir_u in ("OUT", "LTR", "RTL"):
                wind_effect = "favorable para bateadores (viento hacia fuera)"
            elif wdir_u == "IN":
                wind_effect = "favorable para lanzadores (viento hacia dentro)"
            else:
                wind_effect = f"viento de {wdir}"

        temp_effect = ""
        if temp is not None:
            if temp >= 85:
                temp_effect = "calor extremo favorece bateo"
            elif temp >= 75:
                temp_effect = "temperatura cálida"
            elif temp <= 50:
                temp_effect = "frío favorece lanzadores"
            elif temp <= 60:
                temp_effect = "temperatura fresca"

        parts = []
        if temp is not None:
            parts.append(f"{temp:.0f}°F")
        if wind is not None:
            parts.append(f"viento {wind:.0f} mph {wdir}")
        if precip is not None:
            parts.append(f"lluvia {precip:.0f}%")
        summary = f"Clima: {' · '.join(parts)}" if parts else "Sin datos"

        return WeatherImpact(
            temperature=temp,
            wind_speed=wind,
            wind_direction=wdir,
            precipitation_pct=precip,
            condition=data.get("condition", ""),
            wind_effect=wind_effect,
            temp_effect=temp_effect,
            summary=summary,
        )

    def _build_park(self, data: dict | None) -> ParkFactor:
        if not data:
            return ParkFactor(summary="Sin datos del estadio")
        name = data.get("stadium_name", "")
        hr = data.get("hr_factor", 1.0)
        woba = data.get("woba_factor", 1.0)
        k = data.get("k_factor", 1.0)

        parts = []
        hr_label = "alto" if hr > 1.05 else "bajo" if hr < 0.95 else "neutral"
        parts.append(f"HR {hr:.2f} ({hr_label})")
        parts.append(f"wOBA {woba:.2f}")
        parts.append(f"K {k:.2f}")
        summary = f"{name}: {' · '.join(parts)}" if name else " · ".join(parts)
        return ParkFactor(
            hr_factor=hr,
            woba_factor=woba,
            k_factor=k,
            stadium_name=name,
            summary=summary,
        )

    def _build_fatigue(self, game: dict, side: str) -> FatigueAnalysis:
        prefix = f"{side}_"
        return FatigueAnalysis(
            rest_days=game.get(f"{prefix}rest_days", 0),
            travel_miles=game.get(f"{prefix}travel_miles", 0),
            tz_crossings=game.get(f"{prefix}tz_crossings", 0),
            day_game_after_night=game.get(f"{prefix}day_game_after_night", False),
            summary="",
        )

    def _build_market_signals(self, data: dict | None, home: str, away: str) -> MarketSignals:
        if not data:
            return MarketSignals()
        parts = []
        if data.get("sharp_money_flag"):
            parts.append("Sharp money detectado")
        if data.get("rlm_flag"):
            parts.append("RLM detectado")
        home_ml = data.get("home_moneyline")
        away_ml = data.get("away_moneyline")
        ml_parts = []
        if home_ml:
            ml_parts.append(f"{home} {home_ml:+d}")
        if away_ml:
            ml_parts.append(f"{away} {away_ml:+d}")
        total = data.get("total_close")
        total_str = f"Total {total}" if total else ""
        summary = " · ".join(parts + [", ".join(ml_parts), total_str]) if parts or ml_parts else ""
        return MarketSignals(
            sharp_money_flag=data.get("sharp_money_flag", False),
            rlm_flag=data.get("rlm_flag", False),
            home_moneyline=home_ml,
            away_moneyline=away_ml,
            total_line=total,
            summary=summary,
        )

    def _determine_recommended_bet(
        self,
        game: dict,
        sim: dict | None,
        market: dict | None,
        pitchers: dict,
        teams_data: dict,
        weather_data: dict | None,
        home_win_prob: float,
        away_win_prob: float,
        home: str,
        away: str,
    ) -> RecommendedBet | None:
        if not market or not sim:
            return None

        home_ml = market.get("home_moneyline")
        away_ml = market.get("away_moneyline")
        if not home_ml or not away_ml:
            return None

        imp_home, imp_away = _vig_free_prob(home_ml, away_ml)
        edge_home = (home_win_prob - imp_home) * 100
        edge_away = (away_win_prob - imp_away) * 100

        candidates = []
        for team, opp, side, opp_side, edge_pct, odds, wp in [
            (home, away, "home", "away", edge_home, home_ml, home_win_prob),
            (away, home, "away", "home", edge_away, away_ml, away_win_prob),
        ]:
            if edge_pct < 1:
                continue

            score = 0
            if edge_pct >= 10:
                score += 30
            elif edge_pct >= 7:
                score += 25
            elif edge_pct >= 5:
                score += 20
            elif edge_pct >= 3:
                score += 10

            gap = abs(home_win_prob - away_win_prob) * 100
            if gap >= 30:
                score += 15
            elif gap >= 20:
                score += 10
            elif gap >= 10:
                score += 5

            if market.get("sharp_money_flag"):
                score += 10
            if market.get("rlm_flag"):
                score += 5

            pit_rec = pitchers.get(side, {})
            pit_opp = pitchers.get(opp_side, {})
            fat_rec = pit_rec.get("fatigue_score")
            fat_opp = pit_opp.get("fatigue_score")
            if fat_rec is not None and fat_opp is not None:
                diff = fat_opp - fat_rec
                if diff >= 0.20:
                    score += 15
                elif diff >= 0.10:
                    score += 10
                elif diff >= 0.05:
                    score += 5

            td_rec = teams_data.get(side, {})
            td_opp = teams_data.get(opp_side, {})
            bull_rec = td_rec.get("bullpen_era_30d")
            bull_opp = td_opp.get("bullpen_era_30d")
            if bull_rec is not None and bull_opp is not None:
                bdiff = bull_opp - bull_rec
                if bdiff >= 1.5:
                    score += 10
                elif bdiff >= 0.8:
                    score += 6
                elif bdiff >= 0.3:
                    score += 3

            if weather_data:
                precip = weather_data.get("precipitation_pct")
                if precip is not None and precip < 20:
                    score += 2
                wind = weather_data.get("wind_speed")
                if wind is not None and wind < 15:
                    score += 2
                temp = weather_data.get("temperature")
                if temp is not None and 60 <= temp <= 85:
                    score += 1

            kelly = _kelly(wp, odds)
            stake = kelly * 10000

            reasons = []
            if edge_pct >= 3:
                reasons.append(f"Edge del {edge_pct:.1f}% sobre la cuota real")
            if wp >= 0.60:
                reasons.append(f"Modelo proyecta {wp:.0f}% de probabilidad de victoria")
            if market.get("sharp_money_flag"):
                reasons.append("Respaldado por dinero sharp (profesional)")
            if market.get("rlm_flag"):
                reasons.append("RLM: la línea se mueve contra el público")

            conf = "Alta" if score >= 40 else "Media" if score >= 25 else "Baja"

            candidates.append(
                {
                    "team": team,
                    "opponent": opp,
                    "market_type": "moneyline",
                    "odds": odds,
                    "edge_pct": round(edge_pct, 1),
                    "confidence": conf,
                    "kelly_fraction": round(kelly, 4),
                    "recommended_stake": round(stake, 2),
                    "reasoning": reasons[:6],
                    "score": score,
                }
            )

        if not candidates:
            return None

        candidates.sort(key=lambda c: (c["score"], c["edge_pct"]), reverse=True)
        best = candidates[0]
        return RecommendedBet(
            team=best["team"],
            opponent=best["opponent"],
            market_type=best["market_type"],
            odds=best["odds"],
            edge_pct=best["edge_pct"],
            confidence=best["confidence"],
            kelly_fraction=best["kelly_fraction"],
            recommended_stake=best["recommended_stake"],
            reasoning=best["reasoning"],
        )

    def _evaluate_props(
        self,
        game: dict,
        pitchers: dict,
        home_batters: list[dict],
        away_batters: list[dict],
        home: str,
        away: str,
        weather_data: dict | None,
        park_data: dict | None,
    ) -> list[PropAnalysisItem]:
        results: list[PropAnalysisItem] = []

        try:
            from prediction.poisson_props import PoissonPropsEngine

            engine = PoissonPropsEngine()
        except ImportError:
            return results

        weather = weather_data or {}
        park = park_data or {}

        for side, batters, opp_pitcher_data in [
            ("home", home_batters, pitchers.get("away", {})),
            ("away", away_batters, pitchers.get("home", {})),
        ]:
            opp_fip = opp_pitcher_data.get("fip_30d", 4.20)
            park_hit = park.get("woba_factor", 1.0)

            for batter in batters[:4]:
                woba = batter.get("woba_30d", 0.310)
                hard_hit = batter.get("hard_hit_pct_30d", 0.35) or 0.35
                barrel = batter.get("barrel_pct_30d", 0.08) or 0.08
                k_rate = batter.get("k_pct_30d", 0.22) or 0.22

                try:
                    features = engine.build_hit_features(
                        woba=woba,
                        hard_hit_pct=hard_hit,
                        barrel_pct=barrel,
                        opponent_fip=opp_fip or 4.20,
                        park_hit_factor=park_hit,
                        platoon_advantage=True,
                        k_rate=k_rate,
                    )
                    result = engine.evaluate_bet(
                        prop_type="HITS",
                        player_name=batter.get("full_name", "Unknown"),
                        line_value=1.5,
                        over_odds=-110,
                        under_odds=-110,
                        features=features,
                    )
                    if result.recommendation != "no_bet":
                        edge = max(result.ev_over, result.ev_under)
                        results.append(
                            PropAnalysisItem(
                                player_name=result.player_name,
                                prop_type="HITS",
                                line_value=result.line_value,
                                predicted_mean=result.predicted_mean,
                                prob_over=result.prob_over,
                                prob_under=result.prob_under,
                                ev_over=result.ev_over,
                                ev_under=result.ev_under,
                                recommendation=result.recommendation,
                                edge_pct=round(edge * 100, 1),
                                kelly_fraction=result.kelly_fraction,
                            )
                        )
                except Exception:
                    continue

        for side, pitcher_data in [
            ("home", pitchers.get("home", {})),
            ("away", pitchers.get("away", {})),
        ]:
            if not pitcher_data.get("player_id"):
                continue
            velo = pitcher_data.get("avg_velo_30d", 93.0) or 93.0
            whiff = pitcher_data.get("whiff_pct_30d", 0.12) or 0.12
            spin = pitcher_data.get("avg_spin_30d", 2200.0) or 2200.0
            park_k = park.get("k_factor", 1.0)

            try:
                features = engine.build_strikeout_features(
                    pitcher_velo=velo,
                    pitcher_whiff_pct=whiff,
                    opponent_k_pct=0.225,
                    park_k_factor=park_k,
                    days_rested=4,
                    pitcher_spin=spin,
                )
                result = engine.evaluate_bet(
                    prop_type="STRIKEOUTS",
                    player_name=pitcher_data.get("full_name", "Unknown"),
                    line_value=5.5,
                    over_odds=-110,
                    under_odds=-110,
                    features=features,
                )
                if result.recommendation != "no_bet":
                    edge = max(result.ev_over, result.ev_under)
                    results.append(
                        PropAnalysisItem(
                            player_name=result.player_name,
                            prop_type="STRIKEOUTS",
                            line_value=result.line_value,
                            predicted_mean=result.predicted_mean,
                            prob_over=result.prob_over,
                            prob_under=result.prob_under,
                            ev_over=result.ev_over,
                            ev_under=result.ev_under,
                            recommendation=result.recommendation,
                            edge_pct=round(edge * 100, 1),
                            kelly_fraction=result.kelly_fraction,
                        )
                    )
            except Exception:
                continue

        results.sort(key=lambda p: p.edge_pct, reverse=True)
        return results[:6]

    def _generate_narrative(
        self,
        game: dict,
        home: str,
        away: str,
        home_win_prob: float,
        away_win_prob: float,
        mean_home_runs: float,
        mean_away_runs: float,
        pitch_home: PitchingAnalysis,
        pitch_away: PitchingAnalysis,
        off_home: OffensiveAnalysis,
        off_away: OffensiveAnalysis,
        bull_home: BullpenAnalysis,
        bull_away: BullpenAnalysis,
        weather: WeatherImpact,
        park: ParkFactor,
        fat_home: FatigueAnalysis,
        fat_away: FatigueAnalysis,
        signals: MarketSignals,
        rec_bet: RecommendedBet | None,
    ) -> str:
        home_name = _team_name(home)
        away_name = _team_name(away)
        favorite = home_name if home_win_prob >= away_win_prob else away_name
        underdog = away_name if home_win_prob >= away_win_prob else home_name
        fav_prob = max(home_win_prob, away_win_prob) * 100
        under_prob = min(home_win_prob, away_win_prob) * 100

        paragraphs = []

        intro = (
            f"{favorite} ({fav_prob:.0f}%) vs {underdog} ({under_prob:.0f}%): "
            f"{favorite} es el favorito según el modelo Monte Carlo con un {fav_prob:.0f}% "
            f"de probabilidad de victoria. El marcador proyectado es "
            f"{_team_name(home) if home_win_prob >= away_win_prob else _team_name(away)} "
            f"{max(mean_home_runs, mean_away_runs):.1f} - "
            f"{min(mean_home_runs, mean_away_runs):.1f}."
        )
        paragraphs.append(intro)

        pitch_parts = []
        pitch_parts.append(
            f"En el montículo, {pitch_home.pitcher_name} ({pitch_home.throws}) abrirá por {home_name}"
        )
        if pitch_home.fip_30d:
            pitch_parts.append(f"con FIP de {pitch_home.fip_30d:.2f}")
        if pitch_home.avg_velo_30d:
            pitch_parts.append(f"y velocidad de {pitch_home.avg_velo_30d:.1f} mph")
        pitch_parts.append(".")
        pitch_parts.append(f"Por {away_name} abre {pitch_away.pitcher_name} ({pitch_away.throws})")
        if pitch_away.fip_30d:
            pitch_parts.append(f"con FIP de {pitch_away.fip_30d:.2f}")
        if pitch_away.avg_velo_30d:
            pitch_parts.append(f"y {pitch_away.avg_velo_30d:.1f} mph")
        pitch_parts.append(".")
        paragraphs.append(" ".join(pitch_parts))

        if off_home.woba_30d and off_away.woba_30d:
            better_off = home_name if off_home.woba_30d > off_away.woba_30d else away_name
            worse_off = away_name if off_home.woba_30d > off_away.woba_30d else home_name
            paragraphs.append(
                f"Ofensivamente, {better_off} (wOBA {max(off_home.woba_30d, off_away.woba_30d):.3f}) "
                f"supera a {worse_off} (wOBA {min(off_home.woba_30d, off_away.woba_30d):.3f}) "
                f"en los últimos 30 días."
            )

        if bull_home.bullpen_era_30d and bull_away.bullpen_era_30d:
            better_bull = (
                home_name if bull_home.bullpen_era_30d < bull_away.bullpen_era_30d else away_name
            )
            paragraphs.append(
                f"El bullpen de {better_bull} (ERA {min(bull_home.bullpen_era_30d, bull_away.bullpen_era_30d):.2f}) "
                f"está en mejor forma que el de su oponente."
            )

        weather_parts = []
        if weather.temperature:
            weather_parts.append(f"{weather.temperature:.0f}°F")
        if weather.wind_speed and weather.wind_direction:
            weather_parts.append(f"viento {weather.wind_speed:.0f} mph {weather.wind_direction}")
        if weather_parts:
            weather_str = f"El clima en {park.stadium_name}: {' · '.join(weather_parts)}."
            if weather.wind_effect:
                weather_str += f" El viento está {weather.wind_effect}."
            if weather.temp_effect:
                weather_str += f" La {weather.temp_effect}."
            paragraphs.append(weather_str)

        if park.stadium_name:
            park_str = f"El {park.stadium_name} tiene factor de HR de {park.hr_factor:.2f}"
            if park.hr_factor > 1.05:
                park_str += " (favorece jonrones)"
            elif park.hr_factor < 0.95:
                park_str += " (suprime jonrones)"
            park_str += "."
            paragraphs.append(park_str)

        if signals.sharp_money_flag or signals.rlm_flag:
            signal_parts = []
            if signals.sharp_money_flag:
                signal_parts.append("Se detecta dinero sharp (profesional) en el mercado")
            if signals.rlm_flag:
                signal_parts.append("hay movimiento de línea contrario al público (RLM)")
            paragraphs.append("🔍 " + " y ".join(signal_parts) + ", lo que indica valor oculto.")

        if rec_bet:
            conf_icon = (
                "🟢"
                if rec_bet.confidence == "Alta"
                else "🟡"
                if rec_bet.confidence == "Media"
                else "🔴"
            )
            paragraphs.append(
                f"{conf_icon} Apuesta recomendada: {_team_name(rec_bet.team)} "
                f"Moneyline ({rec_bet.odds:+d}) con un edge del {rec_bet.edge_pct:.1f}% "
                f"y confianza {rec_bet.confidence}."
            )

        return "\n\n".join(paragraphs)

    def _generate_key_factors(
        self,
        home: str,
        away: str,
        home_win_prob: float,
        away_win_prob: float,
        sim: dict | None,
        market: dict | None,
        pitchers: dict,
        teams_data: dict,
        weather_data: dict | None,
        signals: MarketSignals,
    ) -> list[str]:
        factors = []
        fav = home if home_win_prob >= away_win_prob else away
        fav_name = _team_name(fav)

        factors.append(
            f"{fav_name} favorito con {max(home_win_prob, away_win_prob) * 100:.0f}% de win probability"
        )

        if market:
            if market.get("sharp_money_flag"):
                factors.append("Sharp money respalda al favorito")
            if market.get("rlm_flag"):
                factors.append("RLM: la línea se mueve contra el público")

        for side, label in [("home", _team_name(home)), ("away", _team_name(away))]:
            pd = pitchers.get(side, {})
            fip = pd.get("fip_30d")
            fatigue = pd.get("fatigue_score")
            if fip:
                fip_label = "excelente" if fip < 3.2 else "bueno" if fip < 3.8 else "regular"
                factors.append(f"Abridor de {label}: FIP {fip:.2f} ({fip_label})")
            if fatigue is not None and fatigue < 0.4:
                factors.append(f"Abridor de {label} fatigado ({fatigue:.2f})")

        for side, label in [("home", _team_name(home)), ("away", _team_name(away))]:
            td = teams_data.get(side, {})
            bull = td.get("bullpen_era_30d")
            if bull:
                bull_label = "fuerte" if bull < 3.5 else "débil" if bull > 4.5 else "promedio"
                factors.append(f"Bullpen de {label}: ERA {bull:.2f} ({bull_label})")

        if weather_data:
            temp = weather_data.get("temperature")
            if temp is not None and temp >= 85:
                factors.append(f"Calor extremo ({temp:.0f}°F): favorece bateo y carreras")
            elif temp is not None and temp <= 50:
                factors.append(f"Frío ({temp:.0f}°F): favorece lanzadores")

        if sim:
            ei = sim.get("extra_innings_prob", 0)
            if ei and ei > 0.15:
                factors.append(f"Alta probabilidad de extras ({ei:.0f}%)")
            wp = sim.get("walkoff_prob", 0)
            if wp and wp > 0.05:
                factors.append(f"Posibilidad de walkoff ({wp:.0f}%)")

        return factors[:10]
