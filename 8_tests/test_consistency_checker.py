"""Tests para ConsistencyChecker (consistencia de datos ETL)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tempfile

from sqlalchemy import create_engine, text

from etl.validators.consistency_check import ConsistencyChecker


def _create_checker():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE games (
                game_id TEXT PRIMARY KEY,
                game_date TEXT NOT NULL,
                home_team_id TEXT,
                away_team_id TEXT,
                status TEXT,
                home_score INTEGER DEFAULT 0,
                away_score INTEGER DEFAULT 0
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE at_bats (
                ab_id INTEGER PRIMARY KEY,
                game_id TEXT NOT NULL,
                inning INTEGER NOT NULL,
                half_inning TEXT NOT NULL,
                batter_id INTEGER,
                pitcher_id INTEGER,
                home_score_after INTEGER DEFAULT 0,
                away_score_after INTEGER DEFAULT 0,
                events TEXT,
                outs_before INTEGER DEFAULT 0
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE lineups (
                lineup_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                batting_order INTEGER NOT NULL,
                position TEXT NOT NULL
            )
        """)
        )
    return ConsistencyChecker(db_url), engine


# ============================================================================
# Tests: check_game_score_consistency
# ============================================================================


class TestCheckGameScoreConsistency:
    def test_scores_match(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_score, away_score)
                VALUES ('G1', '2026-05-20', 5, 3)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id,
                                     home_score_after, away_score_after)
                VALUES (1, 'G1', 9, 'B', 100, 5, 3)
            """)
            )
        issues = checker.check_game_score_consistency("G1")
        assert issues == []

    def test_home_score_mismatch(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_score, away_score)
                VALUES ('G1', '2026-05-20', 5, 3)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id,
                                     home_score_after, away_score_after)
                VALUES (1, 'G1', 9, 'B', 100, 4, 3)
            """)
            )
        issues = checker.check_game_score_consistency("G1")
        assert len(issues) == 1
        assert "Home score mismatch" in issues[0]

    def test_away_score_mismatch(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_score, away_score)
                VALUES ('G1', '2026-05-20', 5, 3)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id,
                                     home_score_after, away_score_after)
                VALUES (1, 'G1', 9, 'B', 100, 5, 4)
            """)
            )
        issues = checker.check_game_score_consistency("G1")
        assert len(issues) == 1
        assert "Away score mismatch" in issues[0]

    def test_no_at_bats(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_score, away_score)
                VALUES ('G1', '2026-05-20', 0, 0)
            """)
            )
        issues = checker.check_game_score_consistency("G1")
        assert issues == []

    def test_game_not_found(self):
        checker, _ = _create_checker()
        issues = checker.check_game_score_consistency("NONEXISTENT")
        assert issues == []


# ============================================================================
# Tests: check_batter_sequence
# ============================================================================


class TestCheckBatterSequence:
    def test_normal_inning(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date)
                VALUES ('G1', '2026-05-20')
            """)
            )
            for i in range(10):
                conn.execute(
                    text("""
                    INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id)
                    VALUES (:aid, :gid, 1, 'T', :bid)
                """),
                    {"aid": i, "gid": "G1", "bid": i + 1},
                )
        issues = checker.check_batter_sequence("G1")
        assert issues == []

    def test_excessive_at_bats(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date)
                VALUES ('G1', '2026-05-20')
            """)
            )
            for i in range(14):
                conn.execute(
                    text("""
                    INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id)
                    VALUES (:aid, :gid, 1, 'T', :bid)
                """),
                    {"aid": i, "gid": "G1", "bid": i + 1},
                )
        issues = checker.check_batter_sequence("G1")
        assert len(issues) == 1
        assert "Inning" in issues[0]
        assert "14" in issues[0]

    def test_multiple_innings(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date)
                VALUES ('G1', '2026-05-20')
            """)
            )
            aid = 1
            for inning in range(1, 4):
                for half in ("T", "B"):
                    for i in range(6):
                        conn.execute(
                            text("""
                            INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id)
                            VALUES (:aid, :gid, :inn, :half, :bid)
                        """),
                            {"aid": aid, "gid": "G1", "inn": inning, "half": half, "bid": i + 1},
                        )
                        aid += 1
        issues = checker.check_batter_sequence("G1")
        assert issues == []

    def test_no_at_bats(self):
        checker, _ = _create_checker()
        issues = checker.check_batter_sequence("NONEXISTENT")
        assert issues == []


# ============================================================================
# Tests: check_lineup_coherence
# ============================================================================


class TestCheckLineupCoherence:
    def test_valid_lineup(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date)
                VALUES ('G1', '2026-05-20')
            """)
            )
            for order in range(1, 10):
                conn.execute(
                    text("""
                    INSERT INTO lineups (game_id, team_id, player_id, batting_order, position)
                    VALUES ('G1', 'NYY', :pid, :order, :pos)
                """),
                    {"pid": 100 + order, "order": order, "pos": "DH" if order == 9 else str(order)},
                )
        issues = checker.check_lineup_coherence("G1")
        assert issues == []

    def test_wrong_number_of_players(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date)
                VALUES ('G1', '2026-05-20')
            """)
            )
            for order in range(1, 4):
                conn.execute(
                    text("""
                    INSERT INTO lineups (game_id, team_id, player_id, batting_order, position)
                    VALUES ('G1', 'NYY', :pid, :order, :pos)
                """),
                    {"pid": 100 + order, "order": order, "pos": "OF"},
                )
        issues = checker.check_lineup_coherence("G1")
        assert len(issues) >= 1
        assert any("3" in i for i in issues)

    def test_batting_order_not_1_to_9(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date)
                VALUES ('G1', '2026-05-20')
            """)
            )
            for order in (1, 2, 3, 4, 5, 6, 7, 8, 10):  # 10 instead of 9
                conn.execute(
                    text("""
                    INSERT INTO lineups (game_id, team_id, player_id, batting_order, position)
                    VALUES ('G1', 'NYY', :pid, :order, :pos)
                """),
                    {"pid": 100 + order, "order": order, "pos": "IF"},
                )
        issues = checker.check_lineup_coherence("G1")
        assert len(issues) >= 1
        assert any("1-9" in i for i in issues)

    def test_no_lineups(self):
        checker, _ = _create_checker()
        issues = checker.check_lineup_coherence("NONEXISTENT")
        assert len(issues) == 1
        assert "No lineups" in issues[0]

    def test_two_teams_valid(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date)
                VALUES ('G1', '2026-05-20')
            """)
            )
            for team in ("NYY", "BOS"):
                for order in range(1, 10):
                    conn.execute(
                        text("""
                        INSERT INTO lineups (game_id, team_id, player_id, batting_order, position)
                        VALUES ('G1', :team, :pid, :order, :pos)
                    """),
                        {"team": team, "pid": 100 + order, "order": order, "pos": "IF"},
                    )
        issues = checker.check_lineup_coherence("G1")
        assert issues == []


# ============================================================================
# Tests: check_all (integración)
# ============================================================================


class TestCheckAll:
    def test_returns_correct_structure(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_score, away_score)
                VALUES ('G1', '2026-05-20', 2, 1)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id,
                                     home_score_after, away_score_after)
                VALUES (1, 'G1', 9, 'B', 100, 2, 1)
            """)
            )
        result = checker.check_all("G1")
        assert result["game_id"] == "G1"
        assert "issues_count" in result
        assert "passed" in result
        assert "issues" in result
        assert "details" in result
        assert isinstance(result["details"], dict)
        assert "score" in result["details"]
        assert "batter_sequence" in result["details"]
        assert "lineup" in result["details"]

    def test_passed_when_no_issues(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_score, away_score)
                VALUES ('G1', '2026-05-20', 2, 1)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id,
                                     home_score_after, away_score_after)
                VALUES (1, 'G1', 9, 'B', 100, 2, 1)
            """)
            )
            half = 1
            for team in ("NYY", "BOS"):
                for order in range(1, 10):
                    conn.execute(
                        text("""
                        INSERT INTO lineups (game_id, team_id, player_id, batting_order, position)
                        VALUES ('G1', :team, :pid, :order, :pos)
                    """),
                        {"team": team, "pid": 100 + half + order, "order": order, "pos": "IF"},
                    )
                half += 100
        result = checker.check_all("G1")
        assert result["passed"] is True

    def test_failed_when_issues(self):
        checker, engine = _create_checker()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_score, away_score)
                VALUES ('G1', '2026-05-20', 5, 3)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO at_bats (ab_id, game_id, inning, half_inning, batter_id,
                                     home_score_after, away_score_after)
                VALUES (1, 'G1', 9, 'B', 100, 2, 1)
            """)
            )
        result = checker.check_all("G1")
        assert result["passed"] is False
        assert result["issues_count"] > 0
