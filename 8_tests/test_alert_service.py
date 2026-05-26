"""Tests para api/services/alert_service.py (AlertService)."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import ANY, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.services.alert_service import AlertService


def run_async(coro):
    return asyncio.run(coro)


def make_mock_signal(**overrides):
    defaults = {
        "game_id": "GAME-001",
        "team_id": "NYY",
        "opponent_id": "BOS",
        "sportsbook": "DraftKings",
        "timestamp": datetime.now(),
        "ticket_pct": 72.0,
        "money_pct": 42.0,
        "discrepancy": 0.30,
        "line_open": -130,
        "line_current": -115,
        "line_movement": 15,
        "signal_type": "SHARP_MONEY",
        "confidence": 0.85,
        "is_actionable": True,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def make_mock_bet(**overrides):
    defaults = {
        "game_id": "GAME-001",
        "team": "NYY",
        "opponent": "BOS",
        "sportsbook": "DraftKings",
        "market_type": "MONEYLINE",
        "odds": -110,
        "real_prob": 0.55,
        "implied_prob": 0.524,
        "edge": 0.026,
        "kelly_fraction": 0.015,
        "recommended_stake": 150.0,
        "timestamp": datetime.now(),
        "confidence": 0.7,
        "is_actionable": True,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


# ============================================================================
# Tests for __init__
# ============================================================================


class TestAlertServiceInit:
    def test_init_empty_history(self):
        svc = AlertService()
        assert svc.alert_history == []

    def test_init_no_subscribers(self):
        svc = AlertService()
        assert svc.subscribers == []

    def test_init_last_scan_none(self):
        svc = AlertService()
        assert svc.last_scan is None


# ============================================================================
# Tests for scan_market_for_alerts
# ============================================================================

PATCHES_MARKET = [
    "features.sharp_money.SharpMoneyDetector",
    "api.services.alert_service.send_sharp_money_alert",
]


class TestScanMarketForAlerts:
    def _setup(self):
        self.patches = [patch(p) for p in PATCHES_MARKET]
        self.mocks = [p.__enter__() for p in self.patches]
        self.mock_detector_class = self.mocks[0]
        self.mock_send_alert = self.mocks[1]

        self.mock_detector = self.mock_detector_class.return_value
        self.svc = AlertService()

    def _teardown(self):
        for p in self.patches:
            p.__exit__(None, None, None)

    def test_skips_games_with_no_actionable_signals(self):
        self._setup()
        self.mock_detector.analyze_full_game.return_value = [
            make_mock_signal(is_actionable=False),
        ]
        run_async(self.svc.scan_market_for_alerts({"games": [{"game_id": "G1"}]}))
        self._teardown()

        assert len(self.svc.alert_history) == 0
        self.mock_send_alert.assert_not_called()

    def test_generates_alert_for_actionable_signal(self):
        self._setup()
        self.mock_detector.analyze_full_game.return_value = [
            make_mock_signal(is_actionable=True),
        ]
        run_async(self.svc.scan_market_for_alerts({"games": [{"game_id": "G1"}]}))
        self._teardown()

        assert len(self.svc.alert_history) == 1
        self.mock_send_alert.assert_awaited_once()

    def test_multiple_games_multiple_signals(self):
        self._setup()

        def side_effect(**kwargs):
            gid = kwargs["game_id"]
            if gid == "G1":
                return [make_mock_signal(game_id="G1", is_actionable=True)]
            elif gid == "G2":
                return [
                    make_mock_signal(game_id="G2", team_id="BOS", is_actionable=True),
                    make_mock_signal(game_id="G2", team_id="NYY", is_actionable=False),
                ]
            return []

        self.mock_detector.analyze_full_game.side_effect = side_effect

        run_async(
            self.svc.scan_market_for_alerts({"games": [{"game_id": "G1"}, {"game_id": "G2"}]})
        )
        self._teardown()

        assert len(self.svc.alert_history) == 2
        assert self.mock_send_alert.await_count == 2

    def test_alert_details_match_signal(self):
        self._setup()
        sig = make_mock_signal(
            game_id="G-DETAIL",
            team_id="LAD",
            signal_type="RLM",
            confidence=0.72,
            discrepancy=0.18,
            line_movement=10,
            ticket_pct=65.0,
            money_pct=47.0,
            is_actionable=True,
        )
        self.mock_detector.analyze_full_game.return_value = [sig]

        run_async(self.svc.scan_market_for_alerts({"games": [{"game_id": "G-DETAIL"}]}))
        self._teardown()

        alert = self.svc.alert_history[0]
        assert alert["game_id"] == "G-DETAIL"
        assert alert["team_id"] == "LAD"
        assert alert["signal_type"] == "RLM"
        assert alert["confidence"] == 0.72
        assert alert["details"]["discrepancy"] == 0.18
        assert alert["details"]["line_movement"] == 10
        assert alert["details"]["ticket_pct"] == 65.0
        assert alert["details"]["money_pct"] == 47.0
        assert "timestamp" in alert

    def test_send_alert_called_with_correct_args(self):
        self._setup()
        sig = make_mock_signal(game_id="G-ARGS", team_id="HOU", signal_type="BOTH", confidence=0.91)
        self.mock_detector.analyze_full_game.return_value = [sig]

        run_async(self.svc.scan_market_for_alerts({"games": [{"game_id": "G-ARGS"}]}))
        self._teardown()

        self.mock_send_alert.assert_awaited_once_with(
            game_id="G-ARGS",
            team_id="HOU",
            signal_type="BOTH",
            confidence=0.91,
            details=ANY,
        )

    def test_no_games_no_signals(self):
        self._setup()
        run_async(self.svc.scan_market_for_alerts({"games": []}))
        self._teardown()

        assert self.svc.alert_history == []
        self.mock_detector.analyze_full_game.assert_not_called()
        self.mock_send_alert.assert_not_called()

    def test_market_data_missing_games_key(self):
        self._setup()
        run_async(self.svc.scan_market_for_alerts({}))
        self._teardown()

        assert self.svc.alert_history == []

    def test_detector_analyze_full_game_receives_correct_args(self):
        self._setup()
        self.mock_detector.analyze_full_game.return_value = []

        run_async(
            self.svc.scan_market_for_alerts(
                {
                    "games": [
                        {
                            "game_id": "G-2026",
                            "home_team_id": "NYY",
                            "away_team_id": "BOS",
                            "sportsbook": "FanDuel",
                            "home_ticket_pct": 70.0,
                            "home_money_pct": 40.0,
                            "home_moneyline_open": -140,
                            "home_moneyline_close": -125,
                        }
                    ]
                }
            )
        )
        self._teardown()

        self.mock_detector.analyze_full_game.assert_called_once_with(
            game_id="G-2026",
            home_team="NYY",
            away_team="BOS",
            sportsbook="FanDuel",
            timestamp=ANY,
            home_ticket_pct=70.0,
            home_money_pct=40.0,
            home_line_open=-140,
            home_line_current=-125,
        )


# ============================================================================
# Tests for scan_ev_alerts
# ============================================================================

PATCHES_EV = [
    "risk.ev_calculator.EVCalculator",
    "api.services.alert_service.send_ev_alert",
]


class TestScanEVAlerts:
    def _setup(self):
        self.patches = [patch(p) for p in PATCHES_EV]
        self.mocks = [p.__enter__() for p in self.patches]
        self.mock_calc_class = self.mocks[0]
        self.mock_send_ev = self.mocks[1]

        self.mock_calc = self.mock_calc_class.return_value
        self.svc = AlertService()

    def _teardown(self):
        for p in self.patches:
            p.__exit__(None, None, None)

    def test_sends_alert_for_each_bet(self):
        self._setup()
        self.mock_calc.evaluate_moneyline.return_value = [
            make_mock_bet(game_id="G1", team="NYY"),
            make_mock_bet(game_id="G1", team="BOS"),
        ]

        run_async(self.svc.scan_ev_alerts([{"game_id": "G1"}]))
        self._teardown()

        assert self.mock_send_ev.await_count == 2

    def test_no_bets_no_alerts(self):
        self._setup()
        self.mock_calc.evaluate_moneyline.return_value = []

        run_async(self.svc.scan_ev_alerts([{"game_id": "G1"}]))
        self._teardown()

        self.mock_send_ev.assert_not_called()

    def test_send_ev_alert_correct_args(self):
        self._setup()
        self.mock_calc.evaluate_moneyline.return_value = [
            make_mock_bet(game_id="G-EV", team="LAD", odds=+150, edge=0.05, kelly_fraction=0.03),
        ]

        run_async(self.svc.scan_ev_alerts([{"game_id": "G-EV"}]))
        self._teardown()

        self.mock_send_ev.assert_awaited_once_with(
            game_id="G-EV",
            team="LAD",
            odds=+150,
            edge=0.05,
            kelly=0.03,
        )

    def test_calculator_receives_correct_args(self):
        self._setup()
        self.mock_calc.evaluate_moneyline.return_value = []

        run_async(
            self.svc.scan_ev_alerts(
                [
                    {
                        "game_id": "G-CALC",
                        "home_team": "NYY",
                        "away_team": "BOS",
                        "home_win_prob": 0.58,
                        "away_win_prob": 0.42,
                        "home_odds": -130,
                        "away_odds": +110,
                    }
                ]
            )
        )
        self._teardown()

        self.mock_calc.evaluate_moneyline.assert_called_once_with(
            game_id="G-CALC",
            home_team="NYY",
            away_team="BOS",
            home_odds=-130,
            away_odds=+110,
            home_real_prob=0.58,
            away_real_prob=0.42,
        )

    def test_multiple_simulations(self):
        self._setup()

        def side_effect(**kwargs):
            gid = kwargs["game_id"]
            if gid == "G1":
                return [make_mock_bet(game_id="G1", team="NYY")]
            return [make_mock_bet(game_id=gid, team="BOS")]

        self.mock_calc.evaluate_moneyline.side_effect = side_effect

        run_async(
            self.svc.scan_ev_alerts(
                [
                    {"game_id": "G1"},
                    {"game_id": "G2"},
                    {"game_id": "G3"},
                ]
            )
        )
        self._teardown()

        assert self.mock_calc.evaluate_moneyline.call_count == 3
        assert self.mock_send_ev.await_count == 3

    def test_uses_defaults_when_keys_missing(self):
        self._setup()
        self.mock_calc.evaluate_moneyline.return_value = []

        run_async(self.svc.scan_ev_alerts([{}]))
        self._teardown()

        self.mock_calc.evaluate_moneyline.assert_called_once_with(
            game_id="",
            home_team="",
            away_team="",
            home_odds=0,
            away_odds=0,
            home_real_prob=0.5,
            away_real_prob=0.5,
        )


# ============================================================================
# Tests for continuous_scan
# ============================================================================


class TestContinuousScan:
    def test_loops_and_calls_scan_market(self):
        svc = AlertService()
        with patch.object(svc, "scan_market_for_alerts") as mock_scan:
            with patch("api.services.alert_service.asyncio.sleep") as mock_sleep:
                real_now = datetime.now()
                call_count = [0]

                def mock_now():
                    call_count[0] += 1
                    if call_count[0] >= 3:
                        return real_now + timedelta(hours=4)
                    return real_now

                with patch("api.services.alert_service.datetime") as mock_dt:
                    mock_dt.now = mock_now
                    run_async(svc.continuous_scan(interval_seconds=1, duration_minutes=180))

        assert mock_scan.await_count >= 1
        assert mock_sleep.await_count >= 1

    def test_respects_interval(self):
        svc = AlertService()
        with patch.object(svc, "scan_market_for_alerts") as mock_scan:
            mock_scan.return_value = None
            with patch("api.services.alert_service.asyncio.sleep") as mock_sleep:
                real_now = datetime.now()
                call_count = [0]

                def mock_now():
                    call_count[0] += 1
                    if call_count[0] >= 3:
                        return real_now + timedelta(hours=4)
                    return real_now

                with patch("api.services.alert_service.datetime") as mock_dt:
                    mock_dt.now = mock_now
                    run_async(svc.continuous_scan(interval_seconds=30, duration_minutes=180))

        mock_sleep.assert_awaited_with(30)

    def test_logs_error_on_failure_and_continues(self):
        svc = AlertService()
        with patch.object(svc, "scan_market_for_alerts") as mock_scan:
            mock_scan.side_effect = ValueError("scan failed")
            with patch("api.services.alert_service.asyncio.sleep") as mock_sleep:
                real_now = datetime.now()
                call_count = [0]

                def mock_now():
                    call_count[0] += 1
                    if call_count[0] >= 3:
                        return real_now + timedelta(hours=4)
                    return real_now

                with patch("api.services.alert_service.datetime") as mock_dt:
                    mock_dt.now = mock_now
                    run_async(svc.continuous_scan(interval_seconds=1, duration_minutes=180))

        assert mock_sleep.await_count >= 1
        assert mock_scan.await_count >= 1

    def test_zero_duration_ends_immediately(self):
        svc = AlertService()
        with patch.object(svc, "scan_market_for_alerts") as mock_scan:
            with patch("api.services.alert_service.asyncio.sleep") as mock_sleep:
                run_async(svc.continuous_scan(interval_seconds=60, duration_minutes=0))

        mock_scan.assert_not_called()
        mock_sleep.assert_not_called()


# ============================================================================
# Tests for get_recent_alerts
# ============================================================================


class TestGetRecentAlerts:
    def _make_alerts(self, confidences):
        svc = AlertService()
        for i, c in enumerate(confidences):
            svc.alert_history.append(
                {
                    "game_id": f"G{i}",
                    "team_id": "T",
                    "signal_type": "SHARP_MONEY",
                    "confidence": c,
                    "timestamp": datetime.now(),
                    "details": {},
                }
            )
        return svc

    def test_filters_by_min_confidence(self):
        svc = self._make_alerts([0.9, 0.5, 0.7, 0.3])
        result = svc.get_recent_alerts(min_confidence=0.6)
        assert len(result) == 2
        assert all(a["confidence"] >= 0.6 for a in result)

    def test_returns_last_n_alerts(self):
        svc = self._make_alerts([0.9, 0.8, 0.7, 0.6])
        result = svc.get_recent_alerts(limit=2)
        assert len(result) == 2
        assert result[0]["confidence"] == 0.7
        assert result[1]["confidence"] == 0.6

    def test_returns_all_when_limit_exceeds_count(self):
        svc = self._make_alerts([0.9, 0.8])
        result = svc.get_recent_alerts(limit=50)
        assert len(result) == 2

    def test_empty_history_returns_empty(self):
        svc = AlertService()
        assert svc.get_recent_alerts() == []

    def test_negative_confidence_returns_all(self):
        svc = self._make_alerts([0.1, 0.2, 0.3])
        result = svc.get_recent_alerts(min_confidence=-1.0)
        assert len(result) == 3

    def test_does_not_mutate_history(self):
        svc = self._make_alerts([0.9, 0.8])
        original_len = len(svc.alert_history)
        svc.get_recent_alerts(limit=1)
        assert len(svc.alert_history) == original_len


# ============================================================================
# Tests for get_unread_count
# ============================================================================


class TestGetUnreadCount:
    def test_all_read_returns_zero(self):
        svc = AlertService()
        svc.alert_history = [
            {"is_read": True},
            {"is_read": True},
        ]
        assert svc.get_unread_count() == 0

    def test_counts_unread_only(self):
        svc = AlertService()
        svc.alert_history = [
            {"is_read": True},
            {"is_read": False},
            {"is_read": False},
            {},
        ]
        assert svc.get_unread_count() == 3

    def test_empty_history_returns_zero(self):
        assert AlertService().get_unread_count() == 0

    def test_missing_is_read_key_counts_as_unread(self):
        svc = AlertService()
        svc.alert_history = [{"game_id": "G1"}, {"is_read": False}]
        assert svc.get_unread_count() == 2


# ============================================================================
# Tests for mark_read
# ============================================================================


class TestMarkRead:
    def test_mark_all_read_when_no_id(self):
        svc = AlertService()
        svc.alert_history = [
            {"is_read": False},
            {"is_read": False},
            {"is_read": True},
        ]
        svc.mark_read()
        assert all(a["is_read"] for a in svc.alert_history)

    def test_mark_specific_alert_by_index(self):
        svc = AlertService()
        svc.alert_history = [
            {"is_read": False},
            {"is_read": False},
            {"is_read": False},
        ]
        svc.mark_read(alert_id=1)
        assert svc.alert_history[0]["is_read"] is False
        assert svc.alert_history[1]["is_read"] is True
        assert svc.alert_history[2]["is_read"] is False

    def test_invalid_index_ignored(self):
        svc = AlertService()
        svc.alert_history = [{"is_read": False}]
        svc.mark_read(alert_id=99)
        assert svc.alert_history[0]["is_read"] is False

    def test_negative_index_ignored(self):
        svc = AlertService()
        svc.alert_history = [{"is_read": False}]
        svc.mark_read(alert_id=-1)
        assert svc.alert_history[0]["is_read"] is False

    def test_mark_already_read_is_idempotent(self):
        svc = AlertService()
        svc.alert_history = [{"is_read": True}]
        svc.mark_read(alert_id=0)
        assert svc.alert_history[0]["is_read"] is True

    def test_empty_history_no_error(self):
        svc = AlertService()
        svc.mark_read()
        svc.mark_read(alert_id=0)
        # No exception = pass

    def test_mark_read_adds_key_when_missing(self):
        svc = AlertService()
        svc.alert_history = [{}]
        svc.mark_read(alert_id=0)
        assert svc.alert_history[0]["is_read"] is True
