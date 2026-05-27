# =============================================================================
# run_historical_ingest.py
# Ingesta histórica masiva de Statcast, Weather y Features.
# Los datos de mercado se cargan desde CSV en data/historical_odds/.
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================

import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine, text

from etl.config import DATABASE_URL, LOGS_DIR
from etl.ingestors.market_ingestor import MarketIngestor
from etl.orchestrator import ETLOrchestrator

logger = logging.getLogger(__name__)

CHECKPOINT_FILE = os.path.join(LOGS_DIR, "ingest_checkpoint.json")
HISTORICAL_ODDS_DIR = "data/historical_odds"


def _load_checkpoint() -> set:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return set(json.load(f))
    return set()


def _save_checkpoint(done: set):
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(sorted(done), f, indent=2)


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def load_historical_odds_csv(
    db_url: str,
    odds_dir: str = HISTORICAL_ODDS_DIR,
    sportsbook_id: int = 0,
) -> int:
    ingestor = MarketIngestor(db_url)
    total = 0
    if not os.path.isdir(odds_dir):
        logger.warning("Historical odds directory not found: %s", odds_dir)
        return 0
    for fname in sorted(os.listdir(odds_dir)):
        if not fname.lower().endswith(".csv"):
            continue
        fpath = os.path.join(odds_dir, fname)
        logger.info("Loading historical odds from %s", fpath)
        loaded = ingestor.load_historical_odds_from_csv(fpath, sportsbook_id)
        total += loaded
        logger.info("Loaded %d rows from %s", loaded, fname)
    logger.info("Total historical odds rows loaded: %d", total)
    return total


def run_historical_ingest(
    db_url: str,
    start_date: date,
    end_date: date,
    skip_statcast: bool = False,
    skip_weather: bool = False,
    skip_markets: bool = False,
    skip_features: bool = False,
    rate_limit_seconds: float = 0.5,
    checkpoint: bool = True,
):
    logger.info(
        "Starting historical ingest from %s to %s",
        start_date,
        end_date,
    )

    done = _load_checkpoint() if checkpoint else set()
    orch = ETLOrchestrator(db_url)
    market = MarketIngestor(db_url)

    for day in _date_range(start_date, end_date):
        day_str = day.isoformat()
        if checkpoint and day_str in done:
            logger.info("Skipping %s (already in checkpoint)", day_str)
            continue

        logger.info("=== Processing %s ===", day_str)

        try:
            if not skip_statcast:
                logger.info("Loading schedule for %s", day_str)
                orch.load_schedule(day)
                logger.info("Ingesting Statcast for %s", day_str)
                orch.ingest_statcast(day)
            else:
                logger.info("Skipping Statcast for %s", day_str)

            time.sleep(rate_limit_seconds)

            if not skip_weather:
                logger.info("Ingesting weather for %s", day_str)
                orch.ingest_weather(day)
            else:
                logger.info("Skipping weather for %s", day_str)

            time.sleep(rate_limit_seconds)

            if checkpoint:
                done.add(day_str)
                _save_checkpoint(done)

            logger.info("Finished %s", day_str)

        except Exception as e:
            logger.error("Failed on %s: %s", day_str, e, exc_info=True)
            if checkpoint:
                _save_checkpoint(done)
            raise

    if not skip_features:
        logger.info("Computing rolling stats for entire range up to %s", end_date)
        from prediction.feature_pipeline import FeaturePipeline

        fp = FeaturePipeline(db_url)
        fp.run_full_pipeline(end_date)
        logger.info("Feature computation complete")

    if not skip_markets:
        logger.info("Loading historical odds from CSV...")
        total = load_historical_odds_csv(db_url)
        logger.info("Historical odds load complete: %d rows", total)

    logger.info("Historical ingest complete: %s to %s", start_date, end_date)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(description="MLB Predictive System — Historical Data Ingest")
    parser.add_argument(
        "--start",
        type=str,
        default="2024-03-28",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2024-09-30",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--skip-statcast",
        action="store_true",
        help="Skip Statcast play-by-play ingestion",
    )
    parser.add_argument(
        "--skip-weather",
        action="store_true",
        help="Skip weather ingestion",
    )
    parser.add_argument(
        "--skip-markets",
        action="store_true",
        help="Skip historical odds CSV loading",
    )
    parser.add_argument(
        "--skip-features",
        action="store_true",
        help="Skip rolling stats computation",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0.5,
        help="Seconds to wait between API calls (default: 0.5)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable checkpoint resume",
    )

    args = parser.parse_args()

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
