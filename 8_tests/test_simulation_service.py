"""Tests para api/services/simulation_service.py (SimulationService)."""

import pytest
import asyncio
import sys, os
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.services.simulation_service import SimulationService
from api.models.pydantic_models import SimulationRequest, SimulationResponse


SAMPLE_REQUEST = SimulationRequest(
    game_id="2026-05-20-NYY-BOS",
    home_team_id="NYY",
    away_team_id="BOS",
    home_pitcher_id=1,
    away_pitcher_id=2,
    park_factor_hr=1.05,
    n_iterations=10000,
)


def make_mock_result(**overrides):
    defaults = {
        "home_win_prob": 0.55,
        "away_win_prob": 0.45,
        "mean_home_runs": 4.5,
        "mean_away_runs": 3.8,
        "std_home_runs": 2.1,
        "std_away_runs": 1.9,
        "extra_innings_prob": 0.08,
        "walkoff_prob": 0.03,
        "n_iterations": 10000,
        "home_run_distribution": {0: 0.1, 1: 0.2, 2: 0.3},
        "away_run_distribution": {0: 0.15, 1: 0.25, 2: 0.2},
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def run_async(coro):
    return asyncio.run(coro)


_MOCK_CONFIG = MagicMock()
_MOCK_CONFIG.DATABASE_URL = "sqlite://"
sys.modules["config"] = _MOCK_CONFIG

PATCHES_SRC = [
    "prediction.monte_carlo_simulator.MonteCarloMLBSimulator",
    "prediction.player_state_builder._fetch_team_lineup",
    "prediction.player_state_builder._fetch_pitcher_state",
    "prediction.player_state_builder._build_placeholder_lineup",
    "api.database.get_engine",
]


class TestCache:
    def test_init_cache_empty(self):
        svc = SimulationService()
        assert svc.cache == {}

    def test_get_cached_returns_none(self):
        svc = SimulationService()
        assert svc.get_cached("nonexistent") is None

    def test_get_cached_returns_response(self):
        svc = SimulationService()
        resp = SimulationResponse(
            game_id="G1",
            home_win_prob=0.5,
            away_win_prob=0.5,
            mean_home_runs=4.0,
            mean_away_runs=4.0,
            std_home_runs=2.0,
            std_away_runs=2.0,
            extra_innings_prob=0.0,
            walkoff_prob=0.0,
            n_iterations=10000,
            home_run_distribution={},
            away_run_distribution={},
            computed_at=datetime.now(),
        )
        svc.cache["G1"] = resp
        assert svc.get_cached("G1") is resp


class TestRunSimulation:
    def _run(self, **patch_overrides):
        return run_async(self.svc.run_simulation(SAMPLE_REQUEST))

    def _setup(self):
        self.patches = [
            patch(PATCHES_SRC[0]),
            patch(PATCHES_SRC[1]),
            patch(PATCHES_SRC[2]),
            patch(PATCHES_SRC[3]),
            patch(PATCHES_SRC[4]),
        ]
        self.mocks = [p.__enter__() for p in self.patches]
        self.mock_sim_class = self.mocks[0]
        self.mock_fetch_lineup = self.mocks[1]
        self.mock_fetch_pitcher = self.mocks[2]
        self.mock_placeholder = self.mocks[3]
        self.mock_engine = self.mocks[4]

        self.mock_sim = self.mock_sim_class.return_value
        self.mock_sim.run_simulation.return_value = make_mock_result()
        self.mock_fetch_lineup.return_value = [MagicMock() for _ in range(9)]
        self.mock_fetch_pitcher.return_value = MagicMock()
        self.svc = SimulationService()

    def _teardown(self):
        for p in self.patches:
            p.__exit__(None, None, None)

    def test_returns_simulation_response(self):
        self._setup()
        response = self._run()
        self._teardown()

        assert isinstance(response, SimulationResponse)
        assert response.game_id == "2026-05-20-NYY-BOS"
        assert response.home_win_prob == 0.55
        assert response.away_win_prob == 0.45
        assert response.mean_home_runs == 4.5
        assert response.mean_away_runs == 3.8
        assert response.std_home_runs == 2.1
        assert response.std_away_runs == 1.9
        assert response.extra_innings_prob == 0.08
        assert response.walkoff_prob == 0.03
        assert response.n_iterations == 10000

    def test_caches_result(self):
        self._setup()
        response = self._run()
        cached = self.svc.get_cached("2026-05-20-NYY-BOS")
        self._teardown()

        assert cached is response
        assert cached.home_win_prob == 0.55

    def test_uses_seed_42(self):
        self._setup()
        self._run()
        self._teardown()

        self.mock_sim_class.assert_called_once_with(seed=42)

    def test_run_simulation_called_with_correct_args(self):
        self._setup()
        self._run()
        self._teardown()

        call_kwargs = self.mock_sim.run_simulation.call_args.kwargs
        assert call_kwargs["park_factor_hr"] == 1.05
        assert call_kwargs["n_iterations"] == 10000
        assert callable(call_kwargs["progress_callback"])

    def test_computed_at_is_datetime(self):
        self._setup()
        response = self._run()
        self._teardown()

        assert isinstance(response.computed_at, datetime)


class TestLineupPadding:
    def _setup(self, home_len=9, away_len=9):
        self.patches = [
            patch(PATCHES_SRC[0]),
            patch(PATCHES_SRC[1]),
            patch(PATCHES_SRC[2]),
            patch(PATCHES_SRC[3]),
            patch(PATCHES_SRC[4]),
        ]
        self.mocks = [p.__enter__() for p in self.patches]
        self.mock_sim_class = self.mocks[0]
        self.mock_fetch_lineup = self.mocks[1]
        self.mock_fetch_pitcher = self.mocks[2]
        self.mock_placeholder = self.mocks[3]
        self.mock_engine = self.mocks[4]

        self.mock_sim = self.mock_sim_class.return_value
        self.mock_sim.run_simulation.return_value = make_mock_result()
        self.mock_fetch_lineup.side_effect = [
            [MagicMock() for _ in range(home_len)],
            [MagicMock() for _ in range(away_len)],
        ]
        self.mock_fetch_pitcher.return_value = MagicMock()
        self.svc = SimulationService()

    def _teardown(self):
        for p in self.patches:
            p.__exit__(None, None, None)

    def test_pads_home_lineup_when_short(self):
        self._setup(home_len=5, away_len=9)
        self.mock_placeholder.return_value = [MagicMock() for _ in range(4)]
        run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        self.mock_placeholder.assert_called_once_with("NYY", 0.310, 4)

    def test_pads_away_lineup_when_short(self):
        self._setup(home_len=9, away_len=3)
        self.mock_placeholder.return_value = [MagicMock() for _ in range(6)]
        run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        self.mock_placeholder.assert_called_once_with("BOS", 0.310, 6)

    def test_no_padding_when_both_full(self):
        self._setup(home_len=9, away_len=9)
        run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        self.mock_placeholder.assert_not_called()

    def test_pads_both_when_both_short(self):
        self._setup(home_len=4, away_len=2)
        self.mock_placeholder.side_effect = [
            [MagicMock() for _ in range(5)],
            [MagicMock() for _ in range(7)],
        ]
        run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        assert self.mock_placeholder.call_count == 2
        self.mock_placeholder.assert_any_call("NYY", 0.310, 5)
        self.mock_placeholder.assert_any_call("BOS", 0.310, 7)


class TestDatabaseInteraction:
    def _setup(self):
        self.patches = [
            patch(PATCHES_SRC[0]),
            patch(PATCHES_SRC[1]),
            patch(PATCHES_SRC[2]),
            patch(PATCHES_SRC[3]),
            patch(PATCHES_SRC[4]),
        ]
        self.mocks = [p.__enter__() for p in self.patches]
        self.mock_sim_class = self.mocks[0]
        self.mock_fetch_lineup = self.mocks[1]
        self.mock_fetch_pitcher = self.mocks[2]
        self.mock_placeholder = self.mocks[3]
        self.mock_engine = self.mocks[4]

        self.mock_sim = self.mock_sim_class.return_value
        self.mock_sim.run_simulation.return_value = make_mock_result()
        self.mock_fetch_lineup.return_value = [MagicMock() for _ in range(9)]
        self.mock_fetch_pitcher.return_value = MagicMock()
        self.svc = SimulationService()

    def _teardown(self):
        for p in self.patches:
            p.__exit__(None, None, None)

    def test_fetches_lineups_with_correct_args(self):
        self._setup()
        _MOCK_CONFIG.DATABASE_URL = "sqlite://"
        run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        engine = self.mock_engine.return_value
        self.mock_fetch_lineup.assert_any_call(engine, "NYY", "2026-05-20")
        self.mock_fetch_lineup.assert_any_call(engine, "BOS", "2026-05-20")

    def test_fetches_pitchers_with_correct_args(self):
        self._setup()
        _MOCK_CONFIG.DATABASE_URL = "sqlite://"
        run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        engine = self.mock_engine.return_value
        self.mock_fetch_pitcher.assert_any_call(engine, 1, "2026-05-20")
        self.mock_fetch_pitcher.assert_any_call(engine, 2, "2026-05-20")


class TestRunDistributionKeys:
    def _setup(self, **overrides):
        self.patches = [
            patch(PATCHES_SRC[0]),
            patch(PATCHES_SRC[1]),
            patch(PATCHES_SRC[2]),
            patch(PATCHES_SRC[3]),
            patch(PATCHES_SRC[4]),
        ]
        self.mocks = [p.__enter__() for p in self.patches]
        self.mock_sim_class = self.mocks[0]
        self.mock_fetch_lineup = self.mocks[1]
        self.mock_fetch_pitcher = self.mocks[2]
        self.mock_placeholder = self.mocks[3]
        self.mock_engine = self.mocks[4]

        self.mock_sim = self.mock_sim_class.return_value
        self.mock_sim.run_simulation.return_value = make_mock_result(**overrides)
        self.mock_fetch_lineup.return_value = [MagicMock() for _ in range(9)]
        self.mock_fetch_pitcher.return_value = MagicMock()
        self.svc = SimulationService()

    def _teardown(self):
        for p in self.patches:
            p.__exit__(None, None, None)

    def test_home_run_distribution_keys_are_strings(self):
        self._setup(home_run_distribution={0: 0.1, 1: 0.2, 5: 0.05})
        response = run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        assert all(isinstance(k, str) for k in response.home_run_distribution)
        assert response.home_run_distribution["0"] == 0.1
        assert response.home_run_distribution["5"] == 0.05

    def test_away_run_distribution_keys_are_strings(self):
        self._setup(away_run_distribution={0: 0.2, 3: 0.1})
        response = run_async(self.svc.run_simulation(SAMPLE_REQUEST))
        self._teardown()

        assert all(isinstance(k, str) for k in response.away_run_distribution)
        assert response.away_run_distribution["3"] == 0.1
