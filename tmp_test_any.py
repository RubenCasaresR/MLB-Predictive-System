from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(
        text("SELECT * FROM (VALUES (1), (2), (3)) AS t(v) WHERE v = ANY(:vals)"),
        {"vals": [1, 3]}
    ).fetchall()
    print("ANY result:", [r[0] for r in result])
