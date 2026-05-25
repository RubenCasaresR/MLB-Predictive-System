from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    # Add game_id to pitches table
    conn.execute(text("ALTER TABLE pitches ADD COLUMN IF NOT EXISTS game_id VARCHAR(20)"))
    print("Added game_id to pitches")
    
    # Verify columns
    cols = conn.execute(text("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'pitches'
        ORDER BY ordinal_position
    """)).fetchall()
    print("\n=== pitches columns ===")
    for c in cols:
        print(f"  {c.column_name:25s} {c.data_type:15s} nullable={c.is_nullable}")
