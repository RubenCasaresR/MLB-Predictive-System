import json, requests

target_pk = 824679
url = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live".format(pk=target_pk)

# Exact same fields param as the ingestor
params = {"fields": "liveData,plays,allPlays,result,about,matchup,playEvents,count,details,pitchData,breaks,coordinates,hitData"}
resp = requests.get(url, params=params, timeout=30)
data = resp.json()
plays = data.get("liveData",{}).get("plays",{}).get("allPlays",[])

print("Total plays:", len(plays))
play = plays[0]
print("\n=== TOP-LEVEL KEYS ===")
for k, v in play.items():
    if isinstance(v, dict):
        print(" ", k, ": dict with keys=", list(v.keys()))
    elif isinstance(v, list):
        print(" ", k, ": list of len=", len(v))
    else:
        print(" ", k, ":", type(v).__name__, "=", repr(v)[:100])

# Check for atBatIndex at top level
ab_top = play.get("atBatIndex")
ab_about = play.get("about", {}).get("atBatIndex")
print("\nplay.get('atBatIndex'):", ab_top)
print("play['about'].get('atBatIndex'):", ab_about)

# Scan ALL plays for top-level atBatIndex
has_at_bat = 0
no_at_bat = 0
for p in plays:
    if p.get("atBatIndex") is not None:
        has_at_bat += 1
    else:
        no_at_bat += 1

print("\nPlays WITH top-level atBatIndex:", has_at_bat)
print("Plays WITHOUT top-level atBatIndex:", no_at_bat)

if has_at_bat > 0:
    for i, p in enumerate(plays[:5]):
        print("  Play {}: atBatIndex={}, result keys={}, about keys={}".format(i, p.get("atBatIndex"), list(p.get("result",{}).keys()), list(p.get("about",{}).keys())))
