import json, requests

target_pk = 824679
url = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live".format(pk=target_pk)

# Test without any fields param
resp = requests.get(url, timeout=30)
data = resp.json()
plays = data.get("liveData",{}).get("plays",{}).get("allPlays",[])

print("Total plays:", len(plays))
play = plays[0]

# Top-level keys
print("\n=== TOP-LEVEL KEYS (no fields filter) ===")
for k, v in play.items():
    if isinstance(v, dict):
        print(" ", k, ": dict with keys=", list(v.keys())[:10])
    elif isinstance(v, list):
        print(" ", k, ": list of len=", len(v))
    else:
        print(" ", k, ":", type(v).__name__, "=", repr(v)[:100])

# Check atBatIndex
print("\nplay.get('atBatIndex'):", play.get("atBatIndex"))
print("play['about'].get('atBatIndex'):", play.get("about", {}).get("atBatIndex"))

# Scan for atBatIndex
has = sum(1 for p in plays if p.get("atBatIndex") is not None)
no = sum(1 for p in plays if p.get("atBatIndex") is None)
print("\nWith atBatIndex:", has, " Without:", no)

# Check first few non-at-bat plays
for i, p in enumerate(plays):
    if p.get("atBatIndex") is None:
        print("\nFirst non-AB play (index {}):".format(i))
        print("  result.event:", p.get("result",{}).get("event"))
        print("  about.halfInning:", p.get("about",{}).get("halfInning"))
        print("  about.inning:", p.get("about",{}).get("inning"))
        break
