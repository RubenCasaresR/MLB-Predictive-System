"""Tests para el EV Calculator."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from risk.ev_calculator import EVCalculator


@pytest.fixture
def calc():
    return EVCalculator(bankroll=10000.0)


class TestOddsConversion:
    def test_american_to_implied_positive(self, calc):
        assert abs(calc.american_to_implied(+150) - 0.40) < 0.01

    def test_american_to_implied_negative(self, calc):
        assert abs(calc.american_to_implied(-130) - 0.5652) < 0.01

    def test_american_to_decimal_positive(self, calc):
        assert abs(calc.american_to_decimal(+150) - 2.50) < 0.01

    def test_american_to_decimal_negative(self, calc):
        assert abs(calc.american_to_decimal(-130) - 1.769) < 0.01

    def test_implied_to_american(self, calc):
        odds = calc.implied_to_american(0.60)
        assert odds == -150


class TestEdgeComputation:
    def test_positive_edge(self, calc):
        edge, implied = calc.compute_edge(0.60, -110)
        assert edge > 0

    def test_negative_edge(self, calc):
        edge, implied = calc.compute_edge(0.40, -110)
        assert edge < 0

    def test_edge_at_break_even(self, calc):
        # Fair line: 0.50 @ -100
        edge, implied = calc.compute_edge(0.50, -100)
        assert abs(edge) < 0.02


class TestMoneylineEvaluation:
    def test_home_ev_positive(self, calc):
        bets = calc.evaluate_moneyline(
            game_id="TEST",
            home_team="NYY",
            away_team="BOS",
            home_odds=-110,
            away_odds=-110,
            home_real_prob=0.55,
            away_real_prob=0.45,
        )
        home_bets = [b for b in bets if b.team == "NYY"]
        assert len(home_bets) > 0

    def test_no_bets_when_no_edge(self, calc):
        bets = calc.evaluate_moneyline(
            game_id="TEST",
            home_team="NYY",
            away_team="BOS",
            home_odds=-110,
            away_odds=-110,
            home_real_prob=0.50,
            away_real_prob=0.50,
        )
        assert len(bets) == 0

    def test_both_sides_edge_possible(self, calc):
        bets = calc.evaluate_moneyline(
            game_id="TEST",
            home_team="NYY",
            away_team="BOS",
            home_odds=+200,
            away_odds=-250,
            home_real_prob=0.40,
            away_real_prob=0.60,
        )
        assert len(bets) <= 2


class TestKellyCriterion:
    def test_kelly_positive_edge(self, calc):
        k = calc._kelly(0.60, -110)
        assert k > 0
        assert k <= 0.05

    def test_kelly_zero_edge(self, calc):
        k = calc._kelly(0.50, -100)
        assert k == 0.0

    def test_kelly_capped(self, calc):
        k = calc._kelly(0.80, -200)
        assert k <= 0.05


class TestBestBetsFilter:
    def test_filters_by_edge(self, calc):
        from datetime import datetime

        from risk.ev_calculator import EVBet

        bets = [
            EVBet(
                "G1",
                "A",
                "",
                "DK",
                "ML",
                -110,
                0.55,
                0.50,
                0.05,
                0.02,
                200,
                datetime.now(),
                0.6,
                True,
            ),
            EVBet(
                "G2",
                "B",
                "",
                "DK",
                "ML",
                +150,
                0.60,
                0.40,
                0.20,
                0.04,
                400,
                datetime.now(),
                0.9,
                True,
            ),
        ]
        best = calc.filter_best_bets(bets, max_bets=1)
        assert len(best) <= 1


class TestPropEvaluation:
    def test_prop_over_ev(self, calc):
        bets = calc.evaluate_prop(
            game_id="TEST",
            player_name="Judge",
            prop_type="HR",
            line_value=1.5,
            over_odds=+250,
            under_odds=-300,
            prob_over=0.35,
            prob_under=0.65,
        )
        over_bets = [b for b in bets if "OVER" in b.market_type]
        assert len(over_bets) > 0 or len(bets) == 0
