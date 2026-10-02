"""
phase2.py - injury luck in MLB on public data, Phase 2 (the full paper).

Declared in PREREGISTRATION_ADDENDUM_PHASE2_2026-10-02.md (sealed 6634bfeb1212f484, SEAL_PHASE2.txt) before any of
these quantities was computed. Adds P2.1-P2.8 to the sealed preregistration (3fd792e537b6834b); amends nothing in it.

  P2.1  preseason talent control from the opening-day 40-man roster (the paper's primary specification)
  P2.2  reverse-causality designs with the preseason control, and their range
  P2.3  episode-end rule: appearance-validated (primary) vs activation only
  P2.4  projection sensitivity: K = 50, 100, 200 and an age-adjusted Marcel
  P2.5  persistence of the unforeseen part under the preseason control; calibrated null and power; the carry-over
        decomposition of year-to-year persistence
  P2.6  families and roster slots (descriptive; group-level foreseeability)
  P2.7  decision levers: carry-over visibility, depth as insurance, workload (cited)
  P2.8  2026 out-of-sample check (models fitted through 2025, not refitted)

The episode, projection and club-season code is copied from injury_luck.py (R1 rule) so that this script imports no
other pipeline file. Before anything else it rebuilds the primary club-season table and stops unless it equals
results/team_season_public.csv within 1e-9.

Usage (library):     python3 phase2.py --root "<MLB Total Research>" [--out <v2_public>] [--B 2000] [--nsim 1000]
Usage (repository):  python3 pipeline/phase2.py [--out <folder>] [--B 2000]   (inputs resolve through pipeline/paths.py)
Writes results/phase2_results.json, results/team_season_phase2.csv, results/team_season_2026_phase2.csv.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import warnings

warnings.formatwarning = lambda msg, cat, fname, lineno, line=None: f"{cat.__name__}: {msg} [{os.path.basename(str(fname))}:{lineno}]\n"
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=None, help="library root (MLB Total Research); omit inside the public repository")
ap.add_argument("--out", default=os.path.dirname(HERE))
ap.add_argument("--B", type=int, default=2000)
ap.add_argument("--nsim", type=int, default=1000)
ap.add_argument("--wcb", type=int, default=9999)
args = ap.parse_args()
T0 = time.time()
OUTDIR = args.out
RES = os.path.join(OUTDIR, "results")
ROSTER_KEY = "IL_Team_Burden/v2_public/data_public/opening_day_40man_2015_2026.csv"
COMPANION_KEY = "Postseason_Injury_Risk/Postseason_results.json"
if args.root:
    def P_(rel):
        return os.path.join(args.root, rel)
else:
    sys.path.insert(0, HERE)
    import paths  # noqa: E402
    P_ = paths.resolve

ADDENDUM = ("PREREGISTRATION_ADDENDUM_PHASE2_2026-10-02.md", "6634bfeb1212f484")
PINS = {
    "Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv": "e5ed2129cf8218ec",
    "_staging_tmp/fangraphs_war_2010_2025.csv": "cad855bb7fd170dc",
    "Postseason_Injury_Risk/data/games_flat.csv": "ad002536e1d8a01b",
    "Postseason_Injury_Risk/data/standings.csv": "911f807ec5f69104",
    "Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv": "08345a5d95486529",
    "Postseason_Injury_Risk/data/people.csv": "b34f61471c31711d",
    "Sweeper_Injury_Risk/data/txns_live.jsonl": "f65ea265e77b5735",
    ROSTER_KEY: "3a4a5b25d1420e1e",
}
SEED = 20261002
OUTCOME = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
SEASONS_P = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
PREV_OF = {2015: 2014, 2016: 2015, 2017: 2016, 2018: 2017, 2019: 2018, 2021: 2019, 2022: 2021, 2023: 2022, 2024: 2023,
           2025: 2024, 2026: 2025}
W = (5, 4, 3)
K = 100
PRE_FEATS = ["team_proj_od", "roster_age_od", "roster_il_days_prev_od"]


def sha16(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()[:16]


def log(*x):
    print(*x, flush=True)


bad, hashes = [], {}
for rel, pin in PINS.items():
    if not os.path.exists(P_(rel)):
        bad.append(f"missing {rel}"); continue
    hashes[rel] = sha16(P_(rel))
    if pin and hashes[rel] != pin:
        bad.append(f"{rel} {hashes[rel]} != {pin}")
ad = os.path.join(OUTDIR, ADDENDUM[0])
if not os.path.exists(ad) or sha16(ad) != ADDENDUM[1]:
    bad.append("addendum hash")
if bad:
    sys.exit(f"PIN FAIL: {bad}")
R = json.load(open(os.path.join(RES, "injury_luck_results.json")))
P1B = json.load(open(os.path.join(RES, "phase1b_results.json")))
assert R["meta"]["episode_rule"] == "r1"

# =====================================================================================================================
# 1. Inputs and the R1 episode build (copied from injury_luck.py; extended to 2026, an activation-only end rule for
#    P2.3, and an age-adjusted projection for P2.4)
# =====================================================================================================================
G = pd.read_csv(P_("Postseason_Injury_Risk/data/games_flat.csv"))
G = G[(G.gameType == "R") & G.status.isin(["Final", "Completed Early"])].copy()
G["date"] = pd.to_datetime(G.date)
tg = pd.concat([G[["season", "date", "home_id", "home"]].rename(columns={"home_id": "tid", "home": "team"}),
                G[["season", "date", "away_id", "away"]].rename(columns={"away_id": "tid", "away": "team"})])
TEAM_DATES = {k: np.sort(v.date.to_numpy()) for k, v in tg.groupby(["season", "tid"])}
SPAN = {s: (g.date.min(), g.date.max()) for s, g in G.groupby("season")}
NAME = tg.sort_values("season").groupby("tid").team.last().to_dict()


def games_between(season, tid, a, b):
    d = TEAM_DATES.get((season, tid))
    if d is None:
        return np.nan
    return int(np.searchsorted(d, np.datetime64(b), side="right") - np.searchsorted(d, np.datetime64(a), side="left"))


PL = pd.read_csv(P_("Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv"), parse_dates=["il_start", "il_end"])
PL["dx"] = PL.dx.fillna("")
P = PL[~PL.covid_era_blank].copy()
P["club_id"] = P.club_id.astype(int)
fg = pd.read_csv(P_("_staging_tmp/fangraphs_war_2010_2025.csv")).rename(columns={"mlbamid": "player_id"})
fg = fg.dropna(subset=["player_id"]); fg["player_id"] = fg.player_id.astype(int)
st_full = pd.read_csv(P_("Postseason_Injury_Risk/data/standings.csv"))
ppl = pd.read_csv(P_("Postseason_Injury_Risk/data/people.csv"), usecols=["mlbam", "birth_date"])
ppl["birth_date"] = pd.to_datetime(ppl.birth_date, errors="coerce")
BIRTH = dict(zip(ppl.mlbam, ppl.birth_date))
ABBR = {"ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox",
        "CHC": "Chicago Cubs", "CHW": "Chicago White Sox", "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians",
        "COL": "Colorado Rockies", "DET": "Detroit Tigers", "HOU": "Houston Astros", "KCR": "Kansas City Royals",
        "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers",
        "MIN": "Minnesota Twins", "NYM": "New York Mets", "NYY": "New York Yankees", "OAK": "Athletics", "ATH": "Athletics",
        "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SDP": "San Diego Padres", "SEA": "Seattle Mariners",
        "SFG": "San Francisco Giants", "STL": "St. Louis Cardinals", "TBR": "Tampa Bay Rays", "TEX": "Texas Rangers",
        "TOR": "Toronto Blue Jays", "WSN": "Washington Nationals", "FLA": "Miami Marlins"}
ID_OF = {v: k for k, v in NAME.items()}
GL = pd.read_csv(P_("Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv"), usecols=["player_id", "season", "date", "gamePk", "GS"])
GL = GL[GL.gamePk.isin(set(G.gamePk))]
SUSP_RX = re.compile(r"placed .* on the restricted list|\bsuspended\b|declared ineligible", re.I)
ACT_RE = re.compile(r"\b(activated|reinstated)\b", re.I)                                     # P2.3 rule B, the
OTHER_RE = re.compile(r"paternity|bereavement|restricted|reserve list|inactive|suspen|military", re.I)  # reconcile pattern
sus, acts, seen = {}, {}, set()
with open(P_("Sweeper_Injury_Risk/data/txns_live.jsonl")) as fh:
    for line in fh:
        t = json.loads(line); d = t.get("description") or ""; pid = (t.get("person") or {}).get("id")
        if pid and SUSP_RX.search(d):
            sus.setdefault(int(pid), []).append(np.datetime64(pd.Timestamp(t.get("effectiveDate") or t.get("date"))))
        if t.get("typeDesc") == "Status Change" and pid is not None and t.get("id") not in seen and ACT_RE.search(d) and not OTHER_RE.search(d):
            seen.add(t.get("id"))
            acts.setdefault(int(pid), []).append(np.datetime64(pd.Timestamp(t.get("date"))))
SUS = {k: np.sort(np.array(v, dtype="datetime64[ns]")) for k, v in sus.items()}
ACTS = {k: np.sort(np.array(v, dtype="datetime64[ns]")) for k, v in acts.items()}


def next_act(pid, d):
    a = ACTS.get(int(pid))
    if a is None:
        return pd.NaT
    j = np.searchsorted(a, np.datetime64(d), side="right")
    return pd.Timestamp(a[j]) if j < len(a) else pd.NaT


def r1_end_dates(P, base_col="il_end", use_pitcher_appearance=True):
    """injury_luck.py r1_end_dates; base_col and use_pitcher_appearance are the P2.3 hooks (defaults = R1 as run)."""
    GLd = GL.assign(date=pd.to_datetime(GL.date))
    app = {int(k): np.sort(v.date.unique()) for k, v in GLd.groupby("player_id")}
    seasons_played = fg[fg.g.fillna(0) > 0].groupby("player_id").season.apply(lambda s: np.sort(s.unique())).to_dict()
    ends, srcs = [], []
    for r in P.itertuples():
        base = getattr(r, base_col)
        c = [(base, "census")] if pd.notna(base) else []
        t0 = np.datetime64(r.il_start)
        a = app.get(int(r.mlbam))
        if use_pitcher_appearance and a is not None and (a > t0).any():
            c.append((pd.Timestamp(a[a > t0][0]), "pitcher_appearance"))
        ys = seasons_played.get(int(r.mlbam))
        if ys is not None:
            y = ys[(ys > r.il_start.year) & (ys <= 2014)]
            if len(y) and int(y[0]) in SPAN:
                c.append((SPAN[int(y[0])][0], "next_season_played_pre2015"))
        x = SUS.get(int(r.mlbam))
        if x is not None and (x > t0).any():
            c.append((pd.Timestamp(x[x > t0][0]), "restricted_or_suspended"))
        if not c:
            ends.append(pd.NaT); srcs.append("open"); continue
        e, src = min(c, key=lambda z: z[0])
        if pd.notna(base) and e >= base:
            e, src = base, "census"
        ends.append(e); srcs.append(src)
    return ends, srcs


def build(P, endcol):
    """injury_luck.py build(P, endcol, gcap=True), seasons 2012-2026; no games-played cap in 2026 (no 2026 fWAR)."""
    rows = []
    for s in range(2012, 2027):
        if s not in SPAN:
            continue
        a, b = SPAN[s]
        x = P[(P.il_start <= b) & (P[endcol].fillna(b) >= a) & P.il_start.dt.year.between(s - 1, s)].copy()
        x["start"] = x.il_start.clip(lower=a)
        x["end"] = (x[endcol].fillna(b + pd.Timedelta(days=1)) - pd.Timedelta(days=1)).clip(upper=b)
        x = x[x.end >= x.start].sort_values(["mlbam", "club_id", "start"])
        for (pid, tid), g in x.groupby(["mlbam", "club_id"]):
            cs = ce = None; site = None; ext = None; n = 0
            for st, en, si, dx, nm, il0, txn, ie, isrc in zip(g.start, g.end, g.site, g.dx, g.name, g.il_start, g.txn_id,
                                                              g[endcol], g.end_src):
                if cs is None:
                    cs, ce, site, ext, n, srcs = st, en, si, (dx, nm, il0, txn), 1, {isrc}
                elif st <= ce + pd.Timedelta(days=1):
                    ce = max(ce, en); n += 1; srcs.add(isrc)
                else:
                    rows.append((s, pid, tid, cs, ce, site, *ext, n, "|".join(sorted(srcs))))
                    cs, ce, site, ext, n, srcs = st, en, si, (dx, nm, il0, txn), 1, {isrc}
            rows.append((s, pid, tid, cs, ce, site, *ext, n, "|".join(sorted(srcs))))
    S_all = pd.DataFrame(rows, columns=["season", "mlbid", "tid", "start", "end", "site", "dx", "name", "first_il_start",
                                        "first_txn_id", "n_placements", "end_rule"])
    S_all["games_missed"] = [games_between(s, t, a, b) for s, t, a, b in zip(S_all.season, S_all.tid, S_all.start, S_all.end)]
    S_all = S_all.sort_values(["mlbid", "season", "first_il_start", "tid"]).reset_index(drop=True)
    drop = []
    for (pid, s), ix in S_all.groupby(["mlbid", "season"]).groups.items():
        if S_all.loc[ix, "tid"].nunique() < 2:
            continue
        ix = list(ix)
        for u, i in enumerate(ix):
            later = [j for j in ix[u + 1:] if S_all.at[j, "tid"] != S_all.at[i, "tid"]]
            if not later:
                continue
            cut = min(S_all.at[j, "start"] for j in later) - pd.Timedelta(days=1)
            if S_all.at[i, "end"] > cut:
                S_all.at[i, "end_rule"] += "|cross_club_overlap"
                if cut < S_all.at[i, "start"]:
                    drop.append(i)
                else:
                    S_all.at[i, "end"] = cut
    S_all = S_all.drop(index=drop).reset_index(drop=True)
    S_all["games_missed"] = [games_between(s, t, a, b) for s, t, a, b in zip(S_all.season, S_all.tid, S_all.start, S_all.end)]
    gpl = fg.groupby(["player_id", "season"]).g.max().to_dict()
    for (pid, s), ix in S_all.groupby(["mlbid", "season"]).groups.items():
        if s == 2026:
            continue
        g_ = gpl.get((pid, s), 0)
        excess = S_all.loc[ix, "games_missed"].sum() + (0 if pd.isna(g_) else g_) - (60 if s == 2020 else 162)
        if excess <= 0:
            continue
        for i in sorted(ix, key=lambda i: (S_all.at[i, "start"], S_all.at[i, "tid"]), reverse=True):
            if excess <= 0:
                break
            gm_i = int(S_all.at[i, "games_missed"]); keep = int(gm_i - min(gm_i, excess)); excess -= gm_i - keep
            d = TEAM_DATES[(s, S_all.at[i, "tid"])]
            d = d[(d >= np.datetime64(S_all.at[i, "start"])) & (d <= np.datetime64(S_all.at[i, "end"]))]
            S_all.at[i, "games_missed"] = keep
            S_all.at[i, "end"] = pd.Timestamp(d[keep - 1]) if keep > 0 else S_all.at[i, "start"]
            S_all.at[i, "end_rule"] += "|games_played_cap"
    S_all["days"] = (S_all.end - S_all.start).dt.days + 1
    war = fg.groupby(["player_id", "season"]).agg(war=("war", "sum"), g_played=("g", "max")).reset_index()
    gm = S_all.groupby(["mlbid", "season"]).games_missed.sum().rename("gm").reset_index().rename(columns={"mlbid": "player_id"})
    war = war.merge(gm, on=["player_id", "season"], how="left").fillna({"gm": 0})
    war["exposure"] = (np.where(war.season == 2020, 60, 162) - war.gm).clip(lower=1)
    Wd = {(p, s): (w, e) for p, s, w, e in zip(war.player_id, war.season, war.war, war.exposure)}
    return S_all, war, Wd


def make_rate(Wd):
    def rate(pid, s, k=K):
        num = den = 0.0
        for w, kk in zip(W, (1, 2, 3)):
            v = Wd.get((pid, s - kk))
            if v is not None:
                num += w * v[0]; den += w * v[1]
        return num / (den + k)
    return rate


def age_on(pid, s):
    b = BIRTH.get(pid)
    return np.nan if b is None or pd.isna(b) else (pd.Timestamp(f"{s}-06-30") - b).days / 365.25


def age_factor(age):
    if not np.isfinite(age):
        return 1.0
    return 1 + 0.006 * (29 - age) if age < 29 else 1 + 0.003 * (29 - age)


ROSTER = pd.read_csv(P_(ROSTER_KEY)).drop_duplicates(["season", "club_id", "mlbam"])
assert ROSTER.groupby(["season", "club_id"]).ngroups == 330, "roster file does not cover 330 club-seasons"
ROSTER_SETS = {k: set(v.mlbam) for k, v in ROSTER.groupby(["season", "club_id"])}


def club_table(S_all, Wd, variants=("K100",)):
    """Club-season table for the outcome seasons and 2026: WAR lost, realised team_proj (outcome seasons), the opening-day
    control and preseason features, carry-over split. variants: K100 (primary), K50, K200, AGE."""
    rate = make_rate(Wd)
    S = S_all[S_all.season.isin(OUTCOME + [2026])].copy()

    def r_var(p, s, v):
        if v == "AGE":
            return rate(p, s, 100) * age_factor(age_on(p, s))
        return rate(p, s, int(v[1:]))
    out = {}
    for v in variants:
        S[f"rate_{v}"] = np.clip([r_var(p, s, v) for p, s in zip(S.mlbid, S.season)], 0, None)
        S[f"wl_{v}"] = S[f"rate_{v}"] * S.games_missed
    S["rate"] = S["rate_K100"] if "rate_K100" in S else np.clip([rate(p, s) for p, s in zip(S.mlbid, S.season)], 0, None)
    S["war_lost"] = S.rate * S.games_missed
    last = {s: SPAN[s][1] for s in SPAN}
    open_set = set(zip(S_all.loc[S_all.end >= S_all.season.map(last), "mlbid"], S_all.loc[S_all.end >= S_all.season.map(last), "season"]))
    S["il_open_final_day"] = S.end == S.season.map(lambda s: SPAN[s][1])
    S["carry"] = [(p, PREV_OF[s]) in open_set for p, s in zip(S.mlbid, S.season)]
    agg = {"stints": ("mlbid", "size"), "games_missed": ("games_missed", "sum"), "war_lost": ("war_lost", "sum"), "il_days": ("days", "sum")}
    for v in variants:
        agg[f"war_lost_{v}"] = (f"wl_{v}", "sum")
    T = S.groupby(["season", "tid"]).agg(**agg).reset_index()
    T = T.merge(S[S.carry].groupby(["season", "tid"]).war_lost.sum().rename("wl_carry").reset_index(), how="left").fillna({"wl_carry": 0.0})
    T["wl_new"] = T.war_lost - T.wl_carry
    # opening-day roster: control, features, carry-over visibility V_t
    days_prev = S_all.groupby(["mlbid", "season"]).days.sum().to_dict()
    rows = []
    for (s, tid), ids in ROSTER_SETS.items():
        ids = sorted(ids)
        ages = np.array([age_on(p, s) for p in ids])
        r_ = {v: np.array([r_var(p, s, v) for p in ids]) for v in variants}
        proj = np.clip(r_["K100"] if "K100" in r_ else np.array([rate(p, s) for p in ids]), 0, None) * 162
        w = np.clip(proj, 0.01, None)
        age = np.where(np.isfinite(ages), ages, np.nanmean(ages))
        dprev = np.array([days_prev.get((p, s - 1), 0.0) for p in ids], float)
        vis = np.array([(p, PREV_OF[s]) in open_set for p in ids])
        row = {"season": s, "tid": tid, "n_roster": len(ids), "roster_age_od": float(np.average(age, weights=w)),
               "roster_il_days_prev_od": float(np.average(dprev, weights=w)), "V_open_prev": float(proj[vis].sum()),
               "n_open_prev_on_roster": int(vis.sum())}
        for v in variants:
            row["team_proj_od" + ("" if v == "K100" else f"_{v}")] = float(np.clip(r_[v], 0, None).sum() * 162)
        rows.append(row)
    T = T.merge(pd.DataFrame(rows), on=["season", "tid"], how="left")
    return S, T


# ---- Rule A (primary): census end + full R1 ------------------------------------------------------------------------
P["end_src"] = P.il_end_src
P["il_end_r1"], P["end_src"] = r1_end_dates(P)
S_all, war, Wd = build(P, "il_end_r1")
rate = make_rate(Wd)
S, TA = club_table(S_all, Wd, variants=("K100", "K50", "K200", "AGE"))
log(f"rule A built: {len(S_all)} episodes 2012-2026, {len(S)} in outcome seasons and 2026  {time.time() - T0:.0f}s")

# realised roster control and the rest of the injury_luck.py club-season table (outcome seasons only), for the gate
T = TA[TA.season.isin(OUTCOME)].copy()
st = st_full[["season", "team_id", "W", "L", "qualified", "league_id"]].rename(columns={"team_id": "tid"})
T = T.merge(st, on=["season", "tid"], how="left")
assert T.W.notna().all()
fgp = fg[fg.season.isin(OUTCOME)].copy()
fgp["tid"] = fgp.team.map(ABBR).map(ID_OF)
fgp = fgp.dropna(subset=["tid"]).drop_duplicates(["player_id", "season", "tid"])
fgp["proj_war"] = [rate(p, s) * 162 for p, s in zip(fgp.player_id, fgp.season)]
T = T.merge(fgp.groupby(["season", "tid"]).proj_war.sum().rename("team_proj").reset_index(), on=["season", "tid"], how="left")
T = T.sort_values(["tid", "season"]).reset_index(drop=True)
T["war_lost_prev"] = T.groupby("tid").war_lost.shift(1)
T["W_prev"] = T.groupby("tid").W.shift(1)
for c in ("wl_carry", "wl_new"):
    T[f"{c}_prev"] = T.groupby("tid")[c].shift(1)
T["q"] = T.qualified.astype(str).str.lower().isin(["true", "1"]).astype(int)
T["club"] = T.tid.map(NAME)

# episode attributes for P2.2 / P2.6 (injury_luck.py code)
FAM_V11 = [("UCL / Tommy John", r"tommy john|ucl|ulnar collateral"), ("Elbow (other)", r"elbow"),
           ("Lat / teres", r"lat|lats|latissimus|teres"), ("Shoulder", r"shoulder|rotator cuff|rotator|labrum|labral"),
           ("Forearm / flexor", r"forearm|flexor|pronator"), ("Oblique / core", r"oblique|intercostal|abdominal|core|ribs?|ribcage"),
           ("Hamstring", r"hamstring"), ("Back / neck", r"back|lumbar|spine|spinal|disc|discs|neck|cervical"),
           ("Knee", r"knee|acl|mcl|meniscus|patellar?|patella"), ("Hand / wrist / finger", r"hand|wrist|fingers?|thumb|hamate|metacarpal"),
           ("Foot / ankle", r"foot|ankle|toes?|achilles|plantar|heel"), ("Hip / groin", r"hip|groin|adductor|hernia|sports hernia"),
           ("Calf / quad / leg", r"calf|quad|quadriceps|leg|shin|tibia|fibula"), ("Concussion", r"concussion|head"),
           ("Illness / other", r"illness|covid|covid-19|virus|flu|vertigo|appendicitis|appendectomy|surgery|undisclosed|personal|blood|infection|anxiety|mononucleosis")]
FAM_V11_RX = [(n, re.compile(r"\b(?:" + p + r")\b")) for n, p in FAM_V11]


def family_v11(note):
    n = str(note).lower()
    for name, rx in FAM_V11_RX:
        if rx.search(n):
            return name
    return "Unstated"


S = S[S.season.isin(OUTCOME)].copy()
S["family"] = S.dx.map(family_v11)
_pa = fg[fg.role == "hitter"].groupby(["player_id", "season"]).pa.sum()
_rs = fg.groupby(["player_id", "season"]).role.agg(lambda r: frozenset(r))
RD = {k: ("pitcher" if ("pitcher" in v and _pa.get(k, 0.0) < 100) else "hitter") for k, v in _rs.items()}
gsg = GL.groupby(["player_id", "season"]).agg(g=("gamePk", "nunique"), gs=("GS", "sum"))
SPD = ((gsg.gs / gsg.g.clip(lower=1)) >= 0.5).to_dict()


def group_of(pid, s):
    role = next((RD[(pid, y)] for y in (s, s - 1, s - 2, s - 3) if (pid, y) in RD), None)
    if role is None:
        return "unknown"
    if role == "hitter":
        return "hitter"
    sp = next((SPD[(pid, y)] for y in range(s, s - 4, -1) if (pid, y) in SPD), None)
    return "pitcher, role unknown" if sp is None else ("starter" if sp else "reliever")


S["group"] = [group_of(p, s) for p, s in zip(S.mlbid, S.season)]
LG = st_full.set_index(["season", "team_id"]).league_id.to_dict()
G["hw"] = (G.home_score > G.away_score).astype(int)
res = pd.concat([pd.DataFrame({"season": G.season, "date": G.date, "tid": G.home_id, "w": G.hw, "l": 1 - G.hw}),
                 pd.DataFrame({"season": G.season, "date": G.date, "tid": G.away_id, "w": 1 - G.hw, "l": G.hw})])
GB = {}
for s in OUTCOME:
    r = res[res.season == s]
    days = pd.date_range(SPAN[s][0], SPAN[s][1])
    clubs = sorted(r.tid.unique())
    Wm = r.pivot_table(index="date", columns="tid", values="w", aggfunc="sum").reindex(days, fill_value=0).fillna(0).cumsum()
    Lm = r.pivot_table(index="date", columns="tid", values="l", aggfunc="sum").reindex(days, fill_value=0).fillna(0).cumsum()
    nspot = 5 if s <= 2021 else 6
    for lg in {LG[(s, c)] for c in clubs}:
        cl = [c for c in clubs if LG[(s, c)] == lg]
        Wl, Ll = Wm[cl].to_numpy(), Lm[cl].to_numpy()
        pct = np.where(Wl + Ll > 0, Wl / np.maximum(Wl + Ll, 1), 0.5)
        order = np.argsort(-pct, axis=1, kind="stable")
        cut = order[:, nspot - 1]
        wc, lc = Wl[np.arange(len(days)), cut], Ll[np.arange(len(days)), cut]
        gb = ((wc[:, None] - Wl) + (Ll - lc[:, None])) / 2
        for j, c in enumerate(cl):
            GB[(s, c)] = (days, gb[:, j])


def gb_before(s, tid, d):
    days, gb = GB[(s, tid)]
    i = (d - days[0]).days - 1
    return 0.0 if i < 0 else float(gb[min(i, len(gb) - 1)])


S["gb_at_start"] = [gb_before(s, t, d) for s, t, d in zip(S.season, S.tid, S.start)]
S["out_of_contention"] = S.gb_at_start >= 10
S["pre_aug1"] = S.start < pd.to_datetime(S.season.astype(str) + "-08-01")
jul1 = pd.to_datetime(S.season.astype(str) + "-07-01")
S["gm_post_jul1"] = [games_between(s, t, max(a, j), b) if (a < j and b >= j) else 0
                     for s, t, a, b, j in zip(S.season, S.tid, S.start, S.end, jul1)]
S["war_lost_c"] = np.where(S.start < jul1, S.rate * S.gm_post_jul1, 0.0)
S["opening"] = S.season.map({s: SPAN[s][0] for s in SPAN})
S["in_season_onset"] = S.first_il_start > S.opening
S["gm_remaining"] = [int((TEAM_DATES[(s, t)] >= np.datetime64(a)).sum()) for s, t, a in zip(S.season, S.tid, S.start)]
FAM_MED = S.groupby("family").games_missed.median()
S["gm_fixed"] = np.minimum(S.family.map(FAM_MED), S.gm_remaining)
S["wl_fixed"] = S.rate * S.gm_fixed


def add_col(mask, val="war_lost"):
    a = S[mask].groupby(["season", "tid"])[val].sum().rename("x").reset_index()
    return T[["season", "tid"]].merge(a, how="left").fillna({"x": 0.0})["x"].to_numpy()


T["war_lost_a"] = add_col(S.pre_aug1); T["war_lost_b"] = add_col(~S.out_of_contention); T["war_lost_c"] = add_col(S.season > 0, "war_lost_c")
for g_ in ["hitter", "starter", "reliever", "pitcher, role unknown", "unknown"]:
    T[f"war_lost_{g_}"] = add_col(S.group == g_)
T["x_f_fixed"] = add_col(S.in_season_onset & S.pre_aug1, "wl_fixed")
T["wl_in_cont"] = add_col(~S.out_of_contention); T["wl_out_cont"] = add_col(S.out_of_contention)
T["wl_od"] = add_col(~S.in_season_onset); T["wl_inseason"] = add_col(S.in_season_onset)
rs = res[res.date >= pd.to_datetime(res.season.astype(str) + "-07-01")].groupby(["season", "tid"]).agg(W_post=("w", "sum"), G_post=("w", "size"))
rp = res[res.date < pd.to_datetime(res.season.astype(str) + "-07-01")].groupby(["season", "tid"]).agg(W_pre=("w", "sum"))
T = T.merge(rs.reset_index(), on=["season", "tid"], how="left").merge(rp.reset_index(), on=["season", "tid"], how="left")
for g_ in ["hitter", "starter", "reliever"]:
    T[f"war_lost_{g_}_prev"] = T.sort_values(["tid", "season"]).groupby("tid")[f"war_lost_{g_}"].shift(1)
T = T.sort_values(["tid", "season"]).reset_index(drop=True)

# ---- gate: the primary club-season table must equal results/team_season_public.csv ---------------------------------
PUB = pd.read_csv(os.path.join(RES, "team_season_public.csv"))
chk = PUB.merge(T, on=["season", "tid"], suffixes=("_pub", ""))
assert len(chk) == len(PUB) == len(T) == 300
gate = {}
for c_mine, c_pub in [("stints", "stints"), ("games_missed", "games_missed"), ("war_lost", "war_lost"), ("war_lost_K50", "war_lost_K50"),
                      ("war_lost_K200", "war_lost_K200"), ("il_days", "il_days"), ("team_proj", "team_proj"), ("war_lost_prev", "war_lost_prev"),
                      ("W_prev", "W_prev"), ("war_lost_a", "war_lost_a"), ("war_lost_b", "war_lost_b"), ("war_lost_c", "war_lost_c"),
                      ("war_lost_hitter", "war_lost_hitter"), ("war_lost_starter", "war_lost_starter"), ("war_lost_reliever", "war_lost_reliever"),
                      ("W_post", "W_post"), ("G_post", "G_post"), ("W_pre", "W_pre")]:
    a_, b_ = chk[c_mine].to_numpy(float), chk[c_pub + "_pub"].to_numpy(float)
    nn = ~(np.isnan(a_) & np.isnan(b_))
    if (np.isnan(a_) != np.isnan(b_)).any():
        sys.exit(f"GATE FAIL: NaN pattern {c_mine}")
    gate[c_mine] = float(np.abs(a_[nn] - b_[nn]).max())
if max(gate.values()) > 1e-9:
    sys.exit(f"GATE FAIL: {gate}")
log(f"gate passed: primary club-season table equals team_season_public.csv (max abs diff {max(gate.values()):.1e})")

# ---- Rule B (P2.3): activation-only ends, R1 without the pitcher-appearance step -----------------------------------
PB = P.copy()
PB["il_end_act"] = [next_act(p, d) for p, d in zip(PB.mlbam, PB.il_start)]
PB["end_src"] = np.where(PB.il_end_act.notna(), "activation_only", "open")
PB["il_end_b"], _src = r1_end_dates(PB, base_col="il_end_act", use_pitcher_appearance=False)
PB["end_src"] = _src
SB_all, warB, WdB = build(PB, "il_end_b")
SB, TB = club_table(SB_all, WdB, variants=("K100",))
TB = TB[TB.season.isin(OUTCOME)]
T = T.merge(TB[["season", "tid", "war_lost", "team_proj_od", "games_missed", "stints"]].rename(
    columns={"war_lost": "war_lost_B", "team_proj_od": "team_proj_od_B", "games_missed": "games_missed_B", "stints": "stints_B"}),
    on=["season", "tid"], how="left")
SB = SB[SB.season.isin(OUTCOME)]
log(f"rule B built  {time.time() - T0:.0f}s")

# =====================================================================================================================
# 2. Estimators (numpy, used for point values and inside the bootstrap)
# =====================================================================================================================


def ols(y, X):
    Z = np.column_stack([np.ones(len(y)), X])
    return np.linalg.lstsq(Z, y, rcond=None)[0]


def sdum(season, levels):
    return np.column_stack([(season == s).astype(float) for s in levels[1:]]) if len(levels) > 1 else np.zeros((len(season), 0))


def wins_coef(D, cols, ctrl=("team_proj_od", "W_prev"), y="W"):
    """coefficients of cols in OLS of y on cols + ctrl + season FE (rows with W_prev)."""
    M = D.dropna(subset=["W_prev"])
    lv = sorted(M.season.unique())
    X = np.column_stack([M[list(cols) + list(ctrl)].to_numpy(float), sdum(M.season.to_numpy(), lv)])
    return ols(M[y].to_numpy(float), X)[1:1 + len(cols)]


def logit_fit(y, X):
    Z = np.column_stack([np.ones(len(y)), X]); b = np.zeros(Z.shape[1])
    for _ in range(100):
        eta = np.clip(Z @ b, -35, 35); p = 1 / (1 + np.exp(-eta))
        g = Z.T @ (y - p); H = (Z * (p * (1 - p))[:, None]).T @ Z
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return None
        b = b + step
        if np.max(np.abs(step)) < 1e-10:
            return b
    return None if np.max(np.abs(step)) > 1e-6 else b


def playoff(D, col="war_lost", ctrl="team_proj_od", at=None, pm=None):
    lv = sorted(D.season.unique())
    sd = sdum(D.season.to_numpy(), lv)
    b = logit_fit(D.q.to_numpy(float), np.column_stack([D[col], D[ctrl], sd]))
    if b is None:
        return None
    at = at if at is not None else [float(D[col].quantile(q)) for q in (.1, .5, .9)]
    pm = pm if pm is not None else float(D[ctrl].median())
    probs = [float(np.mean(1 / (1 + np.exp(-(b[0] + b[1] * v + b[2] * pm + sd @ b[3:]))))) for v in at]
    return {"or": float(np.exp(b[1])), "p": probs, "at": [float(v) for v in at], "pm": pm}


def loso(D, cols, seasons, y="war_lost", demean=False):
    M = D[D.season.isin(seasons)]
    yy = M[y].to_numpy(float).copy(); X = M[cols].to_numpy(float).copy(); ss = M.season.to_numpy()
    if demean:
        for s in seasons:
            m = ss == s
            yy[m] -= yy[m].mean(); X[m] -= X[m].mean(0)
    pred = np.empty(len(yy)); sse = sst = 0.0
    for s in seasons:
        te = ss == s; tr = ~te
        b = ols(yy[tr], X[tr]); pred[te] = b[0] + X[te] @ b[1:]
        sse += ((yy[te] - pred[te]) ** 2).sum(); sst += ((yy[te] - (0.0 if demean else yy[tr].mean())) ** 2).sum()
    return 1 - sse / sst, pd.Series(yy - pred, index=M.index)


def icc_mat(Y):
    k, n = Y.shape
    Y = Y - Y.mean(0, keepdims=True); cm = Y.mean(1)
    msb = n * ((cm - Y.mean()) ** 2).sum() / (k - 1); msw = ((Y - cm[:, None]) ** 2).sum() / ((k - 1) * (n - 1))
    return float((msb - msw) / (msb + (n - 1) * msw))


def icc1(D, col, key="club_key"):
    Y = D.pivot_table(index=key, columns="season", values=col)
    return np.nan if Y.isna().any().any() else icc_mat(Y.to_numpy(float))


def sd_within(D, col):
    return float(D.groupby("season")[col].std().mean())


def q(D, col, p):
    return float(D[col].quantile(p))


def demean_s(D, col):
    return D[col] - D.groupby("season")[col].transform("mean")


def cov_decomp(D):
    M = D.dropna(subset=["war_lost_prev"])
    wl, c, n, wp = (demean_s(M, k).to_numpy() for k in ("war_lost", "wl_carry", "wl_new", "war_lost_prev"))
    cv = lambda a, b: float(np.mean(a * b))  # noqa: E731
    tot = cv(wl, wp)
    Mn = M.dropna(subset=["wl_new_prev"])
    nn, nnp = demean_s(Mn, "wl_new").to_numpy(), demean_s(Mn, "wl_new_prev").to_numpy()
    return {"carry_share_of_cov": cv(c, wp) / tot, "slope_total": tot / cv(wp, wp), "slope_carry": cv(c, wp) / cv(wp, wp),
            "slope_new": cv(n, wp) / cv(wp, wp), "r_new_new_prev": float(np.corrcoef(nn, nnp)[0, 1]),
            "r_total": float(np.corrcoef(wl, wp)[0, 1]), "n": int(len(M))}


GROUPS = ["hitter", "starter", "reliever"]
DESIGNS = {"a_primary": (["war_lost"], None), "b_pre_aug1": (["war_lost_a"], None), "c_in_contention": (["war_lost_b"], None),
           "d_split_season": (["war_lost_c"], "c"), "e_contention_split": (["wl_in_cont", "wl_out_cont"], None),
           "f_inseason_pre_aug1_duration_fixed": (["x_f_fixed"], None), "g_opening_day_vs_in_season": (["wl_od", "wl_inseason"], None)}
RANGE_TERMS = [("a_primary", 0), ("b_pre_aug1", 0), ("c_in_contention", 0), ("d_split_season", 0), ("e_contention_split", 0),
               ("f_inseason_pre_aug1_duration_fixed", 0), ("g_opening_day_vs_in_season", 1)]


def design_coefs(D, name):
    cols, kind = DESIGNS[name]
    if kind == "c":
        return wins_coef(D, cols, ctrl=("team_proj_od", "W_prev", "W_pre", "G_post"), y="W_post")
    return wins_coef(D, cols)


def stats(D, full=False):
    """Every bootstrapped Phase 2 statistic on a club-season table D (D carries club_key)."""
    o = {}
    b = float(wins_coef(D, ["war_lost"])[0]); o["P21.b"] = b
    sd = sd_within(D, "war_lost"); o["P21.sd_war"] = sd
    o["P21.one_sd_wins"] = sd * abs(b); o["P21.p10_p90_wins"] = (q(D, "war_lost", .9) - q(D, "war_lost", .1)) * abs(b)
    pp = playoff(D)
    if pp is None:
        raise ValueError("logit")
    o["P21.or"] = pp["or"]; o["P21.p10"], o["P21.p50"], o["P21.p90"] = pp["p"]; o["P21.p10_minus_p90"] = pp["p"][0] - pp["p"][2]
    for nm, m in (("pre", D.season < 2022), ("post", D.season >= 2022)):
        pe = playoff(D[m], at=pp["at"], pm=pp["pm"])
        if pe is None:
            raise ValueError("logit era")
        o[f"P21.{nm}.or"] = pe["or"]; o[f"P21.{nm}.p10"], o[f"P21.{nm}.p50"], o[f"P21.{nm}.p90"] = pe["p"]
    if full:  # playoff curve for Figure 2 (percentiles 5..95 of war_lost)
        grid = [q(D, "war_lost", g / 100) for g in range(5, 100, 5)]
        o["curve.all"] = playoff(D, at=grid, pm=pp["pm"])["p"]
        o["curve.pre"] = playoff(D[D.season < 2022], at=grid, pm=pp["pm"])["p"]
        o["curve.post"] = playoff(D[D.season >= 2022], at=grid, pm=pp["pm"])["p"]
    for nm, cols in (("prior", ["war_lost_prev"]), ("roster", PRE_FEATS), ("all", ["war_lost_prev"] + PRE_FEATS)):
        r2, rr = loso(D, cols, SEASONS_P); o[f"P21.r2_{nm}"] = r2
        if nm == "all":
            D.loc[rr.index, "u2"] = rr
    o["P21.r2_all_demeaned"] = loso(D, ["war_lost_prev"] + PRE_FEATS, SEASONS_P, demean=True)[0]
    DP = D[D.season.isin(SEASONS_P)]
    o["P21.sd_unexp_war"] = sd_within(DP, "u2"); o["P21.sd_unexp_wins"] = o["P21.sd_unexp_war"] * abs(b)
    # P2.2
    for nm in DESIGNS:
        cf = design_coefs(D, nm)
        for j, v in enumerate(cf):
            o[f"P22.{nm}.{j}"] = float(v)
    for nm, col in (("b_pre_aug1", "war_lost_a"), ("c_in_contention", "war_lost_b")):
        pb = playoff(D, col=col)
        o[f"P22.{nm}.or"] = pb["or"] if pb else np.nan
    # P2.3 rule B
    bB = float(wins_coef(D, ["war_lost_B"], ctrl=("team_proj_od_B", "W_prev"))[0])
    sdB = sd_within(D, "war_lost_B")
    o["P23.B.b"] = bB; o["P23.B.sd_war"] = sdB; o["P23.B.one_sd_wins"] = sdB * abs(bB)
    o["P23.B.p10_p90_wins"] = (q(D, "war_lost_B", .9) - q(D, "war_lost_B", .1)) * abs(bB)
    pB = playoff(D, col="war_lost_B", ctrl="team_proj_od_B")
    o["P23.B.or"] = pB["or"] if pB else np.nan
    o["P23.B.p10"], o["P23.B.p90"] = (pB["p"][0], pB["p"][2]) if pB else (np.nan, np.nan)
    # P2.4
    for v in ("K50", "K200", "AGE"):
        bv = float(wins_coef(D, [f"war_lost_{v}"], ctrl=(f"team_proj_od_{v}", "W_prev"))[0])
        o[f"P24.{v}.b"] = bv; o[f"P24.{v}.one_sd_wins"] = sd_within(D, f"war_lost_{v}") * abs(bv)
    # P2.5
    o["P25.icc_primary"] = icc1(DP, "u2")
    _, rr = loso(D, PRE_FEATS, OUTCOME); D["ur2"] = rr
    o["P25.icc_roster300"] = icc1(D, "ur2")
    for k_, v_ in cov_decomp(D).items():
        if k_ != "n":
            o[f"P25.cov.{k_}"] = v_
    # P2.6
    tot = D.war_lost.sum()
    for g_ in GROUPS:
        r2g, rg = loso(D, [f"war_lost_{g_}_prev"] + PRE_FEATS, SEASONS_P, y=f"war_lost_{g_}")
        o[f"P26.{g_}.r2"] = r2g; D.loc[rg.index, f"ug_{g_}"] = rg
        o[f"P26.{g_}.sd_unexp_war"] = sd_within(D[D.season.isin(SEASONS_P)], f"ug_{g_}")
        o[f"P26.{g_}.share"] = float(D[f"war_lost_{g_}"].sum() / tot)
    # P2.7
    o["P27.carry_share"] = float(D.wl_carry.sum() / tot)
    M = D.dropna(subset=["war_lost_prev"])
    bv = ols(M.wl_carry.to_numpy(float), M[["V_open_prev"]].to_numpy(float))
    fit = bv[0] + bv[1] * M.V_open_prev.to_numpy(float)
    o["P27.CV.slope"] = float(bv[1]); o["P27.CV.r2"] = float(1 - ((M.wl_carry - fit) ** 2).sum() / ((M.wl_carry - M.wl_carry.mean()) ** 2).sum())
    S27 = sorted(M.season.unique())
    o["P27.CV.loso_r2"] = loso(M, ["V_open_prev"], S27, y="wl_carry")[0]
    o["P27.WV.loso_r2"] = loso(M, ["V_open_prev"], S27, y="war_lost")[0]
    o["P27.V_mean"] = float(M.V_open_prev.mean())
    gsum = gsum_u = 0.0
    for g_ in GROUPS + ["all"]:
        col = "war_lost" if g_ == "all" else f"war_lost_{g_}"
        rv = q(D, col, .9) - q(D, col, .5); o[f"P27.reserve.{g_}.war"] = rv; o[f"P27.reserve.{g_}.wins"] = rv * abs(b)
        o[f"P27.reserve.{g_}.p50"] = q(D, col, .5); o[f"P27.reserve.{g_}.p90"] = q(D, col, .9)
        ucol = "u2" if g_ == "all" else f"ug_{g_}"
        DU = D[D.season.isin(SEASONS_P)]
        ru = q(DU, ucol, .9) - q(DU, ucol, .5); o[f"P27.reserve_unforeseen.{g_}.war"] = ru; o[f"P27.reserve_unforeseen.{g_}.wins"] = ru * abs(b)
        if g_ != "all":
            gsum += rv; gsum_u += ru
    o["P27.reserve.sum_groups.war"] = gsum; o["P27.reserve.sum_groups.wins"] = gsum * abs(b)
    o["P27.reserve_unforeseen.sum_groups.war"] = gsum_u
    return o


T["club_key"] = T.tid
PT = stats(T.copy(), full=True)
log(f"point values done  {time.time() - T0:.0f}s")

# =====================================================================================================================
# 3. Bootstrap (2,000 club draws; draws fixed up front from the seed)
# =====================================================================================================================
clubs = sorted(T.tid.unique())
byclub = {c: T[T.tid == c] for c in clubs}
TAKE = np.random.default_rng(SEED).integers(0, len(clubs), (args.B, len(clubs)))
BS, fails = {}, 0
for bi in range(args.B):
    D = pd.concat([byclub[clubs[i]].assign(club_key=j) for j, i in enumerate(TAKE[bi])], ignore_index=True)
    try:
        o = stats(D, full=True)
    except Exception:  # noqa: BLE001
        fails += 1; continue
    for k_, v_ in o.items():
        BS.setdefault(k_, []).append(v_)
    if bi % 250 == 0:
        log(f"bootstrap {bi}/{args.B}  {time.time() - T0:.0f}s")


def ci(k_, j=None):
    v = np.asarray(BS[k_], float)
    v = v[:, j] if j is not None else v
    v = v[np.isfinite(v)]
    return [float(np.quantile(v, .025)), float(np.quantile(v, .975))]


def pv(k_):
    return {"est": PT[k_], "ci95": ci(k_)}


# BCa for the P2.1 wins coefficient (jackknife over clubs for the acceleration)
from scipy.stats import norm  # noqa: E402
bsb = np.asarray(BS["P21.b"]); th = PT["P21.b"]
z0 = float(norm.ppf((bsb < th).mean()))
jk = np.array([float(wins_coef(T[T.tid != c], ["war_lost"])[0]) for c in clubs]); jm = jk.mean()
acc = float(((jm - jk) ** 3).sum() / (6 * (((jm - jk) ** 2).sum()) ** 1.5))
qq = [float(norm.cdf(z0 + (z0 + z) / (1 - acc * (z0 + z)))) for z in (norm.ppf(.025), norm.ppf(.975))]
BCA = {"bca95": [float(np.quantile(bsb, qq[0])), float(np.quantile(bsb, qq[1]))], "z0": z0, "acceleration": acc}

# wild-cluster bootstrap-t (unrestricted residuals, Rademacher weights by club)
M = T.dropna(subset=["W_prev"]).reset_index(drop=True)
lv = sorted(M.season.unique())
X = np.column_stack([np.ones(len(M)), M[["war_lost", "team_proj_od", "W_prev"]].to_numpy(float), sdum(M.season.to_numpy(), lv)])
y = M.W.to_numpy(float)
XtXi = np.linalg.inv(X.T @ X); A = XtXi @ X.T; bh = A @ y; uh = y - X @ bh
n_, k_p = X.shape; gid = pd.factorize(M.tid)[0]; Gn = gid.max() + 1
Ind = np.zeros((n_, Gn)); Ind[np.arange(n_), gid] = 1.0
c_cr1 = Gn / (Gn - 1) * (n_ - 1) / (n_ - k_p)
h = X @ XtXi[:, 1]
se_h = float(np.sqrt(c_cr1 * (((h * uh) @ Ind) ** 2).sum()))
fm = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": M.tid})
assert abs(fm.params[1] - bh[1]) < 1e-9 and abs(fm.bse[1] - se_h) < 1e-9
rw = np.random.default_rng(20261004)
Wt = rw.choice([-1.0, 1.0], size=(args.wcb, Gn))[:, gid]
Ustar = Wt * uh
bstar = bh[1] + Ustar @ A[1]
Mres = np.eye(n_) - X @ A
ures = Ustar @ Mres.T
sestar = np.sqrt(c_cr1 * (((ures * h) @ Ind) ** 2).sum(1))
tstar = (bstar - bh[1]) / sestar
WCB = {"ci95": [float(bh[1] - np.quantile(tstar, .975) * se_h), float(bh[1] - np.quantile(tstar, .025) * se_h)],
       "reps": args.wcb, "weights": "Rademacher by club", "seed": 20261004, "residuals": "unrestricted"}
log(f"bootstrap done ({fails} draws dropped)  {time.time() - T0:.0f}s")

# =====================================================================================================================
# 4. P2.5 simulation-calibrated null and power with the preseason features (Phase 1b R4 code, features swapped)
# =====================================================================================================================


def loso_resid(D, cols, seasons):
    Mx = D[D.season.isin(seasons)]
    yy = Mx.war_lost.to_numpy(float); Xx = Mx[cols].to_numpy(float); ss = Mx.season.to_numpy(); r = np.empty(len(yy))
    for s in seasons:
        te = ss == s; bb = ols(yy[~te], Xx[~te]); r[te] = yy[te] - (bb[0] + Xx[te] @ bb[1:])
    return Mx.assign(u=r)


def mat(D, col):
    Y = D.pivot_table(index="tid", columns="season", values=col).to_numpy(float)
    return Y - Y.mean(0, keepdims=True)


def perm_q95(Y, rng, npm=200):
    k, n = Y.shape
    return np.quantile([icc_mat(np.column_stack([Y[rng.permutation(k), j] for j in range(n)])) for _ in range(npm)], .95)


obs_p = PT["P25.icc_primary"]; obs_a = PT["P25.icc_roster300"]
Ts = T.sort_values(["tid", "season"]).reset_index(drop=True)
Zs = np.column_stack([Ts[PRE_FEATS].to_numpy(float), pd.get_dummies(Ts.season, prefix="s", dtype=float).to_numpy()])
fit_s = Zs @ np.linalg.lstsq(Zs, Ts.war_lost.to_numpy(float), rcond=None)[0]
e_s = Ts.war_lost.to_numpy(float) - fit_s
sig = float(pd.Series(e_s).groupby(Ts.season.values).std().mean())
rng = np.random.default_rng(20261003)
idx_by_season = {s: np.where(Ts.season.to_numpy() == s)[0] for s in OUTCOME}
cl_arr = Ts.tid.to_numpy(); ucl = np.unique(cl_arr)
RHOS = [0.0, 0.03, 0.06, 0.11, 0.15, 0.20, 0.25]
SIM = {"dgp": "in-sample fit of war_lost on the preseason roster features + season effects; residuals permuted within season; "
              "club effect sqrt(rho) sigma u_club added with sqrt(1 - rho) on the residual; the club's prior-year WAR lost rebuilt "
              "from the simulated values; each panel through the exact LOSO and ICC(1) pipeline",
       "seed": 20261003, "sigma_within_season": sig, "rho": {}}
store = {}
for rho in RHOS:
    NS = args.nsim if rho == 0.0 else max(args.nsim // 2, 200)
    NP = min(NS, 200)
    Pp, Aa, rejP, rejA = [], [], 0, 0
    for it in range(NS):
        eps = np.empty(len(e_s))
        for s, ix in idx_by_season.items():
            eps[ix] = rng.permutation(e_s[ix])
        u = dict(zip(ucl, rng.standard_normal(len(ucl))))
        Dm = Ts[["season", "tid"] + PRE_FEATS].copy()
        Dm["war_lost"] = fit_s + np.sqrt(1 - rho) * eps + np.sqrt(rho) * sig * np.array([u[c] for c in cl_arr])
        Dm["war_lost_prev"] = Dm.groupby("tid").war_lost.shift(1)
        Yp = mat(loso_resid(Dm, ["war_lost_prev"] + PRE_FEATS, SEASONS_P), "u"); Ya = mat(loso_resid(Dm, PRE_FEATS, OUTCOME), "u")
        ip, ia = icc_mat(Yp), icc_mat(Ya); Pp.append(ip); Aa.append(ia)
        if it < NP:
            rejP += ip > perm_q95(Yp, rng); rejA += ia > perm_q95(Ya, rng)
    store[rho] = (np.array(Pp), np.array(Aa))
    SIM["rho"][str(rho)] = {"n_panels": NS, "primary_mean": float(np.mean(Pp)), "primary_q95": float(np.quantile(Pp, .95)),
                            "roster300_mean": float(np.mean(Aa)), "power_primary_permutation_test": rejP / NP,
                            "power_roster300_permutation_test": rejA / NP, "n_panels_with_permutation_test": NP}
    log(f"simulation rho={rho} done  {time.time() - T0:.0f}s")
P0, A0 = store[0.0]
crit_p, crit_a = float(np.quantile(P0, .95)), float(np.quantile(A0, .95))


def interp80(pw):
    grid = RHOS[1:]
    hit = next((r for r in grid if pw[str(r)] >= 0.8), None)
    if hit is None or grid.index(hit) == 0:
        return hit
    r0 = grid[grid.index(hit) - 1]
    return r0 + (0.8 - pw[str(r0)]) * (hit - r0) / (pw[str(hit)] - pw[str(r0)])


pwp = {str(r): float((store[r][0] > crit_p).mean()) for r in RHOS[1:]}
pwa = {str(r): float((store[r][1] > crit_a).mean()) for r in RHOS[1:]}
SIM["calibrated"] = {"primary_observed": obs_p, "primary_null_mean": float(P0.mean()), "primary_null_q95": crit_p,
                     "primary_null_band95": [float(np.quantile(P0, .025)), float(np.quantile(P0, .975))],
                     "primary_p_calibrated": float((1 + (P0 >= obs_p).sum()) / (1 + len(P0))),
                     "roster300_observed": obs_a, "roster300_null_q95": crit_a,
                     "roster300_p_calibrated": float((1 + (A0 >= obs_a).sum()) / (1 + len(A0))),
                     "type1_primary_permutation_test_at_nominal_05": SIM["rho"]["0.0"]["power_primary_permutation_test"],
                     "power_primary": pwp, "power_roster300": pwa,
                     "icc_at_80pct_power_primary": interp80(pwp), "icc_at_80pct_power_roster300": interp80(pwa),
                     "null_primary_hist": np.histogram(P0, bins=40)[0].tolist(),
                     "null_primary_hist_edges": np.histogram(P0, bins=40)[1].tolist()}

# =====================================================================================================================
# 5. Persistence statistics (P2.5a), with the permutation test and REML (injury_luck.py persistence())
# =====================================================================================================================
rng_perm = np.random.default_rng(SEED + 1)


def persistence(D, col, seasons):
    D = D[D.season.isin(seasons)]
    Y = D.pivot_table(index="club_key", columns="season", values=col)
    Ym = Y.to_numpy(float); kk, nn_ = Ym.shape
    obs = icc_mat(Ym)
    Yc = Ym - Ym.mean(0, keepdims=True)
    null = np.array([icc_mat(np.column_stack([Yc[rng_perm.permutation(kk), j] for j in range(nn_)])) for _ in range(2000)])
    Yd = Y - Y.mean(0)
    pairs = [(s - 1, s) for s in seasons if s - 1 in seasons]
    a_ = np.concatenate([Yd[s0].to_numpy() for s0, _ in pairs]); b_ = np.concatenate([Yd[s1].to_numpy() for _, s1 in pairs])
    odd = [s for s in seasons if s % 2 == 1]; even = [s for s in seasons if s % 2 == 0]
    r_sh = float(np.corrcoef(Yd[odd].mean(axis=1), Yd[even].mean(axis=1))[0, 1])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            md = sm.MixedLM.from_formula(f"{col} ~ C(season)", groups="club_key", data=D.reset_index(drop=True)).fit(reml=True)
            v_re = float(md.cov_re.iloc[0, 0]); icc_reml = v_re / (v_re + float(md.scale))
        except Exception:  # noqa: BLE001
            icc_reml = None
    return {"icc1": obs, "p_perm_one_sided": float((1 + (null >= obs).sum()) / 2001), "null_q95": float(np.quantile(null, .95)),
            "icc_reml": icc_reml, "yoy_r": float(np.corrcoef(a_, b_)[0, 1]), "yoy_pairs": int(len(a_)), "split_half_r": r_sh,
            "split_half_spearman_brown": (float(2 * r_sh / (1 + r_sh)) if r_sh > 0 else None),
            "sd_within_season_war": sd_within(D, col), "n_club_seasons": int(len(D)), "n_seasons": len(seasons)}


TT = T.copy()
_, rr = loso(TT, ["war_lost_prev"] + PRE_FEATS, SEASONS_P); TT.loc[rr.index, "unexpected_p2"] = rr
_, rr = loso(TT, PRE_FEATS, OUTCOME); TT["unexpected_p2_roster300"] = rr
PERS = {"primary": persistence(TT, "unexpected_p2", SEASONS_P), "roster300": persistence(TT, "unexpected_p2_roster300", OUTCOME)}
assert abs(PERS["primary"]["icc1"] - obs_p) < 1e-12
PERS["primary"]["ci95_icc1"] = ci("P25.icc_primary"); PERS["roster300"]["ci95_icc1"] = ci("P25.icc_roster300")
pcal = SIM["calibrated"]["primary_p_calibrated"]
PERS["statement"] = ("no stable club component detected" if pcal >= .05 else
                     "the unforeseen part persists within clubs under the preseason control")

# =====================================================================================================================
# 6. P2.8 2026 out-of-sample check
# =====================================================================================================================
T26 = TA[TA.season == 2026].copy()
T26 = T26.merge(T[T.season == 2025][["tid", "war_lost"]].rename(columns={"war_lost": "war_lost_prev"}), on="tid", how="left")
assert len(T26) == 30 and T26.war_lost_prev.notna().all()
TR = T[T.season.isin(SEASONS_P)]
CHK = {}
for nm, cols in (("prior", ["war_lost_prev"]), ("roster", PRE_FEATS), ("all", ["war_lost_prev"] + PRE_FEATS)):
    bb = ols(TR.war_lost.to_numpy(float), TR[cols].to_numpy(float))
    pred = bb[0] + T26[cols].to_numpy(float) @ bb[1:]
    yv = T26.war_lost.to_numpy(float)
    r2 = 1 - ((yv - pred) ** 2).sum() / ((yv - TR.war_lost.mean()) ** 2).sum()
    Xd = TR[cols].to_numpy(float) - TR.groupby("season")[cols].transform("mean").to_numpy(float)
    yd = (TR.war_lost - TR.groupby("season").war_lost.transform("mean")).to_numpy(float)
    bd = ols(yd, Xd)
    pd_ = bd[0] + (T26[cols].to_numpy(float) - T26[cols].to_numpy(float).mean(0)) @ bd[1:]
    yd26 = yv - yv.mean()
    CHK[nm] = {"oos_r2_2026": float(r2), "oos_r2_2026_season_demeaned": float(1 - ((yd26 - pd_) ** 2).sum() / (yd26 ** 2).sum())}
    if nm == "all":
        T26["expected_2026"] = pred; T26["unexpected_2026"] = yv - pred
rank = T26.sort_values("unexpected_2026", ascending=False)
CHK["n_club_seasons"] = 30
CHK["war_lost_2026_mean"] = float(T26.war_lost.mean()); CHK["war_lost_2026_sd"] = float(T26.war_lost.std())
CHK["unexpected_2026_sd"] = float(T26.unexpected_2026.std())
CHK["ranking"] = [{"rank": i + 1, "club": NAME[t], "war_lost": float(w), "expected": float(e), "unexpected": float(u)}
                  for i, (t, w, e, u) in enumerate(zip(rank.tid, rank.war_lost, rank.expected_2026, rank.unexpected_2026))]
CHK["episodes_2026"] = int((S_all.season == 2026).sum())
CHK["note"] = "models fitted once on the 240 club-seasons of P2.1 (2016-19, 2022-25) and applied to 2026; nothing refitted"

# =====================================================================================================================
# 7. Assemble
# =====================================================================================================================
b_prereg = R["E2"]["est"]
fq = sm.Logit(T.q.astype(float), sm.add_constant(pd.concat([T[["war_lost", "team_proj_od"]], pd.get_dummies(T.season, prefix="s", drop_first=True, dtype=float)], axis=1))).fit(disp=0, cov_type="cluster", cov_kwds={"groups": T.tid})
assert abs(np.exp(fq.params["war_lost"]) - PT["P21.or"]) < 1e-6
dsg = {}
for nm in DESIGNS:
    cols, kind = DESIGNS[nm]
    Mx = T.dropna(subset=["W_prev"])
    ctrl = ["team_proj_od", "W_prev"] + (["W_pre", "G_post"] if kind == "c" else [])
    yv = "W_post" if kind == "c" else "W"
    Xx = pd.concat([Mx[cols + ctrl], pd.get_dummies(Mx.season, prefix="s", drop_first=True, dtype=float)], axis=1).astype(float)
    ff = sm.OLS(Mx[yv].astype(float), sm.add_constant(Xx)).fit(cov_type="cluster", cov_kwds={"groups": Mx.tid})
    dsg[nm] = {c: {"est": float(ff.params[c]), "se": float(ff.bse[c]), "lo_cluster": float(ff.conf_int().loc[c, 0]),
                   "hi_cluster": float(ff.conf_int().loc[c, 1]), "ci95_bootstrap": ci(f"P22.{nm}.{j}")} for j, c in enumerate(cols)}
    assert abs(dsg[nm][cols[0]]["est"] - PT[f"P22.{nm}.0"]) < 1e-9
for nm in ("b_pre_aug1", "c_in_contention"):
    dsg[nm]["playoff_or"] = pv(f"P22.{nm}.or")
cands = {nm: PT[f"P22.{nm}.{j}"] for nm, j in RANGE_TERMS}
lo_k = min(cands, key=cands.get); hi_k = max(cands, key=cands.get)
dsg["range"] = {"designs": cands, "most_negative": [lo_k, cands[lo_k]], "least_negative": [hi_k, cands[hi_k]],
                "excluded": "out-of-contention term of (e) and opening-day term of (g)",
                "realised_roster_range_phase1b": [P1B["R3_reverse_causality_designs"]["range"]["most_negative"][1],
                                                  P1B["R3_reverse_causality_designs"]["range"]["least_negative"][1]]}
dsg["share_war_lost_out_of_contention"] = float(S.war_lost[S.out_of_contention].sum() / S.war_lost.sum())
dsg["share_war_lost_opening_day_placed"] = float(S.war_lost[~S.in_season_onset].sum() / S.war_lost.sum())
dsg["family_median_games"] = {k: float(v) for k, v in FAM_MED.items()}


def rule_summary(Sx, Tx, col, ctrl, pre):
    pp = PT if pre == "A" else None
    out = {"games_missed_per_episode": float(Sx.games_missed.sum() / len(Sx)), "episodes": int(len(Sx)),
           "share_episodes_open_final_day": float((Sx.end == Sx.season.map(lambda s: SPAN[s][1])).mean()),
           "share_war_lost_open_final_day": float(Sx.war_lost[Sx.end == Sx.season.map(lambda s: SPAN[s][1])].sum() / Sx.war_lost.sum()),
           "mean_war": float(Tx[col].mean()), "p10_war": q(Tx, col, .1), "p90_war": q(Tx, col, .9)}
    return out


P23 = {"A_primary": {**rule_summary(S, T, "war_lost", "team_proj_od", "A"), "sd_war": pv("P21.sd_war"), "one_sd_wins": pv("P21.one_sd_wins"),
                     "p10_p90_wins": pv("P21.p10_p90_wins"), "b": pv("P21.b"), "or": pv("P21.or"), "p10": pv("P21.p10"), "p90": pv("P21.p90")},
       "B_activation_only": {**rule_summary(SB, T, "war_lost_B", "team_proj_od_B", "B"), "sd_war": pv("P23.B.sd_war"),
                             "one_sd_wins": pv("P23.B.one_sd_wins"), "p10_p90_wins": pv("P23.B.p10_p90_wins"), "b": pv("P23.B.b"),
                             "or": pv("P23.B.or"), "p10": pv("P23.B.p10"), "p90": pv("P23.B.p90"),
                             "placement_end_sources": {k: int(v) for k, v in pd.Series(_src).value_counts().items()}},
       "note": "P(playoffs) under each rule at that rule's own p10 and p90 of war_lost and its own median team_proj_od"}
P24 = {"K100": {"mean_war": float(T.war_lost.mean()), "sd_war": PT["P21.sd_war"], "b": pv("P21.b"), "one_sd_wins": pv("P21.one_sd_wins")}}
for v in ("K50", "K200", "AGE"):
    P24[v] = {"mean_war": float(T[f"war_lost_{v}"].mean()), "sd_war": sd_within(T, f"war_lost_{v}"), "b": pv(f"P24.{v}.b"),
              "one_sd_wins": pv(f"P24.{v}.one_sd_wins")}
P24["age_factor"] = "rate x [1 + 0.006 (29 - age)] below 29, x [1 + 0.003 (29 - age)] from 29; age on 30 June; factor 1 if birth date missing"

fam = S.groupby("family").agg(episodes=("mlbid", "size"), war_lost=("war_lost", "sum"))
fam["share_war_lost"] = fam.war_lost / fam.war_lost.sum(); fam["war_per_episode"] = fam.war_lost / fam.episodes
fam["carry_share"] = S[S.carry].groupby("family").war_lost.sum().reindex(fam.index).fillna(0) / fam.war_lost
fam["open_final_day_share"] = S[S.il_open_final_day].groupby("family").war_lost.sum().reindex(fam.index).fillna(0) / fam.war_lost
fam = fam.sort_values("war_lost", ascending=False)
grp = {}
for g_ in GROUPS:
    Sg = S[S.group == g_]
    grp[g_] = {"mean_war_lost_per_club_season": float(T[f"war_lost_{g_}"].mean()), "share": pv(f"P26.{g_}.share"),
               "carry_share": float(Sg.war_lost[Sg.carry].sum() / Sg.war_lost.sum()),
               "open_final_day_share": float(Sg.war_lost[Sg.il_open_final_day].sum() / Sg.war_lost.sum()),
               "oos_r2": pv(f"P26.{g_}.r2"), "sd_unexpected_war": pv(f"P26.{g_}.sd_unexp_war"), "episodes": int(len(Sg))}
season_split = T.groupby("season").agg(war_lost=("war_lost", "sum"), carry=("wl_carry", "sum"))
P26 = {"families": fam.drop(columns=["war_lost"]).reset_index().to_dict(orient="records"), "groups": grp,
       "concentration_carried": {k: R["E7"][k] for k in ("top1_share_mean", "top3_share_mean", "gini_club_seasons")},
       "carry_share_by_season": {int(s): float(r.carry / r.war_lost) for s, r in season_split.iterrows()}}

P21 = {"control": "opening-day 40-man roster (Stats API rosterType=40Man, eve of each club's first scheduled game; includes the 60-day IL)",
       "roster_rows": int(len(ROSTER)), "roster_club_seasons": int(ROSTER.groupby(["season", "club_id"]).ngroups),
       "roster_size_mean": float(TA.n_roster.mean()),
       "corr_team_proj_od_vs_realised": float(T[["team_proj_od", "team_proj"]].corr().iloc[0, 1]),
       "corr_team_proj_od_vs_realised_within_season": float(demean_s(T, "team_proj_od").corr(demean_s(T, "team_proj"))),
       "team_proj_od_median": float(T.team_proj_od.median()),
       "wins": {"est": PT["P21.b"], "se_cluster": se_h, "lo_cluster": float(fm.conf_int()[1][0]), "hi_cluster": float(fm.conf_int()[1][1]),
                "n": int(len(M)), "r2": float(fm.rsquared), "ci95_bootstrap": ci("P21.b"), "bca95": BCA["bca95"], "bca": BCA,
                "wild_cluster_t": WCB},
       "conversion_abs": abs(PT["P21.b"]),
       "one_sd_wins": {"est": PT["P21.one_sd_wins"], "ci95_joint": ci("P21.one_sd_wins")},
       "p10_p90_wins": {"est": PT["P21.p10_p90_wins"], "ci95_joint": ci("P21.p10_p90_wins")},
       "one_sd_wins_prereg_conversion": R["E1"]["one_sd_wins"], "p10_p90_wins_prereg_conversion": R["E1"]["p10_to_p90_wins"],
       "sd_war_within_season": PT["P21.sd_war"],
       "playoffs": {"or": PT["P21.or"], "or_ci_cluster": [float(np.exp(fq.conf_int().loc["war_lost", 0])), float(np.exp(fq.conf_int().loc["war_lost", 1]))],
                    "or_ci95_bootstrap": ci("P21.or"), "p_at_p10_p50_p90": [PT["P21.p10"], PT["P21.p50"], PT["P21.p90"]],
                    "ci95_p": [ci("P21.p10"), ci("P21.p50"), ci("P21.p90")], "p10_minus_p90": pv("P21.p10_minus_p90"),
                    "war_lost_at": [R["E1"]["p10"], R["E1"]["p50"], R["E1"]["p90"]],
                    "era": {nm: {"or": pv(f"P21.{nm}.or"), "p_at_p10_p50_p90": [PT[f"P21.{nm}.p{x}"] for x in (10, 50, 90)],
                                 "ci95_p": [ci(f"P21.{nm}.p{x}") for x in (10, 50, 90)], "n": int((T.season < 2022).sum() if nm == "pre" else (T.season >= 2022).sum()),
                                 "seasons": "2015-2021 (10-club format)" if nm == "pre" else "2022-2025 (12-club format)"} for nm in ("pre", "post")}},
       "foreseeability": {nm: {"oos_r2": PT[f"P21.r2_{nm}"], "ci95": ci(f"P21.r2_{nm}")} for nm in ("prior", "roster", "all")},
       "beside": {"prereg_realised_roster": {"wins": R["E2"]["est"], "wins_ci": [R["E2"]["lo"], R["E2"]["hi"]], "or": R["E3"]["all"]["or_per_war_lost"],
                                             "p": R["E3"]["all"]["p_at_p10_p50_p90"], "oos_r2": {k: R["E4"][k]["oos_r2"] for k in ("prior_year_only", "roster_only", "all")},
                                             "sd_unexpected_wins": R["E5"]["sd_unexpected_oos_wins"], "one_sd_wins": R["E1"]["one_sd_wins"]},
                  "phase1b_organisation_roster": {"wins": P1B["R2_preseason_control"]["wins_per_war_lost"]["preseason_control_team_proj_pre"]["est"],
                                                  "or": P1B["R2_preseason_control"]["playoff_or"]["preseason_control_team_proj_pre"]["or_per_war_lost"]}}}
P21["foreseeability"]["all"]["oos_r2_season_demeaned"] = PT["P21.r2_all_demeaned"]
P21["foreseeability"]["all"]["ci95_season_demeaned"] = ci("P21.r2_all_demeaned")
P21["unexpected"] = {"sd_war": pv("P21.sd_unexp_war"), "sd_wins": pv("P21.sd_unexp_wins"),
                     "share_of_variance": float(PT["P21.sd_unexp_war"] ** 2 / sd_within(T[T.season.isin(SEASONS_P)], "war_lost") ** 2)}
P21["figure_curve"] = {"percentiles": list(range(5, 100, 5)), "all": PT["curve.all"], "pre": PT["curve.pre"], "post": PT["curve.post"],
                       "all_lo": [ci("curve.all", j)[0] for j in range(19)], "all_hi": [ci("curve.all", j)[1] for j in range(19)],
                       "pre_lo": [ci("curve.pre", j)[0] for j in range(19)], "pre_hi": [ci("curve.pre", j)[1] for j in range(19)],
                       "post_lo": [ci("curve.post", j)[0] for j in range(19)], "post_hi": [ci("curve.post", j)[1] for j in range(19)]}

P25 = {"primary": PERS["primary"], "roster300": PERS["roster300"], "statement": PERS["statement"], "simulation": SIM,
       "carry_over_decomposition": {**{k_: {"est": PT[f"P25.cov.{k_}"], "ci95": ci(f"P25.cov.{k_}")} for k_ in
                                          ("carry_share_of_cov", "slope_total", "slope_carry", "slope_new", "r_new_new_prev", "r_total")},
                                    "n": cov_decomp(T)["n"]},
       "carry_share_of_war_lost": pv("P27.carry_share")}
P27 = {"a_carry_over": {"carry_share": pv("P27.carry_share"), "V_mean_war": pv("P27.V_mean"), "C_on_V_slope": pv("P27.CV.slope"),
                        "C_on_V_r2": pv("P27.CV.r2"), "C_on_V_loso_r2": pv("P27.CV.loso_r2"), "WL_on_V_loso_r2": pv("P27.WV.loso_r2"),
                        "n_open_prev_on_roster_mean": float(T.n_open_prev_on_roster[T.season > 2015].mean())},
       "b_depth": {g_: {"p50_war": PT[f"P27.reserve.{g_}.p50"], "p90_war": PT[f"P27.reserve.{g_}.p90"],
                        "reserve_war": pv(f"P27.reserve.{g_}.war"), "reserve_wins": pv(f"P27.reserve.{g_}.wins"),
                        "reserve_unforeseen_war": pv(f"P27.reserve_unforeseen.{g_}.war"), "reserve_unforeseen_wins": pv(f"P27.reserve_unforeseen.{g_}.wins")}
                   for g_ in GROUPS + ["all"]},
       "c_workload": None}
P27["b_depth"]["sum_groups"] = {"reserve_war": pv("P27.reserve.sum_groups.war"), "reserve_wins": pv("P27.reserve.sum_groups.wins"),
                                "reserve_unforeseen_war": pv("P27.reserve_unforeseen.sum_groups.war")}
try:
    PS = json.load(open(P_(COMPANION_KEY)))
    cv_ = PS["D"]["C3_cum_ext_days_per_30"]
    P27["c_workload"] = {"hr": cv_["hr"], "lo": cv_["lo"], "hi": cv_["hi"], "per_days": 30, "endpoint_season": 2025,
                         "source": COMPANION_KEY + " D.C3_cum_ext_days_per_30", "source_sha16": sha16(P_(COMPANION_KEY)),
                         "status": "companion work, unpublished; cited, not recomputed"}
except (FileNotFoundError, KeyError, TypeError):
    P27["c_workload"] = {"status": "companion value not available in this checkout (unpublished companion work); cited in the paper"}

OUT = {"meta": {"addendum": {"file": ADDENDUM[0], "sha16": ADDENDUM[1]}, "prereg": R["meta"]["prereg"], "inputs_sha16": hashes,
                "seed": SEED, "B": args.B, "draws_dropped": fails, "nsim_null": args.nsim, "episode_rule": "r1",
                "outcome_seasons": OUTCOME, "seasons_foreseeability": SEASONS_P, "gate_max_abs_diff": max(gate.values()),
                "n_club_seasons": int(len(T)), "n_episodes_outcome_seasons": int(len(S)),
                "label": "Phase 2, declared in the sealed addendum before computation; estimation with intervals"},
       "P2_1_preseason_control": P21, "P2_2_reverse_causality": dsg, "P2_3_duration_rule": P23, "P2_4_projection": P24,
       "P2_5_persistence": P25, "P2_6_families_slots": P26, "P2_7_levers": P27, "P2_8_check_2026": CHK}
OUT["meta"]["runtime_s"] = round(time.time() - T0, 1)
json.dump(OUT, open(os.path.join(RES, "phase2_results.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
keep = ["season", "tid", "club", "stints", "games_missed", "war_lost", "W", "L", "q", "W_prev", "team_proj", "team_proj_od", "roster_age_od",
        "roster_il_days_prev_od", "n_roster", "war_lost_prev", "wl_carry", "wl_new", "V_open_prev", "war_lost_B", "team_proj_od_B",
        "war_lost_K50", "war_lost_K200", "war_lost_AGE", "team_proj_od_K50", "team_proj_od_K200", "team_proj_od_AGE",
        "war_lost_hitter", "war_lost_starter", "war_lost_reliever"]
TT[keep + ["unexpected_p2", "unexpected_p2_roster300"]].to_csv(os.path.join(RES, "team_season_phase2.csv"), index=False)
T26.assign(club=T26.tid.map(NAME))[["season", "tid", "club", "stints", "war_lost", "war_lost_prev", "team_proj_od", "roster_age_od",
                                    "roster_il_days_prev_od", "expected_2026", "unexpected_2026"]].to_csv(os.path.join(RES, "team_season_2026_phase2.csv"), index=False)
log(json.dumps({k: OUT["P2_1_preseason_control"][k] for k in ("wins", "one_sd_wins", "p10_p90_wins")}, indent=1, default=str)[:2500])
log("P2.5 statement:", P25["statement"], "| calibrated P", round(pcal, 3), "| ICC at 80% power", SIM["calibrated"]["icc_at_80pct_power_primary"])
log(f"done in {time.time() - T0:.0f}s")
