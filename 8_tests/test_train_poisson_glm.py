"""Tests para train_poisson_glm.py (PoissonGLMTrainer)."""

import json
import os
import pickle
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from prediction.model_training.train_poisson_glm import PoissonGLMTrainer

SAMPLE_RAW_DF = pd.DataFrame(
    {
        "pitcher_id": [1, 1, 1, 1, 2, 2, 2, 2],
        "game_date": pd.to_datetime(
            [
                "2024-05-01",
                "2024-05-01",
                "2024-05-02",
                "2024-05-02",
                "2024-05-01",
                "2024-05-01",
                "2024-05-02",
                "2024-05-02",
            ]
        ),
        "velo": [96.0, 95.0, 94.0, 93.0, 90.0, 91.0, 89.0, 88.0],
        "spin": [2500, 2450, 2400, 2350, 2100, 2150, 2050, 2000],
        "whiff": [0, 0, 1, 0, 0, 1, 0, 0],
        "is_k": [0, 1, 0, 0, 1, 0, 0, 1],
    }
)

# Larger dataset with clear signal: higher velo → more strikeouts
LARGER_RAW_DF = pd.DataFrame(
    {
        "pitcher_id": [1] * 40 + [2] * 40,
        "game_date": pd.to_datetime(
            [f"2024-{m:02d}-{d:02d}" for m in range(1, 5) for d in range(1, 11)] * 2
        ),
        "velo": [98.0 + (i % 10) * 0.2 for i in range(40)]
        + [88.0 + (i % 10) * 0.2 for i in range(40)],
        "spin": [2500 + (i % 10) * 10 for i in range(40)]
        + [2000 + (i % 10) * 10 for i in range(40)],
        "whiff": [0.3 + (i % 10) * 0.02 for i in range(40)]
        + [0.1 + (i % 10) * 0.01 for i in range(40)],
        "is_k": [1 if i % 3 == 0 else 0 for i in range(40)]
        + [1 if i % 5 == 0 else 0 for i in range(40)],
    }
)


# ============================================================================
# __init__
# ============================================================================


class TestInit:
    def test_stores_db_url(self, tmp_path):
        d = str(tmp_path / "models")
        t = PoissonGLMTrainer("sqlite://", d)
        assert t.db_url == "sqlite://"

    def test_creates_models_dir(self, tmp_path):
        d = str(tmp_path / "models")
        assert not os.path.exists(d)
        t = PoissonGLMTrainer("sqlite://", d)
        assert os.path.isdir(d)

    def test_engine_created(self, tmp_path):
        t = PoissonGLMTrainer("sqlite://", str(tmp_path / "models"))
        assert t.engine is not None
        assert str(t.engine.url) == "sqlite://"


# ============================================================================
# load_training_data
# ============================================================================


class TestLoadTrainingData:
    @patch("prediction.model_training.train_poisson_glm.pd.read_sql")
    def test_returns_dataframe(self, mock_read_sql):
        mock_read_sql.return_value = SAMPLE_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        df = t.load_training_data([2024])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 8

    @patch("prediction.model_training.train_poisson_glm.pd.read_sql")
    def test_sql_includes_seasons(self, mock_read_sql):
        mock_read_sql.return_value = SAMPLE_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        t.load_training_data([2023, 2024])
        sql = mock_read_sql.call_args[0][0]
        assert "2023" in sql and "2024" in sql

    @patch("prediction.model_training.train_poisson_glm.pd.read_sql")
    def test_sql_has_limit(self, mock_read_sql):
        mock_read_sql.return_value = SAMPLE_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        t.load_training_data([2024])
        sql = mock_read_sql.call_args[0][0]
        assert "LIMIT 50000" in sql

    @patch("prediction.model_training.train_poisson_glm.pd.read_sql")
    def test_empty_dataframe(self, mock_read_sql):
        mock_read_sql.return_value = pd.DataFrame()
        t = PoissonGLMTrainer("sqlite://", "models")
        df = t.load_training_data([2024])
        assert df.empty

    @patch("prediction.model_training.train_poisson_glm.pd.read_sql")
    def test_single_season(self, mock_read_sql):
        mock_read_sql.return_value = SAMPLE_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        t.load_training_data([2022])
        sql = mock_read_sql.call_args[0][0]
        assert "2022" in sql


# ============================================================================
# extract_strikeout_features
# ============================================================================


class TestExtractStrikeoutFeatures:
    def test_returns_features_and_targets(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(SAMPLE_RAW_DF)
        assert isinstance(X, np.ndarray)
        assert isinstance(y, np.ndarray)

    def test_groups_by_pitcher_and_date(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(SAMPLE_RAW_DF)
        # 2 pitchers × 2 dates each = 4 rows
        assert X.shape[0] == 4
        assert y.shape[0] == 4

    def test_velo_centered(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(SAMPLE_RAW_DF)
        # pitcher 1, date 1: avg_velo = (96+95)/2 = 95.5, centered = 95.5-93 = 2.5
        # pitcher 1, date 2: avg_velo = (94+93)/2 = 93.5, centered = 93.5-93 = 0.5
        # pitcher 2, date 1: avg_velo = (90+91)/2 = 90.5, centered = 90.5-93 = -2.5
        # pitcher 2, date 2: avg_velo = (89+88)/2 = 88.5, centered = 88.5-93 = -4.5
        assert X[0, 0] == pytest.approx(2.5)
        assert X[1, 0] == pytest.approx(0.5)
        assert X[2, 0] == pytest.approx(-2.5)
        assert X[3, 0] == pytest.approx(-4.5)

    def test_spin_centered(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(SAMPLE_RAW_DF)
        # pitcher 1, date 1: avg_spin = (2500+2450)/2 = 2475, centered = (2475-2200)/100 = 2.75
        assert X[0, 2] == pytest.approx(2.75)

    def test_whiff_rate(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(SAMPLE_RAW_DF)
        # pitcher 1, date 1: whiffs = 0/2 = 0
        # pitcher 1, date 2: whiffs = 1/2 = 0.5
        assert X[0, 1] == 0.0
        assert X[1, 1] == 0.5

    def test_k_per_game_target(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(SAMPLE_RAW_DF)
        # pitcher 1, date 1: is_k = [0,1] → k_count = 1
        # pitcher 1, date 2: is_k = [0,0] → k_count = 0
        # pitcher 2, date 1: is_k = [1,0] → k_count = 1
        # pitcher 2, date 2: is_k = [0,1] → k_count = 1
        assert y[0] == 1
        assert y[1] == 0
        assert y[2] == 1
        assert y[3] == 1

    def test_feature_columns_in_order(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(SAMPLE_RAW_DF)
        assert X.shape[1] == 3


# ============================================================================
# train_strikeout_model (mocked DB)
# ============================================================================


class TestTrainStrikeoutModelConvergence:
    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_returns_dict_with_expected_keys(self, mock_load):
        mock_load.return_value = LARGER_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        model = t.train_strikeout_model([2024])
        assert "intercept" in model
        assert "coefficients" in model
        assert "metrics" in model
        assert "trained_at" in model
        assert "seasons" in model

    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_coefficients_have_expected_keys(self, mock_load):
        mock_load.return_value = SAMPLE_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        model = t.train_strikeout_model([2024])
        assert "velo_centered" in model["coefficients"]
        assert "whiff_rate" in model["coefficients"]
        assert "spin_centered" in model["coefficients"]

    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_metrics_have_expected_keys(self, mock_load):
        mock_load.return_value = SAMPLE_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        model = t.train_strikeout_model([2024])
        assert "r_squared" in model["metrics"]
        assert "mse" in model["metrics"]
        assert "mae" in model["metrics"]
        assert "train_samples" in model["metrics"]
        assert "test_samples" in model["metrics"]

    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_seasons_stored(self, mock_load):
        mock_load.return_value = LARGER_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        model = t.train_strikeout_model([2023, 2024])
        assert model["seasons"] == [2023, 2024]

    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_coefficients_not_all_zero(self, mock_load):
        mock_load.return_value = LARGER_RAW_DF
        t = PoissonGLMTrainer("sqlite://", "models")
        model = t.train_strikeout_model([2024])
        coefs = model["coefficients"]
        assert any(abs(v) > 1e-6 for v in coefs.values())

    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_model_saved_to_disk(self, mock_load, tmp_path):
        mock_load.return_value = SAMPLE_RAW_DF
        d = str(tmp_path / "models")
        t = PoissonGLMTrainer("sqlite://", d)
        model = t.train_strikeout_model([2024])
        path = os.path.join(d, "strikeout_poisson_model.json")
        assert os.path.isfile(path)
        with open(path) as f:
            saved = json.load(f)
        assert saved["intercept"] == model["intercept"]


# ============================================================================
# train_strikeout_model (edge cases)
# ============================================================================


class TestTrainStrikeoutModelEdgeCases:
    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_empty_data_raises(self, mock_load):
        mock_load.return_value = pd.DataFrame()
        t = PoissonGLMTrainer("sqlite://", "models")
        with pytest.raises((KeyError, ValueError)):
            t.train_strikeout_model([2024])

    @patch.object(PoissonGLMTrainer, "load_training_data")
    def test_single_valid_season(self, mock_load):
        mock_load.return_value = SAMPLE_RAW_DF
        d = PoissonGLMTrainer("sqlite://", "models")
        model = d.train_strikeout_model([2024])
        assert model["seasons"] == [2024]

    def test_linalg_error_fallback(self):
        # Force LinAlgError by passing degenerate data with zero variance
        df = pd.DataFrame(
            {
                "pitcher_id": [1, 1],
                "game_date": pd.to_datetime(["2024-05-01", "2024-05-01"]),
                "velo": [95.0, 95.0],
                "spin": [2400.0, 2400.0],
                "whiff": [0.5, 0.5],
                "is_k": [2, 2],
            }
        )
        t = PoissonGLMTrainer("sqlite://", "models")
        X, y = t.extract_strikeout_features(df)
        # Identical rows → perfect collinearity (but we have only 1 row after groupby)
        # The IRLS with solve may fail on singular XWX
        # Just verify the method doesn't crash entirely
        with patch.object(PoissonGLMTrainer, "load_training_data", return_value=df):
            with pytest.raises((ValueError, np.linalg.LinAlgError)):
                t.train_strikeout_model([2024])


# ============================================================================
# evaluate_model
# ============================================================================


class TestEvaluateModel:
    def test_returns_metrics_dict(self, tmp_path):
        path = tmp_path / "model.json"
        model = {
            "intercept": 0.5,
            "coefficients": {"velo_centered": 0.1},
            "metrics": {
                "r_squared": 0.85,
                "mse": 0.12,
                "mae": 0.30,
                "train_samples": 100,
                "test_samples": 25,
            },
            "trained_at": "2026-05-20T12:00:00",
            "seasons": [2024],
        }
        with open(path, "w") as f:
            json.dump(model, f)

        t = PoissonGLMTrainer("sqlite://", "models")
        metrics = t.evaluate_model(str(path))
        assert metrics["r_squared"] == 0.85
        assert metrics["mse"] == 0.12
        assert metrics["mae"] == 0.30

    def test_file_not_found(self):
        t = PoissonGLMTrainer("sqlite://", "models")
        with pytest.raises(FileNotFoundError):
            t.evaluate_model("nonexistent.json")

    def test_loads_full_metrics(self, tmp_path):
        path = tmp_path / "model.json"
        model = {
            "intercept": 0.0,
            "coefficients": {},
            "metrics": {
                "r_squared": 0.0,
                "mse": 0.0,
                "mae": 0.0,
                "train_samples": 0,
                "test_samples": 0,
            },
            "trained_at": "",
            "seasons": [],
        }
        with open(path, "w") as f:
            json.dump(model, f)

        t = PoissonGLMTrainer("sqlite://", "models")
        metrics = t.evaluate_model(str(path))
        assert metrics["train_samples"] == 0
        assert metrics["test_samples"] == 0


# ============================================================================
# Integración: mock DB → train → evaluate
# ============================================================================


class TestIntegration:
    @patch("prediction.model_training.train_poisson_glm.pd.read_sql")
    def test_load_train_evaluate_flow(self, mock_read_sql, tmp_path):
        mock_read_sql.return_value = LARGER_RAW_DF
        d = str(tmp_path / "models")
        t = PoissonGLMTrainer("sqlite://", d)
        model = t.train_strikeout_model([2024])
        path = os.path.join(d, "strikeout_poisson_model.json")
        metrics = t.evaluate_model(path)
        assert metrics["r_squared"] >= -1.0  # valid R²
        assert metrics["train_samples"] + metrics["test_samples"] > 10

    @patch("prediction.model_training.train_poisson_glm.pd.read_sql")
    def test_save_then_load_roundtrip(self, mock_read_sql, tmp_path):
        mock_read_sql.return_value = LARGER_RAW_DF
        d = str(tmp_path / "models")
        t = PoissonGLMTrainer("sqlite://", d)
        model = t.train_strikeout_model([2024])
        path = os.path.join(d, "strikeout_poisson_model.json")
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["intercept"] == model["intercept"]
        for k in model["coefficients"]:
            assert loaded["coefficients"][k] == model["coefficients"][k]
