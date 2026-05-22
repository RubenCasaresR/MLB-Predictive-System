-- Migration 001: Initial Schema
-- Aplica en orden: schema.sql completo
-- Uso: psql -U postgres -d mlb_predictive -f 001_initial_schema.sql

BEGIN;

-- Verificar que no exista ya
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'teams') THEN
        RAISE EXCEPTION 'Schema already applied. Aborting.';
    END IF;
END $$;

-- Cargar schema principal
\i ../schema.sql

-- Seed data inicial
INSERT INTO sportsbooks (book_id, name) VALUES
    (1, 'DraftKings'),
    (2, 'FanDuel'),
    (3, 'BetMGM'),
    (4, 'Caesars'),
    (5, 'PointsBet');

COMMIT;
