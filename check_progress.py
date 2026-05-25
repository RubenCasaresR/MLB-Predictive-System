from sqlalchemy import create_engine, text
from etl.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    dates = conn.execute(text("""
        SELECT RIGHT(game_id, 6) AS yymmdd, COUNT(DISTINCT game_id) AS games, COUNT(*) AS at_bats
        FROM at_bats
        GROUP BY RIGHT(game_id, 6)
        ORDER BY RIGHT(game_id, 6)
    """)).fetchall()
    print("Games by date:")
    for d in dates:
        yy = "20" + d.yymmdd[:2]
        mm = d.yymmdd[2:4]
        dd = d.yymmdd[4:6]
        print(f"  {yy}-{mm}-{dd}: {d.games} games, {d.at_bats} at_bats")
    total_games = sum(d.games for d in dates)
    total_at_bats = sum(d.at_bats for d in dates)
    print(f"\nTotal: {total_games} games, {total_at_bats} at_bats")
