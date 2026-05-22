import requests, json
key = '7ba003e078bcffd206d41a3c51cc5d77'
r = requests.get('https://api.the-odds-api.com/v4/sports/baseball_mlb/odds', params={'apiKey': key, 'regions': 'us', 'markets': 'h2h', 'oddsFormat': 'american'}, timeout=10)
events = r.json()
eid = events[0]['id']
print('Event:', eid, events[0]['away_team'], '@', events[0]['home_team'])
r2 = requests.get('https://api.the-odds-api.com/v4/sports/baseball_mlb/events/' + eid + '/odds', params={'apiKey': key, 'regions': 'us', 'markets': 'player_strikeouts', 'oddsFormat': 'american'}, timeout=10)
print('Player strikeouts status:', r2.status_code)
if r2.status_code == 200:
    data = r2.json()
    print('Bookmakers:', len(data.get('bookmakers', [])))
    for bm in data.get('bookmakers', [])[:1]:
        for m in bm.get('markets', []):
            print('Market:', m['key'])
            for o in m.get('outcomes', [])[:3]:
                print(' ', o.get('name'), o.get('price'), 'pt:', o.get('point', 'N/A'))
else:
    print(r2.text[:500])
