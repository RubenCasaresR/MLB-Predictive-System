import requests
from sqlalchemy import create_engine, text

# Force IPv4
DB_URL = "postgresql://mlb_user:@127.0.0.1:5432/mlb_predictive"
engine = create_engine(DB_URL)
with engine.connect() as conn:
    row = conn.execute(text("SELECT mlb_game_pk FROM games WHERE game_date='2026-05-22' AND status='FINAL' LIMIT 1")).fetchone()
if row:
    pk = row[0]
    print(f"Fetching play-by-play for gamePk={pk}...")
    url = f"https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"
    params = {"fields": "liveData,plays,allPlays,result,about,matchup,playEvents"}
    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()
    plays = data.get("liveData",{}).get("plays",{}).get("allPlays",[])
    print(f"Total plays: {len(plays)}")
    for i, play in enumerate(plays[:5]):
        about = play.get("about", {})
        ab_idx_about = about.get("atBatIndex")
        ab_idx_top = play.get("atBatIndex")
        print(f"Play {i}: about.atBatIndex={ab_idx_about}, top-level atBatIndex={ab_idx_top}")
        if "atBatIndex" not in about:
            print(f"  WARNING: atBatIndex NOT in about keys! about keys={list(about.keys())}")
        if ab_idx_about is None and ab_idx_top is not None:
            print(f"  *** FOUND IT: atBatIndex is at TOP level, not inside about!")
else:
    print("No FINAL game found for 2026-05-22")
