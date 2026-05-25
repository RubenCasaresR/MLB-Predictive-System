import json, requests
from datetime import date

# Fetch schedule for May 22
sched_url = "https://statsapi.mlb.com/api/v1/schedule"
params = {"date": "2026-05-22", "sportId": 1}
resp = requests.get(sched_url, params=params, timeout=30)
data = resp.json()

games = []
for date_entry in data.get("dates", []):
    for game in date_entry.get("games", []):
        games.append(game)

print(f"Found {len(games)} games on 2026-05-22")

# Pick first FINAL game
target_pk = None
for g in games:
    if g["status"]["detailedState"] == "Final":
        target_pk = g["gamePk"]
        print(f"Using gamePk={target_pk}: {g['teams']['away']['team']['name']} @ {g['teams']['home']['team']['name']}")
        break

if not target_pk:
    print("No FINAL games found")
    exit(1)

# Fetch play-by-play
url = f"https://statsapi.mlb.com/api/v1.1/game/{target_pk}/feed/live"
params2 = {"fields": "liveData,plays,allPlays,result,about,matchup,playEvents"}
resp2 = requests.get(url, params=params2, timeout=30)
data2 = resp2.json()
plays = data2.get("liveData",{}).get("plays",{}).get("allPlays",[])
print(f"\nTotal plays in game: {len(plays)}")

# Categorize plays
normal_abs = 0
non_abs = 0
for play in plays:
    about = play.get("about", {})
    ab_idx_top = play.get("atBatIndex")
    if about.get("atBatIndex") is not None:
        normal_abs += 1
    elif ab_idx_top is not None:
        non_abs += 1
        print(f"  Non-about atBatIndex (top-level={ab_idx_top}): event={play.get('result',{}).get('event','N/A')}")
    else:
        non_abs += 1
        if non_abs <= 5:
            print(f"  No atBatIndex at all: event={play.get('result',{}).get('event','N/A')}")

print(f"\nPlays with about.atBatIndex: {normal_abs}")
print(f"Plays without about.atBatIndex: {non_abs}")

# Show first 3 normal plays
print(f"\n--- First 3 normal plays ---")
count = 0
for play in plays:
    ab_idx = play.get("about", {}).get("atBatIndex")
    if ab_idx is not None:
        count += 1
        print(f"  ab_id={ab_idx}, event={play.get('result',{}).get('event','N/A')}, isOut={play.get('result',{}).get('isOut','N/A')}")
        if count >= 3:
            break
