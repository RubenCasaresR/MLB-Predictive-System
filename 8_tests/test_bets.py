"""Tests para api/routers/bets.py (7 endpoints, 256 líneas)."""

import os
import sys
from unittest.mock import ANY, AsyncMock, MagicMock, patch

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
        conn.execute(
            text("""
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
        """)
        )
        conn.execute(
            text("""
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
                placed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS simulation_results (
                game_id TEXT PRIMARY KEY,
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
        """)
        )


def _seed_data(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO approved_bets
                (game_id, team, opponent, sportsbook, market_type,
                 odds, edge, kelly_fraction, recommended_stake, confidence)
            VALUES
                ('GAME-001', 'NYY', 'BOS', 'DraftKings', 'MONEYLINE',
                 -110, 0.05, 0.02, 200.0, 0.8)
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO bet_history
                (bet_id, game_id, team, market_type, odds, stake, won, profit_loss, kelly_pct, edge)
            VALUES
                (1, 'GAME-001', 'NYY', 'MONEYLINE', -110, 100.0, 1, 90.91, 0.02, 0.05)
        """)
        )
        # Use exec_driver_sql on the Connection object (not raw DBAPI)
        # to avoid SQLAlchemy text() parsing JSON colons (:) as bind params
        conn.exec_driver_sql(
            "INSERT OR IGNORE INTO simulation_results "
            "(game_id, home_win_prob, away_win_prob, mean_home_runs, mean_away_runs, "
            "std_home_runs, std_away_runs, extra_innings_prob, walkoff_prob, "
            "run_distribution, n_iterations, computed_at) "
            "VALUES ('GAME-001', 0.58, 0.42, 4.5, 3.8, 2.1, 1.9, 0.08, 0.03, "
            "'{\"0\":0.1,\"1\":0.2}', 10000, '2026-05-20T12:00:00')"
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


def _auth_header(client=None):
    """Register a test user and return Authorization header."""
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


# ============================================================================
# POST /api/v1/bets/ev
# ============================================================================


class TestCalculateEV:
    def test_requires_auth(self):
        resp = client.post(
            "/api/v1/bets/ev",
            json={
                "game_id": "G1",
                "home_odds": -110,
                "away_odds": -110,
                "home_real_prob": 0.55,
                "away_real_prob": 0.45,
            },
        )
        assert resp.status_code == 401

    def test_returns_bets_with_token(self):
        headers = _auth_header()
        mock_bet = MagicMock()
        mock_bet.team = "NYY"
        mock_bet.odds = -110
        mock_bet.edge = 0.05
        mock_bet.kelly_fraction = 0.02
        mock_bet.recommended_stake = 200.0
        mock_bet.implied_prob = 0.524
        mock_bet.real_prob = 0.55

        with patch("risk.ev_calculator.EVCalculator") as mock_cls:
            mock_cls.return_value.evaluate_moneyline.return_value = [mock_bet]
            resp = client.post(
                "/api/v1/bets/ev",
                json={
                    "game_id": "G1",
                    "home_odds": -110,
                    "away_odds": -110,
                    "home_real_prob": 0.55,
                    "away_real_prob": 0.45,
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "bets" in data
        assert len(data["bets"]) == 1
        assert data["bets"][0]["team"] == "NYY"
        assert data["bets"][0]["edge"] == 0.05

    def test_calculator_receives_correct_args(self):
        headers = _auth_header()
        with patch("risk.ev_calculator.EVCalculator") as mock_cls:
            mock_cls.return_value.evaluate_moneyline.return_value = []
            client.post(
                "/api/v1/bets/ev",
                json={
                    "game_id": "G-EV",
                    "home_odds": -130,
                    "away_odds": +110,
                    "home_real_prob": 0.60,
                    "away_real_prob": 0.40,
                },
                headers=headers,
            )

        mock_cls.return_value.evaluate_moneyline.assert_called_once_with(
            game_id="G-EV",
            home_team="HOME",
            away_team="AWAY",
            home_odds=-130,
            away_odds=+110,
            home_real_prob=0.60,
            away_real_prob=0.40,
        )


# ============================================================================
# POST /api/v1/bets/simulate
# Nota: usa 'from services.simulation_service import SimulationService'
# que es un bug (services/ no existe). El test usa create=True en patch.
# ============================================================================

MOCK_SIM_RESPONSE = {
    "game_id": "G1",
    "home_win_prob": 0.58,
    "away_win_prob": 0.42,
    "mean_home_runs": 4.5,
    "mean_away_runs": 3.8,
    "std_home_runs": 2.1,
    "std_away_runs": 1.9,
    "extra_innings_prob": 0.08,
    "walkoff_prob": 0.03,
    "n_iterations": 10000,
    "home_run_distribution": {"0": 0.1},
    "away_run_distribution": {"0": 0.15},
    "computed_at": "2026-05-20T12:00:00",
}


class TestRunSimulation:
    def test_requires_auth(self):
        resp = client.post(
            "/api/v1/bets/simulate",
            json={
                "game_id": "G1",
                "home_team_id": "NYY",
                "away_team_id": "BOS",
                "home_pitcher_id": 1,
                "away_pitcher_id": 2,
            },
        )
        assert resp.status_code == 401

    def test_returns_simulation_response(self):
        headers = _auth_header()
        # Import path is now api.services.simulation_service (bug fixed)
        with patch("api.services.simulation_service.SimulationService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.run_simulation = AsyncMock(return_value=MagicMock(**MOCK_SIM_RESPONSE))

            resp = client.post(
                "/api/v1/bets/simulate",
                json={
                    "game_id": "G1",
                    "home_team_id": "NYY",
                    "away_team_id": "BOS",
                    "home_pitcher_id": 1,
                    "away_pitcher_id": 2,
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == "G1"
        assert data["home_win_prob"] == 0.58

    def test_passes_request_to_service(self):
        headers = _auth_header()
        with patch("api.services.simulation_service.SimulationService") as mock_cls:
            mock_svc = mock_cls.return_value
            mock_svc.run_simulation = AsyncMock(return_value=MagicMock(**MOCK_SIM_RESPONSE))

            client.post(
                "/api/v1/bets/simulate",
                json={
                    "game_id": "G1",
                    "home_team_id": "NYY",
                    "away_team_id": "BOS",
                    "home_pitcher_id": 1,
                    "away_pitcher_id": 2,
                },
                headers=headers,
            )

            args, _ = mock_svc.run_simulation.call_args
            assert args[0].game_id == "G1"


# ============================================================================
# POST /api/v1/bets/props/evaluate
# ============================================================================


class TestEvaluateProp:
    def test_requires_auth(self):
        resp = client.post(
            "/api/v1/bets/props/evaluate",
            json={
                "player_id": 1,
                "prop_type": "HR",
                "line_value": 1.5,
                "over_odds": +200,
                "under_odds": -250,
                "features": {"exit_velo": 95.0},
            },
        )
        assert resp.status_code == 401

    def test_returns_prop_response(self):
        headers = _auth_header()
        mock_result = MagicMock()
        mock_result.recommendation = "over"
        mock_result.player_name = "Player_1"
        mock_result.prop_type = "HR"
        mock_result.line_value = 1.5
        mock_result.predicted_mean = 0.8
        mock_result.prob_over = 0.35
        mock_result.prob_under = 0.65
        mock_result.ev_over = 0.05
        mock_result.ev_under = -0.15
        mock_result.kelly_fraction = 0.01

        with patch("prediction.poisson_props.PoissonPropsEngine") as mock_cls:
            mock_cls.return_value.evaluate_bet.return_value = mock_result
            resp = client.post(
                "/api/v1/bets/props/evaluate",
                json={
                    "player_id": 1,
                    "prop_type": "HR",
                    "line_value": 1.5,
                    "over_odds": +200,
                    "under_odds": -250,
                    "features": {"exit_velo": 95.0},
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] == "over"
        assert data["prop_type"] == "HR"

    def test_returns_204_when_no_bet(self):
        headers = _auth_header()
        mock_result = MagicMock()
        mock_result.recommendation = "no_bet"

        with patch("prediction.poisson_props.PoissonPropsEngine") as mock_cls:
            mock_cls.return_value.evaluate_bet.return_value = mock_result
            resp = client.post(
                "/api/v1/bets/props/evaluate",
                json={
                    "player_id": 1,
                    "prop_type": "HR",
                    "line_value": 1.5,
                    "over_odds": +200,
                    "under_odds": -250,
                    "features": {"exit_velo": 95.0},
                },
                headers=headers,
            )

        assert resp.status_code == 204

    def test_passes_correct_args_to_engine(self):
        headers = _auth_header()
        with patch("prediction.poisson_props.PoissonPropsEngine") as mock_cls:
            mock_cls.return_value.evaluate_bet.return_value = MagicMock(
                recommendation="over",
                player_name="Player_99",
                prop_type="STRIKEOUTS",
                line_value=5.5,
                predicted_mean=0.0,
                prob_over=0.0,
                prob_under=0.0,
                ev_over=0.0,
                ev_under=0.0,
                kelly_fraction=0.0,
            )
            client.post(
                "/api/v1/bets/props/evaluate",
                json={
                    "player_id": 99,
                    "prop_type": "STRIKEOUTS",
                    "line_value": 5.5,
                    "over_odds": +150,
                    "under_odds": -180,
                    "features": {"k_pct": 0.28},
                },
                headers=headers,
            )

        mock_cls.return_value.evaluate_bet.assert_called_once_with(
            prop_type="STRIKEOUTS",
            player_name="Player_99",
            line_value=5.5,
            over_odds=+150,
            under_odds=-180,
            features={"k_pct": 0.28},
        )


# ============================================================================
# POST /api/v1/bets/slip
# ============================================================================


class TestSubmitBetSlip:
    def test_requires_auth(self):
        resp = client.post(
            "/api/v1/bets/slip",
            json={
                "bets": [
                    {
                        "game_id": "G1",
                        "team": "NYY",
                        "market_type": "MONEYLINE",
                        "odds": -110,
                        "stake": 100.0,
                        "edge": 0.05,
                        "kelly_fraction": 0.02,
                    }
                ]
            },
        )
        assert resp.status_code == 401

    def test_approved_when_no_violations(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.check_exposure.return_value = {
                "approved": True,
                "violations": [],
                "current_bankroll": 10000,
                "stake": 100,
                "stake_pct": 0.01,
            }
            resp = client.post(
                "/api/v1/bets/slip",
                json={
                    "bets": [
                        {
                            "game_id": "G1",
                            "team": "NYY",
                            "market_type": "MONEYLINE",
                            "odds": -110,
                            "stake": 100.0,
                            "edge": 0.05,
                            "kelly_fraction": 0.02,
                        }
                    ]
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is True
        assert data["total_stake"] == 100.0

    def test_rejected_with_violations(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.check_exposure.return_value = {
                "approved": False,
                "violations": ["Exceeds max stake per bet"],
                "current_bankroll": 10000,
                "stake": 600,
                "stake_pct": 0.06,
            }
            resp = client.post(
                "/api/v1/bets/slip",
                json={
                    "bets": [
                        {
                            "game_id": "G1",
                            "team": "NYY",
                            "market_type": "MONEYLINE",
                            "odds": -110,
                            "stake": 600.0,
                            "edge": 0.05,
                            "kelly_fraction": 0.02,
                        }
                    ]
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is False
        assert "Exceeds max stake per bet" in data["violations"]

    def test_multiple_bets_aggregate_stake(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.check_exposure.return_value = {
                "approved": True,
                "violations": [],
                "current_bankroll": 10000,
                "stake": 150,
                "stake_pct": 0.015,
            }
            resp = client.post(
                "/api/v1/bets/slip",
                json={
                    "bets": [
                        {
                            "game_id": "G1",
                            "team": "NYY",
                            "market_type": "MONEYLINE",
                            "odds": -110,
                            "stake": 100.0,
                            "edge": 0.05,
                            "kelly_fraction": 0.02,
                        },
                        {
                            "game_id": "G2",
                            "team": "LAD",
                            "market_type": "MONEYLINE",
                            "odds": +150,
                            "stake": 50.0,
                            "edge": 0.03,
                            "kelly_fraction": 0.01,
                        },
                    ]
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_stake"] == 150.0

    def test_empty_bets_list_returns_zero_stake(self):
        headers = _auth_header()
        with patch("risk.bankroll_manager.PersistentBankrollManager") as mock_cls:
            mock_cls.return_value.check_exposure.return_value = {
                "approved": True,
                "violations": [],
                "current_bankroll": 10000,
                "stake": 0,
                "stake_pct": 0,
            }
            resp = client.post("/api/v1/bets/slip", json={"bets": []}, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_stake"] == 0.0


# ============================================================================
# GET /api/v1/bets/simulate/{game_id}
# ============================================================================


class TestGetSimulation:
    def test_requires_auth(self):
        resp = client.get("/api/v1/bets/simulate/GAME-001")
        assert resp.status_code == 401

    def test_returns_simulation_when_found(self):
        headers = _auth_header()
        # run_distribution is now parsed with json.loads (bug fixed),
        # so mock row returns a JSON string as SQLite would
        mock_row = [
            0.58,
            0.42,
            4.5,
            3.8,
            2.1,
            1.9,
            0.08,
            0.03,
            '{"0":0.1,"1":0.2}',  # run_distribution as JSON string
            10000,
            "2026-05-20T12:00:00",
        ]
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = mock_row
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value.execute.return_value = mock_cursor
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("api.database.get_engine", return_value=mock_engine):
            resp = client.get("/api/v1/bets/simulate/GAME-001", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == "GAME-001"
        assert data["home_win_prob"] == 0.58
        assert data["n_iterations"] == 10000

    def test_returns_404_when_not_found(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/simulate/NONEXISTENT", headers=headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ============================================================================
# GET /api/v1/bets/approved
# ============================================================================


class TestGetApprovedBets:
    def test_requires_auth(self):
        resp = client.get("/api/v1/bets/approved")
        assert resp.status_code == 401

    def test_returns_approved_bets(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/approved", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["game_id"] == "GAME-001"
        assert data[0]["edge"] == 0.05

    def test_filters_by_min_edge(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/approved?min_edge=0.10", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # All results should have edge >= 0.10 (seed data has 0.05)
        assert len(data) == 0

    def test_respects_limit(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/approved?limit=1", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 1

    def test_returns_empty_when_no_pending(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/approved?min_edge=0.99", headers=headers)
        assert resp.json() == []


# ============================================================================
# GET /api/v1/bets/history
# ============================================================================


class TestGetBetHistory:
    def test_requires_auth(self):
        resp = client.get("/api/v1/bets/history")
        assert resp.status_code == 401

    def test_returns_history(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/history", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["bet_id"] == 1
        assert data[0]["team"] == "NYY"

    def test_respects_limit(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/history?limit=1", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 1

    def test_returns_expected_fields(self):
        headers = _auth_header()
        resp = client.get("/api/v1/bets/history", headers=headers)
        data = resp.json()
        for r in data:
            assert "bet_id" in r
            assert "game_id" in r
            assert "team" in r
            assert "odds" in r
            assert "stake" in r
            assert "won" in r
            assert "profit_loss" in r
