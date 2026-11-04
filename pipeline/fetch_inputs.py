"""fetch_inputs.py - rebuild every MLB Stats API input of the pipeline from the public API (post hoc, 2026-11-04).

Writes, into --out (default inputs/):
  games_flat.csv      regular-season schedule 2010-2026, one row per game PLAYED, on the date it was played. A postponed or
                      suspended game and its make-up share one gamePk; the make-up record is kept. (The schedule file the
                      sealed results were built from kept the postponed record instead and so lost 667 make-up games,
                      DEVIATIONS #31. Pass --emulate-pinned to reproduce that file's games for a reproduction check.)
  standings.csv       season, team_id, W, L, league_id, division_id, qualified (appears in a postseason game)
  gamelogs_flat.csv   pitcher game logs: player_id, season, date, gamePk, GS, team, team_id
  people.csv          mlbam, name, birth_date, mlb_debut, primary_position, height, weight, bats, throws
  txns_live.jsonl     transactions 2010-01-01 .. --txn-end, one API record per line
FanGraphs WAR is licensed and is not fetched here (see README). Baseball-Reference WAR, for the bWAR robustness check, is
fetched by bwar_input.py. The API is revised over time, so files fetched later will not match the pinned hashes byte for
byte; set the pins in pipeline/paths.py to your files. A pull on 2026-11-04 reproduced every headline value of the paper
(DEVIATIONS #31).

usage: python3 pipeline/fetch_inputs.py [--out inputs] [--emulate-pinned] [--txn-end 2026-09-29] [--workers 8]
"""
import argparse, concurrent.futures as cf, datetime as dt, json, os, time, urllib.request
import pandas as pd

API = "https://statsapi.mlb.com/api/v1"
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inputs"))
ap.add_argument("--emulate-pinned", action="store_true", help="keep the first-listed record of each gamePk (drops make-ups)")
ap.add_argument("--txn-end", default="2026-09-29")
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--people-ids", default=None, help="optional CSV with an mlbam column of extra ids (e.g. the FanGraphs export)")
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)


def get(u, tries=5):
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-replication"}), timeout=120).read())
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(2 + 3 * i)
    raise RuntimeError(f"{u}: {err}")


# ---- schedule ------------------------------------------------------------------------------------------------------
rows = []
for s in range(2010, 2027):
    for day in get(f"{API}/schedule?sportId=1&season={s}&gameType=R")["dates"]:
        for g in day["games"]:
            if g["gameType"] != "R":
                continue
            t = g["teams"]
            rows.append({"gamePk": g["gamePk"], "season": int(g.get("season", s)), "gameType": "R", "date": g.get("officialDate", day["date"]),
                         "listed_date": day["date"], "status": g["status"]["detailedState"], "home_id": t["home"]["team"]["id"],
                         "home": t["home"]["team"]["name"], "away_id": t["away"]["team"]["id"], "away": t["away"]["team"]["name"],
                         "home_score": t["home"].get("score"), "away_score": t["away"].get("score")})
    print("schedule", s, flush=True)
A = pd.DataFrame(rows)
A["played"] = A.status.str.startswith("Final") | A.status.str.startswith("Completed Early")
if a.emulate_pinned:
    G = A.sort_values(["gamePk", "listed_date"]).drop_duplicates("gamePk", keep="first"); G = G[G.played]
else:
    G = A[A.played].sort_values(["gamePk", "date"]).drop_duplicates("gamePk", keep="last")
cols = ["gamePk", "season", "gameType", "date", "status", "home_id", "home", "away_id", "away", "home_score", "away_score"]
G[cols].sort_values(["season", "date", "gamePk"]).to_csv(os.path.join(a.out, "games_flat.csv"), index=False)
print("games", len(G), "(make-ups dropped)" if a.emulate_pinned else "(make-ups kept)", flush=True)

# ---- standings (qualified = played a postseason game) ------------------------------------------------------------------
post = set()
for s in range(2010, 2027):
    for day in get(f"{API}/schedule?sportId=1&season={s}&gameType=F,D,L,W")["dates"]:
        for g in day["games"]:
            post |= {(s, g["teams"]["home"]["team"]["id"]), (s, g["teams"]["away"]["team"]["id"])}
st = []
for s in range(2010, 2027):
    for rec in get(f"{API}/standings?leagueId=103,104&season={s}&standingsTypes=regularSeason")["records"]:
        for t in rec["teamRecords"]:
            st.append({"season": s, "team_id": t["team"]["id"], "W": t["wins"], "L": t["losses"], "league_id": rec["league"]["id"],
                       "division_id": rec["division"]["id"], "qualified": (s, t["team"]["id"]) in post})
pd.DataFrame(st).to_csv(os.path.join(a.out, "standings.csv"), index=False)

# ---- transactions ---------------------------------------------------------------------------------------------------
end = dt.date.fromisoformat(a.txn_end); d = dt.date(2010, 1, 1)
with open(os.path.join(a.out, "txns_live.jsonl"), "w") as fh:
    while d <= end:
        e = min(dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1) - dt.timedelta(days=1), end)
        for x in get(f"{API}/transactions?sportId=1&startDate={d}&endDate={e}")["transactions"]:
            fh.write(json.dumps(x) + "\n")
        d = e + dt.timedelta(days=1)
print("transactions written", flush=True)

# ---- pitcher game logs ------------------------------------------------------------------------------------------------
jobs = []
for s in range(2010, 2027):
    sp = get(f"{API}/stats?stats=season&group=pitching&season={s}&sportId=1&playerPool=ALL&limit=5000")["stats"][0]["splits"]
    jobs += [(s, x["player"]["id"]) for x in sp]


def one(j):
    s, p = j
    d_ = get(f"{API}/people/{p}/stats?stats=gameLog&group=pitching&season={s}&sportId=1&gameType=R")
    sp = d_["stats"][0]["splits"] if d_.get("stats") else []
    return [(p, s, x["date"], x["game"]["gamePk"], int(x["stat"].get("gamesStarted", 0) or 0), (x.get("team") or {}).get("name"),
             (x.get("team") or {}).get("id")) for x in sp]


gl = []
with cf.ThreadPoolExecutor(a.workers) as ex:
    for r in ex.map(one, sorted(set(jobs))):
        gl += r
GL = pd.DataFrame(gl, columns=["player_id", "season", "date", "gamePk", "GS", "team", "team_id"]).drop_duplicates(["player_id", "gamePk"])
GL.to_csv(os.path.join(a.out, "gamelogs_flat.csv"), index=False); print("game logs", len(GL), flush=True)

# ---- people ---------------------------------------------------------------------------------------------------------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ids = set(GL.player_id) | set(pd.read_csv(os.path.join(REPO, "data_public", "placements_public.csv")).mlbam) \
    | set(pd.read_csv(os.path.join(REPO, "data_public", "opening_day_40man_2015_2026.csv")).mlbam)
if a.people_ids:
    ids |= set(pd.read_csv(a.people_ids).iloc[:, 0].dropna().astype(int))
ids = sorted(int(i) for i in ids); pp = []
for i in range(0, len(ids), 300):
    for p in get(f"{API}/people?personIds=" + ",".join(map(str, ids[i:i + 300])))["people"]:
        pp.append({"mlbam": p["id"], "name": p.get("fullName"), "birth_date": p.get("birthDate"), "mlb_debut": p.get("mlbDebutDate"),
                   "primary_position": (p.get("primaryPosition") or {}).get("abbreviation"), "height": p.get("height"), "weight": p.get("weight"),
                   "bats": (p.get("batSide") or {}).get("code"), "throws": (p.get("pitchHand") or {}).get("code")})
pd.DataFrame(pp).to_csv(os.path.join(a.out, "people.csv"), index=False); print("people", len(pp), "\ndone", flush=True)
