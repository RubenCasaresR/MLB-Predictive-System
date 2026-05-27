"""Tests para FeaturePipeline con SQLite (SQL refactorizado cross-platform)."""

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

from prediction.feature_pipeline import FeaturePipeline

# ============================================================================
# Helpers: crear tablas y seed data
# ============================================================================


def _create_tables(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE games (
                game_id TEXT PRIMARY KEY,
                game_date TEXT NOT NULL,
                home_team_id TEXT,
                away_team_id TEXT,
                status TEXT DEFAULT 'SCHEDULED',
                venue_id INTEGER,
                start_time_et TEXT,
                home_rest_days INTEGER DEFAULT 0,
                away_rest_days INTEGER DEFAULT 0
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE players (
                player_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                team_id TEXT,
                primary_position TEXT,
                bats TEXT CHECK (bats IN ('L', 'R', 'S')),
                throws TEXT CHECK (throws IN ('L', 'R')),
                status TEXT DEFAULT 'ACTIVE'
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE at_bats (
                ab_id INTEGER PRIMARY KEY,
                game_id TEXT NOT NULL REFERENCES games(game_id),
                pitcher_id INTEGER,
                batter_id INTEGER,
                events TEXT,
                inning INTEGER,
                half_inning TEXT,
                launch_angle REAL,
                away_score_before INTEGER,
                away_score_after INTEGER,
                home_score_before INTEGER,
                home_score_after INTEGER
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE pitches (
                pitch_id INTEGER PRIMARY KEY,
                ab_id INTEGER NOT NULL REFERENCES at_bats(ab_id),
                release_speed REAL,
                swing INTEGER DEFAULT 0,
                whiff INTEGER DEFAULT 0
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE player_rolling_stats (
                stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                game_id TEXT NOT NULL,
                as_of_date TEXT,
                woba_7d REAL,
                woba_14d REAL,
                woba_30d REAL,
                fip_30d REAL,
                k_per_9_30d REAL,
                bb_per_9_30d REAL,
                hr_per_9_30d REAL,
                avg_velo_30d REAL,
                whiff_pct_30d REAL,
                days_rested INTEGER,
                pitches_last_7d INTEGER,
                fatigue_score REAL,
                UNIQUE(player_id, game_id)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE batter_rolling_stats (
                stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                game_id TEXT NOT NULL,
                as_of_date TEXT,
                woba_30d REAL,
                k_pct_30d REAL,
                bb_pct_30d REAL,
                hr_per_9_30d REAL,
                groundball_pct_30d REAL,
                flyball_pct_30d REAL,
                UNIQUE(player_id, game_id)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE team_rolling_stats (
                stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                as_of_date TEXT,
                woba_30d REAL,
                bullpen_era_30d REAL,
                bullpen_fip_30d REAL,
                UNIQUE(team_id, game_id)
            )
        """)
        )


def _seed_games(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO games (game_id, game_date, home_team_id, away_team_id, status,
                               home_rest_days, away_rest_days)
            VALUES ('2026-05-19-NYY-BOS', '2026-05-19', 'BOS', 'NYY', 'FINAL', 1, 1)
        """)
        )


def _seed_at_bats(engine):
    with engine.begin() as conn:
        # Pitcher 100: 2 ABs, events: single, home_run
        conn.execute(
            text("""
            INSERT INTO at_bats (ab_id, game_id, pitcher_id, batter_id, events, inning, half_inning)
            VALUES
                (1, '2026-05-19-NYY-BOS', 100, 1, 'Single', 1, 'T'),
                (2, '2026-05-19-NYY-BOS', 100, 2, 'Home Run', 2, 'T'),
                (3, '2026-05-19-NYY-BOS', 200, 3, 'Strikeout', 1, 'B'),
                (4, '2026-05-19-NYY-BOS', 200, 4, 'Walk', 2, 'B')
        """)
        )


def _seed_players(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO players (player_id, full_name, team_id, bats, throws)
            VALUES
                (1, 'Batter_1', 'BOS', 'R', 'R'),
                (2, 'Batter_2', 'BOS', 'L', 'R'),
                (3, 'Batter_3', 'NYY', 'S', 'R'),
                (4, 'Batter_4', 'NYY', 'R', 'R'),
                (100, 'Pitcher_100', 'BOS', 'R', 'R'),
                (200, 'Pitcher_200', 'NYY', 'R', 'R')
        """)
        )


def _seed_pitches(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO pitches (pitch_id, ab_id, release_speed, swing, whiff)
            VALUES
                -- Pitcher 100 (2 ABs x 3 pitches each)
                (1, 1, 95.1, 1, 0),
                (2, 1, 94.5, 1, 0),
                (3, 1, 93.8, 0, 0),
                (4, 2, 96.2, 1, 0),
                (5, 2, 97.0, 1, 1),
                (6, 2, 95.5, 1, 0),
                -- Pitcher 200 (2 ABs x 2 pitches each)
                (7, 3, 91.0, 1, 1),
                (8, 3, 92.2, 1, 0),
                (9, 4, 90.5, 0, 0),
                (10, 4, 89.8, 1, 0)
        """)
        )


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def pipeline():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    _create_tables(engine)
    _seed_games(engine)
    _seed_at_bats(engine)
    _seed_pitches(engine)
    _seed_players(engine)
    fp = FeaturePipeline.__new__(FeaturePipeline)
    fp.db_url = "sqlite://"
    fp.engine = engine
    return fp


@pytest.fixture
def pipeline_with_batter_angles():
    """Same as pipeline but with launch_angle data for batter stats."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    _create_tables(engine)
    _seed_games(engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO at_bats (ab_id, game_id, pitcher_id, batter_id, events, inning, half_inning, launch_angle)
            VALUES
                (1, '2026-05-19-NYY-BOS', 100, 1, 'Single', 1, 'T', 8.0),
                (2, '2026-05-19-NYY-BOS', 100, 2, 'Home Run', 2, 'T', 30.0),
                (3, '2026-05-19-NYY-BOS', 200, 3, 'Strikeout', 1, 'B', NULL),
                (4, '2026-05-19-NYY-BOS', 200, 4, 'Walk', 2, 'B', NULL),
                (5, '2026-05-19-NYY-BOS', 100, 1, 'Field Out', 3, 'T', 5.0),
                (6, '2026-05-19-NYY-BOS', 100, 2, 'Fly Out', 4, 'T', 40.0)
        """)
        )
    _seed_pitches(engine)
    _seed_players(engine)
    fp = FeaturePipeline.__new__(FeaturePipeline)
    fp.db_url = "sqlite://"
    fp.engine = engine
    return fp


# ============================================================================
# Tests
# ============================================================================


class TestComputePlayerRollingStats:
    def test_inserts_stats_for_final_games(self, pipeline):
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT player_id, game_id, woba_30d, fip_30d FROM player_rolling_stats")
            ).fetchall()
        assert len(rows) == 2

    def test_woba_calculation_pitcher_100(self, pipeline):
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_30d FROM player_rolling_stats WHERE player_id = 100")
            ).fetchone()
        # wOBA = AVG(0.90 (single), 2.00 (home_run)) = 1.45
        assert row is not None
        assert round(row[0], 4) == 1.4500

    def test_woba_calculation_pitcher_200(self, pipeline):
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_30d FROM player_rolling_stats WHERE player_id = 200")
            ).fetchone()
        # wOBA = AVG(0 (strikeout), 0.70 (walk)) = 0.35
        assert row is not None
        assert round(row[0], 4) == 0.3500

    def test_avg_velo_pitcher_100(self, pipeline):
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT avg_velo_30d FROM player_rolling_stats WHERE player_id = 100")
            ).fetchone()
        # AVG(95.1, 94.5, 93.8, 96.2, 97.0, 95.5) = 95.35
        assert row is not None
        assert round(row[0], 2) == 95.35

    def test_whiff_pct_pitcher_100(self, pipeline):
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT whiff_pct_30d FROM player_rolling_stats WHERE player_id = 100")
            ).fetchone()
        # whiff_pct = SUM(whiff=TRUE) / NULLIF(SUM(swing=TRUE), 0) * 100
        # pitch 5: whiff=1, swing=1 → 1 whiff out of 5 swings → 20%
        assert row is not None
        assert round(row[0], 2) == 20.00

    def test_whiff_pct_pitcher_200(self, pipeline):
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT whiff_pct_30d FROM player_rolling_stats WHERE player_id = 200")
            ).fetchone()
        # 1 whiff (pitch 7) out of 3 swings (pitches 7, 8, 10) → 33.33%
        assert row is not None
        assert round(row[0], 2) == 33.33

    def test_fip_calculation(self, pipeline):
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT fip_30d FROM player_rolling_stats WHERE player_id = 100")
            ).fetchone()
        # FIP = (13*HR + 3*BB - 2*K) / IP * 9 + 3.10
        # Pitcher 100: 1 HR, 0 BB, 0 K, 2 AB → FIP = (13*1 + 3*0 - 2*0)/2*9 + 3.10
        #   = 13/2*9 + 3.10 = 58.5 + 3.10 = 61.60
        assert row is not None
        assert round(row[0], 4) == 61.6000

    def test_skip_non_final_games(self, pipeline):
        with pipeline.engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO games (game_id, game_date, home_team_id, away_team_id, status)
                VALUES ('2026-05-20-LAD-SFG', '2026-05-20', 'SFG', 'LAD', 'SCHEDULED')
            """)
            )
            conn.execute(
                text("""
                INSERT INTO at_bats (ab_id, game_id, pitcher_id, batter_id, events, inning, half_inning)
                VALUES (100, '2026-05-20-LAD-SFG', 300, 5, 'home_run', 1, 'T')
            """)
            )
        pipeline.compute_player_rolling_stats(date(2026, 5, 20))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT COUNT(*) FROM player_rolling_stats WHERE game_id = '2026-05-20-LAD-SFG'"
                )
            ).scalar()
        assert row == 0


class TestComputeBatterRollingStats:
    def test_inserts_4_batter_rows(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT player_id, woba_30d, k_pct_30d, bb_pct_30d FROM batter_rolling_stats")
            ).fetchall()
        # 4 batter_ids: 1 (2 ABs), 2 (2 ABs), 3 (1 AB), 4 (1 AB)
        assert len(rows) == 4

    def test_woba_batter_1(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_30d FROM batter_rolling_stats WHERE player_id = 1")
            ).fetchone()
        # Batter 1: single (0.90), field_out (0) → AVG = 0.45
        assert row is not None
        assert round(row[0], 4) == 0.4500

    def test_k_pct_batter_3(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text("SELECT k_pct_30d FROM batter_rolling_stats WHERE player_id = 3")
            ).fetchone()
        # Batter 3: 1 AB, strikeout → k_pct = 1/1*100 = 100
        assert row is not None
        assert round(row[0], 1) == 100.0

    def test_bb_pct_batter_4(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text("SELECT bb_pct_30d FROM batter_rolling_stats WHERE player_id = 4")
            ).fetchone()
        # Batter 4: 1 AB, walk → bb_pct = 1/1*100 = 100
        assert row is not None
        assert round(row[0], 1) == 100.0

    def test_groundball_pct_batter_1(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text("SELECT groundball_pct_30d FROM batter_rolling_stats WHERE player_id = 1")
            ).fetchone()
        # Batter 1: 2 ABs with launch_angle: 8.0 (gb), 5.0 (gb) → 2/2*100 = 100
        assert row is not None
        assert round(row[0], 1) == 100.0

    def test_flyball_pct_batter_2(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text("SELECT flyball_pct_30d FROM batter_rolling_stats WHERE player_id = 2")
            ).fetchone()
        # Batter 2: 2 ABs with launch_angle: 30.0 (fb), 40.0 (fb) → 2/2*100 = 100
        assert row is not None
        assert round(row[0], 1) == 100.0

    def test_hr_per_9_batter_2(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text("SELECT hr_per_9_30d FROM batter_rolling_stats WHERE player_id = 2")
            ).fetchone()
        # Batter 2: 1 HR in 2 events → 1/2*9 = 4.5
        assert row is not None
        assert round(row[0], 2) == 4.5

    def test_null_launch_angle_ignored(self, pipeline_with_batter_angles):
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT groundball_pct_30d, flyball_pct_30d FROM batter_rolling_stats WHERE player_id = 4"
                )
            ).fetchone()
        # Batter 4: walk with NULL launch_angle → no batted balls → 0
        assert row is not None
        assert row[0] == 0
        assert row[1] == 0

    def test_upserts_on_conflict(self, pipeline_with_batter_angles):
        with pipeline_with_batter_angles.engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO batter_rolling_stats (player_id, game_id, as_of_date, woba_30d)
                VALUES (1, '2026-05-19-NYY-BOS', '2026-05-19', 0.999)
            """)
            )
        pipeline_with_batter_angles.compute_batter_rolling_stats(date(2026, 5, 19))
        with pipeline_with_batter_angles.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_30d FROM batter_rolling_stats WHERE player_id = 1")
            ).fetchone()
        # Should be updated to 0.45 (not 0.999)
        assert round(row[0], 4) == 0.4500


class TestComputeWobaWindows:
    def test_woba_7d(self, pipeline):
        with pipeline.engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats (player_id, game_id, as_of_date)
                VALUES (100, '2026-05-19-NYY-BOS', '2026-05-19')
            """)
            )
        pipeline._compute_woba_windows(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_7d FROM player_rolling_stats WHERE player_id = 100")
            ).fetchone()
        assert row is not None
        assert round(row[0], 4) == 1.4500

    def test_woba_14d(self, pipeline):
        with pipeline.engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats (player_id, game_id, as_of_date)
                VALUES (100, '2026-05-19-NYY-BOS', '2026-05-19')
            """)
            )
        pipeline._compute_woba_windows(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_14d FROM player_rolling_stats WHERE player_id = 100")
            ).fetchone()
        assert row is not None
        assert round(row[0], 4) == 1.4500

    def test_woba_window_out_of_range(self, pipeline):
        with pipeline.engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats (player_id, game_id, as_of_date)
                VALUES (100, '2026-05-19-NYY-BOS', '2026-05-19')
            """)
            )
        # target_date far in the future — no games in window
        pipeline._compute_woba_windows(date(2026, 7, 1))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_7d FROM player_rolling_stats WHERE player_id = 100")
            ).fetchone()
        # should remain NULL (no matching ABs in window)
        assert row is not None
        assert row[0] is None


class TestComputeTeamRollingStats:
    def test_inserts_team_stats(self, pipeline):
        pipeline.compute_team_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT team_id, game_id FROM team_rolling_stats ORDER BY team_id")
            ).fetchall()
        # Both home (BOS) and away (NYY) teams
        assert len(rows) == 2
        teams = {r[0] for r in rows}
        assert teams == {"BOS", "NYY"}

    def test_team_woba_from_home_and_away_abs(self, pipeline):
        pipeline.compute_team_rolling_stats(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("SELECT woba_30d FROM team_rolling_stats WHERE team_id = 'NYY'")
            ).fetchone()
        assert row is not None
        assert row[0] is not None


class TestComputeFatigueScores:
    def test_updates_fatigue_fields(self, pipeline):
        with pipeline.engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats (player_id, game_id, as_of_date)
                VALUES (100, '2026-05-19-NYY-BOS', '2026-05-19')
            """)
            )
        pipeline.compute_fatigue_scores(date(2026, 5, 19))
        with pipeline.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT days_rested, pitches_last_7d, fatigue_score
                    FROM player_rolling_stats WHERE player_id = 100
                """)
            ).fetchone()
        assert row is not None
        assert row[0] == 1  # home_rest_days = 1
        assert row[1] == 6  # 6 pitches in the last 7 days
        assert row[2] is not None
        # fatigue = LEAST(1.0, 1 * 0.10 + 6/200.0 * 0.30) = LEAST(1.0, 0.10 + 0.009) = 0.109
        assert round(row[2], 3) == 0.109


class TestRunFullPipeline:
    def test_runs_all_steps_without_error(self, pipeline):
        with pipeline.engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats (player_id, game_id, as_of_date)
                VALUES (100, '2026-05-19-NYY-BOS', '2026-05-19')
            """)
            )
        # Should not raise — detect_sharp_money and refresh_materialized_view
        # are skipped because they use PG-specific features
        pipeline.compute_player_rolling_stats(date(2026, 5, 19))
        pipeline.compute_batter_rolling_stats(date(2026, 5, 19))
        pipeline._compute_woba_windows(date(2026, 5, 19))
        pipeline.compute_team_rolling_stats(date(2026, 5, 19))
        pipeline.compute_fatigue_scores(date(2026, 5, 19))
        # Verify final state
        with pipeline.engine.connect() as conn:
            prs = conn.execute(text("SELECT COUNT(*) FROM player_rolling_stats")).scalar()
            brs = conn.execute(text("SELECT COUNT(*) FROM batter_rolling_stats")).scalar()
            trs = conn.execute(text("SELECT COUNT(*) FROM team_rolling_stats")).scalar()
        assert prs == 2
        assert brs == 4
        assert trs == 2
