# =============================================================================
# simulation_service.py
# Servicio de simulación - wrappea Monte Carlo para la API
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime, date
import logging

from api.models.pydantic_models import SimulationRequest, SimulationResponse

logger = logging.getLogger(__name__)


def _parse_game_id_date(game_id: str) -> date:
    s = game_id[-6:]
    return date(2000 + int(s[0:2]), int(s[2:4]), int(s[4:6]))


class SimulationService:
    def __init__(self):
        self.cache: Dict[str, SimulationResponse] = {}
        logger.info("SimulationService initialized")

    async def run_simulation(self, request: SimulationRequest) -> SimulationResponse:
        from prediction.monte_carlo_simulator import MonteCarloMLBSimulator
        from prediction.player_state_builder import (
            _fetch_pitcher_state, _fetch_team_lineup, _build_placeholder_lineup,
        )
        from api.database import get_engine
        from sqlalchemy import text

        engine = get_engine()
        target_date = _parse_game_id_date(request.game_id)

        home_lineup = _fetch_team_lineup(engine, request.home_team_id, target_date)
        away_lineup = _fetch_team_lineup(engine, request.away_team_id, target_date)

        if len(home_lineup) < 9:
            home_lineup.extend(_build_placeholder_lineup(
                request.home_team_id, 0.310, 9 - len(home_lineup),
            ))
        if len(away_lineup) < 9:
            away_lineup.extend(_build_placeholder_lineup(
                request.away_team_id, 0.310, 9 - len(away_lineup),
            ))

        home_pitcher = _fetch_pitcher_state(
            engine, request.home_pitcher_id if request.home_pitcher_id else 0, target_date
        )
        away_pitcher = _fetch_pitcher_state(
            engine, request.away_pitcher_id if request.away_pitcher_id else 0, target_date
        )

        def progress(current, total):
            if current % 1000 == 0:
                logger.info(f"Simulating {request.game_id}: {current}/{total}")

        loop = asyncio.get_event_loop()
        sim = MonteCarloMLBSimulator(seed=42)

        result = await loop.run_in_executor(
            None,
            lambda: sim.run_simulation(
                home_lineup=home_lineup,
                away_lineup=away_lineup,
                home_pitcher=home_pitcher,
                away_pitcher=away_pitcher,
                park_factor_hr=request.park_factor_hr,
                n_iterations=request.n_iterations,
                progress_callback=progress,
            ),
        )

        now = datetime.now()
        response = SimulationResponse(
            game_id=request.game_id,
            home_win_prob=result.home_win_prob,
            away_win_prob=result.away_win_prob,
            mean_home_runs=result.mean_home_runs,
            mean_away_runs=result.mean_away_runs,
            std_home_runs=result.std_home_runs,
            std_away_runs=result.std_away_runs,
            extra_innings_prob=result.extra_innings_prob,
            walkoff_prob=result.walkoff_prob,
            n_iterations=request.n_iterations,
            home_run_distribution={
                str(k): v for k, v in result.home_run_distribution.items()
            },
            away_run_distribution={
                str(k): v for k, v in result.away_run_distribution.items()
            },
            computed_at=now,
        )

        # Persist to DB
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO simulation_results
                        (game_id, home_win_prob, away_win_prob,
                         mean_home_runs, mean_away_runs,
                         std_home_runs, std_away_runs,
                         extra_innings_prob, walkoff_prob,
                         run_distribution, n_iterations, computed_at)
                    VALUES (:gid, :hwp, :awp,
                            :mhr, :mar,
                            :shrs, :sars,
                            :eip, :wp,
                            :rd, :ni, :ca)
                    ON CONFLICT (game_id) DO UPDATE SET
                        home_win_prob = EXCLUDED.home_win_prob,
                        away_win_prob = EXCLUDED.away_win_prob,
                        mean_home_runs = EXCLUDED.mean_home_runs,
                        mean_away_runs = EXCLUDED.mean_away_runs,
                        std_home_runs = EXCLUDED.std_home_runs,
                        std_away_runs = EXCLUDED.std_away_runs,
                        extra_innings_prob = EXCLUDED.extra_innings_prob,
                        walkoff_prob = EXCLUDED.walkoff_prob,
                        run_distribution = EXCLUDED.run_distribution,
                        n_iterations = EXCLUDED.n_iterations,
                        computed_at = EXCLUDED.computed_at
                """),
                {
                    "gid": request.game_id,
                    "hwp": result.home_win_prob,
                    "awp": result.away_win_prob,
                    "mhr": result.mean_home_runs,
                    "mar": result.mean_away_runs,
                    "shrs": result.std_home_runs,
                    "sars": result.std_away_runs,
                    "eip": result.extra_innings_prob,
                    "wp": result.walkoff_prob,
                    "rd": json.dumps({
                        "home": {str(k): v for k, v in result.home_run_distribution.items()},
                        "away": {str(k): v for k, v in result.away_run_distribution.items()},
                    }),
                    "ni": request.n_iterations,
                    "ca": now,
                },
            )

        self.cache[request.game_id] = response
        logger.info(
            f"Simulation complete for {request.game_id}: "
            f"P(home)={result.home_win_prob:.3f}"
        )
        return response

    def get_cached(self, game_id: str) -> Optional[SimulationResponse]:
        return self.cache.get(game_id)
