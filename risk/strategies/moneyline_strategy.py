# =============================================================================
# moneyline_strategy.py
# Estrategia de apuestas Moneyline para Backtesting
# Rubén Eduardo Casales Rosales - MLB Predictive System
# =============================================================================

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from risk.kelly_criterion import KellyCriterion, KellyVariant

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BetDecision — una apuesta candidata
# ---------------------------------------------------------------------------


@dataclass
class BetDecision:
    game_id: str
    side: str  # "home" | "away"
    team_abbr: str
    odds: int
    predicted_win_pct: float
    stake: float
    edge: float
    kelly_fraction: float
    is_viable: bool


# ---------------------------------------------------------------------------
# BacktestStrategy — interfaz inyectable
# ---------------------------------------------------------------------------


class BacktestStrategy(ABC):
    """Interfaz para estrategias de backtesting."""

    @abstractmethod
    def evaluate_game(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        home_win_pct: float,
        home_odds: int,
        away_odds: int,
    ) -> list[BetDecision]: ...


# ---------------------------------------------------------------------------
# MoneylineStrategy — implementación concreta
# ---------------------------------------------------------------------------


class MoneylineStrategy(BacktestStrategy):
    """Apuesta moneyline cuando el modelo detecta edge > min_edge.

    Usa 1/4 Kelly con max_stake_pct=5% y min_edge=2%.
    """

    def __init__(
        self,
        bankroll: float = 10_000.0,
        variant: KellyVariant = KellyVariant.QUARTER,
        min_edge: float = 0.02,
        max_stake_pct: float = 0.05,
        min_kelly: float = 0.001,
    ):
        self.kelly = KellyCriterion(
            bankroll=bankroll,
            variant=variant,
            min_edge=min_edge,
            max_stake_pct=max_stake_pct,
            min_kelly=min_kelly,
        )
        self.min_edge = min_edge
        logger.info(
            "MoneylineStrategy: bankroll=%.0f variant=%s min_edge=%.1f%%",
            bankroll,
            variant.value,
            min_edge * 100,
        )

    def _american_odds_to_implied(self, odds: int) -> float:
        if odds > 0:
            return 100.0 / (odds + 100.0)
        else:
            return abs(odds) / (abs(odds) + 100.0)

    def evaluate_game(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        home_win_pct: float,
        home_odds: int,
        away_odds: int,
    ) -> list[BetDecision]:
        decisions: list[BetDecision] = []

        if home_odds is None or away_odds is None:
            return decisions

        # Home side
        home_implied = self._american_odds_to_implied(home_odds)
        home_edge = home_win_pct - home_implied

        if home_edge > self.min_edge:
            kr = self.kelly.compute(home_win_pct, home_odds)
            decisions.append(
                BetDecision(
                    game_id=game_id,
                    side="home",
                    team_abbr=home_team,
                    odds=home_odds,
                    predicted_win_pct=home_win_pct,
                    stake=kr.recommended_stake,
                    edge=home_edge,
                    kelly_fraction=kr.fractional_kelly,
                    is_viable=kr.is_viable,
                )
            )

        # Away side
        away_implied = self._american_odds_to_implied(away_odds)
        away_win_pct = 1.0 - home_win_pct
        away_edge = away_win_pct - away_implied

        if away_edge > self.min_edge:
            kr = self.kelly.compute(away_win_pct, away_odds)
            decisions.append(
                BetDecision(
                    game_id=game_id,
                    side="away",
                    team_abbr=away_team,
                    odds=away_odds,
                    predicted_win_pct=away_win_pct,
                    stake=kr.recommended_stake,
                    edge=away_edge,
                    kelly_fraction=kr.fractional_kelly,
                    is_viable=kr.is_viable,
                )
            )

        return decisions
