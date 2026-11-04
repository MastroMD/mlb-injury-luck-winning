"""
posthoc_r5.py - the projected WAR on the injured list at Opening Day (post hoc, 2026-11-04; DEVIATIONS #31). Not part of any
sealed plan.

Builds the episodes, the Marcel projection and the club-season table with phase2.py's own code (its source is executed up
to the rule-A build, so nothing is re-implemented), then, for each opening-day 40-man roster player:
  on the IL at Opening Day   = an episode at his opening-day club that covers the club's first regular-season game, the
                               definition of the X4 feature of phase2_posthoc_r2.py (whose R² this script reproduces); a
                               stricter sensitivity requires the first placement, at any club, to be dated and announced by
                               that game, with first games from --schedule;
  carry-over                 = an episode open on the final regular-season day of the previous outcome season (2019 for
                               2021), as in phase2.py's V_open_prev.
Club-season quantities: V_od = projected WAR (Marcel rate x 162, positive part) of opening-day roster players on the IL at
Opening Day; the carry-over projected WAR split into players on the IL at Opening Day and players healthy then, with the WAR
the club lost to each group. Reported: leave-one-season-out R² of WAR lost on the four declared features with and without
V_od (the P2.1 procedure, 2016-2019 and 2022-2025), by season and pooled, with a club-bootstrap interval for the gain; the
2026 check (fitted on those eight seasons); the V_od coefficient (club-clustered); the carry-over split slopes; the primary
wins model with WAR lost split into the part from players on the IL at Opening Day and the rest. With --projections, the
wins model is refitted with an external projection as the talent control (alone, beside the primary control, and with WAR
lost split), and the external projection is regressed on the primary control and V_od.

The strict sensitivity takes club first-game dates from --schedule (default: the pipeline's games_flat.csv); the paper's
sensitivity uses the corrected schedule from fetch_inputs.py, because the pinned schedule lacks some clubs' postponed openers.

The paper's file results/posthoc_r5_2026-11-04.json was written in the work folder of the fresh-pull rerun (rerun_variant.py
on fetch_inputs.py --emulate-pinned), with --schedule pointing at the corrected schedule and --projections at the reader's
Steamer and ZiPS sums. On those rebuilt inputs its R² values differ from the X4 values of results/ by less than 0.001,
because a few birth dates differ.

usage: python3 pipeline/posthoc_r5.py [--schedule <games_flat.csv>] [--projections <csv>] [--out results/posthoc_r5_2026-11-04.json]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
ap = argparse.ArgumentParser()
ap.add_argument("--schedule", default=None)
ap.add_argument("--out", default=os.path.join(REPO, "results", "posthoc_r5_2026-11-04.json"))
ap.add_argument("--B", type=int, default=2000)
ap.add_argument("--projections", default=None, help="optional CSV season,club_id,steamer_pos,zips_pos: external preseason projections summed over "
                "each opening-day 40-man roster (licensed data the reader exports; not shipped)")
A = ap.parse_args()

SRC_PATH = os.path.join(HERE, "phase2.py")
SRC = open(SRC_PATH, encoding="utf-8").read()
MARK = 'S, TA = club_table(S_all, Wd, variants=("K100", "K50", "K200", "AGE"))\n'
if SRC.count(MARK) != 1:
    sys.exit("phase2.py build anchor not found")
SRC = SRC[:SRC.index(MARK) + len(MARK)]
NS = {"__name__": "phase2_build", "__file__": SRC_PATH}
argv0 = sys.argv; sys.argv = [SRC_PATH]
exec(compile(SRC, SRC_PATH, "exec"), NS)
sys.argv = argv0
S_all, Wd, TA, SPAN, PREV_OF, P_, OUTCOME, SEASONS_P = (NS[k] for k in ("S_all", "Wd", "TA", "SPAN", "PREV_OF", "P_", "OUTCOME", "SEASONS_P"))
rate = NS["make_rate"](Wd)
PRE = ["war_lost_prev", "team_proj_od", "roster_age_od", "roster_il_days_prev_od"]

# ---- club first-game dates, placement dates ------------------------------------------------------------------------
G = pd.read_csv(A.schedule or P_("Postseason_Injury_Risk/data/games_flat.csv"))
G = G[(G.gameType == "R") & G.status.isin(["Final", "Completed Early"])].copy(); G["date"] = pd.to_datetime(G.date)
FIRST = pd.concat([G[["season", "date", "home_id"]].rename(columns={"home_id": "tid"}),
                   G[["season", "date", "away_id"]].rename(columns={"away_id": "tid"})]).groupby(["season", "tid"]).date.min().to_dict()
PL = pd.read_csv(P_("Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv"))
TXD = pd.to_datetime(PL.set_index("txn_id").date).to_dict()
E = S_all.copy()
E["first_il_start"] = pd.to_datetime(E.first_il_start); E["end"] = pd.to_datetime(E.end)
E["txn_date"] = E.first_txn_id.map(TXD)
last = {s: SPAN[s][1] for s in SPAN}
open_set = set(zip(E.loc[E.end >= E.season.map(last), "mlbid"], E.loc[E.end >= E.season.map(last), "season"]))
gm_club = E.groupby(["mlbid", "season", "tid"]).games_missed.sum().to_dict()

# ---- opening-day roster players -------------------------------------------------------------------------------------
R = pd.read_csv(P_(NS["ROSTER_KEY"])).drop_duplicates(["season", "club_id", "mlbam"])
R = R[R.season.isin(OUTCOME + [2026])].copy()
ep = {k: g for k, g in E.groupby(["mlbid", "season"])}
TD = NS["TEAM_DATES"]
E["start"] = pd.to_datetime(E.start)
cover = set()
for (s_, t_), g_ in E.groupby(["season", "tid"]):
    if (s_, t_) in TD:
        o_ = pd.Timestamp(TD[(s_, t_)][0]); cover |= {(int(m), s_, t_) for m in g_.mlbid[(g_.start <= o_) & (g_.end >= o_)]}
od, strict, carry, proj, wl = [], [], [], [], []
for p, s, c in zip(R.mlbam, R.season, R.club_id):
    g = ep.get((p, s)); fd = FIRST.get((s, c))
    od.append((int(p), s, c) in cover)
    strict.append(bool(g is not None and fd is not None and ((g.first_il_start <= fd) & (g.txn_date <= fd)).any()))
    carry.append((p, PREV_OF[s]) in open_set)
    r_ = max(rate(p, s), 0.0); proj.append(r_ * 162); wl.append(r_ * gm_club.get((p, s, c), 0))
R["od_il"], R["od_strict"], R["carry"], R["proj"], R["wl_club"] = od, strict, carry, proj, wl
R["V_od"] = R.proj * R.od_il; R["V_od_strict"] = R.proj * R.od_strict
R["wl_od"] = R.wl_club * R.od_il; R["wl_not_od"] = R.wl_club * ~R.od_il
for nm, m in (("carry_od", R.carry & R.od_il), ("carry_healthy", R.carry & ~R.od_il), ("other", ~R.carry)):
    R[f"V_{nm}"] = R.proj * m; R[f"wl_{nm}"] = R.wl_club * m
CLUB = R.groupby(["season", "club_id"])[["V_od", "V_od_strict", "wl_od", "V_carry_od", "V_carry_healthy", "V_other", "wl_carry_od", "wl_carry_healthy", "wl_other"]].sum()
CLUB = CLUB.reset_index().rename(columns={"club_id": "tid"})
T = pd.read_csv(os.path.join(REPO, "results", "team_season_phase2.csv")).merge(CLUB, on=["season", "tid"], how="left")
T26 = TA[TA.season == 2026].merge(T[T.season == 2025][["tid", "war_lost"]].rename(columns={"war_lost": "war_lost_prev"}), on="tid").merge(CLUB, on=["season", "tid"])


def ols(y, X):
    return np.linalg.lstsq(np.column_stack([np.ones(len(y)), X]), y, rcond=None)[0]


def loso(D, cols):
    M = D[D.season.isin(SEASONS_P)]; y = M.war_lost.to_numpy(float); X = M[cols].to_numpy(float); ss = M.season.to_numpy()
    pred = np.empty(len(y)); m0 = np.empty(len(y)); per = {}
    for s in SEASONS_P:
        te = ss == s; b = ols(y[~te], X[~te]); pred[te] = b[0] + X[te] @ b[1:]; m0[te] = y[~te].mean()
        per[int(s)] = float(1 - ((y[te] - pred[te]) ** 2).sum() / ((y[te] - m0[te]) ** 2).sum())
    return float(1 - ((y - pred) ** 2).sum() / ((y - m0) ** 2).sum()), per, M.tid.to_numpy(), y, pred, m0


r2_d, per_d, tid, y, pd_, m0 = loso(T, PRE)
r2_v, per_v, _, _, pv_, _ = loso(T, PRE + ["V_od"])
r2_o, per_o, _, _, _, _ = loso(T, ["V_od"])
r2_s, _, _, _, _, _ = loso(T, PRE + ["V_od_strict"]); r2_so, _, _, _, _, _ = loso(T, ["V_od_strict"])
X4 = json.load(open(os.path.join(REPO, "results", "phase2_posthoc_opener_extras.json")))["X4_foreseeability"]
rng = np.random.default_rng(20261104); clubs = np.unique(tid); gains = []
for _ in range(A.B):
    idx = np.concatenate([np.flatnonzero(tid == c) for c in rng.choice(clubs, len(clubs))])
    r2 = lambda p: 1 - ((y[idx] - p[idx]) ** 2).sum() / ((y[idx] - m0[idx]) ** 2).sum()  # noqa: E731
    gains.append(r2(pv_) - r2(pd_))
TR = T[T.season.isin(SEASONS_P)]


def r2_2026(cols):
    b = ols(TR.war_lost.to_numpy(float), TR[cols].to_numpy(float)); p = b[0] + T26[cols].to_numpy(float) @ b[1:]
    return float(1 - ((T26.war_lost - p) ** 2).sum() / ((T26.war_lost - TR.war_lost.mean()) ** 2).sum())


f = sm.OLS(TR.war_lost, sm.add_constant(TR[PRE + ["V_od"]].astype(float))).fit(cov_type="cluster", cov_kwds={"groups": TR.tid})
ci = f.conf_int()
D = T[T.season.isin(OUTCOME) & T.W_prev.notna()]


def slope(yc, xc):
    m = sm.OLS(D[yc], sm.add_constant(D[[xc]].astype(float))).fit(cov_type="cluster", cov_kwds={"groups": D.tid})
    return {"slope": float(m.params[xc]), "lo": float(m.conf_int().loc[xc, 0]), "hi": float(m.conf_int().loc[xc, 1]), "x_mean_war": float(D[xc].mean())}


M27 = D.dropna(subset=["war_lost_prev"])   # the P2.7 sample: wl_carry on the two parts of V_open_prev, jointly
fj = sm.OLS(M27.wl_carry, sm.add_constant(M27[["V_carry_od", "V_carry_healthy"]].astype(float))).fit(cov_type="cluster", cov_kwds={"groups": M27.tid})
f1 = sm.OLS(M27.wl_carry, sm.add_constant(M27[["V_open_prev"]].astype(float))).fit()
JOINT = {k: {"slope": float(fj.params[k]), "lo": float(fj.conf_int().loc[k, 0]), "hi": float(fj.conf_int().loc[k, 1])} for k in ("V_carry_od", "V_carry_healthy")}
JOINT["single_slope_reproduced"] = float(f1.params["V_open_prev"]); JOINT["V_parts_sum_equals_V_open_prev_maxdiff"] = float((M27.V_carry_od + M27.V_carry_healthy - M27.V_open_prev).abs().max())
RO = R[R.season.isin(OUTCOME)]
out = {"label": "post hoc (2026-11-04), DEVIATIONS #31; projected WAR on the IL at Opening Day",
       "schedule_for_first_games": os.path.basename(A.schedule) if A.schedule else "pipeline games_flat.csv",
       "n_club_seasons_loso": int(T.season.isin(SEASONS_P).sum()),
       "loso_r2": {"declared": r2_d, "declared_plus_V_od": r2_v, "V_od_only": r2_o,
                   "gain_ci95_club_bootstrap": [float(np.quantile(gains, .025)), float(np.quantile(gains, .975))], "B": A.B},
       "reproduces_X4": {"declared_plus_V_od_X4": X4["all_plus_od_il"]["oos_r2"], "V_od_only_X4": X4["od_il_only"]["oos_r2"],
                         "max_abs_diff": max(abs(r2_v - X4["all_plus_od_il"]["oos_r2"]), abs(r2_o - X4["od_il_only"]["oos_r2"]))},
       "strict_sensitivity": {"declared_plus_V_od": r2_s, "V_od_only": r2_so, "check_2026_declared_plus_V_od": r2_2026(PRE + ["V_od_strict"]),
                              "rule": "first placement, at any club, dated and announced by the club's first game in --schedule"},
       "by_season": [{"season": s, "declared": per_d[s], "declared_plus_V_od": per_v[s], "V_od_only": per_o[s]} for s in per_d],
       "check_2026": {"declared": r2_2026(PRE), "declared_plus_V_od": r2_2026(PRE + ["V_od"]), "V_od_only": r2_2026(["V_od"])},
       "V_od_coefficient": {"est": float(f.params["V_od"]), "lo_cluster": float(ci.loc["V_od", 0]), "hi_cluster": float(ci.loc["V_od", 1]),
                            "p": float(f.pvalues["V_od"])},
       "V_od_war": {"mean": float(TR.V_od.mean()), "sd": float(TR.V_od.std()), "corr_with_war_lost": float(TR[["V_od", "war_lost"]].corr().iloc[0, 1])},
       "carry_over_split": {"on_il_at_opening_day": slope("wl_carry_od", "V_carry_od"), "healthy_at_opening_day": slope("wl_carry_healthy", "V_carry_healthy"),
                            "other_roster_players": slope("wl_other", "V_other"),
                            "share_of_carry_projected_war_on_il_at_od": float(D.V_carry_od.sum() / (D.V_carry_od.sum() + D.V_carry_healthy.sum())),
                            "share_of_carry_war_lost_on_il_at_od": float(D.wl_carry_od.sum() / (D.wl_carry_od.sum() + D.wl_carry_healthy.sum())),
                            "n_club_seasons": int(len(D)), "paper_carry_on_parts_jointly": JOINT},
       "player_seasons": {"opening_day_roster": int(len(RO)), "on_il_at_opening_day": int(RO.od_il.sum()), "carry_over": int(RO.carry.sum()),
                          "carry_over_on_il_at_od": int((RO.carry & RO.od_il).sum()),
                          "ratio_war_lost_to_projected": {"carry_od": float(RO.wl_carry_od.sum() / RO.V_carry_od.sum()),
                                                          "carry_healthy": float(RO.wl_carry_healthy.sum() / RO.V_carry_healthy.sum()),
                                                          "other": float(RO.wl_other.sum() / RO.V_other.sum())}}}
# wins model split by Opening Day status: WAR lost by roster players on the IL at Opening Day, and the rest of the club's WAR lost
W = T[T.W_prev.notna()].copy(); W["wl_rest"] = W.war_lost - W.wl_od


def wins(cols, ctrl, D_):
    import statsmodels.formula.api as smf
    m = smf.ols("W ~ " + " + ".join(cols + [ctrl, "W_prev", "C(season)"]), D_).fit(cov_type="cluster", cov_kwds={"groups": D_.tid})
    return {k: {"est": float(m.params[k]), "lo": float(m.conf_int().loc[k, 0]), "hi": float(m.conf_int().loc[k, 1]), "p": float(m.pvalues[k])} for k in cols + [ctrl]}


out["wins_split_by_opening_day"] = {"team_proj_od": wins(["wl_od", "wl_rest"], "team_proj_od", W), "n": int(len(W)),
                                    "wl_od_share_of_war_lost": float(W.wl_od.sum() / W.war_lost.sum())}
if A.projections:
    import statsmodels.formula.api as smf
    PJ = pd.read_csv(A.projections).rename(columns={"club_id": "tid"})
    WJ = W.merge(PJ[["season", "tid", "steamer_pos", "zips_pos"]], on=["season", "tid"])
    TJ = T[T.season.isin(OUTCOME)].merge(PJ[["season", "tid", "steamer_pos", "zips_pos"]], on=["season", "tid"])
    pc = {"n": int(len(WJ))}
    for ctrl in ("steamer_pos", "zips_pos"):
        pc[ctrl] = {"wins": wins(["war_lost"], ctrl, WJ), "wins_split": wins(["wl_od", "wl_rest"], ctrl, WJ),
                    "wins_with_both_controls": wins(["war_lost", "team_proj_od"], ctrl, WJ)}
        m = smf.ols(f"{ctrl} ~ team_proj_od + V_od + C(season)", TJ).fit(cov_type="cluster", cov_kwds={"groups": TJ.tid})
        pc[ctrl]["control_on_marcel_and_V_od"] = {k: {"est": float(m.params[k]), "lo": float(m.conf_int().loc[k, 0]), "hi": float(m.conf_int().loc[k, 1])}
                                                  for k in ("team_proj_od", "V_od")}
        dm = lambda x: x - TJ.groupby("season")[x.name].transform("mean")  # noqa: E731
        pc[ctrl]["corr_with_team_proj_od_within_season"] = float(dm(TJ.team_proj_od).corr(dm(TJ[ctrl])))
    out["projection_controls"] = pc
json.dump(out, open(A.out, "w"), indent=1)
print(json.dumps({k: out[k] for k in ("loso_r2", "check_2026", "V_od_coefficient", "carry_over_split")}, indent=1))
