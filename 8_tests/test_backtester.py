"""Tests para BacktestEngine — motor de backtesting diario."""

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from unittest.mock import ANY, MagicMock, PropertyMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from risk.backtester import (
    BacktestEngine,
    BacktestGameRecord,
    BacktestResult,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_engine() -> BacktestEngine:
    eng = BacktestEngine(db_url="sqlite:///:memory:", initial_bankroll=10_000)
    eng.bankroll.save_state = MagicMock()
    return eng


def _dummy_context() -> dict:
    return {
        "pf_hr": 1.0, "pf_woba": 1.0, "pf_k": 1.0,
        "temperature": 70.0, "wind_speed": 0.0, "wind_direction": "NONE",
        "umpire_cs_rate": 0.0, "stadium_id": 0, "umpire_id": 0,
        "home_bp_era": 4.50, "home_bp_fip": 4.50,
        "away_bp_era": 4.50, "away_bp_fip": 4.50,
        "home_rest_days": 4, "away_rest_days": 4,
        "home_travel_miles": 0, "away_travel_miles": 0,
        "home_tz_crossings": 0, "away_tz_crossings": 0,
    }


# ============================================================================
# Implied probability
# ============================================================================


class TestImpliedProb:
    def test_positive_odds(self):
        assert BacktestEngine._implied_prob(+100) == 0.50
        assert BacktestEngine._implied_prob(+200) == 1.0 / 3.0
        assert round(BacktestEngine._implied_prob(+400), 4) == 0.20

    def test_negative_odds(self):
        assert round(BacktestEngine._implied_prob(-110), 4) == 0.5238
        assert BacktestEngine._implied_prob(-200) == 2.0 / 3.0
        assert round(BacktestEngine._implied_prob(-500), 4) == 0.8333

    def test_even_odds(self):
        assert BacktestEngine._implied_prob(0) == 0.0


# ============================================================================
# Skipped records
# ============================================================================


class TestSkippedRecord:
    def test_creates_record_with_reason(self):
        engine = _make_engine()
        game = {
            "game_id": "G01",
            "home_team": "NYY",
            "away_team": "BOS",
            "home_score": 5,
            "away_score": 3,
        }
        rec = engine._skipped_record(game, "no_lineup")
        assert rec.game_id == "G01"
        assert rec.skipped_reason == "no_lineup"
        assert rec.won is None
        assert rec.stake == 0.0

    def test_no_odds_creates_record_with_skipped_reason(self):
        engine = _make_engine()
        game = {
            "game_id": "G01",
            "home_team": "NYY",
            "away_team": "BOS",
            "home_score": 5,
            "away_score": 3,
            "home_odds": None,
            "away_odds": None,
        }
        rec = engine._evaluate_bet(game, 0.6, date(2023, 6, 15))
        assert rec.skipped_reason == "no_odds"
        assert rec.won is None


# ============================================================================
# Evaluate bet
# ============================================================================


class TestEvaluateBet:
    def test_skipped_when_no_odds(self):
        engine = _make_engine()
        game = {"game_id": "G01", "home_team": "NYY", "away_team": "BOS",
                "home_score": 5, "away_score": 3, "home_odds": None, "away_odds": None}
        rec = engine._evaluate_bet(game, 0.6, date(2023, 6, 15))
        assert rec.won is None
        assert rec.stake == 0.0

    def test_bets_home_when_home_wins_and_has_edge(self):
        engine = _make_engine()
        game = {"game_id": "G01", "home_team": "NYY", "away_team": "BOS",
                "home_score": 5, "away_score": 3, "home_odds": -110, "away_odds": -110}
        rec = engine._evaluate_bet(game, 0.65, date(2023, 6, 15))
        assert rec.side == "home"
        assert rec.won is True
        assert rec.stake > 0
        assert rec.edge > 0
        assert rec.odds_taken == -110

    def test_bets_away_when_away_wins_and_has_edge(self):
        engine = _make_engine()
        game = {"game_id": "G02", "home_team": "NYY", "away_team": "BOS",
                "home_score": 2, "away_score": 5, "home_odds": -110, "away_odds": -110}
        rec = engine._evaluate_bet(game, 0.35, date(2023, 6, 15))
        assert rec.side == "away"
        assert rec.won is True
        assert rec.stake > 0

    def test_no_bet_when_no_edge(self):
        engine = _make_engine()
        game = {"game_id": "G03", "home_team": "NYY", "away_team": "BOS",
                "home_score": 5, "away_score": 3, "home_odds": -110, "away_odds": -110}
        rec = engine._evaluate_bet(game, 0.52, date(2023, 6, 15))
        assert rec.won is None
        assert rec.stake == 0.0

    def test_prefers_best_edge(self):
        engine = _make_engine()
        game = {"game_id": "G04", "home_team": "NYY", "away_team": "BOS",
                "home_score": 5, "away_score": 3, "home_odds": -110, "away_odds": +200}
        # home_win=0.6, implied_home=0.5238 → edge_ratio=1.145
        # away_win=0.4, implied_away=0.3333 → edge_ratio=1.200
        # Both have edge > 0.02, code picks highest edge_ratio → away
        # Home wins 5-3, so away bet loses
        rec = engine._evaluate_bet(game, 0.60, date(2023, 6, 15))
        assert rec.side == "away"
        assert rec.won is False


# ============================================================================
# Get final games
# ============================================================================


class TestGetFinalGames:
    def test_returns_empty_when_no_games(self):
        engine = BacktestEngine(db_url="sqlite:///:memory:")
        games = engine._get_final_games(date(2023, 6, 15))
        assert games == []


# ============================================================================
# Get game context (SQLite returns empty results)
# ============================================================================


class TestGetGameContext:
    def test_returns_none_when_tables_missing(self):
        engine = BacktestEngine(db_url="sqlite:///:memory:")
        ctx = engine._get_game_context("G01", "NYY", "BOS", date(2023, 6, 14))
        assert ctx is None


# ============================================================================
# Full run (mocked internals)
# ============================================================================


class TestRun:
    @patch("risk.backtester.MonteCarloMLBSimulator")
    @patch("risk.backtester.build_player_states_from_db")
    @patch("risk.backtester.fetch_league_avg_probs")
    def test_bets_home_when_edge_exists(self, mock_flap, mock_bps, mock_mcs):
        mock_flap.return_value = None
        mock_bps.return_value = ([], [], MagicMock(), MagicMock())
        mock_sim = MagicMock()
        mock_res = MagicMock()
        mock_res.home_win_prob = 0.65
        mock_sim.run_simulation.return_value = mock_res
        mock_mcs.return_value = mock_sim

        engine = _make_engine()

        with patch.object(engine, "_get_final_games") as mock_gg:
            mock_gg.return_value = [{
                "game_id": "G01", "home_team": "NYY", "away_team": "BOS",
                "home_pitcher": 100, "away_pitcher": 200,
                "home_score": 5, "away_score": 3,
                "home_odds": -110, "away_odds": -110,
            }]
            with patch.object(engine, "_get_game_context") as mock_gc:
                mock_gc.return_value = _dummy_context()

                result = engine.run(date(2023, 6, 15), date(2023, 6, 15))

        assert result.n_games == 1
        assert result.total_bets == 1
        assert result.total_wins == 1
        assert result.total_return_pct > 0

    @patch("risk.backtester.MonteCarloMLBSimulator")
    @patch("risk.backtester.build_player_states_from_db")
    @patch("risk.backtester.fetch_league_avg_probs")
    def test_skips_games_without_lineups(self, mock_flap, mock_bps, mock_mcs):
        from prediction.player_state_builder import IncompleteLineupError

        mock_flap.return_value = None
        mock_bps.side_effect = IncompleteLineupError("No lineup")
        mock_mcs.return_value = MagicMock()

        engine = _make_engine()

        with patch.object(engine, "_get_final_games") as mock_gg:
            mock_gg.return_value = [{
                "game_id": "G01", "home_team": "NYY", "away_team": "BOS",
                "home_pitcher": 100, "away_pitcher": 200,
                "home_score": 5, "away_score": 3,
                "home_odds": -110, "away_odds": -110,
            }]

            result = engine.run(date(2023, 6, 15), date(2023, 6, 15))

        assert result.n_games == 1
        assert result.n_games_skipped == 1
        assert result.total_bets == 0

    @patch("risk.backtester.MonteCarloMLBSimulator")
    @patch("risk.backtester.build_player_states_from_db")
    @patch("risk.backtester.fetch_league_avg_probs")
    def test_multiple_days(self, mock_flap, mock_bps, mock_mcs):
        mock_flap.return_value = None
        mock_bps.return_value = ([], [], MagicMock(), MagicMock())
        mock_sim = MagicMock()
        mock_res = MagicMock()
        mock_res.home_win_prob = 0.55
        mock_sim.run_simulation.return_value = mock_res
        mock_mcs.return_value = mock_sim

        engine = _make_engine()

        with patch.object(engine, "_get_final_games") as mock_gg:
            with patch.object(engine, "_get_game_context") as mock_gc:
                mock_gg.side_effect = lambda d: [{
                    "game_id": f"G{d.day:02d}",
                    "home_team": "NYY", "away_team": "BOS",
                    "home_pitcher": 100, "away_pitcher": 200,
                    "home_score": 5, "away_score": 3,
                    "home_odds": -110, "away_odds": -110,
                }] if d.day in (1, 2) else []

                mock_gc.return_value = _dummy_context()

                result = engine.run(date(2023, 6, 1), date(2023, 6, 3))

        assert result.n_games == 2
        assert result.total_bets == 2

    @patch("risk.backtester.MonteCarloMLBSimulator")
    @patch("risk.backtester.build_player_states_from_db")
    @patch("risk.backtester.fetch_league_avg_probs")
    def test_skips_games_without_odds(self, mock_flap, mock_bps, mock_mcs):
        mock_flap.return_value = None
        mock_bps.return_value = ([], [], MagicMock(), MagicMock())
        mock_mcs.return_value = MagicMock()

        engine = _make_engine()

        with patch.object(engine, "_get_final_games") as mock_gg:
            mock_gg.return_value = [{
                "game_id": "G01", "home_team": "NYY", "away_team": "BOS",
                "home_pitcher": 100, "away_pitcher": 200,
                "home_score": 5, "away_score": 3,
                "home_odds": None, "away_odds": None,
            }]
            with patch.object(engine, "_get_game_context") as mock_gc:
                mock_gc.return_value = _dummy_context()

                result = engine.run(date(2023, 6, 15), date(2023, 6, 15))

        assert result.n_games == 1
        assert result.n_games_skipped == 0
        assert result.total_bets == 0


# ============================================================================
# Build result
# ============================================================================


class TestBuildResult:
    def test_empty_backtest(self):
        engine = _make_engine()
        result = engine._build_result([], 0, 0, date(2023, 1, 1), date(2023, 1, 1))
        assert result.total_bets == 0
        assert result.win_rate == 0.0
        assert result.roi_pct == 0.0
        assert result.final_bankroll == 10_000

    def test_with_records(self):
        engine = _make_engine()
        engine.bankroll.record_bet(250, -110, True, game_id="G1")
        engine.bankroll.record_bet(200, +150, True, game_id="G2")
        engine.bankroll.record_bet(100, -110, False, game_id="G3")

        records = [
            BacktestGameRecord(
                game_id="G1", game_date=date(2023, 1, 1),
                home_team="A", away_team="B",
                home_score=5, away_score=3, home_odds=-110, away_odds=-110,
                home_win_prob=0.6, side="home", odds_taken=-110,
                stake=250, won=True, edge=0.05,
            ),
            BacktestGameRecord(
                game_id="G2", game_date=date(2023, 1, 1),
                home_team="A", away_team="B",
                home_score=2, away_score=4, home_odds=-110, away_odds=-110,
                home_win_prob=0.4, side="away", odds_taken=+150,
                stake=200, won=True, edge=0.05,
            ),
            BacktestGameRecord(
                game_id="G3", game_date=date(2023, 1, 1),
                home_team="A", away_team="B",
                home_score=3, away_score=2, home_odds=-110, away_odds=-110,
                home_win_prob=0.55, side="home", odds_taken=-110,
                stake=100, won=False, edge=0.02,
            ),
        ]
        result = engine._build_result(records, 3, 0, date(2023, 1, 1), date(2023, 1, 2))
        assert result.total_bets == 3
        assert result.total_wins == 2
        assert result.total_losses == 1

    def test_print_report(self):
        engine = _make_engine()
        result = BacktestResult(
            initial_bankroll=10000.0, final_bankroll=11000.0,
            total_return_pct=10.0, total_bets=100, total_wins=55,
            total_losses=45, win_rate=55.0, roi_pct=5.0,
            sharpe_ratio=0.8, max_drawdown_pct=12.0,
            n_games=150, n_games_skipped=50,
            start_date="2023-04-01", end_date="2023-09-30",
        )
        engine.print_report(result)

    def test_export_report(self):
        engine = _make_engine()
        result = BacktestResult(
            initial_bankroll=10000.0, final_bankroll=11000.0,
            total_return_pct=10.0, total_bets=100, total_wins=55,
            total_losses=45, win_rate=55.0, roi_pct=5.0,
            sharpe_ratio=0.8, max_drawdown_pct=12.0,
            n_games=150, n_games_skipped=50,
            start_date="2023-04-01", end_date="2023-09-30",
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            engine.export_report(result, path)
            with open(path) as f:
                data = json.load(f)
            assert data["initial_bankroll"] == 10000.0
            assert data["roi_pct"] == 5.0
        finally:
            os.unlink(path)


# ============================================================================
# Data leakage — build_player_states recibe X-1
# ============================================================================


class TestDataLeakageIsolation:
    def test_build_player_states_called_with_day_before(self):
        engine = _make_engine()

        with patch.object(engine, "_get_final_games") as mock_gg:
            mock_gg.return_value = [{
                "game_id": "G01", "home_team": "NYY", "away_team": "BOS",
                "home_pitcher": 100, "away_pitcher": 200,
                "home_score": 5, "away_score": 3,
                "home_odds": -110, "away_odds": -110,
            }]
            with patch.object(engine, "_get_game_context") as mock_gc:
                mock_gc.return_value = _dummy_context()
                with patch("risk.backtester.build_player_states_from_db") as mock_bps:
                    mock_bps.return_value = ([], [], MagicMock(), MagicMock())
                    with patch("risk.backtester.fetch_league_avg_probs") as mock_flap:
                        mock_flap.return_value = None
                        with patch("risk.backtester.MonteCarloMLBSimulator") as mock_mcs:
                            mock_sim = MagicMock()
                            mock_res = MagicMock()
                            mock_res.home_win_prob = 0.55
                            mock_sim.run_simulation.return_value = mock_res
                            mock_mcs.return_value = mock_sim

                            engine.run(date(2023, 6, 15), date(2023, 6, 15))

                            args, kwargs = mock_bps.call_args
                            target_date_arg = args[-1]
                            assert target_date_arg == date(2023, 6, 14), (
                                f"Expected 2023-06-14, got {target_date_arg}"
                            )
