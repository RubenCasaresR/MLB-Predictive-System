-- =============================================================================
-- MLB Predictive System - Esquema Relacional Completo
-- Versión: 1.0.0
-- Motor: PostgreSQL 15+
-- =============================================================================
-- Este esquema cubre:
--   1. Tablas maestras (teams, players, umpires, stadiums)
--   2. Juegos y play-by-play (games, at_bats, pitches)
--   3. Alineaciones, clima, park factors
--   4. Datos de mercado (moneyline, run line, totals, props)
--   5. Feature store (estadísticas rolling para ML)
--   6. Vistas materializadas para inferencia
--   7. Índices de performance
-- =============================================================================

BEGIN;

-- ============================================================================
-- 1. TABLAS MAESTRAS
-- ============================================================================

CREATE TABLE teams (
    team_id     VARCHAR(3)    PRIMARY KEY,
    full_name   VARCHAR(50)   NOT NULL,
    league      CHAR(1)       NOT NULL CHECK (league IN ('A', 'N')),
    division    VARCHAR(10)   NOT NULL,
    ballpark    VARCHAR(50)   NOT NULL,
    timezone    VARCHAR(30)   NOT NULL,
    created_at  TIMESTAMP     DEFAULT NOW()
);

CREATE TABLE players (
    player_id        INTEGER       PRIMARY KEY,
    full_name        VARCHAR(80)   NOT NULL,
    team_id          VARCHAR(3)    REFERENCES teams(team_id),
    primary_position VARCHAR(2),
    bats             CHAR(1)       CHECK (bats IN ('L', 'R', 'S')),
    throws           CHAR(1)       CHECK (throws IN ('L', 'R')),
    status           VARCHAR(10)   DEFAULT 'ACTIVE',
    debut_date       DATE,
    created_at       TIMESTAMP     DEFAULT NOW()
);

CREATE TABLE umpires (
    umpire_id         INTEGER      PRIMARY KEY,
    full_name         VARCHAR(80)  NOT NULL,
    position          VARCHAR(10)  NOT NULL CHECK (position IN ('HP', '1B', '2B', '3B')),
    sz_top_z          DECIMAL(5,3),
    sz_bottom_z       DECIMAL(5,3),
    called_strike_rate NUMERIC(5,3),
    consistency_score DECIMAL(4,3),
    created_at        TIMESTAMP    DEFAULT NOW()
);

CREATE TABLE stadiums (
    stadium_id    INTEGER      PRIMARY KEY,
    name          VARCHAR(80)  NOT NULL,
    team_id       VARCHAR(3)   REFERENCES teams(team_id),
    altitude_ft   INTEGER,
    capacity      INTEGER,
    wall_distance_lf INTEGER,
    wall_distance_cf INTEGER,
    wall_distance_rf INTEGER,
    wall_height_lf   DECIMAL(4,1),
    wall_height_cf   DECIMAL(4,1),
    wall_height_rf   DECIMAL(4,1),
    pf_overall    DECIMAL(4,3),
    pf_lefthand   DECIMAL(4,3),
    pf_righthand  DECIMAL(4,3),
    pf_hr         DECIMAL(4,3),
    created_at    TIMESTAMP     DEFAULT NOW()
);

-- ============================================================================
-- 2. JUEGOS Y PLAY-BY-PLAY
-- ============================================================================

CREATE TABLE games (
    game_id              VARCHAR(12)  PRIMARY KEY,
    game_date            DATE         NOT NULL,
    season               SMALLINT     NOT NULL,
    home_team_id         VARCHAR(3)   NOT NULL REFERENCES teams(team_id),
    away_team_id         VARCHAR(3)   NOT NULL REFERENCES teams(team_id),
    home_score           SMALLINT,
    away_score           SMALLINT,
    home_probable_pitcher INTEGER     REFERENCES players(player_id),
    away_probable_pitcher INTEGER     REFERENCES players(player_id),
    home_plate_umpire_id INTEGER     REFERENCES umpires(umpire_id),
    start_time_et        TIMESTAMP,
    status               VARCHAR(15)  DEFAULT 'SCHEDULED'
                         CHECK (status IN ('SCHEDULED','PREGAME','IN_PROGRESS','FINAL','POSTPONED','SUSPENDED')),
    venue_id             INTEGER      REFERENCES stadiums(stadium_id),
    attendance           INTEGER,
    duration_min         INTEGER,
    home_travel_miles    INTEGER      DEFAULT 0,
    away_travel_miles    INTEGER      DEFAULT 0,
    home_tz_crossings    SMALLINT     DEFAULT 0,
    away_tz_crossings    SMALLINT     DEFAULT 0,
    home_day_game_after_night  BOOLEAN DEFAULT FALSE,
    away_day_game_after_night  BOOLEAN DEFAULT FALSE,
    home_rest_days       SMALLINT     DEFAULT 0,
    away_rest_days       SMALLINT     DEFAULT 0,
    created_at           TIMESTAMP    DEFAULT NOW(),
    updated_at           TIMESTAMP    DEFAULT NOW()
);

CREATE TABLE at_bats (
    ab_id                     BIGINT        PRIMARY KEY,
    game_id                   VARCHAR(12)   NOT NULL REFERENCES games(game_id),
    inning                    SMALLINT      NOT NULL,
    half_inning               CHAR(1)       NOT NULL CHECK (half_inning IN ('T', 'B')),
    batter_id                 INTEGER       NOT NULL REFERENCES players(player_id),
    pitcher_id                INTEGER       NOT NULL REFERENCES players(player_id),
    outs_before               SMALLINT      NOT NULL,
    home_score_before         SMALLINT      NOT NULL,
    away_score_before         SMALLINT      NOT NULL,
    bases_code                CHAR(3),
    balls                     SMALLINT,
    strikes                   SMALLINT,
    events                    VARCHAR(30),
    description               TEXT,
    is_ab                     BOOLEAN       DEFAULT TRUE,
    woba_denom                BOOLEAN,
    launch_speed              DECIMAL(5,1),
    launch_angle              DECIMAL(4,1),
    estimated_woba_using_speedangle DECIMAL(4,3),
    home_score_after          SMALLINT,
    away_score_after          SMALLINT,
    created_at                TIMESTAMP     DEFAULT NOW()
);

CREATE TABLE pitches (
    pitch_id          BIGINT        PRIMARY KEY,
    ab_id             BIGINT        NOT NULL REFERENCES at_bats(ab_id),
    pitch_number      SMALLINT      NOT NULL,
    pitch_type        VARCHAR(6),
    pitch_name        VARCHAR(20),
    release_speed     DECIMAL(5,1),
    release_spin_rate DECIMAL(6,1),
    release_extension DECIMAL(4,1),
    release_pos_x     DECIMAL(5,2),
    release_pos_z     DECIMAL(5,2),
    zone              SMALLINT,
    strike            BOOLEAN,
    ball              BOOLEAN,
    swing             BOOLEAN,
    whiff             BOOLEAN,
    pfx_x             DECIMAL(5,2),
    pfx_z             DECIMAL(5,2),
    plate_x           DECIMAL(5,3),
    plate_z           DECIMAL(5,3),
    call_description  VARCHAR(30),
    description       TEXT,
    delta_home_win_exp DECIMAL(5,4),
    created_at        TIMESTAMP     DEFAULT NOW()
);

-- ============================================================================
-- 3. ALINEACIONES, CLIMA, PARK FACTORS
-- ============================================================================

CREATE TABLE lineups (
    lineup_id      BIGSERIAL    PRIMARY KEY,
    game_id        VARCHAR(12)  NOT NULL REFERENCES games(game_id),
    team_id        VARCHAR(3)   NOT NULL REFERENCES teams(team_id),
    player_id      INTEGER      NOT NULL REFERENCES players(player_id),
    batting_order  SMALLINT     NOT NULL,
    position       VARCHAR(2)   NOT NULL,
    is_starter     BOOLEAN      DEFAULT TRUE,
    UNIQUE(game_id, team_id, batting_order)
);

CREATE TABLE weather_hourly (
    weather_id       BIGSERIAL    PRIMARY KEY,
    game_id          VARCHAR(12)  NOT NULL REFERENCES games(game_id),
    forecast_hour    TIMESTAMP    NOT NULL,
    temperature      DECIMAL(4,1),
    feels_like       DECIMAL(4,1),
    wind_speed       DECIMAL(4,1),
    wind_direction   VARCHAR(10),
    wind_gust        DECIMAL(4,1),
    humidity         DECIMAL(4,1),
    precipitation_pct DECIMAL(4,1),
    cloud_cover_pct  DECIMAL(4,1),
    condition        VARCHAR(50),
    UNIQUE(game_id, forecast_hour)
);

CREATE TABLE park_factors_monthly (
    pf_id         BIGSERIAL   PRIMARY KEY,
    stadium_id    INTEGER     NOT NULL REFERENCES stadiums(stadium_id),
    season        SMALLINT    NOT NULL,
    month         SMALLINT    NOT NULL,
    pf_single     DECIMAL(4,3),
    pf_double     DECIMAL(4,3),
    pf_triple     DECIMAL(4,3),
    pf_hr         DECIMAL(4,3),
    pf_bb         DECIMAL(4,3),
    pf_k          DECIMAL(4,3),
    pf_woba       DECIMAL(4,3),
    UNIQUE(stadium_id, season, month)
);

-- ============================================================================
-- 4. DATOS DE MERCADO (APUESTAS)
-- ============================================================================

CREATE TABLE sportsbooks (
    book_id      SMALLINT     PRIMARY KEY,
    name         VARCHAR(30)  NOT NULL UNIQUE,
    is_active    BOOLEAN      DEFAULT TRUE,
    scrape_freq_min INTEGER   DEFAULT 1
);

CREATE TABLE market_lines (
    market_id            BIGSERIAL    PRIMARY KEY,
    game_id              VARCHAR(12)  NOT NULL REFERENCES games(game_id),
    sportsbook_id        SMALLINT     NOT NULL REFERENCES sportsbooks(book_id),
    recorded_at          TIMESTAMP    NOT NULL,
    home_moneyline_open   INTEGER,
    home_moneyline_close  INTEGER,
    away_moneyline_open   INTEGER,
    away_moneyline_close  INTEGER,
    home_runline_open     DECIMAL(4,2),
    home_runline_odds_open  INTEGER,
    away_runline_open     DECIMAL(4,2),
    away_runline_odds_open  INTEGER,
    home_runline_close    DECIMAL(4,2),
    home_runline_odds_close INTEGER,
    away_runline_close    DECIMAL(4,2),
    away_runline_odds_close INTEGER,
    total_open            DECIMAL(4,1),
    total_over_odds_open  INTEGER,
    total_under_odds_open INTEGER,
    total_close           DECIMAL(4,1),
    total_over_odds_close INTEGER,
    total_under_odds_close INTEGER,
    home_ticket_pct       DECIMAL(5,2),
    home_money_pct        DECIMAL(5,2),
    away_ticket_pct       DECIMAL(5,2),
    away_money_pct        DECIMAL(5,2),
    home_implied_prob     DECIMAL(5,4),
    away_implied_prob     DECIMAL(5,4),
    sharp_money_flag      BOOLEAN DEFAULT FALSE,
    rlm_flag              BOOLEAN DEFAULT FALSE,
    UNIQUE(game_id, sportsbook_id, recorded_at)
);

CREATE TABLE player_props_lines (
    prop_id       BIGSERIAL    PRIMARY KEY,
    game_id       VARCHAR(12)  NOT NULL REFERENCES games(game_id),
    player_id     INTEGER      NOT NULL REFERENCES players(player_id),
    prop_type     VARCHAR(30)  NOT NULL
                  CHECK (prop_type IN ('STRIKEOUTS','HITS','HR','RBIS','WALKS','SINGLES','DOUBLES','TOTAL_BASES','PITCHING_WINS')),
    line_value    DECIMAL(4,1) NOT NULL,
    over_odds     INTEGER      NOT NULL,
    under_odds    INTEGER      NOT NULL,
    sportsbook_id SMALLINT     NOT NULL REFERENCES sportsbooks(book_id),
    recorded_at   TIMESTAMP    NOT NULL,
    UNIQUE(game_id, player_id, prop_type, sportsbook_id, recorded_at)
);

-- ============================================================================
-- 5. FEATURE STORE (ESTADÍSTICAS ROLLING PARA ML)
-- ============================================================================

CREATE TABLE player_rolling_stats (
    stat_id            BIGSERIAL    PRIMARY KEY,
    player_id          INTEGER      NOT NULL REFERENCES players(player_id),
    game_id            VARCHAR(12)  NOT NULL REFERENCES games(game_id),
    as_of_date         DATE         NOT NULL,
    -- Bateo (rolling windows: 7d, 14d, 30d, season)
    woba_7d            DECIMAL(4,3),
    woba_14d           DECIMAL(4,3),
    woba_30d           DECIMAL(4,3),
    woba_season        DECIMAL(4,3),
    woba_vs_lhp_30d    DECIMAL(4,3),
    woba_vs_rhp_30d    DECIMAL(4,3),
    xwoba_30d          DECIMAL(4,3),
    xwoba_season       DECIMAL(4,3),
    slg_30d            DECIMAL(4,3),
    obp_30d            DECIMAL(4,3),
    hard_hit_pct_30d   DECIMAL(4,1),
    barrel_pct_30d     DECIMAL(4,1),
    k_pct_30d          DECIMAL(4,1),
    bb_pct_30d         DECIMAL(4,1),
    launch_angle_avg_30d DECIMAL(4,1),
    -- Pitcheo
    fip_30d            DECIMAL(4,2),
    fip_season         DECIMAL(4,2),
    xera_30d           DECIMAL(4,2),
    xera_season        DECIMAL(4,2),
    si_era_30d         DECIMAL(4,2),
    k_per_9_30d        DECIMAL(4,1),
    bb_per_9_30d       DECIMAL(4,1),
    hr_per_9_30d       DECIMAL(4,2),
    k_pct_pitch_30d    DECIMAL(4,1),
    bb_pct_pitch_30d   DECIMAL(4,1),
    whiff_pct_30d      DECIMAL(4,1),
    swing_pct_30d      DECIMAL(4,1),
    o_contact_pct_30d  DECIMAL(4,1),
    avg_velo_30d       DECIMAL(5,1),
    avg_velo_fb_30d    DECIMAL(5,1),
    avg_spin_30d       DECIMAL(6,1),
    avg_spin_fb_30d    DECIMAL(6,1),
    velo_drop_3g       DECIMAL(5,1),
    spin_drop_3g       DECIMAL(6,1),
    -- Fatiga
    days_rested        SMALLINT,
    pitches_last_7d    INTEGER,
    innings_last_7d    DECIMAL(4,1),
    tz_crossings_3d    SMALLINT,
    travel_miles_3d    INTEGER,
    day_game_after_night BOOLEAN DEFAULT FALSE,
    fatigue_score      DECIMAL(4,3),
    -- Mercado
    sharp_money_any    BOOLEAN,
    UNIQUE(player_id, game_id)
);

CREATE TABLE batter_rolling_stats (
    stat_id            BIGSERIAL    PRIMARY KEY,
    player_id          INTEGER      NOT NULL REFERENCES players(player_id),
    game_id            VARCHAR(12)  NOT NULL REFERENCES games(game_id),
    as_of_date         DATE         NOT NULL,
    woba_30d           DECIMAL(4,3),
    k_pct_30d          DECIMAL(4,1),
    bb_pct_30d         DECIMAL(4,1),
    hr_per_9_30d       DECIMAL(4,2),
    groundball_pct_30d DECIMAL(4,1),
    flyball_pct_30d    DECIMAL(4,1),
    UNIQUE(player_id, game_id)
);

CREATE TABLE team_rolling_stats (
    stat_id           BIGSERIAL    PRIMARY KEY,
    team_id           VARCHAR(3)   NOT NULL REFERENCES teams(team_id),
    game_id           VARCHAR(12)  NOT NULL REFERENCES games(game_id),
    as_of_date        DATE         NOT NULL,
    woba_30d          DECIMAL(4,3),
    woba_vs_lhp_30d   DECIMAL(4,3),
    woba_vs_rhp_30d   DECIMAL(4,3),
    slg_30d           DECIMAL(4,3),
    obp_30d           DECIMAL(4,3),
    k_pct_30d         DECIMAL(4,1),
    bb_pct_30d        DECIMAL(4,1),
    hard_hit_pct_30d  DECIMAL(4,1),
    barrel_pct_30d    DECIMAL(4,1),
    team_fip_30d      DECIMAL(4,2),
    whiff_pct_30d     DECIMAL(4,1),
    bullpen_era_30d    DECIMAL(4,2),
    bullpen_fip_30d    DECIMAL(4,2),
    record_last_10    VARCHAR(10),
    run_diff_30d      INTEGER,
    UNIQUE(team_id, game_id)
);

-- ============================================================================
-- 6. VISTAS MATERIALIZADAS
-- ============================================================================

-- Vista principal para inferencia del modelo
CREATE MATERIALIZED VIEW mv_game_features AS
SELECT
    g.game_id,
    g.game_date,
    g.season,
    g.home_team_id,
    g.away_team_id,
    g.home_score,
    g.away_score,

    -- Pitcher matchup
    hp.player_id        AS home_pitcher_id,
    hp.full_name        AS home_pitcher_name,
    hp.throws           AS home_pitcher_throws,
    hrs.avg_velo_30d    AS home_pitcher_velo,
    hrs.avg_spin_30d    AS home_pitcher_spin,
    hrs.whiff_pct_30d   AS home_pitcher_whiff_pct,
    hrs.k_per_9_30d     AS home_pitcher_k9,
    hrs.bb_per_9_30d    AS home_pitcher_bb9,
    hrs.fip_30d         AS home_pitcher_fip,
    hrs.xera_30d        AS home_pitcher_xera,
    hrs.days_rested     AS home_pitcher_rest,
    hrs.velo_drop_3g    AS home_pitcher_velo_drop,
    hrs.spin_drop_3g    AS home_pitcher_spin_drop,
    hrs.pitches_last_7d AS home_pitcher_pitch_load,

    ap.player_id        AS away_pitcher_id,
    ap.full_name        AS away_pitcher_name,
    ap.throws           AS away_pitcher_throws,
    ars.avg_velo_30d    AS away_pitcher_velo,
    ars.avg_spin_30d    AS away_pitcher_spin,
    ars.whiff_pct_30d   AS away_pitcher_whiff_pct,
    ars.k_per_9_30d     AS away_pitcher_k9,
    ars.bb_per_9_30d    AS away_pitcher_bb9,
    ars.fip_30d         AS away_pitcher_fip,
    ars.xera_30d        AS away_pitcher_xera,
    ars.days_rested     AS away_pitcher_rest,
    ars.velo_drop_3g    AS away_pitcher_velo_drop,
    ars.spin_drop_3g    AS away_pitcher_spin_drop,
    ars.pitches_last_7d AS away_pitcher_pitch_load,

    -- Team hitting
    hts.woba_30d        AS home_team_woba,
    hts.woba_vs_lhp_30d AS home_team_woba_vs_lhp,
    hts.woba_vs_rhp_30d AS home_team_woba_vs_rhp,
    hts.k_pct_30d       AS home_team_k_pct,
    hts.barrel_pct_30d  AS home_team_barrel_pct,
    hts.hard_hit_pct_30d AS home_team_hard_hit_pct,

    ats.woba_30d        AS away_team_woba,
    ats.woba_vs_lhp_30d AS away_team_woba_vs_lhp,
    ats.woba_vs_rhp_30d AS away_team_woba_vs_rhp,
    ats.k_pct_30d       AS away_team_k_pct,
    ats.barrel_pct_30d  AS away_team_barrel_pct,
    ats.hard_hit_pct_30d AS away_team_hard_hit_pct,

    -- Fatigue
    g.away_tz_crossings,
    g.away_travel_miles,
    g.away_day_game_after_night,
    g.away_rest_days,
    g.home_rest_days,

    -- Park
    pf.pf_hr            AS park_hr_factor,
    pf.pf_woba          AS park_woba_factor,
    pf.pf_k             AS park_k_factor,

    -- Weather
    w.temperature,
    w.wind_speed,
    w.wind_direction,
    w.precipitation_pct,

    -- Market (latest recorded line pre-game)
    ml.home_moneyline_close,
    ml.away_moneyline_close,
    ml.total_close,
    ml.home_implied_prob,
    ml.away_implied_prob,
    ml.sharp_money_flag,
    ml.rlm_flag,
    ml.home_ticket_pct,
    ml.home_money_pct,

    -- Umpire
    u.full_name         AS home_plate_umpire,
    u.called_strike_rate AS umpire_cs_rate

FROM games g
LEFT JOIN players hp ON hp.player_id = g.home_probable_pitcher
LEFT JOIN players ap ON ap.player_id = g.away_probable_pitcher
LEFT JOIN player_rolling_stats hrs ON hrs.player_id = g.home_probable_pitcher AND hrs.game_id = g.game_id
LEFT JOIN player_rolling_stats ars ON ars.player_id = g.away_probable_pitcher AND ars.game_id = g.game_id
LEFT JOIN team_rolling_stats hts ON hts.team_id = g.home_team_id AND hts.game_id = g.game_id
LEFT JOIN team_rolling_stats ats ON ats.team_id = g.away_team_id AND ats.game_id = g.game_id
LEFT JOIN park_factors_monthly pf ON pf.stadium_id = g.venue_id
    AND pf.season = g.season
    AND pf.month = EXTRACT(MONTH FROM g.game_date)
LEFT JOIN weather_hourly w ON w.game_id = g.game_id
    AND w.forecast_hour = date_trunc('hour', g.start_time_et)
LEFT JOIN market_lines ml ON ml.game_id = g.game_id
    AND ml.recorded_at = (
        SELECT MAX(ml2.recorded_at) FROM market_lines ml2
        WHERE ml2.game_id = g.game_id AND ml2.recorded_at <= g.start_time_et
    )
LEFT JOIN umpires u ON u.umpire_id = g.home_plate_umpire_id;

CREATE UNIQUE INDEX idx_mv_game_features ON mv_game_features(game_id);

-- ============================================================================
-- 7. ÍNDICES DE PERFORMANCE
-- ============================================================================

CREATE INDEX idx_atbats_game     ON at_bats(game_id);
CREATE INDEX idx_atbats_pitcher  ON at_bats(pitcher_id);
CREATE INDEX idx_atbats_batter   ON at_bats(batter_id);
CREATE INDEX idx_pitches_ab      ON pitches(ab_id);
CREATE INDEX idx_lineups_game    ON lineups(game_id, team_id);
CREATE INDEX idx_weather_game    ON weather_hourly(game_id);
CREATE INDEX idx_market_game_ts  ON market_lines(game_id, recorded_at DESC);
CREATE INDEX idx_market_sb_ts    ON market_lines(sportsbook_id, recorded_at DESC);
CREATE INDEX idx_props_game      ON player_props_lines(game_id, prop_type);
CREATE INDEX idx_rolling_player  ON player_rolling_stats(player_id, as_of_date DESC);
CREATE INDEX idx_rolling_team    ON team_rolling_stats(team_id, as_of_date DESC);

-- ============================================================================
-- 8. FUNCIONES Y TRIGGERS
-- ============================================================================

-- Trigger para actualizar updated_at en games
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_games_updated
    BEFORE UPDATE ON games
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();

-- Tabla de resultados de simulación Monte Carlo
CREATE TABLE IF NOT EXISTS simulation_results (
    game_id          VARCHAR(30) PRIMARY KEY REFERENCES games(game_id),
    home_win_prob    DECIMAL(6,4) NOT NULL,
    away_win_prob    DECIMAL(6,4) NOT NULL,
    mean_home_runs   DECIMAL(6,2) DEFAULT 0,
    mean_away_runs   DECIMAL(6,2) DEFAULT 0,
    std_home_runs    DECIMAL(6,2) DEFAULT 0,
    std_away_runs    DECIMAL(6,2) DEFAULT 0,
    extra_innings_prob DECIMAL(6,4) DEFAULT 0,
    walkoff_prob     DECIMAL(6,4) DEFAULT 0,
    run_distribution JSONB,
    n_iterations     INTEGER DEFAULT 10000,
    computed_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_simulation_results_game_id
    ON simulation_results(game_id);

-- Tabla de alertas del sistema
CREATE TABLE IF NOT EXISTS alerts (
    alert_id         BIGSERIAL PRIMARY KEY,
    game_id          VARCHAR(30) REFERENCES games(game_id),
    team_id          VARCHAR(3),
    signal_type      VARCHAR(30) NOT NULL,
    confidence       DECIMAL(5,4) DEFAULT 0,
    message          TEXT,
    details          JSONB,
    is_read          BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_unread
    ON alerts(is_read, created_at DESC)
    WHERE is_read = FALSE;

-- Tabla de resultados de apuestas aprobadas
CREATE TABLE IF NOT EXISTS approved_bets (
    bet_id           BIGSERIAL PRIMARY KEY,
    game_id          VARCHAR(30) REFERENCES games(game_id),
    team             VARCHAR(50),
    opponent         VARCHAR(50),
    sportsbook       VARCHAR(50),
    market_type      VARCHAR(30),
    odds             INTEGER,
    edge             DECIMAL(6,4),
    kelly_fraction   DECIMAL(6,4),
    recommended_stake DECIMAL(10,2),
    confidence       DECIMAL(5,4),
    status           VARCHAR(20) DEFAULT 'pending',
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approved_bets_status
    ON approved_bets(status, created_at DESC);

-- Tabla de usuarios para autenticación
CREATE TABLE IF NOT EXISTS users (
    user_id          BIGSERIAL PRIMARY KEY,
    username         VARCHAR(50) UNIQUE NOT NULL,
    hashed_password  VARCHAR(255) NOT NULL,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Función para calcular implied probability de odds americanos
CREATE OR REPLACE FUNCTION american_to_implied(odds INTEGER)
RETURNS DECIMAL(5,4) AS $$
BEGIN
    IF odds > 0 THEN
        RETURN ROUND(100.0 / (odds + 100)::DECIMAL, 4);
    ELSE
        RETURN ROUND(ABS(odds)::DECIMAL / (ABS(odds) + 100)::DECIMAL, 4);
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Función para detectar Sharp Money
CREATE OR REPLACE FUNCTION detect_sharp_money(
    p_ticket_pct DECIMAL,
    p_money_pct DECIMAL,
    p_line_movement INTEGER,
    p_threshold DECIMAL DEFAULT 0.15
) RETURNS BOOLEAN AS $$
DECLARE
    discrepancy DECIMAL;
BEGIN
    -- Sharp Money: dinero significativamente diferente al volumen de boletos
    discrepancy := ABS(p_ticket_pct - p_money_pct);
    RETURN discrepancy >= p_threshold;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Función para detectar Reverse Line Movement
CREATE OR REPLACE FUNCTION detect_rlm(
    team VARCHAR(3),
    p_ticket_pct DECIMAL,
    p_money_pct DECIMAL,
    line_previous INTEGER,
    line_current INTEGER
) RETURNS BOOLEAN AS $$
BEGIN
    -- RLM: el público apuesta mayoritario a un lado (ticket%)
    -- pero el dinero o la línea se mueven en dirección contraria
    IF p_ticket_pct > 50 AND p_money_pct < 50 THEN
        -- Público en Team A, dinero en Team B
        IF line_current < line_previous THEN
            -- Línea se mueve hacia Team B (contra el público)
            RETURN TRUE;
        END IF;
    END IF;
    RETURN FALSE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- Tablas faltantes (definidas originalmente solo en Python, nunca en schema.sql)
-- ============================================================================

CREATE TABLE IF NOT EXISTS bankroll_state (
    user_id         VARCHAR(50)  PRIMARY KEY,
    current         DECIMAL(12,2) NOT NULL,
    peak            DECIMAL(12,2) NOT NULL,
    total_wagered   DECIMAL(14,2) DEFAULT 0,
    total_profit    DECIMAL(14,2) DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bet_history (
    bet_id          BIGSERIAL    PRIMARY KEY,
    user_id         VARCHAR(50)  NOT NULL,
    game_id         VARCHAR(12),
    team            VARCHAR(50),
    market_type     VARCHAR(30),
    odds            INTEGER,
    stake           DECIMAL(8,2),
    won             BOOLEAN,
    profit_loss     DECIMAL(8,2),
    kelly_pct       DECIMAL(5,4),
    edge            DECIMAL(5,4),
    placed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled_at      TIMESTAMP
);

COMMIT;
