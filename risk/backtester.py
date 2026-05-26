# =============================================================================
# risk/backtester.py
# Walk-Forward Backtesting Engine para MLB Predictive System
# Rubén Eduardo Casales Rosales - MLB Predictive System
# =============================================================================

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sqlalchemy import create_engine, text

from prediction.model_training.train_multiclass_model import (
    engineer_features,
    load_training_data,
    map_target,
    train_model,
)
from prediction.monte_carlo_simulator import MonteCarloMLBSimulator
from prediction.player_state_builder import build_player_states_from_db
from risk.kelly_criterion import BankrollManager
from risk.strategies import BacktestStrategy, MoneylineStrategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestMonthResult:
    month: str
    n_games: int
    n_bets: int
    n_wins: int
    n_losses: int
    total_stake: float
    total_profit: float
    roi_pct: float
    bankroll_end: float


@dataclass
class BacktestResult:
    initial_bankroll: float
    final_bankroll: float
    total_return_pct: float
    total_bets: int
    total_wins: int
    total_losses: int
    win_rate: float
    roi_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    monthly: list[BacktestMonthResult] = field(default_factory=list)


class WalkForwardBacktester:
    """Backtester walk-forward mensual.

    Para cada mes:
      1. Entrena modelo con datos anteriores al mes.
      2. Simula cada juego del mes con Monte Carlo.
      3. Evalúa estrategia de apuestas.
      4. Liquida apuestas por resultado real.
    """

    def __init__(
        self,
        db_url: str,
        strategy: BacktestStrategy | None = None,
        initial_bankroll: float = 10_000.0,
        n_simulations: int = 1_000,
        models_dir: str = "models/backtest",
    ):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.strategy = strategy or MoneylineStrategy(
            bankroll=initial_bankroll,
        )
        self.initial_bankroll = initial_bankroll
        self.n_simulations = n_simulations
        self.models_dir = models_dir
        self.bankroll = BankrollManager(initial=initial_bankroll)
        self.monthly_results: list[BacktestMonthResult] = []
        os.makedirs(models_dir, exist_ok=True)

    def run(
        self,
        start_date: date = date(2024, 4, 1),
        end_date: date = date(2024, 9, 30),
        training_start: date = date(2023, 3, 1),
    ) -> BacktestResult:
        """Ejecuta backtest walk-forward completo."""
        windows = self._build_monthly_windows(start_date, end_date)

        for cutoff, win_start, win_end in windows:
            logger.info("=" * 60)
            logger.info("Month: %s — cutoff=%s", win_start.strftime("%B"), cutoff)
            logger.info("Training cutoff: %s | Window: %s to %s", cutoff, win_start, win_end)

            if cutoff < training_start:
                logger.warning("Skipping — not enough training data before %s", cutoff)
                continue

            model_path = self._train_model(cutoff)
            month_result = self._simulate_month(model_path, win_start, win_end)
            self.monthly_results.append(month_result)

            logger.info(
                "Month %s: %d bets, %.1f%% ROI, bankroll=%.0f",
                win_start.strftime("%B"),
                month_result.n_bets,
                month_result.roi_pct,
                month_result.bankroll_end,
            )

        return self._build_final_result()

    def _build_monthly_windows(
        self,
        start: date,
        end: date,
    ) -> list[tuple[date, date, date]]:
        """Genera ventanas mensuales: (cutoff, start, end)."""
        windows = []
        current = start
        while current <= end:
            month_end = date(
                current.year + (current.month // 12),
                (current.month % 12) + 1,
                1,
            ) - timedelta(days=1)
            month_end = min(month_end, end)
            windows.append((current, current, month_end))
            current = date(
                current.year + (current.month // 12),
                (current.month % 12) + 1,
                1,
            )
        return windows

    def _train_model(self, cutoff_date: date) -> str:
        """Entrena CatBoost con datos hasta cutoff_date."""
        logger.info("Training model with cutoff %s...", cutoff_date)
        df_raw = load_training_data(self.db_url, cutoff_date=cutoff_date)
        y = map_target(df_raw["events"])
        X = engineer_features(df_raw)

        n_total = len(X)
        n_val = max(1, int(n_total * 0.15))
        n_train = n_total - n_val

        X_train = X.iloc[:n_train]
        X_val = X.iloc[n_train:]
        y_train = y.iloc[:n_train]
        y_val = y.iloc[n_train:]

        model = train_model(X_train, y_train, X_val, y_val, models_dir=self.models_dir)
        tag = cutoff_date.isoformat()
        path = os.path.join(self.models_dir, f"model_{tag}.cbm")
        model.save_model(path)
        logger.info("Model saved to %s", path)
        return path

    def _simulate_month(
        self,
        model_path: str,
        month_start: date,
        month_end: date,
    ) -> BacktestMonthResult:
        """Simula todos los juegos FINAL en la ventana y aplica la estrategia."""
        sim = MonteCarloMLBSimulator(model_path=model_path, seed=42)
        month_label = month_start.strftime("%Y-%m")

        games = self._get_games(month_start, month_end)

        n_bets = 0
        n_wins = 0
        n_losses = 0
        total_stake = 0.0
        total_profit = 0.0

        for game in games:
            gid = game["game_id"]
            game_date = game["game_date"]
            home_team = game["home_team_id"]
            away_team = game["away_team_id"]
            home_p_id = game["home_pitcher"]
            away_p_id = game["away_pitcher"]
            home_odds = game["home_odds"]
            away_odds = game["away_odds"]
            home_score = game["home_score"]
            away_score = game["away_score"]

            if home_odds is None or away_odds is None:
                continue

            home_lineup, away_lineup, home_pitcher, away_pitcher = build_player_states_from_db(
                self.engine,
                gid,
                home_team,
                away_team,
                home_p_id,
                away_p_id,
                game_date,
            )

            context = self._get_game_context(gid, game_date, home_team, away_team)
            if context is None:
                continue

            result = sim.run_simulation(
                home_lineup=home_lineup,
                away_lineup=away_lineup,
                home_pitcher=home_pitcher,
                away_pitcher=away_pitcher,
                park_factor_hr=context["pf_hr"],
                park_factor_single=context["pf_woba"],
                park_factor_k=context["pf_k"],
                temperature_f=context["temperature"],
                wind_speed=context["wind_speed"],
                wind_direction=context["wind_direction"],
                umpire_cs_rate=context["umpire_cs_rate"],
                stadium_id=context["stadium_id"],
                umpire_id=context["umpire_id"],
                home_bullpen_fip_30d=context["home_bp_fip"],
                away_bullpen_fip_30d=context["away_bp_fip"],
                home_rest_days=context.get("home_rest_days", 4),
                away_rest_days=context.get("away_rest_days", 4),
                home_travel_miles=context.get("home_travel_miles", 0),
                away_travel_miles=context.get("away_travel_miles", 0),
                home_tz_crossings=context.get("home_tz_crossings", 0),
                away_tz_crossings=context.get("away_tz_crossings", 0),
                n_iterations=self.n_simulations,
            )

            home_win_pct = result.home_win_prob
            decisions = self.strategy.evaluate_game(
                game_id=gid,
                home_team=home_team,
                away_team=away_team,
                home_win_pct=home_win_pct,
                home_odds=home_odds,
                away_odds=away_odds,
            )

            for bet in decisions:
                if not bet.is_viable or bet.stake <= 0:
                    continue

                actual_home_won = home_score > away_score
                won = (bet.side == "home" and actual_home_won) or (
                    bet.side == "away" and not actual_home_won
                )

                self.bankroll.record_bet(bet.stake, bet.odds, won)
                n_bets += 1
                total_stake += bet.stake
                if won:
                    n_wins += 1
                    if bet.odds > 0:
                        total_profit += bet.stake * (bet.odds / 100.0)
                    else:
                        total_profit += bet.stake * (100.0 / abs(bet.odds))
                else:
                    n_losses += 1
                    total_profit -= bet.stake

        roi = (total_profit / total_stake * 100.0) if total_stake > 0 else 0.0
        return BacktestMonthResult(
            month=month_label,
            n_games=len(games),
            n_bets=n_bets,
            n_wins=n_wins,
            n_losses=n_losses,
            total_stake=round(total_stake, 2),
            total_profit=round(total_profit, 2),
            roi_pct=round(roi, 2),
            bankroll_end=round(self.bankroll.current, 2),
        )

    def _get_games(self, start: date, end: date) -> list[dict]:
        """Obtiene juegos FINAL con market lines en el rango."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        g.game_id, g.game_date,
                        g.home_team_id, g.away_team_id,
                        COALESCE(g.home_probable_pitcher, 0) AS home_pitcher,
                        COALESCE(g.away_probable_pitcher, 0) AS away_pitcher,
                        g.home_score, g.away_score,
                        ml.home_moneyline_close, ml.away_moneyline_close
                    FROM games g
                    LEFT JOIN market_lines ml
                        ON ml.game_id = g.game_id
                        AND ml.sportsbook_id = 0
                    WHERE g.game_date BETWEEN :s AND :e
                      AND g.status = 'FINAL'
                    ORDER BY g.game_date, g.game_id
                """),
                {"s": start, "e": end},
            ).fetchall()

        return [
            {
                "game_id": r[0],
                "game_date": r[1],
                "home_team_id": r[2],
                "away_team_id": r[3],
                "home_pitcher": r[4],
                "away_pitcher": r[5],
                "home_score": r[6],
                "away_score": r[7],
                "home_odds": r[8],
                "away_odds": r[9],
            }
            for r in rows
        ]

    def _get_game_context(
        self,
        game_id: str,
        game_date: date,
        home_team: str,
        away_team: str,
    ) -> dict | None:
        """Obtiene contexto del juego: parque, clima, umpire, bullpens."""
        try:
            with self.engine.connect() as conn:
                f = conn.execute(
                    text("""
                        SELECT
                            park_hr_factor, park_woba_factor, park_k_factor,
                            temperature, wind_speed, wind_direction,
                            umpire_cs_rate,
                            home_rest_days, away_rest_days,
                            away_tz_crossings, away_travel_miles
                        FROM mv_game_features
                        WHERE game_id = :gid
                    """),
                    {"gid": game_id},
                ).fetchone()

                gi = conn.execute(
                    text("""
                        SELECT venue_id, home_plate_umpire_id
                        FROM games WHERE game_id = :gid
                    """),
                    {"gid": game_id},
                ).fetchone()

                h_bp = conn.execute(
                    text("""
                        SELECT bullpen_era_30d, bullpen_fip_30d
                        FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :gd
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": home_team, "gd": game_date},
                ).fetchone()
                a_bp = conn.execute(
                    text("""
                        SELECT bullpen_era_30d, bullpen_fip_30d
                        FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :gd
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": away_team, "gd": game_date},
                ).fetchone()

            return {
                "pf_hr": float(f.park_hr_factor) if f and f.park_hr_factor else 1.0,
                "pf_woba": float(f.park_woba_factor) if f and f.park_woba_factor else 1.0,
                "pf_k": float(f.park_k_factor) if f and f.park_k_factor else 1.0,
                "temperature": float(f.temperature) if f and f.temperature is not None else 70.0,
                "wind_speed": float(f.wind_speed) if f and f.wind_speed is not None else 0.0,
                "wind_direction": str(f.wind_direction) if f and f.wind_direction else "NONE",
                "umpire_cs_rate": float(f.umpire_cs_rate) if f and f.umpire_cs_rate else 0.0,
                "stadium_id": int(gi[0]) if gi and gi[0] else 0,
                "umpire_id": int(gi[1]) if gi and gi[1] else 0,
                "home_bp_era": float(h_bp[0]) if h_bp and h_bp[0] else 4.50,
                "home_bp_fip": float(h_bp[1]) if h_bp and h_bp[1] else 4.50,
                "away_bp_era": float(a_bp[0]) if a_bp and a_bp[0] else 4.50,
                "away_bp_fip": float(a_bp[1]) if a_bp and a_bp[1] else 4.50,
                "home_rest_days": int(f.home_rest_days) if f and f.home_rest_days else 4,
                "away_rest_days": int(f.away_rest_days) if f and f.away_rest_days else 4,
                "home_travel_miles": 0,
                "away_travel_miles": int(f.away_travel_miles) if f and f.away_travel_miles else 0,
                "home_tz_crossings": 0,
                "away_tz_crossings": int(f.away_tz_crossings) if f and f.away_tz_crossings else 0,
            }
        except Exception as e:
            logger.warning("Could not fetch context for game %s: %s", game_id, e)
            return None

    def _build_final_result(self) -> BacktestResult:
        """Construye el resultado consolidado del backtest."""
        total_bets = sum(m.n_bets for m in self.monthly_results)
        total_wins = sum(m.n_wins for m in self.monthly_results)
        total_losses = sum(m.n_losses for m in self.monthly_results)
        total_stake = sum(m.total_stake for m in self.monthly_results)
        total_profit = sum(m.total_profit for m in self.monthly_results)

        win_rate = (total_wins / total_bets * 100.0) if total_bets > 0 else 0.0
        roi = (total_profit / total_stake * 100.0) if total_stake > 0 else 0.0
        total_return = (
            (self.bankroll.current - self.initial_bankroll) / self.initial_bankroll * 100.0
        )

        return BacktestResult(
            initial_bankroll=round(self.initial_bankroll, 2),
            final_bankroll=round(self.bankroll.current, 2),
            total_return_pct=round(total_return, 2),
            total_bets=total_bets,
            total_wins=total_wins,
            total_losses=total_losses,
            win_rate=round(win_rate, 2),
            roi_pct=round(roi, 2),
            sharpe_ratio=round(self.bankroll.sharpe_ratio(), 3),
            max_drawdown_pct=round(self.bankroll.drawdown * 100.0, 2),
            monthly=self.monthly_results,
        )

    def print_report(self, result: BacktestResult):
        """Imprime el reporte final del backtest."""
        print("=" * 60)
        print("BACKTEST REPORT — Walk-Forward Monte Carlo")
        print("=" * 60)
        print(f"  Initial Bankroll:     ${result.initial_bankroll:,.2f}")
        print(f"  Final Bankroll:       ${result.final_bankroll:,.2f}")
        print(f"  Total Return:         {result.total_return_pct:+.2f}%")
        print(f"  Total Bets:           {result.total_bets}")
        print(f"  Win Rate:             {result.win_rate:.1f}%")
        print(f"  ROI:                  {result.roi_pct:+.2f}%")
        print(f"  Sharpe Ratio:         {result.sharpe_ratio:.3f}")
        print(f"  Max Drawdown:         {result.max_drawdown_pct:.1f}%")
        print("-" * 60)
        print(
            f"{'Month':<10} {'Games':>6} {'Bets':>5} {'Wins':>5} {'Losses':>6} "
            f"{'Stake':>10} {'Profit':>10} {'ROI':>8} {'Bankroll':>10}"
        )
        print("-" * 60)
        for m in result.monthly:
            print(
                f"{m.month:<10} {m.n_games:>6} {m.n_bets:>5} {m.n_wins:>5} "
                f"{m.n_losses:>6} ${m.total_stake:>8,.0f} "
                f"${m.total_profit:>+8,.0f} {m.roi_pct:>+7.1f}% "
                f"${m.bankroll_end:>9,.0f}"
            )
        print("=" * 60)

    def export_report(self, result: BacktestResult, path: str = "logs/backtest_report.json"):
        """Exporta el reporte a JSON."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "initial_bankroll": result.initial_bankroll,
            "final_bankroll": result.final_bankroll,
            "total_return_pct": result.total_return_pct,
            "total_bets": result.total_bets,
            "total_wins": result.total_wins,
            "total_losses": result.total_losses,
            "win_rate": result.win_rate,
            "roi_pct": result.roi_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "monthly": [asdict(m) for m in result.monthly],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Report exported to %s", path)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse

    from etl.config import DATABASE_URL

    parser = argparse.ArgumentParser(description="MLB Predictive System — Walk-Forward Backtester")
    parser.add_argument("--start", type=str, default="2024-04-01")
    parser.add_argument("--end", type=str, default="2024-09-30")
    parser.add_argument("--bankroll", type=float, default=10_000.0)
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument("--models-dir", type=str, default="models/backtest")
    parser.add_argument("--output", type=str, default="logs/backtest_report.json")
    args = parser.parse_args()

    bt = WalkForwardBacktester(
        db_url=DATABASE_URL,
        initial_bankroll=args.bankroll,
        n_simulations=args.iterations,
        models_dir=args.models_dir,
    )
    result = bt.run(
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
    )
    bt.print_report(result)
    bt.export_report(result, args.output)
