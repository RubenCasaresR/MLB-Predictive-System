import logging, sys
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from etl.config import DATABASE_URL
from etl.ingestors.statcast_ingestor import StatcastIngestor
from datetime import date

ing = StatcastIngestor(db_url=DATABASE_URL)
ing.ingest_date_range(date(2026,3,27), date(2026,5,24))
print("===DONE===")
