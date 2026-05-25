from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    fks = conn.execute(text("""
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.table_name = 'at_bats'
          AND tc.constraint_type = 'FOREIGN KEY'
    """)).fetchall()
    for fk in fks:
        print("FK: {} -> {} -> {}.{}".format(fk.constraint_name, fk.column_name, fk.foreign_table_name, fk.foreign_column_name))
    cnt = conn.execute(text("SELECT COUNT(*) FROM players")).scalar()
    print("Players in DB: {}".format(cnt))
    sample = conn.execute(text("SELECT batter_id FROM at_bats LIMIT 1")).fetchone()
    if sample:
        print("Sample batter_id: {}".format(sample[0]))
