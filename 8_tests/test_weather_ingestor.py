"""Tests para WeatherIngestor (parseo con datos mock)."""

import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from etl.ingestors.weather_ingestor import WeatherIngestor


@pytest.fixture
def ingestor():
    return WeatherIngestor(db_url="sqlite://")


SAMPLE_FORECAST = {
    "properties": {
        "periods": [
            {
                "startTime": "2026-05-20T18:00:00",
                "temperature": 72,
                "windSpeed": "12 mph",
                "windDirection": "SW",
                "relativeHumidity": {"value": 55},
                "probabilityOfPrecipitation": {"value": 10},
                "shortForecast": "Partly Cloudy",
            },
            {
                "startTime": "2026-05-20T19:00:00",
                "temperature": 70,
                "windSpeed": "10 mph",
                "windDirection": "S",
                "relativeHumidity": {"value": 60},
                "probabilityOfPrecipitation": {"value": 5},
                "shortForecast": "Mostly Cloudy",
            },
        ]
    }
}


class TestParseForecast:
    def test_parses_hourly_periods(self, ingestor):
        hourly = ingestor.parse_forecast(SAMPLE_FORECAST)
        assert len(hourly) == 2
        assert hourly[0]["temperature"] == 72
        assert hourly[0]["wind_speed"] == 12.0
        assert hourly[0]["wind_direction"] == "SW"
        assert hourly[0]["humidity"] == 55
        assert hourly[0]["precipitation_pct"] == 10
        assert hourly[0]["condition"] == "Partly Cloudy"

    def test_second_period(self, ingestor):
        hourly = ingestor.parse_forecast(SAMPLE_FORECAST)
        assert hourly[1]["temperature"] == 70
        assert hourly[1]["wind_speed"] == 10.0
        assert hourly[1]["humidity"] == 60

    def test_empty_forecast(self, ingestor):
        empty = {"properties": {"periods": []}}
        hourly = ingestor.parse_forecast(empty)
        assert hourly == []

    def test_none_precipitation(self, ingestor):
        forecast = {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-05-20T18:00:00",
                        "temperature": 72,
                        "windSpeed": "5 mph",
                        "windDirection": "N",
                        "relativeHumidity": {},
                        "probabilityOfPrecipitation": {"value": None},
                        "shortForecast": "Clear",
                    }
                ]
            }
        }
        hourly = ingestor.parse_forecast(forecast)
        assert hourly[0]["humidity"] is None
        assert hourly[0]["precipitation_pct"] is None

    def test_parse_wind_speed_various_formats(self, ingestor):
        assert ingestor._parse_wind_speed("5 mph") == 5.0
        assert ingestor._parse_wind_speed("10 mph") == 10.0
        assert ingestor._parse_wind_speed("0 mph") == 0.0

    def test_parse_wind_speed_no_number(self, ingestor):
        assert ingestor._parse_wind_speed("calm") == 0.0
        assert ingestor._parse_wind_speed("") == 0.0


class TestIngestGameWeather:
    def test_skips_unknown_stadium(self, ingestor):
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite://")
        ingestor.engine = engine
        with engine.begin() as conn:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS stadiums (
                    stadium_id INTEGER PRIMARY KEY, name TEXT,
                    roof_type VARCHAR(10) DEFAULT 'open'
                )
            """)
            )
            conn.execute(text("INSERT INTO stadiums VALUES (999, 'Unknown Park', 'open')"))
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS weather_hourly (
                    forecast_hour TEXT, temperature REAL, game_id TEXT
                )
            """)
            )
        # No exception expected — stadium 999 not in STADIUM_COORDS
        ingestor.ingest_game_weather("test-game", 999, datetime.now())
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM weather_hourly")).scalar()
        assert count == 0

    def test_ingests_weather_within_window(self, ingestor, monkeypatch):
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite://")
        ingestor.engine = engine
        with engine.begin() as conn:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS weather_hourly (
                    forecast_hour TEXT, temperature REAL, wind_speed REAL,
                    wind_direction TEXT, humidity REAL, precipitation_pct REAL,
                    condition TEXT, game_id TEXT
                )
            """)
            )
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS stadiums (
                    stadium_id INTEGER PRIMARY KEY, name TEXT,
                    roof_type VARCHAR(10) DEFAULT 'open'
                )
            """)
            )
            conn.execute(text("INSERT OR IGNORE INTO stadiums VALUES (1, 'Test Park', 'open')"))
        monkeypatch.setattr(
            ingestor,
            "get_forecast_for_stadium",
            lambda lat, lon: SAMPLE_FORECAST,
        )
        ingestor.ingest_game_weather("test-game", 1, datetime(2026, 5, 20, 19, 0))
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM weather_hourly")).fetchall()
        # Both periods are within game window (19:00 ± 3h/5h)
        assert len(rows) == 2
        assert rows[0][1] == 72
        assert rows[0][7] == "test-game"
