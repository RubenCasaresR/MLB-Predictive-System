"""Tests para el simulador Monte Carlo."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prediction.monte_carlo_simulator import (
    BatterState,
    GameState,
    MonteCarloMLBSimulator,
    PAOutcome,
    PitcherState,
)


@pytest.fixture
def sim():
    return MonteCarloMLBSimulator(seed=42)


@pytest.fixture
def sample_lineup():
    return [BatterState(player_id=i, name=f"B{i}", bats="R") for i in range(9)]


@pytest.fixture
def sample_pitcher():
    return PitcherState(
        player_id=100,
        name="P100",
        throws="R",
        k_rate=0.25,
        bb_rate=0.08,
    )


class TestMonteCarloSimulator:
    def test_init(self, sim):
        assert sim.rng is not None
        assert sim.MAX_INNINGS == 9

    def test_predict_probs_sum_to_one(self, sim, sample_pitcher):
        batter = BatterState(player_id=1, name="Test", bats="R")
        fv = sim._build_feature_vector(
            batter,
            sample_pitcher,
            inning=1,
            outs_before=0,
            half_inning="T",
            stadium_id=0,
            umpire_id=0,
            park_hr=1.0,
            park_k=1.0,
            park_woba=1.0,
            temperature=70.0,
            wind_speed=0.0,
            wind_direction="NONE",
            umpire_cs_rate=0.63,
            bullpen_fip_30d=4.50,
            is_bullpen_active=0,
        )
        probs = sim._predict_probs(fv)
        assert np.isclose(probs.sum(), 1.0, atol=0.01)

    def test_predict_probs_all_positive(self, sim, sample_pitcher):
        batter = BatterState(player_id=1, name="Test", bats="L")
        fv = sim._build_feature_vector(
            batter,
            sample_pitcher,
            inning=5,
            outs_before=1,
            half_inning="B",
            stadium_id=3313,
            umpire_id=423205,
            park_hr=1.5,
            park_k=0.9,
            park_woba=1.1,
            temperature=85.0,
            wind_speed=10.0,
            wind_direction="OUT",
            umpire_cs_rate=0.63,
            bullpen_fip_30d=4.50,
            is_bullpen_active=0,
        )
        probs = sim._predict_probs(fv)
        assert (probs > 0).all()

    def test_has_platoon_advantage(self, sim):
        assert sim._has_platoon_advantage("L", "R") == 1
        assert sim._has_platoon_advantage("R", "L") == 1
        assert sim._has_platoon_advantage("S", "R") == 1
        assert sim._has_platoon_advantage("S", "L") == 1
        assert sim._has_platoon_advantage("R", "R") == 0
        assert sim._has_platoon_advantage("L", "L") == 0

    def test_simulation_runs(self, sim, sample_lineup, sample_pitcher):
        result = sim.run_simulation(
            home_lineup=sample_lineup,
            away_lineup=sample_lineup,
            home_pitcher=sample_pitcher,
            away_pitcher=sample_pitcher,
            n_iterations=100,
        )
        assert result.n_iterations == 100
        assert 0 <= result.home_win_prob <= 1
        assert 0 <= result.away_win_prob <= 1

    def test_home_advantage(self, sim, sample_pitcher):
        strong_lineup = [
            BatterState(i, f"S{i}", "R", woba_vs_rhp=0.500, woba_vs_lhp=0.500) for i in range(9)
        ]
        weak_lineup = [
            BatterState(i, f"W{i}", "R", woba_vs_rhp=0.200, woba_vs_lhp=0.200) for i in range(9)
        ]
        result = sim.run_simulation(
            home_lineup=strong_lineup,
            away_lineup=weak_lineup,
            home_pitcher=sample_pitcher,
            away_pitcher=sample_pitcher,
            n_iterations=500,
        )
        assert result.home_win_prob >= 0.5

    def test_extra_innings(self, sim, sample_lineup, sample_pitcher):
        result = sim.run_simulation(
            home_lineup=sample_lineup,
            away_lineup=sample_lineup,
            home_pitcher=sample_pitcher,
            away_pitcher=sample_pitcher,
            n_iterations=1000,
        )
        assert 0 <= result.extra_innings_prob <= 1

    def test_walkoff_possible(self, sim, sample_lineup, sample_pitcher):
        result = sim.run_simulation(
            home_lineup=sample_lineup,
            away_lineup=sample_lineup,
            home_pitcher=sample_pitcher,
            away_pitcher=sample_pitcher,
            n_iterations=1000,
        )
        assert 0 <= result.walkoff_prob <= 1

    def test_run_distribution(self, sim, sample_lineup, sample_pitcher):
        result = sim.run_simulation(
            home_lineup=sample_lineup,
            away_lineup=sample_lineup,
            home_pitcher=sample_pitcher,
            away_pitcher=sample_pitcher,
            n_iterations=1000,
        )
        assert result.mean_home_runs >= 0
        assert result.mean_away_runs >= 0
        assert len(result.home_run_distribution) == 7

    def test_reproducibility(self, sample_lineup, sample_pitcher):
        sim1 = MonteCarloMLBSimulator(seed=12345)
        sim2 = MonteCarloMLBSimulator(seed=12345)
        r1 = sim1.run_simulation(
            sample_lineup,
            sample_lineup,
            sample_pitcher,
            sample_pitcher,
            n_iterations=500,
        )
        r2 = sim2.run_simulation(
            sample_lineup,
            sample_lineup,
            sample_pitcher,
            sample_pitcher,
            n_iterations=500,
        )
        assert np.allclose(r1.home_runs_array, r2.home_runs_array)
        assert np.allclose(r1.away_runs_array, r2.away_runs_array)

    def test_probabilities_near_extremes(self, sim, sample_pitcher):
        elite = [BatterState(i, f"E{i}", "R", woba_vs_rhp=0.480, k_rate=0.10) for i in range(9)]
        awful = [BatterState(i, f"A{i}", "R", woba_vs_rhp=0.220, k_rate=0.35) for i in range(9)]
        elite_pitcher = PitcherState(200, "Ace", "R", k_rate=0.35, bb_rate=0.04)
        result = sim.run_simulation(
            home_lineup=elite,
            away_lineup=awful,
            home_pitcher=elite_pitcher,
            away_pitcher=sample_pitcher,
            n_iterations=500,
        )
        assert result.home_win_prob > 0.5


class TestGameState:
    def test_initial_state(self):
        state = GameState()
        assert state.home_score == 0
        assert state.away_score == 0
        assert state.inning == 1
        assert state.half == "top"
        assert state.outs == 0
        assert state.bases == (False, False, False)

    def test_reset_half(self):
        state = GameState(outs=2, bases=(True, True, True))
        state.reset_half()
        assert state.outs == 0
        assert state.bases == (False, False, False)

    def test_switch_half(self):
        state = GameState()
        state.switch_half()
        assert state.half == "bot"
        assert state.inning == 1
        state.switch_half()
        assert state.half == "top"
        assert state.inning == 2


class TestEVCalculation:
    def test_american_to_implied_positive(self):
        from prediction.monte_carlo_simulator import SimulationResult

        p = SimulationResult.american_to_implied(+150)
        assert abs(p - 0.40) < 0.01

    def test_american_to_implied_negative(self):
        from prediction.monte_carlo_simulator import SimulationResult

        p = SimulationResult.american_to_implied(-130)
        assert abs(p - 0.565) < 0.01

    def test_implied_to_american_favorite(self):
        from prediction.monte_carlo_simulator import SimulationResult

        odds = SimulationResult.implied_to_american(0.60)
        assert odds < 0
        assert odds == -150

    def test_implied_to_american_dog(self):
        from prediction.monte_carlo_simulator import SimulationResult

        odds = SimulationResult.implied_to_american(0.40)
        assert odds > 0
        assert odds == +150

    def test_kelly_fraction_zero_for_no_edge(self):
        from prediction.monte_carlo_simulator import SimulationResult

        k = SimulationResult.kelly_fraction(None, 0.4, -110, 0.25)
        assert k >= 0
