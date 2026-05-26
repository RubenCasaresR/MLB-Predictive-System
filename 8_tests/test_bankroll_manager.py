"""Tests para PersistentBankrollManager con SQLite."""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

from risk.bankroll_manager import ExposureLimit, PersistentBankrollManager

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def db_url():
    return "sqlite://"


@pytest.fixture
def bm(db_url):
    from sqlalchemy import create_engine, text

    bm = PersistentBankrollManager(initial=10000.0, db_url=db_url, user_id="test")
    with bm.engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS bankroll_state (
                user_id TEXT PRIMARY KEY,
                current REAL NOT NULL,
                peak REAL NOT NULL,
                total_wagered REAL DEFAULT 0,
                total_profit REAL DEFAULT 0,
                updated_at TEXT
            )
        """)
        )
    return bm


# ============================================================================
# Tests: save_state
# ============================================================================


class TestSaveState:
    def test_persists_bankroll_to_db(self, bm):
        bm.save_state()
        with bm.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT current, peak, total_wagered, total_profit, user_id FROM bankroll_state"
                )
            ).fetchone()
        assert row is not None
        assert row[0] == 10000.0
        assert row[1] == 10000.0
        assert row[2] == 0.0
        assert row[3] == 0.0
        assert row[4] == "test"

    def test_updates_existing_row(self, bm):
        bm.save_state()
        bm.current = 9500.0
        bm.total_wagered = 500.0
        bm.total_profit = -500.0
        bm.save_state()
        with bm.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT current, total_wagered, total_profit FROM bankroll_state WHERE user_id = 'test'"
                )
            ).fetchone()
        assert round(row[0], 2) == 9500.0
        assert row[2] == -500.0

    def test_peak_only_increases(self, bm):
        bm.save_state()
        bm.current = 10500.0
        bm.peak = 10500.0
        bm.save_state()
        bm.current = 9000.0
        bm.peak = 10500.0  # peak stays
        bm.save_state()
        with bm.engine.connect() as conn:
            row = conn.execute(
                text("SELECT peak FROM bankroll_state WHERE user_id = 'test'")
            ).fetchone()
        assert row[0] == 10500.0

    def test_silent_noop_when_no_engine(self):
        bm = PersistentBankrollManager(initial=10000.0, db_url="", user_id="noengine")
        # should not raise
        bm.save_state()


# ============================================================================
# Tests: check_exposure
# ============================================================================


class TestCheckExposure:
    def test_approved_within_limits(self, bm):
        result = bm.check_exposure(stake=400.0)
        assert result["approved"] is True
        assert result["violations"] == []

    def test_exceeds_max_per_bet(self, bm):
        result = bm.check_exposure(stake=600.0)
        assert result["approved"] is False
        assert any("exceeds max per bet" in v for v in result["violations"])

    def test_exceeds_max_drawdown(self, bm):
        # max_drawdown = 0.20, so min bankroll = 8000
        result = bm.check_exposure(stake=2500.0)
        assert result["approved"] is False
        assert any("drawdown" in v for v in result["violations"])

    def test_exceeds_daily_limit(self, bm):
        bet_date = date(2026, 5, 20)
        # Add some bets today
        bm.bet_history = [
            {"stake": 2000, "won": True, "date": bet_date},
        ]
        result = bm.check_exposure(stake=600.0, bet_date=bet_date)
        assert result["approved"] is False
        assert any("Daily total" in v for v in result["violations"])

    def test_recent_losses_triggers_cooling_off(self, bm):
        bm.bet_history = [
            {"stake": 300, "won": False, "date": date(2026, 5, 19)},
            {"stake": 400, "won": False, "date": date(2026, 5, 19)},
            {"stake": 500, "won": False, "date": date(2026, 5, 19)},
            {"stake": 200, "won": False, "date": date(2026, 5, 20)},
            {"stake": 300, "won": False, "date": date(2026, 5, 20)},
        ]  # last 5 losses total = 1700 > 1500 (15% of 10000)
        result = bm.check_exposure(stake=100.0)
        assert result["approved"] is False
        assert any("cooling off" in v.lower() for v in result["violations"])

    def test_returns_correct_metadata(self, bm):
        result = bm.check_exposure(stake=250.0)
        assert result["current_bankroll"] == 10000.0
        assert result["stake"] == 250.0
        assert result["stake_pct"] == 2.5


# ============================================================================
# Tests: get_bet_slip_summary
# ============================================================================


class TestBetSlipSummary:
    def test_empty_bets(self, bm):
        summary = bm.get_bet_slip_summary([])
        assert summary["total_bets"] == 0
        assert summary["total_stake"] == 0.0
        assert summary["average_kelly"] == 0

    def test_single_bet(self, bm):
        summary = bm.get_bet_slip_summary(
            [
                {"recommended_stake": 250, "kelly_fraction": 0.025},
            ]
        )
        assert summary["total_bets"] == 1
        assert summary["total_stake"] == 250.0
        assert summary["stake_pct"] == 2.5
        assert summary["average_kelly"] == 0.025

    def test_multiple_bets(self, bm):
        summary = bm.get_bet_slip_summary(
            [
                {"recommended_stake": 200, "kelly_fraction": 0.02},
                {"recommended_stake": 300, "kelly_fraction": 0.03},
                {"recommended_stake": 150, "kelly_fraction": 0.015},
            ]
        )
        assert summary["total_bets"] == 3
        assert summary["total_stake"] == 650.0
        assert summary["stake_pct"] == 6.5
        assert round(summary["average_kelly"], 4) == 0.0217
        assert summary["remaining_capacity"] == 9350.0


# ============================================================================
# Tests: ExposureLimit
# ============================================================================


class TestExposureLimit:
    def test_defaults(self):
        limits = ExposureLimit()
        assert limits.max_per_bet == 500.0
        assert limits.max_per_day == 2500.0
        assert limits.max_per_week == 10000.0
        assert limits.max_drawdown == 0.20
        assert limits.max_concurrent_bets == 10
