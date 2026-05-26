# =============================================================================
# train_multiclass_model.py
# Entrena un CatBoostClassifier multiclase (8 clases) para predecir
# el resultado de cada aparición al plato (PA).
#
# Las probabilidades suaves de predict_proba() alimentan el simulador
# Monte Carlo, reemplazando los multiplicadores heurísticos.
#
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import logging
import os
from datetime import date, datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from pandas import DataFrame, Series
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapeo de eventos MLB → 8 clases (0..7)
# Debe coincidir 1:1 con PAOutcome en monte_carlo_simulator.py
# ---------------------------------------------------------------------------

EVENT_MAP = {
    # 0: OUT
    "Strikeout": 0,
    "Strikeout Double Play": 0,
    "Field Out": 0,
    "Forceout": 0,
    "Grounded Into DP": 0,
    "Double Play": 0,
    "Triple Play": 0,
    "Fielders Choice Out": 0,
    "Runner Out": 0,
    "Other Out": 0,
    "Bunt Lineout": 0,
    "Lineout": 0,
    "Pop Out": 0,
    "Flyout": 0,
    "Groundout": 0,
    "Bunt Groundout": 0,
    # 1: SINGLE
    "Single": 1,
    # 2: DOUBLE
    "Double": 2,
    # 3: TRIPLE
    "Triple": 3,
    # 4: HOME RUN
    "Home Run": 4,
    # 5: WALK
    "Walk": 5,
    "Intent Walk": 5,
    # 6: HIT BY PITCH
    "Hit By Pitch": 6,
    # 7: SACRIFICE (separado de OUT — el simulador necesita la distinción)
    "Sac Fly": 7,
    "Sac Bunt": 7,
}

CLASS_NAMES = [
    "out",
    "single",
    "double",
    "triple",
    "home_run",
    "walk",
    "hit_by_pitch",
    "sacrifice",
]

# ---------------------------------------------------------------------------
# Query de extracción
# Una fila por at_bat con contexto completo del juego.
# ---------------------------------------------------------------------------

TRAINING_QUERY = """
SELECT
    ab.ab_id,
    g.game_id,
    g.game_date,
    g.venue_id                              AS stadium_id,
    g.home_plate_umpire_id                  AS umpire_id,

    ab.inning,
    ab.half_inning,
    ab.outs_before,

    ab.batter_id,
    ab.pitcher_id,
    pb.bats                                 AS batter_bats,
    pp.throws                               AS pitcher_throws,
    pp.primary_position                     AS pitcher_role,

    -- Rolling stats del pitcher (ventana 30d)
    prs_p.k_per_9_30d,
    prs_p.bb_per_9_30d,
    prs_p.hr_per_9_30d,
    prs_p.fip_30d,
    prs_p.avg_velo_30d,
    prs_p.whiff_pct_30d,

    -- Rolling stats del bateador (ventana 30d)
    prs_b.woba_30d,
    prs_b.k_pct_30d,
    prs_b.bb_pct_30d,
    prs_b.slg_30d,
    prs_b.hard_hit_pct_30d,
    prs_b.barrel_pct_30d,

    -- Factor del parque
    pf.pf_hr                                AS park_hr,
    pf.pf_k                                 AS park_k,
    pf.pf_woba                              AS park_woba,

    -- Clima
    w.temperature,
    w.wind_speed,
    w.wind_direction,

    -- Umpire
    u.called_strike_rate                    AS umpire_cs_rate,

    -- Bullpen del equipo del pitcher
    trs.bullpen_fip_30d,

    -- Target
    ab.events
FROM at_bats ab
JOIN games g            ON g.game_id = ab.game_id
JOIN players pb         ON pb.player_id = ab.batter_id
JOIN players pp         ON pp.player_id = ab.pitcher_id

LEFT JOIN player_rolling_stats prs_p
    ON prs_p.player_id = ab.pitcher_id
   AND prs_p.game_id   = g.game_id

LEFT JOIN player_rolling_stats prs_b
    ON prs_b.player_id = ab.batter_id
   AND prs_b.game_id   = g.game_id

LEFT JOIN park_factors_monthly pf
    ON pf.stadium_id = g.venue_id
   AND pf.season     = g.season
   AND pf.month      = EXTRACT(MONTH FROM g.game_date)

LEFT JOIN weather_hourly w
    ON w.game_id = g.game_id
   AND w.forecast_hour = date_trunc('hour', g.start_time_et)

LEFT JOIN umpires u
    ON u.umpire_id = g.home_plate_umpire_id

LEFT JOIN team_rolling_stats trs
    ON trs.team_id = pp.team_id
   AND trs.game_id = g.game_id

WHERE g.status = 'FINAL'
  AND ab.events IS NOT NULL
  AND g.game_date < :cutoff_date
ORDER BY g.game_date, ab.ab_id
"""

# ---------------------------------------------------------------------------
# Columnas del feature vector
# ---------------------------------------------------------------------------

CATEGORICAL_FEATURES: list[str] = [
    "stadium_id",
    "umpire_id",
    "batter_id",
    "pitcher_id",
    "batter_bats",
    "pitcher_throws",
    "half_inning",
    "wind_direction",
]

NUMERIC_FEATURES: list[str] = [
    "inning",
    "outs_before",
    "k_per_9_30d",
    "bb_per_9_30d",
    "hr_per_9_30d",
    "fip_30d",
    "avg_velo_30d",
    "whiff_pct_30d",
    "woba_30d",
    "k_pct_30d",
    "bb_pct_30d",
    "slg_30d",
    "hard_hit_pct_30d",
    "barrel_pct_30d",
    "park_hr",
    "park_k",
    "park_woba",
    "temperature",
    "wind_speed",
    "umpire_cs_rate",
    "bullpen_fip_30d",
]

# Valores por defecto (promedios MLB 2026) para imputar nulos
DEFAULT_VALS: dict = {
    "k_per_9_30d": 8.0,
    "bb_per_9_30d": 3.0,
    "hr_per_9_30d": 1.2,
    "fip_30d": 4.20,
    "avg_velo_30d": 93.0,
    "whiff_pct_30d": 24.0,
    "woba_30d": 0.320,
    "k_pct_30d": 22.0,
    "bb_pct_30d": 8.5,
    "slg_30d": 0.420,
    "hard_hit_pct_30d": 38.0,
    "barrel_pct_30d": 8.0,
    "park_hr": 1.0,
    "park_k": 1.0,
    "park_woba": 1.0,
    "temperature": 70.0,
    "wind_speed": 0.0,
    "umpire_cs_rate": 0.63,
    "bullpen_fip_30d": 4.50,
}


# ============================================================================
# Carga de datos
# ============================================================================


def load_training_data(
    db_url: str,
    cutoff_date: date,
) -> DataFrame:
    """Ejecuta la query y devuelve un DataFrame con features + target crudos."""
    engine = create_engine(db_url)
    logger.info("Loading training data from DB (cutoff=%s)...", cutoff_date)
    df = pd.read_sql(
        text(TRAINING_QUERY),
        engine,
        params={"cutoff_date": cutoff_date},
        parse_dates=["game_date"],
    )
    logger.info("Loaded %d at-bats", len(df))
    return df


# ============================================================================
# Feature Engineering
# ============================================================================


def map_target(y_events: Series) -> Series:
    """Convierte events string a entero de clase 0..7."""
    return y_events.map(EVENT_MAP).fillna(0).astype(np.int8)


def build_platoon_advantage(df: DataFrame) -> Series:
    """Regla de negocio:
    has_platoon_advantage = 1 si:
      - batter_bats='L' y pitcher_throws='R', o
      - batter_bats='R' y pitcher_throws='L', o
      - batter_bats='S' (switch-hitter siempre elige lado ventajoso)
    = 0 en cualquier otro caso."""
    b = df["batter_bats"]
    p = df["pitcher_throws"]
    return (((b == "L") & (p == "R")) | ((b == "R") & (p == "L")) | (b == "S")).astype(np.int8)


def engineer_features(df: DataFrame) -> DataFrame:
    """Construye el feature matrix X listo para CatBoost."""
    logger.info("Engineering features...")

    # --- Imputar nulos numéricos con promedios de liga ---
    for col, default in DEFAULT_VALS.items():
        if col in df.columns:
            df[col] = df[col].fillna(default)

    # --- Categóricas: llenar nulos con token especial ---
    for col in CATEGORICAL_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna("__MISSING__")

    # --- Feature derivada: platoon advantage ---
    df["has_platoon_advantage"] = build_platoon_advantage(df)

    # --- Feature derivada: temperatura extrema ---
    df["heat_stress"] = np.maximum(0, (df["temperature"] - 80) / 40.0)
    df["cold_stress"] = np.maximum(0, (50 - df["temperature"]) / 30.0)

    # --- Feature derivada: fatiga de inning ---
    df["late_inning"] = (df["inning"] >= 7).astype(np.int8)

    # --- Feature derivada: bullpen activo ---
    # 1 si el pitcher es relevista (RP) o el inning >= 7
    df["is_bullpen_active"] = ((df["pitcher_role"] == "RP") | (df["inning"] >= 7)).astype(np.int8)

    # --- Orden de columnas: cat first, then num, then derived ---
    derived_features = [
        "has_platoon_advantage",
        "heat_stress",
        "cold_stress",
        "late_inning",
        "is_bullpen_active",
    ]
    feature_cols = CATEGORICAL_FEATURES + NUMERIC_FEATURES + derived_features
    X = df[feature_cols].copy()

    logger.info(
        "Feature matrix: %d rows, %d cols (%d cat, %d num, %d derived)",
        X.shape[0],
        X.shape[1],
        len(CATEGORICAL_FEATURES),
        len(NUMERIC_FEATURES),
        len(derived_features),
    )
    return X


# ============================================================================
# Split cronológico
# ============================================================================


def chronological_split(
    X: DataFrame,
    y: Series,
    df_raw: DataFrame,
    val_start: date,
    test_start: date,
) -> tuple[DataFrame, DataFrame, DataFrame, Series, Series, Series]:
    """Divide en train / validation / test por fecha de juego.
    Esto evita data leakage (no entrenamos con el futuro)."""
    val_start_ts = pd.Timestamp(val_start)
    test_start_ts = pd.Timestamp(test_start)
    train_mask = df_raw["game_date"] < val_start_ts
    val_mask = (df_raw["game_date"] >= val_start_ts) & (df_raw["game_date"] < test_start_ts)
    test_mask = df_raw["game_date"] >= test_start_ts

    X_train = X[train_mask].reset_index(drop=True)
    X_val = X[val_mask].reset_index(drop=True)
    X_test = X[test_mask].reset_index(drop=True)
    y_train = y[train_mask].reset_index(drop=True)
    y_val = y[val_mask].reset_index(drop=True)
    y_test = y[test_mask].reset_index(drop=True)

    logger.info("Split: train=%d  val=%d  test=%d", len(X_train), len(X_val), len(X_test))
    return X_train, X_val, X_test, y_train, y_val, y_test


# ============================================================================
# Entrenamiento
# ============================================================================


def train_model(
    X_train: DataFrame,
    y_train: Series,
    X_val: DataFrame,
    y_val: Series,
    models_dir: str = "models",
) -> CatBoostClassifier:
    """Entrena CatBoost multiclase con early stopping.
    Sin balanceo de clases — las probs crudas deben reflejar
    la distribución real de MLB para el Monte Carlo."""

    cat_indices = list(range(len(CATEGORICAL_FEATURES)))

    model = CatBoostClassifier(
        iterations=1500,
        learning_rate=0.05,
        depth=6,
        loss_function="MultiClass",
        eval_metric="MultiClass",
        cat_features=cat_indices,
        random_seed=42,
        od_type="Iter",
        od_wait=40,
        verbose=200,
        allow_writing_files=False,
        thread_count=-1,
    )

    logger.info("Starting CatBoost training...")
    model.fit(
        X_train,
        y_train,
        eval_set=(X_val, y_val),
        use_best_model=True,
        plot=False,
    )

    best_iter = model.get_best_iteration()
    logger.info("Training finished. Best iteration = %d", best_iter)

    os.makedirs(models_dir, exist_ok=True)
    path = os.path.join(models_dir, "pa_multiclass_model.cbm")
    model.save_model(path)
    logger.info("Model saved to %s", path)

    return model


# ============================================================================
# Evaluación
# ============================================================================


def evaluate_model(
    model: CatBoostClassifier,
    X_test: DataFrame,
    y_test: Series,
) -> None:
    """Evalúa en test set: accuracy, logloss, matriz de confusión,
    y probs promedio por clase (calibración gruesa)."""
    from sklearn.metrics import classification_report, confusion_matrix, log_loss

    y_pred = model.predict(X_test).flatten()
    y_proba = model.predict_proba(X_test)

    acc = (y_pred == y_test.values).mean()
    logger.info("Test accuracy: %.4f", acc)

    ll = log_loss(y_test, y_proba, labels=list(range(8)))
    logger.info("Test logloss: %.4f", ll)

    cm = confusion_matrix(y_test, y_pred)
    logger.info("Confusion matrix:\n%s", cm)

    report = classification_report(
        y_test,
        y_pred,
        target_names=CLASS_NAMES,
        digits=4,
    )
    logger.info("Classification report:\n%s", report)

    avg_proba = pd.DataFrame(y_proba, columns=CLASS_NAMES).mean()
    logger.info("Avg predicted probability per class:\n%s", avg_proba)


# ============================================================================
# Feature Importance
# ============================================================================


def analyze_feature_importance(
    model: CatBoostClassifier,
    feature_names: list[str],
    output_dir: str = "models",
) -> None:
    """Exporta importancia de features (PredictionValuesChange) a CSV y PNG.

    Args:
        model: CatBoost model entrenado.
        feature_names: Lista ordenada de nombres de features.
        output_dir: Directorio de salida (default: models/).
    """
    importances = model.get_feature_importance(type="PredictionValuesChange")
    fi_df = pd.DataFrame(
        {
            "feature": feature_names,
            "importance": importances,
        }
    ).sort_values("importance", ascending=False)

    csv_path = os.path.join(output_dir, "feature_importance.csv")
    fi_df.to_csv(csv_path, index=False)
    logger.info("Feature importance CSV saved to %s", csv_path)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        top_n = min(30, len(fi_df))
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.barh(
            range(top_n),
            fi_df["importance"].values[:top_n][::-1],
        )
        ax.set_yticks(range(top_n))
        ax.set_yticklabels(fi_df["feature"].values[:top_n][::-1])
        ax.set_xlabel("Importance (PredictionValuesChange)")
        ax.set_title(f"Top {top_n} Feature Importance")
        fig.tight_layout()

        png_path = os.path.join(output_dir, "feature_importance.png")
        fig.savefig(png_path, dpi=150)
        plt.close(fig)
        logger.info("Feature importance chart saved to %s", png_path)

    except ImportError:
        logger.warning("matplotlib not available — skipping chart export")


# ============================================================================
# Pipeline completo
# ============================================================================


def run_training_pipeline(
    db_url: str,
    models_dir: str = "models",
    data_cutoff: date = date(2026, 5, 26),
    train_cutoff: date = date(2026, 5, 16),
    val_cutoff: date = date(2026, 5, 21),
) -> CatBoostClassifier:
    """Pipeline completo: extraer → features → train → evaluar."""

    df_raw = load_training_data(db_url, cutoff_date=data_cutoff)

    last_date = df_raw["game_date"].max()
    logger.info("Data range: %s to %s", df_raw["game_date"].min(), last_date)

    # Convert split dates to Timestamps for comparison
    tc = pd.Timestamp(train_cutoff)
    vc = pd.Timestamp(val_cutoff)
    if tc > last_date:
        tc = last_date - pd.Timedelta(days=6)
        vc = last_date - pd.Timedelta(days=1)
        logger.warning("Adjusted splits: train < %s, val < %s", tc.date(), vc.date())

    y = map_target(df_raw["events"])

    X = engineer_features(df_raw)

    X_train, X_val, X_test, y_train, y_val, y_test = chronological_split(
        X,
        y,
        df_raw,
        val_start=tc,
        test_start=vc,
    )

    model = train_model(X_train, y_train, X_val, y_val, models_dir)

    evaluate_model(model, X_test, y_test)

    feature_names = (
        CATEGORICAL_FEATURES
        + NUMERIC_FEATURES
        + [
            "has_platoon_advantage",
            "heat_stress",
            "cold_stress",
            "late_inning",
            "is_bullpen_active",
        ]
    )
    analyze_feature_importance(model, feature_names, models_dir)

    return model


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from etl.config import DATABASE_URL, MODELS_DIR

    run_training_pipeline(DATABASE_URL, MODELS_DIR)
