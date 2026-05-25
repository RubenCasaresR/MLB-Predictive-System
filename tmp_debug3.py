import json, requests

target_pk = 824679
url = f"https://statsapi.mlb.com/api/v1.1/game/{target_pk}/feed/live"
params = {"fields": "liveData,plays,allPlays,result,about,isComplete,atBatIndex,isScoringPlay,isTopInning,halfInning,inning,outs,matchup,playEvents,details,event,isOut"}
resp = requests.get(url, params=params, timeout=30)
data = resp.json()
plays = data.get("liveData",{}).get("plays",{}).get("allPlays",[])

print(f"Total plays: {len(plays)}")
play = plays[0]
print("\n=== TOP-LEVEL KEYS ===")
for k, v in play.items():
    if isinstance(v, dict):
        print(f"  {k}: dict with keys={list(v.keys())}")
    elif isinstance(v, list):
        print(f"  {k}: list of len={len(v)}")
    else:
        print(f"  {k}: {type(v).__name__} = {repr(v)[:100]}")

print("\n=== ABOUT ===")
about = play.get("about", {})
for k, v in about.items():
    print(f"  {k}: {repr(v)[:100]}")

print("\n=== RESULT ===")
result = play.get("result", {})
for k, v in result.items():
    print(f"  {k}: {repr(v)[:100]}")

# Now check ALL plays for atBatIndex
print("\n=== SCANNING ALL PLAYS ===")
found_in_about = 0
found_top_level = 0
found_none = 0
for i, play in enumerate(plays):
    ab_about = play.get("about", {}).get("atBatIndex")
    ab_top = play.get("atBatIndex")
    if ab_about is not None:
        found_in_about += 1
    elif ab_top is not None:
        found_top_level += 1
        if found_top_level <= 3:
            print(f"  Play {i}: TOP-LEVEL atBatIndex={ab_top}, event={play.get('result',{}).get('event','N/A')}")
    else:
        found_none += 1

print(f"\n  atBatIndex IN about: {found_in_about}")
print(f"  atBatIndex TOP-level: {found_top_level}")
print(f"  No atBatIndex (non-AB): {found_none}")
