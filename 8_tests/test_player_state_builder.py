"""Tests para player_state_builder: construcción de estados desde DB."""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

from prediction.monte_carlo_simulator import BatterState, PitcherState
from prediction.player_state_builder import (
    _fetch_pitcher_state,
    _fetch_team_lineup,
    build_player_states_from_db,
)

# ============================================================================
# Helpers
# ============================================================================


def _create_tables(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE players (
                player_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                team_id TEXT,
                bats TEXT,
                throws TEXT,
                status TEXT DEFAULT 'ACTIVE'
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
                k_pct_pitch_30d REAL,
                bb_pct_pitch_30d REAL,
                hr_per_9_30d REAL,
                whiff_pct_30d REAL,
                avg_velo_30d REAL,
                avg_spin_30d REAL,
                days_rested INTEGER,
                pitches_last_7d INTEGER,
                k_per_9_30d REAL,
                bb_per_9_30d REAL,
                fip_30d REAL,
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
                UNIQUE(team_id, game_id)
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
                position TEXT NOT NULL,
                is_starter INTEGER DEFAULT 1,
                UNIQUE(game_id, team_id, batting_order)
            )
        """)
        )


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False})
    _create_tables(e)
    return e


@pytest.fixture
def sample_date():
    return date(2026, 5, 20)


# ============================================================================
# Tests: _fetch_pitcher_state
# ============================================================================


class TestFetchPitcherState:
    def test_with_data(self, engine, sample_date):
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO players (player_id, full_name, throws)
                VALUES (100, 'Gerrit Cole', 'R')
            """)
            )
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats
                    (player_id, game_id, as_of_date,
                     k_pct_pitch_30d, bb_pct_pitch_30d, hr_per_9_30d,
                     whiff_pct_30d, avg_velo_30d, avg_spin_30d,
                     days_rested, pitches_last_7d)
                VALUES (100, '2026-05-19-NYY-BOS', '2026-05-19',
                        30.0, 8.0, 1.2, 15.0, 97.5, 2450.0, 5, 85)
            """)
            )

        ps = _fetch_pitcher_state(engine, 100, sample_date)
        assert isinstance(ps, PitcherState)
        assert ps.player_id == 100
        assert ps.name == "Gerrit Cole"
        assert ps.throws == "R"
        assert ps.k_rate == 0.3
        assert ps.bb_rate == 0.08
        assert ps.hr_rate == 1.2
        assert ps.whiff_pct == 0.15
        assert ps.avg_velo == 97.5
        assert ps.avg_spin == 2450.0
        assert ps.fatigue_factor == 1.0

    def test_fallback_no_data(self, engine, sample_date):
        ps = _fetch_pitcher_state(engine, 999, sample_date)
        assert isinstance(ps, PitcherState)
        assert ps.player_id == 999
        assert ps.throws == "R"
        assert ps.k_rate == 0.225
        assert ps.bb_rate == 0.08
        assert ps.hr_rate == 0.03
        assert ps.whiff_pct == 0.11
        assert ps.avg_velo == 93.0
        assert ps.avg_spin == 2200.0
        assert ps.fatigue_factor == 1.0

    def test_fallback_no_player_row(self, engine, sample_date):
        # No players table row for this pitcher_id
        ps = _fetch_pitcher_state(engine, 999, sample_date)
        assert ps.name == "Pitcher_999"
        assert ps.throws == "R"

    def test_fatigue_low_rest(self, engine, sample_date):
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO players (player_id, full_name, throws)
                VALUES (200, 'Tired Pitcher', 'R')
            """)
            )
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats
                    (player_id, game_id, as_of_date, days_rested, pitches_last_7d)
                VALUES (200, 'G1', '2026-05-19', 2, 120)
            """)
            )

        ps = _fetch_pitcher_state(engine, 200, sample_date)
        # days_rested=2, rest deficit = 4-2=2, fatigue -= 2*0.05 = 0.1
        # pitches_last_7d=120, excess=20, fatigue -= 20*0.001 = 0.02
        # fatigue = 1.0 - 0.1 - 0.02 = 0.88
        assert ps.fatigue_factor == 0.88

    def test_fatigue_min_cap(self, engine, sample_date):
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO players (player_id, full_name, throws)
                VALUES (300, 'Exhausted', 'R')
            """)
            )
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats
                    (player_id, game_id, as_of_date, days_rested, pitches_last_7d)
                VALUES (300, 'G1', '2026-05-19', 0, 500)
            """)
            )

        ps = _fetch_pitcher_state(engine, 300, sample_date)
        # 1.0 - 4*0.05 - (500-100)*0.001 = 1.0 - 0.2 - 0.4 = 0.4
        # capped at 0.75
        assert ps.fatigue_factor == 0.75


# ============================================================================
# Tests: _fetch_team_lineup
# ============================================================================


class TestFetchTeamLineup:
    def test_with_lineups_table(self, engine, sample_date):
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO players (player_id, full_name, team_id, bats)
                VALUES (1, 'Batter A', 'NYY', 'L'),
                       (2, 'Batter B', 'NYY', 'R'),
                       (3, 'Batter C', 'NYY', 'S')
            """)
            )
            conn.execute(
                text("""
                INSERT INTO batter_rolling_stats
                    (player_id, game_id, as_of_date, woba_30d,
                     k_pct_30d, bb_pct_30d, hr_per_9_30d,
                     groundball_pct_30d, flyball_pct_30d)
                VALUES
                    (1, 'G1', '2026-05-19', 0.380, 20.0, 10.0, 0.8, 44.0, 35.0),
                    (2, 'G1', '2026-05-19', 0.310, 22.0, 8.0, 0.5, 44.0, 35.0),
                    (3, 'G1', '2026-05-19', 0.350, 18.0, 12.0, 0.6, 44.0, 35.0)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO lineups (game_id, team_id, player_id, batting_order, position)
                VALUES ('20260520-NYY-BOS', 'NYY', 1, 1, 'DH'),
                       ('20260520-NYY-BOS', 'NYY', 2, 2, '1B'),
                       ('20260520-NYY-BOS', 'NYY', 3, 3, '2B')
            """)
            )

        lineup = _fetch_team_lineup(engine, "NYY", sample_date)
        assert len(lineup) == 9
        assert lineup[0].player_id == 1
        assert lineup[0].bats == "L"
        assert lineup[0].woba_vs_rhp == 0.38
        assert lineup[0].k_rate == 0.2
        assert lineup[1].player_id == 2
        assert lineup[2].player_id == 3

    def test_empty_no_lineups(self, engine, sample_date):
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO players (player_id, full_name, team_id, bats)
                VALUES (1, 'Batter A', 'NYY', 'L')
            """)
            )
        lineup = _fetch_team_lineup(engine, "NYY", sample_date)
        assert len(lineup) == 9  # fills with league avg placeholders
        assert lineup[0].player_id < 0  # placeholder ids are negative

    def test_with_stats_only_latest(self, engine, sample_date):
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO players (player_id, full_name, team_id, bats)
                VALUES (1, 'Batter', 'NYY', 'R')
            """)
            )
            conn.execute(
                text("""
                INSERT INTO batter_rolling_stats
                    (player_id, game_id, as_of_date, woba_30d)
                VALUES (1, 'G1', '2026-05-10', 0.200),
                       (1, 'G2', '2026-05-19', 0.400)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO lineups (game_id, team_id, player_id, batting_order, position)
                VALUES ('20260520-NYY-BOS', 'NYY', 1, 1, 'DH')
            """)
            )

        lineup = _fetch_team_lineup(engine, "NYY", sample_date)
        assert len(lineup) == 9  # 1 real + 8 league avg placeholders
        assert lineup[0].woba_vs_rhp == 0.4





# ============================================================================
# Tests: build_player_states_from_db (integración)
# ============================================================================


class TestBuildPlayerStatesFromDb:
    def test_all_fallbacks(self, engine, sample_date):
        home_l, away_l, home_p, away_p = build_player_states_from_db(
            engine,
            "G1",
            "NYY",
            "BOS",
            100,
            200,
            sample_date,
        )
        assert len(home_l) == 9
        assert len(away_l) == 9
        assert home_p.player_id == 100
        assert away_p.player_id == 200
        assert home_p.k_rate == 0.225
        assert all(b.woba_vs_rhp == 0.310 for b in home_l)

    def test_with_real_pitcher_and_placeholder_batters(self, engine, sample_date):
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO players (player_id, full_name, throws)
                VALUES (100, 'Gerrit Cole', 'R')
            """)
            )
            conn.execute(
                text("""
                INSERT INTO player_rolling_stats
                    (player_id, game_id, as_of_date, k_pct_pitch_30d,
                     whiff_pct_30d, avg_velo_30d)
                VALUES (100, 'G0', '2026-05-19', 30.0, 15.0, 97.5)
            """)
            )

        home_l, away_l, home_p, away_p = build_player_states_from_db(
            engine,
            "G1",
            "NYY",
            "BOS",
            100,
            200,
            sample_date,
        )
        assert home_p.k_rate == 0.3
        assert home_p.whiff_pct == 0.15
        assert home_p.avg_velo == 97.5
        assert len(home_l) == 9

    def test_placeholder_uses_league_avg_woba(self, engine, sample_date):
        home_l, _, _, _ = build_player_states_from_db(
            engine,
            "G1",
            "NYY",
            "BOS",
            100,
            200,
            sample_date,
        )
        assert all(b.woba_vs_rhp == 0.310 for b in home_l)
