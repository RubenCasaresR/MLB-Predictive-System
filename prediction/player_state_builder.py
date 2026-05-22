"""Construye BatterState/PitcherState desde la base de datos."""

import logging
from typing import List, Tuple
from datetime import date
from sqlalchemy import create_engine, text

from prediction.monte_carlo_simulator import BatterState, PitcherState

logger = logging.getLogger(__name__)

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
        k_pct, bb_pct, hr_per_9, whiff_pct, velo, spin, days_rested, pitches_l7, throws, name = row
        name = name or f"Pitcher_{pitcher_id}"
        k_rate = (k_pct or _LEAGUE_AVG_K_RATE * 100) / 100.0
        bb_rate = (bb_pct or _LEAGUE_AVG_BB_RATE * 100) / 100.0
        hr_rate = hr_per_9 if hr_per_9 is not None else _LEAGUE_AVG_HR_RATE
        whiff = (whiff_pct or _LEAGUE_AVG_WHIFF_PCT * 100) / 100.0
        avg_velo = velo or _LEAGUE_AVG_VELO
        avg_spin = spin or _LEAGUE_AVG_SPIN
        fatigue = 1.0
        if days_rested and days_rested < 4:
            fatigue -= (4 - days_rested) * 0.05
        if pitches_l7 and pitches_l7 > 100:
            fatigue -= (pitches_l7 - 100) * 0.001
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
    )


def _fetch_team_lineup(engine, team_id: str, target_date: date) -> List[BatterState]:
    rows = []
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT brs.player_id, brs.woba_30d, brs.k_pct_30d,
                       brs.bb_pct_30d, brs.hr_per_9_30d,
                       brs.groundball_pct_30d, brs.flyball_pct_30d,
                       p.bats, p.full_name
                FROM batter_rolling_stats brs
                JOIN players p ON p.player_id = brs.player_id
                WHERE p.team_id = :tid
                  AND brs.as_of_date = (
                    SELECT MAX(brs2.as_of_date)
                    FROM batter_rolling_stats brs2
                    WHERE brs2.player_id = brs.player_id
                      AND brs2.as_of_date <= :gd
                  )
                ORDER BY brs.woba_30d DESC
                LIMIT 9
            """),
            {"tid": team_id, "gd": target_date.isoformat()},
        )
        rows = result.fetchall()

    lineups = []
    for (
        pid, woba_30d, k_pct, bb_pct, hr_per_9,
        gb_pct, fb_pct, bats, name,
    ) in rows:
        name = name or f"Player_{pid}"
        k_rate = (k_pct or _LEAGUE_AVG_K_RATE * 100) / 100.0
        bb_rate = (bb_pct or _LEAGUE_AVG_BB_RATE * 100) / 100.0
        hr_rate = hr_per_9 if hr_per_9 is not None else _LEAGUE_AVG_HR_RATE
        gb_rate = (gb_pct or _LEAGUE_AVG_GB_RATE * 100) / 100.0
        fb_rate = (fb_pct or _LEAGUE_AVG_FB_RATE * 100) / 100.0

        woba_vs = woba_30d if woba_30d is not None else _LEAGUE_AVG_WOBA
        lineups.append(BatterState(
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
        ))

    return lineups


def _build_placeholder_lineup(team_id: str, team_woba: float, count: int = 9) -> List[BatterState]:
    return [
        BatterState(
            player_id=-(hash(team_id) % 10000 + i),
            name=f"{team_id}_Batter_{i+1}",
            bats=("L" if i % 3 == 0 else "R"),
            woba_vs_rhp=round(team_woba, 3),
            woba_vs_lhp=round(team_woba * 0.95, 3),
        )
        for i in range(count)
    ]


def _fetch_team_avg_woba(engine, team_id: str, target_date: date) -> float:
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT woba_30d
                FROM team_rolling_stats
                WHERE team_id = :tid
                  AND as_of_date <= :gd
                ORDER BY as_of_date DESC
                LIMIT 1
            """),
            {"tid": team_id, "gd": target_date.isoformat()},
        )
        row = result.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    return _LEAGUE_AVG_WOBA


def build_player_states_from_db(
    engine, game_id: str,
    home_team_id: str, away_team_id: str,
    home_pitcher_id: int, away_pitcher_id: int,
    target_date: date,
) -> Tuple[List[BatterState], List[BatterState], PitcherState, PitcherState]:

    home_pitcher = _fetch_pitcher_state(engine, home_pitcher_id, target_date)
    away_pitcher = _fetch_pitcher_state(engine, away_pitcher_id, target_date)

    home_lineup = _fetch_team_lineup(engine, home_team_id, target_date)
    away_lineup = _fetch_team_lineup(engine, away_team_id, target_date)

    if len(home_lineup) < 9:
        team_woba = _fetch_team_avg_woba(engine, home_team_id, target_date)
        needed = 9 - len(home_lineup)
        home_lineup.extend(_build_placeholder_lineup(home_team_id, team_woba, needed))
        logger.info(
            f"Filled {needed} placeholder batters for {home_team_id} "
            f"(team wOBA={team_woba:.3f})"
        )

    if len(away_lineup) < 9:
        team_woba = _fetch_team_avg_woba(engine, away_team_id, target_date)
        needed = 9 - len(away_lineup)
        away_lineup.extend(_build_placeholder_lineup(away_team_id, team_woba, needed))
        logger.info(
            f"Filled {needed} placeholder batters for {away_team_id} "
            f"(team wOBA={team_woba:.3f})"
        )

    return home_lineup, away_lineup, home_pitcher, away_pitcher
