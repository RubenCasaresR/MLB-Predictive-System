# =============================================================================
# train_poisson_glm.py
# Entrenamiento del Modelo Poisson GLM para Props
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Entrena modelos de regresión Poisson usando datos históricos de Statcast.
# Los coeficientes se guardan para usarse en inferencia (poisson_props.py).
#
# El modelo se re-entrena:
#   - Diariamente (incremental)
#   - Completamente al inicio de cada temporada
# =============================================================================

import json
import logging
import os
import pickle
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class PoissonGLMTrainer:
    def __init__(self, db_url: str, models_dir: str = "models"):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.models_dir = models_dir
        os.makedirs(models_dir, exist_ok=True)
        logger.info(f"PoissonGLMTrainer initialized (models_dir={models_dir})")

    def load_training_data(self, seasons: list[int] = [2022, 2023, 2024]) -> pd.DataFrame:
        logger.info(f"Loading training data for seasons {seasons}")
        season_list = ", ".join(str(s) for s in seasons)

        query = f"""
        SELECT
            ab.pitcher_id,
            ab.batter_id,
            p.release_speed AS velo,
            p.release_spin_rate AS spin,
            p.pfx_x,
            p.pfx_z,
            p.zone,
            p.strike,
            p.whiff,
            g.season,
            g.game_date,
            CASE WHEN ab.events IN ('Strikeout','Strikeout Double Play') THEN 1 ELSE 0 END AS is_k
        FROM pitches p
        JOIN at_bats ab ON ab.ab_id = p.ab_id
        JOIN games g ON g.game_id = ab.game_id
        WHERE g.season IN ({season_list})
          AND p.release_speed IS NOT NULL
        LIMIT 50000
        """
        df = pd.read_sql(query, self.engine)
        logger.info(f"Loaded {len(df)} training samples")
        return df

    def extract_strikeout_features(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        agg = (
            df.groupby(["pitcher_id", "game_date"])
            .agg(
                avg_velo=("velo", "mean"),
                avg_spin=("spin", "mean"),
                whiff_rate=("whiff", "mean"),
                k_count=("is_k", "sum"),
                total_pitches=("is_k", "count"),
            )
            .reset_index()
        )

        agg["k_per_game"] = agg["k_count"]
        agg["velo_centered"] = agg["avg_velo"] - 93.0
        agg["spin_centered"] = (agg["avg_spin"] - 2200.0) / 100.0

        features = agg[["velo_centered", "whiff_rate", "spin_centered"]].values
        targets = agg["k_per_game"].values

        return features, targets

    def train_strikeout_model(self, seasons: list[int] = [2022, 2023, 2024]) -> dict:
        df = self.load_training_data(seasons)
        X, y = self.extract_strikeout_features(df)

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        X_train = np.column_stack([np.ones(X_train.shape[0]), X_train])
        X_test = np.column_stack([np.ones(X_test.shape[0]), X_test])

        beta = np.zeros(X_train.shape[1])
        for _ in range(100):
            mu = np.exp(X_train @ beta)
            W = np.diag(mu)
            try:
                XWX = X_train.T @ W @ X_train
                XWy = X_train.T @ W @ (X_train @ beta + (y_train - mu) / mu)
                beta_new = np.linalg.solve(XWX, XWy)
                if np.allclose(beta, beta_new, rtol=1e-6):
                    break
                beta = beta_new
            except np.linalg.LinAlgError:
                logger.warning("SVD decomposition used for stability")
                beta = np.linalg.lstsq(
                    np.sqrt(W) @ X_train,
                    np.sqrt(W) @ (X_train @ beta + (y_train - mu) / mu),
                    rcond=None,
                )[0]

        y_pred = np.exp(X_test @ beta)
        r2 = r2_score(y_test, y_pred)
        mse = mean_squared_error(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)

        model = {
            "intercept": float(beta[0]),
            "coefficients": {
                "velo_centered": float(beta[1]),
                "whiff_rate": float(beta[2]),
                "spin_centered": float(beta[3]),
            },
            "metrics": {
                "r_squared": round(r2, 4),
                "mse": round(mse, 4),
                "mae": round(mae, 4),
                "train_samples": len(X_train),
                "test_samples": len(X_test),
            },
            "trained_at": datetime.now().isoformat(),
            "seasons": seasons,
        }

        path = os.path.join(self.models_dir, "strikeout_poisson_model.json")
        with open(path, "w") as f:
            json.dump(model, f, indent=2)

        logger.info(f"Strikeout model trained: R²={r2:.4f}, MAE={mae:.4f}, saved to {path}")
        return model

    def evaluate_model(self, model_path: str, test_data: pd.DataFrame | None = None):
        with open(model_path) as f:
            model = json.load(f)

        logger.info(f"Model metrics: {model['metrics']}")
        return model["metrics"]


# ============================================================================
# MODO LÍNEA DE COMANDOS
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from etl.config import DATABASE_URL, MODELS_DIR

    trainer = PoissonGLMTrainer(DATABASE_URL, MODELS_DIR)
    model = trainer.train_strikeout_model(seasons=[2023, 2024])
    trainer.evaluate_model(os.path.join(MODELS_DIR, "strikeout_poisson_model.json"))
