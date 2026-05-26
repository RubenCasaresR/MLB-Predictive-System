"""Tests para api/routers/risk.py (125 líneas, 5 endpoints)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.app import app


def _create_tables(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                role TEXT DEFAULT 'user'
            )
        """)
        )


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


def _auth_header(client=None):
    if client is None:
        client = TestClient(app)
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        data={
            "username": "testuser",
            "password": "testpass123",
        },
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


client = TestClient(app)


MOCK_BANKROLL_STATUS = {
    "initial": 10000.0,
    "current": 12500.0,
    "peak": 13000.0,
    "drawdown": 3.85,
    "total_wagered": 5000.0,
    "total_profit": 2500.0,
    "roi": 50.0,
    "total_return": 150.0,
    "sharpe_ratio": 1.5,
    "bet_count": 42,
}

MOCK_EXPOSURE_CHECK = {
    "approved": True,
    "violations": [],
    "current_bankroll": 10000.0,
    "stake": 100.0,
    "stake_pct": 1.0,
}


# ============================================================================
# GET /api/v1/risk/bankroll
# ============================================================================


class TestGetBankroll:
    def test_requires_auth(self):
        resp = client.get("/api/v1/risk/bankroll")
        assert resp.status_code == 401

    def test_returns_bankroll_status(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.status.return_value = MOCK_BANKROLL_STATUS
            resp = client.get("/api/v1/risk/bankroll", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == 12500.0
        assert data["initial"] == 10000.0
        assert data["peak"] == 13000.0
        assert data["bet_count"] == 42
        assert "updated_at" in data

    def test_passes_correct_methods(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.status.return_value = MOCK_BANKROLL_STATUS
            client.get("/api/v1/risk/bankroll", headers=headers)
        mock_cls.assert_called_once_with()


# ============================================================================
# POST /api/v1/risk/bankroll/update
# ============================================================================


class TestUpdateBankroll:
    def test_requires_auth(self):
        resp = client.post("/api/v1/risk/bankroll/update?new_amount=15000")
        assert resp.status_code == 401

    def test_updates_bankroll(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.current = 10000.0
            resp = client.post(
                "/api/v1/risk/bankroll/update?new_amount=15000",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["previous"] == 10000.0
        assert data["current"] == 15000.0
        mock_cls.assert_called_once()

    def test_rejects_non_positive_amount(self):
        headers = _auth_header()
        resp = client.post(
            "/api/v1/risk/bankroll/update?new_amount=0",
            headers=headers,
        )
        assert resp.status_code == 400

    def test_rejects_negative_amount(self):
        headers = _auth_header()
        resp = client.post(
            "/api/v1/risk/bankroll/update?new_amount=-500",
            headers=headers,
        )
        assert resp.status_code == 400

    def test_saves_state(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.current = 10000.0
            client.post(
                "/api/v1/risk/bankroll/update?new_amount=20000",
                headers=headers,
            )
            mock_cls.return_value.save_state.assert_called_once()


# ============================================================================
# POST /api/v1/risk/exposure/check
# ============================================================================


class TestCheckExposure:
    def test_requires_auth(self):
        resp = client.post("/api/v1/risk/exposure/check?stake=100")
        assert resp.status_code == 401

    def test_returns_exposure_response(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.check_exposure.return_value = MOCK_EXPOSURE_CHECK
            resp = client.post(
                "/api/v1/risk/exposure/check?stake=100",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is True
        assert data["current_bankroll"] == 10000.0

    def test_reports_violations(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.check_exposure.return_value = {
                "approved": False,
                "violations": ["Stake exceeds max per bet"],
                "current_bankroll": 10000.0,
                "stake": 5000.0,
                "stake_pct": 50.0,
            }
            resp = client.post(
                "/api/v1/risk/exposure/check?stake=5000",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is False
        assert "Stake exceeds max per bet" in data["violations"]

    def test_passes_stake_to_manager(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.check_exposure.return_value = MOCK_EXPOSURE_CHECK
            client.post(
                "/api/v1/risk/exposure/check?stake=250",
                headers=headers,
            )
        mock_cls.return_value.check_exposure.assert_called_once_with(stake=250.0)


# ============================================================================
# GET /api/v1/risk/limits
# ============================================================================


class TestGetRiskLimits:
    def test_requires_auth(self):
        resp = client.get("/api/v1/risk/limits")
        assert resp.status_code == 401

    def test_returns_limits(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.ExposureLimit") as mock_cls:
            mock_limits = MagicMock()
            mock_limits.max_per_bet = 500
            mock_limits.max_per_day = 2000
            mock_limits.max_per_week = 5000
            mock_limits.max_drawdown = 0.1
            mock_limits.max_concurrent_bets = 5
            mock_cls.return_value = mock_limits

            resp = client.get("/api/v1/risk/limits", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["max_per_bet"] == 500
        assert data["max_per_day"] == 2000
        assert data["max_concurrent_bets"] == 5


# ============================================================================
# GET /api/v1/risk/exposure/summary
# ============================================================================


class TestGetExposureSummary:
    def test_requires_auth(self):
        resp = client.get("/api/v1/risk/exposure/summary")
        assert resp.status_code == 401

    def test_returns_exposure_summary(self):
        headers = _auth_header()
        mock_cursor = MagicMock()
        mock_cursor.scalar.return_value = 500.0
        mock_cursor.fetchall.return_value = [
            ["DraftKings", 300.0],
            ["FanDuel", 200.0],
        ]

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("api.database.get_engine", return_value=mock_engine):
            resp = client.get("/api/v1/risk/exposure/summary", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_exposed"] == 500.0
        assert data["by_sportsbook"]["DraftKings"] == 300.0
        assert data["by_sportsbook"]["FanDuel"] == 200.0

    def test_empty_exposure(self):
        headers = _auth_header()
        mock_cursor = MagicMock()
        mock_cursor.scalar.return_value = 0
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = mock_cursor
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("api.database.get_engine", return_value=mock_engine):
            resp = client.get("/api/v1/risk/exposure/summary", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_exposed"] == 0.0
        assert data["by_sportsbook"] == {}
        assert data["by_game"] == {}
