# =============================================================================
# advanced_stats.py
# Métricas Avanzadas de Béisbol (wOBA, FIP, xERA)
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Implementación de estadísticas modernas de evaluación de jugadores:
#   - wOBA (weighted On-Base Average) con splits vs LHP/RHP
#   - FIP (Fielding Independent Pitching)
#   - xERA (Expected ERA basado en calidad de contacto Statcast)
#
# Todas las funciones aceptan tanto DataFrames de pandas como valores
# escalares para flexibilidad en pipeline batch o streaming.
# =============================================================================

import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================================
# PESOS OFICIALES wOBA (FanGraphs / MLB)
# ============================================================================
# Los pesos varían ligeramente cada año. Estos son los valores 2024.
# Actualizar anualmente con los coeficientes publicados por FanGraphs.

WOBA_WEIGHTS = {
    2024: {
        "walk": 0.690,
        "hit_by_pitch": 0.720,
        "single": 0.870,
        "double": 1.220,
        "triple": 1.580,
        "home_run": 2.020,
        "out": 0.000,
    },
    2023: {
        "walk": 0.688,
        "hit_by_pitch": 0.718,
        "single": 0.870,
        "double": 1.221,
        "triple": 1.575,
        "home_run": 2.018,
        "out": 0.000,
    },
    2022: {
        "walk": 0.686,
        "hit_by_pitch": 0.715,
        "single": 0.868,
        "double": 1.220,
        "triple": 1.570,
        "home_run": 2.015,
        "out": 0.000,
    },
}

# ============================================================================
# CONSTANTES DE LIGA
# ============================================================================

LEAGUE_AVG_WOBA = 0.310
LEAGUE_AVG_FIP = 4.20
LEAGUE_AVG_ERA = 4.30
LEAGUE_AVG_K_PER_9 = 8.70
LEAGUE_AVG_BB_PER_9 = 3.20
LEAGUE_AVG_HR_PER_9 = 1.20


# ============================================================================
# FUNCIONES wOBA
# ============================================================================


def calculate_woba(
    walks: int | pd.Series,
    hit_by_pitch: int | pd.Series,
    singles: int | pd.Series,
    doubles: int | pd.Series,
    triples: int | pd.Series,
    home_runs: int | pd.Series,
    at_bats: int | pd.Series,
    sacrifice_flys: int | pd.Series | None = None,
    season: int = 2024,
) -> float | pd.Series:
    weights = WOBA_WEIGHTS.get(season, WOBA_WEIGHTS[2024])
    numerator = (
        weights["walk"] * walks
        + weights["hit_by_pitch"] * hit_by_pitch
        + weights["single"] * singles
        + weights["double"] * doubles
        + weights["triple"] * triples
        + weights["home_run"] * home_runs
    )
    denominator = at_bats + walks + hit_by_pitch + (sacrifice_flys or 0)
    if isinstance(denominator, pd.Series):
        return numerator / denominator.replace(0, np.nan)
    return numerator / denominator if denominator > 0 else 0.0


def calculate_woba_with_splits(
    stats_vs_lhp: dict[str, int],
    stats_vs_rhp: dict[str, int],
    season: int = 2024,
) -> dict[str, float]:

    woba_vs_lhp = calculate_woba(**stats_vs_lhp, season=season)
    woba_vs_rhp = calculate_woba(**stats_vs_rhp, season=season)
    combined = {
        k: (stats_vs_lhp.get(k, 0) + stats_vs_rhp.get(k, 0))
        for k in set(stats_vs_lhp) | set(stats_vs_rhp)
    }
    total_pa = (
        combined.get("at_bats", 0) + combined.get("walks", 0) + combined.get("hit_by_pitch", 0)
    )
    if "walks" in stats_vs_lhp and "walks" in stats_vs_rhp:
        lhp_pa = (
            stats_vs_lhp.get("at_bats", 0)
            + stats_vs_lhp.get("walks", 0)
            + stats_vs_lhp.get("hit_by_pitch", 0)
        )
        rhp_pa = (
            stats_vs_rhp.get("at_bats", 0)
            + stats_vs_rhp.get("walks", 0)
            + stats_vs_rhp.get("hit_by_pitch", 0)
        )
    else:
        lhp_pa = rhp_pa = 0

    return {
        "woba_vs_lhp": round(woba_vs_lhp, 3),
        "woba_vs_rhp": round(woba_vs_rhp, 3),
        "lhp_pa": lhp_pa,
        "rhp_pa": rhp_pa,
    }


def calculate_xwoba(
    launch_speed: float | pd.Series,
    launch_angle: float | pd.Series,
    sprint_speed: float | pd.Series | None = None,
) -> float | pd.Series:

    if isinstance(launch_speed, pd.Series):
        xwoba = _xwoba_from_statcast(launch_speed.values, launch_angle.values)
        return pd.Series(xwoba, index=launch_speed.index)
    return float(_xwoba_from_statcast(np.array([launch_speed]), np.array([launch_angle]))[0])


def _xwoba_from_statcast(speeds: np.ndarray, angles: np.ndarray) -> np.ndarray:
    # Modelo simplificado de xwOBA basado en velocidad y ángulo de salida
    # Basado en el modelo público de Statcast/Alex Chamberlain
    # Peso: 0.35 * speed_bucket + 0.50 * angle_bucket + 0.15 * interaction
    speed_score = np.clip((speeds - 80) / 40, 0, 1)
    angle_score = np.clip(1 - np.abs(angles - 25) / 35, 0, 1)
    sweet_spot = ((angles >= 8) & (angles <= 32)).astype(float)
    xwoba = (
        0.100
        + 0.350 * speed_score
        + 0.150 * angle_score
        + 0.300 * sweet_spot * speed_score
        + 0.100 * (speeds > 95).astype(float)
    )
    return np.clip(xwoba, 0.000, 2.500)


# ============================================================================
# FUNCIONES FIP
# ============================================================================


def calculate_fip(
    strikeouts: int | pd.Series,
    walks: int | pd.Series,
    hit_by_pitch: int | pd.Series,
    home_runs: int | pd.Series,
    innings_pitched: float | pd.Series,
    use_custom_factor: float | None = None,
    season: int = 2024,
) -> float | pd.Series:

    fip_constant = {
        2024: 3.10,
        2023: 3.12,
        2022: 3.15,
    }.get(season, 3.10)

    if use_custom_factor is not None:
        fip_constant = use_custom_factor

    numerator = 13 * home_runs + 3 * (walks + hit_by_pitch) - 2 * strikeouts

    if isinstance(innings_pitched, pd.Series):
        result = numerator / innings_pitched + fip_constant
        return result.replace([np.inf, -np.inf], np.nan)

    if innings_pitched <= 0:
        return 0.0
    return (numerator / innings_pitched) + fip_constant


def calculate_xera(
    fip: float | pd.Series,
    quality_of_contact: float | pd.Series | None = None,
    defense_rating: float | pd.Series | None = None,
    park_factor: float | pd.Series | None = None,
) -> float | pd.Series:

    era = fip
    if quality_of_contact is not None:
        era = era + (quality_of_contact - 0.300) * 2.0
    if defense_rating is not None:
        era = era - (defense_rating - 0.0) * 0.5
    if park_factor is not None:
        era = era / park_factor
    return era


def calculate_siera(
    strikeouts: int | pd.Series,
    walks: int | pd.Series,
    ground_balls: int | pd.Series,
    fly_balls: int | pd.Series,
    innings_pitched: float | pd.Series,
) -> float | pd.Series:

    k_rate = (
        strikeouts / (innings_pitched * 3)
        if isinstance(strikeouts, (int, float))
        else strikeouts / (innings_pitched * 3)
    )
    bb_rate = (
        walks / (innings_pitched * 3)
        if isinstance(walks, (int, float))
        else walks / (innings_pitched * 3)
    )
    gb_rate = (
        ground_balls / (ground_balls + fly_balls)
        if isinstance(ground_balls, (int, float))
        else ground_balls / (ground_balls + fly_balls)
    )

    siera = 6.0 - 5.0 * k_rate + 3.0 * bb_rate - 1.5 * gb_rate
    return siera


# ============================================================================
# CÁLCULO BATCH SOBRE DATAFRAMES (ROLLING WINDOWS)
# ============================================================================


def compute_rolling_stats(
    df: pd.DataFrame,
    player_col: str = "player_id",
    date_col: str = "game_date",
    windows: list[int] = [7, 14, 30],
    stats_to_compute: list[str] | None = None,
) -> pd.DataFrame:

    if stats_to_compute is None:
        stats_to_compute = ["woba", "fip", "k_pct", "bb_pct"]

    if df.empty:
        return df

    df = df.sort_values([player_col, date_col]).reset_index(drop=True)
    results = []

    for player_id, group in df.groupby(player_col):
        group = group.sort_values(date_col)
        for window in windows:
            rolled = group.rolling(window=window, min_periods=1)
            for stat in stats_to_compute:
                if stat in group.columns:
                    col_name = f"{stat}_{window}d"
                    group[col_name] = rolled[stat].mean()
        results.append(group)

    return pd.concat(results, ignore_index=True)


def compute_woba_rolling(
    events_df: pd.DataFrame,
    player_col: str = "player_id",
    game_col: str = "game_id",
    windows: list[int] = [7, 14, 30],
    season: int = 2024,
) -> pd.DataFrame:

    events = events_df.copy()

    agg = (
        events.groupby([player_col, game_col])
        .agg(
            walks=("events", lambda x: (x == "walk").sum()),
            hit_by_pitch=("events", lambda x: (x == "hit_by_pitch").sum()),
            singles=("events", lambda x: (x == "single").sum()),
            doubles=("events", lambda x: (x == "double").sum()),
            triples=("events", lambda x: (x == "triple").sum()),
            home_runs=("events", lambda x: (x == "home_run").sum()),
            at_bats=(
                "events",
                lambda x: x.isin(
                    [
                        "single",
                        "double",
                        "triple",
                        "home_run",
                        "out",
                        "strikeout",
                        "fielders_choice",
                        "double_play",
                        "triple_play",
                    ]
                ).sum(),
            ),
        )
        .reset_index()
    )

    agg["woba"] = calculate_woba(
        agg["walks"],
        agg["hit_by_pitch"],
        agg["singles"],
        agg["doubles"],
        agg["triples"],
        agg["home_runs"],
        agg["at_bats"],
        season=season,
    )

    for window in windows:
        agg[f"woba_{window}d"] = agg.groupby(player_col)["woba"].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )

    return agg


# ============================================================================
# UTILIDAD
# ============================================================================


def fip_constant_for_season(season: int) -> float:
    return {
        2024: 3.10,
        2023: 3.12,
        2022: 3.15,
        2021: 3.16,
        2020: 3.18,
    }.get(season, 3.14)


def league_adjusted_stats(
    player_stat: float,
    league_avg: float,
    park_factor: float = 1.0,
) -> float:
    return (player_stat / league_avg) * park_factor


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    print("=== MLB Advanced Stats Calculator ===\n")

    woba = calculate_woba(
        walks=85,
        hit_by_pitch=12,
        singles=100,
        doubles=35,
        triples=2,
        home_runs=40,
        at_bats=500,
        sacrifice_flys=8,
        season=2024,
    )
    print(f"wOBA: {woba:.3f}")

    fip = calculate_fip(
        strikeouts=220,
        walks=50,
        hit_by_pitch=8,
        home_runs=25,
        innings_pitched=180.0,
        season=2024,
    )
    print(f"FIP: {fip:.2f}")

    xera = calculate_xera(fip, quality_of_contact=0.320)
    print(f"xERA: {xera:.2f}")

    siera = calculate_siera(
        strikeouts=220,
        walks=50,
        ground_balls=180,
        fly_balls=120,
        innings_pitched=180.0,
    )
    print(f"SIERA: {siera:.2f}")

    splits = calculate_woba_with_splits(
        stats_vs_lhp={
            "walks": 20,
            "hit_by_pitch": 3,
            "singles": 25,
            "doubles": 8,
            "triples": 0,
            "home_runs": 8,
            "at_bats": 130,
            "sacrifice_flys": 2,
        },
        stats_vs_rhp={
            "walks": 65,
            "hit_by_pitch": 9,
            "singles": 75,
            "doubles": 27,
            "triples": 2,
            "home_runs": 32,
            "at_bats": 370,
            "sacrifice_flys": 6,
        },
    )
    print(f"wOBA vs LHP: {splits['woba_vs_lhp']:.3f}")
    print(f"wOBA vs RHP: {splits['woba_vs_rhp']:.3f}")
