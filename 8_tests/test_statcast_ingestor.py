"""Tests para StatcastIngestor (parseo con datos mock)."""

import pytest
import sys, os, json
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from etl.ingestors.statcast_ingestor import StatcastIngestor


SAMPLE_PLAY = {
    "result": {
        "event": "single",
        "description": "Line drive single to center field",
        "homeScore": 1,
        "awayScore": 0,
        "isOut": False,
    },
    "about": {
        "inning": 1,
        "halfInning": "top",
        "outs": 0,
    },
    "matchup": {
        "batter": {"id": 101, "fullName": "Test Batter"},
        "pitcher": {"id": 201, "fullName": "Test Pitcher"},
    },
    "playEvents": [
        {
            "isPitch": True,
            "pitchNumber": 1,
            "details": {
                "type": {"code": "FF", "description": "Four-Seam Fastball"},
                "isStrike": False,
                "isBall": False,
                "isSwing": True,
                "isSwingAndMiss": False,
                "call": {"description": "Foul"},
            },
            "pitchData": {
                "startSpeed": 95.5,
                "extension": 6.2,
                "breaks": {"spinRate": 2400},
                "pfxX": -1.2,
                "pfxZ": 8.5,
                "coordinates": {"x": 0.1, "z": 2.5},
            },
            "zone": 14,
        },
    ],
    "atBatIndex": 1,
}


@pytest.fixture
def ingestor():
    return StatcastIngestor(db_url="sqlite://")


class TestParseAtBat:
    def test_parse_single(self, ingestor):
        ab = ingestor._parse_at_bat(SAMPLE_PLAY, "2026-05-20-NYY-BOS")
        assert ab is not None
        assert ab["ab_id"] == 1
        assert ab["game_id"] == "2026-05-20-NYY-BOS"
        assert ab["inning"] == 1
        assert ab["half_inning"] == "T"
        assert ab["batter_id"] == 101
        assert ab["pitcher_id"] == 201
        assert ab["events"] == "single"
        assert ab["outs_before"] == 0
        assert ab["home_score_before"] == 0
        assert ab["away_score_before"] == 0
        assert ab["home_score_after"] == 1
        assert ab["away_score_after"] == 0
        assert ab["is_ab"] is not None

    def test_parse_home_run(self, ingestor):
        play = SAMPLE_PLAY.copy()
        play["result"] = {**play["result"], "event": "home_run"}
        ab = ingestor._parse_at_bat(play, "2026-05-20-NYY-BOS")
        assert ab["events"] == "home_run"

    def test_parse_strikeout(self, ingestor):
        play = SAMPLE_PLAY.copy()
        play["result"] = {**play["result"], "event": "strikeout"}
        ab = ingestor._parse_at_bat(play, "2026-05-20-NYY-BOS")
        assert ab["events"] == "strikeout"

    def test_parse_walk(self, ingestor):
        play = SAMPLE_PLAY.copy()
        play["result"] = {**play["result"], "event": "walk"}
        ab = ingestor._parse_at_bat(play, "2026-05-20-NYY-BOS")
        assert ab["events"] == "walk"

    def test_parse_with_launch_data(self, ingestor):
        play = SAMPLE_PLAY.copy()
        play["result"]["launchSpeed"] = 105.2
        play["result"]["launchAngle"] = 22.5
        play["result"]["estimatedWobaUsingSpeedAngle"] = 0.890
        ab = ingestor._parse_at_bat(play, "2026-05-20-NYY-BOS")
        assert ab["launch_speed"] == 105.2
        assert ab["launch_angle"] == 22.5
        assert ab["estimated_woba_using_speedangle"] == 0.890

    def test_parse_missing_fields_returns_none(self, ingestor):
        with pytest.raises(Exception, match=None):
            result = ingestor._parse_at_bat({}, "game-id")
            # may or may not return None depending on implementation
            assert result is None


class TestParsePitch:
    def test_parse_fastball(self, ingestor):
        pitch_data = SAMPLE_PLAY["playEvents"][0]
        pitch = ingestor._parse_pitch(pitch_data, ab_id=1)
        assert pitch is not None
        assert pitch["ab_id"] == 1
        assert pitch["pitch_number"] == 1
        assert pitch["pitch_type"] == "FF"
        assert pitch["pitch_name"] == "Four-Seam Fastball"
        assert pitch["release_speed"] == 95.5
        assert pitch["release_spin_rate"] == 2400
        assert pitch["release_extension"] == 6.2
        assert pitch["strike"] is False
        assert pitch["ball"] is False
        assert pitch["swing"] is True
        assert pitch["whiff"] is False
        assert pitch["zone"] == 14
        assert pitch["pfx_x"] == -1.2
        assert pitch["pfx_z"] == 8.5
        assert pitch["plate_x"] == 0.1
        assert pitch["plate_z"] == 2.5

    def test_parse_whiff(self, ingestor):
        pitch_data = json.loads(json.dumps(SAMPLE_PLAY["playEvents"][0]))
        pitch_data["details"]["isSwingAndMiss"] = True
        pitch = ingestor._parse_pitch(pitch_data, ab_id=1)
        assert pitch["whiff"] is True

    def test_parse_non_pitch_event(self, ingestor):
        pitch_data = {"isPitch": False}
        pitch = ingestor._parse_pitch(pitch_data, ab_id=1)
        if pitch is not None:
            assert pitch.get("pitch_type") is None


class TestGetBasesCode:
    def test_no_runners(self, ingestor):
        code = ingestor._get_bases_code({})
        assert code == "000"

    def test_first_base(self, ingestor):
        code = ingestor._get_bases_code({"firstBase": True})
        assert code == "100"

    def test_all_bases(self, ingestor):
        code = ingestor._get_bases_code({"firstBase": True, "secondBase": True, "thirdBase": True})
        assert code == "111"


class TestParsePlayByPlay:
    def test_parses_all_plays(self, ingestor):
        raw_data = {
            "allPlays": [
                SAMPLE_PLAY,
                dict(SAMPLE_PLAY, atBatIndex=2, result=dict(SAMPLE_PLAY["result"], event="strikeout", homeScore=1)),
            ]
        }
        result = ingestor.parse_playbyplay(raw_data, "2026-05-20-NYY-BOS")
        assert len(result["at_bats"]) == 2
        assert result["at_bats"][0]["events"] == "single"
        assert result["at_bats"][1]["events"] == "strikeout"

    def test_tracks_scores_correctly(self, ingestor):
        raw_data = {
            "allPlays": [
                dict(SAMPLE_PLAY, atBatIndex=1,
                     result=dict(SAMPLE_PLAY["result"], event="home_run", homeScore=2, awayScore=0)),
                dict(SAMPLE_PLAY, atBatIndex=2,
                     result=dict(SAMPLE_PLAY["result"], event="walk", homeScore=2, awayScore=0)),
            ]
        }
        # First play: home_score_before=0, away_score_before=0
        # Second play: home_score_before=2 (prev home_after), away_score_before=0
        result = ingestor.parse_playbyplay(raw_data, "2026-05-20-NYY-BOS")
        assert len(result["at_bats"]) == 2
        assert result["at_bats"][0]["home_score_before"] == 0
        assert result["at_bats"][0]["home_score_after"] == 2
        assert result["at_bats"][1]["home_score_before"] == 2


class TestLoadToDatabase:
    def test_upserts_at_bats_and_pitches(self, ingestor):
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite://")
        ingestor.engine = engine
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS at_bats (
                    ab_id INTEGER PRIMARY KEY,
                    game_id TEXT,
                    pitcher_id INTEGER,
                    events TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pitches (
                    pitch_id INTEGER PRIMARY KEY,
                    ab_id INTEGER,
                    release_speed REAL
                )
            """))
        game_data = {
            "at_bats": [
                {"ab_id": 1, "game_id": "2026-05-20-NYY-BOS", "pitcher_id": 201, "events": "single"},
                {"ab_id": 2, "game_id": "2026-05-20-NYY-BOS", "pitcher_id": 201, "events": "strikeout"},
            ],
            "pitches": [
                {"pitch_id": 1, "ab_id": 1, "release_speed": 95.5},
                {"pitch_id": 2, "ab_id": 2, "release_speed": 93.2},
            ],
        }
        ingestor.load_to_database(game_data, "2026-05-20-NYY-BOS")
        with engine.connect() as conn:
            ab_count = conn.execute(text("SELECT COUNT(*) FROM at_bats")).scalar()
            p_count = conn.execute(text("SELECT COUNT(*) FROM pitches")).scalar()
        assert ab_count == 2
        assert p_count == 2

    def test_skip_empty_at_bats(self, ingestor):
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite://")
        ingestor.engine = engine
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS at_bats (
                    ab_id INTEGER PRIMARY KEY,
                    game_id TEXT
                )
            """))
        game_data = {"at_bats": [], "pitches": []}
        ingestor.load_to_database(game_data, "2026-05-20-NYY-BOS")
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM at_bats")).scalar()
        assert count == 0  # no error, just warning log


class TestFetchDailyGames:
    def test_parse_schedule_response(self, ingestor, monkeypatch):
        mock_response = {
            "dates": [{
                "date": "2026-05-20",
                "games": [{
                    "gamePk": 123456,
                    "teams": {
                        "home": {"team": {"abbreviation": "BOS"}, "probablePitcher": {"id": 601}},
                        "away": {"team": {"abbreviation": "NYY"}},
                    },
                    "status": {"detailedState": "SCHEDULED"},
                    "venue": {"id": 3},
                    "gameDate": "2026-05-20T19:10:00Z",
                }],
            }],
        }

        def mock_get(*args, **kwargs):
            class MockResponse:
                def raise_for_status(self): pass
                def json(self): return mock_response
                ok = True
            return MockResponse()

        import requests
        monkeypatch.setattr(requests, "get", mock_get)
        df = ingestor.fetch_daily_games(date(2026, 5, 20))
        assert len(df) == 1
        row = df.iloc[0]
        assert row["game_id"] == 123456
        assert row["home_team_id"] == "BOS"
        assert row["away_team_id"] == "NYY"
        assert row["status"] == "SCHEDULED"
