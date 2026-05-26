# =============================================================================
# run.py
# Unified CLI runner — MLB Predictive System
# Rubén Eduardo Casares Rosales
# =============================================================================
# Punto de entrada único para todos los pipelines del sistema.
#
# Uso:
#   python run.py daily                    # Pipeline diario (hoy)
#   python run.py daily --date 2024-06-15  # Pipeline diario (fecha específica)
#   python run.py historical               # Ingesta histórica masiva
#   python run.py backtest                 # Backtesting walk-forward
#   python run.py loop [--interval 24]     # Loop infinito (para Docker)
#   python run.py all                      # Daily + backtest secuencial
# =============================================================================

import logging
import logging.config
import os
import signal
import time
from argparse import ArgumentParser
from datetime import date, datetime

from etl.config import DATABASE_URL, LOGGING_CONFIG

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

_SHUTDOWN = False
_HEARTBEAT_FILE = "/tmp/etl_healthy"


def _signal_handler(signum, frame):
    global _SHUTDOWN
    logger.info("Received signal %d — shutting down gracefully...", signum)
    _SHUTDOWN = True


def _touch_heartbeat():
    try:
        os.makedirs(os.path.dirname(_HEARTBEAT_FILE), exist_ok=True)
        with open(_HEARTBEAT_FILE, "w") as f:
            f.write(datetime.utcnow().isoformat())
    except Exception:
        pass


def _sleep_with_shutdown(seconds: int):
    for _ in range(seconds):
        if _SHUTDOWN:
            break
        time.sleep(1)


# =============================================================================
# Comando: daily
# =============================================================================


def cmd_daily(args):
    from etl.orchestrator import ETLOrchestrator

    target = date.fromisoformat(args.date) if args.date else date.today()
    logger.info("=== Daily pipeline for %s ===", target)
    orch = ETLOrchestrator(DATABASE_URL)
    orch.run_daily_pipeline(target)
    _touch_heartbeat()
    logger.info("=== Daily pipeline complete ===")


# =============================================================================
# Comando: historical
# =============================================================================


def cmd_historical(args):
    from run_historical_ingest import run_historical_ingest

    run_historical_ingest(
        db_url=DATABASE_URL,
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
        skip_statcast=args.skip_statcast,
        skip_weather=args.skip_weather,
        skip_markets=args.skip_markets,
        skip_features=args.skip_features,
        rate_limit_seconds=args.rate_limit,
        checkpoint=not args.no_checkpoint,
    )


# =============================================================================
# Comando: backtest
# =============================================================================


def cmd_backtest(args):
    from risk.backtester import WalkForwardBacktester

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


# =============================================================================
# Comando: loop  (reemplaza a python -m etl.orchestrator --loop)
# =============================================================================


def cmd_loop(args):
    from etl.orchestrator import ETLOrchestrator

    signal.signal(signal.SIGTERM, _signal_handler)
    logger.info("Loop mode — interval: %dh, heartbeat: %s", args.interval, _HEARTBEAT_FILE)

    orch = ETLOrchestrator(DATABASE_URL)
    _touch_heartbeat()

    while not _SHUTDOWN:
        logger.info("=== Loop iteration ===")
        orch.run_daily_pipeline(date.today())
        _touch_heartbeat()

        if _SHUTDOWN:
            break

        logger.info("Sleeping for %d hours...", args.interval)
        _sleep_with_shutdown(args.interval * 3600)

    logger.info("Loop exited gracefully")


# =============================================================================
# Comando: all  (daily + backtest)
# =============================================================================


def cmd_all(args):
    logger.info("=== Running full pipeline: daily + backtest ===")
    cmd_daily(args)
    logger.info("")
    cmd_backtest(args)
    logger.info("=== Full pipeline complete ===")


# =============================================================================
# CLI
# =============================================================================

_COMMANDS = {
    "daily": cmd_daily,
    "historical": cmd_historical,
    "backtest": cmd_backtest,
    "loop": cmd_loop,
    "all": cmd_all,
}


def main():
    parser = ArgumentParser(
        description="MLB Predictive System — Unified CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("daily", help="Run daily ETL pipeline")
    p.add_argument("--date", type=str, help="Target date (YYYY-MM-DD, default: today)")

    p = sub.add_parser("historical", help="Run historical data ingest")
    p.add_argument("--start", default="2024-03-28", help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", default="2024-09-30", help="End date (YYYY-MM-DD)")
    p.add_argument("--skip-statcast", action="store_true", help="Skip Statcast ingestion")
    p.add_argument("--skip-weather", action="store_true", help="Skip weather ingestion")
    p.add_argument("--skip-markets", action="store_true", help="Skip historical odds CSV loading")
    p.add_argument("--skip-features", action="store_true", help="Skip rolling stats computation")
    p.add_argument("--rate-limit", type=float, default=0.5, help="Seconds between API calls")
    p.add_argument("--no-checkpoint", action="store_true", help="Disable checkpoint resume")

    p = sub.add_parser("backtest", help="Run walk-forward backtest")
    p.add_argument("--start", default="2024-04-01", help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", default="2024-09-30", help="End date (YYYY-MM-DD)")
    p.add_argument("--bankroll", type=float, default=10000.0, help="Initial bankroll")
    p.add_argument("--iterations", type=int, default=1000, help="Monte Carlo iterations")
    p.add_argument("--models-dir", default="models/backtest", help="Model output directory")
    p.add_argument("--output", default="logs/backtest_report.json", help="Report output path")

    p = sub.add_parser("loop", help="Run ETL in infinite loop (for Docker)")
    p.add_argument("--interval", type=int, default=24, help="Hours between pipeline runs")

    sub.add_parser("all", help="Run daily pipeline then backtest")

    args = parser.parse_args()

    handler = _COMMANDS.get(args.command)
    if handler:
        handler(args)


if __name__ == "__main__":
    main()
