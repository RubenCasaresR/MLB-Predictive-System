"""Tests para etl/config.py (constantes y variables de entorno)."""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import etl.config as cfg


def _reload_config():
    """Re-import etl.config, clearing the cached module first."""
    if "etl.config" in sys.modules:
        del sys.modules["etl.config"]
    import etl.config as c

    return c


# ============================================================================
# BASE DE DATOS
# ============================================================================


class TestDBConfig:
    def test_default_host(self):
        assert cfg.DB_CONFIG["host"] == "localhost"

    def test_default_port(self):
        assert cfg.DB_CONFIG["port"] == 5432

    def test_default_database(self):
        assert cfg.DB_CONFIG["database"] == "mlb_predictive"

    def test_default_user(self):
        assert cfg.DB_CONFIG["user"] == "mlb_user"

    def test_default_password(self, monkeypatch):
        monkeypatch.setenv("MLB_DB_PASSWORD", "")
        c = _reload_config()
        assert c.DB_CONFIG["password"] == ""

    def test_database_url_contains_components(self):
        assert "postgresql://" in cfg.DATABASE_URL
        assert "mlb_user" in cfg.DATABASE_URL
        assert "localhost:5432" in cfg.DATABASE_URL
        assert "mlb_predictive" in cfg.DATABASE_URL

    def test_env_override_host(self, monkeypatch):
        monkeypatch.setenv("MLB_DB_HOST", "10.0.0.1")
        c = _reload_config()
        assert c.DB_CONFIG["host"] == "10.0.0.1"

    def test_env_override_port(self, monkeypatch):
        monkeypatch.setenv("MLB_DB_PORT", "9999")
        c = _reload_config()
        assert c.DB_CONFIG["port"] == 9999

    def test_env_override_database(self, monkeypatch):
        monkeypatch.setenv("MLB_DB_NAME", "test_db")
        c = _reload_config()
        assert c.DB_CONFIG["database"] == "test_db"

    def test_env_override_user(self, monkeypatch):
        monkeypatch.setenv("MLB_DB_USER", "admin")
        c = _reload_config()
        assert c.DB_CONFIG["user"] == "admin"

    def test_env_override_password(self, monkeypatch):
        monkeypatch.setenv("MLB_DB_PASSWORD", "secret")
        c = _reload_config()
        assert c.DB_CONFIG["password"] == "secret"

    def test_database_url_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        c = _reload_config()
        assert c.DATABASE_URL == "sqlite:///test.db"

    def test_database_url_default_format(self, monkeypatch):
        monkeypatch.setenv("MLB_DB_HOST", "db.example.com")
        monkeypatch.setenv("MLB_DB_PORT", "6432")
        monkeypatch.setenv("MLB_DB_NAME", "mlb_prod")
        monkeypatch.setenv("MLB_DB_USER", "svc_user")
        monkeypatch.setenv("MLB_DB_PASSWORD", "pw")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import dotenv
        monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
        c = _reload_config()
        assert c.DATABASE_URL == "postgresql://svc_user:pw@db.example.com:6432/mlb_prod"


# ============================================================================
# APIS DE DATOS
# ============================================================================


class TestAPIConfig:
    def test_statcast_base_url(self):
        assert cfg.STATCAST_BASE_URL == "https://statsapi.mlb.com/api/v1"

    def test_weather_base_url(self):
        assert cfg.WEATHER_BASE_URL == "https://api.weather.gov"

    def test_odds_base_url(self):
        assert cfg.ODDS_BASE_URL == "https://api.the-odds-api.com/v4"

    def test_weather_api_key_default(self, monkeypatch):
        monkeypatch.setenv("WEATHER_API_KEY", "")
        c = _reload_config()
        assert c.WEATHER_API_KEY == ""

    def test_odds_api_key_default(self, monkeypatch):
        monkeypatch.setenv("ODDS_API_KEY", "")
        c = _reload_config()
        assert c.ODDS_API_KEY == ""

    def test_weather_api_key_override(self, monkeypatch):
        monkeypatch.setenv("WEATHER_API_KEY", "wx-key-123")
        c = _reload_config()
        assert c.WEATHER_API_KEY == "wx-key-123"

    def test_odds_api_key_override(self, monkeypatch):
        monkeypatch.setenv("ODDS_API_KEY", "odds-key-456")
        c = _reload_config()
        assert c.ODDS_API_KEY == "odds-key-456"


# ============================================================================
# SPORTSBOOKS CONFIG
# ============================================================================


class TestSportsbooksConfig:
    def test_active_sportsbooks_count(self):
        assert len(cfg.ACTIVE_SPORTSBOOKS) == 3

    def test_draftkings_config(self):
        dk = cfg.ACTIVE_SPORTSBOOKS[0]
        assert dk["id"] == 1
        assert dk["name"] == "DraftKings"
        assert dk["api_endpoint"] == "https://api.draftkings.com"

    def test_fanduel_config(self):
        fd = cfg.ACTIVE_SPORTSBOOKS[1]
        assert fd["id"] == 2
        assert fd["name"] == "FanDuel"
        assert fd["api_endpoint"] == "https://api.fanduel.com"

    def test_betmgm_config(self):
        mgm = cfg.ACTIVE_SPORTSBOOKS[2]
        assert mgm["id"] == 3
        assert mgm["name"] == "BetMGM"
        assert mgm["api_endpoint"] == "https://api.betmgm.com"

    def test_market_poll_interval(self):
        assert cfg.MARKET_POLL_INTERVAL_SECONDS == 60

    def test_pre_game_window(self):
        assert cfg.MARKET_PRE_GAME_WINDOW_HOURS == 3


# ============================================================================
# PARÁMETROS DEL MOTOR PREDICTIVO
# ============================================================================


class TestPredictiveEngineParams:
    def test_monte_carlo_iterations(self):
        assert cfg.MONTE_CARLO_DEFAULT_ITERATIONS == 10000

    def test_monte_carlo_seed(self):
        assert cfg.MONTE_CARLO_SEED == 42

    def test_kelly_fraction(self):
        assert cfg.KELLY_FRACTION == 0.25

    def test_max_kelly_bet(self):
        assert cfg.MAX_KELLY_BET == 0.05

    def test_ev_threshold(self):
        assert cfg.EV_MINIMUM_THRESHOLD == 0.02

    def test_bankroll_initial_default(self):
        assert cfg.BANKROLL_INITIAL == 10000.0

    def test_bankroll_initial_override(self, monkeypatch):
        monkeypatch.setenv("BANKROLL_INITIAL", "50000")
        c = _reload_config()
        assert c.BANKROLL_INITIAL == 50000.0

    def test_bankroll_currency(self):
        assert cfg.BANKROLL_CURRENCY == "USD"


# ============================================================================
# RUTAS DE ARCHIVOS
# ============================================================================


class TestPaths:
    def test_data_dir_default(self):
        assert cfg.DATA_DIR == "data"

    def test_models_dir_default(self):
        assert cfg.MODELS_DIR == "models"

    def test_logs_dir_default(self):
        assert cfg.LOGS_DIR == "logs"

    def test_paths_constructed_correctly(self):
        assert cfg.PATHS["data_dir"] == "data"
        assert cfg.PATHS["models_dir"] == "models"
        assert cfg.PATHS["logs_dir"] == "logs"
        assert cfg.PATHS["statcast_raw"] == os.path.join("data", "statcast_raw")
        assert cfg.PATHS["market_raw"] == os.path.join("data", "market_raw")
        assert cfg.PATHS["weather_raw"] == os.path.join("data", "weather_raw")
        assert cfg.PATHS["features_parquet"] == os.path.join("data", "features")
        assert cfg.PATHS["model_registry"] == os.path.join("models", "registry.json")

    def test_data_dir_override(self, monkeypatch):
        monkeypatch.setenv("MLB_DATA_DIR", "/custom/data")
        c = _reload_config()
        assert c.DATA_DIR == "/custom/data"
        assert c.PATHS["statcast_raw"] == os.path.join("/custom/data", "statcast_raw")

    def test_models_dir_override(self, monkeypatch):
        monkeypatch.setenv("MLB_MODELS_DIR", "/custom/models")
        c = _reload_config()
        assert c.MODELS_DIR == "/custom/models"
        assert c.PATHS["model_registry"] == os.path.join("/custom/models", "registry.json")

    def test_logs_dir_override(self, monkeypatch):
        monkeypatch.setenv("MLB_LOGS_DIR", "/custom/logs")
        c = _reload_config()
        assert c.LOGS_DIR == "/custom/logs"


# ============================================================================
# LOGGING
# ============================================================================


class TestLoggingConfig:
    def test_logging_config_structure(self):
        assert cfg.LOGGING_CONFIG["version"] == 1
        assert "formatters" in cfg.LOGGING_CONFIG
        assert "handlers" in cfg.LOGGING_CONFIG
        assert "root" in cfg.LOGGING_CONFIG

    def test_standard_formatter(self):
        fmt = cfg.LOGGING_CONFIG["formatters"]["standard"]["format"]
        assert "%(asctime)s" in fmt
        assert "%(levelname)s" in fmt
        assert "%(name)s" in fmt

    def test_console_handler(self):
        h = cfg.LOGGING_CONFIG["handlers"]["console"]
        assert h["class"] == "logging.StreamHandler"

    def test_file_handler(self):
        h = cfg.LOGGING_CONFIG["handlers"]["file"]
        assert h["class"] == "logging.handlers.RotatingFileHandler"
        assert h["maxBytes"] == 10485760
        assert h["backupCount"] == 5

    def test_default_log_level(self):
        assert cfg.LOGGING_CONFIG["root"]["level"] == "INFO"

    def test_log_level_override(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        c = _reload_config()
        assert c.LOGGING_CONFIG["root"]["level"] == "DEBUG"


# ============================================================================
# FEATURE ENGINEERING PARAMS
# ============================================================================


class TestFeatureParams:
    def test_rolling_windows(self):
        assert cfg.ROLLING_WINDOWS == [7, 14, 30]

    def test_woba_season(self):
        assert cfg.WOBA_SEASON == 2024

    def test_fatigue_params(self):
        assert cfg.FATIGUE_PARAMS["velo_drop_threshold"] == 1.5
        assert cfg.FATIGUE_PARAMS["spin_drop_threshold"] == 150
        assert cfg.FATIGUE_PARAMS["high_pitch_count"] == 100
        assert cfg.FATIGUE_PARAMS["tz_crossing_penalty"] == 0.08

    def test_sharp_money_params(self):
        assert cfg.SHARP_MONEY_PARAMS["discrepancy_threshold"] == 0.12
        assert cfg.SHARP_MONEY_PARAMS["rlm_ticket_threshold"] == 0.55
        assert cfg.SHARP_MONEY_PARAMS["min_line_movement"] == 5
