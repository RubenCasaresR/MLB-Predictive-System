from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'pitches_pitch_id_seq') THEN
                CREATE SEQUENCE pitches_pitch_id_seq;
            END IF;
        END
        $$;
    """))
    conn.execute(text("ALTER TABLE pitches ALTER COLUMN pitch_id SET DEFAULT nextval('pitches_pitch_id_seq')"))
    conn.execute(text("ALTER SEQUENCE pitches_pitch_id_seq OWNED BY pitches.pitch_id"))
    conn.execute(text("SELECT setval('pitches_pitch_id_seq', COALESCE((SELECT max(pitch_id) FROM pitches), 0)::int + 1)"))
    print("pitch_id now has auto-increment!")
