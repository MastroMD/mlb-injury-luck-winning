"""
phase2_posthoc_r2.py - post hoc analyses in reply to the Phase 2 referee report (REVIEWER2_REPORT_PHASE2.md).

Nothing here is preregistered and nothing here changes a sealed value. The sealed outputs stay in results/phase2_results.json;
this script never writes them. It runs pipeline/phase2.py's own code (read from disk and executed, not re-typed) with four
marked substitutions, so every value comes through the same estimators, seeds and bootstrap draws as the sealed run:

  S1 club opener    "Opening Day" for designs (f) and (g) and for the opening-day share is each club's first scheduled game,
                    not the league's first game (international opening series in 2019, 2024 and 2025 came 7-9 days early).
  S2 departure end  an IL placement also ends when the player leaves the club in the public transaction feed (traded, claimed,
                    released, elected free agency, retired, designated for assignment, outrighted, placed on waivers, returned,
                    sold, deceased), and a placement from season y is not charged in season y+1 when that club's opening-day
                    40-man roster for y+1 (which lists the 60-day IL) does not include the player. Applied to rule A and rule B.
  S3 gate           the check against results/team_season_public.csv is skipped under S2 (the club-season table is meant to
                    differ); under S1 alone it runs and must pass.
  S4 output names   results/phase2_posthoc_<build>.json and two csv files; the sealed files are never opened for writing.

Modes
  --build opener    --full    Phase 2 with S1. Every value outside P2.2 (f), (g), the range and the opening-day share must equal
                              results/phase2_results.json (checked; exit 1 otherwise), so the harness reproduces the sealed run.
  --build departure --full    Phase 2 with S1 and S2.
  --build opener|departure --extras
                              the point analyses, permutation tests and simulations listed under EXTRAS below, written to
                              results/phase2_posthoc_extras_<build>.json.

Usage (library):  python3 phase2_posthoc_r2.py --root "<MLB Total Research>" --build opener --full [--B 2000]
Usage (repo):     python3 pipeline/phase2_posthoc_r2.py --build departure --extras
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=None)
ap.add_argument("--out", default=os.path.dirname(HERE))
ap.add_argument("--build", choices=["opener", "departure"], required=True)
ap.add_argument("--full", action="store_true")
ap.add_argument("--extras", action="store_true")
ap.add_argument("--B", type=int, default=2000)
ap.add_argument("--nsim", type=int, default=1000)
ap.add_argument("--wcb", type=int, default=9999)
ap.add_argument("--nsim_inv", type=int, default=500, help="panels per rho for the inverted simulation (extras, opener build)")
A = ap.parse_args()
if A.full == A.extras:
    sys.exit("choose exactly one of --full and --extras")
T0 = time.time()
SRC_PATH = os.path.join(HERE, "phase2.py")
SRC = open(SRC_PATH, encoding="utf-8").read()
TAG = A.build + ("" if A.full else "_extras")
OUTNAME = "phase2_posthoc_" + TAG


def sub(src, old, new):
    if src.count(old) != 1:
        sys.exit(f"substitution anchor found {src.count(old)} times: {old[:70]}")
    return src.replace(old, new)


# ---- S1-S4 -----------------------------------------------------------------------------------------------------------
SRC = sub(SRC, 'S["opening"] = S.season.map({s: SPAN[s][0] for s in SPAN})',
          'S["opening"] = [pd.Timestamp(TEAM_DATES[(s_, t_)][0]) for s_, t_ in zip(S.season, S.tid)]  # POSTHOC S1')
if A.build == "departure":
    SRC = sub(SRC, 'P["il_end_r1"], P["end_src"] = r1_end_dates(P)\n',
              'P["il_end_r1"], P["end_src"] = r1_end_dates(P)\nP["il_end_r1"], P["end_src"] = POSTHOC_DEPART(P, "il_end_r1", P["end_src"])  # POSTHOC S2\n')
    SRC = sub(SRC, 'PB["end_src"] = _src\n',
              'PB["end_src"] = _src\nPB["il_end_b"], _src = POSTHOC_DEPART(PB, "il_end_b", _src); PB["end_src"] = _src  # POSTHOC S2\n')
    SRC = sub(SRC, "if max(gate.values()) > 1e-9:", "if False and max(gate.values()) > 1e-9:  # POSTHOC S3")
SRC = sub(SRC, 'os.path.join(RES, "phase2_results.json"), "w"', 'os.path.join(RES, POSTHOC_OUT + ".json"), "w"')
SRC = sub(SRC, 'os.path.join(RES, "team_season_phase2.csv")', 'os.path.join(RES, POSTHOC_OUT + "_team_season.csv")')
SRC = sub(SRC, 'os.path.join(RES, "team_season_2026_phase2.csv")', 'os.path.join(RES, POSTHOC_OUT + "_team_season_2026.csv")')
if A.extras:  # point values only: stop before the bootstrap, keep the section-4 helpers and the simulation's data-generating fit
    cut = SRC.index("clubs = sorted(T.tid.unique())")
    helpers = SRC[SRC.index("def loso_resid(D, cols, seasons):"): SRC.index("obs_p = PT[")]
    dgp = SRC[SRC.index("Ts = T.sort_values([\"tid\", \"season\"]).reset_index(drop=True)"): SRC.index("RHOS = [")]
    SRC = SRC[:cut] + "\n" + helpers + "\n" + dgp.replace("rng = np.random.default_rng(20261003)", "") + "\n"

# ---- S2: departures from the public transaction feed ---------------------------------------------------------------
LEAVE_FROM = {"TR", "CLW", "R5", "CP", "PUR", "RTN", "LON", "R5M"}   # the club the player leaves is fromTeam
LEAVE_AT = {"REL", "DFA", "RET", "DEC", "DES", "OUT", "WA"}          # the club is fromTeam or toTeam
NS = {"__name__": "phase2_posthoc", "__file__": SRC_PATH, "POSTHOC_OUT": OUTNAME}
DEP, DEP_LOG = {}, {"rows": 0}


def load_departures(P_):
    with open(P_("Sweeper_Injury_Risk/data/txns_live.jsonl")) as fh:
        for line in fh:
            t = json.loads(line); code = t.get("typeCode")
            if code not in LEAVE_FROM and code not in LEAVE_AT:
                continue
            pid = (t.get("person") or {}).get("id")
            if pid is None or not t.get("date"):
                continue
            fr = (t.get("fromTeam") or {}).get("id"); to = (t.get("toTeam") or {}).get("id")
            d = np.datetime64(pd.Timestamp(t["date"]))
            for c in ({fr} if code in LEAVE_FROM else {fr, to}):
                if c is not None:
                    DEP.setdefault((int(pid), int(c)), []).append(d)
            DEP_LOG["rows"] += 1
    for k in list(DEP):
        DEP[k] = np.sort(np.array(DEP[k], dtype="datetime64[ns]"))


def POSTHOC_DEPART(P, col, src):
    if not DEP:
        load_departures(NS["P_"])
    SPAN, RS = NS["SPAN"], NS["ROSTER_SETS"]
    end, src = P[col].copy(), list(src)
    for i, (pid, club, t0, e) in enumerate(zip(P.mlbam, P.club_id, P.il_start, P[col])):
        cand = []
        a = DEP.get((int(pid), int(club)))
        if a is not None:
            j = np.searchsorted(a, np.datetime64(t0), side="right")
            if j < len(a):
                cand.append((pd.Timestamp(a[j]), "departure"))
        y = t0.year
        if y in SPAN and (y + 1, int(club)) in RS and int(pid) not in RS[(y + 1, int(club))]:
            cand.append((SPAN[y][1] + pd.Timedelta(days=1), "absent_next_opening_day_roster"))
        if cand:
            d, why = min(cand)
            if pd.isna(e) or d < e:
                end.iat[i] = d; src[i] = why
    return end, src


NS["POSTHOC_DEPART"] = POSTHOC_DEPART
sys.argv = ["phase2.py", "--out", A.out, "--B", str(A.B), "--nsim", str(A.nsim), "--wcb", str(A.wcb)] + (["--root", A.root] if A.root else [])
exec(compile(SRC, SRC_PATH, "exec"), NS)
RES = NS["RES"]


def flat(d, p=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from flat(v, f"{p}/{k}")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from flat(v, f"{p}[{i}]")
    else:
        yield p, d


def stamp(path, meta):
    J = json.load(open(path))
    J["meta"]["posthoc"] = meta
    json.dump(J, open(path, "w"), indent=1)


META = {"label": "POST HOC, in reply to REVIEWER2_REPORT_PHASE2.md; not preregistered; sealed values unchanged",
        "build": A.build, "substitutions": ["S1 club opener"] + (["S2 departure end", "S3 gate skipped"] if A.build == "departure" else []) + ["S4 output names"]}

if A.full:
    path = os.path.join(RES, OUTNAME + ".json")
    if A.build == "departure":
        S_all_ = NS["S_all"]; S_ = NS["S"]
        META["departure_feed_rows_used"] = DEP_LOG["rows"]
        META["episodes_ended_by_S2_outcome_seasons"] = {k: int(S_[S_.end_rule.str.contains(k)].shape[0]) for k in ("departure", "absent_next_opening_day_roster")}
    stamp(path, META)
    if A.build == "opener":   # the harness must reproduce the sealed run outside the S1-touched values
        sealed = dict(flat(json.load(open(os.path.join(RES, "phase2_results.json")))))
        mine = dict(flat(json.load(open(path))))
        touched = ("/P2_2_reverse_causality/f_inseason_pre_aug1_duration_fixed", "/P2_2_reverse_causality/g_opening_day_vs_in_season",
                   "/P2_2_reverse_causality/range", "/P2_2_reverse_causality/share_war_lost_opening_day_placed", "/meta/runtime_s", "/meta/posthoc")
        diff = [k for k in sealed if not k.startswith(touched) and (k not in mine or (mine[k] != sealed[k] and not (
            isinstance(mine[k], float) and isinstance(sealed[k], float) and abs(mine[k] - sealed[k]) <= 1e-9 * max(1.0, abs(sealed[k])))))]
        print(f"reproduction check: {len(sealed)} sealed values, {len(diff)} differ outside the S1-touched keys")
        for k in diff[:20]:
            print("   ", k, sealed[k], mine.get(k))
        if diff:
            sys.exit(1)
        J = json.load(open(path)); J["meta"]["posthoc"]["reproduction_check"] = {"sealed_values": len(sealed), "differing_outside_S1": 0}
        json.dump(J, open(path, "w"), indent=1)
    print(f"wrote results/{OUTNAME}.json  {time.time() - T0:.0f}s")
    sys.exit(0)

# =====================================================================================================================
# EXTRAS (point analyses on the club-season table T of this build; bootstraps reuse the sealed run's club draws)
# =====================================================================================================================
import statsmodels.api as sm  # noqa: E402
from scipy.stats import beta as _beta  # noqa: E402

g = NS
T, S, S_all, TA, PT = g["T"].copy(), g["S"].copy(), g["S_all"], g["TA"], g["PT"]
SPAN, TEAM_DATES, ROSTER_SETS, PREV_OF = g["SPAN"], g["TEAM_DATES"], g["ROSTER_SETS"], g["PREV_OF"]
OUTCOME, SEASONS_P, PRE_FEATS, SEED = g["OUTCOME"], g["SEASONS_P"], g["PRE_FEATS"], g["SEED"]
ols, loso, icc_mat, sd_within, wins_coef, playoff, logit_fit, sdum, demean_s, q = (g[k] for k in (
    "ols", "loso", "icc_mat", "sd_within", "wins_coef", "playoff", "logit_fit", "sdum", "demean_s", "q"))
rate, games_between, family_v11, res, NAME = g["rate"], g["games_between"], g["family_v11"], g["res"], g["NAME"]
b = PT["P21.b"]; ab = abs(b)
X = {"meta": META, "B": A.B, "seed": SEED}
clubs = sorted(T.tid.unique())
TAKE = np.random.default_rng(SEED).integers(0, len(clubs), (A.B, len(clubs)))   # the sealed run's draws


def cl_fit(D, y, cols, ctrl, logit=False):
    M = D.dropna(subset=[c for c in cols + ctrl + [y] if c in D])
    Xx = pd.concat([M[cols + ctrl], pd.get_dummies(M.season, prefix="s", drop_first=True, dtype=float)], axis=1).astype(float)
    mod = (sm.Logit if logit else sm.OLS)(M[y].astype(float), sm.add_constant(Xx))
    f = mod.fit(disp=0, cov_type="cluster", cov_kwds={"groups": M.tid}) if logit else mod.fit(cov_type="cluster", cov_kwds={"groups": M.tid})
    return {c: {"est": float(f.params[c]), "lo_cluster": float(f.conf_int().loc[c, 0]), "hi_cluster": float(f.conf_int().loc[c, 1])} for c in cols}, int(len(M))


def boot(fn):
    """2.5% and 97.5% quantiles of fn over the sealed run's club draws (draws whose fit fails are dropped and counted)."""
    byclub = {c: T[T.tid == c] for c in clubs}
    vals, bad = [], 0
    for row in TAKE:
        D = pd.concat([byclub[clubs[i]].assign(club_key=j) for j, i in enumerate(row)], ignore_index=True)
        try:
            vals.append(fn(D))
        except Exception:  # noqa: BLE001
            bad += 1
    v = np.array(vals, float)
    return [float(x) for x in np.nanquantile(v, .025, axis=0)], [float(x) for x in np.nanquantile(v, .975, axis=0)], bad


# X0 build summary -----------------------------------------------------------------------------------------------------
X["X0_build"] = {"episodes_outcome_seasons": int(len(S)), "war_lost_total": float(T.war_lost.sum()),
                 "war_lost_mean": float(T.war_lost.mean()), "sd_war_within": float(PT["P21.sd_war"]), "b": b,
                 "one_sd_wins": float(PT["P21.one_sd_wins"]), "p10_p90_wins": float(PT["P21.p10_p90_wins"])}
if A.build == "departure":
    PUB = pd.read_csv(os.path.join(RES, "team_season_public.csv"))
    ended = S[S.end_rule.str.contains("departure|absent_next_opening_day_roster")]
    X["X0_build"].update({"episodes_touched": int(len(ended)),
                          "episodes_touched_by_rule": {k: int(S.end_rule.str.contains(k).sum()) for k in ("departure", "absent_next_opening_day_roster")},
                          "war_lost_removed": float(PUB.war_lost.sum() - T.war_lost.sum()),
                          "war_lost_removed_share": float(1 - T.war_lost.sum() / PUB.war_lost.sum()),
                          "episodes_dropped": int(PUB.stints.sum() - T.stints.sum())})
    T26s = pd.read_csv(os.path.join(RES, "team_season_2026_phase2.csv"))
    T26n = TA[TA.season == 2026]
    X["X0_build"]["war_lost_2026_removed_share"] = float(1 - T26n.war_lost.sum() / T26s.war_lost.sum())

# X1 shutdown-free windows: wins before a date on WAR lost before that date -------------------------------------------
X["X1_windows"] = {}
for cut in ("08-01", "09-01"):
    cd = pd.to_datetime(S.season.astype(str) + "-" + cut)
    gm = [games_between(s, t, a, min(e, c - pd.Timedelta(days=1))) if a < c else 0 for s, t, a, e, c in zip(S.season, S.tid, S.start, S.end, cd)]
    S["_wl_pre"] = S.rate * np.array(gm, float)
    a_ = S.groupby(["season", "tid"])._wl_pre.sum().rename("wl_pre").reset_index()
    r_ = res[res.date < pd.to_datetime(res.season.astype(str) + "-" + cut)].groupby(["season", "tid"]).agg(W_cut=("w", "sum"), G_cut=("w", "size")).reset_index()
    D = T.merge(a_, on=["season", "tid"], how="left").fillna({"wl_pre": 0.0}).merge(r_, on=["season", "tid"], how="left")
    cf, n = cl_fit(D, "W_cut", ["wl_pre"], ["team_proj_od", "W_prev", "G_cut"])
    X["X1_windows"]["before_" + cut] = {**cf["wl_pre"], "n": n, "mean_games": float(D.G_cut.mean()), "mean_war_lost": float(D.wl_pre.mean())}

# X2 design coefficients of this build, the preregistered range set and a post hoc set --------------------------------
DES = g["DESIGNS"]
dco = {}
for nm, (cols, kind) in DES.items():
    ctrl = ["team_proj_od", "W_prev"] + (["W_pre", "G_post"] if kind == "c" else [])
    cf, _ = cl_fit(T, "W_post" if kind == "c" else "W", cols, ctrl)
    for j, c in enumerate(cols):
        dco[f"{nm}.{j}"] = cf[c]
prereg_set = [f"{nm}.{j}" for nm, j in g["RANGE_TERMS"]]
posthoc_set = ["a_primary.0", "b_pre_aug1.0", "d_split_season.0", "f_inseason_pre_aug1_duration_fixed.0", "g_opening_day_vs_in_season.1"]
win = {f"window_{k}": v for k, v in X["X1_windows"].items()}
allc = {**{k: v["est"] for k, v in dco.items()}, **{k: v["est"] for k, v in win.items()}}


def rng_of(keys):
    lo = min(keys, key=lambda k: allc[k]); hi = max(keys, key=lambda k: allc[k])
    return {"most_negative": [lo, allc[lo]], "least_negative": [hi, allc[hi]]}


sdw, wl10, wl90 = PT["P21.sd_war"], q(T, "war_lost", .1), q(T, "war_lost", .9)
X["X2_designs"] = {"coefs": dco, "range_prereg_set": rng_of(prereg_set),
                   "range_posthoc_set": rng_of(posthoc_set + list(win)),
                   "posthoc_set": posthoc_set + list(win),
                   "posthoc_set_rule": "drops (c) and the in-contention term of (e), which condition on contention (selected on the outcome); adds the two windows",
                   "share_war_lost_opening_day_placed": float(S.war_lost[~S.in_season_onset].sum() / S.war_lost.sum())}
for nm in ("range_prereg_set", "range_posthoc_set"):
    rr = X["X2_designs"][nm]; lo_b, hi_b = abs(rr["most_negative"][1]), abs(rr["least_negative"][1])
    X["X2_designs"][nm]["one_sd_wins"] = [sdw * hi_b, sdw * lo_b]
    X["X2_designs"][nm]["p10_p90_wins"] = [(wl90 - wl10) * hi_b, (wl90 - wl10) * lo_b]

# X3 talent controls ---------------------------------------------------------------------------------------------------
X["X3_talent"] = {}
for nm, ctrl in (("none", ["W_prev"]), ("realised_roster", ["team_proj", "W_prev"]), ("opening_day_primary", ["team_proj_od", "W_prev"]),
                 ("opening_day_and_realised", ["team_proj_od", "team_proj", "W_prev"])):
    cf, n = cl_fit(T, "W", ["war_lost"], ctrl)
    X["X3_talent"][nm] = {**cf["war_lost"], "n": n}
cf, _ = cl_fit(T, "W", ["team_proj_od"], ["war_lost", "W_prev"])
X["X3_talent"]["coef_team_proj_od"] = cf["team_proj_od"]


def _ratio(D):
    c = wins_coef(D, ["war_lost", "team_proj_od"], ctrl=("W_prev",))
    return [abs(c[0]) / c[1]]


lo_, hi_, bad = boot(_ratio)
X["X3_talent"]["ratio_abs_b_to_talent_coef"] = {"est": _ratio(T)[0], "ci95_bootstrap": [lo_[0], hi_[0]], "draws_failed": bad}

# X4 foreseeability decomposition ------------------------------------------------------------------------------------
rows = []
for (s, tid), ids in ROSTER_SETS.items():
    if s not in OUTCOME + [2026]:
        continue
    o = TEAM_DATES[(s, tid)][0]
    on = S_all[(S_all.season == s) & (S_all.tid == tid) & (S_all.start <= o) & (S_all.end >= o) & S_all.mlbid.isin(ids)].mlbid.unique()
    rows.append({"season": s, "tid": tid, "od_il_proj": float(sum(max(rate(int(p), s), 0.0) for p in on) * 162), "od_il_n": int(len(on))})
ODIL = pd.DataFrame(rows)
T = T.merge(ODIL, on=["season", "tid"], how="left")
T["share_of_talent"] = T.war_lost / T.team_proj_od
fs = {}
for nm, cols in (("talent", ["team_proj_od"]), ("talent_prev_il_days", ["team_proj_od", "roster_il_days_prev_od"]),
                 ("roster_features", PRE_FEATS), ("all_paper", ["war_lost_prev"] + PRE_FEATS),
                 ("all_plus_od_il", ["war_lost_prev"] + PRE_FEATS + ["od_il_proj"]), ("od_il_only", ["od_il_proj"]),
                 ("V_only", ["V_open_prev"])):
    r2, rr = loso(T, cols, SEASONS_P)
    fs[nm] = {"oos_r2": float(r2), "oos_r2_season_demeaned": float(loso(T, cols, SEASONS_P, demean=True)[0]),
              "sd_unforeseen_war": float(sd_within(T.loc[rr.index].assign(u=rr), "u"))}
    fs[nm]["sd_unforeseen_wins"] = fs[nm]["sd_unforeseen_war"] * ab
fs["share_model_all_paper"] = {"oos_r2": float(loso(T, ["war_lost_prev"] + PRE_FEATS, SEASONS_P, y="share_of_talent")[0])}
_, rr = loso(T, ["war_lost_prev"] + PRE_FEATS + ["od_il_proj"], SEASONS_P)   # persistence of the residual with the opening-day IL feature
Yod = T.loc[rr.index].assign(u=rr).pivot_table(index="tid", columns="season", values="u").to_numpy(float)
Yodc = Yod - Yod.mean(0, keepdims=True); rng_od = np.random.default_rng(SEED + 9)
null_od = np.array([icc_mat(np.column_stack([Yodc[rng_od.permutation(Yod.shape[0]), j] for j in range(Yod.shape[1])])) for _ in range(2000)])
fs["all_plus_od_il"]["icc1"] = float(icc_mat(Yod)); fs["all_plus_od_il"]["p_perm_one_sided"] = float((1 + (null_od >= icc_mat(Yod)).sum()) / 2001)
fs["increment_beyond_talent"] = (fs["all_paper"]["oos_r2"] - fs["talent"]["oos_r2"]) / (1 - fs["talent"]["oos_r2"])
fs["increment_beyond_talent_with_od_il"] = (fs["all_plus_od_il"]["oos_r2"] - fs["talent"]["oos_r2"]) / (1 - fs["talent"]["oos_r2"])
fs["corr_war_lost_team_proj_od_within_season"] = float(demean_s(T, "war_lost").corr(demean_s(T, "team_proj_od")))
fs["od_il_proj_mean"] = float(T.od_il_proj.mean()); fs["od_il_n_mean"] = float(T.od_il_n.mean())
fs["sd_total_war"] = float(sd_within(T[T.season.isin(SEASONS_P)], "war_lost"))
fs["sd_ratio_unforeseen_to_total"] = fs["all_paper"]["sd_unforeseen_war"] / fs["sd_total_war"]
X["X4_foreseeability"] = fs

# X5 the "carry-over" quantity split, and 2021 against 2020 --------------------------------------------------------
last = {s: SPAN[s][1] for s in SPAN}
OPEN = S_all[S_all.end >= S_all.season.map(last)].copy()
OPEN["family"] = OPEN.dx.map(family_v11)
openfam = OPEN.groupby(["mlbid", "season"]).family.agg(lambda f: set(f)).to_dict()
C = S[S.carry & (S.season > 2015)].copy()
C["club_opener"] = [pd.Timestamp(TEAM_DATES[(s, t)][0]) for s, t in zip(C.season, C.tid)]
C["same_family"] = [f in openfam.get((p, PREV_OF[s]), set()) for p, s, f in zip(C.mlbid, C.season, C.family)]
C["by_opener"] = C.first_il_start <= C.club_opener
prevclub = OPEN.groupby(["mlbid", "season"]).tid.agg(lambda t: set(t)).to_dict()
C["same_club"] = [t in prevclub.get((p, PREV_OF[s]), set()) for p, s, t in zip(C.mlbid, C.season, C.tid)]
C["part"] = np.where(C.by_opener & C.same_family, "continuing", np.where(C.same_family, "same_family_later", "other_family"))
tw = C.war_lost.sum()
X5 = {"carry_war_2016_2025": float(tw), "parts_share_of_carry": {k: float(C.war_lost[C.part == k].sum() / tw) for k in ("continuing", "same_family_later", "other_family")},
      "placed_after_club_opener_share": float(C.war_lost[~C.by_opener].sum() / tw), "same_family_share": float(C.war_lost[C.same_family].sum() / tw),
      "same_club_share": float(C.war_lost[C.same_club].sum() / tw)}
for k in ("continuing", "same_family_later", "other_family"):
    T["wl_" + k] = T[["season", "tid"]].merge(C[C.part == k].groupby(["season", "tid"]).war_lost.sum().rename("x").reset_index(), how="left").fillna({"x": 0.0})["x"].to_numpy()
X5["parts_share_of_war_lost"] = {k: float(T["wl_" + k].sum() / T.war_lost.sum()) for k in ("continuing", "same_family_later", "other_family")}


def cov_parts(D):
    M = D.dropna(subset=["war_lost_prev"])
    wp = demean_s(M, "war_lost_prev").to_numpy(); tot = float(np.mean(demean_s(M, "war_lost").to_numpy() * wp))
    return [float(np.mean(demean_s(M, "wl_" + k).to_numpy() * wp)) / tot for k in ("continuing", "same_family_later", "other_family")]


lo_, hi_, bad = boot(cov_parts)
est = cov_parts(T)
X5["parts_share_of_yoy_covariance"] = {k: {"est": est[i], "ci95_bootstrap": [lo_[i], hi_[i]]} for i, k in enumerate(("continuing", "same_family_later", "other_family"))}
open20 = set(zip(OPEN.mlbid[OPEN.season == 2020], OPEN.season[OPEN.season == 2020]))
S21 = S[S.season == 2021]
c21 = S21.war_lost[[(p, 2020) in open20 for p in S21.mlbid]].sum()
X5["season_2021"] = {"reference_2019_share": float(S21.war_lost[S21.carry].sum() / S21.war_lost.sum()), "reference_2020_share": float(c21 / S21.war_lost.sum())}
X["X5_carry_split"] = X5

# X6 persistence of WAR lost net of talent only (no club-history features), 300 club-seasons --------------------------
rngp = np.random.default_rng(SEED + 7)
pers = {}
for nm, col in (("total", "war_lost"), ("carry", "wl_carry"), ("new", "wl_new"), ("continuing", "wl_continuing")):
    M = T.copy()
    Z = np.column_stack([np.ones(len(M)), M.team_proj_od.to_numpy(float), sdum(M.season.to_numpy(), sorted(M.season.unique()))])
    M["r"] = M[col].to_numpy(float) - Z @ np.linalg.lstsq(Z, M[col].to_numpy(float), rcond=None)[0]
    Y = M.pivot_table(index="tid", columns="season", values="r").to_numpy(float)
    obs = icc_mat(Y); Yc = Y - Y.mean(0, keepdims=True); k_, n_ = Y.shape
    null = np.array([icc_mat(np.column_stack([Yc[rngp.permutation(k_), j] for j in range(n_)])) for _ in range(4000)])
    Md = M.sort_values(["tid", "season"]); Md["r_prev"] = Md.groupby("tid").r.shift(1)
    m = Md.r_prev.notna()
    sdr = float(sd_within(M, "r"))
    pers[nm] = {"icc1": obs, "p_perm_one_sided": float((1 + (null >= obs).sum()) / 4001), "null_q95": float(np.quantile(null, .95)),
                "yoy_r": float(np.corrcoef(Md.r[m], Md.r_prev[m])[0, 1]), "sd_within_war": sdr,
                "club_sd_war": float(np.sqrt(max(obs, 0.0)) * sdr), "club_sd_wins": float(np.sqrt(max(obs, 0.0)) * sdr * ab)}
X["X6_persistence_net_of_talent"] = {**pers, "residualised_on": "team_proj_od + season effects (in-sample OLS), 10 outcome seasons, 4,000 within-season permutations",
                                     "n_club_seasons": int(len(T))}

# X7 simulation: upper bound for the club effect (inverted), primary residual; opener build only ------------------------
if A.build == "opener":
    obs_p = PT["P25.icc_primary"]
    rs = np.random.default_rng(20261005)
    Ts, fit_s, e_s, sig, idx_by_season, cl_arr, ucl = (g[k] for k in ("Ts", "fit_s", "e_s", "sig", "idx_by_season", "cl_arr", "ucl"))
    inv = {}
    for rho in (0.02, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10):
        vals = []
        for _ in range(A.nsim_inv):
            eps = np.empty(len(e_s))
            for s, ix in idx_by_season.items():
                eps[ix] = rs.permutation(e_s[ix])
            u = dict(zip(ucl, rs.standard_normal(len(ucl))))
            Dm = Ts[["season", "tid"] + PRE_FEATS].copy()
            Dm["war_lost"] = fit_s + np.sqrt(1 - rho) * eps + np.sqrt(rho) * sig * np.array([u[c] for c in cl_arr])
            Dm["war_lost_prev"] = Dm.groupby("tid").war_lost.shift(1)
            vals.append(icc_mat(g["mat"](g["loso_resid"](Dm, ["war_lost_prev"] + PRE_FEATS, SEASONS_P), "u")))
        vals = np.array(vals)
        inv[str(rho)] = {"share_at_or_below_observed": float((vals <= obs_p).mean()), "mean_observed_scale_icc": float(vals.mean()), "panels": A.nsim_inv}
    grid = sorted(float(r) for r in inv)
    ub = None
    for r0, r1 in zip(grid, grid[1:]):
        s0, s1 = inv[str(r0)]["share_at_or_below_observed"], inv[str(r1)]["share_at_or_below_observed"]
        if s0 > .05 >= s1:
            ub = r0 + (s0 - .05) * (r1 - r0) / (s0 - s1); break
    ty = g["J_SEALED"] if "J_SEALED" in g else json.load(open(os.path.join(RES, "phase2_results.json")))
    t1 = ty["P2_5_persistence"]["simulation"]["rho"]["0.0"]
    k1 = round(t1["power_primary_permutation_test"] * t1["n_panels_with_permutation_test"]); n1 = t1["n_panels_with_permutation_test"]
    X["X7_simulation_inverted"] = {"observed_icc": obs_p, "grid": inv, "rho_upper_95": ub, "sigma_within_season_war": float(sig),
                                   "club_sd_wins_at_upper": (float(np.sqrt(ub) * sig * ab) if ub else None),
                                   "rho_definition": "share of the within-season variance of WAR lost (given the preseason features) that is a fixed club effect in the data-generating model; the reported ICC(1) of the out-of-sample residual is on a smaller scale (mean_observed_scale_icc)",
                                   "type1_permutation": {"rejections": int(k1), "panels": int(n1), "ci95_clopper_pearson": [float(_beta.ppf(.025, k1, n1 - k1 + 1)) if k1 else 0.0, float(_beta.ppf(.975, k1 + 1, n1 - k1))]},
                                   "seed": 20261005}

# X8 conditional percentiles at the median projection; playoff model with W_prev ------------------------------------
pm = float(T.team_proj_od.median())


def cond(D):
    lv = sorted(D.season.unique())
    Z = np.column_stack([np.ones(len(D)), D.team_proj_od.to_numpy(float), sdum(D.season.to_numpy(), lv)])
    bb = np.linalg.lstsq(Z, D.war_lost.to_numpy(float), rcond=None)[0]
    r = D.war_lost.to_numpy(float) - Z @ bb
    base = float(np.mean([bb[0] + bb[1] * pm + (bb[1 + lv.index(s)] if lv.index(s) > 0 else 0.0) for s in lv]))
    c10, c50, c90 = (base + float(np.quantile(r, qq)) for qq in (.1, .5, .9))
    pp = playoff(D, at=[c10, c50, c90], pm=pm)
    bw = abs(float(wins_coef(D, ["war_lost"])[0]))
    return [c10, c50, c90, (c90 - c10) * bw, (c90 - c50), (c90 - c50) * bw, pp["p"][0], pp["p"][1], pp["p"][2], pp["p"][0] - pp["p"][2]]


est = cond(T); lo_, hi_, bad = boot(cond)
names = ["war_p10", "war_p50", "war_p90", "p10_p90_wins", "reserve_war", "reserve_wins", "p_playoffs_p10", "p_playoffs_p50", "p_playoffs_p90", "drop"]
X["X8_conditional"] = {n_: {"est": est[i], "ci95_bootstrap": [lo_[i], hi_[i]]} for i, n_ in enumerate(names)}
X["X8_conditional"]["median_projection"] = pm; X["X8_conditional"]["draws_failed"] = bad
cf, n = cl_fit(T, "q", ["war_lost"], ["team_proj_od", "W_prev"], logit=True)
X["X8_conditional"]["playoff_with_W_prev"] = {"logit_slope": cf["war_lost"], "n": n}
X["X8_conditional"]["playoff_primary_logit_slope"] = float(np.log(PT["P21.or"]))

# X9 the opening-day control: leakage, rookies, the zero floor, opening-day players against later acquisitions -------
ROS = g["ROSTER"].copy()
JOIN = {"TR", "CLW", "SFA", "SGN", "R5", "CP", "PUR", "RTN", "ACQ", "OBT"}
mlb = set(ROS.club_id.unique()); joins = {}
with open(g["P_"]("Sweeper_Injury_Risk/data/txns_live.jsonl")) as fh:
    for line in fh:
        t = json.loads(line)
        if t.get("typeCode") in JOIN:
            to = (t.get("toTeam") or {}).get("id"); pid = (t.get("person") or {}).get("id")
            if to in mlb and pid is not None and t.get("date"):
                joins.setdefault(int(pid), []).append((pd.Timestamp(t["date"]), int(to)))
leak = 0
for s_, c_, d_, p_ in zip(ROS.season, ROS.club_id, pd.to_datetime(ROS.roster_date), ROS.mlbam):
    js = sorted(joins.get(int(p_), []))
    before = [j for j in js if j[0] <= d_]
    after = [j for j in js if d_ < j[0] <= d_ + pd.Timedelta(days=14) and j[1] == c_]
    if before and before[-1][1] != c_ and after:
        leak += 1
Wd = g["Wd"]
nodata = [all((int(p_), s_ - k) not in Wd for k in (1, 2, 3)) for s_, p_ in zip(ROS.season, ROS.mlbam)]
rv = np.array([rate(int(p_), s_) for s_, p_ in zip(ROS.season, ROS.mlbam)])
ROS["neg"] = rv < 0; ROS["neg_war"] = np.minimum(rv, 0) * 162; ROS["nodata"] = nodata; ROS["rate"] = rv
nf = ROS.groupby(["season", "club_id"]).apply(lambda d: float(d.rate.sum() * 162), include_groups=False).rename("team_proj_od_nofloor").reset_index().rename(columns={"club_id": "tid"})
T = T.merge(nf, on=["season", "tid"], how="left")
cf, n = cl_fit(T, "W", ["war_lost"], ["team_proj_od_nofloor", "W_prev"])
S["on_od_roster"] = [int(p) in ROSTER_SETS.get((s, t), set()) for p, s, t in zip(S.mlbid, S.season, S.tid)]
for k, m in (("wl_od_roster", S.on_od_roster), ("wl_acquired", ~S.on_od_roster)):
    T[k] = T[["season", "tid"]].merge(S[m].groupby(["season", "tid"]).war_lost.sum().rename("x").reset_index(), how="left").fillna({"x": 0.0})["x"].to_numpy()
cf2, _ = cl_fit(T, "W", ["wl_od_roster", "wl_acquired"], ["team_proj_od", "W_prev"])
X["X9_control"] = {"roster_rows": int(len(ROS)), "leak_candidates": int(leak),
                   "share_rows_no_fwar_prior3": float(np.mean(nodata)), "share_rows_negative_rate": float(ROS.neg.mean()),
                   "negative_war_per_club_mean": float(ROS[ROS.season.isin(OUTCOME)].groupby(["season", "club_id"]).neg_war.sum().mean()),
                   "no_floor": {**cf["war_lost"], "one_sd_wins": float(PT["P21.sd_war"] * abs(cf["war_lost"]["est"])), "n": n},
                   "split_by_opening_day_roster": {**cf2, "acquired_share_of_war_lost": float(T.wl_acquired.sum() / T.war_lost.sum())}}

# X10 projection variants: rank agreement --------------------------------------------------------------------------
X["X10_projection"] = {}
for v in ("K50", "K200", "AGE"):
    rho_s = [T[T.season == s][["war_lost", f"war_lost_{v}"]].corr(method="spearman").iloc[0, 1] for s in OUTCOME]
    X["X10_projection"][v] = {"spearman_within_season_mean": float(np.mean(rho_s)), "spearman_within_season_min": float(np.min(rho_s)),
                              "sd_war": float(sd_within(T, f"war_lost_{v}"))}

# X11 the 2026 check: interval, single-season series, leverage ----------------------------------------------------
TR_ = T[T.season.isin(SEASONS_P)]
T26 = TA[TA.season == 2026].merge(T[T.season == 2025][["tid", "war_lost"]].rename(columns={"war_lost": "war_lost_prev"}), on="tid", how="left")
cols = ["war_lost_prev"] + PRE_FEATS
bb = ols(TR_.war_lost.to_numpy(float), TR_[cols].to_numpy(float))
pred = bb[0] + T26[cols].to_numpy(float) @ bb[1:]; yv = T26.war_lost.to_numpy(float); mu = TR_.war_lost.mean()
r2_26 = 1 - ((yv - pred) ** 2).sum() / ((yv - mu) ** 2).sum()
bs26 = []
for row in TAKE:
    yy, pp_ = yv[row], pred[row]
    bs26.append(1 - ((yy - pp_) ** 2).sum() / ((yy - mu) ** 2).sum())
loco = [1 - ((np.delete(yv, i) - np.delete(pred, i)) ** 2).sum() / ((np.delete(yv, i) - mu) ** 2).sum() for i in range(len(yv))]
e2 = np.sort((yv - pred) ** 2)[::-1]
single = {}
for s in SEASONS_P:
    tr = T[T.season.isin([x for x in SEASONS_P if x != s])]; te = T[T.season == s]
    b2 = ols(tr.war_lost.to_numpy(float), tr[cols].to_numpy(float)); p2 = b2[0] + te[cols].to_numpy(float) @ b2[1:]
    single[str(s)] = float(1 - ((te.war_lost - p2) ** 2).sum() / ((te.war_lost - tr.war_lost.mean()) ** 2).sum())
X["X11_check_2026"] = {"oos_r2_2026": float(r2_26), "ci95_bootstrap_clubs": [float(np.quantile(bs26, .025)), float(np.quantile(bs26, .975))],
                       "leave_one_club_out_range": [float(min(loco)), float(max(loco))], "top5_share_of_sse": float(e2[:5].sum() / e2.sum()),
                       "single_season_loso_r2": single, "mean_2026": float(yv.mean()), "mean_training": float(mu), "mean_predicted": float(pred.mean())}

# X12 stress test: WAR lost from episodes still open on the final day removed -------------------------------------
T["wl_closed"] = T[["season", "tid"]].merge(S[~S.il_open_final_day].groupby(["season", "tid"]).war_lost.sum().rename("x").reset_index(), how="left").fillna({"x": 0.0})["x"].to_numpy()
cf, n = cl_fit(T, "W", ["wl_closed"], ["team_proj_od", "W_prev"])
X["X12_open_final_day_removed"] = {**cf["wl_closed"], "n": n, "sd_war": float(sd_within(T, "wl_closed")),
                                   "one_sd_wins": float(sd_within(T, "wl_closed") * abs(cf["wl_closed"]["est"])),
                                   "share_war_lost_open_final_day": float(S.war_lost[S.il_open_final_day].sum() / S.war_lost.sum())}

# X13 carry-over visibility, season-demeaned --------------------------------------------------------------------------
M = T.dropna(subset=["war_lost_prev"])
S27 = sorted(M.season.unique())
X["X13_visibility"] = {"C_on_V_loso_r2": float(loso(M, ["V_open_prev"], S27, y="wl_carry")[0]),
                       "C_on_V_loso_r2_season_demeaned": float(loso(M, ["V_open_prev"], S27, y="wl_carry", demean=True)[0]),
                       "C_on_V_loso_r2_without_2021": float(loso(M[M.season != 2021], ["V_open_prev"], [s for s in S27 if s != 2021], y="wl_carry")[0])}

# X14 depth: does opening-day depth change the wins association? ----------------------------------------------------
drow = []
for (s, tid), ids in ROSTER_SETS.items():
    if s in OUTCOME:
        pr = np.sort(np.array([max(rate(int(p), s), 0.0) * 162 for p in ids]))[::-1]
        drow.append({"season": s, "tid": tid, "depth_od": float(pr[26:].sum())})
T = T.merge(pd.DataFrame(drow), on=["season", "tid"], how="left")
T["wl_c"] = T.war_lost - T.war_lost.mean(); T["depth_c"] = T.depth_od - T.depth_od.mean(); T["wl_x_depth"] = T.wl_c * T.depth_c
cf, n = cl_fit(T, "W", ["wl_c", "depth_c", "wl_x_depth"], ["team_proj_od", "W_prev"])
X["X14_depth"] = {**cf, "n": n, "depth_mean_war": float(T.depth_od.mean()), "depth_sd_war": float(T.depth_od.std()),
                  "definition": "projected WAR (rate x 162, floored at 0) of opening-day 40-man players outside the top 26 by projection"}

# X15 variance shares for the comparators ----------------------------------------------------------------------------
P1 = json.load(open(os.path.join(RES, "phase1b_results.json")))["R5_comparators"]
vw = float(T.groupby("season").W.var().mean())
X["X15_variance"] = {"var_wins_within_season": vw, "sd_wins_within_season": float(np.sqrt(vw)),
                     "share": {"injury_all": float(PT["P21.one_sd_wins"] ** 2 / vw), "injury_unforeseen": float(PT["P21.sd_unexp_wins"] ** 2 / vw),
                               "binomial": float(P1["binomial_sd_wins_500_team_162"] ** 2 / vw), "pythagorean": float(P1["pythagorean_residual_sd_wins"] ** 2 / vw)}}

# X16 small items ----------------------------------------------------------------------------------------------------
J2 = json.load(open(os.path.join(RES, "phase2_results.json")))
mde = J2["P2_5_persistence"]["simulation"]["calibrated"]["icc_at_80pct_power_primary"]
X["X16_misc"] = {"mde_club_sd_wins": float(np.sqrt(mde) * PT["P21.sd_unexp_war"] * ab)}

X["meta"]["runtime_s"] = round(time.time() - T0, 1)
json.dump(X, open(os.path.join(RES, OUTNAME + ".json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print(f"wrote results/{OUTNAME}.json  {time.time() - T0:.0f}s")
