"""Construye BatterState/PitcherState desde la base de datos."""

import logging
from datetime import date
from typing import List, Tuple

import numpy as np
from sqlalchemy import create_engine, text

from prediction.monte_carlo_simulator import BatterState, PitcherState

logger = logging.getLogger(__name__)


class IncompleteLineupError(Exception):
    """Se lanza cuando un equipo no tiene los 9 bateadores confirmados en el lineup."""
    pass


def fetch_league_avg_probs(engine) -> np.ndarray | None:
    """Consulta la BD y calcula probabilidades promedio reales de la liga (últimos 30 días)."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT
                        COALESCE(AVG(prs.k_per_9_30d) / 27.0, 0.225) AS league_k_rate,
                        COALESCE(AVG(prs.bb_per_9_30d) / 27.0, 0.085) AS league_bb_rate,
                        COALESCE(AVG(prs.hr_per_9_30d) / 27.0, 0.030) AS league_hr_rate
                    FROM player_rolling_stats prs
                    WHERE prs.k_per_9_30d IS NOT NULL
                      AND prs.as_of_date >= CURRENT_DATE - 30
                """),
            ).fetchone()
        k_rate = float(row[0]) if row and row[0] else 0.225
        bb_rate = float(row[1]) if row and row[1] else 0.085
        hr_rate = float(row[2]) if row and row[2] else 0.030

        single_rate = 0.155
        double_rate = 0.045
        triple_rate = 0.005
        hbp_rate = 0.010
        sac_rate = 0.045
        out_rate = max(0.0, 1.0 - k_rate - bb_rate - hr_rate - single_rate - double_rate - triple_rate - hbp_rate - sac_rate)

        probs = np.array([out_rate, single_rate, double_rate, triple_rate, hr_rate, bb_rate, hbp_rate, sac_rate])
        return probs / probs.sum()
    except Exception as e:
        logger.warning(f"Could not fetch league avg probs from DB: {e}")
        return None


# Valores por defecto liga
_LEAGUE_AVG_WOBA = 0.310
_LEAGUE_AVG_K_RATE = 0.225
_LEAGUE_AVG_BB_RATE = 0.080
_LEAGUE_AVG_HR_RATE = 0.030
_LEAGUE_AVG_GB_RATE = 0.440
_LEAGUE_AVG_FB_RATE = 0.350
_LEAGUE_AVG_WHIFF_PCT = 0.110
_LEAGUE_AVG_VELO = 93.0
_LEAGUE_AVG_SPIN = 2200.0


def _fetch_pitcher_state(engine, pitcher_id: int, target_date: date) -> PitcherState:
    row = None
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT prs.k_pct_pitch_30d, prs.bb_pct_pitch_30d,
                       prs.hr_per_9_30d, prs.whiff_pct_30d,
                       prs.avg_velo_30d, prs.avg_spin_30d,
                       prs.days_rested, prs.pitches_last_7d,
                       prs.k_per_9_30d, prs.bb_per_9_30d, prs.fip_30d,
                       p.throws, p.full_name
                FROM player_rolling_stats prs
                JOIN players p ON p.player_id = prs.player_id
                WHERE prs.player_id = :pid
                  AND prs.as_of_date <= :gd
                ORDER BY prs.as_of_date DESC
                LIMIT 1
            """),
            {"pid": pitcher_id, "gd": target_date.isoformat()},
        )
        row = result.fetchone()

    if row:
        (
            k_pct,
            bb_pct,
            hr_per_9,
            whiff_pct,
            velo,
            spin,
            days_rested,
            pitches_l7,
            k_9,
            bb_9,
            fip,
            throws,
            name,
        ) = row
        name = name or f"Pitcher_{pitcher_id}"
        k_rate = (float(k_pct) if k_pct is not None else _LEAGUE_AVG_K_RATE * 100) / 100.0
        bb_rate = (float(bb_pct) if bb_pct is not None else _LEAGUE_AVG_BB_RATE * 100) / 100.0
        hr_rate = float(hr_per_9) if hr_per_9 is not None else _LEAGUE_AVG_HR_RATE
        whiff = (float(whiff_pct) if whiff_pct is not None else _LEAGUE_AVG_WHIFF_PCT * 100) / 100.0
        avg_velo = float(velo) if velo is not None else _LEAGUE_AVG_VELO
        avg_spin = float(spin) if spin is not None else _LEAGUE_AVG_SPIN
        rest = int(days_rested) if days_rested is not None else 0
        p7 = int(pitches_l7) if pitches_l7 is not None else 0
        k_per_9 = float(k_9) if k_9 is not None else 8.0
        bb_per_9 = float(bb_9) if bb_9 is not None else 3.0
        fip_val = float(fip) if fip is not None else 4.50
        fatigue = 1.0
        if rest < 4:
            fatigue -= (4 - rest) * 0.05
        if p7 > 100:
            fatigue -= (p7 - 100) * 0.001
        fatigue = max(0.75, min(1.0, fatigue))
    else:
        name = f"Pitcher_{pitcher_id}"
        throws = "R"
        k_rate = _LEAGUE_AVG_K_RATE
        bb_rate = _LEAGUE_AVG_BB_RATE
        hr_rate = _LEAGUE_AVG_HR_RATE
        whiff = _LEAGUE_AVG_WHIFF_PCT
        avg_velo = _LEAGUE_AVG_VELO
        avg_spin = _LEAGUE_AVG_SPIN
        fatigue = 1.0
        k_per_9 = 8.0
        bb_per_9 = 3.0
        fip_val = 4.50

    return PitcherState(
        player_id=pitcher_id,
        name=name,
        throws=throws or "R",
        k_rate=round(k_rate, 3),
        bb_rate=round(bb_rate, 3),
        hr_rate=round(hr_rate, 3),
        whiff_pct=round(whiff, 3),
        avg_velo=round(avg_velo, 1),
        avg_spin=round(avg_spin, 1),
        fatigue_factor=round(fatigue, 3),
        k_per_9_30d=round(k_per_9, 1),
        bb_per_9_30d=round(bb_per_9, 1),
        hr_per_9_30d=round(hr_rate, 1),
        fip_30d=round(fip_val, 2),
        avg_velo_30d=round(avg_velo, 1),
        whiff_pct_30d=round(whiff * 100, 1),
    )


def _fetch_team_lineup(engine, team_id: str, target_date: date) -> list[BatterState]:
    rows = []
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT l.player_id, l.batting_order,
                       brs.woba_30d, brs.k_pct_30d,
                       brs.bb_pct_30d, brs.hr_per_9_30d,
                       brs.groundball_pct_30d, brs.flyball_pct_30d,
                       p.bats, p.full_name
                FROM lineups l
                JOIN players p ON p.player_id = l.player_id
                LEFT JOIN batter_rolling_stats brs
                    ON brs.player_id = l.player_id
                    AND brs.as_of_date = (
                        SELECT MAX(brs2.as_of_date)
                        FROM batter_rolling_stats brs2
                        WHERE brs2.player_id = l.player_id
                          AND brs2.as_of_date <= :gd
                    )
                WHERE l.team_id = :tid
                  AND l.game_id LIKE :gid_pattern
                  AND l.is_starter = TRUE
                ORDER BY l.batting_order
            """),
            {"tid": team_id, "gd": target_date.isoformat(), "gid_pattern": f"{target_date.isoformat().replace('-', '')}%"},
        )
        rows = result.fetchall()

    lineups = []
    for (
        pid,
        order,
        woba_30d,
        k_pct,
        bb_pct,
        hr_per_9,
        gb_pct,
        fb_pct,
        bats,
        name,
    ) in rows:
        name = name or f"Player_{pid}"
        k_rate = (float(k_pct) if k_pct is not None else _LEAGUE_AVG_K_RATE * 100) / 100.0
        bb_rate = (float(bb_pct) if bb_pct is not None else _LEAGUE_AVG_BB_RATE * 100) / 100.0
        hr_rate = float(hr_per_9) if hr_per_9 is not None else _LEAGUE_AVG_HR_RATE
        gb_rate = (float(gb_pct) if gb_pct is not None else _LEAGUE_AVG_GB_RATE * 100) / 100.0
        fb_rate = (float(fb_pct) if fb_pct is not None else _LEAGUE_AVG_FB_RATE * 100) / 100.0

        woba_vs = float(woba_30d) if woba_30d is not None else _LEAGUE_AVG_WOBA
        lineups.append(
            BatterState(
                player_id=pid,
                name=name,
                bats=bats or "R",
                woba_vs_rhp=round(woba_vs, 3),
                woba_vs_lhp=round(woba_vs * 0.95, 3),
                k_rate=round(k_rate, 3),
                bb_rate=round(bb_rate, 3),
                hr_rate=round(hr_rate, 3),
                groundball_rate=round(gb_rate, 3),
                flyball_rate=round(fb_rate, 3),
                woba_30d=round(woba_vs, 3),
                k_pct_30d=round(k_rate * 100, 1),
                bb_pct_30d=round(bb_rate * 100, 1),
            )
        )

    if len(lineups) < 9:
        raise IncompleteLineupError(
            f"Team {team_id} has only {len(lineups)} confirmed batters "
            f"on {target_date} (need 9)"
        )

    return lineups


def build_player_states_from_db(
    engine,
    game_id: str,
    home_team_id: str,
    away_team_id: str,
    home_pitcher_id: int,
    away_pitcher_id: int,
    target_date: date,
) -> tuple[list[BatterState], list[BatterState], PitcherState, PitcherState]:

    home_pitcher = _fetch_pitcher_state(engine, home_pitcher_id, target_date)
    away_pitcher = _fetch_pitcher_state(engine, away_pitcher_id, target_date)

    home_lineup = _fetch_team_lineup(engine, home_team_id, target_date)
    away_lineup = _fetch_team_lineup(engine, away_team_id, target_date)

    return home_lineup, away_lineup, home_pitcher, away_pitcher
