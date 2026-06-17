"""Tests para api/routers/stats.py (7 endpoints GET)."""

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
            CREATE TABLE IF NOT EXISTS players (
                player_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                team_id TEXT,
                position TEXT,
                bats TEXT,
                throws TEXT
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS player_rolling_stats (
                player_id INTEGER,
                as_of_date TEXT,
                woba_30d REAL,
                fip_30d REAL,
                xera_30d REAL,
                avg_velo_30d REAL,
                whiff_pct_30d REAL,
                fatigue_score REAL,
                PRIMARY KEY (player_id, as_of_date)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                game_date TEXT NOT NULL,
                home_team_id TEXT,
                away_team_id TEXT,
                home_probable_pitcher INTEGER,
                away_probable_pitcher INTEGER,
                status TEXT DEFAULT 'SCHEDULED',
                start_time_et TEXT
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS teams (
                team_id TEXT PRIMARY KEY,
                name TEXT,
                league TEXT,
                division TEXT,
                ballpark TEXT
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS at_bats (
                ab_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pitcher_id INTEGER
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS pitches (
                p_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ab_id INTEGER,
                release_speed REAL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS stadiums (
                stadium_id INTEGER PRIMARY KEY,
                name TEXT,
                roof_type VARCHAR(10) DEFAULT 'open'
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS market_lines (
                game_id TEXT,
                home_moneyline_close INTEGER,
                away_moneyline_close INTEGER,
                total_close REAL,
                sharp_money_flag INTEGER,
                rlm_flag INTEGER,
                recorded_at TEXT
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS simulation_results (
                game_id TEXT PRIMARY KEY,
                home_win_prob REAL,
                away_win_prob REAL
            )
        """)
        )


def _seed_data(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO players (player_id, full_name, team_id, position, bats, throws)
            VALUES (1, 'Aaron Judge', 'NYY', 'CF', 'R', 'R')
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO players (player_id, full_name, team_id, position, bats, throws)
            VALUES (2, 'Mookie Betts', 'LAD', 'RF', 'R', 'R')
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO player_rolling_stats
                (player_id, as_of_date, woba_30d, fip_30d, xera_30d, avg_velo_30d, whiff_pct_30d, fatigue_score)
            VALUES (1, '2026-05-20', 0.412, 3.10, 4.20, 95.5, 12.5, 0.15)
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO games (game_id, game_date, home_team_id, away_team_id,
                                         home_probable_pitcher, away_probable_pitcher,
                                         status, start_time_et)
            VALUES ('2026-05-20-NYY-BOS', '2026-05-20', 'NYY', 'BOS',
                    1, 2, 'SCHEDULED', '19:05')
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO teams (team_id, name, league, division, ballpark)
            VALUES ('NYY', 'New York Yankees', 'AL', 'East', 'Yankee Stadium')
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO teams (team_id, name, league, division, ballpark)
            VALUES ('LAD', 'Los Angeles Dodgers', 'NL', 'West', 'Dodger Stadium')
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO at_bats (ab_id, pitcher_id) VALUES (1, 1)
        """)
        )
        conn.execute(
            text("""
            INSERT OR IGNORE INTO pitches (p_id, ab_id, release_speed) VALUES (1, 1, 95.0)
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


client = TestClient(app)


# ============================================================================
# Helpers for mocking engine (PostgreSQL-specific SQL)
# ============================================================================


def _make_mock_engine(fetchone_result=None, fetchall_result=None):
    """Create a mock engine that returns the given fetchone/fetchall results."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_main_result = MagicMock()
    if fetchall_result is not None:
        mock_main_result.fetchall.return_value = fetchall_result
    mock_main_result.fetchone.return_value = fetchone_result
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = None
    mock_conn.__aenter__.return_value = mock_conn
    mock_conn.__aexit__.return_value = None

    # Default execute returns an awaitable
    mock_conn.execute = AsyncMock(return_value=mock_main_result)
    mock_engine.connect.return_value = mock_conn
    return mock_engine


def _make_mock_engine_with_extra(
    fetchone_result=None,
    fetchall_result=None,
    pitcher_home_result=None,
    pitcher_away_result=None,
    team_home_result=None,
    team_away_result=None,
):
    """Create a mock engine that returns different results per query text pattern."""
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = None
    mock_conn.__aenter__.return_value = mock_conn
    mock_conn.__aexit__.return_value = None
    mock_engine.connect.return_value = mock_conn

    def _execute_side_effect(*exec_args, **exec_kwargs):
        sql = exec_args[0] if exec_args else None
        params = exec_args[1] if len(exec_args) > 1 else (exec_kwargs or {})
        sql_str = str(sql) if hasattr(sql, "__str__") else str(sql)
        mock_res = MagicMock()
        # Match pitcher query by looking at SQL text
        if "players p" in sql_str and "player_rolling_stats" in sql_str:
            pid = params.get("pid", 0) if isinstance(params, dict) else 0
            if pid == 1:
                mock_res.fetchone.return_value = pitcher_home_result or (
                    "Gerrit Cole",
                    "R",
                    2.95,
                    10.2,
                    5.1,
                    1.2,
                    96.8,
                    30.5,
                    0.72,
                )
            elif pid == 2:
                mock_res.fetchone.return_value = pitcher_away_result or (
                    "Clayton Kershaw",
                    "L",
                    3.45,
                    8.2,
                    7.3,
                    1.1,
                    91.2,
                    25.0,
                    0.85,
                )
            else:
                mock_res.fetchone.return_value = None
        elif "team_rolling_stats" in sql_str:
            tid = params.get("tid", "") if isinstance(params, dict) else ""
            if tid == "NYY" and team_home_result:
                mock_res.fetchone.return_value = team_home_result
            elif tid == "BOS" and team_away_result:
                mock_res.fetchone.return_value = team_away_result
            elif tid == "LAD" and team_home_result:
                mock_res.fetchone.return_value = team_home_result
            elif tid == "SFG" and team_away_result:
                mock_res.fetchone.return_value = team_away_result
            else:
                mock_res.fetchone.return_value = None
        else:
            if fetchall_result is not None:
                mock_res.fetchall.return_value = fetchall_result
            mock_res.fetchone.return_value = fetchone_result
        return mock_res

    mock_conn.execute = AsyncMock(side_effect=_execute_side_effect)
    return mock_engine


# ============================================================================
# GET /api/v1/stats/players/{player_id}
# ============================================================================


class TestGetPlayerStats:
    def test_returns_player_stats_with_rolling(self):
        resp = client.get("/api/v1/stats/players/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_id"] == 1
        assert data["full_name"] == "Aaron Judge"
        assert data["team_id"] == "NYY"
        assert data["position"] == "CF"
        assert data["bats"] == "R"
        assert data["throws"] == "R"
        assert data["woba_30d"] == 0.412
        assert data["fip_30d"] == 3.1
        assert data["xera_30d"] == 4.2
        assert data["avg_velo_30d"] == 95.5
        assert data["whiff_pct_30d"] == 12.5
        assert data["fatigue_score"] == 0.15

    def test_returns_404_when_player_not_found(self):
        resp = client.get("/api/v1/stats/players/999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Player not found"

    def test_returns_none_stats_when_no_rolling_data(self):
        resp = client.get("/api/v1/stats/players/2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_id"] == 2
        assert data["full_name"] == "Mookie Betts"
        assert data["woba_30d"] is None
        assert data["fip_30d"] is None
        assert data["fatigue_score"] is None


# ============================================================================
# GET /api/v1/stats/players
# ============================================================================


class TestListPlayers:
    def test_returns_all_players(self):
        resp = client.get("/api/v1/stats/players")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {p["full_name"] for p in data}
        assert "Aaron Judge" in names
        assert "Mookie Betts" in names

    def test_filters_by_team_id(self):
        resp = client.get("/api/v1/stats/players?team_id=NYY")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["full_name"] == "Aaron Judge"

    def test_filters_by_position(self):
        resp = client.get("/api/v1/stats/players?position=CF")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["full_name"] == "Aaron Judge"

    def test_returns_empty_when_no_match(self):
        resp = client.get("/api/v1/stats/players?team_id=FAKE")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_combines_filters(self):
        resp = client.get("/api/v1/stats/players?team_id=NYY&position=CF")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["player_id"] == 1

    def test_all_players_have_required_fields(self):
        resp = client.get("/api/v1/stats/players")
        data = resp.json()
        for p in data:
            assert "player_id" in p
            assert "full_name" in p
            assert "team_id" in p


# ============================================================================
# GET /api/v1/stats/preview/{game_id}
# Uses LEFT JOIN LATERAL (PostgreSQL) — mock engine
# ============================================================================


class TestGetGamePreview:
    GAME_PREVIEW_ROW = (
        "2026-05-20",  # game_date
        "NYY",  # home_team_id
        "BOS",  # away_team_id
        1,  # home_probable_pitcher
        2,  # away_probable_pitcher
        "SCHEDULED",  # status
        "19:05",  # start_time_et
        -120,  # home_moneyline_close
        100,  # away_moneyline_close
        8.5,  # total_close
        0.58,  # home_win_prob
        0.42,  # away_win_prob
        True,  # sharp_money_flag
        True,  # rlm_flag
    )

    PITCHER_HOME_ROW = (
        "Gerrit Cole",
        "R",
        2.95,
        10.2,
        5.1,
        1.2,
        96.8,
        30.5,
        0.72,
    )
    PITCHER_AWAY_ROW = (
        "Clayton Kershaw",
        "L",
        3.45,
        8.2,
        7.3,
        1.1,
        91.2,
        25.0,
        0.85,
    )
    TEAM_HOME_ROW = (3.42, 3.80, 0.335)
    TEAM_AWAY_ROW = (4.12, 4.05, 0.312)

    def test_returns_game_preview_with_all_data(self):
        engine = _make_mock_engine_with_extra(
            fetchone_result=self.GAME_PREVIEW_ROW,
            pitcher_home_result=self.PITCHER_HOME_ROW,
            pitcher_away_result=self.PITCHER_AWAY_ROW,
            team_home_result=self.TEAM_HOME_ROW,
            team_away_result=self.TEAM_AWAY_ROW,
        )
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/preview/2026-05-20-NYY-BOS")

        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == "2026-05-20-NYY-BOS"
        assert data["game_date"] == "2026-05-20"
        assert data["home_team"] == "NYY"
        assert data["away_team"] == "BOS"
        assert data["status"] == "SCHEDULED"
        assert data["home_moneyline"] == -120
        assert data["away_moneyline"] == 100
        assert data["total"] == 8.5
        assert data["home_win_prob"] == 0.58
        assert data["away_win_prob"] == 0.42
        assert data["sharp_money_flag"] is True
        assert data["rlm_flag"] is True
        # New fields
        assert data["home_pitcher"]["name"] == "Gerrit Cole"
        assert data["home_pitcher"]["fip"] == 2.95
        assert data["away_pitcher"]["name"] == "Clayton Kershaw"
        assert data["home_bullpen"]["era"] == 3.42
        assert data["away_bullpen"]["era"] == 4.12
        assert data["better_team"] == "home"
        assert data["better_pitcher"] == "home"
        assert data["better_bullpen"] == "home"
        assert data["better_offense"] == "home"

    def test_returns_404_when_game_not_found(self):
        engine = _make_mock_engine(fetchone_result=None)
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/preview/NONEXISTENT")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Game not found"

    def test_returns_defaults_when_no_market_data(self):
        minimal_row = (
            "2026-05-21",
            "LAD",
            "SFG",
            None,
            None,
            "SCHEDULED",
            "19:10",
            None,
            None,
            None,
            0.0,
            0.0,
            None,
            None,
        )
        engine = _make_mock_engine_with_extra(
            fetchone_result=minimal_row,
            pitcher_home_result=None,
            pitcher_away_result=None,
            team_home_result=None,
            team_away_result=None,
        )
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/preview/2026-05-21-LAD-SFG")

        assert resp.status_code == 200
        data = resp.json()
        assert data["home_moneyline"] is None
        assert data["away_moneyline"] is None
        assert data["total"] is None
        assert data["sharp_money_flag"] is False
        assert data["rlm_flag"] is False
        assert data["home_win_prob"] == 0.0
        assert data["away_win_prob"] == 0.0

    def test_start_time_returned_when_present(self):
        engine = _make_mock_engine_with_extra(
            fetchone_result=self.GAME_PREVIEW_ROW,
            pitcher_home_result=self.PITCHER_HOME_ROW,
            pitcher_away_result=self.PITCHER_AWAY_ROW,
            team_home_result=self.TEAM_HOME_ROW,
            team_away_result=self.TEAM_AWAY_ROW,
        )
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/preview/2026-05-20-NYY-BOS")

        data = resp.json()
        assert data["start_time"] == "19:05"


# ============================================================================
# GET /api/v1/stats/preview
# Uses LEFT JOIN LATERAL (PostgreSQL) — mock engine
# ============================================================================


class TestListTodaysGames:
    TODAYS_GAMES_ROWS = [
        (
            "2026-05-20-NYY-BOS",
            "2026-05-20",
            "NYY",
            "BOS",
            1,
            2,
            "SCHEDULED",
            "19:05",
            -120,
            100,
            8.5,
            0.58,
            0.42,
            True,
            True,
        ),
    ]

    PITCHER_HOME_ROW = (
        "Gerrit Cole",
        "R",
        2.95,
        10.2,
        5.1,
        1.2,
        96.8,
        30.5,
        0.72,
    )
    PITCHER_AWAY_ROW = (
        "Clayton Kershaw",
        "L",
        3.45,
        8.2,
        7.3,
        1.1,
        91.2,
        25.0,
        0.85,
    )
    TEAM_HOME_ROW = (3.42, 3.80, 0.335)
    TEAM_AWAY_ROW = (4.12, 4.05, 0.312)

    def test_returns_games_for_given_date(self):
        engine = _make_mock_engine_with_extra(
            fetchall_result=self.TODAYS_GAMES_ROWS,
            pitcher_home_result=self.PITCHER_HOME_ROW,
            pitcher_away_result=self.PITCHER_AWAY_ROW,
            team_home_result=self.TEAM_HOME_ROW,
            team_away_result=self.TEAM_AWAY_ROW,
        )
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/preview?date=2026-05-20")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["game_id"] == "2026-05-20-NYY-BOS"
        assert data[0]["home_pitcher"]["name"] == "Gerrit Cole"
        assert data[0]["home_bullpen"]["era"] == 3.42
        assert data[0]["better_team"] == "home"

    def test_returns_empty_when_no_games_that_day(self):
        engine = _make_mock_engine(fetchall_result=[])
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/preview?date=2020-01-01")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_games_have_expected_fields(self):
        engine = _make_mock_engine_with_extra(
            fetchall_result=self.TODAYS_GAMES_ROWS,
            pitcher_home_result=self.PITCHER_HOME_ROW,
            pitcher_away_result=self.PITCHER_AWAY_ROW,
            team_home_result=self.TEAM_HOME_ROW,
            team_away_result=self.TEAM_AWAY_ROW,
        )
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/preview?date=2026-05-20")

        data = resp.json()
        for g in data:
            assert "game_id" in g
            assert "game_date" in g
            assert "home_team" in g
            assert "away_team" in g
            assert "status" in g
            assert "home_pitcher" in g
            assert "away_bullpen" in g
            assert "better_team" in g
            assert "better_pitcher" in g


# ============================================================================
# GET /api/v1/stats/teams/{team_id}
# ============================================================================


class TestGetTeamStats:
    def test_returns_team_info(self):
        resp = client.get("/api/v1/stats/teams/NYY")
        assert resp.status_code == 200
        data = resp.json()
        assert data["team_id"] == "NYY"
        assert data["name"] == "New York Yankees"
        assert data["league"] == "AL"
        assert data["division"] == "East"
        assert data["ballpark"] == "Yankee Stadium"

    def test_returns_404_when_team_not_found(self):
        resp = client.get("/api/v1/stats/teams/FAKE")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Team not found"

    def test_returns_expected_structure(self):
        resp = client.get("/api/v1/stats/teams/LAD")
        data = resp.json()
        assert set(data.keys()) == {"team_id", "name", "league", "division", "ballpark"}


# ============================================================================
# GET /api/v1/stats/pitchers/{pitcher_id}/fatigue
# Uses lazy import: from features.fatigue_detector import FatigueDetector
# ============================================================================


class TestGetPitcherFatigue:
    def test_returns_fatigue_data(self):
        mock_fatigue = MagicMock()
        mock_fatigue.overall_fatigue = 0.35
        mock_fatigue.is_high_risk = False
        mock_fatigue.components = {"velo_drop": 0.1, "rest": 0.0}

        with patch("features.fatigue_detector.FatigueDetector") as mock_cls:
            mock_cls.return_value.evaluate_pitcher_fatigue.return_value = mock_fatigue
            resp = client.get("/api/v1/stats/pitchers/1/fatigue")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pitcher_id"] == 1
        assert data["fatigue_score"] == 0.35
        assert data["is_high_risk"] is False
        assert data["components"] == {"velo_drop": 0.1, "rest": 0.0}

    def test_uses_default_velo_when_no_pitch_data(self):
        mock_fatigue = MagicMock()
        mock_fatigue.overall_fatigue = 0.0
        mock_fatigue.is_high_risk = False
        mock_fatigue.components = {}

        with patch("features.fatigue_detector.FatigueDetector") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.evaluate_pitcher_fatigue.return_value = mock_fatigue
            resp = client.get("/api/v1/stats/pitchers/999/fatigue")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pitcher_id"] == 999

    def test_returns_expected_structure(self):
        mock_fatigue = MagicMock()
        mock_fatigue.overall_fatigue = 0.0
        mock_fatigue.is_high_risk = False
        mock_fatigue.components = {}

        with patch("features.fatigue_detector.FatigueDetector") as mock_cls:
            mock_cls.return_value.evaluate_pitcher_fatigue.return_value = mock_fatigue
            resp = client.get("/api/v1/stats/pitchers/1/fatigue")

        data = resp.json()
        assert set(data.keys()) == {"pitcher_id", "fatigue_score", "is_high_risk", "components"}


# ============================================================================
# GET /api/v1/stats/market/sharp-money
# Uses DISTINCT ON (PostgreSQL) — mock engine
# ============================================================================


class TestGetSharpMoneySignals:
    SHARP_MONEY_ROWS = [
        ("2026-05-20-NYY-BOS", "SHARP_MONEY"),
        ("2026-05-20-NYY-BOS", "RLM"),
    ]

    def test_returns_sharp_money_signals(self):
        engine = _make_mock_engine(fetchall_result=self.SHARP_MONEY_ROWS)
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/market/sharp-money")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(s["game_id"] == "2026-05-20-NYY-BOS" for s in data)

    def test_filters_by_game_id(self):
        engine = _make_mock_engine(fetchall_result=[self.SHARP_MONEY_ROWS[0]])
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/market/sharp-money?game_id=2026-05-20-NYY-BOS")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["game_id"] == "2026-05-20-NYY-BOS"
        assert data[0]["signal_type"] == "SHARP_MONEY"

    def test_returns_empty_when_no_matching_game(self):
        engine = _make_mock_engine(fetchall_result=[])
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/market/sharp-money?game_id=NONEXISTENT")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_signals_have_expected_fields(self):
        engine = _make_mock_engine(fetchall_result=self.SHARP_MONEY_ROWS)
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/market/sharp-money")

        data = resp.json()
        for s in data:
            assert "game_id" in s
            assert "signal_type" in s
            assert "confidence" in s

    def test_includes_min_confidence_in_response(self):
        engine = _make_mock_engine(fetchall_result=self.SHARP_MONEY_ROWS)
        with patch("api.routers.stats.get_async_engine", return_value=engine):
            resp = client.get("/api/v1/stats/market/sharp-money?min_confidence=0.7")

        data = resp.json()
        for s in data:
            assert s["confidence"] == 0.7
