# =============================================================================
# risk.py
# Router de gestión de riesgo y bankroll
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_current_user
from api.models.pydantic_models import BankrollResponse, ExposureResponse

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/risk",
    tags=["risk"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/bankroll", response_model=BankrollResponse)
async def get_bankroll_status():
    from risk.bankroll_manager import PersistentBankrollManager

    bm = PersistentBankrollManager()
    status = bm.status()
    return BankrollResponse(
        initial=status["initial"],
        current=status["current"],
        peak=status["peak"],
        drawdown_pct=status["drawdown"],
        total_wagered=status["total_wagered"],
        total_profit=status["total_profit"],
        roi_pct=status["roi"],
        total_return_pct=status["total_return"],
        sharpe_ratio=status["sharpe_ratio"],
        bet_count=status["bet_count"],
        updated_at="2025-01-01T00:00:00",
    )


@router.post("/bankroll/update")
async def update_bankroll(new_amount: float):
    import os

    from risk.bankroll_manager import PersistentBankrollManager

    if new_amount <= 0:
        raise HTTPException(status_code=400, detail="Bankroll must be positive")

    bm = PersistentBankrollManager()
    previous = bm.current
    bm.current = new_amount
    bm.save_state()

    return {
        "status": "updated",
        "previous": round(previous, 2),
        "current": round(new_amount, 2),
    }


@router.post("/exposure/check", response_model=ExposureResponse)
async def check_exposure(
    stake: float = Query(..., gt=0),
    sportsbook: str | None = Query(None),
):
    from risk.bankroll_manager import PersistentBankrollManager

    bm = PersistentBankrollManager()
    check = bm.check_exposure(stake=stake)
    return ExposureResponse(
        approved=check["approved"],
        violations=check["violations"],
        current_bankroll=check["current_bankroll"],
        stake=check["stake"],
        stake_pct=check["stake_pct"],
    )


@router.get("/limits")
async def get_risk_limits():
    from risk.bankroll_manager import ExposureLimit

    limits = ExposureLimit()
    return {
        "max_per_bet": limits.max_per_bet,
        "max_per_day": limits.max_per_day,
        "max_per_week": limits.max_per_week,
        "max_drawdown": limits.max_drawdown,
        "max_concurrent_bets": limits.max_concurrent_bets,
    }


@router.get("/exposure/summary")
async def get_exposure_summary():
    from sqlalchemy import text

    from api.database import get_engine

    engine = get_engine()

    with engine.connect() as conn:
        by_sportsbook = conn.execute(
            text("""
                SELECT COALESCE(sportsbook, 'unknown'), SUM(stake)
                FROM bet_history WHERE won IS NULL
                GROUP BY sportsbook
            """)
        ).fetchall()

        by_game = conn.execute(
            text("""
                SELECT COALESCE(game_id, 'unknown'), SUM(stake)
                FROM bet_history WHERE won IS NULL
                GROUP BY game_id
            """)
        ).fetchall()

        total = conn.execute(
            text("SELECT COALESCE(SUM(stake), 0) FROM bet_history WHERE won IS NULL")
        ).scalar()

    return {
        "total_exposed": float(total),
        "by_sportsbook": {r[0]: float(r[1]) for r in by_sportsbook},
        "by_game": {r[0]: float(r[1]) for r in by_game},
    }
