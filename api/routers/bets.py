# =============================================================================
# bets.py
# Router de apuestas EV+ - FastAPI
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from api.auth import get_current_user
from api.database import get_async_engine
from api.models.pydantic_models import (
    BetSlipRequest,
    BetSlipResponse,
    EVRequest,
    EVResponse,
    PropRequest,
    PropResponse,
    SimulationRequest,
    SimulationResponse,
)
from api.models.sure_bet_models import SureBetsResponse

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/bets",
    tags=["bets"],
    dependencies=[Depends(get_current_user)],
)


# ============================================================================
# EV+ CALCULATOR
# ============================================================================


@router.post("/ev", response_model=EVResponse)
async def calculate_ev(request: EVRequest):
    from risk.ev_calculator import EVCalculator

    calc = EVCalculator()
    bets = calc.evaluate_moneyline(
        game_id=request.game_id,
        home_team="HOME",
        away_team="AWAY",
        home_odds=request.home_odds,
        away_odds=request.away_odds,
        home_real_prob=request.home_real_prob,
        away_real_prob=request.away_real_prob,
    )

    return EVResponse(
        game_id=request.game_id,
        bets=[
            {
                "team": b.team,
                "odds": b.odds,
                "edge": b.edge,
                "kelly_fraction": b.kelly_fraction,
                "recommended_stake": b.recommended_stake,
                "implied_prob": b.implied_prob,
                "real_prob": b.real_prob,
            }
            for b in bets
        ],
    )


# ============================================================================
# SIMULATION
# ============================================================================


@router.post("/simulate", response_model=SimulationResponse)
async def run_simulation(request: SimulationRequest):
    from api.services.simulation_service import SimulationService

    service = SimulationService()
    result = await service.run_simulation(request)
    return result


# ============================================================================
# PROPS EVALUATION
# ============================================================================


@router.post("/props/evaluate", response_model=PropResponse)
async def evaluate_prop(request: PropRequest):
    from prediction.poisson_props import PoissonPropsEngine

    engine = PoissonPropsEngine()
    result = engine.evaluate_bet(
        prop_type=request.prop_type,
        player_name=f"Player_{request.player_id}",
        line_value=request.line_value,
        over_odds=request.over_odds,
        under_odds=request.under_odds,
        features=request.features,
    )

    if result.recommendation == "no_bet":
        raise HTTPException(
            status_code=204,
            detail="No EV+ opportunity found for this prop",
        )

    return PropResponse(
        player_name=result.player_name,
        prop_type=result.prop_type,
        line_value=result.line_value,
        predicted_mean=result.predicted_mean,
        prob_over=result.prob_over,
        prob_under=result.prob_under,
        ev_over=result.ev_over,
        ev_under=result.ev_under,
        recommendation=result.recommendation,
        kelly_fraction=result.kelly_fraction,
    )


# ============================================================================
# BET SLIP SUBMISSION
# ============================================================================


@router.post("/slip", response_model=BetSlipResponse)
async def submit_bet_slip(request: BetSlipRequest):
    from risk.bankroll_manager import PersistentBankrollManager

    bm = PersistentBankrollManager()

    total_stake = sum(b.stake for b in request.bets)
    violations = []

    for bet in request.bets:
        check = bm.check_exposure(stake=bet.stake, game_id=bet.game_id)
        if not check["approved"]:
            violations.extend(check["violations"])

    if violations:
        return BetSlipResponse(
            approved=False,
            total_stake=round(total_stake, 2),
            violations=violations,
        )

    return BetSlipResponse(
        approved=True,
        total_stake=round(total_stake, 2),
    )


@router.get("/simulate/{game_id}", response_model=SimulationResponse)
async def get_simulation(game_id: str):
    async_engine = get_async_engine()
    async with async_engine.connect() as conn:
        row = await conn.execute(
            text("""
                SELECT home_win_prob, away_win_prob,
                       mean_home_runs, mean_away_runs,
                       std_home_runs, std_away_runs,
                       extra_innings_prob, walkoff_prob,
                       run_distribution, n_iterations, computed_at
                FROM simulation_results
                WHERE game_id = :gid
            """),
            {"gid": game_id},
        )
        result = row.fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Simulation not found for this game")

    run_dist = json.loads(result[8]) if result[8] else {}

    return SimulationResponse(
        game_id=game_id,
        home_win_prob=float(result[0]),
        away_win_prob=float(result[1]),
        mean_home_runs=float(result[2]) if result[2] else 0,
        mean_away_runs=float(result[3]) if result[3] else 0,
        std_home_runs=float(result[4]) if result[4] else 0,
        std_away_runs=float(result[5]) if result[5] else 0,
        extra_innings_prob=float(result[6]) if result[6] else 0,
        walkoff_prob=float(result[7]) if result[7] else 0,
        n_iterations=result[9] or 10000,
        home_run_distribution=run_dist,
        away_run_distribution=run_dist,
        computed_at=result[10] or datetime.now(),
    )


@router.get("/approved", response_model=list[dict])
async def get_approved_bets(
    limit: int = Query(10, ge=1, le=100),
    min_edge: float = Query(0.02, ge=0.0, le=1.0),
):
    async_engine = get_async_engine()
    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT ab.game_id, ab.team, ab.opponent, ab.sportsbook,
                       ab.market_type, ab.odds, ab.edge, ab.kelly_fraction,
                       ab.recommended_stake, ab.confidence, ab.created_at
                FROM approved_bets ab
                WHERE ab.status = 'pending'
                  AND ab.edge >= :me
                ORDER BY ab.edge * ab.confidence DESC
                LIMIT :lim
            """),
            {"me": min_edge, "lim": limit},
        )
        rows = result.fetchall()

    return [
        {
            "game_id": r[0],
            "team": r[1],
            "opponent": r[2],
            "sportsbook": r[3],
            "market_type": r[4],
            "odds": r[5],
            "edge": float(r[6]) if r[6] else 0,
            "kelly_fraction": float(r[7]) if r[7] else 0,
            "recommended_stake": float(r[8]) if r[8] else 0,
            "confidence": float(r[9]) if r[9] else 0,
            "created_at": str(r[10]) if r[10] else "",
        }
        for r in rows
    ]


# ============================================================================
# SURE BETS (Apuestas Seguras)
# ============================================================================


@router.get("/sure-bets", response_model=SureBetsResponse)
async def get_sure_bets():
    from api.services.sure_bets import SureBetService

    service = SureBetService()
    return await service.get_sure_bets()


@router.get("/history")
async def get_bet_history(limit: int = Query(50, ge=1, le=500)):
    async_engine = get_async_engine()
    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT bet_id, game_id, team, market_type, odds, stake,
                       won, profit_loss, kelly_pct, edge, placed_at
                FROM bet_history
                ORDER BY placed_at DESC
                LIMIT :lim
            """),
            {"lim": limit},
        )
        rows = result.fetchall()

    return [
        {
            "bet_id": r[0],
            "game_id": r[1],
            "team": r[2],
            "market_type": r[3],
            "odds": r[4],
            "stake": float(r[5]) if r[5] else 0,
            "won": r[6],
            "profit_loss": float(r[7]) if r[7] else 0,
            "kelly_pct": float(r[8]) if r[8] else 0,
            "edge": float(r[9]) if r[9] else 0,
            "placed_at": str(r[10]) if r[10] else "",
        }
        for r in rows
    ]
