# =============================================================================
# bankroll_manager.py
# Gestión de Capital y Exposición de Riesgo
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Extensión del BankrollManager con funcionalidad de base de datos
# y límites de exposición por deporte, liga, y sportsbook.
# =============================================================================

import json
from typing import Dict, List, Optional
from datetime import datetime, date
from dataclasses import dataclass, asdict
from sqlalchemy import create_engine, text
import logging

from risk.kelly_criterion import BankrollManager as BaseBankrollManager

logger = logging.getLogger(__name__)


@dataclass
class ExposureLimit:
    max_per_bet: float = 500.0
    max_per_day: float = 2500.0
    max_per_week: float = 10000.0
    max_per_sportsbook: float = 5000.0
    max_drawdown: float = 0.20
    max_concurrent_bets: int = 10


class PersistentBankrollManager(BaseBankrollManager):
    def __init__(
        self,
        initial: float = 10000.0,
        db_url: str = "",
        user_id: str = "default",
    ):
        super().__init__(initial)
        self.db_url = db_url
        self.user_id = user_id
        self.engine = create_engine(db_url) if db_url else None
        self.limits = ExposureLimit()
        logger.info(f"PersistentBankrollManager for user {user_id}")

    def save_state(self):
        if not self.engine:
            return
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO bankroll_state (user_id, current, peak,
                        total_wagered, total_profit, updated_at)
                    VALUES (:uid, :cur, :peak, :wagered, :profit, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE SET
                        current = EXCLUDED.current,
                        peak = CASE WHEN EXCLUDED.peak > bankroll_state.peak THEN EXCLUDED.peak ELSE bankroll_state.peak END,
                        total_wagered = bankroll_state.total_wagered + EXCLUDED.total_wagered,
                        total_profit = bankroll_state.total_profit + EXCLUDED.total_profit,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "uid": self.user_id,
                    "cur": self.current,
                    "peak": self.peak,
                    "wagered": self.total_wagered,
                    "profit": self.total_profit,
                },
            )

    def check_exposure(
        self,
        stake: float,
        sportsbook: str = "",
        bet_date: date = None,
    ) -> Dict:

        if bet_date is None:
            bet_date = date.today()

        violations = []

        if stake > self.limits.max_per_bet:
            violations.append(f"Stake ${stake:.2f} exceeds max per bet ${self.limits.max_per_bet:.2f}")

        if self.current - stake < self.current * (1 - self.limits.max_drawdown):
            violations.append(f"Bet would exceed max drawdown of {self.limits.max_drawdown:.0%}")

        daily_total = sum(
            b["stake"]
            for b in self.bet_history
            if b.get("date", date.today()) == bet_date
        )
        if daily_total + stake > self.limits.max_per_day:
            violations.append(f"Daily total ${daily_total + stake:.2f} exceeds ${self.limits.max_per_day:.2f}")

        recent_bets = [b for b in self.bet_history if b.get("won") is False]
        recent_losses = sum(b["stake"] for b in recent_bets[-5:])
        if recent_losses > self.current * 0.15:
            violations.append("Recent losses exceed 15% of bankroll (cooling off suggested)")

        return {
            "approved": len(violations) == 0,
            "violations": violations,
            "current_bankroll": round(self.current, 2),
            "stake": round(stake, 2),
            "stake_pct": round(stake / self.current * 100, 2) if self.current > 0 else 0,
        }

    def get_bet_slip_summary(self, bets: List[Dict]) -> Dict:
        total_stake = sum(b.get("recommended_stake", 0) for b in bets)
        total_kelly = sum(b.get("kelly_fraction", 0) for b in bets)

        return {
            "total_bets": len(bets),
            "total_stake": round(total_stake, 2),
            "stake_pct": round(total_stake / self.current * 100, 2) if self.current > 0 else 0,
            "average_kelly": round(total_kelly / len(bets), 4) if bets else 0,
            "current_bankroll": round(self.current, 2),
            "remaining_capacity": round(self.current - total_stake, 2),
        }


# ============================================================================
# TABLA SQL PARA BANKROLL
# ============================================================================

BANKROLL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bankroll_state (
    user_id         VARCHAR(50)  PRIMARY KEY,
    current         DECIMAL(12,2) NOT NULL,
    peak            DECIMAL(12,2) NOT NULL,
    total_wagered   DECIMAL(14,2) DEFAULT 0,
    total_profit    DECIMAL(14,2) DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bet_history (
    bet_id          BIGSERIAL    PRIMARY KEY,
    user_id         VARCHAR(50)  NOT NULL,
    game_id         VARCHAR(12),
    team            VARCHAR(50),
    market_type     VARCHAR(30),
    odds            INTEGER,
    stake           DECIMAL(8,2),
    won             BOOLEAN,
    profit_loss     DECIMAL(8,2),
    kelly_pct       DECIMAL(5,4),
    edge            DECIMAL(5,4),
    placed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled_at      TIMESTAMP
);
"""


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    bm = PersistentBankrollManager(initial=10000.0)

    print("=== Exposure Check ===")
    check = bm.check_exposure(stake=450.0)
    print(f"  Approved: {check['approved']}")
    if check["violations"]:
        for v in check["violations"]:
            print(f"  Violation: {v}")

    bets_data = [
        {"recommended_stake": 250, "kelly_fraction": 0.025},
        {"recommended_stake": 180, "kelly_fraction": 0.018},
        {"recommended_stake": 320, "kelly_fraction": 0.032},
    ]
    summary = bm.get_bet_slip_summary(bets_data)
    print(f"\n=== Bet Slip Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
