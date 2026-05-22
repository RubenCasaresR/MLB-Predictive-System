# =============================================================================
# stats.py
# Router de estadísticas y datos de jugadores/equipos
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
import logging
import os
import requests as http_requests
from datetime import date as d, datetime, timezone
from zoneinfo import ZoneInfo

from api.database import get_engine
from api.models.pydantic_models import PlayerStatsResponse, GamePreviewResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


def _to_local_tz(dt_str: str) -> str:
    """Convierte timestamp UTC (naive o con Z) a la zona horaria configurada."""
    if not dt_str:
        return ""
    try:
        tz_name = os.getenv("TIMEZONE", "America/Mexico_City")
        # Intentar parse ISO 8601 primero
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            # Formato DB: "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = datetime.fromisoformat(dt_str)
        # Si es naive, asumir UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Convertir a zona objetivo y devolver ISO con offset
        target_tz = ZoneInfo(tz_name)
        dt_local = dt.astimezone(target_tz)
        return dt_local.isoformat()
    except Exception as e:
        logger.warning(f"Timezone conversion failed for '{dt_str}': {e}")
        return dt_str


@router.get("/players/{player_id}", response_model=PlayerStatsResponse)
async def get_player_stats(player_id: int):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT player_id, full_name, team_id, position, bats, throws "
                 "FROM players WHERE player_id = :pid"),
            {"pid": player_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Player not found")

        stats_row = conn.execute(
            text("SELECT woba_30d, fip_30d, xera_30d, avg_velo_30d, "
                 "whiff_pct_30d, fatigue_score "
                 "FROM player_rolling_stats "
                 "WHERE player_id = :pid "
                 "ORDER BY as_of_date DESC LIMIT 1"),
            {"pid": player_id},
        ).fetchone()

    return PlayerStatsResponse(
        player_id=row[0],
        full_name=row[1] or "",
        team_id=row[2] or "",
        position=row[3] or "",
        bats=row[4] or "",
        throws=row[5] or "",
        woba_30d=float(stats_row[0]) if stats_row and stats_row[0] else None,
        fip_30d=float(stats_row[1]) if stats_row and stats_row[1] else None,
        xera_30d=float(stats_row[2]) if stats_row and stats_row[2] else None,
        avg_velo_30d=float(stats_row[3]) if stats_row and stats_row[3] else None,
        whiff_pct_30d=float(stats_row[4]) if stats_row and stats_row[4] else None,
        fatigue_score=float(stats_row[5]) if stats_row and stats_row[5] else None,
    )


@router.get("/players", response_model=List[PlayerStatsResponse])
async def list_players(
    team_id: Optional[str] = Query(None),
    position: Optional[str] = Query(None),
):
    engine = get_engine()
    query = "SELECT player_id, full_name, team_id FROM players WHERE 1=1"
    params = {}
    if team_id:
        query += " AND team_id = :tid"
        params["tid"] = team_id
    if position:
        query += " AND position = :pos"
        params["pos"] = position
    query += " ORDER BY full_name LIMIT 100"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()

    return [
        PlayerStatsResponse(player_id=r[0], full_name=r[1] or "", team_id=r[2] or "")
        for r in rows
    ]


@router.get("/preview/{game_id}", response_model=GamePreviewResponse)
async def get_game_preview(game_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT g.game_date, g.home_team_id, g.away_team_id,
                       g.home_probable_pitcher, g.away_probable_pitcher,
                       g.status, g.start_time_et,
                       ml.home_moneyline_close, ml.away_moneyline_close,
                       ml.total_close,
                       COALESCE(sr.home_win_prob, 0) AS home_win_prob,
                       COALESCE(sr.away_win_prob, 0) AS away_win_prob,
                       ml.sharp_money_flag, ml.rlm_flag
                FROM games g
                LEFT JOIN LATERAL (
                    SELECT home_moneyline_close, away_moneyline_close,
                           total_close, sharp_money_flag, rlm_flag
                    FROM market_lines
                    WHERE game_id = g.game_id
                    ORDER BY recorded_at DESC
                    LIMIT 1
                ) ml ON TRUE
                LEFT JOIN simulation_results sr ON sr.game_id = g.game_id
                WHERE g.game_id = :gid
            """),
            {"gid": game_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Game not found")

    return GamePreviewResponse(
        game_id=game_id,
        game_date=str(row[0]) if row[0] else "",
        home_team=row[1] or "",
        away_team=row[2] or "",
        home_pitcher_id=row[3],
        away_pitcher_id=row[4],
        status=row[5] or "",
        start_time=_to_local_tz(str(row[6])) if row[6] else "",
        home_moneyline=row[7],
        away_moneyline=row[8],
        total=float(row[9]) if row[9] else None,
        home_win_prob=float(row[10]) if row[10] else None,
        away_win_prob=float(row[11]) if row[11] else None,
        sharp_money_flag=bool(row[12]) if row[12] else False,
        rlm_flag=bool(row[13]) if row[13] else False,
    )


@router.get("/preview", response_model=List[GamePreviewResponse])
async def list_todays_games(date: Optional[str] = Query(None)):
    from datetime import date as d
    target = date or d.today().isoformat()

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT g.game_id, g.game_date, g.home_team_id, g.away_team_id,
                       g.home_probable_pitcher, g.away_probable_pitcher,
                       g.status, g.start_time_et,
                       ml.home_moneyline_close, ml.away_moneyline_close,
                       ml.total_close,
                       COALESCE(sr.home_win_prob, 0) AS home_win_prob,
                       COALESCE(sr.away_win_prob, 0) AS away_win_prob,
                       ml.sharp_money_flag, ml.rlm_flag
                FROM games g
                LEFT JOIN LATERAL (
                    SELECT home_moneyline_close, away_moneyline_close,
                           total_close, sharp_money_flag, rlm_flag
                    FROM market_lines
                    WHERE game_id = g.game_id
                    ORDER BY recorded_at DESC
                    LIMIT 1
                ) ml ON TRUE
                LEFT JOIN simulation_results sr ON sr.game_id = g.game_id
                WHERE g.game_date = :gd
                ORDER BY g.start_time_et
            """),
            {"gd": target},
        ).fetchall()

    return [
        GamePreviewResponse(
            game_id=r[0], game_date=str(r[1]) or "",
            home_team=r[2] or "", away_team=r[3] or "",
            home_pitcher_id=r[4], away_pitcher_id=r[5],
            status=r[6] or "", start_time=_to_local_tz(str(r[7])) if r[7] else "",
            home_moneyline=r[8], away_moneyline=r[9],
            total=float(r[10]) if r[10] else None,
            home_win_prob=float(r[11]) if r[11] else None,
            away_win_prob=float(r[12]) if r[12] else None,
            sharp_money_flag=bool(r[13]) if r[13] else False,
            rlm_flag=bool(r[14]) if r[14] else False,
        )
        for r in rows
    ]


@router.get("/teams/{team_id}")
async def get_team_stats(team_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, league, division, ballpark FROM teams WHERE team_id = :tid"),
            {"tid": team_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Team not found")

    return {"team_id": team_id, "name": row[0], "league": row[1],
            "division": row[2], "ballpark": row[3]}


@router.get("/pitchers/{pitcher_id}/fatigue")
async def get_pitcher_fatigue(pitcher_id: int):
    from features.fatigue_detector import FatigueDetector
    from datetime import date, timedelta

    engine = get_engine()
    with engine.connect() as conn:
        velo_row = conn.execute(
            text("""
                SELECT AVG(p.release_speed) AS avg_velo
                FROM pitches p
                JOIN at_bats ab ON ab.ab_id = p.ab_id
                WHERE ab.pitcher_id = :pid
                  AND p.release_speed IS NOT NULL
            """),
            {"pid": pitcher_id},
        ).fetchone()

    avg_velo = float(velo_row[0]) if velo_row and velo_row[0] else 93.0
    detector = FatigueDetector()
    fatigue = detector.evaluate_pitcher_fatigue(
        recent_avg_velo=avg_velo,
        baseline_avg_velo=avg_velo,
        recent_avg_spin=2200.0,
        baseline_avg_spin=2200.0,
        pitch_count_7d=0,
        travel_miles=0,
        tz_crossings=0,
        rest_days=3,
        is_day_after_night=False,
    )

    return {
        "pitcher_id": pitcher_id,
        "fatigue_score": fatigue.overall_fatigue,
        "is_high_risk": fatigue.is_high_risk,
        "components": fatigue.components,
    }


@router.get("/market/sharp-money")
async def get_sharp_money_signals(
    game_id: Optional[str] = Query(None),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
):
    engine = get_engine()
    query = """
        SELECT DISTINCT ON (ml.game_id)
            ml.game_id,
            CASE
                WHEN ml.sharp_money_flag THEN 'SHARP_MONEY'
                WHEN ml.rlm_flag THEN 'RLM'
                ELSE 'NONE'
            END AS signal_type
        FROM market_lines ml
        WHERE (ml.sharp_money_flag = TRUE OR ml.rlm_flag = TRUE)
    """
    params = {}
    if game_id:
        query += " AND ml.game_id = :gid"
        params["gid"] = game_id
    query += " ORDER BY ml.game_id, ml.recorded_at DESC"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()

    return [
        {"game_id": r[0], "signal_type": r[1], "confidence": min_confidence}
        for r in rows if r[1] != "NONE"
    ]


# ============================================================================
# LIVE DATA FROM MLB API (fallback cuando DB está vacía)
# ============================================================================

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_GAME_URL = "https://statsapi.mlb.com/api/v1.1/game"
MLB_TEAMS_URL = "https://statsapi.mlb.com/api/v1/teams"


def _short_team_name(name: str) -> str:
    """Extrae código corto del nombre del equipo (Cleveland Guardians → CLE)"""
    name_map = {
        "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL",
        "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
        "Chicago Cubs": "CHC", "Chicago White Sox": "CHW",
        "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
        "Colorado Rockies": "COL", "Detroit Tigers": "DET",
        "Houston Astros": "HOU", "Kansas City Royals": "KC",
        "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD",
        "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
        "Minnesota Twins": "MIN", "New York Yankees": "NYY",
        "New York Mets": "NYM", "Oakland Athletics": "OAK",
        "Athletics": "OAK",
        "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT",
        "San Diego Padres": "SD", "San Francisco Giants": "SF",
        "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
        "Tampa Bay Rays": "TB", "Texas Rangers": "TEX",
        "Toronto Blue Jays": "TOR", "Washington Nationals": "WSH",
    }
    return name_map.get(name, name.split()[-1][:3].upper())


def _make_game_id(away_name: str, home_name: str, date_str: str) -> str:
    """Crea game_id en formato CLEBOS250615"""
    yymmdd = date_str.replace("-", "")[2:]
    return f"{_short_team_name(away_name)}{_short_team_name(home_name)}{yymmdd}"


def _parse_mlb_game(game: dict) -> dict:
    """Convierte un game de la MLB API al formato del frontend"""
    status_obj = game.get("status", {})
    teams = game.get("teams", {})
    away = teams.get("away", {}).get("team", {})
    home = teams.get("home", {}).get("team", {})
    away_pitcher = teams.get("away", {}).get("probablePitcher", {}) or {}
    home_pitcher = teams.get("home", {}).get("probablePitcher", {}) or {}
    venue = game.get("venue", {}) or {}
    date_str = game.get("gameDate", "")[:10]

    home_name = home.get("name", "???")
    away_name = away.get("name", "???")
    home_short = _short_team_name(home_name)
    away_short = _short_team_name(away_name)

    game_id = _make_game_id(away_name, home_name, date_str or d.today().isoformat())

    return {
        "game_id": game_id,
        "game_pk": game.get("gamePk"),
        "game_date": date_str,
        "home_team": home_short,
        "away_team": away_short,
        "home_team_name": home_name,
        "away_team_name": away_name,
        "home_pitcher_id": home_pitcher.get("fullName", ""),
        "away_pitcher_id": away_pitcher.get("fullName", ""),
        "status": status_obj.get("detailedState", "UNKNOWN"),
        "status_code": status_obj.get("codedState", ""),
        "start_time": game.get("gameDate", ""),
        "venue": venue.get("name", ""),
        "home_score": teams.get("home", {}).get("score"),
        "away_score": teams.get("away", {}).get("score"),
        "inning": status_obj.get("inning", ""),
        "is_live": status_obj.get("abstractGameState") == "Live",
    }


@router.get("/live/schedule")
async def get_live_schedule(date: Optional[str] = None):
    """Obtiene el calendario en vivo desde la API pública de MLB"""
    target = date or d.today().isoformat()
    try:
        resp = http_requests.get(
            MLB_SCHEDULE_URL,
            params={"sportId": 1, "date": target},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"MLB API schedule failed: {e}")
        raise HTTPException(status_code=502, detail="No se pudo obtener el calendario de MLB")

    games = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            parsed = _parse_mlb_game(game)
            parsed["start_time"] = _to_local_tz(parsed["start_time"])
            games.append(parsed)

    return games


@router.get("/live/schedule/{game_pk}")
async def get_live_game(game_pk: int):
    """Obtiene detalle de un juego en vivo desde la API pública de MLB"""
    try:
        resp = http_requests.get(
            f"{MLB_GAME_URL}/{game_pk}/feed/live",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"MLB API game feed failed: {e}")
        raise HTTPException(status_code=502, detail="No se pudo obtener el detalle del juego")

    game_data = data.get("gameData", {})
    live_data = data.get("liveData", {})
    linescore = live_data.get("linescore", {})
    boxscore = live_data.get("boxscore", {})

    away_team = game_data.get("teams", {}).get("away", {})
    home_team = game_data.get("teams", {}).get("home", {})
    status_obj = game_data.get("status", {})

    result = _parse_mlb_game(game_data)
    result["start_time"] = _to_local_tz(result["start_time"])

    result["home_score"] = linescore.get("teams", {}).get("home", {}).get("runs")
    result["away_score"] = linescore.get("teams", {}).get("away", {}).get("runs")
    result["inning"] = linescore.get("currentInning")
    result["inning_state"] = linescore.get("inningState")
    result["outs"] = linescore.get("outs")

    # Probables pitchers desde gameData
    probable = game_data.get("probablePitchers", {})
    if probable.get("away"):
        result["away_pitcher_id"] = probable["away"].get("fullName", "")
    if probable.get("home"):
        result["home_pitcher_id"] = probable["home"].get("fullName", "")

    return result
