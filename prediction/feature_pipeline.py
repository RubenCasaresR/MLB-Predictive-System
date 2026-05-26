# =============================================================================
# feature_pipeline.py
# Pipeline de cómputo batch de características (features)
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Ejecuta diariamente el cálculo de todas las características:
#   - Player Rolling Stats (wOBA, FIP, xERA, etc.)
#   - Team Rolling Stats
#   - Fatigue Scores
#   - Sharp Money Flags
#   - Materializa mv_game_features
# =============================================================================

from typing import List, Optional
from datetime import date, timedelta
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class FeaturePipeline:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        logger.info("FeaturePipeline initialized")

    def compute_player_rolling_stats(self, target_date: date):
        logger.info(f"Computing player rolling stats for {target_date}")
        start_date = target_date - timedelta(days=30)
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO player_rolling_stats (
                    player_id, game_id, as_of_date,
                    woba_30d, fip_30d, k_per_9_30d, bb_per_9_30d, hr_per_9_30d,
                    avg_velo_30d, whiff_pct_30d
                )
                SELECT
                    ab.pitcher_id,
                    g.game_id,
                    g.game_date,
                    ROUND(CAST(AVG(CASE
                        WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 0.70
                        WHEN ab.events = 'Single' THEN 0.90
                        WHEN ab.events = 'Double' THEN 1.25
                        WHEN ab.events = 'Triple' THEN 1.60
                        WHEN ab.events = 'Home Run' THEN 2.00
                        ELSE 0 END) AS NUMERIC), 4) AS woba,
                    ROUND(COALESCE(
                        (13.0 * SUM(CASE WHEN ab.events = 'Home Run' THEN 1 ELSE 0 END)
                         + 3.0 * SUM(CASE WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 1 ELSE 0 END)
                         - 2.0 * SUM(CASE WHEN ab.events IN ('Strikeout','Strikeout Double Play') THEN 1 ELSE 0 END))
                        / NULLIF(SUM(CASE WHEN ab.events IS NOT NULL THEN 1 ELSE 0 END), 0) * 9.0 + 3.10, 4.20
                    ), 4) AS fip,
                    ROUND(
                        SUM(CASE WHEN ab.events IN ('Strikeout','Strikeout Double Play') THEN 1 ELSE 0 END)::NUMERIC
                        / NULLIF(SUM(CASE WHEN ab.events IS NOT NULL THEN 1 ELSE 0 END), 0) * 27.0
                    , 2) AS k_per_9,
                    ROUND(
                        SUM(CASE WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 1 ELSE 0 END)::NUMERIC
                        / NULLIF(SUM(CASE WHEN ab.events IS NOT NULL THEN 1 ELSE 0 END), 0) * 27.0
                    , 2) AS bb_per_9,
                    ROUND(
                        SUM(CASE WHEN ab.events = 'Home Run' THEN 1 ELSE 0 END)::NUMERIC
                        / NULLIF(SUM(CASE WHEN ab.events IS NOT NULL THEN 1 ELSE 0 END), 0) * 27.0
                    , 2) AS hr_per_9,
                    ROUND(CAST(AVG(p.release_speed) AS NUMERIC), 2) AS avg_velo,
                    ROUND(CAST(SUM(CASE WHEN p.whiff = TRUE THEN 1 ELSE 0 END) AS NUMERIC)
                        / NULLIF(SUM(CASE WHEN p.swing = TRUE THEN 1 ELSE 0 END), 0) * 100, 2) AS whiff_pct
                FROM games g
                JOIN at_bats ab ON ab.game_id = g.game_id
                LEFT JOIN pitches p ON p.ab_id = ab.ab_id
                WHERE g.game_date BETWEEN :start AND :end
                  AND g.status = 'FINAL'
                  AND ab.pitcher_id IS NOT NULL
                GROUP BY ab.pitcher_id, g.game_id, g.game_date
                ON CONFLICT (player_id, game_id) DO UPDATE SET
                    woba_30d = EXCLUDED.woba_30d,
                    fip_30d = EXCLUDED.fip_30d,
                    k_per_9_30d = EXCLUDED.k_per_9_30d,
                    bb_per_9_30d = EXCLUDED.bb_per_9_30d,
                    hr_per_9_30d = EXCLUDED.hr_per_9_30d,
                    avg_velo_30d = EXCLUDED.avg_velo_30d,
                    whiff_pct_30d = EXCLUDED.whiff_pct_30d
                """), {"start": start_date, "end": target_date})

        logger.info("Player rolling stats computed")

    def compute_batter_rolling_stats(self, target_date: date):
        logger.info(f"Computing batter rolling stats for {target_date}")
        start_date = target_date - timedelta(days=30)
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO batter_rolling_stats (
                    player_id, game_id, as_of_date,
                    woba_30d, k_pct_30d, bb_pct_30d,
                    hr_per_9_30d, groundball_pct_30d, flyball_pct_30d
                )
                SELECT
                    ab.batter_id,
                    g.game_id,
                    g.game_date,
                    ROUND(CAST(AVG(CASE
                        WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 0.70
                        WHEN ab.events = 'Single' THEN 0.90
                        WHEN ab.events = 'Double' THEN 1.25
                        WHEN ab.events = 'Triple' THEN 1.60
                        WHEN ab.events = 'Home Run' THEN 2.00
                        ELSE 0 END) AS NUMERIC), 4) AS woba,
                    ROUND(CAST(SUM(CASE WHEN ab.events IN ('Strikeout','Strikeout Double Play') THEN 1 ELSE 0 END) AS NUMERIC)
                        / NULLIF(CAST(COUNT(*) AS NUMERIC), 0) * 100, 1) AS k_pct,
                    ROUND(CAST(SUM(CASE WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 1 ELSE 0 END) AS NUMERIC)
                        / NULLIF(CAST(COUNT(*) AS NUMERIC), 0) * 100, 1) AS bb_pct,
                    ROUND(COALESCE(
                        CAST(SUM(CASE WHEN ab.events = 'Home Run' THEN 1 ELSE 0 END) AS NUMERIC)
                        / NULLIF(SUM(CASE WHEN ab.events IS NOT NULL THEN 1 ELSE 0 END), 0) * 9.0, 0
                    ), 2) AS hr_per_9,
                    ROUND(COALESCE(
                        CAST(SUM(CASE WHEN ab.launch_angle IS NOT NULL AND ab.launch_angle < 10 THEN 1 ELSE 0 END) AS NUMERIC)
                        / NULLIF(SUM(CASE WHEN ab.launch_angle IS NOT NULL THEN 1 ELSE 0 END), 0) * 100, 0
                    ), 1) AS gb_pct,
                    ROUND(COALESCE(
                        CAST(SUM(CASE WHEN ab.launch_angle IS NOT NULL AND ab.launch_angle > 25 THEN 1 ELSE 0 END) AS NUMERIC)
                        / NULLIF(SUM(CASE WHEN ab.launch_angle IS NOT NULL THEN 1 ELSE 0 END), 0) * 100, 0
                    ), 1) AS fb_pct
                FROM games g
                JOIN at_bats ab ON ab.game_id = g.game_id
                WHERE g.game_date BETWEEN :start AND :end
                  AND g.status = 'FINAL'
                  AND ab.batter_id IS NOT NULL
                GROUP BY ab.batter_id, g.game_id, g.game_date
                ON CONFLICT (player_id, game_id) DO UPDATE SET
                    woba_30d = EXCLUDED.woba_30d,
                    k_pct_30d = EXCLUDED.k_pct_30d,
                    bb_pct_30d = EXCLUDED.bb_pct_30d,
                    hr_per_9_30d = EXCLUDED.hr_per_9_30d,
                    groundball_pct_30d = EXCLUDED.groundball_pct_30d,
                    flyball_pct_30d = EXCLUDED.flyball_pct_30d
                """), {"start": start_date, "end": target_date})
        logger.info("Batter rolling stats computed")

    def compute_team_rolling_stats(self, target_date: date):
        logger.info(f"Computing team rolling stats for {target_date}")
        start_date = target_date - timedelta(days=30)
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO team_rolling_stats (team_id, game_id, as_of_date, woba_30d)
                SELECT
                    team_id, game_id, game_date,                     ROUND(CAST(AVG(woba) AS NUMERIC), 4)
                FROM (
                    SELECT g.home_team_id AS team_id, g.game_id, g.game_date,
                           CASE
                               WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 0.70
                               WHEN ab.events = 'Single' THEN 0.90
                               WHEN ab.events = 'Double' THEN 1.25
                               WHEN ab.events = 'Triple' THEN 1.60
                               WHEN ab.events = 'Home Run' THEN 2.00
                               ELSE 0 END AS woba
                    FROM games g
                    JOIN at_bats ab ON ab.game_id = g.game_id
                    WHERE g.game_date BETWEEN :start AND :end
                      AND g.status = 'FINAL'
                    UNION ALL
                    SELECT g.away_team_id, g.game_id, g.game_date,
                           CASE
                               WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 0.70
                               WHEN ab.events = 'Single' THEN 0.90
                               WHEN ab.events = 'Double' THEN 1.25
                               WHEN ab.events = 'Triple' THEN 1.60
                               WHEN ab.events = 'Home Run' THEN 2.00
                               ELSE 0 END
                    FROM games g
                    JOIN at_bats ab ON ab.game_id = g.game_id
                    WHERE g.game_date BETWEEN :start AND :end
                      AND g.status = 'FINAL'
                ) team_events
                GROUP BY team_id, game_id, game_date
                ON CONFLICT (team_id, game_id) DO UPDATE SET
                    woba_30d = EXCLUDED.woba_30d
            """), {"start": start_date, "end": target_date})

            conn.execute(text("""
                INSERT INTO team_rolling_stats (team_id, game_id, as_of_date, bullpen_era_30d, bullpen_fip_30d)
                WITH team_pitchers AS (
                    SELECT
                        ab.game_id,
                        g.game_date,
                        CASE WHEN ab.half_inning = 'T' THEN g.home_team_id ELSE g.away_team_id END AS team_id,
                        ab.pitcher_id,
                        FIRST_VALUE(ab.pitcher_id) OVER (
                            PARTITION BY ab.game_id,
                                CASE WHEN ab.half_inning = 'T' THEN g.home_team_id ELSE g.away_team_id END
                            ORDER BY ab.ab_id
                        ) AS starter_pitcher_id
                    FROM games g
                    JOIN at_bats ab ON ab.game_id = g.game_id
                    WHERE g.game_date BETWEEN :start AND :end
                      AND g.status = 'FINAL'
                      AND ab.pitcher_id IS NOT NULL
                ),
                relief_at_bats AS (
                    SELECT
                        tp.team_id,
                        tp.game_id,
                        tp.game_date,
                        ab.events,
                        CASE WHEN tp.team_id = g.home_team_id
                             THEN ab.away_score_after - ab.away_score_before
                             ELSE ab.home_score_after - ab.home_score_before
                        END AS runs
                    FROM team_pitchers tp
                    JOIN at_bats ab ON ab.game_id = tp.game_id AND ab.pitcher_id = tp.pitcher_id
                    JOIN games g ON g.game_id = ab.game_id
                    WHERE tp.pitcher_id != tp.starter_pitcher_id
                ),
                relief_stats AS (
                    SELECT
                        team_id,
                        game_id,
                        game_date,
                        SUM(CASE WHEN events IN ('Strikeout','Strikeout Double Play') THEN 1 ELSE 0 END) AS k,
                        SUM(CASE WHEN events IN ('Walk','Intent Walk','Hit By Pitch') THEN 1 ELSE 0 END) AS bb_hbp,
                        SUM(CASE WHEN events = 'Home Run' THEN 1 ELSE 0 END) AS hr,
                        SUM(CASE WHEN events IN ('Strikeout','Strikeout Double Play','Field Out','Forceout',
                                                    'Grounded Into DP','Sac Fly','Sac Bunt','Double Play',
                                                    'Triple Play','Fielders Choice Out') THEN 1 ELSE 0 END) AS outs,
                        SUM(runs) AS runs
                    FROM relief_at_bats
                    GROUP BY team_id, game_id, game_date
                )
                SELECT
                    team_id, game_id, game_date,
                    LEAST(ROUND(COALESCE(runs::NUMERIC / NULLIF(outs::NUMERIC / 3.0, 0), 0), 2), 99.99) AS bullpen_era,
                    LEAST(ROUND(COALESCE(
                        (13.0 * hr + 3.0 * bb_hbp - 2.0 * k)::NUMERIC / NULLIF(outs::NUMERIC / 3.0, 0) + 3.10,
                        4.50
                    ), 2), 99.99) AS bullpen_fip
                FROM relief_stats
                ON CONFLICT (team_id, game_id) DO UPDATE SET
                    bullpen_era_30d = EXCLUDED.bullpen_era_30d,
                    bullpen_fip_30d = EXCLUDED.bullpen_fip_30d
            """), {"start": start_date, "end": target_date})
        logger.info("Team rolling stats computed")

    def compute_fatigue_scores(self, target_date: date):
        logger.info(f"Computing fatigue scores for {target_date}")
        window_start = target_date - timedelta(days=30)
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE player_rolling_stats
                SET days_rested = sub.days_rested,
                    pitches_last_7d = sub.pitches_last_7d,
                    fatigue_score = sub.fatigue_score
                FROM (
                    SELECT
                        prs.player_id, prs.game_id,
                        COALESCE(g.home_rest_days, g.away_rest_days, 0) AS days_rested,
                        COALESCE(subq.total_pitches, 0) AS pitches_last_7d,
                        CASE WHEN (COALESCE(g.home_rest_days, g.away_rest_days, 0) * 0.10
                            + COALESCE(subq.total_pitches, 0) / 200.0 * 0.30) > 1.0
                            THEN 1.0
                            ELSE COALESCE(g.home_rest_days, g.away_rest_days, 0) * 0.10
                                + COALESCE(subq.total_pitches, 0) / 200.0 * 0.30
                        END AS fatigue_score
                    FROM player_rolling_stats prs
                    JOIN games g ON g.game_id = prs.game_id
                    LEFT JOIN (
                        SELECT
                            ab.pitcher_id,
                            g2.game_id,
                            COUNT(p.pitch_id) AS total_pitches
                        FROM games g2
                        JOIN at_bats ab ON ab.game_id = g2.game_id
                        LEFT JOIN pitches p ON p.ab_id = ab.ab_id
                        WHERE g2.game_date BETWEEN :week_start AND :end
                        GROUP BY ab.pitcher_id, g2.game_id
                    ) subq ON subq.pitcher_id = prs.player_id
                ) sub
                WHERE player_rolling_stats.player_id = sub.player_id
                  AND player_rolling_stats.game_id = sub.game_id
            """), {
                "week_start": target_date - timedelta(days=7),
                "end": target_date,
            })
        logger.info("Fatigue scores computed")

    def detect_sharp_money(self, target_date: date):
        logger.info(f"Detecting sharp money for {target_date}")
        with self.engine.begin() as conn:
            conn.execute(text("""
                WITH lagged AS (
                    SELECT market_id,
                           LAG(home_moneyline_close) OVER (
                               PARTITION BY game_id, sportsbook_id
                               ORDER BY recorded_at
                           ) AS prev_moneyline
                    FROM market_lines
                    WHERE recorded_at::date = :gd
                )
                UPDATE market_lines
                SET sharp_money_flag = detect_sharp_money(
                    home_ticket_pct, home_money_pct, 0, 0.12
                ),
                rlm_flag = detect_rlm(
                    'HOME', home_ticket_pct, home_money_pct,
                    lagged.prev_moneyline,
                    home_moneyline_close
                )
                FROM lagged
                WHERE market_lines.market_id = lagged.market_id
                  AND market_lines.recorded_at::date = :gd
            """), {"gd": target_date})
        logger.info("Sharp money flags updated")

    def refresh_materialized_view(self):
        logger.info("Refreshing materialized view mv_game_features")
        with self.engine.begin() as conn:
            conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_game_features"))
        logger.info("Materialized view refreshed")

    def run_full_pipeline(self, target_date: Optional[date] = None):
        if target_date is None:
            target_date = date.today()

        logger.info(f"=== Running full feature pipeline for {target_date} ===")
        self.compute_player_rolling_stats(target_date)
        self.compute_batter_rolling_stats(target_date)
        self._compute_woba_windows(target_date)
        self.compute_team_rolling_stats(target_date)
        self.compute_fatigue_scores(target_date)
        self.detect_sharp_money(target_date)
        self.refresh_materialized_view()
        logger.info("Feature pipeline complete")

    def _compute_woba_windows(self, target_date: date):
        for window in [7, 14]:
            start = target_date - timedelta(days=window)
            col = f"woba_{window}d"
            with self.engine.begin() as conn:
                conn.execute(text(f"""
                    UPDATE player_rolling_stats
                    SET {col} = sub.woba
                    FROM (
                        SELECT ab.pitcher_id, g.game_id,
                                ROUND(CAST(AVG(CASE
                        WHEN ab.events IN ('Walk','Intent Walk','Hit By Pitch') THEN 0.70
                                    WHEN ab.events = 'Single' THEN 0.90
                                    WHEN ab.events = 'Double' THEN 1.25
                                    WHEN ab.events = 'Triple' THEN 1.60
                                    WHEN ab.events = 'Home Run' THEN 2.00
                                    ELSE 0 END) AS NUMERIC), 4) AS woba
                        FROM games g
                        JOIN at_bats ab ON ab.game_id = g.game_id
                        WHERE g.game_date BETWEEN :start AND :end
                          AND g.status = 'FINAL'
                          AND ab.pitcher_id IS NOT NULL
                        GROUP BY ab.pitcher_id, g.game_id
                    ) sub
                    WHERE player_rolling_stats.player_id = sub.pitcher_id
                      AND player_rolling_stats.game_id = sub.game_id
                """), {"start": start, "end": target_date})


# ============================================================================
# MODO LÍNEA DE COMANDOS
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from etl.config import DATABASE_URL
    pipeline = FeaturePipeline(DATABASE_URL)
    pipeline.run_full_pipeline()
