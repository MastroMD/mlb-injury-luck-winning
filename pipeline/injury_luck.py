"""
injury_luck.py — injury luck in MLB on public data (preregistration sealed 3fd792e537b6834b).

One script: rebuilds the F1 episodes and team-season table with framing_f1.py's own code (and stops unless it
equals the sealed f1_team_season.csv within 1e-9), then computes E1-E13 and writes
  results/injury_luck_results.json, results/team_season_public.csv, results/stints_public_2015_2025.csv

Usage (from the repository root):
  python3 pipeline/injury_luck.py [--out <folder>] [--B 2000] [--prereg <preregistration .md>] [--episode-rule r1|sealed]

Inputs resolve through pipeline/paths.py: the census ships in data_public/; everything else goes in inputs/ (or
$INJURY_LUCK_INPUTS). Public-repository copy of the study script: identical estimation code; paths made relative;
the one sensitivity that reads a non-public source (E2 disattenuation) is not included, and the preregistration
hash is checked only when --prereg points at the file.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

import warnings
# log hygiene (2026-10-02): warnings print the script base name only, never an absolute path
warnings.formatwarning = lambda msg, cat, fname, lineno, line=None: f"{cat.__name__}: {msg} [{os.path.basename(str(fname))}:{lineno}]\n"
import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ap.add_argument("--B", type=int, default=2000)
ap.add_argument("--prereg", default=None, help="path to PREREGISTRATION_INJURY_LUCK_2026-09-30.md (hash-checked if given)")
ap.add_argument("--episode-rule", choices=["sealed", "r1"], default="r1",
                help="r1 (default): the Phase 1b episode-end repair (DEVIATIONS.md #10); sealed: the build as sealed (F1)")
ap.add_argument("--keep-covid-era-blanks", action="store_true", help="post hoc sensitivity only: keep the COVID-era blank placements")
ap.add_argument("--dump-dir", default=None, help="write the player-season exposure table (contains fWAR: never publish) here")
args = ap.parse_args()
OUTDIR = args.out
RULE = args.episode_rule
RES = os.path.join(OUTDIR, "results")
os.makedirs(RES, exist_ok=True)
T0 = time.time()

PREREG = ("PREREGISTRATION_INJURY_LUCK_2026-09-30.md", "3fd792e537b6834b")
PINS = {
    "Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv": "e5ed2129cf8218ec",
    "Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_team_season.csv": None,  # compared, not pinned
    "Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_results.json": None,
    "_staging_tmp/fangraphs_war_2010_2025.csv": "cad855bb7fd170dc",
    "Postseason_Injury_Risk/data/games_flat.csv": "ad002536e1d8a01b",
    "Postseason_Injury_Risk/data/standings.csv": "911f807ec5f69104",
    "Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv": "08345a5d95486529",
    "Postseason_Injury_Risk/data/people.csv": "b34f61471c31711d",
    "Sweeper_Injury_Risk/data/txns_live.jsonl": "f65ea265e77b5735",  # R1 (restricted list / suspension ends)
}
SEED, B = 20260930, args.B
OUTCOME = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
W = (5, 4, 3)
K = 100
WPW_F1 = None  # set from f1_results.json


def sha16(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()[:16]


def P_(rel):
    return paths.resolve(rel)


bad = []
hashes = {}
for rel, pin in PINS.items():
    if not os.path.exists(P_(rel)):
        bad.append(f"missing {rel}"); continue
    hashes[rel] = sha16(P_(rel))
    if pin and hashes[rel] != pin:
        bad.append(f"{rel} {hashes[rel]} != {pin}")
if args.prereg is not None and sha16(args.prereg) != PREREG[1]:
    bad.append("preregistration hash")
if bad:
    sys.exit(f"PIN FAIL: {bad}")
F1R = json.load(open(P_("Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_results.json")))
WPW_F1 = -F1R["wins_per_war_lost"]["est"]

# ====================================================================================================
# 1. F1 episodes and team-season table: framing_f1.py code, verbatim where it builds the numbers,
#    extended only to carry dx / first placement start / il_end (no effect on the F1 columns).
# ====================================================================================================
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
P = (PL.copy() if args.keep_covid_era_blanks else PL[~PL.covid_era_blank].copy())
P["club_id"] = P.club_id.astype(int)
fg = pd.read_csv(P_("_staging_tmp/fangraphs_war_2010_2025.csv")).rename(columns={"mlbamid": "player_id"})
fg = fg.dropna(subset=["player_id"]); fg["player_id"] = fg.player_id.astype(int)
st_full = pd.read_csv(P_("Postseason_Injury_Risk/data/standings.csv"))
ppl = pd.read_csv(P_("Postseason_Injury_Risk/data/people.csv"), usecols=["mlbam", "birth_date"])
ppl["birth_date"] = pd.to_datetime(ppl.birth_date, errors="coerce")
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


# ---- R1 episode-end repair (Phase 1b, DEVIATIONS.md #10; a data-defect repair made after output had been seen) --------
# An IL placement may not run through a period in which the player appears in MLB games, nor through time on the
# restricted list or under suspension. il_end becomes the earliest of: the census il_end; the player's first
# regular-season MLB pitching appearance after il_start (Stats API pitcher game logs, 2010-2026); the opening day of
# the first season after il_start's year, up to 2014, in which the player has FanGraphs games (seasons before public
# Statcast appearance dates, which the census already uses from 2015); the first feed transaction placing him on the
# restricted list, suspending him or declaring him ineligible. Episodes are then built exactly as before. Then an
# episode at one club ends the day before the same player's later-placed episode at another club begins (no games
# missed twice for two clubs; an episode wholly covered is dropped). Last, games
# missed are trimmed from the end of a player-season's latest episodes so that games missed + FanGraphs games played
# <= team games (162; 60 in 2020): the latest return consistent with observed playing time.
SUSP_RX = re.compile(r"placed .* on the restricted list|\bsuspended\b|declared ineligible", re.I)


def r1_end_dates(P):
    GLd = GL.assign(date=pd.to_datetime(GL.date))
    app = {int(k): np.sort(v.date.unique()) for k, v in GLd.groupby("player_id")}
    seasons_played = fg[fg.g.fillna(0) > 0].groupby("player_id").season.apply(lambda s: np.sort(s.unique())).to_dict()
    sus = {}
    with open(P_("Sweeper_Injury_Risk/data/txns_live.jsonl")) as fh:
        for line in fh:
            t = json.loads(line); d = t.get("description") or ""; pid = (t.get("person") or {}).get("id")
            if pid and SUSP_RX.search(d):
                sus.setdefault(int(pid), []).append(np.datetime64(pd.Timestamp(t.get("effectiveDate") or t.get("date"))))
    sus = {k: np.sort(np.array(v, dtype="datetime64[ns]")) for k, v in sus.items()}
    ends, srcs = [], []
    for r in P.itertuples():
        c = [(r.il_end, "census")] if pd.notna(r.il_end) else []
        t0 = np.datetime64(r.il_start)
        a = app.get(int(r.mlbam))
        if a is not None and (a > t0).any():
            c.append((pd.Timestamp(a[a > t0][0]), "pitcher_appearance"))
        ys = seasons_played.get(int(r.mlbam))
        if ys is not None:
            y = ys[(ys > r.il_start.year) & (ys <= 2014)]
            if len(y) and int(y[0]) in SPAN:
                c.append((SPAN[int(y[0])][0], "next_season_played_pre2015"))
        x = sus.get(int(r.mlbam))
        if x is not None and (x > t0).any():
            c.append((pd.Timestamp(x[x > t0][0]), "restricted_or_suspended"))
        if not c:
            ends.append(pd.NaT); srcs.append("open"); continue
        e, src = min(c, key=lambda z: z[0])
        if pd.notna(r.il_end) and e >= r.il_end:
            e, src = r.il_end, "census"
        ends.append(e); srcs.append(src)
    return ends, srcs


def build(P, endcol, gcap):
    """Episodes, Marcel projection and the club-season table (framing_f1.py code; endcol / gcap are the R1 hooks)."""
    rows = []
    for s in range(2012, 2026):
        if s not in SPAN:
            continue
        a, b = SPAN[s]
        x = P[(P.il_start <= b) & (P[endcol].fillna(b) >= a) & P.il_start.dt.year.between(s - 1, s)].copy()
        x["start"] = x.il_start.clip(lower=a)
        x["end"] = (x[endcol].fillna(b + pd.Timedelta(days=1)) - pd.Timedelta(days=1)).clip(upper=b)  # [start, end)
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
    n_xclub = 0
    if gcap:
        # cross-club overlap: a player's episode at one club ends the day before his later-placed episode at
        # another club starts (he cannot miss the same games for two clubs); fully covered episodes are dropped
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
                    n_xclub += 1
                    S_all.at[i, "end_rule"] += "|cross_club_overlap"
                    if cut < S_all.at[i, "start"]:
                        drop.append(i)
                    else:
                        S_all.at[i, "end"] = cut
        S_all = S_all.drop(index=drop).reset_index(drop=True)
        S_all["games_missed"] = [games_between(s, t, a, b) for s, t, a, b in zip(S_all.season, S_all.tid, S_all.start, S_all.end)]
    S_all["games_missed_before_gcap"] = S_all.games_missed
    n_trim = 0
    if gcap:
        gpl = fg.groupby(["player_id", "season"]).g.max().to_dict()
        for (pid, s), ix in S_all.groupby(["mlbid", "season"]).groups.items():
            g_ = gpl.get((pid, s), 0)
            excess = S_all.loc[ix, "games_missed"].sum() + (0 if pd.isna(g_) else g_) - (60 if s == 2020 else 162)
            if excess <= 0:
                continue
            n_trim += 1
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

    def rate(pid, s, k=K):
        num = den = 0.0
        for w, kk in zip(W, (1, 2, 3)):
            v = Wd.get((pid, s - kk))
            if v is not None:
                num += w * v[0]; den += w * v[1]
        return num / (den + k)

    S = S_all[S_all.season.isin(OUTCOME)].copy()
    S["rate"] = np.clip([rate(p, s) for p, s in zip(S.mlbid, S.season)], 0, None)
    S["war_lost"] = S.rate * S.games_missed
    for k in (50, 200):
        S[f"war_lost_K{k}"] = np.clip([rate(p, s, k) for p, s in zip(S.mlbid, S.season)], 0, None) * S.games_missed
    T = S.groupby(["season", "tid"]).agg(stints=("mlbid", "size"), games_missed=("games_missed", "sum"),
                                         war_lost=("war_lost", "sum"), war_lost_K50=("war_lost_K50", "sum"),
                                         war_lost_K200=("war_lost_K200", "sum"), il_days=("days", "sum")).reset_index()
    st = st_full[["season", "team_id", "W", "L", "qualified", "league_id"]].rename(columns={"team_id": "tid"})
    T = T.merge(st, on=["season", "tid"], how="left")
    assert T.W.notna().all()
    fgp = fg[fg.season.isin(OUTCOME)].copy()
    fgp["tid"] = fgp.team.map(ABBR).map(ID_OF)
    fgp = fgp.dropna(subset=["tid"]).drop_duplicates(["player_id", "season", "tid"])
    fgp["proj_war"] = [rate(p, s) * 162 for p, s in zip(fgp.player_id, fgp.season)]
    rost = fgp.groupby(["season", "tid"]).proj_war.sum().rename("team_proj").reset_index()
    T = T.merge(rost, on=["season", "tid"], how="left")
    T = T.sort_values(["tid", "season"]).reset_index(drop=True)
    T["war_lost_prev"] = T.groupby("tid").war_lost.shift(1)
    T["W_prev"] = T.groupby("tid").W.shift(1)
    # preseason features: roster age, roster prior-season IL days (public episodes, S-1 incl. 2014 / 2020)
    fgp = fgp.merge(ppl.rename(columns={"mlbam": "player_id"}), on="player_id", how="left")
    fgp["age"] = (pd.to_datetime(fgp.season.astype(str) + "-06-30") - fgp.birth_date).dt.days / 365.25
    prior = S_all.groupby(["mlbid", "season"]).days.sum().rename("il_days_prev").reset_index().rename(columns={"mlbid": "player_id"})
    prior["season"] += 1
    fgp = fgp.merge(prior, on=["player_id", "season"], how="left").fillna({"il_days_prev": 0.0})

    def roster_feats(g):
        w = g.proj_war.clip(lower=0.01)
        age = g.age.fillna(g.age.mean())
        return pd.Series({"roster_age_w": float(np.average(age, weights=w)),
                          "roster_il_days_prev_w": float(np.average(g.il_days_prev, weights=w)),
                          "roster_age_missing": int(g.age.isna().sum())})

    RF = fgp.groupby(["season", "tid"])[["proj_war", "age", "il_days_prev"]].apply(roster_feats).reset_index()
    T = T.merge(RF, on=["season", "tid"], how="left")
    T["q"] = T.qualified.astype(str).str.lower().isin(["true", "1"]).astype(int)
    T["club"] = T.tid.map(NAME)
    return dict(S_all=S_all, S=S, T=T, war=war, rate=rate, fgp=fgp, n_player_seasons_trimmed=n_trim, n_cross_club_overlaps=n_xclub)


P["end_src"] = P.il_end_src
B0 = build(P[~P.covid_era_blank].copy(), "il_end", gcap=False)   # the sealed build (F1 code), gated against f1_team_season.csv below
T = B0["T"]
# ---- F1 reproduction gate
F1T = pd.read_csv(P_("Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_team_season.csv"))
mine = T[["season", "tid", "stints", "games_missed", "war_lost", "W", "L", "team_proj", "war_lost_prev", "W_prev"]]
chk = F1T.merge(mine, on=["season", "tid"], suffixes=("_f1", ""))
if len(chk) != len(F1T) or len(F1T) != len(T):
    sys.exit("F1 GATE FAIL: row count")
maxdiff = 0.0
for c in ["stints", "games_missed", "war_lost", "W", "L", "team_proj", "war_lost_prev", "W_prev"]:
    a, b_ = chk[c + "_f1"].to_numpy(float), chk[c].to_numpy(float)
    both_nan = np.isnan(a) & np.isnan(b_)
    if (np.isnan(a) != np.isnan(b_)).any():
        sys.exit(f"F1 GATE FAIL: NaN pattern {c}")
    d = np.abs(a[~both_nan] - b_[~both_nan]).max() if (~both_nan).any() else 0.0
    maxdiff = max(maxdiff, d)
if maxdiff > 1e-9:
    sys.exit(f"F1 GATE FAIL: max abs diff {maxdiff}")
print(f"F1 gate passed: 300 club-seasons, max abs diff {maxdiff:.2e}")
T_SEALED = T.copy()
if RULE == "r1":
    P["il_end_r1"], P["end_src"] = r1_end_dates(P)
    B1 = build(P, "il_end_r1", gcap=True)
    BLD = B1
else:
    BLD = build(P, "il_end", gcap=False) if args.keep_covid_era_blanks else B0
S_all, S, T, war, rate, fgp = (BLD[k] for k in ("S_all", "S", "T", "war", "rate", "fgp"))
if args.dump_dir:
    os.makedirs(args.dump_dir, exist_ok=True)
    war.to_csv(os.path.join(args.dump_dir, "player_season_exposure.csv"), index=False)
    S_all.to_csv(os.path.join(args.dump_dir, "episodes_all_2012_2025.csv"), index=False)

# ====================================================================================================
# 2. Episode attributes: family v1.1, group, IL open on the final regular-season day, contention, timing
# ====================================================================================================
# FAM_V11 copied verbatim from IL_Team_Burden/pipeline/club_report.py (sha16 b9eee430509285ab)
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


CROSSWALK = {"ucl_graft": {"UCL / Tommy John"}, "elbow_other": {"Elbow (other)"}, "lat_teres": {"Lat / teres"},
             "shoulder": {"Shoulder"}, "forearm_flexor": {"Forearm / flexor"}, "core_oblique": {"Oblique / core"},
             "back": {"Back / neck"}, "knee": {"Knee"}, "hand_wrist_finger": {"Hand / wrist / finger"},
             "ankle_foot": {"Foot / ankle"}, "hip_groin": {"Hip / groin"},
             "hamstring_quad": {"Hamstring", "Calf / quad / leg"}, "calf_achilles": {"Calf / quad / leg", "Foot / ankle"},
             "illness_other": {"Illness / other", "Concussion"}, "unspecified": {"Unstated"}}
S["family"] = S.dx.map(family_v11)
S["il_open_final_day"] = S.end == S.season.map(lambda s: SPAN[s][1])

# group (E9): FanGraphs role, Stats API GS/G
# DEVIATIONS.md #1: the export carries a hitter row for every pitcher, so "both roles -> hitter" (prereg) would
# make every pitcher a hitter. Rule used: pitcher row present and hitter PA < 100 in that season -> pitcher.
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

# contention proxy (E12b): games behind the last playoff spot in the league, through the day before start
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
    i = (d - days[0]).days - 1  # record through the day before d
    return 0.0 if i < 0 else float(gb[min(i, len(gb) - 1)])


S["gb_at_start"] = [gb_before(s, t, d) for s, t, d in zip(S.season, S.tid, S.start)]
S["out_of_contention"] = S.gb_at_start >= 10
S["month"] = S.start.dt.month.clip(4, 9)
S["pre_aug1"] = S.start < pd.to_datetime(S.season.astype(str) + "-08-01")
# (c) split season: WAR lost in games on/after 1 July, episodes starting before 1 July
jul1 = pd.to_datetime(S.season.astype(str) + "-07-01")
S["gm_post_jul1"] = [games_between(s, t, max(a, j), b) if (a < j and b >= j) else 0
                     for s, t, a, b, j in zip(S.season, S.tid, S.start, S.end, jul1)]
S["war_lost_c"] = np.where(S.start < jul1, S.rate * S.gm_post_jul1, 0.0)

agg = S.groupby(["season", "tid"]).apply(lambda g: pd.Series({
    "war_lost_a": g.war_lost[g.pre_aug1].sum(), "war_lost_b": g.war_lost[~g.out_of_contention].sum(),
    "war_lost_c": g.war_lost_c.sum(),
    **{f"war_lost_{k}": g.war_lost[g.group == k].sum() for k in ["hitter", "starter", "reliever", "pitcher, role unknown", "unknown"]}}),
    include_groups=False).reset_index()
T = T.merge(agg, on=["season", "tid"], how="left")
rs = res[res.date >= pd.to_datetime(res.season.astype(str) + "-07-01")].groupby(["season", "tid"]).agg(W_post=("w", "sum"), G_post=("w", "size"))
rp = res[res.date < pd.to_datetime(res.season.astype(str) + "-07-01")].groupby(["season", "tid"]).agg(W_pre=("w", "sum"))
T = T.merge(rs.reset_index(), on=["season", "tid"], how="left").merge(rp.reset_index(), on=["season", "tid"], how="left")
T = T.sort_values(["tid", "season"]).reset_index(drop=True)

# ====================================================================================================
# 3. Estimators (numpy; used for point estimates and inside the bootstrap)
# ====================================================================================================
SEASONS_P = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
FEATS = {"prior_year_only": ["war_lost_prev"], "roster_only": ["team_proj", "roster_age_w", "roster_il_days_prev_w"],
         "all": ["war_lost_prev", "team_proj", "roster_age_w", "roster_il_days_prev_w"]}


def ols(y, X):
    Z = np.column_stack([np.ones(len(y)), X])
    return np.linalg.lstsq(Z, y, rcond=None)[0]


def season_dummies(season, levels):
    return np.column_stack([(season == s).astype(float) for s in levels[1:]]) if len(levels) > 1 else np.zeros((len(season), 0))


def dist(D, col="war_lost"):
    return dict(mean=float(D[col].mean()), sd_within_season=float(D.groupby("season")[col].std().mean()),
                p10=float(D[col].quantile(.1)), p50=float(D[col].quantile(.5)), p90=float(D[col].quantile(.9)))


def wins_coef(D, col="war_lost"):
    M = D.dropna(subset=["W_prev", "team_proj"])
    lv = sorted(M.season.unique())
    X = np.column_stack([M[col], M.team_proj, M.W_prev, season_dummies(M.season.to_numpy(), lv)])
    return float(ols(M.W.to_numpy(float), X)[1])


def wins_coef_c(D):
    M = D.dropna(subset=["W_prev", "team_proj"])
    lv = sorted(M.season.unique())
    X = np.column_stack([M.war_lost_c, M.team_proj, M.W_prev, M.W_pre, M.G_post, season_dummies(M.season.to_numpy(), lv)])
    return float(ols(M.W_post.to_numpy(float), X)[1])


def logit_fit(y, X):
    """Newton-Raphson logistic regression with intercept; returns params or None."""
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


def playoff(D, col="war_lost", at=None, proj_med=None):
    lv = sorted(D.season.unique())
    sd = season_dummies(D.season.to_numpy(), lv)
    X = np.column_stack([D[col], D.team_proj, sd])
    b = logit_fit(D.q.to_numpy(float), X)
    if b is None:
        return None
    at = at if at is not None else [D[col].quantile(q) for q in (.1, .5, .9)]
    pm = proj_med if proj_med is not None else D.team_proj.median()
    probs = []
    for v in at:
        eta = b[0] + b[1] * v + b[2] * pm + sd @ b[3:]
        probs.append(float(np.mean(1 / (1 + np.exp(-eta)))))
    return dict(or_per_war_lost=float(np.exp(b[1])), p_at_p10_p50_p90=probs, war_lost_at=[float(v) for v in at])


def loso(D, cols, seasons, demean=False):
    """Leave-one-season-out predictions and OOS R2 (v1 formula; or season-demeaned with benchmark 0)."""
    M = D[D.season.isin(seasons)].copy()
    y = M.war_lost.to_numpy(float); X = M[cols].to_numpy(float); ss = M.season.to_numpy()
    if demean:
        for s in seasons:
            m = ss == s
            y = y.copy(); X = X.copy()
            y[m] -= y[m].mean(); X[m] -= X[m].mean(0)
    pred = np.empty(len(y)); sse = sst = 0.0
    for s in seasons:
        te = ss == s; tr = ~te
        b = ols(y[tr], X[tr])
        pred[te] = b[0] + X[te] @ b[1:]
        sse += ((y[te] - pred[te]) ** 2).sum()
        sst += ((y[te] - (0.0 if demean else y[tr].mean())) ** 2).sum()
    return 1 - sse / sst, pd.Series(y - pred, index=M.index)


def icc1(D, col, clubcol="club_key"):
    Y = D.pivot_table(index=clubcol, columns="season", values=col)
    if Y.isna().any().any():
        return np.nan
    Y = Y.to_numpy(float); k, n = Y.shape
    Y = Y - Y.mean(0, keepdims=True)
    cm = Y.mean(1)
    msb = n * ((cm - Y.mean()) ** 2).sum() / (k - 1)
    msw = ((Y - cm[:, None]) ** 2).sum() / ((k - 1) * (n - 1))
    return float((msb - msw) / (msb + (n - 1) * msw))


def icc_perm(D, col, rng, nperm=2000, clubcol="club_key"):
    Y = D.pivot_table(index=clubcol, columns="season", values=col).to_numpy(float)
    k, n = Y.shape
    Y = Y - Y.mean(0, keepdims=True)

    def stat(M):
        cm = M.mean(1)
        msb = n * ((cm - M.mean()) ** 2).sum() / (k - 1)
        msw = ((M - cm[:, None]) ** 2).sum() / ((k - 1) * (n - 1))
        return (msb - msw) / (msb + (n - 1) * msw)
    obs = stat(Y)
    null = np.empty(nperm)
    for i in range(nperm):
        null[i] = stat(np.column_stack([Y[rng.permutation(k), j] for j in range(n)]))
    return float(obs), float((1 + (null >= obs).sum()) / (nperm + 1)), float(np.quantile(null, .95)), null


def sd_within(D, col):
    return float(D.groupby("season")[col].std().mean())


# ====================================================================================================
# 4. Point estimates
# ====================================================================================================
e1 = dist(T)
if RULE == "sealed":
    for k_ in ("mean", "sd_within_season", "p10", "p90"):
        assert abs(e1[k_] - F1R["war_lost"][k_]) < 1e-9, k_
# E2 primary: F1's OLS (club-clustered); carried when sealed, refitted on the repaired episodes under R1
_M = T.dropna(subset=["W_prev", "team_proj"]).copy()
_Xm = pd.concat([_M[["war_lost", "team_proj", "W_prev"]], pd.get_dummies(_M.season, prefix="s", drop_first=True, dtype=float)], axis=1)
_fm = sm.OLS(_M.W, sm.add_constant(_Xm)).fit(cov_type="cluster", cov_kwds={"groups": _M.tid})
E2_FIT = dict(est=float(_fm.params["war_lost"]), se=float(_fm.bse["war_lost"]), lo=float(_fm.conf_int().loc["war_lost", 0]),
              hi=float(_fm.conf_int().loc["war_lost", 1]), n=int(len(_M)), r2=float(_fm.rsquared))
if RULE == "sealed":
    assert abs(E2_FIT["est"] - F1R["wins_per_war_lost"]["est"]) < 1e-9
    E2_FIT = dict(F1R["wins_per_war_lost"])
WPW = -E2_FIT["est"]  # wins-per-WAR conversion: F1's coefficient when sealed, the repaired coefficient under R1
_Y = T.dropna(subset=["war_lost_prev"]); _fy = sm.OLS(_Y.war_lost, sm.add_constant(_Y.war_lost_prev)).fit()
SEALED_F1 = {"mean": F1R["war_lost"]["mean"], "sd_within_season": F1R["war_lost"]["sd_within_season"], "p10": F1R["war_lost"]["p10"],
             "p90": F1R["war_lost"]["p90"], "max": F1R["war_lost"]["max"], "one_sd_wins": F1R["wins_one_sd"],
             "p10_to_p90_wins": (F1R["war_lost"]["p90"] - F1R["war_lost"]["p10"]) * WPW_F1, "wins_per_war_lost": F1R["wins_per_war_lost"],
             "yoy_r2": F1R["yoy_r2"], "note": "sealed F1 values (framing prereg 1898c1f6e60769bd), shown beside the repaired primary"}
R = {"meta": {"prereg": {"file": PREREG[0], "sha16": PREREG[1]}, "inputs_sha16": hashes, "seed": SEED, "B": B,
              "episode_rule": RULE, "outcome_seasons": OUTCOME, "K_primary": K, "wins_per_war_conversion": WPW,
              "wins_per_war_conversion_source": "F1 sealed coefficient" if RULE == "sealed" else "repaired E2 coefficient (R1)",
              "f1_gate": {"passed": True, "max_abs_diff": maxdiff, "rows": int(len(T_SEALED)), "note": "run on the sealed build before any repair"},
              "n_episodes_outcome_seasons": int(len(S)), "n_club_seasons": int(len(T))}}
if RULE == "r1":
    R["meta"]["r1_repair"] = {"placement_end_source_counts": {k: int(v) for k, v in P.end_src.value_counts().items()},
                              "outcome_episodes_changed": int((~S.end_rule.isin(["census", "open"])).sum()),
                              "player_seasons_trimmed_by_games_played_cap_2012_2025": int(BLD["n_player_seasons_trimmed"]),
                              "episodes_cut_by_cross_club_overlap_2012_2025": int(BLD["n_cross_club_overlaps"]),
                              "outcome_episode_end_rules": {k: int(v) for k, v in S.end_rule.value_counts().items()}}
T["club_key"] = T.tid
# E1 ---------------------------------------------------------------------------------------------
R["E1"] = {"source": ("F1 carried (framing prereg 1898c1f6e60769bd); recomputed only to check equality" if RULE == "sealed"
                      else "R1-repaired episodes (Phase 1b defect repair); sealed F1 values in E1.sealed_F1"),
           "mean": e1["mean"], "sd_within_season": e1["sd_within_season"],
           "p10": e1["p10"], "p50": e1["p50"], "p90": e1["p90"], "max": float(T.war_lost.max()),
           "p10_to_p90_war": e1["p90"] - e1["p10"],
           "p10_to_p90_wins": (e1["p90"] - e1["p10"]) * WPW,
           "one_sd_wins": e1["sd_within_season"] * WPW,
           "by_season_mean": {int(s): float(v) for s, v in T.groupby("season").war_lost.mean().items()},
           "brackets_carried": {"marcel_with_zeros": F1R["war_lost_zeros"], "same_season_pace": F1R["war_lost_pace"],
                                "note": "sealed F1 brackets; not rebuilt under R1"},
           "K_sensitivity": {f"K{k}": dist(T, f"war_lost_K{k}") for k in (50, 200)},
           "yoy_r2": float(_fy.rsquared), "yoy_slope": float(_fy.params.iloc[1]), "yoy_n": int(len(_Y)),
           "yoy_r2_carried": F1R["yoy_r2"]}
if RULE == "sealed":
    for k_ in ("mean", "sd_within_season", "p10", "p90", "max", "one_sd_wins"):
        R["E1"][k_] = SEALED_F1[k_]
else:
    R["E1"]["sealed_F1"] = SEALED_F1
# E2 ---------------------------------------------------------------------------------------------
R["E2"] = {"source": "F1 carried" if RULE == "sealed" else "F1 OLS specification refitted on R1-repaired episodes",
           **E2_FIT, "wins_per_war_lost_abs": WPW,
           "K_sensitivity": {f"K{k}": wins_coef(T, f"war_lost_K{k}") for k in (50, 200)}}
if RULE == "r1":
    R["E2"]["sealed_F1"] = F1R["wins_per_war_lost"]


# E3 ---------------------------------------------------------------------------------------------
AT = [e1["p10"], e1["p50"], e1["p90"]]  # equal to the F1 values under the sealed rule (asserted above)
PM = float(T.team_proj.median())
R["E3"] = {"spec": "logit qualified ~ war_lost + team_proj + season FE, 300 rows; P at median team_proj averaged over season FE",
           "all": playoff(T, at=AT, proj_med=PM), "team_proj_median": PM, "qualified_rate": float(T.q.mean())}
Xs = sm.add_constant(pd.concat([T[["war_lost", "team_proj"]], pd.get_dummies(T.season, prefix="s", drop_first=True, dtype=float)], axis=1))
fq = sm.Logit(T.q, Xs).fit(disp=0, cov_type="cluster", cov_kwds={"groups": T.tid})
R["E3"]["all"]["or_ci_cluster_robust"] = [float(np.exp(fq.conf_int().loc["war_lost", 0])), float(np.exp(fq.conf_int().loc["war_lost", 1]))]
assert abs(np.exp(fq.params["war_lost"]) - R["E3"]["all"]["or_per_war_lost"]) < 1e-6
T22 = T[T.season >= 2022]
R["E3"]["format_2022plus"] = playoff(T22, at=AT, proj_med=PM)
R["E3"]["format_2022plus"]["n"] = int(len(T22))
TW = T.dropna(subset=["W_prev"])
lv = sorted(TW.season.unique())
bW = logit_fit(TW.q.to_numpy(float), np.column_stack([TW.war_lost, TW.team_proj, TW.W_prev, season_dummies(TW.season.to_numpy(), lv)]))
R["E3"]["with_W_prev"] = {"or_per_war_lost": float(np.exp(bW[1])), "n": int(len(TW))}
# E4 / E5 ----------------------------------------------------------------------------------------
E4 = {}
for nm, cols in FEATS.items():
    r2, resid = loso(T, cols, SEASONS_P)
    E4[nm] = {"oos_r2": float(r2), "n": int(T.season.isin(SEASONS_P).sum())}
    if nm == "all":
        T.loc[resid.index, "unexpected_oos"] = resid
    E4[nm]["oos_r2_season_demeaned"] = float(loso(T, cols, SEASONS_P, demean=True)[0])
    S21 = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
    E4[nm]["oos_r2_incl_2021"] = float(loso(T, cols, S21)[0])
R["E4"] = {"seasons": SEASONS_P, "sst": "about the training-fold mean (v1 formula)", **E4}
r2ro, resid_ro = loso(T, FEATS["roster_only"], OUTCOME)
T["unexpected_roster_loso"] = resid_ro
h = sm.OLS(T.war_lost, sm.add_constant(T[FEATS["roster_only"]])).fit()
T["unexpected_roster_insample"] = h.resid
T["war_lost_expected_oos"] = T.war_lost - T.unexpected_oos
TP = T[T.season.isin(SEASONS_P)]
R["E5"] = {"sd_unexpected_oos_war": sd_within(TP, "unexpected_oos"),
           "sd_unexpected_oos_wins": sd_within(TP, "unexpected_oos") * WPW, "n": int(len(TP)),
           "share_of_variance_unexpected": float(sd_within(TP, "unexpected_oos") ** 2 / sd_within(TP, "war_lost") ** 2),
           "sd_war_lost_same_rows": sd_within(TP, "war_lost"),
           "sensitivity": {"roster_loso_300": {"sd_war": sd_within(T, "unexpected_roster_loso"), "sd_wins": sd_within(T, "unexpected_roster_loso") * WPW, "oos_r2": float(r2ro)},
                           "roster_insample_300": {"sd_war": sd_within(T, "unexpected_roster_insample"), "sd_wins": sd_within(T, "unexpected_roster_insample") * WPW}}}
# E6 ---------------------------------------------------------------------------------------------
fam = S.groupby("family").agg(episodes=("mlbid", "size"), war_lost=("war_lost", "sum"), il_days=("days", "sum"))
fam["share_war_lost"] = fam.war_lost / fam.war_lost.sum()
fam["war_per_episode"] = fam.war_lost / fam.episodes
fam["war_per_club_season"] = fam.war_lost / len(T)
fam = fam.sort_values("war_lost", ascending=False)
PLo = PL[PL.season.isin(OUTCOME) & ~PL.covid_era_blank].copy()
PLo["family"] = PLo.dx.map(family_v11)


def crosstab(D, sitecol="site"):
    cw = D[D[sitecol].isin(CROSSWALK)]
    agree = np.mean([f in CROSSWALK[s] for f, s in zip(cw.family, cw[sitecol])])
    return {"n": int(len(D)), "n_with_crosswalk": int(len(cw)), "agreement": float(agree),
            "n_no_counterpart": {k: int(v) for k, v in D.loc[~D[sitecol].isin(CROSSWALK), sitecol].value_counts().items()},
            "table": {s: {f: int(n) for f, n in g.family.value_counts().items()} for s, g in D.groupby(sitecol)}}


R["E6"] = {"taxonomy": "v1.1 (FAM_V11, whole-word) on the episode's first-placement dx",
           "families": fam.reset_index().to_dict(orient="records"),
           "elbow_plus_shoulder_share": float(fam.loc[[f for f in ["UCL / Tommy John", "Elbow (other)", "Shoulder"] if f in fam.index], "share_war_lost"].sum()),
           "crosstab_placements": crosstab(PLo), "crosstab_episodes": crosstab(S)}
# E7 ---------------------------------------------------------------------------------------------
ss_ = S.sort_values("war_lost", ascending=False).groupby(["season", "tid"])
conc = pd.DataFrame({"top1": ss_.head(1).groupby(["season", "tid"]).war_lost.sum(),
                     "top3": ss_.head(3).groupby(["season", "tid"]).war_lost.sum()}).reset_index().merge(T[["season", "tid", "war_lost"]])


def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


R["E7"] = {"top1_share_mean": float((conc.top1 / conc.war_lost).mean()), "top3_share_mean": float((conc.top3 / conc.war_lost).mean()),
           "gini_club_seasons": gini(T.war_lost),
           "top_episodes": S.sort_values("war_lost", ascending=False).head(15)[["season", "tid", "mlbid", "name", "start", "end", "games_missed", "rate", "war_lost", "dx", "family"]]
           .assign(start=lambda d: d.start.dt.strftime("%Y-%m-%d"), end=lambda d: d.end.dt.strftime("%Y-%m-%d"), club=lambda d: d.tid.map(NAME)).to_dict(orient="records")}
# E8 ---------------------------------------------------------------------------------------------
R["E8"] = {"name": "IL open on the final regular-season day", "share_of_episodes": float(S.il_open_final_day.mean()),
           "share_of_war_lost": float(S.war_lost[S.il_open_final_day].sum() / S.war_lost.sum()), "n_episodes": int(S.il_open_final_day.sum())}
# E9 ---------------------------------------------------------------------------------------------
R["E9"] = {"mean_war_lost_per_club_season": {g: float(T[f"war_lost_{g}"].mean()) for g in ["hitter", "starter", "reliever", "pitcher, role unknown", "unknown"]},
           "episodes": {k: int(v) for k, v in S.group.value_counts().items()}}
# E10 --------------------------------------------------------------------------------------------
hh = P_("Hot_Hand_Bat_Tracking/repo/results/paper_results.json")
E10 = {"batting_order": {"wins": 1.0, "source": "Tango, Lichtman & Dolphin, The Book (2007), as cited in IL_Team_Burden v1", "status": "published book; page citation not verified in this build"}}
if os.path.exists(hh):
    pj = json.load(open(hh))["primary"]["platoon"]
    lhb, rhb = pj["LHB_league_split_pts"], pj["RHB_league_split_pts"]
    runs = 180 * ((0.7 * lhb + 0.7 * rhb) / 1000) / 1.25
    E10["platoon_one_spot"] = {"LHB_pts": lhb, "RHB_pts": rhb, "runs": runs, "wins": runs / 9.5, "source_sha16": sha16(hh),
                               "source": "Hot_Hand_Bat_Tracking/repo/results/paper_results.json primary.platoon",
                               "status": "unpublished (companion work in preparation); conversion formula carried from v1"}
else:
    E10["platoon_one_spot"] = {"status": "source results file absent; cite as unpublished, no value"}
E10["injury_luck_one_sd_wins"] = R["E1"]["one_sd_wins"]
E10["injury_luck_unexpected_one_sd_wins"] = R["E5"]["sd_unexpected_oos_wins"]
R["E10"] = E10
# E11 --------------------------------------------------------------------------------------------
rng = np.random.default_rng(SEED)
E11 = {"mde_icc_prefit": 0.1098, "mde_icc_prefit_n10": 0.0881, "alpha_one_sided": 0.05}


def persistence(D, col, seasons, rng, pairs_rule="calendar-consecutive"):
    D = D[D.season.isin(seasons)]
    obs, p, q95, null = icc_perm(D, col, rng)
    Y = D.pivot_table(index="club_key", columns="season", values=col)
    Yd = Y - Y.mean(0)
    pairs = [(s - 1, s) for s in seasons if s - 1 in seasons]
    a = np.concatenate([Yd[s0].to_numpy() for s0, _ in pairs]); b = np.concatenate([Yd[s1].to_numpy() for _, s1 in pairs])
    odd = [s for s in seasons if s % 2 == 1]; even = [s for s in seasons if s % 2 == 0]
    r_sh = float(np.corrcoef(Yd[odd].mean(1), Yd[even].mean(1))[0, 1])
    try:
        md = sm.MixedLM.from_formula(f"{col} ~ C(season)", groups="club_key", data=D.reset_index(drop=True)).fit(reml=True)
        v_re = float(md.cov_re.iloc[0, 0]); icc_reml = v_re / (v_re + float(md.scale))
    except Exception as ex:  # noqa: BLE001
        icc_reml = None
    return {"icc1": obs, "p_perm_one_sided": p, "null_q95": q95, "null_mean": float(null.mean()), "n_club_seasons": int(len(D)),
            "n_seasons": len(seasons), "icc_reml": icc_reml, "yoy_r": float(np.corrcoef(a, b)[0, 1]), "yoy_pairs": int(len(a)),
            "split_half_r": r_sh, "split_half_spearman_brown": (float(2 * r_sh / (1 + r_sh)) if r_sh > 0 else None),  # undefined for r <= 0 (Phase 1b)
            "sd_within_season_war": sd_within(D, col)}


E11["primary"] = persistence(T, "unexpected_oos", SEASONS_P, rng)
E11["primary"]["mde_sd_club_effect_war"] = float(np.sqrt(0.1098) * E11["primary"]["sd_within_season_war"])
E11["primary"]["mde_sd_club_effect_wins"] = E11["primary"]["mde_sd_club_effect_war"] * WPW
E11["sens_roster_loso_300"] = persistence(T, "unexpected_roster_loso", OUTCOME, rng)
E11["sens_roster_insample_300"] = persistence(T, "unexpected_roster_insample", OUTCOME, rng)
p1, pa = E11["primary"]["p_perm_one_sided"], E11["sens_roster_loso_300"]["p_perm_one_sided"]
E11["verdict"] = ("luck at this precision" if p1 >= .05 and pa >= .05 else
                  "persistent club component carried by the club's prior year (foreseeable)" if p1 >= .05 else
                  "persistent club component beyond what is foreseeable")
R["E11"] = E11
# E12 --------------------------------------------------------------------------------------------
E12 = {"a_pre_aug1": {"wins_per_war_lost": wins_coef(T, "war_lost_a"), "playoff": playoff(T, "war_lost_a", proj_med=PM)},
       "b_in_contention": {"wins_per_war_lost": wins_coef(T, "war_lost_b"), "playoff": playoff(T, "war_lost_b", proj_med=PM),
                           "threshold_games_behind": 10, "share_war_lost_excluded": float(S.war_lost[S.out_of_contention].sum() / S.war_lost.sum())},
       "c_split_season": {"wins_per_war_lost_post_jul1": wins_coef_c(T)}}
for k_ in ("a_pre_aug1", "b_in_contention"):
    E12[k_]["shift_vs_primary"] = E12[k_]["wins_per_war_lost"] - R["E2"]["est"]
E12["c_split_season"]["shift_vs_primary"] = E12["c_split_season"]["wins_per_war_lost_post_jul1"] - R["E2"]["est"]


def month_profile(D):
    t = D.groupby("month").war_lost.sum()
    return {("<=Apr" if m == 4 else ">=Sep" if m == 9 else str(m)): float(v / t.sum()) for m, v in t.items()}


qual = S.merge(T[["season", "tid", "q"]], on=["season", "tid"])
E12["d_month_profile"] = {"in_contention": month_profile(S[~S.out_of_contention]), "out_of_contention": month_profile(S[S.out_of_contention]),
                          "qualified": month_profile(qual[qual.q == 1]), "not_qualified": month_profile(qual[qual.q == 0]),
                          "n_out_of_contention_episodes": int(S.out_of_contention.sum())}
R["E12"] = E12

# ====================================================================================================
# 5. E13 bootstrap: resample clubs, refit everything
# ====================================================================================================
clubs = sorted(T.tid.unique())
byclub = {c: T[T.tid == c] for c in clubs}
rb = np.random.default_rng(SEED)
keys = ["E1.sd_within_season", "E1.mean", "E1.p10", "E1.p90", "E1.p10_to_p90_wins", "E1.p10_to_p90_wins_joint", "E1.one_sd_wins_joint",
        "E2.est", "E2.disattenuated", "E3.or", "E3.p10", "E3.p50", "E3.p90", "E3.p10_minus_p90", "E3_22.or", "E3_22.p10", "E3_22.p50", "E3_22.p90",
        "E4.prior_year_only", "E4.roster_only", "E4.all", "E4.all_demeaned", "E5.sd_war", "E5.sd_wins",
        "E11.icc1", "E11.roster_loso_icc1", "E11.roster_insample_icc1",
        "E12.a", "E12.b", "E12.c", "E12.a_shift", "E12.b_shift", "E12.c_shift", "E12.a_or", "E12.b_or"]
BS = {k: [] for k in keys}
fails = 0
for bi in range(B):
    take = rb.integers(0, len(clubs), len(clubs))
    D = pd.concat([byclub[clubs[i]].assign(club_key=j) for j, i in enumerate(take)], ignore_index=True)
    try:
        d1 = dist(D); b2 = wins_coef(D)
        BS["E1.sd_within_season"].append(d1["sd_within_season"]); BS["E1.mean"].append(d1["mean"])
        BS["E1.p10"].append(d1["p10"]); BS["E1.p90"].append(d1["p90"])
        BS["E1.p10_to_p90_wins"].append((d1["p90"] - d1["p10"]) * WPW)
        BS["E1.p10_to_p90_wins_joint"].append((d1["p90"] - d1["p10"]) * -b2)
        BS["E1.one_sd_wins_joint"].append(d1["sd_within_season"] * -b2)
        BS["E2.est"].append(b2)
        BS["E2.disattenuated"].append(np.nan)  # non-public sensitivity: not computed in this repository
        pq_ = playoff(D, proj_med=D.team_proj.median())
        p22 = playoff(D[D.season >= 2022], at=pq_["war_lost_at"] if pq_ else None, proj_med=D.team_proj.median()) if pq_ else None
        if pq_ is None or p22 is None:
            raise ValueError("logit")
        BS["E3.or"].append(pq_["or_per_war_lost"]); BS["E3.p10"].append(pq_["p_at_p10_p50_p90"][0])
        BS["E3.p50"].append(pq_["p_at_p10_p50_p90"][1]); BS["E3.p90"].append(pq_["p_at_p10_p50_p90"][2])
        BS["E3.p10_minus_p90"].append(pq_["p_at_p10_p50_p90"][0] - pq_["p_at_p10_p50_p90"][2])
        BS["E3_22.or"].append(p22["or_per_war_lost"]); BS["E3_22.p10"].append(p22["p_at_p10_p50_p90"][0])
        BS["E3_22.p50"].append(p22["p_at_p10_p50_p90"][1]); BS["E3_22.p90"].append(p22["p_at_p10_p50_p90"][2])
        for nm, cols in FEATS.items():
            r2, rsd = loso(D, cols, SEASONS_P)
            BS[f"E4.{nm}"].append(r2)
            if nm == "all":
                D.loc[rsd.index, "u"] = rsd
        BS["E4.all_demeaned"].append(loso(D, FEATS["all"], SEASONS_P, demean=True)[0])
        DP = D[D.season.isin(SEASONS_P)]
        BS["E5.sd_war"].append(sd_within(DP, "u")); BS["E5.sd_wins"].append(sd_within(DP, "u") * WPW)
        BS["E11.icc1"].append(icc1(DP, "u"))
        _, rr = loso(D, FEATS["roster_only"], OUTCOME); D["ur"] = rr
        BS["E11.roster_loso_icc1"].append(icc1(D, "ur"))
        hh_ = ols(D.war_lost.to_numpy(float), D[FEATS["roster_only"]].to_numpy(float))
        D["ui"] = D.war_lost - (hh_[0] + D[FEATS["roster_only"]].to_numpy(float) @ hh_[1:])
        BS["E11.roster_insample_icc1"].append(icc1(D, "ui"))
        a_, b_, c_ = wins_coef(D, "war_lost_a"), wins_coef(D, "war_lost_b"), wins_coef_c(D)
        BS["E12.a"].append(a_); BS["E12.b"].append(b_); BS["E12.c"].append(c_)
        BS["E12.a_shift"].append(a_ - b2); BS["E12.b_shift"].append(b_ - b2); BS["E12.c_shift"].append(c_ - b2)
        pa_ = playoff(D, "war_lost_a", proj_med=D.team_proj.median()); pb_ = playoff(D, "war_lost_b", proj_med=D.team_proj.median())
        BS["E12.a_or"].append(pa_["or_per_war_lost"] if pa_ else np.nan); BS["E12.b_or"].append(pb_["or_per_war_lost"] if pb_ else np.nan)
    except Exception:  # noqa: BLE001
        fails += 1
        n0 = min(len(v) for v in BS.values())
        for v in BS.values():
            del v[n0:]
    if bi % 250 == 0:
        print(f"bootstrap {bi}/{B}  {time.time() - T0:.0f}s", flush=True)


def ci(k):
    v = np.asarray(BS[k], float); v = v[np.isfinite(v)]
    return [float(np.quantile(v, .025)), float(np.quantile(v, .975))] if len(v) else None


R["E13"] = {"B": B, "seed": SEED, "draws_dropped": fails, "method": "club-clustered percentile bootstrap, 30 clubs resampled",
            "ci95": {k: ci(k) for k in keys}}
# attach CIs next to the point values they belong to
C_ = R["E13"]["ci95"]
R["E1"]["ci95"] = {"sd_within_season": C_["E1.sd_within_season"], "mean": C_["E1.mean"], "p10": C_["E1.p10"], "p90": C_["E1.p90"],
                   "p10_to_p90_wins": C_["E1.p10_to_p90_wins"], "p10_to_p90_wins_joint": C_["E1.p10_to_p90_wins_joint"],
                   "one_sd_wins_joint": C_["E1.one_sd_wins_joint"]}
R["E2"]["ci95_bootstrap"] = C_["E2.est"]
R["E3"]["all"]["ci95_bootstrap"] = {"or": C_["E3.or"], "p10": C_["E3.p10"], "p50": C_["E3.p50"], "p90": C_["E3.p90"], "p10_minus_p90": C_["E3.p10_minus_p90"]}
R["E3"]["all"]["p10_minus_p90"] = R["E3"]["all"]["p_at_p10_p50_p90"][0] - R["E3"]["all"]["p_at_p10_p50_p90"][2]
R["E3"]["format_2022plus"]["ci95_bootstrap"] = {"or": C_["E3_22.or"], "p10": C_["E3_22.p10"], "p50": C_["E3_22.p50"], "p90": C_["E3_22.p90"]}
for nm in FEATS:
    R["E4"][nm]["ci95"] = C_[f"E4.{nm}"]
R["E4"]["all"]["ci95_season_demeaned"] = C_["E4.all_demeaned"]
R["E5"]["ci95"] = {"sd_war": C_["E5.sd_war"], "sd_wins": C_["E5.sd_wins"]}
R["E11"]["primary"]["ci95_icc1"] = C_["E11.icc1"]
R["E11"]["sens_roster_loso_300"]["ci95_icc1"] = C_["E11.roster_loso_icc1"]
R["E11"]["sens_roster_insample_300"]["ci95_icc1"] = C_["E11.roster_insample_icc1"]
for k_, kk in (("a_pre_aug1", "a"), ("b_in_contention", "b")):
    R["E12"][k_]["ci95"] = C_[f"E12.{kk}"]; R["E12"][k_]["ci95_shift"] = C_[f"E12.{kk}_shift"]; R["E12"][k_]["ci95_or"] = C_[f"E12.{kk}_or"]
R["E12"]["c_split_season"]["ci95"] = C_["E12.c"]; R["E12"]["c_split_season"]["ci95_shift"] = C_["E12.c_shift"]
R["meta"]["runtime_s"] = round(time.time() - T0, 1)
# figure support: bootstrap band of P(playoffs) along a war_lost grid (median-projection club) and E11 null
grid = np.linspace(0, 20, 41)
band = []
rb2 = np.random.default_rng(SEED + 1)
for bi in range(min(B, 1000)):
    take = rb2.integers(0, len(clubs), len(clubs))
    D = pd.concat([byclub[clubs[i]] for i in take], ignore_index=True)
    pp = playoff(D, at=list(grid), proj_med=PM)
    if pp:
        band.append(pp["p_at_p10_p50_p90"])
band = np.asarray(band)
R["figure_support"] = {"playoff_curve": {"war_lost_grid": grid.tolist(), "p": playoff(T, at=list(grid), proj_med=PM)["p_at_p10_p50_p90"],
                                         "lo": np.quantile(band, .025, axis=0).tolist(), "hi": np.quantile(band, .975, axis=0).tolist(), "draws": int(len(band))}}

# ====================================================================================================
# 6. Write
# ====================================================================================================
json.dump(R, open(os.path.join(RES, "injury_luck_results.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
T.drop(columns=["club_key", "war_lost_v1"], errors="ignore").to_csv(os.path.join(RES, "team_season_public.csv"), index=False)
S.assign(club=S.tid.map(NAME)).to_csv(os.path.join(RES, "stints_public_2015_2025.csv"), index=False)
print(json.dumps({k: R[k] for k in ["E1", "E2", "E4", "E5"]}, indent=1, default=str)[:3000])
print("E11", json.dumps(R["E11"], indent=1)[:2500])
print(f"done in {time.time() - T0:.0f}s")
