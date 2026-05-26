"""Tests para MarketIngestor (parseo con datos mock)."""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from etl.ingestors.market_ingestor import MarketIngestor


@pytest.fixture
def ingestor():
    return MarketIngestor(db_url="sqlite://", odds_api_key="test_key")


SAMPLE_ODDS_RESPONSE = [
    {
        "id": "abc123",
        "home_team": "New York Yankees",
        "away_team": "Boston Red Sox",
        "commence_time": "2026-05-20T19:10:00Z",
        "bookmakers": [
            {
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "New York Yankees", "price": -120},
                            {"name": "Boston Red Sox", "price": +110},
                        ],
                    },
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "New York Yankees", "point": -1.5, "price": +150},
                            {"name": "Boston Red Sox", "point": +1.5, "price": -170},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 8.5, "price": -110},
                            {"name": "Under", "point": 8.5, "price": -110},
                        ],
                    },
                ],
            },
        ],
    },
]


class TestTeamNameToAbbr:
    def test_known_teams(self, ingestor):
        assert ingestor._team_name_to_abbr("New York Yankees") == "NYY"
        assert ingestor._team_name_to_abbr("Boston Red Sox") == "BOS"
        assert ingestor._team_name_to_abbr("Los Angeles Dodgers") == "LAD"
        assert ingestor._team_name_to_abbr("Houston Astros") == "HOU"
        assert ingestor._team_name_to_abbr("Atlanta Braves") == "ATL"
        assert ingestor._team_name_to_abbr("Chicago Cubs") == "CHC"

    def test_fallback_to_truncated(self, ingestor):
        assert len(ingestor._team_name_to_abbr("Unknown Team")) >= 3

    def test_all_30_teams_have_mapping(self, ingestor):
        teams = [
            "New York Yankees",
            "Boston Red Sox",
            "Los Angeles Dodgers",
            "Houston Astros",
            "Atlanta Braves",
            "New York Mets",
            "Philadelphia Phillies",
            "San Diego Padres",
            "St. Louis Cardinals",
            "Chicago Cubs",
            "San Francisco Giants",
            "Toronto Blue Jays",
            "Milwaukee Brewers",
            "Baltimore Orioles",
            "Tampa Bay Rays",
            "Seattle Mariners",
            "Texas Rangers",
            "Cleveland Guardians",
            "Minnesota Twins",
            "Arizona Diamondbacks",
            "Cincinnati Reds",
            "Miami Marlins",
            "Kansas City Royals",
            "Chicago White Sox",
            "Detroit Tigers",
            "Colorado Rockies",
            "Pittsburgh Pirates",
            "Los Angeles Angels",
            "Oakland Athletics",
            "Washington Nationals",
        ]
        for team in teams:
            assert len(ingestor._team_name_to_abbr(team)) == 3, f"Missing mapping for {team}"


class TestGetSportsbookId:
    def test_known_sportsbooks(self, ingestor):
        assert ingestor._get_sportsbook_id("DraftKings") == 1
        assert ingestor._get_sportsbook_id("FanDuel") == 2
        assert ingestor._get_sportsbook_id("BetMGM") == 3

    def test_unknown_sportsbook(self, ingestor):
        assert ingestor._get_sportsbook_id("UnknownBook") == 0


class TestParseOdds:
    def test_parses_h2h_moneyline(self, ingestor):
        result = ingestor.parse_odds(SAMPLE_ODDS_RESPONSE)
        assert len(result["games"]) == 1
        game = result["games"][0]
        assert game["home_moneyline_close"] == -120
        assert game["away_moneyline_close"] == 110

    def test_parses_spreads(self, ingestor):
        result = ingestor.parse_odds(SAMPLE_ODDS_RESPONSE)
        game = result["games"][0]
        assert game["home_runline_close"] == -1.5
        assert game["away_runline_close"] == 1.5
        assert game["home_runline_odds_close"] == 150
        assert game["away_runline_odds_close"] == -170

    def test_parses_totals(self, ingestor):
        result = ingestor.parse_odds(SAMPLE_ODDS_RESPONSE)
        game = result["games"][0]
        assert game["total_close"] == 8.5
        assert game["total_over_odds_close"] == -110
        assert game["total_under_odds_close"] == -110

    def test_generates_game_id(self, ingestor):
        result = ingestor.parse_odds(SAMPLE_ODDS_RESPONSE)
        game = result["games"][0]
        assert "game_id" in game
        assert "BOS" in game["game_id"]
        assert "NYY" in game["game_id"]

    def test_sportsbook_id(self, ingestor):
        result = ingestor.parse_odds(SAMPLE_ODDS_RESPONSE)
        game = result["games"][0]
        assert game["sportsbook_id"] == 1  # DraftKings

    def test_game_events(self, ingestor):
        result = ingestor.parse_odds(SAMPLE_ODDS_RESPONSE)
        assert len(result["game_events"]) == 1
        event = result["game_events"][0]
        assert event["id"] == "abc123"
        assert "NYY" in event["composite_id"]
        assert "BOS" in event["composite_id"]

    def test_empty_response(self, ingestor):
        result = ingestor.parse_odds([])
        assert result["games"] == []
        assert result["props"] == []
        assert result["game_events"] == []

    def test_handles_missing_markets(self, ingestor):
        resp = [
            {
                "id": "no-markets",
                "home_team": "Team A",
                "away_team": "Team B",
                "commence_time": "2026-05-20T19:00:00Z",
                "bookmakers": [{"title": "DK", "markets": []}],
            }
        ]
        result = ingestor.parse_odds(resp)
        # No H2H market → no game entry
        assert len(result["games"]) == 0


class TestFetchPublicVolume:
    def test_parse_draftkings_volume(self, ingestor, monkeypatch):
        mock_response = {
            "bookmakers": [
                {
                    "title": "DraftKings",
                    "markets": [
                        {
                            "outcomes": [
                                {"ticket_pct": 65.0, "money_pct": 42.0},
                                {"ticket_pct": 35.0, "money_pct": 58.0},
                            ]
                        }
                    ],
                }
            ]
        }

        def mock_get(*a, **kw):
            class MockResp:
                ok = True

                def raise_for_status(self):
                    pass

                def json(self):
                    return mock_response

            return MockResp()

        import requests

        monkeypatch.setattr(requests, "get", mock_get)
        result = ingestor.fetch_public_volume("abc123")
        assert result is not None
        assert result["home_ticket_pct"] == 65.0
        assert result["home_money_pct"] == 42.0
        assert result["away_ticket_pct"] == 35.0
        assert result["away_money_pct"] == 58.0


class TestLoadToDb:
    def test_loads_games(self, ingestor):
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite://")
        ingestor.engine = engine
        with engine.begin() as conn:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS market_lines (
                    game_id TEXT,
                    sportsbook_id INTEGER,
                    recorded_at TEXT,
                    home_moneyline_close INTEGER,
                    away_moneyline_close INTEGER
                )
            """)
            )
        parsed = {
            "games": [
                {
                    "game_id": "2026-05-20-NYY-BOS",
                    "sportsbook_id": 1,
                    "recorded_at": "2026-05-20T18:00:00",
                    "home_moneyline_close": -120,
                    "away_moneyline_close": 110,
                }
            ],
            "props": [],
        }
        ingestor.load_to_db(parsed)
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM market_lines")).scalar()
        assert count == 1

    def test_loads_empty_games(self, ingestor):
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite://")
        ingestor.engine = engine
        with engine.begin() as conn:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS market_lines (game_id TEXT)
            """)
            )
        ingestor.load_to_db({"games": [], "props": []})
        # Should not raise
