-- =============================================================================
-- Seed data: Park Factors MLB 2024
-- Fuente: Statcast / FanGraphs
-- 1.00 = neutral, >1 favorece bateadores, <1 favorece lanzadores
-- =============================================================================

INSERT INTO stadiums (stadium_id, name, team_id, altitude_ft, capacity, pf_overall, pf_lefthand, pf_righthand, pf_hr) VALUES
    (1, 'Yankee Stadium', 'NYY', 55, 46537, 1.02, 1.05, 0.99, 1.12),
    (2, 'Fenway Park', 'BOS', 30, 37755, 1.04, 1.06, 1.02, 0.98),
    (3, 'Dodger Stadium', 'LAD', 515, 56000, 0.98, 0.96, 0.99, 0.92),
    (4, 'Wrigley Field', 'CHC', 595, 41649, 1.02, 1.03, 1.01, 1.05),
    (5, 'Minute Maid Park', 'HOU', 40, 41168, 1.01, 1.02, 1.00, 1.08),
    (6, 'Oracle Park', 'SFG', 20, 41915, 0.96, 0.94, 0.98, 0.88),
    (7, 'Truist Park', 'ATL', 1050, 41084, 1.03, 1.04, 1.02, 1.06),
    (8, 'Busch Stadium', 'STL', 535, 45329, 0.97, 0.96, 0.98, 0.90),
    (9, 'Citizens Bank Park', 'PHI', 39, 42792, 1.05, 1.07, 1.03, 1.10),
    (10, 'Petco Park', 'SDP', 30, 40162, 0.96, 0.95, 0.97, 0.89),
    (11, 'Target Field', 'MIN', 810, 38544, 1.01, 1.02, 1.00, 0.97),
    (12, 'Comerica Park', 'DET', 585, 41083, 0.98, 0.97, 0.99, 0.92),
    (13, 'American Family Field', 'MIL', 635, 41900, 1.02, 1.03, 1.01, 1.04),
    (14, 'Globe Life Field', 'TEX', 555, 40300, 0.99, 0.98, 1.00, 0.95),
    (15, 'Coors Field', 'COL', 5280, 50398, 1.15, 1.14, 1.16, 1.22),
    (16, 'Tropicana Field', 'TBR', 10, 25249, 0.97, 0.96, 0.98, 0.90),
    (17, 'PNC Park', 'PIT', 790, 38362, 0.99, 0.98, 1.00, 0.94),
    (18, 'Great American Ball Park', 'CIN', 510, 43359, 1.05, 1.06, 1.04, 1.14),
    (19, 'Kauffman Stadium', 'KCR', 760, 37400, 0.98, 0.97, 0.99, 0.91),
    (20, 'Citi Field', 'NYM', 30, 41922, 0.97, 0.96, 0.98, 0.90),
    (21, 'Nationals Park', 'WSN', 25, 41155, 0.99, 1.00, 0.99, 1.00),
    (22, 'Camden Yards', 'BAL', 30, 44970, 1.01, 1.02, 1.00, 1.03),
    (23, 'loanDepot park', 'MIA', 10, 36742, 0.98, 0.97, 0.99, 0.93),
    (24, 'Rogers Centre', 'TOR', 260, 49162, 1.01, 1.01, 1.00, 1.04),
    (25, 'Progressive Field', 'CLE', 660, 34830, 0.98, 0.97, 0.99, 0.93),
    (26, 'Rate Field', 'CHW', 600, 40615, 0.99, 0.98, 1.00, 0.96),
    (27, 'Angel Stadium', 'LAA', 30, 45517, 1.01, 1.02, 1.00, 1.03),
    (28, 'Oakland Coliseum', 'OAK', 25, 46847, 0.97, 0.98, 0.97, 0.92),
    (29, 'T-Mobile Park', 'SEA', 10, 47929, 0.96, 0.95, 0.97, 0.89),
    (30, 'Chase Field', 'ARI', 1100, 48443, 1.06, 1.07, 1.05, 1.11)
ON CONFLICT (stadium_id) DO UPDATE SET
    pf_overall = EXCLUDED.pf_overall,
    pf_hr = EXCLUDED.pf_hr,
    pf_lefthand = EXCLUDED.pf_lefthand,
    pf_righthand = EXCLUDED.pf_righthand;

-- Monthly park factors (2024, June)
INSERT INTO park_factors_monthly (stadium_id, season, month, pf_single, pf_double, pf_triple, pf_hr, pf_bb, pf_k, pf_woba)
SELECT stadium_id, 2024, 6, pf_overall, pf_overall, pf_overall, pf_hr, 1.00, 1.00, pf_overall
FROM stadiums
ON CONFLICT (stadium_id, season, month) DO NOTHING;

-- Teams seed
INSERT INTO teams (team_id, full_name, league, division, ballpark, timezone) VALUES
    ('NYY', 'New York Yankees', 'A', 'AL East', 'Yankee Stadium', 'America/New_York'),
    ('BOS', 'Boston Red Sox', 'A', 'AL East', 'Fenway Park', 'America/New_York'),
    ('LAD', 'Los Angeles Dodgers', 'N', 'NL West', 'Dodger Stadium', 'America/Los_Angeles'),
    ('HOU', 'Houston Astros', 'A', 'AL West', 'Minute Maid Park', 'America/Chicago'),
    ('ATL', 'Atlanta Braves', 'N', 'NL East', 'Truist Park', 'America/New_York'),
    ('CHC', 'Chicago Cubs', 'N', 'NL Central', 'Wrigley Field', 'America/Chicago'),
    ('SDP', 'San Diego Padres', 'N', 'NL West', 'Petco Park', 'America/Los_Angeles'),
    ('SFG', 'San Francisco Giants', 'N', 'NL West', 'Oracle Park', 'America/Los_Angeles'),
    ('PHI', 'Philadelphia Phillies', 'N', 'NL East', 'Citizens Bank Park', 'America/New_York'),
    ('STL', 'St. Louis Cardinals', 'N', 'NL Central', 'Busch Stadium', 'America/Chicago'),
    ('NYM', 'New York Mets', 'N', 'NL East', 'Citi Field', 'America/New_York'),
    ('MIL', 'Milwaukee Brewers', 'N', 'NL Central', 'American Family Field', 'America/Chicago'),
    ('TOR', 'Toronto Blue Jays', 'A', 'AL East', 'Rogers Centre', 'America/Toronto'),
    ('BAL', 'Baltimore Orioles', 'A', 'AL East', 'Oriole Park', 'America/New_York'),
    ('TBR', 'Tampa Bay Rays', 'A', 'AL East', 'Tropicana Field', 'America/New_York'),
    ('CLE', 'Cleveland Guardians', 'A', 'AL Central', 'Progressive Field', 'America/New_York'),
    ('MIN', 'Minnesota Twins', 'A', 'AL Central', 'Target Field', 'America/Chicago'),
    ('DET', 'Detroit Tigers', 'A', 'AL Central', 'Comerica Park', 'America/New_York'),
    ('CHW', 'Chicago White Sox', 'A', 'AL Central', 'Guaranteed Rate Field', 'America/Chicago'),
    ('KCR', 'Kansas City Royals', 'A', 'AL Central', 'Kauffman Stadium', 'America/Chicago'),
    ('TEX', 'Texas Rangers', 'A', 'AL West', 'Globe Life Field', 'America/Chicago'),
    ('SEA', 'Seattle Mariners', 'A', 'AL West', 'T-Mobile Park', 'America/Los_Angeles'),
    ('OAK', 'Oakland Athletics', 'A', 'AL West', 'Oakland Coliseum', 'America/Los_Angeles'),
    ('LAA', 'Los Angeles Angels', 'A', 'AL West', 'Angel Stadium', 'America/Los_Angeles'),
    ('MIA', 'Miami Marlins', 'N', 'NL East', 'LoanDepot Park', 'America/New_York'),
    ('WSN', 'Washington Nationals', 'N', 'NL East', 'Nationals Park', 'America/New_York'),
    ('CIN', 'Cincinnati Reds', 'N', 'NL Central', 'Great American Ball Park', 'America/New_York'),
    ('PIT', 'Pittsburgh Pirates', 'N', 'NL Central', 'PNC Park', 'America/New_York'),
    ('COL', 'Colorado Rockies', 'N', 'NL West', 'Coors Field', 'America/Denver'),
    ('ARI', 'Arizona Diamondbacks', 'N', 'NL West', 'Chase Field', 'America/Phoenix')
ON CONFLICT (team_id) DO NOTHING;
