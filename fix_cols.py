from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    conn.execute(text("ALTER TABLE pitches ALTER COLUMN plate_x TYPE numeric(7,3)"))
    conn.execute(text("ALTER TABLE pitches ALTER COLUMN plate_z TYPE numeric(7,3)"))
    print("Column types widened successfully!")

with engine.connect() as conn:
    print(f"at_bats: {conn.execute(text('SELECT COUNT(*) FROM at_bats')).scalar()}")
    print(f"pitches: {conn.execute(text('SELECT COUNT(*) FROM pitches')).scalar()}")
