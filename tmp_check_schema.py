from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    cols = conn.execute(text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'players' ORDER BY ordinal_position")).fetchall()
    print("=== players table ===")
    for c in cols:
        print("  {} {} nullable={}".format(c.column_name, c.data_type, c.is_nullable))
    print()
    cols2 = conn.execute(text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'at_bats' ORDER BY ordinal_position")).fetchall()
    print("=== at_bats table ===")
    for c in cols2:
        print("  {} {} nullable={}".format(c.column_name, c.data_type, c.is_nullable))
