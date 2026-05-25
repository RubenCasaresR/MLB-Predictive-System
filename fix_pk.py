from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    # Drop dependent FK first, then the PK
    conn.execute(text("ALTER TABLE pitches DROP CONSTRAINT IF EXISTS pitches_ab_id_fkey"))
    conn.execute(text("DROP TABLE IF EXISTS at_bats_tmp"))
    conn.execute(text("ALTER TABLE at_bats DROP CONSTRAINT at_bats_pkey CASCADE"))
    conn.execute(text("ALTER TABLE at_bats ADD PRIMARY KEY (ab_id, game_id)"))
    print("Changed PK to (ab_id, game_id)")

    # Also handle the players.throws check constraint issue
    # 'S' (switch hitter) is valid for bats but throws should only be 'L' or 'R'
    # Some players in the API have throws='S' (switch pitcher?), let's widen the check
    conn.execute(text("ALTER TABLE players DROP CONSTRAINT IF EXISTS players_throws_check"))
    conn.execute(text("ALTER TABLE players ADD CONSTRAINT players_throws_check CHECK (throws = ANY (ARRAY['L'::bpchar, 'R'::bpchar, 'S'::bpchar]))"))
    print("Relaxed players.throws check to allow 'S'")

    # Fix primary_position VARCHAR(2) issue - 'TWP' is too long
    conn.execute(text("ALTER TABLE players ALTER COLUMN primary_position TYPE varchar(4)"))
    print("Widened primary_position to varchar(4)")

    pks = conn.execute(text("""
        SELECT a.attname
        FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'at_bats'::regclass AND i.indisprimary
    """)).fetchall()
    print("New PK columns:", [r.attname for r in pks])
