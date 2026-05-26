"""Tests para el detector de Sharp Money."""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from features.sharp_money import SharpMoneyDetector


@pytest.fixture
def detector():
    return SharpMoneyDetector()


class TestSharpMoneyDetection:
    def test_public_money_vs_sharp_discrepancy(self, detector):
        signal = detector.analyze(
            game_id="TEST",
            team_id="NYY",
            opponent_id="BOS",
            sportsbook="DraftKings",
            timestamp=datetime.now(),
            ticket_pct_team=72.0,
            money_pct_team=42.0,
            line_open_team=-130,
            line_current_team=-115,
        )
        assert signal is not None
        assert signal.signal_type == "SHARP_MONEY" or signal.signal_type == "BOTH"

    def test_no_signal_when_balanced(self, detector):
        signal = detector.analyze(
            game_id="TEST",
            team_id="NYY",
            opponent_id="BOS",
            sportsbook="DraftKings",
            timestamp=datetime.now(),
            ticket_pct_team=50.0,
            money_pct_team=50.0,
            line_open_team=-120,
            line_current_team=-120,
        )
        assert signal is None

    def test_reverse_line_movement(self, detector):
        signal = detector.analyze(
            game_id="TEST",
            team_id="NYY",
            opponent_id="BOS",
            sportsbook="DraftKings",
            timestamp=datetime.now(),
            ticket_pct_team=68.0,
            money_pct_team=65.0,
            line_open_team=-130,
            line_current_team=-110,
        )
        if signal:
            assert "RLM" in signal.signal_type or signal.signal_type == "SHARP_MONEY"

    def test_high_confidence_actionable(self, detector):
        signal = detector.analyze(
            game_id="TEST",
            team_id="LAD",
            opponent_id="SFG",
            sportsbook="FanDuel",
            timestamp=datetime.now(),
            ticket_pct_team=80.0,
            money_pct_team=35.0,
            line_open_team=-150,
            line_current_team=-120,
        )
        assert signal is not None
        assert signal.is_actionable
        assert signal.confidence >= 0.60


class TestFullGameAnalysis:
    def test_home_and_away_signals(self, detector):
        signals = detector.analyze_full_game(
            game_id="TEST",
            home_team="NYY",
            away_team="BOS",
            sportsbook="DraftKings",
            timestamp=datetime.now(),
            home_ticket_pct=72.0,
            home_money_pct=42.0,
            home_line_open=-130,
            home_line_current=-115,
        )
        assert len(signals) >= 1

    def test_no_signals_when_fair_market(self, detector):
        signals = detector.analyze_full_game(
            game_id="TEST",
            home_team="NYY",
            away_team="BOS",
            sportsbook="DraftKings",
            timestamp=datetime.now(),
            home_ticket_pct=50.0,
            home_money_pct=50.0,
            home_line_open=-120,
            home_line_current=-120,
        )
        assert len(signals) == 0


class TestBatchAnalysis:
    def test_batch_dataframe(self, detector):
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "game_id": "TEST",
                    "home_team_id": "NYY",
                    "away_team_id": "BOS",
                    "sportsbook": "DraftKings",
                    "recorded_at": datetime.now(),
                    "home_ticket_pct": 72.0,
                    "home_money_pct": 42.0,
                    "home_moneyline_open": -130,
                    "home_moneyline_close": -115,
                }
            ]
        )
        result = detector.batch_analyze(df)
        assert len(result) >= 1


class TestSQLGeneration:
    def test_query_generation(self, detector):
        sql = detector.query_market_data_sql("2025-06-15-NYY-BOS")
        assert "market_lines" in sql
        assert "2025-06-15-NYY-BOS" in sql
        assert "JOIN" in sql
