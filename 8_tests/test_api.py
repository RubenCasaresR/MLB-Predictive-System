"""Tests de integración API con FastAPI TestClient + SQLite en memoria."""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.app import app


def _create_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                role TEXT DEFAULT 'user'
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                game_date TEXT NOT NULL,
                season INTEGER,
                home_team_id TEXT,
                away_team_id TEXT,
                status TEXT DEFAULT 'SCHEDULED',
                venue_id INTEGER,
                start_time_et TEXT,
                home_probable_pitcher INTEGER,
                away_probable_pitcher INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                team_id TEXT,
                signal_type TEXT,
                confidence REAL,
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_read INTEGER DEFAULT 0
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS approved_bets (
                bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                team TEXT,
                opponent TEXT,
                sportsbook TEXT,
                market_type TEXT,
                odds INTEGER,
                edge REAL,
                kelly_fraction REAL,
                recommended_stake REAL,
                confidence REAL,
                status TEXT DEFAULT 'pending',
                user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bet_history (
                bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                team TEXT,
                market_type TEXT,
                odds INTEGER,
                stake REAL,
                won INTEGER,
                profit_loss REAL,
                kelly_pct REAL,
                edge REAL,
                sportsbook TEXT,
                placed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS simulation_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL UNIQUE,
                home_win_prob REAL,
                away_win_prob REAL,
                mean_home_runs REAL,
                mean_away_runs REAL,
                std_home_runs REAL,
                std_away_runs REAL,
                extra_innings_prob REAL,
                walkoff_prob REAL,
                run_distribution TEXT,
                n_iterations INTEGER,
                computed_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bankroll_state (
                state_id INTEGER PRIMARY KEY AUTOINCREMENT,
                current REAL NOT NULL DEFAULT 10000.0,
                initial REAL NOT NULL DEFAULT 10000.0,
                peak REAL NOT NULL DEFAULT 10000.0,
                total_wagered REAL NOT NULL DEFAULT 0.0,
                total_profit REAL NOT NULL DEFAULT 0.0,
                bet_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))


def _seed_data(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT OR IGNORE INTO games (game_id, game_date, home_team_id, away_team_id, status)
            VALUES ('2026-05-20-NYY-BOS', '2026-05-20', 'BOS', 'NYY', 'SCHEDULED')
        """))


@pytest.fixture(autouse=True)
def setup_db():
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"

    old_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    _create_tables(engine)
    _seed_data(engine)

    yield

    engine.dispose()
    if old_db_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = old_db_url
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


# ============================================================================
# Tests
# ============================================================================

class TestHealth:
    def test_health_endpoint(self, monkeypatch):
        import requests as http_requests
        monkeypatch.setattr(http_requests, "get", lambda *a, **kw: type("R", (), {
            "ok": True, "status_code": 200, "json": lambda: {}
        })())
        resp = TestClient(app).get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "components" in data
        assert "database" in data["components"]
        assert data["version"] == "1.0.0"


class TestAuth:
    def test_register(self):
        resp = TestClient(app).post("/api/v1/auth/register", json={
            "username": "testuser",
            "password": "testpass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user_id"] > 0

    def test_register_duplicate(self):
        client = TestClient(app)
        client.post("/api/v1/auth/register", json={
            "username": "dupuser",
            "password": "pass123",
        })
        resp = client.post("/api/v1/auth/register", json={
            "username": "dupuser",
            "password": "pass123",
        })
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_login_success(self):
        client = TestClient(app)
        client.post("/api/v1/auth/register", json={
            "username": "loginuser",
            "password": "mypassword",
        })
        resp = client.post("/api/v1/auth/login", data={
            "username": "loginuser",
            "password": "mypassword",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self):
        client = TestClient(app)
        client.post("/api/v1/auth/register", json={
            "username": "badpassuser",
            "password": "correctpw",
        })
        resp = client.post("/api/v1/auth/login", data={
            "username": "badpassuser",
            "password": "wrongpw",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self):
        resp = TestClient(app).post("/api/v1/auth/login", data={
            "username": "ghost",
            "password": "x",
        })
        assert resp.status_code == 401


class TestPublicEndpoints:
    def test_root(self):
        resp = TestClient(app).get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "MLB Predictive System"
        assert "docs" in data

    def test_alerts_list(self):
        resp = TestClient(app).get("/api/v1/alerts/")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "total" in data
        assert "unread_count" in data


class TestBetsProtected:
    def test_ev_requires_auth(self):
        resp = TestClient(app).post("/api/v1/bets/ev", json={
            "game_id": "test",
            "home_odds": -110,
            "away_odds": -110,
            "home_real_prob": 0.55,
            "away_real_prob": 0.45,
        })
        assert resp.status_code == 401

    def test_ev_with_token(self):
        cli = TestClient(app)
        cli.post("/api/v1/auth/register", json={
            "username": "bettor", "password": "pass123",
        })
        token = cli.post("/api/v1/auth/login", data={
            "username": "bettor", "password": "pass123",
        }).json()["access_token"]
        resp = cli.post("/api/v1/bets/ev", json={
            "game_id": "test",
            "home_odds": -110,
            "away_odds": -110,
            "home_real_prob": 0.55,
            "away_real_prob": 0.45,
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "bets" in data
        assert len(data["bets"]) > 0

    def test_approved_requires_auth(self):
        resp = TestClient(app).get("/api/v1/bets/approved")
        assert resp.status_code == 401

    def test_approved_with_token(self):
        cli = TestClient(app)
        cli.post("/api/v1/auth/register", json={
            "username": "approver", "password": "pass",
        })
        token = cli.post("/api/v1/auth/login", data={
            "username": "approver", "password": "pass",
        }).json()["access_token"]
        resp = cli.get("/api/v1/bets/approved",
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_simulate_history_requires_auth(self):
        resp = TestClient(app).get("/api/v1/bets/simulate/2026-05-20-NYY-BOS")
        assert resp.status_code == 401

    def test_history_requires_auth(self):
        resp = TestClient(app).get("/api/v1/bets/history")
        assert resp.status_code == 401





class TestRiskProtected:
    def test_bankroll_requires_auth(self):
        resp = TestClient(app).get("/api/v1/risk/bankroll")
        assert resp.status_code == 401

    def test_bankroll_with_token(self):
        cli = TestClient(app)
        cli.post("/api/v1/auth/register", json={
            "username": "riskuser", "password": "riskpass",
        })
        token = cli.post("/api/v1/auth/login", data={
            "username": "riskuser", "password": "riskpass",
        }).json()["access_token"]
        resp = cli.get("/api/v1/risk/bankroll",
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "current" in data
        assert "initial" in data

    def test_limits_requires_auth(self):
        resp = TestClient(app).get("/api/v1/risk/limits")
        assert resp.status_code == 401

    def test_limits_with_token(self):
        cli = TestClient(app)
        cli.post("/api/v1/auth/register", json={
            "username": "limitsuser", "password": "pass",
        })
        token = cli.post("/api/v1/auth/login", data={
            "username": "limitsuser", "password": "pass",
        }).json()["access_token"]
        resp = cli.get("/api/v1/risk/limits",
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "max_per_bet" in data
