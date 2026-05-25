# =============================================================================
# config.py
# Configuración central del sistema MLB Predictive System
# Rubén Eduardo Casares Rosales
# =============================================================================
# Variables de entorno, conexiones a APIs, DB, y parámetros globales.
# =============================================================================

import os
from dotenv import load_dotenv
load_dotenv()
from dataclasses import dataclass, field
from typing import Dict, Optional


# ============================================================================
# BASE DE DATOS
# ============================================================================

DB_CONFIG = {
    "host": os.getenv("MLB_DB_HOST", "localhost"),
    "port": int(os.getenv("MLB_DB_PORT", "5432")),
    "database": os.getenv("MLB_DB_NAME", "mlb_predictive"),
    "user": os.getenv("MLB_DB_USER", "mlb_user"),
    "password": os.getenv("MLB_DB_PASSWORD", ""),
}

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)


# ============================================================================
# APIS DE DATOS
# ============================================================================

STATCAST_BASE_URL = "https://statsapi.mlb.com/api/v1"

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
WEATHER_BASE_URL = "https://api.weather.gov"

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_BASE_URL = "https://api.the-odds-api.com/v4"


# ============================================================================
# SPORTSBOOKS CONFIG
# ============================================================================

ACTIVE_SPORTSBOOKS = [
    {"id": 1, "name": "DraftKings", "api_endpoint": "https://api.draftkings.com"},
    {"id": 2, "name": "FanDuel", "api_endpoint": "https://api.fanduel.com"},
    {"id": 3, "name": "BetMGM", "api_endpoint": "https://api.betmgm.com"},
]

MARKET_POLL_INTERVAL_SECONDS = 60  # Cada minuto en ventana de juego activo
MARKET_PRE_GAME_WINDOW_HOURS = 3  # 3 horas antes del juego


# ============================================================================
# PARÁMETROS DEL MOTOR PREDICTIVO
# ============================================================================

MONTE_CARLO_DEFAULT_ITERATIONS = 10000
MONTE_CARLO_SEED = 42

KELLY_FRACTION = 0.25      # Kelly fraccional (25%)
MAX_KELLY_BET = 0.05       # Máximo 5% del bankroll por apuesta
EV_MINIMUM_THRESHOLD = 0.02  # Mínimo 2% de EV para considerar apuesta

BANKROLL_INITIAL = float(os.getenv("BANKROLL_INITIAL", "10000"))
BANKROLL_CURRENCY = "USD"


# ============================================================================
# RUTAS DE ARCHIVOS
# ============================================================================

DATA_DIR = os.getenv("MLB_DATA_DIR", "data")
MODELS_DIR = os.getenv("MLB_MODELS_DIR", "models")
LOGS_DIR = os.getenv("MLB_LOGS_DIR", "logs")

PATHS = {
    "data_dir": DATA_DIR,
    "models_dir": MODELS_DIR,
    "logs_dir": LOGS_DIR,
    "statcast_raw": os.path.join(DATA_DIR, "statcast_raw"),
    "market_raw": os.path.join(DATA_DIR, "market_raw"),
    "weather_raw": os.path.join(DATA_DIR, "weather_raw"),
    "features_parquet": os.path.join(DATA_DIR, "features"),
    "model_registry": os.path.join(MODELS_DIR, "registry.json"),
}


# ============================================================================
# LOGGING
# ============================================================================

LOGGING_CONFIG = {
    "version": 1,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOGS_DIR, "mlb_system.log"),
            "maxBytes": 10485760,
            "backupCount": 5,
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
}


# ============================================================================
# FEATURE ENGINEERING PARAMS
# ============================================================================

ROLLING_WINDOWS = [7, 14, 30]
WOBA_SEASON = 2024

FATIGUE_PARAMS = {
    "velo_drop_threshold": 1.5,
    "spin_drop_threshold": 150,
    "high_pitch_count": 100,
    "tz_crossing_penalty": 0.08,
}

SHARP_MONEY_PARAMS = {
    "discrepancy_threshold": 0.12,
    "rlm_ticket_threshold": 0.55,
    "min_line_movement": 5,
}
