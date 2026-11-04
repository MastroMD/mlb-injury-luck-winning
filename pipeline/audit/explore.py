"""
explore.py - post hoc, exploratory analyses for the 2026-10-12 comprehensive review (not part of any sealed plan).

Reads the audit's own club-season / episode tables (indep_recompute.py) plus the pinned inputs, and writes
explore_results.json. Every result here is EXPLORATORY and would need a DEVIATIONS entry and a post hoc label
before it enters a manuscript.

  X1  injury family from every IL transaction in the episode (60-day transfers carry the operative diagnosis)
  X2  days- and count-based burden versus talent-weighted WAR lost (which predicts wins?)
  X3  construct validity: hitter WAR lost vs runs scored, pitcher WAR lost vs runs allowed
  X4  wins per WAR lost by roster slot (hitters / starters / relievers)
  X5  secular trend in burden per club-season, 2015-2025 (IL rule changes 2017, 2022)
  X6  playoff berths re-allocated by injury loss per season (logit counterfactual at the median)
  X7  preseason predictors of injury loss (roster age, prior IL days), in-sample coefficients with club-clustered CIs
  X8  wins per WAR lost by body region (throwing-arm vs other) for pitchers
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT, AUD = sys.argv[1], sys.argv[2]
OUT = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
PREV = {s: (2019 if s == 2021 else s - 1) for s in OUT}
R = {}

E = pd.read_csv(f"{AUD}/audit_episodes_all.csv", parse_dates=["st", "en", "il0"])
T = pd.read_csv(f"{AUD}/audit_team_season.csv")
FG = pd.read_csv(f"{ROOT}/inputs/fangraphs_war_2010_2025.csv").dropna(subset=["mlbamid"])
FG["pid"] = FG.mlbamid.astype(int)
G = pd.read_csv(f"{ROOT}/inputs/games_flat.csv")
G = G[(G.gameType == "R") & G.status.isin(["Final", "Completed Early"])].copy()
G["date"] = pd.to_datetime(G.date)
GL = pd.read_csv(f"{ROOT}/inputs/gamelogs_flat.csv", usecols=["player_id", "season", "gamePk", "GS"])
GL = GL[GL.gamePk.isin(set(G.gamePk))]
last_day = G.groupby("season").date.max().to_dict()

# ---- Marcel rate (same as the audit recompute) for slot / region splits
F = FG.groupby(["pid", "season"]).war.sum()
gm_ps = E.groupby(["pid", "season"]).gm.sum()
EXP = {(p, s): (w, max(1, (60 if s == 2020 else 162) - gm_ps.get((p, s), 0))) for (p, s), w in F.items()}


def rate(p, s, K=100):
    num = den = 0.0
    for w, k in zip((5, 4, 3), (1, 2, 3)):
        v = EXP.get((p, s - k))
        if v:
            num += w * v[0]; den += w * v[1]
    return max(0.0, num / (den + K))


EO = E[E.season.isin(OUT)].copy()
EO["r"] = [rate(p, s) for p, s in zip(EO.pid, EO.season)]
EO["wl"] = EO.r * EO.gm

# ---- roster slot (paper's rule: pitcher row and < 100 PA -> pitcher; GS/G >= .5 -> starter)
pa = FG[FG.role == "hitter"].groupby(["pid", "season"]).pa.sum()
roles = FG.groupby(["pid", "season"]).role.agg(frozenset)
RD = {k: ("pitcher" if ("pitcher" in v and pa.get(k, 0.0) < 100) else "hitter") for k, v in roles.items()}
gsg = GL.groupby(["player_id", "season"]).agg(g=("gamePk", "nunique"), gs=("GS", "sum"))
SPD = ((gsg.gs / gsg.g.clip(lower=1)) >= 0.5).to_dict()


def slot(p, s):
    r = next((RD[(p, y)] for y in (s, s - 1, s - 2, s - 3) if (p, y) in RD), None)
    if r is None:
        return "unknown"
    if r == "hitter":
        return "hitter"
    sp = next((SPD[(p, y)] for y in range(s, s - 4, -1) if (p, y) in SPD), None)
    return "pitcher_unknown" if sp is None else ("starter" if sp else "reliever")


EO["slot"] = [slot(p, s) for p, s in zip(EO.pid, EO.season)]

# ---- family taxonomy v1.1 (declared), applied to the first placement (paper) and to every IL transaction (X1)
FAM = [("UCL / Tommy John", r"tommy john|ucl|ulnar collateral"), ("Elbow (other)", r"elbow"),
       ("Lat / teres", r"lat|lats|latissimus|teres"), ("Shoulder", r"shoulder|rotator cuff|rotator|labrum|labral"),
       ("Forearm / flexor", r"forearm|flexor|pronator"), ("Oblique / core", r"oblique|intercostal|abdominal|core|ribs?|ribcage"),
       ("Hamstring", r"hamstring"), ("Back / neck", r"back|lumbar|spine|spinal|disc|discs|neck|cervical"),
       ("Knee", r"knee|acl|mcl|meniscus|patellar?|patella"), ("Hand / wrist / finger", r"hand|wrist|fingers?|thumb|hamate|metacarpal"),
       ("Foot / ankle", r"foot|ankle|toes?|achilles|plantar|heel"), ("Hip / groin", r"hip|groin|adductor|hernia|sports hernia"),
       ("Calf / quad / leg", r"calf|quad|quadriceps|leg|shin|tibia|fibula"), ("Concussion", r"concussion|head"),
       ("Illness / other", r"illness|covid|covid-19|virus|flu|vertigo|appendicitis|appendectomy|surgery|undisclosed|personal|blood|infection|anxiety|mononucleosis")]
FRX = [(n, re.compile(r"\b(?:" + p + r")\b")) for n, p in FAM]


def fam(t):
    t = str(t).lower()
    for n, rx in FRX:
        if rx.search(t):
            return n
    return "Unstated"


EO["family_first"] = EO.dx.map(fam)
# every IL transaction of the player (placed / transferred / recalled-to-IL) dated from the first placement to the episode end
il_rx = re.compile(r"(injured|disabled) list", re.I)
txt = defaultdict(list)
with open(f"{ROOT}/inputs/txns_live.jsonl") as fh:
    for line in fh:
        t = json.loads(line); d = t.get("description") or ""
        if il_rx.search(d) and not re.search(r"\bactivated\b|\breinstated\b", d, re.I):
            p = (t.get("person") or {}).get("id")
            if p:
                txt[int(p)].append((pd.Timestamp(t.get("date")), d))
# diagnosis text after the transaction sentence (the feed appends it, e.g. "... to the 60-day injured list. UCL reconstruction.")
def dx_tail(d):
    m = re.split(r"(?:injured|disabled) list(?: retroactive to [A-Za-z]+ \d+, \d{4})?\.?", d, maxsplit=1)
    return m[1] if len(m) > 1 else ""


PREC = [n for n, _ in FAM]   # precedence = taxonomy order (UCL first)


def fam_all(pid, il0, en, first_dx):
    fams = {fam(first_dx)}
    for d, s in txt.get(pid, []):
        if il0 - pd.Timedelta(days=1) <= d <= en + pd.Timedelta(days=1):
            f = fam(dx_tail(s))
            if f != "Unstated":
                fams.add(f)
    fams.discard("Unstated") if len(fams) > 1 else None
    # a specific diagnosis beats a generic one; UCL beats "Elbow (other)"; anything beats "Illness / other" only via 'surgery'
    for n in PREC:
        if n in fams and not (n == "Illness / other" and len(fams) > 1):
            return n
    return "Unstated"


# the first placement may be in the previous calendar year (carried episodes): look back to the placement date
EO["family_all"] = [fam_all(p, i0, en, dx) for p, i0, en, dx in zip(EO.pid, EO.il0, EO.en, EO.dx)]
tot = EO.wl.sum()
tab = (pd.DataFrame({"first": EO.groupby("family_first").wl.sum() / tot, "all_txns": EO.groupby("family_all").wl.sum() / tot})
       .fillna(0).sort_values("first", ascending=False))
R["X1_family_from_all_il_transactions"] = {
    "share_of_war_lost": {k: {"first_placement": float(v["first"]), "all_transactions": float(v["all_txns"])} for k, v in tab.iterrows()},
    "episodes_changing_family": int((EO.family_first != EO.family_all).sum()),
    "share_war_lost_changing_family": float(EO.loc[EO.family_first != EO.family_all, "wl"].sum() / tot),
    "elbow_other_to_ucl_episodes": int(((EO.family_first == "Elbow (other)") & (EO.family_all == "UCL / Tommy John")).sum()),
    "elbow_other_to_ucl_war": float(EO.loc[(EO.family_first == "Elbow (other)") & (EO.family_all == "UCL / Tommy John"), "wl"].sum() / tot),
    "unstated_resolved_episodes": int(((EO.family_first == "Unstated") & (EO.family_all != "Unstated")).sum()),
    "note": "Exploratory. Family from every IL transaction in the episode (taxonomy v1.1 order as precedence) instead of the first placement only.",
}

# ---- club-season covariates
T = T.sort_values(["tid", "season"]).reset_index(drop=True)
for sl in ("hitter", "starter", "reliever"):
    a = EO[EO.slot == sl].groupby(["season", "tid"]).wl.sum().rename(f"wl_{sl}")
    T = T.merge(a.reset_index(), how="left", on=["season", "tid"]).fillna({f"wl_{sl}": 0.0})
EO["arm"] = EO.family_all.isin(["UCL / Tommy John", "Elbow (other)", "Shoulder", "Forearm / flexor", "Lat / teres"])
for nm, m in (("p_arm", EO.slot.isin(["starter", "reliever"]) & EO.arm), ("p_other", EO.slot.isin(["starter", "reliever"]) & ~EO.arm)):
    a = EO[m].groupby(["season", "tid"]).wl.sum().rename(f"wl_{nm}")
    T = T.merge(a.reset_index(), how="left", on=["season", "tid"]).fillna({f"wl_{nm}": 0.0})
# runs scored / allowed per club-season
rs = pd.concat([G[["season", "home_id", "home_score", "away_score"]].rename(columns={"home_id": "tid", "home_score": "RS", "away_score": "RA"}),
                G[["season", "away_id", "away_score", "home_score"]].rename(columns={"away_id": "tid", "away_score": "RS", "home_score": "RA"})])
rs = rs.groupby(["season", "tid"]).agg(RS=("RS", "sum"), RA=("RA", "sum"), GP=("RS", "size")).reset_index()
T = T.merge(rs, on=["season", "tid"], how="left")
# opening-day projection split by hitters / pitchers
ROS = pd.read_csv(f"{ROOT}/data_public/opening_day_40man_2015_2026.csv").drop_duplicates(["season", "club_id", "mlbam"])
sp = []
for (s, tid), g in ROS[ROS.season.isin(OUT)].groupby(["season", "club_id"]):
    h = p_ = 0.0
    for pid in g.mlbam.astype(int):
        v = rate(pid, s) * 162
        r_ = next((RD[(pid, y)] for y in (s - 1, s - 2, s - 3) if (pid, y) in RD), "hitter")
        if r_ == "pitcher":
            p_ += v
        else:
            h += v
    sp.append(dict(season=s, tid=tid, tp_h=h, tp_p=p_))
T = T.merge(pd.DataFrame(sp), on=["season", "tid"], how="left")
for c in ("RS", "RA", "W"):
    T[f"{c}_prev"] = T.groupby("tid")[c].shift(1)
T["wl_pitch"] = T.wl_starter + T.wl_reliever
D = T[T.W_prev.notna()].copy()


def clus(formula, df, terms):
    f = smf.ols(formula, df).fit(cov_type="cluster", cov_kwds={"groups": df.tid})
    ci = f.conf_int()
    return {t: {"est": float(f.params[t]), "lo": float(ci.loc[t, 0]), "hi": float(ci.loc[t, 1]), "p": float(f.pvalues[t])} for t in terms} | {"n": int(f.nobs), "r2": float(f.rsquared)}


# ---- X2 unweighted burden vs talent-weighted
D["il_days_k"] = D.il_days / 1000; D["gm_k"] = D.gm / 100
R["X2_unweighted_vs_weighted"] = {
    "il_days_per_1000": clus("W ~ il_days_k + tp_od + W_prev + C(season)", D, ["il_days_k"]),
    "games_missed_per_100": clus("W ~ gm_k + tp_od + W_prev + C(season)", D, ["gm_k"]),
    "episodes": clus("W ~ episodes + tp_od + W_prev + C(season)", D, ["episodes"]),
    "war_lost": clus("W ~ wl + tp_od + W_prev + C(season)", D, ["wl"]),
    "both_il_days_and_war_lost": clus("W ~ wl + il_days_k + tp_od + W_prev + C(season)", D, ["wl", "il_days_k"]),
    "corr_war_lost_il_days_within_season": float(np.mean([np.corrcoef(g.wl, g.il_days)[0, 1] for _, g in T.groupby("season")])),
    "standardised_per_within_season_sd": {},
}
for c in ("il_days", "gm", "episodes", "wl"):
    sd = T.groupby("season")[c].std().mean()
    D["z"] = D[c] / sd
    R["X2_unweighted_vs_weighted"]["standardised_per_within_season_sd"][c] = clus("W ~ z + tp_od + W_prev + C(season)", D, ["z"])["z"]

# ---- X3 construct validity: runs
R["X3_runs"] = {
    "runs_scored_on_hitter_and_pitcher_loss": clus("RS ~ wl_hitter + wl_pitch + tp_h + tp_p + RS_prev + GP + C(season)", D, ["wl_hitter", "wl_pitch"]),
    "runs_allowed_on_hitter_and_pitcher_loss": clus("RA ~ wl_hitter + wl_pitch + tp_h + tp_p + RA_prev + GP + C(season)", D, ["wl_hitter", "wl_pitch"]),
    "note": "Exploratory. Hitter WAR lost should lower runs scored and pitcher WAR lost should raise runs allowed; ~10 runs per win.",
}

# ---- X4 wins per WAR lost by slot
R["X4_slot"] = clus("W ~ wl_hitter + wl_starter + wl_reliever + tp_od + W_prev + C(season)", D, ["wl_hitter", "wl_starter", "wl_reliever"])
from statsmodels.stats.contrast import ContrastResults  # noqa: E402,F401
f4 = smf.ols("W ~ wl_hitter + wl_starter + wl_reliever + tp_od + W_prev + C(season)", D).fit(cov_type="cluster", cov_kwds={"groups": D.tid})
R["X4_slot"]["wald_equal_slopes_p"] = float(f4.f_test("wl_hitter = wl_starter, wl_starter = wl_reliever").pvalue)

# ---- X8 pitchers: throwing-arm vs other
R["X8_pitcher_region"] = clus("W ~ wl_p_arm + wl_p_other + wl_hitter + tp_od + W_prev + C(season)", D, ["wl_p_arm", "wl_p_other", "wl_hitter"])
R["X8_pitcher_region"]["arm_share_of_pitcher_war_lost"] = float(EO.loc[EO.slot.isin(["starter", "reliever"]) & EO.arm, "wl"].sum() /
                                                              EO.loc[EO.slot.isin(["starter", "reliever"]), "wl"].sum())

# ---- X5 secular trend
by = T.groupby("season").agg(wl=("wl", "mean"), il_days=("il_days", "mean"), episodes=("episodes", "mean"), gm=("gm", "mean"))
T["yr"] = T.season - 2015
R["X5_trend"] = {"by_season": {int(s): {k: float(v) for k, v in r.items()} for s, r in by.iterrows()},
                 "wl_per_year": clus("wl ~ yr + tp_od", T, ["yr"]),
                 "il_days_per_year": clus("il_days ~ yr", T, ["yr"]),
                 "episodes_per_year": clus("episodes ~ yr", T, ["yr"]),
                 "wl_share_of_tp_od_per_year": clus("I(wl / tp_od) ~ yr", T, ["yr"]),
                 "era_2015_2016_vs_2017_2019_vs_2021_2025_wl": {k: float(v) for k, v in T.groupby(pd.cut(T.season, [2014, 2016, 2019, 2025], labels=["15-16", "17-19", "21-25"]), observed=True).wl.mean().items()}}

# ---- X6 playoff berths re-allocated by injury loss
lg = smf.logit("q ~ wl + tp_od + C(season)", T).fit(disp=0)
med = T.wl.median()
p_act = lg.predict(T); p_med = lg.predict(T.assign(wl=med))
T["dp"] = p_act - p_med
berths = T.groupby("season").dp.apply(lambda x: float(x.abs().sum() / 2))
R["X6_berths"] = {"mean_berths_reallocated_per_season": float(berths.mean()), "by_season": {int(k): float(v) for k, v in berths.items()},
                  "max_single_club_drop_pp": float(-100 * T.dp.min()), "max_single_club_gain_pp": float(100 * T.dp.max()),
                  "note": "Exploratory. Half the summed absolute change in fitted playoff probability when every club's WAR lost is set to the pooled median; an association, not a causal count."}

# ---- X7 preseason predictors (in-sample, standardised within season)
F7 = T[T.season.isin([2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025])].copy()
for c in ("tp_od", "age_od", "ilp_od", "wl_prev"):
    F7[f"z_{c}"] = (F7[c] - F7.groupby("season")[c].transform("mean")) / F7.groupby("season")[c].transform("std")
R["X7_predictors"] = clus("wl ~ z_tp_od + z_age_od + z_ilp_od + z_wl_prev + C(season)", F7, ["z_tp_od", "z_age_od", "z_ilp_od", "z_wl_prev"])
R["X7_predictors"]["note"] = "WAR lost per 1 within-season SD of each Opening Day feature, all four together with season effects; club-clustered."

json.dump(R, open(f"{AUD}/explore_results.json", "w"), indent=1, default=float)
print(json.dumps(R, indent=1, default=float)[:12000])
