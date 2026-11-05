"""postseason_rounds.py - how far each postseason club went, from the public MLB Stats API (post hoc, 2026-11-04).

For each outcome season, every postseason game (gameTypes F wild card, D division series, L league championship, W World
Series) with its winner, reduced to one row per club: the last round reached and whether it won that round. Writes
data_public/postseason_rounds_2015_2025.csv. Needs network access to statsapi.mlb.com.
usage: python3 pipeline/postseason_rounds.py
"""
import json, os, urllib.request
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASONS = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
ROUND = {"F": 1, "D": 2, "L": 3, "W": 4}; NAME = {1: "wild_card", 2: "division_series", 3: "league_championship", 4: "world_series"}
rows = []
for s in SEASONS:
    u = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&season={s}&gameTypes=F,D,L,W"
         "&fields=dates,games,gamePk,gameType,teams,home,away,team,id,name,isWinner,status,detailedState")
    j = json.load(urllib.request.urlopen(u, timeout=60))
    games = [g for d in j["dates"] for g in d["games"] if g["status"]["detailedState"] == "Final"]
    wins = {}; played = {}
    for g in games:
        r = ROUND[g["gameType"]]
        for side in ("home", "away"):
            t = g["teams"][side]["team"]; tid = t["id"]
            played.setdefault(tid, {"name": t["name"], "rounds": set()})["rounds"].add(r)
            if g["teams"][side].get("isWinner"):
                wins[(tid, r)] = wins.get((tid, r), 0) + 1
    for tid, v in played.items():
        last = max(v["rounds"])
        # a club wins a round if it played the next one, or if it is the World Series winner (more wins than its opponent)
        if last == 4:
            opp = [t for t in played if 4 in played[t]["rounds"] and t != tid][0]
            won = wins.get((tid, 4), 0) > wins.get((opp, 4), 0)
        else:
            won = False
        rows.append({"season": s, "tid": tid, "club": v["name"], "last_round": last, "last_round_name": NAME[last], "won_last_round": won,
                     "world_series_winner": last == 4 and won, "pennant": last == 4})
out = pd.DataFrame(rows).sort_values(["season", "last_round", "won_last_round"], ascending=[True, False, False])
os.makedirs(os.path.join(REPO, "data_public"), exist_ok=True)
out.to_csv(os.path.join(REPO, "data_public", "postseason_rounds_2015_2025.csv"), index=False)
print(out[out.pennant][["season", "club", "world_series_winner"]].to_string(index=False))
print("clubs per season:", out.groupby("season").size().to_dict())
