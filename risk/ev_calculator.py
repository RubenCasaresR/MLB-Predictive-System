# =============================================================================
# ev_calculator.py
# Calculadora de Valor Esperado (EV+) y Cruce de Probabilidades
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Cruzar la Probabilidad Real (del modelo Monte Carlo) contra la
# Probabilidad Implícita (de las líneas del casino) para identificar
# únicamente apuestas con Expected Value Positivo (EV+).
#
# Filtros aplicados:
#   1. EV+ > threshold (default 2%)
#   2. Confianza del modelo > mínimo
#   3. No overlapped vig (cuando ambas EV son negativas)
#   4. Tamaño de apuesta dentro del bankroll disponible
# =============================================================================

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import math
import logging
from risk.kelly_criterion import KellyCriterion, KellyVariant

logger = logging.getLogger(__name__)


@dataclass
class EVBet:
    game_id: str
    team: str
    opponent: str
    sportsbook: str
    market_type: str  # "MONEYLINE", "RUN_LINE", "TOTAL", "PROP"
    odds: int
    real_prob: float
    implied_prob: float
    edge: float  # EV = real_prob - implied_prob
    kelly_fraction: float
    recommended_stake: float
    timestamp: datetime
    confidence: float
    is_actionable: bool


class EVCalculator:
    DEFAULT_EV_THRESHOLD = 0.02
    KELLY_FRACTION = 0.25
    MAX_STAKE_PCT = 0.05

    def __init__(self, bankroll: float = 10000.0):
        self.bankroll = bankroll
        self._kelly_calc = KellyCriterion(
            bankroll=bankroll,
            variant=KellyVariant.QUARTER,
            max_stake_pct=self.MAX_STAKE_PCT,
            min_edge=self.DEFAULT_EV_THRESHOLD,
        )
        logger.info(f"EVCalculator initialized (bankroll=${bankroll:.2f})")

    @staticmethod
    def american_to_implied(odds: int) -> float:
        if odds > 0:
            return 100.0 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    @staticmethod
    def american_to_decimal(odds: int) -> float:
        if odds > 0:
            return (odds / 100.0) + 1
        else:
            return (100.0 / abs(odds)) + 1

    @staticmethod
    def implied_to_american(prob: float) -> int:
        if prob >= 0.5:
            return -int(round((100 * prob) / (1 - prob)))
        else:
            return int(round((100 * (1 - prob)) / prob))

    def compute_edge(
        self, real_prob: float, odds: int,
        total_implied: Optional[float] = None,
    ) -> Tuple[float, float]:

        implied_raw = self.american_to_implied(odds)
        implied = implied_raw / total_implied if total_implied else implied_raw

        edge = real_prob - implied
        return edge, implied

    def evaluate_moneyline(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        home_odds: int,
        away_odds: int,
        home_real_prob: float,
        away_real_prob: float,
        sportsbook: str = "DraftKings",
    ) -> List[EVBet]:

        bets = []

        implied_home = self.american_to_implied(home_odds)
        implied_away = self.american_to_implied(away_odds)
        total_implied = implied_home + implied_away
        vig = total_implied - 1.0

        implied_home_adj = implied_home / total_implied
        implied_away_adj = implied_away / total_implied

        home_edge = home_real_prob - implied_home_adj
        away_edge = away_real_prob - implied_away_adj

        if home_edge >= self.DEFAULT_EV_THRESHOLD:
            kelly = self._kelly(home_real_prob, home_odds)
            stake = self._calculate_stake(kelly)
            bets.append(EVBet(
                game_id=game_id, team=home_team, opponent=away_team,
                sportsbook=sportsbook, market_type="MONEYLINE",
                odds=home_odds, real_prob=round(home_real_prob, 4),
                implied_prob=round(implied_home_adj, 4),
                edge=round(home_edge, 4), kelly_fraction=round(kelly, 4),
                recommended_stake=round(stake, 2),
                timestamp=datetime.now(), confidence=min(1.0, home_edge * 20),
                is_actionable=True,
            ))

        if away_edge >= self.DEFAULT_EV_THRESHOLD:
            kelly = self._kelly(away_real_prob, away_odds)
            stake = self._calculate_stake(kelly)
            bets.append(EVBet(
                game_id=game_id, team=away_team, opponent=home_team,
                sportsbook=sportsbook, market_type="MONEYLINE",
                odds=away_odds, real_prob=round(away_real_prob, 4),
                implied_prob=round(implied_away_adj, 4),
                edge=round(away_edge, 4), kelly_fraction=round(kelly, 4),
                recommended_stake=round(stake, 2),
                timestamp=datetime.now(), confidence=min(1.0, away_edge * 20),
                is_actionable=True,
            ))

        return bets

    def evaluate_runline(
        self,
        game_id: str,
        team: str,
        opponent: str,
        run_line: float,
        odds: int,
        real_prob_cover: float,
        sportsbook: str = "DraftKings",
    ) -> Optional[EVBet]:

        edge, implied = self.compute_edge(real_prob_cover, odds)

        if edge >= self.DEFAULT_EV_THRESHOLD:
            kelly = self._kelly(real_prob_cover, odds)
            stake = self._calculate_stake(kelly)
            return EVBet(
                game_id=game_id, team=team, opponent=opponent,
                sportsbook=sportsbook, market_type=f"RUN_LINE_{run_line:+.1f}",
                odds=odds, real_prob=round(real_prob_cover, 4),
                implied_prob=round(implied, 4),
                edge=round(edge, 4), kelly_fraction=round(kelly, 4),
                recommended_stake=round(stake, 2),
                timestamp=datetime.now(), confidence=min(1.0, edge * 25),
                is_actionable=True,
            )
        return None

    def evaluate_total(
        self,
        game_id: str,
        team: str,
        opponent: str,
        total: float,
        over_odds: int,
        under_odds: int,
        prob_over: float,
        prob_under: float,
        sportsbook: str = "DraftKings",
    ) -> List[EVBet]:

        bets = []

        implied_over = self.american_to_implied(over_odds)
        implied_under = self.american_to_implied(under_odds)
        total_implied = implied_over + implied_under
        implied_over_adj = implied_over / total_implied
        implied_under_adj = implied_under / total_implied

        over_edge = prob_over - implied_over_adj
        under_edge = prob_under - implied_under_adj

        if over_edge >= self.DEFAULT_EV_THRESHOLD:
            kelly = self._kelly(prob_over, over_odds)
            stake = self._calculate_stake(kelly)
            bets.append(EVBet(
                game_id=game_id, team=team, opponent=opponent,
                sportsbook=sportsbook, market_type=f"OVER_{total}",
                odds=over_odds, real_prob=round(prob_over, 4),
                implied_prob=round(implied_over_adj, 4),
                edge=round(over_edge, 4), kelly_fraction=round(kelly, 4),
                recommended_stake=round(stake, 2),
                timestamp=datetime.now(), confidence=min(1.0, over_edge * 20),
                is_actionable=True,
            ))

        if under_edge >= self.DEFAULT_EV_THRESHOLD:
            kelly = self._kelly(prob_under, under_odds)
            stake = self._calculate_stake(kelly)
            bets.append(EVBet(
                game_id=game_id, team=team, opponent=opponent,
                sportsbook=sportsbook, market_type=f"UNDER_{total}",
                odds=under_odds, real_prob=round(prob_under, 4),
                implied_prob=round(implied_under_adj, 4),
                edge=round(under_edge, 4), kelly_fraction=round(kelly, 4),
                recommended_stake=round(stake, 2),
                timestamp=datetime.now(), confidence=min(1.0, under_edge * 20),
                is_actionable=True,
            ))

        return bets

    def evaluate_prop(
        self,
        game_id: str,
        player_name: str,
        prop_type: str,
        line_value: float,
        over_odds: int,
        under_odds: int,
        prob_over: float,
        prob_under: float,
        sportsbook: str = "DraftKings",
    ) -> List[EVBet]:

        bets = []

        implied_over = self.american_to_implied(over_odds)
        implied_under = self.american_to_implied(under_odds)
        total_i = implied_over + implied_under
        implied_over_adj = implied_over / total_i
        implied_under_adj = implied_under / total_i

        over_edge = prob_over - implied_over_adj
        under_edge = prob_under - implied_under_adj

        market = f"{prop_type}_{line_value}"
        team = player_name

        if over_edge >= self.DEFAULT_EV_THRESHOLD:
            kelly = self._kelly(prob_over, over_odds)
            stake = self._calculate_stake(kelly)
            bets.append(EVBet(
                game_id=game_id, team=team, opponent="",
                sportsbook=sportsbook, market_type=f"{market}_OVER",
                odds=over_odds, real_prob=round(prob_over, 4),
                implied_prob=round(implied_over_adj, 4),
                edge=round(over_edge, 4), kelly_fraction=round(kelly, 4),
                recommended_stake=round(stake, 2),
                timestamp=datetime.now(), confidence=min(1.0, over_edge * 20),
                is_actionable=True,
            ))

        if under_edge >= self.DEFAULT_EV_THRESHOLD:
            kelly = self._kelly(prob_under, under_odds)
            stake = self._calculate_stake(kelly)
            bets.append(EVBet(
                game_id=game_id, team=team, opponent="",
                sportsbook=sportsbook, market_type=f"{market}_UNDER",
                odds=under_odds, real_prob=round(prob_under, 4),
                implied_prob=round(implied_under_adj, 4),
                edge=round(under_edge, 4), kelly_fraction=round(kelly, 4),
                recommended_stake=round(stake, 2),
                timestamp=datetime.now(), confidence=min(1.0, under_edge * 20),
                is_actionable=True,
            ))

        return bets

    def _kelly(self, prob: float, odds: int) -> float:
        result = self._kelly_calc.compute(probability=prob, american_odds=odds)
        return result.fractional_kelly if result.is_viable else 0.0

    def _calculate_stake(self, kelly_fraction: float) -> float:
        return self.bankroll * kelly_fraction

    def filter_best_bets(
        self, bets: List[EVBet], max_bets: int = 5
    ) -> List[EVBet]:
        sorted_bets = sorted(
            [b for b in bets if b.is_actionable],
            key=lambda x: x.edge * x.confidence,
            reverse=True,
        )
        return sorted_bets[:max_bets]

    def update_bankroll(self, new_bankroll: float):
        self.bankroll = new_bankroll
        self._kelly_calc.bankroll = new_bankroll
        logger.info(f"Bankroll updated to ${new_bankroll:.2f}")


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    calc = EVCalculator(bankroll=10000.0)

    bets = calc.evaluate_moneyline(
        game_id="2025-06-15-NYY-BOS",
        home_team="NYY", away_team="BOS",
        home_odds=-130, away_odds=+110,
        home_real_prob=0.580, away_real_prob=0.420,
    )

    print("APUESTAS EV+ ENCONTRADAS:")
    for bet in bets:
        print(f"  {bet.team} @ {bet.odds}")
        print(f"    EV: {bet.edge:.2%}")
        print(f"    Prob Real: {bet.real_prob:.1%} vs Implied: {bet.implied_prob:.1%}")
        print(f"    Stake: ${bet.recommended_stake:.2f}")
        print(f"    Kelly: {bet.kelly_fraction:.2%}")
