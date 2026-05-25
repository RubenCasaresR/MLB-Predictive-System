from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    conn.execute(text("DELETE FROM pitches"))
    conn.execute(text("DELETE FROM at_bats"))
    print("Tables cleared!")
