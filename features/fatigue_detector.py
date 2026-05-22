# =============================================================================
# fatigue_detector.py
# Detección de Fatiga de Jugadores MLB
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Detecta señales de fatiga que afectan el rendimiento:
#   - Viajes cruzando zonas horarias (timezone crossings)
#   - Juegos de día tras juegos de noche (day-after-night)
#   - Caídas recientes en velocidad del lanzamiento (velo drop)
#   - Caídas en spin rate (fatiga de brazo)
#   - Alta carga de lanzamientos (pitch count)
#   - Poco descanso (short rest)
# =============================================================================

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class FatigueScore:
    player_id: int
    player_name: str
    game_id: str
    game_date: date
    overall_fatigue: float  # 0.0 (descansado) a 1.0 (máxima fatiga)
    components: Dict[str, float] = field(default_factory=dict)
    rest_days: int = 0
    tz_crossings: int = 0
    travel_miles: int = 0
    velo_drop: float = 0.0
    spin_drop: float = 0.0
    pitch_count_recent: int = 0
    innings_recent: float = 0.0
    day_game_after_night: bool = False
    is_high_risk: bool = False


class FatigueDetector:
    VELO_DROP_THRESHOLD = 1.5  # mph
    SPIN_DROP_THRESHOLD = 150  # rpm
    HIGH_PITCH_COUNT = 100
    TZ_CROSSING_FATIGUE = 0.08  # por zona horaria
    TRAVEL_MILES_FATIGUE = 0.0001  # por milla
    DAY_AFTER_NIGHT_PENALTY = 0.10

    def __init__(self):
        logger.info("FatigueDetector initialized")

    def evaluate_pitcher_fatigue(
        self,
        player_id: int,
        player_name: str,
        game_id: str,
        game_date: date,
        rest_days: int,
        avg_velo_last_30d: float,
        avg_velo_last_3g: float,
        avg_spin_last_30d: float,
        avg_spin_last_3g: float,
        pitches_thrown_last_7d: int,
        innings_pitched_last_7d: float,
        tz_crossings_last_3d: int = 0,
        travel_miles_last_3d: int = 0,
        is_day_game_after_night: bool = False,
    ) -> FatigueScore:

        velo_drop = avg_velo_last_30d - avg_velo_last_3g
        spin_drop = avg_spin_last_30d - avg_spin_last_3g

        components = {}
        total_fatigue = 0.0

        # --- Rest days (inverso: menos descanso = más fatiga) ---
        rest_score = max(0, (5 - rest_days) / 5.0)
        if rest_days <= 3:
            rest_score = 0.3 + (4 - rest_days) * 0.15
        elif rest_days >= 6:
            rest_score = 0.0
        else:
            rest_score = max(0, (5 - rest_days) * 0.1)
        components["rest_score"] = round(rest_score, 3)
        total_fatigue += rest_score * 0.25

        # --- Velo drop ---
        if velo_drop > self.VELO_DROP_THRESHOLD:
            velo_score = min(1.0, (velo_drop - self.VELO_DROP_THRESHOLD) / 3.0)
        elif velo_drop > 0:
            velo_score = velo_drop / self.VELO_DROP_THRESHOLD * 0.3
        else:
            velo_score = 0.0
        components["velo_drop_score"] = round(velo_score, 3)
        total_fatigue += velo_score * 0.30

        # --- Spin drop ---
        if spin_drop > self.SPIN_DROP_THRESHOLD:
            spin_score = min(1.0, (spin_drop - self.SPIN_DROP_THRESHOLD) / 300.0)
        elif spin_drop > 0:
            spin_score = spin_drop / self.SPIN_DROP_THRESHOLD * 0.3
        else:
            spin_score = 0.0
        components["spin_drop_score"] = round(spin_score, 3)
        total_fatigue += spin_score * 0.20

        # --- Pitch count load ---
        pitch_score = min(1.0, pitches_thrown_last_7d / 200.0)
        components["pitch_load_score"] = round(pitch_score, 3)
        total_fatigue += pitch_score * 0.10

        # --- Travel fatigue ---
        tz_score = min(1.0, tz_crossings_last_3d * self.TZ_CROSSING_FATIGUE)
        travel_score = min(0.3, travel_miles_last_3d * self.TRAVEL_MILES_FATIGUE)
        components["tz_crossing_score"] = round(tz_score, 3)
        components["travel_miles_score"] = round(travel_score, 3)
        total_fatigue += tz_score * 0.08
        total_fatigue += travel_score * 0.05

        # --- Day game after night ---
        if is_day_game_after_night:
            total_fatigue += self.DAY_AFTER_NIGHT_PENALTY
            components["day_after_night"] = self.DAY_AFTER_NIGHT_PENALTY

        overall = round(min(1.0, total_fatigue), 3)

        return FatigueScore(
            player_id=player_id,
            player_name=player_name,
            game_id=game_id,
            game_date=game_date,
            overall_fatigue=overall,
            components=components,
            rest_days=rest_days,
            tz_crossings=tz_crossings_last_3d,
            travel_miles=travel_miles_last_3d,
            velo_drop=round(velo_drop, 2),
            spin_drop=round(spin_drop, 1),
            pitch_count_recent=pitches_thrown_last_7d,
            innings_recent=innings_pitched_last_7d,
            day_game_after_night=is_day_game_after_night,
            is_high_risk=overall > 0.40,
        )

    def evaluate_batter_fatigue(
        self,
        player_id: int,
        player_name: str,
        game_id: str,
        game_date: date,
        rest_days: int,
        woba_last_14d: float,
        woba_last_7d: float,
        hard_hit_pct_last_14d: float,
        hard_hit_pct_last_7d: float,
        tz_crossings_last_3d: int = 0,
        travel_miles_last_3d: int = 0,
        is_day_game_after_night: bool = False,
    ) -> FatigueScore:

        components = {}
        total_fatigue = 0.0

        rest_score = max(0, (5 - rest_days) / 5.0)
        total_fatigue += rest_score * 0.30

        woba_drop = max(0, woba_last_14d - woba_last_7d)
        woba_score = min(0.5, woba_drop * 3.0)
        components["woba_drop_score"] = round(woba_score, 3)
        total_fatigue += woba_score * 0.30

        hard_hit_drop = max(0, hard_hit_pct_last_14d - hard_hit_pct_last_7d)
        hard_hit_score = min(0.5, hard_hit_drop * 2.0)
        components["hard_hit_drop"] = round(hard_hit_score, 3)
        total_fatigue += hard_hit_score * 0.15

        tz_score = min(1.0, tz_crossings_last_3d * self.TZ_CROSSING_FATIGUE)
        total_fatigue += tz_score * 0.10

        if is_day_game_after_night:
            total_fatigue += self.DAY_AFTER_NIGHT_PENALTY
            components["day_after_night"] = self.DAY_AFTER_NIGHT_PENALTY

        overall = round(min(1.0, total_fatigue), 3)

        return FatigueScore(
            player_id=player_id,
            player_name=player_name,
            game_id=game_id,
            game_date=game_date,
            overall_fatigue=overall,
            components=components,
            rest_days=rest_days,
            tz_crossings=tz_crossings_last_3d,
            travel_miles=travel_miles_last_3d,
            is_high_risk=overall > 0.45,
        )

    def query_travel_fatigue_sql(self, team_ids: List[str], game_date: date) -> str:
        team_list = ", ".join(f"'{t}'" for t in team_ids)
        return f"""
        WITH team_games AS (
            SELECT
                g.game_id,
                g.game_date,
                g.home_team_id,
                g.away_team_id,
                g.home_travel_miles,
                g.away_travel_miles,
                g.home_tz_crossings,
                g.away_tz_crossings,
                g.home_day_game_after_night,
                g.away_day_game_after_night,
                g.home_rest_days,
                g.away_rest_days,
                ROW_NUMBER() OVER (
                    PARTITION BY g.home_team_id ORDER BY g.game_date DESC
                ) AS rn_home,
                ROW_NUMBER() OVER (
                    PARTITION BY g.away_team_id ORDER BY g.game_date DESC
                ) AS rn_away
            FROM games g
            WHERE (g.home_team_id IN ({team_list}) OR g.away_team_id IN ({team_list}))
              AND g.game_date <= '{game_date}'
              AND g.status = 'FINAL'
        )
        SELECT
            tg.game_id,
            teams.team_id,
            teams.full_name,
            CASE
                WHEN tg.home_team_id = teams.team_id THEN tg.home_travel_miles
                ELSE tg.away_travel_miles
            END AS travel_miles,
            CASE
                WHEN tg.home_team_id = teams.team_id THEN tg.home_tz_crossings
                ELSE tg.away_tz_crossings
            END AS tz_crossings,
            CASE
                WHEN tg.home_team_id = teams.team_id THEN tg.home_day_game_after_night
                ELSE tg.away_day_game_after_night
            END AS day_after_night,
            CASE
                WHEN tg.home_team_id = teams.team_id THEN tg.home_rest_days
                ELSE tg.away_rest_days
            END AS rest_days
        FROM team_games tg
        JOIN teams ON (
            (tg.home_team_id = teams.team_id AND tg.rn_home <= 5)
            OR (tg.away_team_id = teams.team_id AND tg.rn_away <= 5)
        )
        WHERE teams.team_id IN ({team_list})
        ORDER BY teams.team_id, tg.game_date DESC;
        """

    def query_velo_spin_drop_sql(self, pitcher_id: int, game_date: date) -> str:
        return f"""
        WITH recent_games AS (
            SELECT
                g.game_id,
                g.game_date,
                AVG(p.release_speed) AS avg_velo,
                AVG(p.release_spin_rate) AS avg_spin,
                COUNT(p.pitch_id) AS total_pitches,
                ROW_NUMBER() OVER (ORDER BY g.game_date DESC) AS rn
            FROM games g
            JOIN at_bats ab ON ab.game_id = g.game_id
            JOIN pitches p ON p.ab_id = ab.ab_id
            WHERE ab.pitcher_id = {pitcher_id}
              AND g.game_date <= '{game_date}'
              AND g.status = 'FINAL'
              AND g.game_date >= '{game_date}'::DATE - INTERVAL '45 days'
            GROUP BY g.game_id, g.game_date
        )
        SELECT
            rn,
            game_date,
            avg_velo,
            avg_spin,
            total_pitches,
            AVG(avg_velo) OVER (ORDER BY rn ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS baseline_velo_30d,
            AVG(avg_spin) OVER (ORDER BY rn ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS baseline_spin_30d,
            AVG(avg_velo) OVER (ORDER BY rn ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS recent_velo_3g,
            AVG(avg_spin) OVER (ORDER BY rn ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS recent_spin_3g
        FROM recent_games
        ORDER BY game_date DESC
        LIMIT 1;
        """


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    detector = FatigueDetector()

    result = detector.evaluate_pitcher_fatigue(
        player_id=100,
        player_name="Gerrit Cole",
        game_id="2025-06-15-NYY-BOS",
        game_date=date(2025, 6, 15),
        rest_days=4,
        avg_velo_last_30d=96.2,
        avg_velo_last_3g=94.8,
        avg_spin_last_30d=2550,
        avg_spin_last_3g=2380,
        pitches_thrown_last_7d=185,
        innings_pitched_last_7d=12.0,
        tz_crossings_last_3d=2,
        travel_miles_last_3d=2800,
        is_day_game_after_night=True,
    )

    print(f"Fatiga de {result.player_name}: {result.overall_fatigue:.2%}")
    print(f"  High risk: {result.is_high_risk}")
    print(f"  Componentes: {result.components}")
    print(f"  Velo drop: {result.velo_drop} mph")
    print(f"  Spin drop: {result.spin_drop} rpm")
    print(f"  Descanso: {result.rest_days} dias")
