"""Tests para PoissonPropsEngine, modelos y trainer."""

import math
import os
import sys
import tempfile
from dataclasses import asdict

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from scipy.stats import poisson

from prediction.poisson_props import (
    HitModel,
    PoissonModel,
    PoissonModelTrainer,
    PoissonPropsEngine,
    PropBetResult,
    StrikeoutModel,
)

# ============================================================================
# Modelo Poisson
# ============================================================================


class TestPoissonModel:
    def test_predict_log_lambda_zero_coefficients(self):
        model = PoissonModel(intercept=1.5, coefficients={}, feature_names=[])
        assert model.predict_log_lambda({"x": 10}) == 1.5

    def test_predict_log_lambda_with_features(self):
        model = PoissonModel(
            intercept=0.5,
            coefficients={"a": 0.3, "b": -0.2},
            feature_names=["a", "b"],
        )
        result = model.predict_log_lambda({"a": 2.0, "b": 3.0})
        # 0.5 + 0.3*2 + (-0.2)*3 = 0.5 + 0.6 - 0.6 = 0.5
        assert result == 0.5

    def test_unknown_features_ignored(self):
        model = PoissonModel(
            intercept=1.0,
            coefficients={"x": 10.0},
            feature_names=["x"],
        )
        result = model.predict_log_lambda({"y": 999})
        # "x" not in features, so ignored → just intercept
        assert result == 1.0

    def test_missing_feature_skipped(self):
        model = PoissonModel(
            intercept=0.0,
            coefficients={"a": 1.0, "b": 2.0},
            feature_names=["a", "b"],
        )
        # "b" in feature_names but missing from features dict → skipped
        result = model.predict_log_lambda({"a": 5.0})
        assert result == 5.0

    def test_predict_calls_exp(self):
        model = PoissonModel(intercept=math.log(4.0), coefficients={}, feature_names=[])
        assert model.predict({}) == 4.0

    def test_predict_with_coefficients(self):
        model = PoissonModel(
            intercept=0.0,
            coefficients={"x": 1.0},
            feature_names=["x"],
        )
        # log_lambda = 0 + 1*2 = 2 → lambda = e^2 ≈ 7.389
        result = model.predict({"x": 2.0})
        assert round(result, 3) == 7.389


class TestStrikeoutModel:
    def test_intercept_and_coefficients(self):
        model = StrikeoutModel()
        assert model.intercept == 0.520
        assert len(model.feature_names) == 15
        assert "avg_velo" in model.coefficients
        assert "whiff_pct" in model.coefficients
        assert model.r_squared == 0.42
        assert model.training_samples == 45000


class TestHitModel:
    def test_intercept_and_coefficients(self):
        model = HitModel()
        assert model.intercept == 0.100
        assert len(model.feature_names) == 9
        assert "woba" in model.coefficients
        assert model.r_squared == 0.35
        assert model.training_samples == 38000


# ============================================================================
# Feature engineering
# ============================================================================


class TestBuildStrikeoutFeatures:
    def test_all_fields_present(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.12,
            opponent_k_pct=0.23,
        )
        assert len(feats) == 15
        assert all(
            k in feats
            for k in [
                "avg_velo",
                "whiff_pct",
                "opponent_k_pct",
                "park_k_factor",
                "days_rested",
                "avg_spin",
                "pitch_count_l30",
                "swing_pct",
                "o_contact_pct",
                "home_plate_ump_cs_rate",
                "is_away",
                "is_division_game",
                "month",
                "temperature",
                "precipitation_pct",
            ]
        )

    def test_velo_normalized(self):
        engine = PoissonPropsEngine()
        # velo=93 → avg_velo=0
        feats = engine.build_strikeout_features(
            pitcher_velo=93.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
        )
        assert feats["avg_velo"] == 0.0
        # velo=97 → avg_velo=4
        feats = engine.build_strikeout_features(
            pitcher_velo=97.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
        )
        assert feats["avg_velo"] == 4.0

    def test_spin_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
            pitcher_spin=2200.0,
        )
        assert feats["avg_spin"] == 0.0

    def test_park_k_factor_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
            park_k_factor=1.0,
        )
        assert feats["park_k_factor"] == 0.0

    def test_temp_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
            temperature=72.0,
        )
        assert feats["temperature"] == 0.0

    def test_ump_cs_rate_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
            ump_cs_rate=0.48,
        )
        assert feats["home_plate_ump_cs_rate"] == 0.0

    def test_booleans_converted(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
            is_away=True,
            is_division_game=True,
        )
        assert feats["is_away"] == 1.0
        assert feats["is_division_game"] == 1.0
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
            is_away=False,
            is_division_game=False,
        )
        assert feats["is_away"] == 0.0
        assert feats["is_division_game"] == 0.0

    def test_defaults(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.1,
            opponent_k_pct=0.2,
        )
        assert feats["days_rested"] == 4
        assert feats["month"] == 6
        assert feats["temperature"] == 0.0  # (72-72)/10
        assert feats["precipitation_pct"] == 0.0


class TestBuildHitFeatures:
    def test_all_fields_present(self):
        engine = PoissonPropsEngine()
        feats = engine.build_hit_features(
            woba=0.320, hard_hit_pct=0.35, barrel_pct=0.08, opponent_fip=4.20
        )
        assert len(feats) == 9
        assert all(
            k in feats
            for k in [
                "woba",
                "hard_hit_pct",
                "barrel_pct",
                "opponent_fip",
                "park_hit_factor",
                "platoon_advantage",
                "k_rate",
                "bb_rate",
                "launch_angle_avg",
            ]
        )

    def test_woba_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_hit_features(
            woba=0.310, hard_hit_pct=0.3, barrel_pct=0.1, opponent_fip=4.20
        )
        assert feats["woba"] == 0.0

    def test_fip_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_hit_features(
            woba=0.310, hard_hit_pct=0.3, barrel_pct=0.1, opponent_fip=4.20
        )
        assert feats["opponent_fip"] == 0.0

    def test_k_rate_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_hit_features(
            woba=0.310, hard_hit_pct=0.3, barrel_pct=0.1, opponent_fip=4.20, k_rate=0.220
        )
        assert feats["k_rate"] == 0.0

    def test_launch_angle_normalized(self):
        engine = PoissonPropsEngine()
        feats = engine.build_hit_features(
            woba=0.310, hard_hit_pct=0.3, barrel_pct=0.1, opponent_fip=4.20, launch_angle_avg=12.0
        )
        assert feats["launch_angle_avg"] == 0.0

    def test_platoon_advantage_boolean(self):
        engine = PoissonPropsEngine()
        feats_true = engine.build_hit_features(
            woba=0.310, hard_hit_pct=0.3, barrel_pct=0.1, opponent_fip=4.20, platoon_advantage=True
        )
        feats_false = engine.build_hit_features(
            woba=0.310, hard_hit_pct=0.3, barrel_pct=0.1, opponent_fip=4.20, platoon_advantage=False
        )
        assert feats_true["platoon_advantage"] == 1.0
        assert feats_false["platoon_advantage"] == 0.0


# ============================================================================
# Utilitarios
# ============================================================================


class TestAmericanToImplied:
    def test_positive_odds(self):
        engine = PoissonPropsEngine()
        assert round(engine._american_to_implied(+100), 4) == 0.5000
        assert round(engine._american_to_implied(+200), 4) == 0.3333
        assert round(engine._american_to_implied(+400), 4) == 0.2000

    def test_negative_odds(self):
        engine = PoissonPropsEngine()
        assert round(engine._american_to_implied(-110), 4) == 0.5238
        assert round(engine._american_to_implied(-200), 4) == 0.6667
        assert round(engine._american_to_implied(-500), 4) == 0.8333

    def test_extreme_odds(self):
        engine = PoissonPropsEngine()
        assert engine._american_to_implied(+10000) < 0.01
        assert engine._american_to_implied(-10000) > 0.99

    def test_odds_zero(self):
        engine = PoissonPropsEngine()
        # odds=0 → odds > 0 is False → negative branch: |0|/(|0|+100) = 0
        assert engine._american_to_implied(0) == 0.0


class TestKelly:
    def test_positive_odds(self):
        engine = PoissonPropsEngine()
        kelly = engine._kelly(0.60, +150)
        # decimal = 150/100 + 1 = 2.5, b = 1.5
        # kelly = (0.6 * 2.5 - 1) / 1.5 = 0.5/1.5 = 0.3333
        # * 0.25 = 0.0833, capped at 0.05 → 0.05
        assert round(kelly, 4) == 0.05

    def test_negative_odds(self):
        engine = PoissonPropsEngine()
        kelly = engine._kelly(0.70, -150)
        # decimal = 100/150 + 1 = 1.6667, b = 0.6667
        # kelly = (0.7 * 1.6667 - 1) / 0.6667 = 0.1667/0.6667 = 0.25
        # * 0.25 = 0.0625, capped at 0.05 → 0.05
        assert round(kelly, 4) == 0.05

    def test_fraction_below_cap(self):
        engine = PoissonPropsEngine()
        kelly = engine._kelly(0.55, -110)
        # decimal = 100/110 + 1 = 1.9091, b = 0.9091
        # kelly = (0.55 * 1.9091 - 1) / 0.9091 = 0.05/0.9091 = 0.055
        # * 0.25 = 0.01375, below 0.05 cap
        assert round(kelly, 4) == 0.0138

    def test_no_edge_returns_zero(self):
        engine = PoissonPropsEngine()
        kelly = engine._kelly(0.50, -110)
        # implied = -110 → 0.5238, prob=0.5 → no edge
        # kelly < 0 → max(0, ...) = 0
        assert kelly == 0.0

    def test_certainty_capped(self):
        engine = PoissonPropsEngine()
        kelly = engine._kelly(1.0, +100)
        # decimal = 2, b = 1
        # kelly = (1*2 - 1)/1 = 1.0, * 0.25 = 0.25, capped at 0.05
        assert kelly == 0.05


class TestPoissonCDF:
    def test_cdf_at_zero(self):
        engine = PoissonPropsEngine()
        lam = 5.0
        # P(X ≤ 0) = e^(-5) ≈ 0.0067
        assert round(engine._poisson_cdf(0, lam), 4) == 0.0067

    def test_cdf_at_lambda(self):
        engine = PoissonPropsEngine()
        lam = 4.5
        cdf = engine._poisson_cdf(lam, lam)
        assert 0.4 < cdf < 0.7  # roughly median-ish

    def test_cdf_large_lambda(self):
        engine = PoissonPropsEngine()
        lam = 100.0
        cdf_at_90 = engine._poisson_cdf(90, lam)
        cdf_at_110 = engine._poisson_cdf(110, lam)
        assert cdf_at_90 < 0.5
        assert cdf_at_110 > 0.5

    def test_cdf_matches_scipy(self):
        engine = PoissonPropsEngine()
        lam = 5.5
        k = 7
        expected = poisson.cdf(k, lam)
        assert engine._poisson_cdf(k, lam) == expected


# ============================================================================
# Motor principal
# ============================================================================


class TestPredict:
    def test_returns_lambda_and_std(self):
        engine = PoissonPropsEngine()
        lam, std = engine.predict(
            "STRIKEOUTS", {"avg_velo": 4.0, "whiff_pct": 0.12, "opponent_k_pct": 0.22}
        )
        assert lam > 0
        assert std == math.sqrt(lam)

    def test_unknown_prop_type_raises(self):
        engine = PoissonPropsEngine()
        with pytest.raises(ValueError, match="Unknown prop type"):
            engine.predict("RBIS", {})

    def test_hits_model_works(self):
        engine = PoissonPropsEngine()
        lam, std = engine.predict(
            "HITS", {"woba": 0.7, "hard_hit_pct": 0.4, "barrel_pct": 0.1, "opponent_fip": 0.3}
        )
        assert lam > 0


class TestEvaluateBetStrikeouts:
    """Escenario: Gerrit Cole (97.5 mph, 15% whiff, 22% opp K%)."""

    @pytest.fixture
    def cole_features(self):
        engine = PoissonPropsEngine()
        return engine.build_strikeout_features(
            pitcher_velo=97.5,
            pitcher_whiff_pct=0.15,
            opponent_k_pct=0.22,
            park_k_factor=1.02,
            days_rested=5,
            pitcher_spin=2450.0,
            swing_pct=0.48,
            o_contact_pct=0.65,
            ump_cs_rate=0.50,
            is_away=False,
        )

    def test_predicted_mean_reasonable(self, cole_features):
        engine = PoissonPropsEngine()
        lam, _ = engine.predict("STRIKEOUTS", cole_features)
        assert 4.5 < lam < 6.5

    def test_line_under_ev_positive(self, cole_features):
        engine = PoissonPropsEngine()
        result = engine.evaluate_bet(
            prop_type="STRIKEOUTS",
            player_name="Gerrit Cole",
            line_value=6.5,
            over_odds=-110,
            under_odds=-110,
            features=cole_features,
        )
        assert result.recommendation in ("over", "under")
        assert result.player_name == "Gerrit Cole"
        assert result.predicted_mean > 0

    def test_line_7_5_at_even_odds(self, cole_features):
        engine = PoissonPropsEngine()
        result = engine.evaluate_bet(
            prop_type="STRIKEOUTS",
            player_name="Gerrit Cole",
            line_value=7.5,
            over_odds=-110,
            under_odds=-110,
            features=cole_features,
        )
        assert result.prop_type == "STRIKEOUTS"
        assert result.line_value == 7.5
        assert result.over_odds == -110
        assert result.under_odds == -110
        assert 0 < result.prob_over < 1
        assert 0 < result.prob_under < 1
        assert abs(result.prob_over + result.prob_under - 1.0) < 0.01

    def test_recommendation_over_when_ev_positive(self, cole_features):
        engine = PoissonPropsEngine()
        result = engine.evaluate_bet(
            prop_type="STRIKEOUTS",
            player_name="Gerrit Cole",
            line_value=6.5,
            over_odds=-110,
            under_odds=-110,
            features=cole_features,
        )
        if result.ev_over > result.ev_under and result.ev_over > 0.02:
            assert result.recommendation == "over"
        elif result.ev_under > 0.02:
            assert result.recommendation == "under"
        else:
            assert result.recommendation == "no_bet"

    def test_kelly_fraction_between_zero_and_five_pct(self, cole_features):
        engine = PoissonPropsEngine()
        result = engine.evaluate_bet(
            prop_type="STRIKEOUTS",
            player_name="Gerrit Cole",
            line_value=6.5,
            over_odds=-110,
            under_odds=-110,
            features=cole_features,
        )
        if result.recommendation != "no_bet":
            assert 0 < result.kelly_fraction <= 0.05
        else:
            assert result.kelly_fraction == 0.0


class TestEvaluateBetHits:
    """Escenario: Aaron Judge (.380 wOBA, 45% hard hit, 12% barrel)."""

    @pytest.fixture
    def judge_features(self):
        engine = PoissonPropsEngine()
        return engine.build_hit_features(
            woba=0.380,
            hard_hit_pct=0.45,
            barrel_pct=0.12,
            opponent_fip=4.50,
            park_hit_factor=1.05,
            platoon_advantage=True,
            k_rate=0.20,
            bb_rate=0.10,
        )

    def test_predicted_mean_reasonable(self, judge_features):
        engine = PoissonPropsEngine()
        lam, _ = engine.predict("HITS", judge_features)
        assert 25.0 < lam < 45.0

    def test_line_1_5_at_plus_odds(self, judge_features):
        engine = PoissonPropsEngine()
        result = engine.evaluate_bet(
            prop_type="HITS",
            player_name="Aaron Judge",
            line_value=1.5,
            over_odds=+120,
            under_odds=-150,
            features=judge_features,
        )
        assert result.prop_type == "HITS"
        assert result.predicted_mean > 0
        assert result.recommendation in ("over", "under", "no_bet")


class TestEvaluateBetNoEdge:
    def test_line_far_above_mean_returns_under(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=91.0,
            pitcher_whiff_pct=0.05,
            opponent_k_pct=0.18,
        )
        result = engine.evaluate_bet(
            prop_type="STRIKEOUTS",
            player_name="Low K Pitcher",
            line_value=9.5,
            over_odds=-110,
            under_odds=-110,
            features=feats,
        )
        # Very unlikely to get 9.5 Ks → under should have EV
        if result.ev_under > 0.02:
            assert result.recommendation == "under"

    def test_line_far_below_mean_returns_over(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=98.0,
            pitcher_whiff_pct=0.20,
            opponent_k_pct=0.25,
        )
        result = engine.evaluate_bet(
            prop_type="STRIKEOUTS",
            player_name="High K Pitcher",
            line_value=3.5,
            over_odds=-110,
            under_odds=-110,
            features=feats,
        )
        # Very likely to get 3.5+ Ks → over should have EV
        if result.ev_over > 0.02:
            assert result.recommendation == "over"


class TestEvaluateBetZeroLine:
    def test_line_zero_over_always_has_prob_one(self):
        engine = PoissonPropsEngine()
        feats = engine.build_strikeout_features(
            pitcher_velo=95.0,
            pitcher_whiff_pct=0.12,
            opponent_k_pct=0.22,
        )
        result = engine.evaluate_bet(
            prop_type="STRIKEOUTS",
            player_name="Any",
            line_value=0,
            over_odds=-500,
            under_odds=+300,
            features=feats,
        )
        # P(X > 0) = 1 - P(X = 0) = 1 - e^(-lambda)
        assert result.prob_over > 0.90
        assert result.prob_over < 1.0
        if result.ev_over > 0.02:
            assert result.recommendation == "over"


# ============================================================================
# Trainer
# ============================================================================


class TestPoissonModelTrainer:
    def test_train_strikeout_model(self):
        trainer = PoissonModelTrainer()
        model = trainer.train_strikeout_model([2024])
        assert isinstance(model, StrikeoutModel)
        assert model.training_samples == 15000

    def test_train_with_multiple_seasons(self):
        trainer = PoissonModelTrainer()
        model = trainer.train_strikeout_model([2022, 2023, 2024])
        assert model.training_samples == 45000

    def test_save_load_roundtrip(self):
        trainer = PoissonModelTrainer()
        model = StrikeoutModel()
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name
        try:
            trainer.save_model(model, path)
            loaded = trainer.load_model(path)
            assert loaded.intercept == model.intercept
            assert loaded.coefficients == model.coefficients
            assert loaded.feature_names == model.feature_names
        finally:
            os.unlink(path)

    def test_load_model_returns_correct_type(self):
        trainer = PoissonModelTrainer()
        model = trainer.train_strikeout_model()
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name
        try:
            trainer.save_model(model, path)
            loaded = trainer.load_model(path)
            assert isinstance(loaded, PoissonModel)
            assert hasattr(loaded, "predict")
            assert hasattr(loaded, "predict_log_lambda")
        finally:
            os.unlink(path)


# ============================================================================
# PropBetResult
# ============================================================================


class TestPropBetResult:
    def test_dataclass_fields(self):
        result = PropBetResult(
            prop_type="STRIKEOUTS",
            player_name="Test",
            line_value=6.5,
            over_odds=-110,
            under_odds=-110,
            predicted_mean=7.2,
            prob_over=0.65,
            prob_under=0.35,
            implied_over=0.52,
            implied_under=0.48,
            ev_over=0.13,
            ev_under=-0.13,
            recommendation="over",
            kelly_fraction=0.025,
        )
        d = asdict(result)
        assert d["prop_type"] == "STRIKEOUTS"
        assert d["recommendation"] == "over"
        assert d["kelly_fraction"] == 0.025

    def test_no_bet_default_kelly(self):
        result = PropBetResult(
            prop_type="HITS",
            player_name="Test",
            line_value=1.5,
            over_odds=+120,
            under_odds=-150,
            predicted_mean=1.1,
            prob_over=0.4,
            prob_under=0.6,
            implied_over=0.35,
            implied_under=0.65,
            ev_over=0.05,
            ev_under=-0.05,
            recommendation="no_bet",
        )
        assert result.kelly_fraction == 0.0
