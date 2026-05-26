"""Tests para fatigue_detector.py (FatigueDetector, FatigueScore)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta

from features.fatigue_detector import (
    FatigueDetector,
    FatigueScore,
)

# ============================================================================
# FatigueScore dataclass
# ============================================================================


class TestFatigueScore:
    def test_default_components_is_empty_dict(self):
        fs = FatigueScore(
            player_id=1,
            player_name="",
            game_id="G1",
            game_date=date.today(),
            overall_fatigue=0.0,
        )
        assert fs.components == {}

    def test_stores_overall_fatigue(self):
        fs = FatigueScore(
            player_id=1,
            player_name="",
            game_id="G1",
            game_date=date.today(),
            overall_fatigue=0.50,
        )
        assert fs.overall_fatigue == 0.50
        # is_high_risk is computed by evaluate_pitcher/batter_fatigue, not the dataclass
        assert fs.is_high_risk is False

    def test_not_high_risk(self):
        fs = FatigueScore(
            player_id=1,
            player_name="",
            game_id="G1",
            game_date=date.today(),
            overall_fatigue=0.20,
        )
        assert fs.is_high_risk is False


# ============================================================================
# FatigueDetector.evaluate_pitcher_fatigue
# ============================================================================


class TestPitcherFatigueRestScore:
    def test_rest_six_days_is_zero(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=6,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.components["rest_score"] == 0.0

    def test_rest_three_days_score(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=3,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # rest_score = 0.3 + (4-3)*0.15 = 0.45
        assert r.components["rest_score"] == 0.45

    def test_rest_one_day_score(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=1,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # rest_score = 0.3 + (4-1)*0.15 = 0.3 + 0.45 = 0.75
        assert r.components["rest_score"] == 0.75

    def test_rest_four_days_score(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=4,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # rest_score = max(0, (5-4)*0.1) = 0.1
        assert r.components["rest_score"] == 0.1


class TestPitcherFatigueVeloDrop:
    def test_velo_drop_above_threshold_scales_linearly(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=96.0,
            avg_velo_last_3g=93.0,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # velo_drop = 3.0, threshold = 1.5
        # velo_score = min(1.0, (3.0-1.5)/3.0) = 0.5
        assert r.components["velo_drop_score"] == 0.5

    def test_velo_drop_small_positive(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=96.0,
            avg_velo_last_3g=95.0,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # velo_drop = 1.0, below threshold
        # velo_score = 1.0/1.5 * 0.3 = 0.2
        assert r.components["velo_drop_score"] == pytest.approx(0.2)

    def test_no_velo_drop(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.velo_drop == 0.0
        assert r.components["velo_drop_score"] == 0.0

    def test_velo_drop_capped_at_one(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=96.0,
            avg_velo_last_3g=85.0,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # velo_drop = 11.0, (11-1.5)/3 = 3.17, min with 1.0 = 1.0
        assert r.components["velo_drop_score"] == 1.0


class TestPitcherFatigueSpinDrop:
    def test_spin_drop_above_threshold(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2500,
            avg_spin_last_3g=2200,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # spin_drop = 300, threshold = 150
        # spin_score = min(1.0, (300-150)/300) = 0.5
        assert r.components["spin_drop_score"] == 0.5

    def test_spin_drop_small_positive(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2500,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        # spin_drop = 100, below threshold
        # spin_score = 100/150 * 0.3 = 0.2
        assert r.components["spin_drop_score"] == pytest.approx(0.2)

    def test_no_spin_drop(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.components["spin_drop_score"] == 0.0


class TestPitcherFatiguePitchLoad:
    def test_pitch_load_scales(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=150,
            innings_pitched_last_7d=10,
        )
        # pitch_score = min(1.0, 150/200) = 0.75
        assert r.components["pitch_load_score"] == 0.75

    def test_pitch_load_capped(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=400,
            innings_pitched_last_7d=20,
        )
        assert r.components["pitch_load_score"] == 1.0


class TestPitcherFatigueTravel:
    def test_tz_crossings(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
            tz_crossings_last_3d=3,
        )
        # tz_score = min(1.0, 3*0.08) = 0.24
        assert r.components["tz_crossing_score"] == 0.24
        assert r.tz_crossings == 3

    def test_travel_miles(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
            travel_miles_last_3d=3000,
        )
        # travel_score = min(0.3, 3000*0.0001) = min(0.3, 0.3) = 0.3
        assert r.components["travel_miles_score"] == 0.3

    def test_travel_miles_capped(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
            travel_miles_last_3d=5000,
        )
        assert r.components["travel_miles_score"] == 0.3


class TestPitcherFatigueDayAfterNight:
    def test_day_after_night_adds_penalty(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
            is_day_game_after_night=True,
        )
        assert r.components["day_after_night"] == 0.10
        assert r.day_game_after_night is True

    def test_no_day_after_night(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert "day_after_night" not in r.components
        assert r.day_game_after_night is False


class TestPitcherFatigueOverall:
    def test_fully_rested_returns_zero(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=6,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.overall_fatigue == 0.0

    def test_multiple_factors_compound(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=2,
            avg_velo_last_30d=96,
            avg_velo_last_3g=92,
            avg_spin_last_30d=2500,
            avg_spin_last_3g=2200,
            pitches_thrown_last_7d=180,
            innings_pitched_last_7d=12,
            tz_crossings_last_3d=3,
            travel_miles_last_3d=2800,
            is_day_game_after_night=True,
        )
        assert r.overall_fatigue > 0.5

    def test_overall_capped_at_one(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=0,
            avg_velo_last_30d=100,
            avg_velo_last_3g=80,
            avg_spin_last_30d=3000,
            avg_spin_last_3g=1500,
            pitches_thrown_last_7d=500,
            innings_pitched_last_7d=30,
            tz_crossings_last_3d=13,
            travel_miles_last_3d=30000,
            is_day_game_after_night=True,
        )
        assert r.overall_fatigue <= 1.0

    def test_high_risk_threshold(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=1,
            avg_velo_last_30d=96,
            avg_velo_last_3g=92,
            avg_spin_last_30d=2500,
            avg_spin_last_3g=2200,
            pitches_thrown_last_7d=180,
            innings_pitched_last_7d=12,
            tz_crossings_last_3d=3,
            travel_miles_last_3d=2800,
            is_day_game_after_night=True,
        )
        assert r.is_high_risk is True

    def test_low_fatigue_not_high_risk(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=6,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.is_high_risk is False


class TestPitcherFatigueFields:
    def test_velo_drop_field(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=96.5,
            avg_velo_last_3g=94.0,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.velo_drop == 2.5

    def test_spin_drop_field(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2550,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.spin_drop == 150.0

    def test_pitch_count_field(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=185,
            innings_pitched_last_7d=12.0,
        )
        assert r.pitch_count_recent == 185
        assert r.innings_recent == 12.0

    def test_player_info(self):
        d = FatigueDetector()
        r = d.evaluate_pitcher_fatigue(
            player_id=42,
            player_name="Shohei Ohtani",
            game_id="G1",
            game_date=date(2026, 5, 20),
            rest_days=5,
            avg_velo_last_30d=95,
            avg_velo_last_3g=95,
            avg_spin_last_30d=2400,
            avg_spin_last_3g=2400,
            pitches_thrown_last_7d=0,
            innings_pitched_last_7d=0,
        )
        assert r.player_id == 42
        assert r.player_name == "Shohei Ohtani"
        assert r.game_id == "G1"
        assert r.game_date == date(2026, 5, 20)


# ============================================================================
# FatigueDetector.evaluate_batter_fatigue
# ============================================================================


class TestBatterFatigue:
    def test_rested_batter_low_fatigue(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=6,
            woba_last_14d=0.350,
            woba_last_7d=0.360,
            hard_hit_pct_last_14d=0.45,
            hard_hit_pct_last_7d=0.46,
        )
        assert r.overall_fatigue < 0.1

    def test_woba_drop_increases_fatigue(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            woba_last_14d=0.350,
            woba_last_7d=0.250,
            hard_hit_pct_last_14d=0.45,
            hard_hit_pct_last_7d=0.44,
        )
        # woba_drop = 0.100, woba_score = min(0.5, 0.100*3) = 0.3
        assert r.components["woba_drop_score"] == 0.3

    def test_no_woba_drop_no_score(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            woba_last_14d=0.300,
            woba_last_7d=0.350,
            hard_hit_pct_last_14d=0.45,
            hard_hit_pct_last_7d=0.44,
        )
        # woba_drop = max(0, 0.300-0.350) = 0
        assert r.components["woba_drop_score"] == 0.0

    def test_hard_hit_drop(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            woba_last_14d=0.350,
            woba_last_7d=0.340,
            hard_hit_pct_last_14d=0.50,
            hard_hit_pct_last_7d=0.35,
        )
        # hard_hit_drop = 0.15, hard_hit_score = min(0.5, 0.15*2) = 0.3
        assert r.components["hard_hit_drop"] == 0.3

    def test_no_hard_hit_drop(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            woba_last_14d=0.350,
            woba_last_7d=0.340,
            hard_hit_pct_last_14d=0.40,
            hard_hit_pct_last_7d=0.45,
        )
        assert r.components["hard_hit_drop"] == 0.0

    def test_batter_travel_fatigue(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            woba_last_14d=0.350,
            woba_last_7d=0.340,
            hard_hit_pct_last_14d=0.45,
            hard_hit_pct_last_7d=0.44,
            tz_crossings_last_3d=4,
        )
        assert r.tz_crossings == 4

    def test_batter_day_after_night(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=5,
            woba_last_14d=0.350,
            woba_last_7d=0.340,
            hard_hit_pct_last_14d=0.45,
            hard_hit_pct_last_7d=0.44,
            is_day_game_after_night=True,
        )
        assert r.components["day_after_night"] == 0.10

    def test_batter_high_risk(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=0,
            woba_last_14d=0.400,
            woba_last_7d=0.200,
            hard_hit_pct_last_14d=0.60,
            hard_hit_pct_last_7d=0.20,
            tz_crossings_last_3d=4,
            travel_miles_last_3d=3000,
            is_day_game_after_night=True,
        )
        assert r.is_high_risk is True

    def test_batter_not_high_risk(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=6,
            woba_last_14d=0.350,
            woba_last_7d=0.360,
            hard_hit_pct_last_14d=0.45,
            hard_hit_pct_last_7d=0.46,
        )
        assert r.is_high_risk is False

    def test_overall_capped(self):
        d = FatigueDetector()
        r = d.evaluate_batter_fatigue(
            player_id=1,
            player_name="A",
            game_id="G1",
            game_date=date.today(),
            rest_days=0,
            woba_last_14d=1.000,
            woba_last_7d=0.000,
            hard_hit_pct_last_14d=1.00,
            hard_hit_pct_last_7d=0.00,
            tz_crossings_last_3d=13,
            travel_miles_last_3d=30000,
            is_day_game_after_night=True,
        )
        assert r.overall_fatigue <= 1.0


# ============================================================================
# SQL generation
# ============================================================================


class TestQueryTravelFatigueSql:
    def test_returns_string(self):
        d = FatigueDetector()
        sql = d.query_travel_fatigue_sql(["NYY", "BOS"], date(2026, 5, 20))
        assert isinstance(sql, str)
        assert "NYY" in sql
        assert "BOS" in sql
        assert "2026-05-20" in sql

    def test_includes_team_games_cte(self):
        d = FatigueDetector()
        sql = d.query_travel_fatigue_sql(["NYY"], date(2026, 5, 20))
        assert "team_games" in sql
        assert "ROW_NUMBER" in sql
        assert "home_travel_miles" in sql
        assert "away_travel_miles" in sql

    def test_multiple_teams(self):
        d = FatigueDetector()
        sql = d.query_travel_fatigue_sql(["NYY", "BOS", "LAD", "HOU"], date(2026, 5, 20))
        assert "NYY" in sql
        assert "BOS" in sql
        assert "LAD" in sql
        assert "HOU" in sql

    def test_single_team(self):
        d = FatigueDetector()
        sql = d.query_travel_fatigue_sql(["NYY"], date(2026, 5, 20))
        assert sql.count("NYY") >= 3

    def test_game_date_formatting(self):
        d = FatigueDetector()
        sql = d.query_travel_fatigue_sql(["NYY"], date(2026, 1, 5))
        assert "2026-01-05" in sql


class TestQueryVeloSpinDropSql:
    def test_returns_string(self):
        d = FatigueDetector()
        sql = d.query_velo_spin_drop_sql(123, date(2026, 5, 20))
        assert isinstance(sql, str)
        assert "123" in sql
        assert "2026-05-20" in sql

    def test_includes_recent_games_cte(self):
        d = FatigueDetector()
        sql = d.query_velo_spin_drop_sql(123, date(2026, 5, 20))
        assert "recent_games" in sql
        assert "release_speed" in sql
        assert "release_spin_rate" in sql

    def test_includes_baseline_windows(self):
        d = FatigueDetector()
        sql = d.query_velo_spin_drop_sql(1, date.today())
        assert "baseline_velo_30d" in sql
        assert "baseline_spin_30d" in sql
        assert "recent_velo_3g" in sql
        assert "recent_spin_3g" in sql

    def test_includes_pitch_table_joins(self):
        d = FatigueDetector()
        sql = d.query_velo_spin_drop_sql(1, date.today())
        assert "pitches p" in sql
        assert "at_bats ab" in sql
        assert "games g" in sql

    def test_limits_to_recent(self):
        d = FatigueDetector()
        sql = d.query_velo_spin_drop_sql(1, date.today())
        assert "45 days" in sql or "45" in sql

    def test_limits_to_one_row(self):
        d = FatigueDetector()
        sql = d.query_velo_spin_drop_sql(1, date.today())
        assert "LIMIT 1" in sql
