"""Initialize the database schema from schema.sql."""

import logging
import os

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def init_database(db_url: str | None = None):
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "postgresql://mlb_user:@localhost:5432/mlb_predictive")

    logger.info(f"Initializing database at {db_url}")

    if not os.path.exists(SCHEMA_PATH):
        logger.error(f"Schema file not found: {SCHEMA_PATH}")
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    with open(SCHEMA_PATH) as f:
        schema_sql = f.read()

    engine = create_engine(db_url)
    with engine.begin() as conn:
        for statement in schema_sql.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--"):
                conn.execute(text(stmt + ";"))
    engine.dispose()
    logger.info("Database initialized successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()
