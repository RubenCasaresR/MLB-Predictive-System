from sqlalchemy import create_engine, text, inspect
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
insp = inspect(engine)
cols = insp.get_columns("pitches")
print("=== pitches columns ===")
for c in cols:
    print(f"  {c['name']:30s} {str(c['type']):30s} nullable={c['nullable']} default={c['default']}")

# Check the primary key and constraints
with engine.connect() as conn:
    pk = conn.execute(text("""
        SELECT a.attname, format_type(a.atttypid, a.atttypmod)
        FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'pitches'::regclass AND i.indisprimary
    """)).fetchall()
    print("\n=== pitches PK ===")
    for r in pk:
        print(f"  {r.attname}: {r.format_type}")
