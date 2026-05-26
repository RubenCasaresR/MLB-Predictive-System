"""Tests para el Criterio de Kelly."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from risk.kelly_criterion import (
    BankrollManager,
    KellyCriterion,
    KellyVariant,
)


@pytest.fixture
def kelly_quarter():
    return KellyCriterion(
        bankroll=10000.0,
        variant=KellyVariant.QUARTER,
    )


@pytest.fixture
def manager():
    return BankrollManager(initial=10000.0)


class TestKellyVariant:
    def test_full_kelly(self, kelly_quarter):
        # For the test, override variant
        kelly_quarter.variant = KellyVariant.FULL
        kelly_quarter.fraction_map[KellyVariant.FULL] = 1.0
        kelly_quarter.max_stake_pct = 1.0
        result = kelly_quarter.compute(0.55, -110)
        assert result.full_kelly >= result.fractional_kelly

    def test_fractional_scales_down(self, kelly_quarter):
        full = KellyCriterion(10000, KellyVariant.FULL, 1.0, 0.001, 0.0)
        half = KellyCriterion(10000, KellyVariant.HALF, 1.0, 0.001, 0.0)
        r_full = full.compute(0.55, -110)
        r_half = half.compute(0.55, -110)
        assert r_half.fractional_kelly <= r_full.fractional_kelly

    def test_quarter_kelly_conservative(self, kelly_quarter):
        r = kelly_quarter.compute(0.55, -110)
        assert r.fractional_kelly <= 0.05
        assert r.risk_level in ("conservative", "moderate")


class TestKellyComputation:
    def test_kelly_fair_price_zero(self, kelly_quarter):
        r = kelly_quarter.compute(0.50, -100)
        assert r.fractional_kelly == 0.0
        assert not r.is_viable

    def test_kelly_high_confidence(self, kelly_quarter):
        r = kelly_quarter.compute(0.70, -150)
        assert r.fractional_kelly > 0
        assert r.is_viable

    def test_kelly_negative_odds(self, kelly_quarter):
        r = kelly_quarter.compute(0.75, -300)
        assert r.fractional_kelly >= 0

    def test_kelly_min_threshold(self, kelly_quarter):
        kelly_quarter.min_kelly = 0.01
        r = kelly_quarter.compute(0.51, -110)
        if r.fractional_kelly < 0.01:
            assert not r.is_viable

    def test_kelly_with_confidence(self, kelly_quarter):
        r1 = kelly_quarter.compute(0.55, -110, confidence=1.0)
        r2 = kelly_quarter.compute(0.55, -110, confidence=0.5)
        assert r2.recommended_stake <= r1.recommended_stake


class TestBankrollManager:
    def test_initial_state(self, manager):
        assert manager.current == 10000.0
        assert manager.peak == 10000.0

    def test_win_increases_bankroll(self, manager):
        manager.record_bet(100, -110, True)
        assert manager.current > 10000.0
        assert manager.total_profit > 0

    def test_loss_decreases_bankroll(self, manager):
        manager.record_bet(500, -110, False)
        assert manager.current < 10000.0
        assert manager.total_profit < 0

    def test_drawdown_tracking(self, manager):
        manager.record_bet(2000, -110, False)
        assert manager.drawdown > 0

    def test_roi_win_only(self, manager):
        manager.record_bet(100, -110, True)
        assert manager.roi() > 0

    def test_roi_loss_only(self, manager):
        manager.record_bet(100, -110, False)
        assert manager.roi() < 0

    def test_sharpe_ratio(self, manager):
        manager.record_bet(100, -110, True)
        manager.record_bet(100, -110, False)
        manager.record_bet(100, -110, True)
        sharpe = manager.sharpe_ratio()
        assert isinstance(sharpe, float)

    def test_status_dict(self, manager):
        manager.record_bet(500, -110, True)
        status = manager.status()
        assert "current" in status
        assert "roi" in status
        assert "sharpe_ratio" in status


class TestMultipleBets:
    def test_scaling(self, kelly_quarter):
        bets = [
            ("A", "ML", 0.55, -110, 1.0),
            ("B", "ML", 0.58, -120, 1.0),
            ("C", "ML", 0.53, -105, 1.0),
        ]
        results = kelly_quarter.compute_multiple(bets)
        assert len(results) == 3
        total_kelly = sum(r.fractional_kelly for r in results)
        assert total_kelly <= 0.25
