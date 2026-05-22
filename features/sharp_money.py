# =============================================================================
# sharp_money.py
# Algoritmo de Detección de Sharp Money y Reverse Line Movement
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Sharp Money: Discrepancia entre Ticket% (volumen de apuestas) y Money%
# (volumen de dinero). Cuando el Money% es significativamente diferente al
# Ticket%, indica que "dinero inteligente" (sharps) está apostando en contra
# del público general.
#
# Reverse Line Movement (RLM): Cuando la línea se mueve en dirección opuesta
# al volumen de apuestas del público. Ej: 70% de apuestas al equipo A,
# pero la línea se mueve a favor del equipo B -> RLM.
# =============================================================================

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class SharpMoneySignal:
    game_id: str
    team_id: str
    opponent_id: str
    sportsbook: str
    timestamp: datetime
    ticket_pct: float
    money_pct: float
    discrepancy: float
    line_open: int
    line_current: int
    line_movement: int
    signal_type: str  # "SHARP_MONEY", "RLM", "BOTH"
    confidence: float  # 0.0 - 1.0
    is_actionable: bool


class SharpMoneyDetector:
    # Umbrales de detección calibrados en datos históricos
    DISCREPANCY_THRESHOLD = 0.12    # 12% de diferencia Ticket% vs Money%
    RLM_TICKET_THRESHOLD = 0.55     # 55%+ del público en un lado
    MIN_CONFIDENCE = 0.60
    MIN_LINE_MOVEMENT = 5           # centavos mínimos de movimiento

    def __init__(self):
        logger.info("SharpMoneyDetector initialized")

    def analyze(
        self,
        game_id: str,
        team_id: str,
        opponent_id: str,
        sportsbook: str,
        timestamp: datetime,
        ticket_pct_team: float,
        money_pct_team: float,
        line_open_team: int,
        line_current_team: int,
    ) -> Optional[SharpMoneySignal]:

        # ticket_pct_team: % de boletos que apuestan al equipo
        # money_pct_team: % de dinero que apuesta al equipo
        ticket_pct = ticket_pct_team / 100.0
        money_pct = money_pct_team / 100.0
        discrepancy = abs(ticket_pct - money_pct)
        line_movement = line_current_team - line_open_team

        signal_type = None
        confidence = 0.0

        # --- Sharp Money: money% votes opposite to ticket% ---
        sharp_money_flag = False
        if discrepancy >= self.DISCREPANCY_THRESHOLD:
            if money_pct < ticket_pct:
                # El dinero va en contra del volumen público
                sharp_money_flag = True
                confidence = min(1.0, discrepancy * 3.0)
                signal_type = "SHARP_MONEY"

        # --- Reverse Line Movement ---
        rlm_flag = False
        public_side = ticket_pct >= self.RLM_TICKET_THRESHOLD
        if public_side and line_movement < -self.MIN_LINE_MOVEMENT:
            # Público en Team (ticket > 55%), línea se mueve CONTRA el Team
            rlm_flag = True
            confidence = max(confidence, min(1.0, abs(line_movement) / 15.0))
            signal_type = "RLM" if signal_type is None else "BOTH"

        if public_side and line_movement > self.MIN_LINE_MOVEMENT and money_pct < ticket_pct:
            rlm_flag = True
            confidence = max(confidence, min(1.0, abs(line_movement) / 15.0))
            signal_type = "RLM" if signal_type is None else "BOTH"

        if not sharp_money_flag and not rlm_flag:
            return None

        is_actionable = confidence >= self.MIN_CONFIDENCE

        return SharpMoneySignal(
            game_id=game_id,
            team_id=team_id,
            opponent_id=opponent_id,
            sportsbook=sportsbook,
            timestamp=timestamp,
            ticket_pct=round(ticket_pct, 3),
            money_pct=round(money_pct, 3),
            discrepancy=round(discrepancy, 3),
            line_open=line_open_team,
            line_current=line_current_team,
            line_movement=line_movement,
            signal_type=signal_type,
            confidence=round(confidence, 3),
            is_actionable=is_actionable,
        )

    def analyze_full_game(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        sportsbook: str,
        timestamp: datetime,
        home_ticket_pct: float,
        home_money_pct: float,
        home_line_open: int,
        home_line_current: int,
    ) -> List[SharpMoneySignal]:

        signals = []

        home_signal = self.analyze(
            game_id=game_id,
            team_id=home_team,
            opponent_id=away_team,
            sportsbook=sportsbook,
            timestamp=timestamp,
            ticket_pct_team=home_ticket_pct,
            money_pct_team=home_money_pct,
            line_open_team=home_line_open,
            line_current_team=home_line_current,
        )
        if home_signal:
            signals.append(home_signal)

        away_ticket_pct = 100.0 - home_ticket_pct
        away_money_pct = 100.0 - home_money_pct

        away_line_open = -home_line_open if home_line_open else 0
        away_line_current = -home_line_current if home_line_current else 0

        away_signal = self.analyze(
            game_id=game_id,
            team_id=away_team,
            opponent_id=home_team,
            sportsbook=sportsbook,
            timestamp=timestamp,
            ticket_pct_team=away_ticket_pct,
            money_pct_team=away_money_pct,
            line_open_team=away_line_open,
            line_current_team=away_line_current,
        )
        if away_signal:
            signals.append(away_signal)

        return signals

    def batch_analyze(
        self,
        market_df: pd.DataFrame,
    ) -> pd.DataFrame:
        results = []
        for _, row in market_df.iterrows():
            signals = self.analyze_full_game(
                game_id=row.get("game_id"),
                home_team=row.get("home_team_id"),
                away_team=row.get("away_team_id"),
                sportsbook=row.get("sportsbook", "DraftKings"),
                timestamp=row.get("recorded_at", datetime.now()),
                home_ticket_pct=row.get("home_ticket_pct", 50.0),
                home_money_pct=row.get("home_money_pct", 50.0),
                home_line_open=row.get("home_moneyline_open", 0),
                home_line_current=row.get("home_moneyline_close", 0),
            )
            for sig in signals:
                results.append({
                    "game_id": sig.game_id,
                    "team_id": sig.team_id,
                    "opponent_id": sig.opponent_id,
                    "sportsbook": sig.sportsbook,
                    "timestamp": sig.timestamp,
                    "signal_type": sig.signal_type,
                    "confidence": sig.confidence,
                    "discrepancy": sig.discrepancy,
                    "line_movement": sig.line_movement,
                    "is_actionable": sig.is_actionable,
                })

        return pd.DataFrame(results)

    def query_market_data_sql(self, game_id: str) -> str:
        return f"""
        SELECT
            ml.game_id,
            g.home_team_id,
            g.away_team_id,
            sb.name AS sportsbook,
            ml.recorded_at,
            ml.home_ticket_pct,
            ml.home_money_pct,
            ml.home_moneyline_open,
            ml.home_moneyline_close
        FROM market_lines ml
        JOIN games g ON g.game_id = ml.game_id
        JOIN sportsbooks sb ON sb.book_id = ml.sportsbook_id
        WHERE ml.game_id = '{game_id}'
        ORDER BY ml.recorded_at DESC;
        """


# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    detector = SharpMoneyDetector()

    # Escenario típico: público masivo en Yankees (72% tickets),
    # pero el dinero inteligente va a Red Sox (58% money)
    signal = detector.analyze(
        game_id="2025-06-15-NYY-BOS",
        team_id="NYY",
        opponent_id="BOS",
        sportsbook="DraftKings",
        timestamp=datetime.now(),
        ticket_pct_team=72.0,
        money_pct_team=42.0,
        line_open_team=-130,
        line_current_team=-115,
    )

    if signal:
        print(f"SEÑAL DETECTADA: {signal.signal_type}")
        print(f"  Juego: {signal.game_id}")
        print(f"  Equipo: {signal.team_id} vs {signal.opponent_id}")
        print(f"  Ticket%: {signal.ticket_pct:.1%}")
        print(f"  Money%:  {signal.money_pct:.1%}")
        print(f"  Discrepancia: {signal.discrepancy:.1%}")
        print(f"  Linea abrio: {signal.line_open}")
        print(f"  Linea actual: {signal.line_current}")
        print(f"  Movimiento: {signal.line_movement}")
        print(f"  Confianza: {signal.confidence:.1%}")
        print(f"  Accionable: {signal.is_actionable}")
    else:
        print("Sin senal Sharp Money/RLM detectada")
