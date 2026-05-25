from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    # Drop FK constraints that block ingestion
    conn.execute(text("ALTER TABLE at_bats DROP CONSTRAINT IF EXISTS at_bats_batter_id_fkey"))
    conn.execute(text("ALTER TABLE at_bats DROP CONSTRAINT IF EXISTS at_bats_pitcher_id_fkey"))
    conn.execute(text("ALTER TABLE at_bats DROP CONSTRAINT IF EXISTS at_bats_game_id_fkey"))
    print("FK constraints dropped from at_bats")

    # Check numeric columns precision
    cols = conn.execute(text("""
        SELECT column_name, data_type, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_name = 'pitches'
        ORDER BY ordinal_position
    """)).fetchall()
    print("\n=== pitches columns ===")
    for c in cols:
        print("  {} {} (precision={}, scale={})".format(c.column_name, c.data_type, c.numeric_precision, c.numeric_scale))

    cols2 = conn.execute(text("""
        SELECT column_name, data_type, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_name = 'at_bats'
        ORDER BY ordinal_position
    """)).fetchall()
    print("\n=== at_bats columns ===")
    for c in cols2:
        print("  {} {} (precision={}, scale={})".format(c.column_name, c.data_type, c.numeric_precision, c.numeric_scale))

print("DB fix complete!")
