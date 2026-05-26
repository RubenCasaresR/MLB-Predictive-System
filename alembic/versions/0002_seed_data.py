"""Migration 0002: Seed Data.

Carga datos iniciales en tablas lookup:
  - sportsbooks (5 casas de apuestas)
  - teams (30 equipos MLB)
  - stadiums (30 estadios)
  - park_factors_monthly (derivado de stadiums)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-26
"""

import logging
from collections.abc import Sequence
from typing import Union

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SPORTSBOOKS = [
    (1, "DraftKings"),
    (2, "FanDuel"),
    (3, "BetMGM"),
    (4, "Caesars"),
    (5, "PointsBet"),
]

TEAMS = [
    ("NYY", "New York Yankees", "A", "AL East", "Yankee Stadium", "America/New_York"),
    ("BOS", "Boston Red Sox", "A", "AL East", "Fenway Park", "America/New_York"),
    ("LAD", "Los Angeles Dodgers", "N", "NL West", "Dodger Stadium", "America/Los_Angeles"),
    ("HOU", "Houston Astros", "A", "AL West", "Minute Maid Park", "America/Chicago"),
    ("ATL", "Atlanta Braves", "N", "NL East", "Truist Park", "America/New_York"),
    ("CHC", "Chicago Cubs", "N", "NL Central", "Wrigley Field", "America/Chicago"),
    ("SDP", "San Diego Padres", "N", "NL West", "Petco Park", "America/Los_Angeles"),
    ("SFG", "San Francisco Giants", "N", "NL West", "Oracle Park", "America/Los_Angeles"),
    ("PHI", "Philadelphia Phillies", "N", "NL East", "Citizens Bank Park", "America/New_York"),
    ("STL", "St. Louis Cardinals", "N", "NL Central", "Busch Stadium", "America/Chicago"),
    ("NYM", "New York Mets", "N", "NL East", "Citi Field", "America/New_York"),
    ("MIL", "Milwaukee Brewers", "N", "NL Central", "American Family Field", "America/Chicago"),
    ("TOR", "Toronto Blue Jays", "A", "AL East", "Rogers Centre", "America/Toronto"),
    ("BAL", "Baltimore Orioles", "A", "AL East", "Oriole Park", "America/New_York"),
    ("TBR", "Tampa Bay Rays", "A", "AL East", "Tropicana Field", "America/New_York"),
    ("CLE", "Cleveland Guardians", "A", "AL Central", "Progressive Field", "America/New_York"),
    ("MIN", "Minnesota Twins", "A", "AL Central", "Target Field", "America/Chicago"),
    ("DET", "Detroit Tigers", "A", "AL Central", "Comerica Park", "America/New_York"),
    ("CHW", "Chicago White Sox", "A", "AL Central", "Guaranteed Rate Field", "America/Chicago"),
    ("KCR", "Kansas City Royals", "A", "AL Central", "Kauffman Stadium", "America/Chicago"),
    ("TEX", "Texas Rangers", "A", "AL West", "Globe Life Field", "America/Chicago"),
    ("SEA", "Seattle Mariners", "A", "AL West", "T-Mobile Park", "America/Los_Angeles"),
    ("OAK", "Oakland Athletics", "A", "AL West", "Oakland Coliseum", "America/Los_Angeles"),
    ("LAA", "Los Angeles Angels", "A", "AL West", "Angel Stadium", "America/Los_Angeles"),
    ("MIA", "Miami Marlins", "N", "NL East", "LoanDepot Park", "America/New_York"),
    ("WSN", "Washington Nationals", "N", "NL East", "Nationals Park", "America/New_York"),
    ("CIN", "Cincinnati Reds", "N", "NL Central", "Great American Ball Park", "America/New_York"),
    ("PIT", "Pittsburgh Pirates", "N", "NL Central", "PNC Park", "America/New_York"),
    ("COL", "Colorado Rockies", "N", "NL West", "Coors Field", "America/Denver"),
    ("ARI", "Arizona Diamondbacks", "N", "NL West", "Chase Field", "America/Phoenix"),
]

STADIUMS = [
    (1, "Yankee Stadium", 55, 46537, 1.02, 1.05, 0.99, 1.12),
    (2, "Fenway Park", 30, 37755, 1.04, 1.06, 1.02, 0.98),
    (3, "Dodger Stadium", 515, 56000, 0.98, 0.96, 0.99, 0.92),
    (4, "Wrigley Field", 595, 41649, 1.02, 1.03, 1.01, 1.05),
    (5, "Minute Maid Park", 40, 41168, 1.01, 1.02, 1.00, 1.08),
    (6, "Oracle Park", 20, 41915, 0.96, 0.94, 0.98, 0.88),
    (7, "Truist Park", 1050, 41084, 1.03, 1.04, 1.02, 1.06),
    (8, "Busch Stadium", 535, 45329, 0.97, 0.96, 0.98, 0.90),
    (9, "Citizens Bank Park", 39, 42792, 1.05, 1.07, 1.03, 1.10),
    (10, "Petco Park", 30, 40162, 0.96, 0.95, 0.97, 0.89),
    (11, "Target Field", 810, 38544, 1.01, 1.02, 1.00, 0.97),
    (12, "Comerica Park", 585, 41083, 0.98, 0.97, 0.99, 0.92),
    (13, "American Family Field", 635, 41900, 1.02, 1.03, 1.01, 1.04),
    (14, "Globe Life Field", 555, 40300, 0.99, 0.98, 1.00, 0.95),
    (15, "Coors Field", 5280, 50398, 1.15, 1.14, 1.16, 1.22),
    (16, "Tropicana Field", 10, 25249, 0.97, 0.96, 0.98, 0.90),
    (17, "PNC Park", 790, 38362, 0.99, 0.98, 1.00, 0.94),
    (18, "Great American Ball Park", 510, 43359, 1.05, 1.06, 1.04, 1.14),
    (19, "Kauffman Stadium", 760, 37400, 0.98, 0.97, 0.99, 0.91),
    (20, "Citi Field", 30, 41922, 0.97, 0.96, 0.98, 0.90),
    (21, "Nationals Park", 25, 41155, 0.99, 1.00, 0.99, 1.00),
    (22, "Camden Yards", 30, 44970, 1.01, 1.02, 1.00, 1.03),
    (23, "loanDepot park", 10, 36742, 0.98, 0.97, 0.99, 0.93),
    (24, "Rogers Centre", 260, 49162, 1.01, 1.01, 1.00, 1.04),
    (25, "Progressive Field", 660, 34830, 0.98, 0.97, 0.99, 0.93),
    (26, "Rate Field", 600, 40615, 0.99, 0.98, 1.00, 0.96),
    (27, "Angel Stadium", 30, 45517, 1.01, 1.02, 1.00, 1.03),
    (28, "Oakland Coliseum", 25, 46847, 0.97, 0.98, 0.97, 0.92),
    (29, "T-Mobile Park", 10, 47929, 0.96, 0.95, 0.97, 0.89),
    (30, "Chase Field", 1100, 48443, 1.06, 1.07, 1.05, 1.11),
]

TEAM_STADIUM_MAP = {
    "NYY": 1,
    "BOS": 2,
    "LAD": 3,
    "CHC": 4,
    "HOU": 5,
    "SFG": 6,
    "ATL": 7,
    "STL": 8,
    "PHI": 9,
    "SDP": 10,
    "MIN": 11,
    "DET": 12,
    "MIL": 13,
    "TEX": 14,
    "COL": 15,
    "TBR": 16,
    "PIT": 17,
    "CIN": 18,
    "KCR": 19,
    "NYM": 20,
    "WSN": 21,
    "BAL": 22,
    "MIA": 23,
    "TOR": 24,
    "CLE": 25,
    "CHW": 26,
    "LAA": 27,
    "OAK": 28,
    "SEA": 29,
    "ARI": 30,
}


def upgrade() -> None:
    logger.info("Seeding lookup tables...")

    for bid, name in SPORTSBOOKS:
        op.execute(
            f"INSERT INTO sportsbooks (book_id, name) VALUES ({bid}, '{name}') ON CONFLICT (book_id) DO NOTHING"
        )

    for tid, name, league, division, ballpark, tz in TEAMS:
        op.execute(
            "INSERT INTO teams (team_id, full_name, league, division, ballpark, timezone) "
            "VALUES ('{}', '{}', '{}', '{}', '{}', '{}') ON CONFLICT (team_id) DO NOTHING".format(
                tid, name.replace("'", "''"), league, division, ballpark, tz
            )
        )

    for sid, sname, alt, cap, pf_all, pf_l, pf_r, pf_hr in STADIUMS:
        op.execute(
            "INSERT INTO stadiums (stadium_id, name, team_id, altitude_ft, capacity, "
            "pf_overall, pf_lefthand, pf_righthand, pf_hr) "
            "VALUES ({}, '{}', '{}', {}, {}, {}, {}, {}) "
            "ON CONFLICT (stadium_id) DO UPDATE SET "
            "pf_overall = EXCLUDED.pf_overall, pf_hr = EXCLUDED.pf_hr, "
            "pf_lefthand = EXCLUDED.pf_lefthand, pf_righthand = EXCLUDED.pf_righthand".format(
                sid,
                sname.replace("'", "''"),
                [k for k, v in TEAM_STADIUM_MAP.items() if v == sid][0],
                alt,
                cap,
                pf_all,
                pf_l,
                pf_r,
                pf_hr,
            )
        )

    for sid, _, _, _, pf_all, _, _, pf_hr in STADIUMS:
        op.execute(
            "INSERT INTO park_factors_monthly (stadium_id, season, month, "
            "pf_single, pf_double, pf_triple, pf_hr, pf_bb, pf_k, pf_woba) "
            "VALUES ({}, 2024, 6, {}, {}, {}, {}, 1.00, 1.00, {}) "
            "ON CONFLICT (stadium_id, season, month) DO NOTHING".format(
                sid, pf_all, pf_all, pf_hr, pf_all
            )
        )

    logger.info("Seed data loaded")


def downgrade() -> None:
    logger.info("Removing seed data...")
    op.execute("DELETE FROM park_factors_monthly")
    op.execute("DELETE FROM stadiums")
    op.execute("DELETE FROM teams")
    op.execute("DELETE FROM sportsbooks")
    logger.info("Seed data removed")
