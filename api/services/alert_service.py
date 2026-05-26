# =============================================================================
# alert_service.py
# Servicio de alertas en tiempo real (Sharp Money, RLM, EV+)
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from api.routers.alerts import send_ev_alert, send_sharp_money_alert

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self):
        self.alert_history: list[dict] = []
        self.subscribers: list[Callable] = []
        self.last_scan: datetime | None = None
        logger.info("AlertService initialized")

    async def scan_market_for_alerts(self, market_data: dict):
        from features.sharp_money import SharpMoneyDetector

        detector = SharpMoneyDetector()
        signals = []

        for game in market_data.get("games", []):
            sig = detector.analyze_full_game(
                game_id=game.get("game_id", ""),
                home_team=game.get("home_team_id", ""),
                away_team=game.get("away_team_id", ""),
                sportsbook=game.get("sportsbook", "DraftKings"),
                timestamp=datetime.now(),
                home_ticket_pct=game.get("home_ticket_pct", 50.0),
                home_money_pct=game.get("home_money_pct", 50.0),
                home_line_open=game.get("home_moneyline_open", 0),
                home_line_current=game.get("home_moneyline_close", 0),
            )
            signals.extend(sig)

        for signal in signals:
            if signal.is_actionable:
                alert = {
                    "game_id": signal.game_id,
                    "team_id": signal.team_id,
                    "signal_type": signal.signal_type,
                    "confidence": signal.confidence,
                    "timestamp": datetime.now(),
                    "details": {
                        "discrepancy": signal.discrepancy,
                        "line_movement": signal.line_movement,
                        "ticket_pct": signal.ticket_pct,
                        "money_pct": signal.money_pct,
                    },
                }
                self.alert_history.append(alert)

                await send_sharp_money_alert(
                    game_id=signal.game_id,
                    team_id=signal.team_id,
                    signal_type=signal.signal_type,
                    confidence=signal.confidence,
                    details=alert["details"],
                )

                logger.info(
                    f"Alert generated: {signal.signal_type} "
                    f"{signal.team_id} ({signal.confidence:.0%})"
                )

    async def scan_ev_alerts(self, simulation_results: list[dict]):
        from risk.ev_calculator import EVCalculator

        calc = EVCalculator()

        for sim in simulation_results:
            home_real = sim.get("home_win_prob", 0.5)
            away_real = sim.get("away_win_prob", 0.5)
            home_odds = sim.get("home_odds", 0)
            away_odds = sim.get("away_odds", 0)

            bets = calc.evaluate_moneyline(
                game_id=sim.get("game_id", ""),
                home_team=sim.get("home_team", ""),
                away_team=sim.get("away_team", ""),
                home_odds=home_odds,
                away_odds=away_odds,
                home_real_prob=home_real,
                away_real_prob=away_real,
            )

            for bet in bets:
                await send_ev_alert(
                    game_id=bet.game_id,
                    team=bet.team,
                    odds=bet.odds,
                    edge=bet.edge,
                    kelly=bet.kelly_fraction,
                )

    async def continuous_scan(self, interval_seconds: int = 60, duration_minutes: int = 180):
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        logger.info(
            f"Starting continuous alert scan "
            f"(interval={interval_seconds}s, duration={duration_minutes}m)"
        )

        while datetime.now() < end_time:
            try:
                market_data = {"games": []}
                await self.scan_market_for_alerts(market_data)
                logger.info(f"Alert scan cycle complete")
            except Exception as e:
                logger.error(f"Alert scan failed: {e}")

            await asyncio.sleep(interval_seconds)

    def get_recent_alerts(self, min_confidence: float = 0.0, limit: int = 50) -> list[dict]:
        filtered = [a for a in self.alert_history if a["confidence"] >= min_confidence]
        return filtered[-limit:]

    def get_unread_count(self) -> int:
        return len([a for a in self.alert_history if not a.get("is_read", False)])

    def mark_read(self, alert_id: int | None = None):
        if alert_id is None:
            for a in self.alert_history:
                a["is_read"] = True
        elif 0 <= alert_id < len(self.alert_history):
            self.alert_history[alert_id]["is_read"] = True
