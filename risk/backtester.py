# =============================================================================
# risk/backtester.py
# Motor de Backtesting Diario con Aislamiento de Data Leakage
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# BacktestEngine: iteración día por día, construye estados con stats
# hasta X-1, ejecuta Monte Carlo, evalúa EV+ con Kelly, y persiste
# bankroll. Diseñado para evitar Data Leakage: nunca usa datos del
# mismo día del juego para predecir.
# =============================================================================

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import List

from sqlalchemy import create_engine, text

from prediction.monte_carlo_simulator import MonteCarloMLBSimulator
from prediction.player_state_builder import (
    IncompleteLineupError,
    build_player_states_from_db,
    fetch_league_avg_probs,
)
from risk.bankroll_manager import PersistentBankrollManager
from risk.kelly_criterion import KellyCriterion, KellyVariant

logger = logging.getLogger(__name__)


@dataclass
class BacktestGameRecord:
    game_id: str
    game_date: date
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    home_odds: int | None
    away_odds: int | None
    home_win_prob: float
    side: str | None
    odds_taken: int | None
    stake: float
    won: bool | None
    edge: float
    skipped_reason: str = ""


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
    n_games: int
    n_games_skipped: int
    start_date: str
    end_date: str
    records: list[BacktestGameRecord] = field(default_factory=list)


class BacktestEngine:
    """Backtester diario con aislamiento estricto de data leakage.

    Para cada día X:
      1. Obtiene juegos FINAL con market lines de cierre.
      2. Construye player states con rolling stats hasta X-1.
      3. Ejecuta Monte Carlo con datos de contexto (parque, clima).
      4. Evalúa EV+ usando Kelly para sizing.
      5. Liquida apuesta con resultado real.
      6. Persiste estado del bankroll.
    """

    def __init__(
        self,
        db_url: str,
        initial_bankroll: float = 10_000.0,
        sportsbook_id: int = 1,
        n_iterations: int = 10_000,
        min_edge: float = 0.02,
        max_stake_pct: float = 0.05,
    ):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.sportsbook_id = sportsbook_id
        self.n_iterations = n_iterations
        self.bankroll = PersistentBankrollManager(
            initial=initial_bankroll,
            db_url=db_url,
            user_id=f"backtest_{datetime.now().strftime('%Y%m%d_%H%M')}",
        )
        self.kelly = KellyCriterion(
            bankroll=initial_bankroll,
            variant=KellyVariant.QUARTER,
            min_edge=min_edge,
            max_stake_pct=max_stake_pct,
        )
        self.initial_bankroll = initial_bankroll

    # ========================================================================
    # Flujo principal
    # ========================================================================

    def run(
        self,
        start_date: date,
        end_date: date,
    ) -> BacktestResult:
        records: list[BacktestGameRecord] = []
        total_games = 0
        total_skipped = 0

        current_date = start_date
        while current_date <= end_date:
            logger.info("Backtesting %s...", current_date.isoformat())
            day_before = current_date - timedelta(days=1)

            games = self._get_final_games(current_date)
            total_games += len(games)

            if not games:
                current_date += timedelta(days=1)
                continue

            league_probs = fetch_league_avg_probs(self.engine)
            sim = MonteCarloMLBSimulator(seed=42, league_avg_probs=league_probs)

            for game in games:
                self.kelly.bankroll = self.bankroll.current

                try:
                    lineups = build_player_states_from_db(
                        self.engine,
                        game["game_id"],
                        game["home_team"],
                        game["away_team"],
                        game["home_pitcher"],
                        game["away_pitcher"],
                        day_before,
                    )
                except IncompleteLineupError:
                    total_skipped += 1
                    records.append(self._skipped_record(game, "incomplete_lineup"))
                    continue

                context = self._get_game_context(
                    game["game_id"],
                    game["home_team"],
                    game["away_team"],
                    day_before,
                )
                if context is None:
                    total_skipped += 1
                    records.append(self._skipped_record(game, "no_context"))
                    continue

                sim_result = sim.run_simulation(
                    home_lineup=lineups[0],
                    away_lineup=lineups[1],
                    home_pitcher=lineups[2],
                    away_pitcher=lineups[3],
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
                    home_bullpen_era=context["home_bp_era"],
                    away_bullpen_era=context["away_bp_era"],
                    home_rest_days=context["home_rest_days"],
                    away_rest_days=context["away_rest_days"],
                    home_travel_miles=context["home_travel_miles"],
                    away_travel_miles=context["away_travel_miles"],
                    home_tz_crossings=context["home_tz_crossings"],
                    away_tz_crossings=context["away_tz_crossings"],
                    n_iterations=self.n_iterations,
                )

                record = self._evaluate_bet(game, sim_result.home_win_prob, current_date)
                records.append(record)

            self.bankroll.save_state()
            current_date += timedelta(days=1)

        return self._build_result(records, total_games, total_skipped, start_date, end_date)

    # ========================================================================
    # Consultas a base de datos
    # ========================================================================

    def _get_final_games(self, game_date: date) -> list[dict]:
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                text("""
                    SELECT
                        g.game_id,
                        g.home_team_id,
                        g.away_team_id,
                        COALESCE(g.home_probable_pitcher, 0) AS home_pitcher,
                        COALESCE(g.away_probable_pitcher, 0) AS away_pitcher,
                        g.home_score,
                        g.away_score,
                        ml.home_moneyline_close,
                        ml.away_moneyline_close
                    FROM games g
                    LEFT JOIN market_lines ml
                        ON ml.game_id = g.game_id
                        AND ml.sportsbook_id = :sb
                        AND ml.recorded_at = (
                            SELECT MAX(ml2.recorded_at)
                            FROM market_lines ml2
                            WHERE ml2.game_id = g.game_id
                              AND ml2.sportsbook_id = :sb
                        )
                    WHERE g.game_date = :gd
                      AND g.status = 'FINAL'
                      AND g.home_score IS NOT NULL
                      AND g.away_score IS NOT NULL
                """),
                {"gd": game_date, "sb": self.sportsbook_id},
            ).fetchall()

            return [
                {
                    "game_id": r[0],
                    "home_team": r[1],
                    "away_team": r[2],
                    "home_pitcher": r[3],
                    "away_pitcher": r[4],
                    "home_score": r[5],
                    "away_score": r[6],
                    "home_odds": r[7],
                    "away_odds": r[8],
                }
                for r in rows
            ]
        except Exception:
            return []

    def _get_game_context(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        as_of: date,
    ) -> dict | None:
        try:
            with self.engine.connect() as conn:
                f = conn.execute(
                    text("""
                        SELECT
                            park_hr_factor, park_woba_factor, park_k_factor,
                            temperature, wind_speed, wind_direction,
                            umpire_cs_rate
                        FROM mv_game_features
                        WHERE game_id = :gid
                    """),
                    {"gid": game_id},
                ).fetchone()

                gi = conn.execute(
                    text("""
                        SELECT g.venue_id, g.home_plate_umpire_id, s.roof_type,
                               g.home_rest_days, g.away_rest_days,
                               g.away_tz_crossings, g.away_travel_miles,
                               g.home_tz_crossings, g.home_travel_miles
                        FROM games g
                        LEFT JOIN stadiums s ON s.stadium_id = g.venue_id
                        WHERE g.game_id = :gid
                    """),
                    {"gid": game_id},
                ).fetchone()

                h_bp = conn.execute(
                    text("""
                        SELECT bullpen_era_30d, bullpen_fip_30d
                        FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :ad
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": home_team, "ad": as_of},
                ).fetchone()

                a_bp = conn.execute(
                    text("""
                        SELECT bullpen_era_30d, bullpen_fip_30d
                        FROM team_rolling_stats
                        WHERE team_id = :tid AND as_of_date <= :ad
                        ORDER BY as_of_date DESC LIMIT 1
                    """),
                    {"tid": away_team, "ad": as_of},
                ).fetchone()

            temp = float(f.temperature) if f and f.temperature is not None else 70.0
            wind_spd = float(f.wind_speed) if f and f.wind_speed is not None else 0.0
            wind_dir = str(f.wind_direction) if f and f.wind_direction else "NONE"

            roof = str(gi[2]) if gi and gi[2] else None
            if roof in ("dome", "retractable"):
                temp = 72.0
                wind_spd = 0.0
                wind_dir = "NONE"

            return {
                "pf_hr": float(f.park_hr_factor) if f and f.park_hr_factor else 1.0,
                "pf_woba": float(f.park_woba_factor) if f and f.park_woba_factor else 1.0,
                "pf_k": float(f.park_k_factor) if f and f.park_k_factor else 1.0,
                "temperature": temp,
                "wind_speed": wind_spd,
                "wind_direction": wind_dir,
                "umpire_cs_rate": float(f.umpire_cs_rate) if f and f.umpire_cs_rate else 0.0,
                "stadium_id": int(gi[0]) if gi and gi[0] else 0,
                "umpire_id": int(gi[1]) if gi and gi[1] else 0,
                "home_bp_era": float(h_bp[0]) if h_bp and h_bp[0] else 4.50,
                "home_bp_fip": float(h_bp[1]) if h_bp and h_bp[1] else 4.50,
                "away_bp_era": float(a_bp[0]) if a_bp and a_bp[0] else 4.50,
                "away_bp_fip": float(a_bp[1]) if a_bp and a_bp[1] else 4.50,
                "home_rest_days": int(gi[3]) if gi and gi[3] is not None else 4,
                "away_rest_days": int(gi[4]) if gi and gi[4] is not None else 4,
                "away_tz_crossings": int(gi[5]) if gi and gi[5] is not None else 0,
                "away_travel_miles": int(gi[6]) if gi and gi[6] is not None else 0,
                "home_tz_crossings": int(gi[7]) if gi and gi[7] is not None else 0,
                "home_travel_miles": int(gi[8]) if gi and gi[8] is not None else 0,
            }
        except Exception as e:
            logger.warning("Could not fetch context for game %s: %s", game_id, e)
            return None

    # ========================================================================
    # Evaluación de apuestas
    # ========================================================================

    def _evaluate_bet(
        self,
        game: dict,
        home_win_prob: float,
        game_date: date,
    ) -> BacktestGameRecord:
        home_odds = game.get("home_odds")
        away_odds = game.get("away_odds")
        home_score = game["home_score"]
        away_score = game["away_score"]

        record = BacktestGameRecord(
            game_id=game["game_id"],
            game_date=game_date,
            home_team=game["home_team"],
            away_team=game["away_team"],
            home_score=home_score,
            away_score=away_score,
            home_odds=home_odds,
            away_odds=away_odds,
            home_win_prob=round(home_win_prob, 4),
            side=None,
            odds_taken=None,
            stake=0.0,
            won=None,
            edge=0.0,
        )

        if home_odds is None or away_odds is None:
            record.skipped_reason = "no_odds"
            return record

        actual_home_won = home_score > away_score

        candidates = [
            ("home", home_win_prob, home_odds),
            ("away", 1.0 - home_win_prob, away_odds),
        ]
        candidates.sort(key=lambda x: x[1] / self._implied_prob(x[2]), reverse=True)

        for side, prob, odds in candidates:
            kr = self.kelly.compute(prob, odds)
            if not kr.is_viable:
                continue

            exposure = self.bankroll.check_exposure(
                stake=kr.recommended_stake,
                game_id=record.game_id,
                bet_date=game_date,
            )
            if not exposure["approved"]:
                logger.debug(
                    "Bet rejected for %s (%s): %s",
                    record.game_id,
                    side,
                    exposure["violations"],
                )
                continue

            won = (side == "home" and actual_home_won) or (
                side == "away" and not actual_home_won
            )

            self.bankroll.record_bet(kr.recommended_stake, odds, won, game_id=record.game_id)
            self.kelly.bankroll = self.bankroll.current

            record.side = side
            record.odds_taken = odds
            record.stake = kr.recommended_stake
            record.won = won
            record.edge = round(prob - self._implied_prob(odds), 4)
            break

        return record

    @staticmethod
    def _implied_prob(american_odds: int) -> float:
        if american_odds > 0:
            return 100.0 / (american_odds + 100.0)
        return abs(american_odds) / (abs(american_odds) + 100.0)

    def _skipped_record(self, game: dict, reason: str = "") -> BacktestGameRecord:
        return BacktestGameRecord(
            game_id=game.get("game_id", ""),
            game_date=game.get("game_date", date.min),
            home_team=game.get("home_team", ""),
            away_team=game.get("away_team", ""),
            home_score=game.get("home_score", 0),
            away_score=game.get("away_score", 0),
            home_odds=game.get("home_odds"),
            away_odds=game.get("away_odds"),
            home_win_prob=0.0,
            side=None,
            odds_taken=None,
            stake=0.0,
            won=None,
            edge=0.0,
            skipped_reason=reason,
        )

    # ========================================================================
    # Resultados
    # ========================================================================

    def _build_result(
        self,
        records: list[BacktestGameRecord],
        total_games: int,
        total_skipped: int,
        start_date: date,
        end_date: date,
    ) -> BacktestResult:
        bets = [r for r in records if r.won is not None]
        total_bets = len(bets)
        total_wins = sum(1 for r in bets if r.won)
        total_losses = total_bets - total_wins
        win_rate = (total_wins / total_bets * 100.0) if total_bets > 0 else 0.0

        total_stake = self.bankroll.total_wagered
        total_profit = self.bankroll.total_profit
        roi = (total_profit / total_stake * 100.0) if total_stake > 0 else 0.0
        total_return = (
            (self.bankroll.current - self.initial_bankroll)
            / self.initial_bankroll
            * 100.0
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
            n_games=total_games,
            n_games_skipped=total_skipped,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            records=records,
        )

    def print_report(self, result: BacktestResult):
        print("=" * 62)
        print(f"  BACKTEST REPORT — Daily Monte Carlo")
        print(f"  {result.start_date}  →  {result.end_date}")
        print("=" * 62)
        print(f"  Initial Bankroll:     ${result.initial_bankroll:>8,.2f}")
        print(f"  Final Bankroll:       ${result.final_bankroll:>8,.2f}")
        print(f"  Total Return:         {result.total_return_pct:>+8.2f}%")
        print(f"  Total Games:          {result.n_games:>8}")
        print(f"  Games Skipped:        {result.n_games_skipped:>8}")
        print(f"  Total Bets:           {result.total_bets:>8}")
        print(f"  Wins  /  Losses:      {result.total_wins:>3}  /  {result.total_losses:<3}")
        print(f"  Win Rate:             {result.win_rate:>7.1f}%")
        print(f"  ROI:                  {result.roi_pct:>+8.2f}%")
        print(f"  Sharpe Ratio:         {result.sharpe_ratio:>8.3f}")
        print(f"  Max Drawdown:         {result.max_drawdown_pct:>7.1f}%")
        print("=" * 62)

    def export_report(self, result: BacktestResult, path: str = "logs/backtest_report.json"):
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
            "n_games": result.n_games,
            "n_games_skipped": result.n_games_skipped,
            "start_date": result.start_date,
            "end_date": result.end_date,
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

    parser = argparse.ArgumentParser(
        description="MLB Predictive System — Daily Backtest Engine",
    )
    parser.add_argument("--start", type=str, default="2023-04-01")
    parser.add_argument("--end", type=str, default="2023-09-30")
    parser.add_argument("--bankroll", type=float, default=10_000.0)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--sportsbook", type=int, default=1)
    parser.add_argument("--output", type=str, default="logs/backtest_report.json")
    args = parser.parse_args()

    bt = BacktestEngine(
        db_url=DATABASE_URL,
        initial_bankroll=args.bankroll,
        sportsbook_id=args.sportsbook,
        n_iterations=args.iterations,
    )
    result = bt.run(
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
    )
    bt.print_report(result)
    bt.export_report(result, args.output)
