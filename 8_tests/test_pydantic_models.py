"""Tests para api/models/pydantic_models.py (198 líneas, 15 modelos)."""

import pytest
import sys, os
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.models.pydantic_models import (
    SimulationRequest, SimulationResponse,
    EVRequest, EVResponse, BetSlipItem, BetSlipRequest, BetSlipResponse,
    PropRequest, PropResponse,
    AlertResponse, AlertListResponse,
    PlayerStatsResponse, GamePreviewResponse,
    BankrollResponse, ExposureResponse,
)


# ============================================================================
# SimulationRequest
# ============================================================================

class TestSimulationRequest:
    def test_valid_request(self):
        req = SimulationRequest(
            game_id="2026-05-20-NYY-BOS",
            home_team_id="NYY",
            away_team_id="BOS",
            home_pitcher_id=1,
            away_pitcher_id=2,
            n_iterations=10000,
        )
        assert req.game_id == "2026-05-20-NYY-BOS"
        assert req.n_iterations == 10000

    def test_default_iterations(self):
        req = SimulationRequest(
            game_id="G1", home_team_id="A", away_team_id="B",
            home_pitcher_id=1, away_pitcher_id=2,
        )
        assert req.n_iterations == 10000

    def test_min_iterations(self):
        req = SimulationRequest(
            game_id="G1", home_team_id="A", away_team_id="B",
            home_pitcher_id=1, away_pitcher_id=2,
            n_iterations=1000,
        )
        assert req.n_iterations == 1000

    def test_max_iterations(self):
        req = SimulationRequest(
            game_id="G1", home_team_id="A", away_team_id="B",
            home_pitcher_id=1, away_pitcher_id=2,
            n_iterations=100000,
        )
        assert req.n_iterations == 100000

    def test_iterations_below_min(self):
        with pytest.raises(ValueError, match="Minimum 1000"):
            SimulationRequest(
                game_id="G1", home_team_id="A", away_team_id="B",
                home_pitcher_id=1, away_pitcher_id=2,
                n_iterations=999,
            )

    def test_iterations_above_max(self):
        with pytest.raises(ValueError, match="Maximum 100000"):
            SimulationRequest(
                game_id="G1", home_team_id="A", away_team_id="B",
                home_pitcher_id=1, away_pitcher_id=2,
                n_iterations=100001,
            )

    def test_default_lineups(self):
        req = SimulationRequest(
            game_id="G1", home_team_id="A", away_team_id="B",
            home_pitcher_id=1, away_pitcher_id=2,
        )
        assert req.home_lineup == []
        assert req.away_lineup == []

    def test_with_lineups(self):
        req = SimulationRequest(
            game_id="G1", home_team_id="A", away_team_id="B",
            home_pitcher_id=1, away_pitcher_id=2,
            home_lineup=[10, 11, 12],
            away_lineup=[20, 21, 22],
        )
        assert req.home_lineup == [10, 11, 12]
        assert req.away_lineup == [20, 21, 22]

    def test_default_park_factor(self):
        req = SimulationRequest(
            game_id="G1", home_team_id="A", away_team_id="B",
            home_pitcher_id=1, away_pitcher_id=2,
        )
        assert req.park_factor_hr == 1.0


# ============================================================================
# SimulationResponse
# ============================================================================

class TestSimulationResponse:
    def test_valid_response(self):
        resp = SimulationResponse(
            game_id="G1",
            home_win_prob=0.58,
            away_win_prob=0.42,
            mean_home_runs=4.5,
            mean_away_runs=3.8,
            std_home_runs=2.1,
            std_away_runs=1.9,
            extra_innings_prob=0.08,
            walkoff_prob=0.03,
            n_iterations=10000,
            home_run_distribution={"0": 0.1, "1": 0.2},
            away_run_distribution={"0": 0.15, "1": 0.25},
            computed_at=datetime(2026, 5, 20, 12, 0, 0),
        )
        assert resp.home_win_prob == 0.58
        assert resp.home_run_distribution["0"] == 0.1


# ============================================================================
# EVRequest
# ============================================================================

class TestEVRequest:
    def test_valid_request(self):
        req = EVRequest(
            game_id="G1", home_odds=-110, away_odds=-110,
            home_real_prob=0.55, away_real_prob=0.45,
        )
        assert req.game_id == "G1"

    def test_positive_odds(self):
        req = EVRequest(
            game_id="G1", home_odds=+150, away_odds=-130,
            home_real_prob=0.55, away_real_prob=0.45,
        )
        assert req.home_odds == 150


# ============================================================================
# EVResponse
# ============================================================================

class TestEVResponse:
    def test_minimal_response(self):
        resp = EVResponse(game_id="G1")
        assert resp.bets == []

    def test_with_bets(self):
        resp = EVResponse(
            game_id="G1",
            bets=[{"team": "NYY", "edge": 0.05}],
        )
        assert len(resp.bets) == 1
        assert resp.bets[0]["team"] == "NYY"

    def test_optional_home_away_team(self):
        resp = EVResponse(game_id="G1", home_team="NYY", away_team="BOS")
        assert resp.home_team == "NYY"
        assert resp.away_team == "BOS"


# ============================================================================
# BetSlipItem
# ============================================================================

class TestBetSlipItem:
    def test_valid_item(self):
        item = BetSlipItem(
            game_id="G1", team="NYY", market_type="MONEYLINE",
            odds=-110, stake=100.0, edge=0.05, kelly_fraction=0.02,
        )
        assert item.odds == -110
        assert item.stake == 100.0


# ============================================================================
# BetSlipRequest
# ============================================================================

class TestBetSlipRequest:
    def test_valid_request(self):
        req = BetSlipRequest(bets=[
            BetSlipItem(
                game_id="G1", team="NYY", market_type="MONEYLINE",
                odds=-110, stake=100.0, edge=0.05, kelly_fraction=0.02,
            ),
        ])
        assert len(req.bets) == 1

    def test_empty_bets(self):
        req = BetSlipRequest(bets=[])
        assert req.bets == []


# ============================================================================
# BetSlipResponse
# ============================================================================

class TestBetSlipResponse:
    def test_approved(self):
        resp = BetSlipResponse(approved=True, total_stake=100.0)
        assert resp.violations == []

    def test_rejected(self):
        resp = BetSlipResponse(
            approved=False, total_stake=500.0,
            violations=["Exceeds max stake"],
        )
        assert len(resp.violations) == 1


# ============================================================================
# PropRequest
# ============================================================================

class TestPropRequest:
    def test_valid_prop(self):
        for pt in ("STRIKEOUTS", "HITS", "HR", "RBIS", "WALKS"):
            req = PropRequest(
                player_id=1, prop_type=pt, line_value=1.5,
                over_odds=+200, under_odds=-250,
                features={"exit_velo": 95.0},
            )
            assert req.prop_type == pt

    def test_invalid_prop_type(self):
        with pytest.raises(ValueError, match="pattern"):
            PropRequest(
                player_id=1, prop_type="INVALID", line_value=1.5,
                over_odds=+200, under_odds=-250,
                features={},
            )

    def test_features_dict(self):
        req = PropRequest(
            player_id=1, prop_type="HR", line_value=1.5,
            over_odds=+200, under_odds=-250,
            features={"exit_velo": 95.0, "launch_angle": 25.0},
        )
        assert req.features["exit_velo"] == 95.0


# ============================================================================
# PropResponse
# ============================================================================

class TestPropResponse:
    def test_valid_response(self):
        resp = PropResponse(
            player_name="Player_1",
            prop_type="HR",
            line_value=1.5,
            predicted_mean=0.8,
            prob_over=0.35,
            prob_under=0.65,
            ev_over=0.05,
            ev_under=-0.15,
            recommendation="over",
            kelly_fraction=0.01,
        )
        assert resp.recommendation == "over"
        assert resp.prop_type == "HR"


# ============================================================================
# AlertResponse
# ============================================================================

class TestAlertResponse:
    def test_valid_alert(self):
        alert = AlertResponse(
            alert_id=1, game_id="G1", team_id="NYY",
            signal_type="sharp_money", confidence=0.85,
            message="Test", created_at=datetime.now(),
        )
        assert alert.is_read is False
        assert alert.alert_id == 1

    def test_read_alert(self):
        alert = AlertResponse(
            alert_id=2, game_id="G1", team_id="NYY",
            signal_type="ev_positive", confidence=0.9,
            message="EV+ found", created_at=datetime.now(),
            is_read=True,
        )
        assert alert.is_read is True


# ============================================================================
# AlertListResponse
# ============================================================================

class TestAlertListResponse:
    def test_valid_response(self):
        resp = AlertListResponse(
            alerts=[
                AlertResponse(
                    alert_id=1, game_id="G1", team_id="NYY",
                    signal_type="sharp_money", confidence=0.85,
                    message="Test", created_at=datetime.now(),
                ),
            ],
            total=1,
            unread_count=1,
        )
        assert resp.total == 1
        assert resp.unread_count == 1
        assert len(resp.alerts) == 1


# ============================================================================
# PlayerStatsResponse
# ============================================================================

class TestPlayerStatsResponse:
    def test_required_fields_only(self):
        stats = PlayerStatsResponse(
            player_id=123, full_name="Aaron Judge", team_id="NYY",
        )
        assert stats.position is None

    def test_all_fields(self):
        stats = PlayerStatsResponse(
            player_id=123, full_name="Aaron Judge", team_id="NYY",
            position="RF", bats="R", throws="R",
            woba_30d=0.412, fip_30d=3.20,
            fatigue_score=0.95,
        )
        assert stats.woba_30d == 0.412
        assert stats.fatigue_score == 0.95

    def test_partial_stats(self):
        stats = PlayerStatsResponse(
            player_id=1, full_name="Player", team_id="NYY",
            avg_velo_30d=95.5, whiff_pct_30d=0.25,
        )
        assert stats.avg_velo_30d == 95.5
        assert stats.woba_30d is None


# ============================================================================
# GamePreviewResponse
# ============================================================================

class TestGamePreviewResponse:
    def test_required_fields(self):
        preview = GamePreviewResponse(
            game_id="2026-05-20-NYY-BOS",
            game_date="2026-05-20",
            home_team="NYY",
            away_team="BOS",
        )
        assert preview.sharp_money_flag is False
        assert preview.rlm_flag is False

    def test_all_fields(self):
        preview = GamePreviewResponse(
            game_id="G1", game_date="2026-05-20",
            home_team="NYY", away_team="BOS",
            home_pitcher_id=1, away_pitcher_id=2,
            status="SCHEDULED", start_time="19:05",
            home_moneyline=-150, away_moneyline=+130,
            total=8.5, home_win_prob=0.58, away_win_prob=0.42,
            sharp_money_flag=True, rlm_flag=True,
        )
        assert preview.sharp_money_flag is True
        assert preview.home_moneyline == -150


# ============================================================================
# BankrollResponse
# ============================================================================

class TestBankrollResponse:
    def test_valid_response(self):
        resp = BankrollResponse(
            initial=10000, current=12500, peak=13000,
            drawdown_pct=3.85, total_wagered=5000,
            total_profit=2500, roi_pct=50,
            total_return_pct=150, sharpe_ratio=1.5,
            bet_count=42, updated_at=datetime.now(),
        )
        assert resp.current == 12500
        assert resp.bet_count == 42


# ============================================================================
# ExposureResponse
# ============================================================================

class TestExposureResponse:
    def test_approved(self):
        resp = ExposureResponse(
            approved=True, violations=[], current_bankroll=10000,
            stake=100, stake_pct=1.0,
        )
        assert resp.approved is True

    def test_violations(self):
        resp = ExposureResponse(
            approved=False, violations=["Exceeds max"],
            current_bankroll=10000, stake=5000, stake_pct=50.0,
        )
        assert resp.approved is False
        assert "Exceeds max" in resp.violations
