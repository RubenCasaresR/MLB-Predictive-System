# =============================================================================
# weather_ingestor.py
# Ingesta de datos climáticos para juegos MLB (NOAA / National Weather Service)
# Rubén Eduardo Casares Rosales - MLB Predictive System
# =============================================================================
# Obtiene pronósticos horarios para estadios MLB usando la API de
# weather.gov (NOAA). Datos críticos para el modelo predictivo:
#   - Temperatura: afecta distancia de batazos (aire más cálido = más HR)
#   - Viento: dirección OUT_TO_CF incrementa HR en ~20%
#   - Humedad: afecta movimiento de pitcheo quebrado
#   - Precipitación: afecta probabilidad de retraso/juego suspendido
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


class WeatherIngestor:
    # Coordenadas de estadios MLB (lat, lon)
    # Coords keyed by stadiums.stadium_id (must match database/seed_data/park_factors_seed.sql)
    STADIUM_COORDS = {
        1: {"name": "Yankee Stadium (NYY)", "lat": 40.8296, "lon": -73.9262},
        2: {"name": "Fenway Park (BOS)", "lat": 42.3467, "lon": -71.0972},
        3: {"name": "Dodger Stadium (LAD)", "lat": 34.0739, "lon": -118.2400},
        4: {"name": "Wrigley Field (CHC)", "lat": 41.9484, "lon": -87.6553},
        5: {"name": "Minute Maid Park (HOU)", "lat": 29.7572, "lon": -95.3556},
        6: {"name": "Oracle Park (SFG)", "lat": 37.7786, "lon": -122.3893},
        7: {"name": "Truist Park (ATL)", "lat": 33.8908, "lon": -84.4676},
        8: {"name": "Busch Stadium (STL)", "lat": 38.6226, "lon": -90.1928},
        9: {"name": "Citizens Bank Park (PHI)", "lat": 39.9056, "lon": -75.1664},
        10: {"name": "Petco Park (SDP)", "lat": 32.7076, "lon": -117.1570},
        11: {"name": "Target Field (MIN)", "lat": 44.9817, "lon": -93.2778},
        12: {"name": "Comerica Park (DET)", "lat": 42.3390, "lon": -83.0485},
        13: {"name": "American Family Field (MIL)", "lat": 43.0282, "lon": -87.9712},
        14: {"name": "Globe Life Field (TEX)", "lat": 32.7478, "lon": -97.0839},
        15: {"name": "Coors Field (COL)", "lat": 39.7560, "lon": -104.9942},
        16: {"name": "Tropicana Field (TBR)", "lat": 27.7683, "lon": -82.6534},
        17: {"name": "PNC Park (PIT)", "lat": 40.4469, "lon": -80.0057},
        18: {"name": "Great American Ball Park (CIN)", "lat": 39.0974, "lon": -84.5066},
        19: {"name": "Kauffman Stadium (KCR)", "lat": 39.0517, "lon": -94.4803},
        20: {"name": "Citi Field (NYM)", "lat": 40.7571, "lon": -73.8458},
        # Additional stadiums not yet in seed DB but with coords for future use
        21: {"name": "Nationals Park (WSN)", "lat": 38.8730, "lon": -77.0075},
        22: {"name": "Camden Yards (BAL)", "lat": 39.2839, "lon": -76.6216},
        23: {"name": "loanDepot park (MIA)", "lat": 25.7781, "lon": -80.2197},
        24: {"name": "Rogers Centre (TOR)", "lat": 43.6414, "lon": -79.3894},
        25: {"name": "Progressive Field (CLE)", "lat": 41.4962, "lon": -81.6852},
        26: {"name": "Rate Field (CHW)", "lat": 41.8300, "lon": -87.6339},
        27: {"name": "Angel Stadium (LAA)", "lat": 33.8003, "lon": -117.8827},
        28: {"name": "Oakland Coliseum (OAK)", "lat": 37.7516, "lon": -122.2005},
        29: {"name": "T-Mobile Park (SEA)", "lat": 47.5914, "lon": -122.3325},
        30: {"name": "Chase Field (ARI)", "lat": 33.4454, "lon": -112.0667},
    }

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "MLB Predictive System/1.0 (contact@mlbpredictive.com)",
            }
        )
        logger.info("WeatherIngestor initialized")

    def _get_roof_type(self, stadium_id: int) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT roof_type FROM stadiums WHERE stadium_id = :sid"),
                {"sid": stadium_id},
            ).fetchone()
            return row[0] if row else None

    def _neutralise_weather(self) -> list[dict]:
        return [
            {
                "forecast_hour": "",
                "temperature": 70.0,
                "wind_speed": 0.0,
                "wind_direction": "NONE",
                "humidity": 50.0,
                "precipitation_pct": 0.0,
                "condition": "Dome",
            }
        ]

    @with_retry()
    def get_forecast_for_stadium(self, lat: float, lon: float) -> dict | None:
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        resp = self.session.get(points_url, timeout=15)
        resp.raise_for_status()
        points = resp.json()

        forecast_url = points["properties"]["forecastHourly"]
        forecast_resp = self.session.get(forecast_url, timeout=15)
        forecast_resp.raise_for_status()

        return forecast_resp.json()

    def parse_forecast(self, raw: dict) -> list[dict]:
        hourly = []
        for period in raw.get("properties", {}).get("periods", []):
            hourly.append(
                {
                    "forecast_hour": period.get("startTime"),
                    "temperature": period.get("temperature"),
                    "wind_speed": self._parse_wind_speed(period.get("windSpeed", "0 mph")),
                    "wind_direction": period.get("windDirection", "VRB"),
                    "humidity": period.get("relativeHumidity", {}).get("value"),
                    "precipitation_pct": period.get("probabilityOfPrecipitation", {}).get(
                        "value", 0
                    ),
                    "condition": period.get("shortForecast", ""),
                }
            )
        return hourly

    def _parse_wind_speed(self, speed_str: str) -> float:
        import re

        match = re.search(r"(\d+)", speed_str)
        return float(match.group(1)) if match else 0.0

    def ingest_game_weather(self, game_id: str, stadium_id: int, game_time: datetime):
        roof = self._get_roof_type(stadium_id)
        if roof in ("dome", "retractable"):
            hourly = self._neutralise_weather()
            df = pd.DataFrame(hourly)
            df["game_id"] = game_id
            df["forecast_hour"] = pd.to_datetime(game_time).tz_localize(None)

            with self.engine.begin() as conn:
                df.to_sql("weather_hourly", conn, if_exists="append", index=False)
            logger.info(f"Loaded neutralised weather (dome) for {game_id}")
            return

        coords = self.STADIUM_COORDS.get(stadium_id)
        if not coords:
            # Try loading from database
            with self.engine.connect() as conn:
                row = conn.execute(
                    text("SELECT name FROM stadiums WHERE stadium_id = :sid"),
                    {"sid": stadium_id},
                ).fetchone()
                logger.warning(f"No coords for stadium {stadium_id} ({row[0] if row else '?'})")
            return

        try:
            raw_forecast = self.get_forecast_for_stadium(coords["lat"], coords["lon"])
        except Exception as e:
            logger.warning(f"Weather API error at stadium {stadium_id}: {e}")
            return
        if raw_forecast is None:
            return

        hourly = self.parse_forecast(raw_forecast)

        df = pd.DataFrame(hourly)
        if df.empty:
            return

        df["game_id"] = game_id
        df["forecast_hour"] = pd.to_datetime(df["forecast_hour"])

        # Ensure both are tz-naive (NOAA returns tz-aware, DB stores tz-naive ET)
        if df["forecast_hour"].dt.tz is not None:
            df["forecast_hour"] = df["forecast_hour"].dt.tz_localize(None)

        # Filter to game window: 3 hours before to 5 hours after start
        window_start = game_time - timedelta(hours=3)
        window_end = game_time + timedelta(hours=5)
        df = df[(df["forecast_hour"] >= window_start) & (df["forecast_hour"] <= window_end)]

        if df.empty:
            logger.info(f"No weather data within game window for {game_id}")
            return

        with self.engine.begin() as conn:
            df.to_sql("weather_hourly", conn, if_exists="append", index=False)

        logger.info(f"Loaded {len(df)} weather records for {game_id}")

    def ingest_team_games(self, game_date: date):
        with self.engine.connect() as conn:
            games = conn.execute(
                text("""
                    SELECT game_id, venue_id, start_time_et
                    FROM games
                    WHERE game_date = :gd
                      AND status IN ('SCHEDULED', 'PREGAME', 'IN_PROGRESS')
                """),
                {"gd": game_date},
            ).fetchall()

        for game_id, venue_id, start_time in games:
            if start_time:
                self.ingest_game_weather(game_id, venue_id, start_time)
            time.sleep(0.5)  # Rate limit: 1 req/500ms for NWS API

        logger.info(f"Weather ingest complete for {game_date}: {len(games)} games")


# ============================================================================
# MODO LÍNEA DE COMANDOS
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from etl.config import DATABASE_URL

    ingestor = WeatherIngestor(DATABASE_URL)
    today = date.today()

    ingestor.ingest_team_games(today)
    ingestor.ingest_team_games(today + timedelta(days=1))
