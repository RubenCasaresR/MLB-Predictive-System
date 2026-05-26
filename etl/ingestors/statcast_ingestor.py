# =============================================================================
# statcast_ingestor.py
# Ingesta de datos Statcast (play-by-play MLB)
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Consume datos diarios de Statcast vía API o archivos CSV.
# Realiza limpieza, validación y carga en PostgreSQL.
#
# Flujo:
#   1. Obtener juegos del día (SCHEDULED, IN_PROGRESS, FINAL)
#   2. Para cada juego FINAL: descargar play-by-play completo
#   3. Parsear at_bats y pitches
#   4. Validar consistencia (score, outs, counts)
#   5. Upsert en base de datos
# =============================================================================

import csv
import json
import logging
import os
from collections.abc import Generator
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

from etl.retry import with_retry


class StatcastIngestor:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.base_url_v11 = "https://statsapi.mlb.com/api/v1.1"
        self.engine = create_engine(db_url)
        self._team_id_to_abbr = self._normalize_team_map(self._fetch_team_map())
        logger.info("StatcastIngestor initialized")

    @staticmethod
    def _normalize_team_map(raw: dict[int, str]) -> dict[int, str]:
        fix = {
            "ATH": "OAK",
            "SD": "SDP",
            "SF": "SFG",
            "AZ": "ARI",
            "CWS": "CHW",
            "WSH": "WSN",
            "KC": "KCR",
            "TB": "TBR",
        }
        return {tid: fix.get(abbr, abbr) for tid, abbr in raw.items()}

    def _fetch_team_map(self) -> dict[int, str]:
        try:
            resp = requests.get(f"{self.base_url}/teams?sportId=1", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return {t["id"]: t["abbreviation"] for t in data.get("teams", [])}
        except Exception as e:
            logger.warning(f"Could not fetch team map: {e}, falling back to hardcoded names")
            return {}

    @staticmethod
    def _map_status(detailed_state: str) -> str:
        mapping = {
            "Scheduled": "SCHEDULED",
            "Pre Game": "PREGAME",
            "Pre-Game": "PREGAME",
            "Warmup": "PREGAME",
            "In Progress": "IN_PROGRESS",
            "Final": "FINAL",
            "Postponed": "POSTPONED",
            "Suspended": "SUSPENDED",
        }
        return mapping.get(detailed_state, detailed_state.upper().replace(" ", "_"))

    @with_retry()
    def fetch_daily_games(self, game_date: date | None = None) -> pd.DataFrame:
        if game_date is None:
            game_date = date.today()

        url = f"{self.base_url}/schedule"
        params = {
            "date": game_date.isoformat(),
            "sportId": 1,
            "hydrate": "probablePitcher",
        }

        logger.info(f"Fetching schedule for {game_date}")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        games = []
        default_map = {
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
            "Washington Nationals": "WSN",
        }
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                home_team_id = game["teams"]["home"]["team"]["id"]
                away_team_id = game["teams"]["away"]["team"]["id"]
                home_abbr = self._team_id_to_abbr.get(home_team_id) or default_map.get(
                    game["teams"]["home"]["team"]["name"],
                    game["teams"]["home"]["team"]["name"][:3].upper(),
                )
                away_abbr = self._team_id_to_abbr.get(away_team_id) or default_map.get(
                    game["teams"]["away"]["team"]["name"],
                    game["teams"]["away"]["team"]["name"][:3].upper(),
                )
                gid = f"{away_abbr}{home_abbr}{game_date.strftime('%y%m%d')}"
                games.append(
                    {
                        "game_id": gid,
                        "mlb_game_pk": game.get("gamePk"),
                        "game_date": game_date.isoformat(),
                        "home_team_id": home_abbr,
                        "away_team_id": away_abbr,
                        "home_probable_pitcher": game["teams"]["home"]
                        .get("probablePitcher", {})
                        .get("id"),
                        "away_probable_pitcher": game["teams"]["away"]
                        .get("probablePitcher", {})
                        .get("id"),
                        "status": self._map_status(game["status"]["detailedState"]),
                        "venue_id": game.get("venue", {}).get("id"),
                        "start_time_et": game.get("gameDate"),
                    }
                )

        return pd.DataFrame(games)

    @with_retry(max_retries=3, base_delay=2.0)
    def fetch_game_playbyplay(self, game_pk: int) -> dict:
        url = f"{self.base_url_v11}/game/{game_pk}/feed/live"

        logger.info(f"Fetching play-by-play for game {game_pk}")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("liveData", {}).get("plays", {})

    def parse_playbyplay(self, raw_data: dict, game_id: str) -> dict:
        at_bats = []
        pitches = []
        prev_home_score = 0
        prev_away_score = 0

        for play in raw_data.get("allPlays", []):
            result = play.get("result", {})
            home_after = result.get("homeScore", prev_home_score)
            away_after = result.get("awayScore", prev_away_score)

            at_bat_index = play.get("atBatIndex")
            if at_bat_index is None:
                prev_home_score = home_after
                prev_away_score = away_after
                continue

            ab = self._parse_at_bat(play, game_id, at_bat_index, prev_home_score, prev_away_score)
            if ab is None:
                prev_home_score = home_after
                prev_away_score = away_after
                continue
            at_bats.append(ab)

            prev_home_score = home_after
            prev_away_score = away_after

            for pitch_data in play.get("playEvents", []):
                if pitch_data.get("isPitch"):
                    pitch = self._parse_pitch(pitch_data, ab["ab_id"], game_id)
                    if pitch:
                        pitches.append(pitch)

        return {"at_bats": at_bats, "pitches": pitches}

    def _parse_at_bat(
        self,
        play: dict,
        game_id: str,
        at_bat_index: int,
        prev_home_score: int = 0,
        prev_away_score: int = 0,
    ) -> dict | None:
        try:
            result = play.get("result", {})
            matchup = play.get("matchup", {})
            about = play.get("about", {})

            count = play.get("count", {})
            event = result.get("event")
            is_ab = result.get("isOut") is not None
            non_woba = event in (
                "intentional_walk",
                "sac_bunt",
                "sac_fly",
                "sac_fly_double_play",
                "catcher_interference",
                "fielders_choice_out",
            )
            return {
                "ab_id": at_bat_index,
                "game_id": game_id,
                "inning": about.get("inning"),
                "half_inning": "T" if about.get("halfInning") == "top" else "B",
                "batter_id": matchup.get("batter", {}).get("id"),
                "pitcher_id": matchup.get("pitcher", {}).get("id"),
                "outs_before": count.get("outs", about.get("outs")),
                "home_score_before": prev_home_score,
                "away_score_before": prev_away_score,
                "bases_code": self._get_bases_code(result.get("beforePitch", {})),
                "balls": count.get("balls"),
                "strikes": count.get("strikes"),
                "events": event,
                "description": result.get("description"),
                "is_ab": is_ab,
                "woba_denom": is_ab and not non_woba,
                "launch_speed": result.get("launchSpeed"),
                "launch_angle": result.get("launchAngle"),
                "estimated_woba_using_speedangle": result.get("estimatedWobaUsingSpeedAngle"),
                "home_score_after": result.get("homeScore", prev_home_score),
                "away_score_after": result.get("awayScore", prev_away_score),
            }
        except Exception as e:
            logger.warning(f"Error parsing at_bat: {e}")
            return None

    def _parse_pitch(self, pitch: dict, ab_id: int, game_id: str) -> dict | None:
        try:
            return {
                "ab_id": ab_id,
                "game_id": game_id,
                "pitch_number": pitch.get("pitchNumber"),
                "pitch_type": pitch.get("details", {}).get("type", {}).get("code"),
                "pitch_name": pitch.get("details", {}).get("type", {}).get("description"),
                "release_speed": pitch.get("pitchData", {}).get("startSpeed"),
                "release_spin_rate": pitch.get("pitchData", {}).get("breaks", {}).get("spinRate"),
                "release_extension": pitch.get("pitchData", {}).get("extension"),
                "zone": pitch.get("zone"),
                "strike": pitch.get("details", {}).get("isStrike"),
                "ball": pitch.get("details", {}).get("isBall"),
                "swing": pitch.get("details", {}).get("isSwing"),
                "whiff": pitch.get("details", {}).get("isSwingAndMiss", False),
                "pfx_x": pitch.get("pitchData", {}).get("pfxX"),
                "pfx_z": pitch.get("pitchData", {}).get("pfxZ"),
                "plate_x": pitch.get("pitchData", {}).get("coordinates", {}).get("x"),
                "plate_z": pitch.get("pitchData", {}).get("coordinates", {}).get("z"),
                "call_description": pitch.get("details", {}).get("call", {}).get("description"),
                "description": pitch.get("details", {}).get("description"),
            }
        except Exception as e:
            logger.warning(f"Error parsing pitch: {e}")
            return None

    def _get_bases_code(self, before_pitch: dict) -> str:
        bases = []
        for base in ["first", "second", "third"]:
            bases.append("1" if before_pitch.get(f"{base}Base") else "0")
        return "".join(bases)

    def _ensure_players(self, player_ids: set):
        if not player_ids:
            return
        ids_list = list(player_ids)
        placeholders = ",".join(f":id_{i}" for i in range(len(ids_list)))
        params = {f"id_{i}": pid for i, pid in enumerate(ids_list)}
        with self.engine.connect() as conn:
            existing = {
                r[0]
                for r in conn.execute(
                    text(f"SELECT player_id FROM players WHERE player_id IN ({placeholders})"),
                    params,
                ).fetchall()
            }
        missing = player_ids - set(existing)
        if not missing:
            return
        for pid in sorted(missing):
            try:
                url = f"{self.base_url}/people/{pid}"
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                people = resp.json().get("people", [])
                if not people:
                    continue
                p = people[0]
                pos = (p.get("primaryPosition") or {}).get("abbreviation")
                with self.engine.begin() as conn:
                    conn.execute(
                        text("""
                        INSERT INTO players (player_id, full_name, primary_position, bats, throws, status)
                        VALUES (:pid, :name, :pos, :bats, :throws, :status)
                        ON CONFLICT (player_id) DO NOTHING
                    """),
                        {
                            "pid": pid,
                            "name": p.get("fullName", f"Player {pid}"),
                            "pos": pos,
                            "bats": (p.get("batSide") or {}).get("code"),
                            "throws": (p.get("pitchHand") or {}).get("code"),
                            "status": (p.get("status") or {}).get("code"),
                        },
                    )
            except Exception as e:
                logger.warning(f"Could not fetch player {pid}: {e}")

    def load_to_database(self, game_data: dict, game_id: str):
        at_bats_df = pd.DataFrame(game_data["at_bats"])
        pitches_df = pd.DataFrame(game_data["pitches"])

        if at_bats_df.empty:
            logger.warning(f"No at_bats for {game_id}, skipping")
            return

        player_ids = set()
        for ab in game_data["at_bats"]:
            if ab.get("batter_id"):
                player_ids.add(ab["batter_id"])
            if ab.get("pitcher_id"):
                player_ids.add(ab["pitcher_id"])
        self._ensure_players(player_ids)

        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT COUNT(*) FROM at_bats WHERE game_id = :gid"),
                {"gid": game_id},
            ).scalar()

            if existing > 0:
                logger.info(f"At_bats already exist for {game_id}, upserting")
                at_bats_df.to_sql("at_bats_tmp", conn, if_exists="replace", index=False)
                cols = [
                    "ab_id",
                    "game_id",
                    "inning",
                    "half_inning",
                    "batter_id",
                    "pitcher_id",
                    "outs_before",
                    "home_score_before",
                    "away_score_before",
                    "bases_code",
                    "balls",
                    "strikes",
                    "events",
                    "description",
                    "is_ab",
                    "woba_denom",
                    "launch_speed",
                    "launch_angle",
                    "estimated_woba_using_speedangle",
                    "home_score_after",
                    "away_score_after",
                ]
                col_list = ", ".join(cols)
                updates = ", ".join(
                    f"{c} = EXCLUDED.{c}"
                    for c in ("events", "balls", "strikes", "home_score_after", "away_score_after")
                )
                conn.execute(
                    text(f"""
                    INSERT INTO at_bats ({col_list})
                    SELECT {col_list} FROM at_bats_tmp
                    ON CONFLICT (ab_id, game_id) DO UPDATE SET
                        {updates}
                """)
                )
                conn.execute(text("DROP TABLE at_bats_tmp"))
            else:
                at_bats_df.to_sql("at_bats", conn, if_exists="append", index=False)

            if not pitches_df.empty:
                existing_p = conn.execute(
                    text("SELECT COUNT(*) FROM pitches WHERE game_id = :gid"),
                    {"gid": game_id},
                ).scalar()

                if existing_p == 0:
                    pitches_df.to_sql(
                        "pitches",
                        conn,
                        if_exists="append",
                        index=False,
                        method="multi",
                    )

        logger.info(f"Loaded {len(at_bats_df)} at_bats and {len(pitches_df)} pitches for {game_id}")

    def ingest_game(self, game_pk: int, game_id: str):
        raw = self.fetch_game_playbyplay(game_pk)
        parsed = self.parse_playbyplay(raw, game_id)
        self.load_to_database(parsed, game_id)
        return parsed

    def ingest_date_range(self, start: date, end: date):
        current = start
        while current <= end:
            games_df = self.fetch_daily_games(current)
            for _, game in games_df.iterrows():
                game_pk = game.get("mlb_game_pk") or game.get("game_id")
                if game_pk and game["status"] == "FINAL":
                    gid = (
                        f"{game['away_team_id']}{game['home_team_id']}{current.strftime('%y%m%d')}"
                    )
                    try:
                        self.ingest_game(int(game_pk), gid)
                    except Exception as e:
                        logger.error(f"Failed to ingest {gid}: {e}")
            current += timedelta(days=1)


# ============================================================================
# UTILIDAD: CARGA DE ARCHIVOS CSV
# ============================================================================


def load_statcast_csv(filepath: str) -> pd.DataFrame:
    logger.info(f"Loading Statcast CSV from {filepath}")
    df = pd.read_csv(filepath)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"])
    if "game_pk" in df.columns:
        df["game_id"] = df["game_pk"].astype(str)

    return df


def csv_to_db(filepath: str, db_url: str, table: str = "at_bats"):
    engine = create_engine(db_url)
    df = load_statcast_csv(filepath)
    df.to_sql(table, engine, if_exists="append", index=False, method="multi")
    logger.info(f"Loaded {len(df)} rows into {table}")
    return len(df)


# ============================================================================
# MODO LÍNEA DE COMANDOS
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    from etl.config import DATABASE_URL

    if len(sys.argv) > 2 and sys.argv[1] == "--csv":
        csv_to_db(sys.argv[2], DATABASE_URL)
    else:
        ingestor = StatcastIngestor(db_url=DATABASE_URL)
        today = date.today()
        ingestor.ingest_date_range(today - timedelta(days=1), today)
