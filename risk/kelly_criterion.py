# =============================================================================
# kelly_criterion.py
# Implementación del Criterio de Kelly para Gestión de Capital
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# El Criterio de Kelly determina la fracción óptima del bankroll a apostar
# para maximizar el crecimiento geométrico a largo plazo.
#
# Estrategias implementadas:
#   - Kelly Completo (Full Kelly): f* = (p*(b+1)-1)/b
#   - Kelly Fraccional: 1/4 Kelly, 1/3 Kelly, 1/2 Kelly
#   - Kelly Ajustado por Riesgo: con factor de confianza del modelo
#   - Kelly con Límite por Apuesta: máximo % del bankroll
#   - Kelly Multiapuesta: correlación entre apuestas simultáneas
# =============================================================================

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class KellyVariant(Enum):
    FULL = "full"
    HALF = "half"  # 1/2 Kelly
    QUARTER = "quarter"  # 1/4 Kelly
    EIGHTH = "eighth"  # 1/8 Kelly
    THIRD = "third"  # 1/3 Kelly


@dataclass
class KellyResult:
    player_name: str
    bet_type: str
    odds: int
    probability: float
    full_kelly: float
    fractional_kelly: float
    recommended_stake: float
    confidence_factor: float
    is_viable: bool
    risk_level: str  # 'conservative', 'moderate', 'aggressive'


class KellyCriterion:
    def __init__(
        self,
        bankroll: float = 10000.0,
        variant: KellyVariant = KellyVariant.QUARTER,
        max_stake_pct: float = 0.05,
        min_edge: float = 0.02,
        min_kelly: float = 0.001,
    ):
        self.bankroll = bankroll
        self.variant = variant
        self.max_stake_pct = max_stake_pct
        self.min_edge = min_edge
        self.min_kelly = min_kelly
        self.fraction_map = {
            KellyVariant.FULL: 1.0,
            KellyVariant.HALF: 0.5,
            KellyVariant.QUARTER: 0.25,
            KellyVariant.EIGHTH: 0.125,
            KellyVariant.THIRD: 0.333,
        }
        logger.info(
            f"KellyCriterion: bankroll=${bankroll:.2f}, "
            f"variant={variant.value}, max_stake={max_stake_pct:.1%}"
        )

    def odds_to_decimal(self, american_odds: int) -> float:
        if american_odds > 0:
            return (american_odds / 100.0) + 1
        else:
            return (100.0 / abs(american_odds)) + 1

    def compute(
        self,
        probability: float,
        american_odds: int,
        confidence: float = 1.0,
    ) -> KellyResult:

        if probability <= 0 or probability >= 1:
            return KellyResult(
                "", "", american_odds, probability, 0, 0, 0, 0, False, "conservative"
            )

        decimal = self.odds_to_decimal(american_odds)
        b = decimal - 1

        if b <= 0:
            return KellyResult(
                "", "", american_odds, probability, 0, 0, 0, 0, False, "conservative"
            )

        # Full Kelly
        full_kelly = (probability * (b + 1) - 1) / b
        full_kelly = max(0.0, full_kelly)

        # Apply fractional multiplier
        fraction = self.fraction_map[self.variant]
        fractional = full_kelly * fraction

        # Apply confidence factor (model uncertainty)
        confidence_adj = fractional * confidence

        # Cap at max stake
        capped = min(confidence_adj, self.max_stake_pct)

        # Apply minimum threshold
        if capped < self.min_kelly:
            is_viable = False
            capped = 0.0
        else:
            is_viable = True

        stake = self.bankroll * capped

        edge = probability - (1.0 / decimal)

        if capped <= 0.01:
            risk_level = "conservative"
        elif capped <= 0.025:
            risk_level = "moderate"
        else:
            risk_level = "aggressive"

        return KellyResult(
            player_name="",
            bet_type="",
            odds=american_odds,
            probability=round(probability, 4),
            full_kelly=round(full_kelly, 4),
            fractional_kelly=round(capped, 4),
            recommended_stake=round(stake, 2),
            confidence_factor=round(confidence, 2),
            is_viable=is_viable,
            risk_level=risk_level,
        )

    def compute_bet(
        self,
        player_name: str,
        bet_type: str,
        probability: float,
        american_odds: int,
        confidence: float = 1.0,
    ) -> KellyResult:

        result = self.compute(probability, american_odds, confidence)
        result.player_name = player_name
        result.bet_type = bet_type
        return result

    def compute_multiple(self, bets: list[tuple[str, str, float, int, float]]) -> list[KellyResult]:

        results = []
        total_kelly = 0.0

        for player_name, bet_type, prob, odds, conf in bets:
            result = self.compute_bet(player_name, bet_type, prob, odds, conf)
            results.append(result)
            total_kelly += result.fractional_kelly

        if total_kelly > 0.25:
            scaling = 0.25 / total_kelly
            for r in results:
                r.fractional_kelly = round(r.fractional_kelly * scaling, 4)
                r.recommended_stake = round(self.bankroll * r.fractional_kelly, 2)
            logger.info(f"Bets scaled by {scaling:.2f} (total kelly={total_kelly:.3f})")

        return results

    def compute_with_hedge(
        self,
        primary_prob: float,
        primary_odds: int,
        hedge_prob: float,
        hedge_odds: int,
        confidence: float = 1.0,
    ) -> dict:

        primary_result = self.compute(primary_prob, primary_odds, confidence)

        hedge_result = self.compute(hedge_prob, hedge_odds, confidence)

        total_investment = primary_result.recommended_stake + hedge_result.recommended_stake

        return {
            "primary": primary_result,
            "hedge": hedge_result,
            "total_investment": round(total_investment, 2),
            "bankroll_after": round(self.bankroll - total_investment, 2),
        }


# ============================================================================
# GESTOR DE BANKROLL
# ============================================================================


class BankrollManager:
    def __init__(self, initial: float = 10000.0):
        self.initial = initial
        self.current = initial
        self.peak = initial
        self.total_wagered = 0.0
        self.total_profit = 0.0
        self.bet_history: list[dict] = []
        self.drawdown = 0.0
        logger.info(f"BankrollManager: initial=${initial:.2f}")

    def record_bet(self, stake: float, odds: int, result: bool):
        self.total_wagered += stake

        if result:
            if odds > 0:
                profit = stake * (odds / 100.0)
            else:
                profit = stake * (100.0 / abs(odds))
            self.current += profit
            self.total_profit += profit
        else:
            self.current -= stake
            self.total_profit -= stake

        if self.current > self.peak:
            self.peak = self.current
            self.drawdown = 0.0
        else:
            self.drawdown = (self.peak - self.current) / self.peak

        self.bet_history.append(
            {
                "stake": stake,
                "odds": odds,
                "won": result,
                "bankroll_before": self.current + (profit if result else -stake),
                "bankroll_after": self.current,
                "timestamp": None,
            }
        )

        logger.info(
            f"Bet recorded: stake=${stake:.2f}, odds={odds:+d}, "
            f"result={'WON' if result else 'LOST'}, "
            f"bankroll=${self.current:.2f}"
        )

    def current_bankroll(self) -> float:
        return self.current

    def roi(self) -> float:
        if self.total_wagered == 0:
            return 0.0
        return self.total_profit / self.total_wagered

    def total_return(self) -> float:
        return (self.current - self.initial) / self.initial

    def sharpe_ratio(self, risk_free_rate: float = 0.0) -> float:
        if len(self.bet_history) < 2:
            return 0.0
        returns = []
        prev = self.initial
        for bet in self.bet_history:
            r = (bet["bankroll_after"] - prev) / prev
            returns.append(r)
            prev = bet["bankroll_after"]
        mean_ret = sum(returns) / len(returns)
        std_ret = (
            math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / len(returns))
            if len(returns) > 1
            else 0.001
        )
        return (mean_ret - risk_free_rate) / std_ret if std_ret > 0 else 0.0

    def status(self) -> dict:
        return {
            "initial": round(self.initial, 2),
            "current": round(self.current, 2),
            "peak": round(self.peak, 2),
            "drawdown": round(self.drawdown * 100, 2),
            "total_wagered": round(self.total_wagered, 2),
            "total_profit": round(self.total_profit, 2),
            "roi": round(self.roi() * 100, 2),
            "total_return": round(self.total_return() * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio(), 3),
            "bet_count": len(self.bet_history),
        }


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    kelly = KellyCriterion(bankroll=10000.0, variant=KellyVariant.QUARTER)

    result = kelly.compute_bet(
        player_name="NYY Moneyline",
        bet_type="MONEYLINE",
        probability=0.62,
        american_odds=-130,
        confidence=0.85,
    )

    print(f"Kelly Analysis for {result.player_name}:")
    print(f"  Full Kelly:     {result.full_kelly:.2%}")
    print(f"  Fractional Kelly: {result.fractional_kelly:.2%}")
    print(f"  Recommended Stake: ${result.recommended_stake:.2f}")
    print(f"  Risk Level:     {result.risk_level}")
    print(f"  Viable:         {result.is_viable}")

    bm = BankrollManager(initial=10000.0)
    bm.record_bet(result.recommended_stake, -130, True)
    bm.record_bet(200, +150, False)
    bm.record_bet(150, -110, True)

    print(f"\nBankroll Status:")
    for k, v in bm.status().items():
        print(f"  {k}: {v}")
