# =============================================================================
# market_ingestor.py
# Ingesta de datos de mercado (líneas de apuestas, ticket%, money%)
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Consume líneas en tiempo real desde APIs de sportsbooks.
# Datos críticos:
#   - Moneyline (abertura y cierre)
#   - Run line (spread)
#   - Over/Under (totals)
#   - Ticket% (porcentaje de boletos por lado)
#   - Money% (porcentaje de dinero por lado)
#   - Líneas de props de jugadores
#
# Frecuencia: cada 60 segundos en ventana pre-game (3h antes)
# =============================================================================

import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

from etl.retry import with_retry


class MarketIngestor:
    def __init__(self, db_url: str, odds_api_key: str = ""):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.odds_api_key = odds_api_key or os.getenv("ODDS_API_KEY", "")
        self.base_url = "https://api.the-odds-api.com/v4"
        self.poll_interval = 60
        logger.info("MarketIngestor initialized")

    @with_retry()
    def fetch_mlb_odds(self, sport: str = "baseball_mlb") -> list[dict]:
        url = f"{self.base_url}/sports/{sport}/odds"
        params = {
            "apiKey": self.odds_api_key,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
            "dateFormat": "iso",
        }

        logger.info(f"Fetching MLB odds from The Odds API")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def parse_odds(self, raw: list[dict]) -> dict:
        games = []
        props = []
        game_events = []

        for event in raw:
            event_id = event.get("id", "")
            home_team = event.get("home_team", "")
            away_team = event.get("away_team", "")
            commence_time = event.get("commence_time", "")

            # Convert team names to abbreviations
            home_abbr = self._team_name_to_abbr(home_team)
            away_abbr = self._team_name_to_abbr(away_team)
            gid = f"{away_abbr}{home_abbr}{commence_time[2:4]}{commence_time[5:7]}{commence_time[8:10]}"

            game_events.append(
                {
                    "id": event_id,
                    "composite_id": gid,
                    "home_team": home_team,
                    "away_team": away_team,
                }
            )

            for bookmaker in event.get("bookmakers", []):
                sb_name = bookmaker.get("title", "")
                sb_id = self._get_sportsbook_id(sb_name)
                timestamp = datetime.now()

                market_data = {"game_id": gid, "sportsbook_id": sb_id, "recorded_at": timestamp}

                for market in bookmaker.get("markets", []):
                    key = market.get("key")
                    outcomes = market.get("outcomes", [])

                    if key == "h2h" and len(outcomes) >= 2:
                        home_odds = next(
                            (o["price"] for o in outcomes if o["name"] == home_team), None
                        )
                        away_odds = next(
                            (o["price"] for o in outcomes if o["name"] == away_team), None
                        )
                        market_data["home_moneyline_open"] = market_data.get(
                            "home_moneyline_close", home_odds
                        )
                        market_data["away_moneyline_open"] = market_data.get(
                            "away_moneyline_close", away_odds
                        )
                        market_data["home_moneyline_close"] = home_odds
                        market_data["away_moneyline_close"] = away_odds

                    elif key == "spreads" and len(outcomes) >= 2:
                        home_spread = next((o for o in outcomes if o["name"] == home_team), None)
                        away_spread = next((o for o in outcomes if o["name"] == away_team), None)
                        if home_spread:
                            market_data["home_runline_close"] = home_spread.get("point")
                            market_data["home_runline_odds_close"] = home_spread.get("price")
                        if away_spread:
                            market_data["away_runline_close"] = away_spread.get("point")
                            market_data["away_runline_odds_close"] = away_spread.get("price")

                    elif key == "totals":
                        over = next((o for o in outcomes if o["name"] == "Over"), None)
                        under = next((o for o in outcomes if o["name"] == "Under"), None)
                        if over:
                            market_data["total_close"] = over.get("point")
                            market_data["total_over_odds_close"] = over.get("price")
                        if under:
                            market_data["total_under_odds_close"] = under.get("price")

                    elif key == "player_strikeouts":
                        for outcome in outcomes:
                            props.append(
                                {
                                    "game_id": gid,
                                    "player_name": outcome.get("participant", ""),
                                    "player_id": None,
                                    "prop_type": "STRIKEOUTS",
                                    "line_value": outcome.get("point"),
                                    "over_odds": outcome.get("price"),
                                    "under_odds": None,
                                    "sportsbook_id": sb_id,
                                    "recorded_at": timestamp,
                                }
                            )

                if market_data.get("home_moneyline_close"):
                    games.append(market_data)

        return {"games": games, "props": props, "game_events": game_events}

    def fetch_public_volume(self, game_id: str) -> dict | None:
        url = f"{self.base_url}/sports/baseball_mlb/events/{game_id}/odds"
        params = {
            "apiKey": self.odds_api_key,
            "regions": "us",
            "markets": "h2h",
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for bookmaker in data.get("bookmakers", []):
                if "DraftKings" in bookmaker.get("title", ""):
                    for market in bookmaker.get("markets", []):
                        outcomes = market.get("outcomes", [])
                        if len(outcomes) >= 2:
                            return {
                                "home_ticket_pct": outcomes[0].get("ticket_pct", 50.0),
                                "home_money_pct": outcomes[0].get("money_pct", 50.0),
                                "away_ticket_pct": outcomes[1].get("ticket_pct", 50.0),
                                "away_money_pct": outcomes[1].get("money_pct", 50.0),
                            }
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch public volume: {e}")
            return None

    def load_to_db(self, parsed: dict):
        games_df = pd.DataFrame(parsed["games"])
        props_df = pd.DataFrame(parsed["props"])

        if not games_df.empty:
            with self.engine.begin() as conn:
                existing = set(
                    row[0] for row in conn.execute(text("SELECT game_id FROM games")).fetchall()
                )
                before = len(games_df)
                games_df = games_df[games_df["game_id"].isin(existing)]
                skipped = before - len(games_df)
                if skipped:
                    logger.info(f"Skipped {skipped} market lines for unknown game_ids")
                if not games_df.empty:
                    games_df.to_sql("market_lines", conn, if_exists="append", index=False)
            logger.info(f"Loaded {len(games_df)} market line snapshots")

        if not props_df.empty:
            with self.engine.begin() as conn:
                props_df.to_sql("player_props_lines_tmp", conn, if_exists="replace", index=False)
                conn.execute(
                    text("""
                    INSERT INTO player_props_lines
                        (game_id, player_id, prop_type, line_value, over_odds, under_odds, sportsbook_id, recorded_at)
                    SELECT
                        t.game_id, COALESCE(t.player_id, p.player_id) AS player_id,
                        t.prop_type, t.line_value, t.over_odds, t.under_odds,
                        t.sportsbook_id, t.recorded_at
                    FROM player_props_lines_tmp t
                    LEFT JOIN players p ON p.full_name = t.player_name AND p.team_id = (
                        SELECT CASE
                            WHEN g.home_team_id = p2.team_id THEN g.home_team_id
                            WHEN g.away_team_id = p2.team_id THEN g.away_team_id
                        END
                        FROM games g WHERE g.game_id = t.game_id
                    )
                    ON CONFLICT (game_id, player_id, prop_type, sportsbook_id, recorded_at) DO NOTHING
                """)
                )
                conn.execute(text("DROP TABLE IF EXISTS player_props_lines_tmp"))
            logger.info(f"Loaded {len(props_df)} props lines")

    def load_historical_odds_from_csv(
        self,
        filepath: str,
        sportsbook_id: int = 0,
    ) -> int:
        """Carga líneas históricas desde CSV y las inserta en market_lines.

        Columnas esperadas del CSV:
            Date, Home Team, Away Team,
            Home Odds Close, Away Odds Close,
            Over/Under Line, Over Odds, Under Odds

        sportsbook_id=0 se usa como 'Historical' genérico.
        Retorna el número de filas insertadas.
        """
        df = pd.read_csv(filepath)
        required = {"Date", "Home Team", "Away Team"}
        if not required.issubset(df.columns):
            logger.error(
                "CSV must contain columns: %s. Found: %s",
                required,
                list(df.columns),
            )
            return 0

        odds_cols = {"Home Odds Close", "Away Odds Close"}
        has_totals = {"Over/Under Line", "Over Odds", "Under Odds"}.issubset(df.columns)
        if not odds_cols.issubset(df.columns):
            logger.error("CSV must contain Home Odds Close and Away Odds Close")
            return 0

        with self.engine.begin() as conn:
            team_map = {
                row[0]: row[1]
                for row in conn.execute(text("SELECT team_id, full_name FROM teams")).fetchall()
            }
            name_to_abbr = {v: k for k, v in team_map.items()}
            name_to_abbr.update({v.lower(): k for k, v in team_map.items()})

        rows = []
        skipped = 0
        for _, row in df.iterrows():
            date_str = str(row["Date"]).strip()
            home_raw = str(row["Home Team"]).strip()
            away_raw = str(row["Away Team"]).strip()

            home_abbr = self._resolve_team_abbr(home_raw, name_to_abbr)
            away_abbr = self._resolve_team_abbr(away_raw, name_to_abbr)
            if not home_abbr or not away_abbr:
                skipped += 1
                continue

            try:
                game_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                try:
                    game_date = datetime.strptime(date_str, "%m/%d/%Y").date()
                except ValueError:
                    skipped += 1
                    continue

            with self.engine.begin() as conn:
                game = conn.execute(
                    text("""
                        SELECT game_id, start_time_et FROM games
                        WHERE game_date = :gd
                          AND home_team_id = :home
                          AND away_team_id = :away
                        LIMIT 1
                    """),
                    {"gd": game_date, "home": home_abbr, "away": away_abbr},
                ).fetchone()

            if not game:
                skipped += 1
                continue

            game_id = game[0]
            recorded_at = game[1] if game[1] else datetime.combine(game_date, datetime.min.time())

            market_row = {
                "game_id": game_id,
                "sportsbook_id": sportsbook_id,
                "recorded_at": recorded_at,
                "home_moneyline_close": int(row["Home Odds Close"]),
                "away_moneyline_close": int(row["Away Odds Close"]),
            }

            if has_totals:
                market_row["total_close"] = float(row["Over/Under Line"])
                market_row["total_over_odds_close"] = int(row["Over Odds"])
                market_row["total_under_odds_close"] = int(row["Under Odds"])

            rows.append(market_row)

        if not rows:
            logger.warning("No rows to insert after matching %d games", skipped)
            return 0

        market_df = pd.DataFrame(rows)
        with self.engine.begin() as conn:
            market_df.to_sql("market_lines", conn, if_exists="append", index=False)

        logger.info(
            "Loaded %d historical odds rows from %s (%d skipped)",
            len(rows),
            filepath,
            skipped,
        )
        return len(rows)

    @staticmethod
    def _resolve_team_abbr(name: str, known: dict) -> str | None:
        name_clean = name.strip().lower()
        abbr = known.get(name) or known.get(name_clean)
        if abbr:
            return abbr
        for full, abbr in known.items():
            if isinstance(full, str) and (
                full.lower().startswith(name_clean) or name_clean.startswith(full.lower())
            ):
                return abbr
        return None

    def _team_name_to_abbr(self, name: str) -> str:
        mapping = {
            "New York Yankees": "NYY",
            "Boston Red Sox": "BOS",
            "Los Angeles Dodgers": "LAD",
            "Houston Astros": "HOU",
            "Atlanta Braves": "ATL",
            "New York Mets": "NYM",
            "Philadelphia Phillies": "PHI",
            "San Diego Padres": "SDP",
            "St. Louis Cardinals": "STL",
            "Chicago Cubs": "CHC",
            "San Francisco Giants": "SFG",
            "Toronto Blue Jays": "TOR",
            "Milwaukee Brewers": "MIL",
            "Baltimore Orioles": "BAL",
            "Tampa Bay Rays": "TBR",
            "Seattle Mariners": "SEA",
            "Texas Rangers": "TEX",
            "Cleveland Guardians": "CLE",
            "Minnesota Twins": "MIN",
            "Arizona Diamondbacks": "ARI",
            "Cincinnati Reds": "CIN",
            "Miami Marlins": "MIA",
            "Kansas City Royals": "KCR",
            "Chicago White Sox": "CHW",
            "Detroit Tigers": "DET",
            "Colorado Rockies": "COL",
            "Pittsburgh Pirates": "PIT",
            "Los Angeles Angels": "LAA",
            "Oakland Athletics": "OAK",
            "Athletics": "OAK",
            "Washington Nationals": "WSN",
        }
        return mapping.get(name, name[:3].upper())

    def _get_sportsbook_id(self, name: str) -> int:
        mapping = {
            "DraftKings": 1,
            "FanDuel": 2,
            "BetMGM": 3,
            "Caesars": 4,
            "PointsBet": 5,
        }
        return mapping.get(name, 0)

    def run_continuous_poll(self, duration_minutes: int = 180):
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        logger.info(f"Starting continuous poll for {duration_minutes} minutes")

        while datetime.now() < end_time:
            try:
                raw = self.fetch_mlb_odds()
                parsed = self.parse_odds(raw)
                self.load_to_db(parsed)
                logger.info(f"Poll cycle complete, {len(parsed['games'])} games")
            except Exception as e:
                logger.error(f"Poll cycle failed: {e}")

            time.sleep(self.poll_interval)


# ============================================================================
# MODO LÍNEA DE COMANDOS
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from etl.config import DATABASE_URL, ODDS_API_KEY

    ingestor = MarketIngestor(DATABASE_URL, ODDS_API_KEY)
    ingestor.run_continuous_poll(duration_minutes=60)
