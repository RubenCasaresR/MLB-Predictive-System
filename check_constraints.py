from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    constraints = conn.execute(text(
        "SELECT conname, contype, pg_get_constraintdef(oid) "
        "FROM pg_constraint WHERE conrelid = 'players'::regclass"
    )).fetchall()
    print("=== players constraints ===")
    for c in constraints:
        print(f"  {c.conname}: {c.contype} - {c.pg_get_constraintdef}")

    # check check constraints
    checks = conn.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) "
        "FROM pg_constraint WHERE contype = 'c' AND conrelid = 'players'::regclass"
    )).fetchall()
    print("=== players check constraints ===")
    for c in checks:
        print(f"  {c.conname}: {c.pg_get_constraintdef}")
