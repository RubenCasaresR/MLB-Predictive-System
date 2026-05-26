"""Tests para advanced_stats.py (wOBA, FIP, xERA, SIERA, xwOBA)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from features.advanced_stats import (
    LEAGUE_AVG_FIP,
    LEAGUE_AVG_WOBA,
    calculate_fip,
    calculate_siera,
    calculate_woba,
    calculate_woba_with_splits,
    calculate_xera,
    calculate_xwoba,
    compute_rolling_stats,
    compute_woba_rolling,
    fip_constant_for_season,
    league_adjusted_stats,
)

# ============================================================================
# wOBA
# ============================================================================


class TestCalculateWoba:
    def test_scalar_known_value(self):
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
        # numerator = 0.690*85 + 0.720*12 + 0.870*100 + 1.220*35 + 1.580*2 + 2.020*40
        # = 58.65 + 8.64 + 87.0 + 42.7 + 3.16 + 80.8 = 280.95
        # denominator = 500 + 85 + 12 + 8 = 605
        # wOBA = 280.95 / 605 = 0.46438...
        assert round(woba, 3) == 0.464

    def test_zero_denominator_returns_zero(self):
        woba = calculate_woba(
            walks=0,
            hit_by_pitch=0,
            singles=0,
            doubles=0,
            triples=0,
            home_runs=0,
            at_bats=0,
            sacrifice_flys=0,
        )
        assert woba == 0.0

    def test_no_sacrifice_flys(self):
        woba = calculate_woba(
            walks=10,
            hit_by_pitch=2,
            singles=10,
            doubles=5,
            triples=1,
            home_runs=3,
            at_bats=50,
        )
        assert round(woba, 3) > 0

    def test_pandas_series(self):
        df = pd.DataFrame(
            {
                "walks": [10, 5],
                "hit_by_pitch": [1, 0],
                "singles": [20, 10],
                "doubles": [5, 3],
                "triples": [0, 1],
                "home_runs": [2, 0],
                "at_bats": [80, 40],
            }
        )
        woba = calculate_woba(
            df["walks"],
            df["hit_by_pitch"],
            df["singles"],
            df["doubles"],
            df["triples"],
            df["home_runs"],
            df["at_bats"],
        )
        assert isinstance(woba, pd.Series)
        assert len(woba) == 2
        assert woba.iloc[0] > 0

    def test_zero_denominator_series_returns_nan(self):
        s = pd.Series([0])
        woba = calculate_woba(s, s, s, s, s, s, s)
        assert pd.isna(woba.iloc[0])

    def test_season_2023_weights(self):
        # 2023 wOBA weights differ slightly
        woba = calculate_woba(
            walks=10,
            hit_by_pitch=1,
            singles=10,
            doubles=5,
            triples=1,
            home_runs=2,
            at_bats=50,
            season=2023,
        )
        woba_2024 = calculate_woba(
            walks=10,
            hit_by_pitch=1,
            singles=10,
            doubles=5,
            triples=1,
            home_runs=2,
            at_bats=50,
            season=2024,
        )
        # Should slightly differ due to weight changes
        assert woba != woba_2024


class TestCalculateWobaWithSplits:
    def test_returns_all_keys(self):
        result = calculate_woba_with_splits(
            stats_vs_lhp={
                "walks": 5,
                "hit_by_pitch": 0,
                "singles": 8,
                "doubles": 2,
                "triples": 0,
                "home_runs": 1,
                "at_bats": 30,
            },
            stats_vs_rhp={
                "walks": 10,
                "hit_by_pitch": 1,
                "singles": 15,
                "doubles": 5,
                "triples": 1,
                "home_runs": 3,
                "at_bats": 70,
            },
        )
        assert "woba_vs_lhp" in result
        assert "woba_vs_rhp" in result
        assert "lhp_pa" in result
        assert "rhp_pa" in result

    def test_splits_differ(self):
        result = calculate_woba_with_splits(
            stats_vs_lhp={
                "walks": 1,
                "hit_by_pitch": 0,
                "singles": 5,
                "doubles": 0,
                "triples": 0,
                "home_runs": 0,
                "at_bats": 30,
            },
            stats_vs_rhp={
                "walks": 10,
                "hit_by_pitch": 2,
                "singles": 20,
                "doubles": 8,
                "triples": 2,
                "home_runs": 5,
                "at_bats": 100,
            },
        )
        # Better vs RHP
        assert result["woba_vs_rhp"] > result["woba_vs_lhp"]

    def test_total_pa_correct(self):
        result = calculate_woba_with_splits(
            stats_vs_lhp={
                "walks": 5,
                "hit_by_pitch": 1,
                "singles": 8,
                "doubles": 2,
                "triples": 0,
                "home_runs": 1,
                "at_bats": 30,
            },
            stats_vs_rhp={
                "walks": 10,
                "hit_by_pitch": 2,
                "singles": 15,
                "doubles": 5,
                "triples": 1,
                "home_runs": 3,
                "at_bats": 70,
            },
        )
        assert result["lhp_pa"] == 36
        assert result["rhp_pa"] == 82

    def test_missing_walks_key_raises_error(self):
        with pytest.raises(TypeError):
            calculate_woba_with_splits(
                stats_vs_lhp={
                    "singles": 5,
                    "doubles": 1,
                    "triples": 0,
                    "home_runs": 0,
                    "at_bats": 25,
                },
                stats_vs_rhp={
                    "singles": 10,
                    "doubles": 3,
                    "triples": 0,
                    "home_runs": 1,
                    "at_bats": 50,
                },
            )


# ============================================================================
# xwOBA
# ============================================================================


class TestCalculateXwoba:
    def test_scalar_returns_float(self):
        xwoba = calculate_xwoba(105.0, 25.0)
        assert isinstance(xwoba, float)
        assert 0.0 <= xwoba <= 2.5

    def test_high_speed_sweet_spot(self):
        # 110 mph at 20 degree launch angle
        xwoba = calculate_xwoba(110.0, 20.0)
        assert round(xwoba, 3) == 0.816

    def test_low_speed_poor_angle(self):
        # 60 mph at 60 degree launch angle
        xwoba = calculate_xwoba(60.0, 60.0)
        assert xwoba < 0.5

    def test_high_speed_bad_angle(self):
        # 110 mph but extreme angle
        xwoba = calculate_xwoba(110.0, 60.0)
        # speed_score = clip((110-80)/40, 0, 1) = 0.75
        # angle_score = clip(1 - |60-25|/35, 0, 1) = 0
        # sweet_spot = 0
        # xwoba = 0.1 + 0.35*0.75 + 0.15*0 + 0.3*0*0.75 + 0.1*1 = 0.1+0.2625+0+0+0.1 = 0.4625
        assert round(xwoba, 2) == 0.46

    def test_pandas_series(self):
        speeds = pd.Series([100.0, 80.0, 110.0])
        angles = pd.Series([25.0, 10.0, 30.0])
        xwoba = calculate_xwoba(speeds, angles)
        assert isinstance(xwoba, pd.Series)
        assert len(xwoba) == 3

    def test_clipped_to_max(self):
        xwoba = calculate_xwoba(200.0, 25.0)
        assert xwoba <= 2.5

    def test_clipped_to_min(self):
        xwoba = calculate_xwoba(0.0, 90.0)
        assert xwoba >= 0.0


# ============================================================================
# FIP
# ============================================================================


class TestCalculateFip:
    def test_scalar_known_value(self):
        fip = calculate_fip(
            strikeouts=220,
            walks=50,
            hit_by_pitch=8,
            home_runs=25,
            innings_pitched=180.0,
            season=2024,
        )
        # numerator = 13*25 + 3*(50+8) - 2*220 = 325 + 174 - 440 = 59
        # FIP = 59/180 + 3.10 = 0.3278 + 3.10 = 3.4278
        assert round(fip, 2) == 3.43

    def test_zero_innings(self):
        fip = calculate_fip(
            strikeouts=0,
            walks=0,
            hit_by_pitch=0,
            home_runs=0,
            innings_pitched=0.0,
        )
        assert fip == 0.0

    def test_custom_factor(self):
        # numerator = 13*10 + 3*(30+5) - 2*100 = 130+105-200 = 35
        # FIP = 35/100 + 3.00 = 3.35
        fip = calculate_fip(
            strikeouts=100,
            walks=30,
            hit_by_pitch=5,
            home_runs=10,
            innings_pitched=100.0,
            use_custom_factor=3.00,
        )
        assert round(fip, 2) == 3.35

    def test_pandas_series(self):
        df = pd.DataFrame(
            {
                "strikeouts": [220, 150],
                "walks": [50, 40],
                "hit_by_pitch": [8, 5],
                "home_runs": [25, 15],
                "innings_pitched": [180.0, 120.0],
            }
        )
        fip = calculate_fip(
            df["strikeouts"],
            df["walks"],
            df["hit_by_pitch"],
            df["home_runs"],
            df["innings_pitched"],
        )
        assert isinstance(fip, pd.Series)
        assert len(fip) == 2

    def test_season_2022_constant(self):
        fip = calculate_fip(
            strikeouts=0,
            walks=0,
            hit_by_pitch=0,
            home_runs=0,
            innings_pitched=1.0,
            season=2022,
        )
        # should use 3.15
        assert round(fip, 2) == 3.15

    def test_unknown_season_default(self):
        fip = calculate_fip(
            strikeouts=0,
            walks=0,
            hit_by_pitch=0,
            home_runs=0,
            innings_pitched=1.0,
            season=2025,
        )
        # defaults to 3.10 (WOBA_WEIGHTS.get defaults to 2024 weights)
        # FIP constant from dict also defaults to 3.10
        assert fip == 3.10


# ============================================================================
# xERA
# ============================================================================


class TestCalculateXera:
    def test_fip_only(self):
        xera = calculate_xera(3.50)
        assert xera == 3.50

    def test_with_quality_of_contact(self):
        xera = calculate_xera(
            fip=3.50,
            quality_of_contact=0.320,
        )
        # 3.50 + (0.320 - 0.300) * 2.0 = 3.50 + 0.04 = 3.54
        assert round(xera, 2) == 3.54

    def test_with_defense(self):
        xera = calculate_xera(
            fip=3.50,
            defense_rating=0.5,
        )
        # 3.50 - (0.5 - 0.0) * 0.5 = 3.50 - 0.25 = 3.25
        assert round(xera, 2) == 3.25

    def test_with_park_factor(self):
        xera = calculate_xera(
            fip=3.50,
            park_factor=1.10,
        )
        # 3.50 / 1.10 = 3.1818
        assert round(xera, 2) == 3.18

    def test_all_adjustments(self):
        xera = calculate_xera(
            fip=4.00,
            quality_of_contact=0.350,
            defense_rating=0.2,
            park_factor=1.05,
        )
        # 4.00 + (0.350-0.300)*2 - (0.2-0.0)*0.5 / 1.05
        # = (4.00 + 0.10 - 0.10) / 1.05 = 4.00 / 1.05 = 3.8095
        assert round(xera, 2) == 3.81

    def test_pandas_series(self):
        fip = pd.Series([3.50, 4.00])
        qoc = pd.Series([0.300, 0.320])
        xera = calculate_xera(fip, quality_of_contact=qoc)
        assert isinstance(xera, pd.Series)


# ============================================================================
# SIERA
# ============================================================================


class TestCalculateSiera:
    def test_scalar_known_value(self):
        siera = calculate_siera(
            strikeouts=220,
            walks=50,
            ground_balls=180,
            fly_balls=120,
            innings_pitched=180.0,
        )
        # k_rate = 220/(180*3) = 220/540 = 0.4074
        # bb_rate = 50/540 = 0.0926
        # gb_rate = 180/(180+120) = 0.60
        # siera = 6.0 - 5.0*0.4074 + 3.0*0.0926 - 1.5*0.60
        # = 6.0 - 2.037 + 0.2778 - 0.90 = 3.3408
        assert round(siera, 2) == 3.34

    def test_strikeout_dominant(self):
        siera = calculate_siera(
            strikeouts=300,
            walks=30,
            ground_balls=150,
            fly_balls=100,
            innings_pitched=180.0,
        )
        # High K, low BB → low SIERA
        assert siera < 3.0

    def test_walk_prone(self):
        siera = calculate_siera(
            strikeouts=50,
            walks=150,
            ground_balls=150,
            fly_balls=100,
            innings_pitched=180.0,
        )
        # k_rate=50/540=0.0926, bb_rate=150/540=0.2778, gb_rate=0.60
        # siera = 6 - 5*0.0926 + 3*0.2778 - 1.5*0.60 = 5.47
        assert siera > 5.0

    def test_zero_ground_balls(self):
        siera = calculate_siera(
            strikeouts=100,
            walks=50,
            ground_balls=0,
            fly_balls=100,
            innings_pitched=100.0,
        )
        # gb_rate = 0/(0+100) = 0.0
        assert siera > 0

    def test_pandas_series(self):
        df = pd.DataFrame(
            {
                "strikeouts": [220, 150],
                "walks": [50, 40],
                "ground_balls": [180, 120],
                "fly_balls": [120, 80],
                "innings_pitched": [180.0, 120.0],
            }
        )
        siera = calculate_siera(
            df["strikeouts"],
            df["walks"],
            df["ground_balls"],
            df["fly_balls"],
            df["innings_pitched"],
        )
        assert isinstance(siera, pd.Series)
        assert len(siera) == 2


# ============================================================================
# Utilitarios
# ============================================================================


class TestFipConstantForSeason:
    def test_2024(self):
        assert fip_constant_for_season(2024) == 3.10

    def test_2022(self):
        assert fip_constant_for_season(2022) == 3.15

    def test_unknown_season(self):
        assert fip_constant_for_season(2025) == 3.14

    def test_2020(self):
        assert fip_constant_for_season(2020) == 3.18


class TestLeagueAdjustedStats:
    def test_above_average(self):
        # Player wOBA 0.350, league 0.310 → 112.9% of league
        result = league_adjusted_stats(0.350, 0.310)
        assert round(result, 3) == 1.129

    def test_below_average(self):
        result = league_adjusted_stats(0.280, 0.310)
        assert round(result, 3) == 0.903

    def test_with_park_factor(self):
        # Coors Field (park factor 1.20)
        result = league_adjusted_stats(0.350, 0.310, park_factor=1.20)
        assert round(result, 3) == 1.355

    def test_at_average(self):
        result = league_adjusted_stats(0.310, 0.310)
        assert result == 1.0


# ============================================================================
# Rolling stats (batch over DataFrame)
# ============================================================================


class TestComputeRollingStats:
    def test_single_player_single_window(self):
        df = pd.DataFrame(
            {
                "player_id": [1, 1, 1],
                "game_date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
                "woba": [0.300, 0.400, 0.500],
            }
        )
        result = compute_rolling_stats(df, windows=[2])
        result = result.sort_values("game_date").reset_index(drop=True)
        # window=2, min_periods=1
        # row 0: mean of first value = 0.300
        # row 1: mean of first 2 = 0.350
        # row 2: mean of last 2 = 0.450
        assert round(result["woba_2d"].iloc[0], 3) == 0.300
        assert round(result["woba_2d"].iloc[1], 3) == 0.350
        assert round(result["woba_2d"].iloc[2], 3) == 0.450

    def test_multiple_players(self):
        df = pd.DataFrame(
            {
                "player_id": [1, 1, 2, 2],
                "game_date": pd.to_datetime(
                    ["2026-05-01", "2026-05-02", "2026-05-01", "2026-05-02"]
                ),
                "woba": [0.300, 0.400, 0.250, 0.350],
                "fip": [3.50, 4.00, 4.50, 3.00],
            }
        )
        result = compute_rolling_stats(df, windows=[2])
        # Each player should have their own rolling means
        p1 = result[result["player_id"] == 1].sort_values("game_date")
        p2 = result[result["player_id"] == 2].sort_values("game_date")
        assert round(p1["woba_2d"].iloc[1], 3) == 0.350
        assert round(p2["woba_2d"].iloc[1], 3) == 0.300

    def test_multiple_windows(self):
        df = pd.DataFrame(
            {
                "player_id": [1, 1, 1],
                "game_date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
                "woba": [0.300, 0.400, 0.500],
            }
        )
        result = compute_rolling_stats(df, windows=[2, 3])
        assert "woba_2d" in result.columns
        assert "woba_3d" in result.columns

    def test_custom_stats(self):
        df = pd.DataFrame(
            {
                "player_id": [1, 1],
                "game_date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
                "k_pct": [0.20, 0.25],
            }
        )
        result = compute_rolling_stats(df, windows=[2], stats_to_compute=["k_pct"])
        assert "k_pct_2d" in result.columns

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["player_id", "game_date", "woba"])
        result = compute_rolling_stats(df)
        assert len(result) == 0
        assert isinstance(result, pd.DataFrame)

    def test_stat_not_in_columns_ignored(self):
        df = pd.DataFrame(
            {
                "player_id": [1],
                "game_date": pd.to_datetime(["2026-05-01"]),
                "woba": [0.300],
            }
        )
        result = compute_rolling_stats(df, stats_to_compute=["woba", "nonexistent"])
        assert "woba_7d" in result.columns
        assert "nonexistent_7d" not in result.columns


class TestComputeWobaRolling:
    def test_single_player(self):
        events = pd.DataFrame(
            {
                "player_id": [1, 1, 1],
                "game_id": ["G1", "G2", "G3"],
                "events": ["single", "home_run", "strikeout"],
            }
        )
        result = compute_woba_rolling(events, windows=[2])
        assert "woba" in result.columns
        assert "woba_2d" in result.columns
        # 3 games per player → 3 rows
        assert len(result) == 3

    def test_multiple_players(self):
        events = pd.DataFrame(
            {
                "player_id": [1, 1, 2, 2],
                "game_id": ["G1", "G2", "G1", "G2"],
                "events": ["single", "walk", "home_run", "strikeout"],
            }
        )
        result = compute_woba_rolling(events, windows=[2])
        # 2 players × 2 games each
        assert len(result) == 4
        assert result["player_id"].nunique() == 2

    def test_multiple_events_per_game(self):
        events = pd.DataFrame(
            {
                "player_id": [1, 1],
                "game_id": ["G1", "G1"],
                "events": ["single", "home_run"],
            }
        )
        result = compute_woba_rolling(events, windows=[2])
        # Grouped by (player_id, game_id) → 1 row
        assert len(result) == 1

    def test_no_events(self):
        events = pd.DataFrame(columns=["player_id", "game_id", "events"])
        result = compute_woba_rolling(events)
        assert len(result) == 0

    def test_woba_value_reasonable(self):
        events = pd.DataFrame(
            {
                "player_id": [1, 1, 1],
                "game_id": ["G1", "G1", "G1"],
                "events": ["walk", "single", "home_run"],
            }
        )
        result = compute_woba_rolling(events, windows=[7])
        woba = result["woba"].iloc[0]
        assert 0 < woba < 2.0

    def test_season_weights(self):
        events = pd.DataFrame(
            {
                "player_id": [1],
                "game_id": ["G1"],
                "events": ["single"],
            }
        )
        r2024 = compute_woba_rolling(events, windows=[7], season=2024)
        r2022 = compute_woba_rolling(events, windows=[7], season=2022)
        # 2024 single weight = 0.870, 2022 = 0.868 → slightly different
        assert abs(r2024["woba"].iloc[0] - r2022["woba"].iloc[0]) < 0.01
