"""
reconcile_public.py — the public-data part of the build reconciliation: how much each episode rule moves the
headline values, reverting one rule at a time from the public build (F1). Reads public inputs only.

Variants (each changes one rule and keeps the rest of F1):
  F1                                           as built (appearance-validated ends, [start, end) counting, merge)
  F1 with end date counted as a game missed    [start, end] counting
  F1 with COVID-era blank placements kept      placements the census flags covid_era_blank are kept
  F1 with activation-only ends                 an episode ends at the first activation line in the transaction
                                               feed, with no appearance check (needs inputs/txns_live.jsonl)
  F1 without merging                           back-to-back placements for one player-club kept separate

The full reconciliation in the study also walks a non-public IL list into F1; that arm is not part of this
repository. Usage (from the repository root): python3 pipeline/reconcile_public.py [--out <folder>]
Output: results/reconciliation_public.json
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
args = ap.parse_args()
RES = os.path.join(args.out, "results")
os.makedirs(RES, exist_ok=True)
KEYS = ["Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv", "Sweeper_Injury_Risk/data/txns_live.jsonl",
        "_staging_tmp/fangraphs_war_2010_2025.csv", "Postseason_Injury_Risk/data/games_flat.csv",
        "Postseason_Injury_Risk/data/standings.csv", "Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_results.json"]
P_ = paths.resolve
missing = [k for k in KEYS if not os.path.exists(P_(k))]
if missing:
    sys.exit(f"missing inputs: {[os.path.relpath(P_(k), paths.REPO) for k in missing]} (see README)")
hashes = {k: paths.sha16(P_(k)) for k in KEYS}
bad = [k for k in KEYS if paths.FILES[k][2] and hashes[k] != paths.FILES[k][2]]
if bad:
    sys.exit(f"PIN FAIL {bad}")
OUTCOME = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
W = (5, 4, 3)
F1R = json.load(open(P_("Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_results.json")))

# --------------------------------------------------------------------------- schedule, standings, FanGraphs
G = pd.read_csv(P_("Postseason_Injury_Risk/data/games_flat.csv"))
G = G[(G.gameType == "R") & G.status.isin(["Final", "Completed Early"])].copy()
G["date"] = pd.to_datetime(G.date)
tg = pd.concat([G[["season", "date", "home_id", "home"]].rename(columns={"home_id": "tid", "home": "team"}),
                G[["season", "date", "away_id", "away"]].rename(columns={"away_id": "tid", "away": "team"})])
TEAM_DATES = {k: np.sort(v.date.to_numpy()) for k, v in tg.groupby(["season", "tid"])}
SPAN = {s: (g.date.min(), g.date.max()) for s, g in G.groupby("season")}
NAME = tg.sort_values("season").groupby("tid").team.last().to_dict()
ID_OF = {v: k for k, v in NAME.items()}
ALIAS = {"Cleveland Indians": "Cleveland Guardians", "Oakland Athletics": "Athletics", "Florida Marlins": "Miami Marlins"}


def games_between(season, tid, a, b):
    d = TEAM_DATES.get((season, tid))
    if d is None:
        return np.nan
    return int(np.searchsorted(d, np.datetime64(b), side="right") - np.searchsorted(d, np.datetime64(a), side="left"))


fg = pd.read_csv(P_("_staging_tmp/fangraphs_war_2010_2025.csv")).rename(columns={"mlbamid": "player_id"})
fg = fg.dropna(subset=["player_id"]); fg["player_id"] = fg.player_id.astype(int)
war0 = fg.groupby(["player_id", "season"]).agg(war=("war", "sum")).reset_index()
st = pd.read_csv(P_("Postseason_Injury_Risk/data/standings.csv"))[["season", "team_id", "W", "L"]].rename(columns={"team_id": "tid"})
ABBR = {"ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox",
        "CHC": "Chicago Cubs", "CHW": "Chicago White Sox", "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians",
        "COL": "Colorado Rockies", "DET": "Detroit Tigers", "HOU": "Houston Astros", "KCR": "Kansas City Royals",
        "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers",
        "MIN": "Minnesota Twins", "NYM": "New York Mets", "NYY": "New York Yankees", "OAK": "Athletics", "ATH": "Athletics",
        "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SDP": "San Diego Padres", "SEA": "Seattle Mariners",
        "SFG": "San Francisco Giants", "STL": "St. Louis Cardinals", "TBR": "Tampa Bay Rays", "TEX": "Texas Rangers",
        "TOR": "Toronto Blue Jays", "WSN": "Washington Nationals", "FLA": "Miami Marlins"}
fgp = fg[fg.season.isin(OUTCOME)].copy()
fgp["tid"] = fgp.team.map(ABBR).map(ID_OF)
fgp = fgp.dropna(subset=["tid"]).drop_duplicates(["player_id", "season", "tid"])


# --------------------------------------------------------------------------- one parameterised builder
def build(pl, end_rule, merge=True):
    """pl: DataFrame(pid, tid, start0, endraw). end_rule 'inclusive' (v1) or 'exclusive' (F1)."""
    rows = []
    for s in range(2012, 2026):
        if s not in SPAN:
            continue
        a, b = SPAN[s]
        x = pl[(pl.start0 <= b) & (pl.endraw.fillna(b) >= a) & pl.start0.dt.year.between(s - 1, s)].copy()
        x["start"] = x.start0.clip(lower=a)
        if end_rule == "inclusive":
            x["end"] = x.endraw.fillna(b).clip(upper=b)
        else:
            x["end"] = (x.endraw.fillna(b + pd.Timedelta(days=1)) - pd.Timedelta(days=1)).clip(upper=b)
        x = x[x.end >= x.start].sort_values(["pid", "tid", "start"])
        for (pid, tid), g in x.groupby(["pid", "tid"]):
            cs = ce = None
            for s0, e0 in zip(g.start, g.end):
                if cs is None:
                    cs, ce = s0, e0
                elif merge and s0 <= ce + pd.Timedelta(days=1):
                    ce = max(ce, e0)
                else:
                    rows.append((s, pid, tid, cs, ce)); cs, ce = s0, e0
            rows.append((s, pid, tid, cs, ce))
    S = pd.DataFrame(rows, columns=["season", "pid", "tid", "start", "end"])
    S["games_missed"] = [games_between(s, t, a, b) for s, t, a, b in zip(S.season, S.tid, S.start, S.end)]
    gm = S.groupby(["pid", "season"]).games_missed.sum().rename("gm").reset_index().rename(columns={"pid": "player_id"})
    war = war0.merge(gm, on=["player_id", "season"], how="left").fillna({"gm": 0})
    war["exposure"] = (np.where(war.season == 2020, 60, 162) - war.gm).clip(lower=1)
    Wd = {(p, s): (w, e) for p, s, w, e in zip(war.player_id, war.season, war.war, war.exposure)}

    def rate(pid, s):
        num = den = 0.0
        for w, k in zip(W, (1, 2, 3)):
            v = Wd.get((pid, s - k))
            if v is not None:
                num += w * v[0]; den += w * v[1]
        return num / (den + 100)
    S = S[S.season.isin(OUTCOME)].copy()
    S["war_lost"] = np.clip([rate(p, s) for p, s in zip(S.pid, S.season)], 0, None) * S.games_missed
    T = S.groupby(["season", "tid"]).agg(episodes=("pid", "size"), games_missed=("games_missed", "sum"), war_lost=("war_lost", "sum")).reset_index()
    T = T.merge(st, on=["season", "tid"], how="left")
    assert T.W.notna().all() and len(T) == 300
    f = fgp.copy(); f["proj_war"] = [rate(p, s) * 162 for p, s in zip(f.player_id, f.season)]
    T = T.merge(f.groupby(["season", "tid"]).proj_war.sum().rename("team_proj").reset_index(), on=["season", "tid"], how="left")
    T = T.sort_values(["tid", "season"]).reset_index(drop=True)
    T["W_prev"] = T.groupby("tid").W.shift(1)
    return S, T


def summary(S, T):
    M = T.dropna(subset=["W_prev", "team_proj"])
    X = pd.concat([M[["war_lost", "team_proj", "W_prev"]], pd.get_dummies(M.season, prefix="s", drop_first=True, dtype=float)], axis=1)
    fm = sm.OLS(M.W, sm.add_constant(X)).fit(cov_type="cluster", cov_kwds={"groups": M.tid})
    return {"mean": float(T.war_lost.mean()), "sd_within_season": float(T.groupby("season").war_lost.std().mean()),
            "p10": float(T.war_lost.quantile(.1)), "p90": float(T.war_lost.quantile(.9)),
            "wins_per_war_lost": float(fm.params["war_lost"]), "wins_per_war_lost_se": float(fm.bse["war_lost"]),
            "episodes_per_club_season": float(T.episodes.mean()), "games_missed_per_club_season": float(T.games_missed.mean()),
            "games_missed_per_episode": float(S.games_missed.sum() / len(S)), "n": int(len(M))}



PL = pd.read_csv(P_("Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv"), parse_dates=["il_start", "il_end"])
ACT_RE = re.compile(r"\b(activated|reinstated)\b", re.I)
OTHER_RE = re.compile(r"paternity|bereavement|restricted|reserve list|inactive|suspen|military", re.I)
acts = {}
seen = set()
with open(P_("Sweeper_Injury_Risk/data/txns_live.jsonl")) as fh:
    for line in fh:
        t = json.loads(line)
        if t.get("typeDesc") != "Status Change":
            continue
        d = t.get("description") or ""
        p = (t.get("person") or {}).get("id")
        if p is None or t.get("id") in seen or not ACT_RE.search(d) or OTHER_RE.search(d):
            continue
        seen.add(t.get("id"))
        acts.setdefault(int(p), []).append(np.datetime64(pd.Timestamp(t.get("date"))))
acts = {k: np.sort(np.array(v, dtype="datetime64[ns]")) for k, v in acts.items()}


def next_act(pid, d):
    a = acts.get(int(pid))
    if a is None:
        return pd.NaT
    j = np.searchsorted(a, np.datetime64(d), side="right")
    return pd.Timestamp(a[j]) if j < len(a) else pd.NaT


PL["act_end"] = [next_act(p, d) for p, d in zip(PL.mlbam, PL.il_start)]
chk = PL[PL.il_end_src == "activation"]
act_match = float((chk.act_end == chk.il_end).mean())
FEED = PL[~PL.covid_era_blank]
FEED_ACT = pd.DataFrame({"pid": FEED.mlbam, "tid": FEED.club_id.astype(int), "start0": FEED.il_start, "endraw": FEED.act_end})
FEED_F1 = pd.DataFrame({"pid": FEED.mlbam, "tid": FEED.club_id.astype(int), "start0": FEED.il_start, "endraw": FEED.il_end})

# --------------------------------------------------------------------------- one rule at a time from F1
S4, T4 = build(FEED_F1, "exclusive")
oat = {"F1": summary(S4, T4)}
f1_equal = (abs(oat["F1"]["mean"] - F1R["war_lost"]["mean"]) < 1e-9 and abs(oat["F1"]["sd_within_season"] - F1R["war_lost"]["sd_within_season"]) < 1e-9
            and abs(oat["F1"]["wins_per_war_lost"] - F1R["wins_per_war_lost"]["est"]) < 1e-9)
if not f1_equal:
    sys.exit("F1 not reproduced from the census")
_, t = build(FEED_F1, "inclusive"); oat["F1 with end date counted as a game missed"] = summary(_, t)
FB = PL.copy()
_, t = build(pd.DataFrame({"pid": FB.mlbam, "tid": FB.club_id.astype(int), "start0": FB.il_start, "endraw": FB.il_end}), "exclusive")
oat["F1 with COVID-era blank placements kept"] = summary(_, t)
_, t = build(FEED_ACT, "exclusive"); oat["F1 with activation-only ends"] = summary(_, t)
_, t = build(FEED_F1, "exclusive", merge=False); oat["F1 without merging"] = summary(_, t)
R = {"meta": {"inputs_sha16": hashes, "f1_reproduced": bool(f1_equal), "activation_rule_match_on_census_activation_rows": act_match,
              "note": "public inputs only; the study's walk from a non-public IL list into F1 is not part of this repository"},
     "one_at_a_time_from_F1": oat}
json.dump(R, open(os.path.join(RES, "reconciliation_public.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
for k_, v in oat.items():
    print(f"{k_:48s} mean {v['mean']:.3f} sd {v['sd_within_season']:.3f} wins/WAR {v['wins_per_war_lost']:.3f} games/episode {v['games_missed_per_episode']:.1f}")
