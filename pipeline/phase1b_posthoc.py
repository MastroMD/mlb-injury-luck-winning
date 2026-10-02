"""
phase1b_posthoc.py — Phase 1b (answer to REVIEWER2_REPORT.md): post hoc analyses on the R1-repaired build.

EVERYTHING IN THIS FILE IS POST HOC AND EXPLORATORY: it was written after the Phase 1 output and the reviewer's
output had been seen (DEVIATIONS.md #10-#16). It never replaces a preregistered estimate.

Reads results/injury_luck_results.json (R1-repaired primary), results/injury_luck_results_sealed.json (as sealed),
results/team_season_public.csv, results/stints_public_2015_2025.csv, the pinned public inputs, and two scratch tables
written by injury_luck.py --dump-dir (player-season exposure with fWAR, and all 2012-2025 episodes; never published),
plus an optional COVID-blank sensitivity run (injury_luck.py --keep-covid-era-blanks).
Writes results/phase1b_results.json.

  R2  preseason talent control (fallback: organisation roster on opening day from the public transaction feed)
  R3  reviewer designs: (a) in-season onsets before 1 August with durations fixed at the family median;
      (b) contention split; (c) opening-day-placed vs in-season; one range statement for wins per WAR lost
  R4  E11 simulation-calibrated null and power; carry-over decomposition
  R5  like-for-like luck comparators from public schedule results
  R6  BCa intervals; P(playoffs) by format era; COVID-blank and suspension sensitivities

Usage (from the repository root): python3 pipeline/injury_luck.py --dump-dir scratch/ ; then
  python3 pipeline/phase1b_posthoc.py --dump scratch/ [--covid <results json of injury_luck.py --keep-covid-era-blanks>]
(scratch/ holds fWAR-derived tables: never commit it.)
"""
import argparse
import json
import os
import re

import warnings
# log hygiene (2026-10-02): warnings print the script base name only, never an absolute path
warnings.formatwarning = lambda msg, cat, fname, lineno, line=None: f"{cat.__name__}: {msg} [{os.path.basename(str(fname))}:{lineno}]\n"
import numpy as np
import pandas as pd
import statsmodels.api as sm
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ap.add_argument("--dump", required=True)
ap.add_argument("--covid", default=None)
ap.add_argument("--nsim", type=int, default=1000)
args = ap.parse_args()
RES = os.path.join(args.out, "results")
P_ = paths.resolve
SEED = 20260930
OUTCOME = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
SP = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
RF = ["team_proj", "roster_age_w", "roster_il_days_prev_w"]
R = json.load(open(os.path.join(RES, "injury_luck_results.json")))
RS = json.load(open(os.path.join(RES, "injury_luck_results_sealed.json")))
assert R["meta"]["episode_rule"] == "r1"
T = pd.read_csv(os.path.join(RES, "team_season_public.csv")).sort_values(["tid", "season"]).reset_index(drop=True)
S = pd.read_csv(os.path.join(RES, "stints_public_2015_2025.csv"), parse_dates=["start", "end", "first_il_start"])
EX = pd.read_csv(os.path.join(args.dump, "player_season_exposure.csv"))
EA = pd.read_csv(os.path.join(args.dump, "episodes_all_2012_2025.csv"), parse_dates=["start", "end", "first_il_start"])
G = pd.read_csv(P_("Postseason_Injury_Risk/data/games_flat.csv"))
G = G[(G.gameType == "R") & G.status.isin(["Final", "Completed Early"])].copy()
G["date"] = pd.to_datetime(G.date)
SPAN = {s: (g.date.min(), g.date.max()) for s, g in G.groupby("season")}
MLB = set(G.home_id.unique())
fg = pd.read_csv(P_("_staging_tmp/fangraphs_war_2010_2025.csv")).rename(columns={"mlbamid": "player_id"}).dropna(subset=["player_id"])
fg["player_id"] = fg.player_id.astype(int)
OUT = {"label": "POST HOC / EXPLORATORY (Phase 1b). Written after the Phase 1 output and the reviewer's output had been seen.",
       "episode_rule": "r1"}


def ols_cl(y, X, groups):
    return sm.OLS(y, sm.add_constant(X)).fit(cov_type="cluster", cov_kwds={"groups": groups})


def wins_fit(D, cols, ctrl=("team_proj", "W_prev")):
    M = D.dropna(subset=list(ctrl) + ["W_prev"]).copy()
    X = pd.concat([M[list(cols) + list(ctrl)], pd.get_dummies(M.season, prefix="s", drop_first=True, dtype=float)], axis=1)
    f = ols_cl(M.W.astype(float), X.astype(float), M.tid)
    return {c: {"est": float(f.params[c]), "se": float(f.bse[c]), "lo": float(f.conf_int().loc[c, 0]),
                "hi": float(f.conf_int().loc[c, 1])} for c in cols} | {"n": int(len(M))}


def logit_or(D, col, ctrl=("team_proj",)):
    X = pd.concat([D[[col] + list(ctrl)], pd.get_dummies(D.season, prefix="s", drop_first=True, dtype=float)], axis=1).astype(float)
    f = sm.Logit(D.q.astype(float), sm.add_constant(X)).fit(disp=0, cov_type="cluster", cov_kwds={"groups": D.tid})
    ci = f.conf_int().loc[col]
    return {"or_per_war_lost": float(np.exp(f.params[col])), "ci95_cluster": [float(np.exp(ci[0])), float(np.exp(ci[1]))], "n": int(len(D))}


# ================================================================================================ R2
Wd = {(p, s): (w, e) for p, s, w, e in zip(EX.player_id, EX.season, EX.war, EX.exposure)}


def rate(pid, s, k=100):
    num = den = 0.0
    for w, kk in zip((5, 4, 3), (1, 2, 3)):
        v = Wd.get((pid, s - kk))
        if v is not None:
            num += w * v[0]; den += w * v[1]
    return num / (den + k) if den > 0 else np.nan


GONE = {"Declared Free Agency", "Released", "Retired", "Deceased", "Voluntarily Retired"}
ev = []
with open(P_("Sweeper_Injury_Risk/data/txns_live.jsonl")) as fh:
    for line in fh:
        t = json.loads(line)
        pid = (t.get("person") or {}).get("id")
        if not pid:
            continue
        to = (t.get("toTeam") or {}).get("id"); fr = (t.get("fromTeam") or {}).get("id"); ty = t.get("typeDesc")
        d = pd.Timestamp(t.get("effectiveDate") or t.get("date"))
        if ty in GONE:
            club = -1
        elif to in MLB:
            club = to
        elif fr in MLB and ty in ("Optioned", "Outrighted", "Assigned", "Status Change"):
            club = fr
        else:
            continue
        ev.append((int(pid), d, int(t.get("id") or 0), club))
EV = pd.DataFrame(ev, columns=["pid", "d", "txn", "club"]).sort_values(["pid", "d", "txn"])
# final S-1 club from FanGraphs single-club rows; traded ("- - -") pitchers from their last S-1 game log
ABBR_T = {"ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112, "CHW": 145, "CIN": 113, "CLE": 114, "COL": 115, "DET": 116,
          "HOU": 117, "KCR": 118, "LAA": 108, "LAD": 119, "MIA": 146, "FLA": 146, "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147,
          "OAK": 133, "ATH": 133, "PHI": 143, "PIT": 134, "SDP": 135, "SEA": 136, "SFG": 137, "STL": 138, "TBR": 139, "TEX": 140,
          "TOR": 141, "WSN": 120}
NAME2ID = {n: i for i, n in G[["home_id", "home"]].drop_duplicates().set_index("home_id").home.items()}
GL = pd.read_csv(P_("Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv"), usecols=["player_id", "season", "date", "gamePk", "team"])
GL = GL[GL.gamePk.isin(set(G.gamePk))].sort_values("date")
last_pitch_club = GL.groupby(["player_id", "season"]).team.last().map(NAME2ID).to_dict()
fgc = fg.assign(tid=fg.team.map(ABBR_T))
single = fgc.dropna(subset=["tid"]).groupby(["player_id", "season"]).tid.agg(lambda x: x.iloc[0] if x.nunique() == 1 else np.nan).to_dict()
cand_players = sorted({p for (p, s) in Wd})
rows = []
n_src = {"feed": 0, "fangraphs_prior_club": 0, "pitcher_log_prior_club": 0, "unassigned_traded_hitter": 0}
evg = {p: g for p, g in EV.groupby("pid")}
for s in OUTCOME:
    od = SPAN[s][0]
    for p in cand_players:
        if not any((p, s - k) in Wd for k in (1, 2, 3)):
            continue
        g = evg.get(p); club = None; src = None
        if g is not None:
            g = g[g.d < od]
            if len(g):
                club = int(g.club.iloc[-1]); src = "feed"
        if club is None:
            c = single.get((p, s - 1))
            if c is not None and not pd.isna(c):
                club, src = int(c), "fangraphs_prior_club"
            elif (p, s - 1) in last_pitch_club and not pd.isna(last_pitch_club[(p, s - 1)]):
                club, src = int(last_pitch_club[(p, s - 1)]), "pitcher_log_prior_club"
            elif (p, s - 1) in Wd:
                src = "unassigned_traded_hitter"
        if src:
            n_src[src] += 1
        if club is not None and club > 0:
            r = rate(p, s)
            if np.isfinite(r):
                rows.append((s, club, p, r * 162))
PRE = pd.DataFrame(rows, columns=["season", "tid", "player_id", "proj_war"])
tp_pre = PRE.groupby(["season", "tid"]).proj_war.sum().rename("team_proj_pre").reset_index()
T = T.merge(tp_pre, on=["season", "tid"], how="left")
# the reviewer's "retained" control: players whose FanGraphs row for season S is with the club they ended S-1 with
r2 = {"method": "fallback: organisation roster on opening day from the public transaction feed (last transaction before the "
                "first regular-season date that places the player with an MLB club; release / free agency / retirement "
                "clears him), for every player with fWAR in S-1..S-3; players without a feed event take their final S-1 "
                "club (FanGraphs single-club row, else last S-1 pitching log). Projection: the same Marcel (K = 100) x 162.",
      "stats_api_roster_endpoint": "not reachable from the build environment when Phase 1b ran (HTTP 403); no cached opening-day rosters were on disk. Opening-day rosters were retrieved for Phase 2 (data_public/opening_day_40man_2015_2026.csv).",
      "limitations": "includes players on the IL or in the minors on opening day (by design: they are the preseason talent); "
                     "traded hitters without a feed event after their trade are unassigned; early-season (first 30 days) "
                     "appearances not used: public hitter appearance dates before 2015 are not on disk",
      "assignment_sources_player_seasons": n_src,
      "corr_with_sealed_team_proj": float(T[["team_proj", "team_proj_pre"]].corr().iloc[0, 1]),
      "corr_within_season_demeaned": float((T.team_proj - T.groupby("season").team_proj.transform("mean")).corr(
          T.team_proj_pre - T.groupby("season").team_proj_pre.transform("mean")))}
r2["wins_per_war_lost"] = {
    "primary_control_team_proj": wins_fit(T, ["war_lost"])["war_lost"],
    "preseason_control_team_proj_pre": wins_fit(T, ["war_lost"], ("team_proj_pre", "W_prev"))["war_lost"],
    "both_controls": wins_fit(T, ["war_lost"], ("team_proj", "team_proj_pre", "W_prev"))["war_lost"],
    "W_prev_only": wins_fit(T, ["war_lost"], ("W_prev",))["war_lost"]}
r2["playoff_or"] = {"primary_control_team_proj": logit_or(T, "war_lost"),
                    "preseason_control_team_proj_pre": logit_or(T, "war_lost", ("team_proj_pre",))}
v = [x["est"] for x in r2["wins_per_war_lost"].values()]
r2["range_wins_per_war_lost_over_controls"] = [float(min(v)), float(max(v))]
OUT["R2_preseason_control"] = r2

# ================================================================================================ R3
S["opening"] = S.season.map({s: SPAN[s][0] for s in SPAN})
S["in_season_onset"] = S.first_il_start > S.opening
S["od_placed"] = ~S.in_season_onset
S["pre_aug1_start"] = S.start < pd.to_datetime(S.season.astype(str) + "-08-01")
TEAM_DATES = {}
for k, g in pd.concat([G[["season", "date", "home_id"]].rename(columns={"home_id": "tid"}),
                       G[["season", "date", "away_id"]].rename(columns={"away_id": "tid"})]).groupby(["season", "tid"]):
    TEAM_DATES[k] = np.sort(g.date.to_numpy())
S["gm_remaining"] = [int((TEAM_DATES[(s, t)] >= np.datetime64(a)).sum()) for s, t, a in zip(S.season, S.tid, S.start)]
fam_med = S.groupby("family").games_missed.median()
S["gm_fixed"] = np.minimum(S.family.map(fam_med), S.gm_remaining)
S["wl_fixed"] = S.rate * S.gm_fixed


def add(col, mask, val="war_lost"):
    a = S[mask].groupby(["season", "tid"])[val].sum().rename(col).reset_index()
    return T[["season", "tid"]].merge(a, how="left").fillna({col: 0.0})[col].to_numpy()


T["x_a_fixed"] = add("x", S.in_season_onset & S.pre_aug1_start, "wl_fixed")
T["x_a_obs"] = add("x", S.in_season_onset & S.pre_aug1_start)
T["wl_in_cont"] = add("x", ~S.out_of_contention); T["wl_out_cont"] = add("x", S.out_of_contention)
T["wl_od"] = add("x", S.od_placed); T["wl_inseason"] = add("x", S.in_season_onset)
r3 = {"a_inseason_onset_pre_aug1_duration_fixed_at_family_median": wins_fit(T, ["x_a_fixed"])["x_a_fixed"],
      "a_inseason_onset_pre_aug1_observed_duration": wins_fit(T, ["x_a_obs"])["x_a_obs"],
      "a_family_median_games": {k: float(v) for k, v in fam_med.items()},
      "b_contention_split": wins_fit(T, ["wl_in_cont", "wl_out_cont"]),
      "c_opening_day_vs_in_season": wins_fit(T, ["wl_od", "wl_inseason"]),
      "c_share_war_lost_opening_day_placed": float(S.war_lost[S.od_placed].sum() / S.war_lost.sum()),
      "b_share_war_lost_out_of_contention": float(S.war_lost[S.out_of_contention].sum() / S.war_lost.sum())}
r3["c_playoff_or"] = {"opening_day": logit_or(T.assign(x=T.wl_od), "x", ("team_proj", "wl_inseason")),
                      "in_season": logit_or(T.assign(x=T.wl_inseason), "x", ("team_proj", "wl_od"))}
E12 = R["E12"]
cands = {"primary (R1, preregistered specification)": R["E2"]["est"],
         "E12a placements before 1 August": E12["a_pre_aug1"]["wins_per_war_lost"],
         "E12b in-contention placements only": E12["b_in_contention"]["wins_per_war_lost"],
         "E12c Apr-Jun placements -> Jul-Sep wins": E12["c_split_season"]["wins_per_war_lost_post_jul1"],
         "R3a in-season onsets before 1 Aug, duration fixed at family median": r3["a_inseason_onset_pre_aug1_duration_fixed_at_family_median"]["est"],
         "R3b in-contention term of the split": r3["b_contention_split"]["wl_in_cont"]["est"],
         "R3c in-season-onset term": r3["c_opening_day_vs_in_season"]["wl_inseason"]["est"],
         "R2 preseason (opening-day organisation) control": r2["wins_per_war_lost"]["preseason_control_team_proj_pre"]["est"]}
lo_k = min(cands, key=cands.get); hi_k = max(cands, key=cands.get)
r3["range"] = {"designs": cands, "most_negative": [lo_k, cands[lo_k]], "least_negative": [hi_k, cands[hi_k]],
               "excluded_as_not_an_estimate": "R3b out-of-contention term (selection on the outcome) and R2 W_prev-only (no talent control)"}
OUT["R3_reverse_causality_designs"] = r3

# ================================================================================================ R4 E11 calibration


def ols(y, X):
    Z = np.column_stack([np.ones(len(y)), X]); return np.linalg.lstsq(Z, y, rcond=None)[0]


def loso_resid(D, cols, seasons):
    M = D[D.season.isin(seasons)]
    y = M.war_lost.to_numpy(float); X = M[cols].to_numpy(float); ss = M.season.to_numpy(); r = np.empty(len(y))
    for s in seasons:
        te = ss == s; b = ols(y[~te], X[~te]); r[te] = y[te] - (b[0] + X[te] @ b[1:])
    return M.assign(u=r)


def mat(D, col):
    Y = D.pivot_table(index="tid", columns="season", values=col).to_numpy(float)
    return Y - Y.mean(0, keepdims=True)


def icc(Y):
    k, n = Y.shape; cm = Y.mean(1)
    msb = n * ((cm - Y.mean()) ** 2).sum() / (k - 1); msw = ((Y - cm[:, None]) ** 2).sum() / ((k - 1) * (n - 1))
    return (msb - msw) / (msb + (n - 1) * msw)


def perm_q95(Y, rng, npm=200):
    k, n = Y.shape
    return np.quantile([icc(np.column_stack([Y[rng.permutation(k), j] for j in range(n)])) for _ in range(npm)], .95)


obs_p = R["E11"]["primary"]["icc1"]; obs_a = R["E11"]["sens_roster_loso_300"]["icc1"]
assert abs(icc(mat(loso_resid(T, ["war_lost_prev"] + RF, SP), "u")) - obs_p) < 1e-9
Xs = pd.get_dummies(T.season, prefix="s", dtype=float)
Z = np.column_stack([T[RF].to_numpy(float), Xs.to_numpy()])
bfit = np.linalg.lstsq(Z, T.war_lost.to_numpy(float), rcond=None)[0]
fit = Z @ bfit; e = T.war_lost.to_numpy(float) - fit
sig = float(pd.Series(e).groupby(T.season.values).std().mean())
rng = np.random.default_rng(SEED + 7)
seasons = T.season.to_numpy(); clubs = T.tid.to_numpy(); uc = np.unique(clubs)
idx_by_season = {s: np.where(seasons == s)[0] for s in OUTCOME}
sim = {"dgp": "roster-only in-sample fit + season FE; residuals permuted within season; a club effect of ICC rho added "
              "(sqrt(1-rho) e + sqrt(rho) sigma u_club); pushed through the exact LOSO + ICC(1) pipeline; the club's own "
              "prior-year WAR lost is rebuilt from the simulated values", "seed": SEED + 7, "n_panels": {}, "rho": {}}
store = {}
for rho in [0.0, 0.03, 0.06, 0.11, 0.2]:
    NS = args.nsim if rho == 0.0 else max(args.nsim // 2, 200)
    Pp, Aa, rejP, rejA = [], [], 0, 0
    NPERM_PANELS = min(NS, 200)
    for it in range(NS):
        eps = np.empty(len(e))
        for s, ix in idx_by_season.items():
            eps[ix] = rng.permutation(e[ix])
        u = dict(zip(uc, rng.standard_normal(len(uc)))); ucs = np.array([u[c] for c in clubs])
        D = T[["season", "tid"] + RF].copy(); D["war_lost"] = fit + np.sqrt(1 - rho) * eps + np.sqrt(rho) * sig * ucs
        D = D.sort_values(["tid", "season"]); D["war_lost_prev"] = D.groupby("tid").war_lost.shift(1)
        Yp = mat(loso_resid(D, ["war_lost_prev"] + RF, SP), "u"); Ya = mat(loso_resid(D, RF, OUTCOME), "u")
        ip, ia = icc(Yp), icc(Ya); Pp.append(ip); Aa.append(ia)
        if it < NPERM_PANELS:
            rejP += ip > perm_q95(Yp, rng); rejA += ia > perm_q95(Ya, rng)
    store[rho] = (np.array(Pp), np.array(Aa))
    sim["n_panels"][str(rho)] = NS
    sim["rho"][str(rho)] = {"primary_mean": float(np.mean(Pp)), "primary_q025": float(np.quantile(Pp, .025)),
                            "primary_q95": float(np.quantile(Pp, .95)), "primary_q975": float(np.quantile(Pp, .975)),
                            "power_primary_permutation_test": rejP / NPERM_PANELS,
                            "sensA_mean": float(np.mean(Aa)), "sensA_q95": float(np.quantile(Aa, .95)),
                            "power_sensA_permutation_test": rejA / NPERM_PANELS, "n_panels_with_permutation_test": NPERM_PANELS}
P0, A0 = store[0.0]
crit_p, crit_a = float(np.quantile(P0, .95)), float(np.quantile(A0, .95))
sim["calibrated"] = {
    "primary_null_mean": float(P0.mean()), "primary_null_q95": crit_p,
    "primary_null_band95": [float(np.quantile(P0, .025)), float(np.quantile(P0, .975))],
    "primary_observed": obs_p, "primary_p_calibrated": float((1 + (P0 >= obs_p).sum()) / (1 + len(P0))),
    "sensA_null_q95": crit_a, "sensA_observed": obs_a, "sensA_p_calibrated": float((1 + (A0 >= obs_a).sum()) / (1 + len(A0))),
    "type1_primary_permutation_test_at_nominal_05": sim["rho"]["0.0"]["power_primary_permutation_test"],
    "power_primary_calibrated_critical": {str(r): float((store[r][0] > crit_p).mean()) for r in [0.03, 0.06, 0.11, 0.2]},
    "power_sensA_calibrated_critical": {str(r): float((store[r][1] > crit_a).mean()) for r in [0.03, 0.06, 0.11, 0.2]}}
pw = sim["calibrated"]["power_primary_calibrated_critical"]
grid = [0.03, 0.06, 0.11, 0.2]
mde = next((r for r in grid if pw[str(r)] >= 0.8), None)
if mde is not None and grid.index(mde) > 0:
    r0 = grid[grid.index(mde) - 1]
    mde = r0 + (0.8 - pw[str(r0)]) * (mde - r0) / (pw[str(mde)] - pw[str(r0)])
sim["calibrated"]["mde_icc_primary_80pct_interpolated"] = mde
sim["statement"] = ("The prefit MDE (ICC 0.110 at 80% power) holds for the roster-only residual, not for the primary residual; "
                    "for the primary, power at ICC 0.11 is the value in power_primary_calibrated_critical['0.11'].")
# carry-over decomposition
last = {s: SPAN[s][1] for s in SPAN}
EA["open_end"] = EA.end >= EA.season.map(last)
prev_of = {2015: 2014, 2016: 2015, 2017: 2016, 2018: 2017, 2019: 2018, 2021: 2019, 2022: 2021, 2023: 2022, 2024: 2023, 2025: 2024}
openset = set(zip(EA.loc[EA.open_end, "mlbid"], EA.loc[EA.open_end, "season"]))
S["carry"] = [(p, prev_of[s]) in openset for p, s in zip(S.mlbid, S.season)]
T["wl_carry"] = add("x", S.carry); T["wl_new"] = add("x", ~S.carry)
T = T.sort_values(["tid", "season"]); T["wl_new_prev"] = T.groupby("tid").wl_new.shift(1)
Y = T.dropna(subset=["war_lost_prev"])
co = {"share_war_lost_carry_over": float(S.war_lost[S.carry].sum() / S.war_lost.sum()),
      "definition": "episodes of players whose episode was open on the final regular-season day of the previous outcome season (2019 for 2021)"}
for c in ["war_lost", "wl_new", "wl_carry"]:
    f = sm.OLS(Y[c], sm.add_constant(Y[["war_lost_prev"]])).fit()
    co[f"{c}_on_war_lost_prev"] = {"slope": float(f.params.iloc[1]), "r2": float(f.rsquared), "n": int(len(Y))}
Y2 = T.dropna(subset=["wl_new_prev"]); f = sm.OLS(Y2.wl_new, sm.add_constant(Y2[["wl_new_prev"]])).fit()
co["wl_new_on_wl_new_prev"] = {"slope": float(f.params.iloc[1]), "r2": float(f.rsquared), "n": int(len(Y2))}
TP = T[T.season.isin(SP)].copy()
for c in ["wl_carry", "wl_new"]:
    TP["tmp"] = TP[c]; D_ = TP.assign(war_lost=TP[c])
    M = loso_resid(D_, ["war_lost_prev"] + RF, SP)
    sst = sum(((D_[D_.season == s][c] - D_[D_.season != s][c].mean()) ** 2).sum() for s in SP)
    co[f"{c}_oos_r2_all_features"] = float(1 - (M.u ** 2).sum() / sst)
sim["carry_over"] = co
OUT["R4_E11_calibration"] = sim

# ================================================================================================ R5
res = []
for s, g in G[G.season.isin(OUTCOME)].groupby("season"):
    for tid in set(g.home_id) | set(g.away_id):
        h = g[g.home_id == tid]; a = g[g.away_id == tid]
        rs = h.home_score.sum() + a.away_score.sum(); ra = h.away_score.sum() + a.home_score.sum()
        w = (h.home_score > h.away_score).sum() + (a.away_score > a.home_score).sum(); n = len(h) + len(a)
        res.append((s, tid, rs, ra, w, n))
PY = pd.DataFrame(res, columns=["season", "tid", "RS", "RA", "W", "G"])
PY["pyth"] = PY.G * PY.RS ** 1.83 / (PY.RS ** 1.83 + PY.RA ** 1.83)
PY["resid"] = PY.W - PY.pyth
OUT["R5_comparators"] = {
    "binomial_sd_wins_500_team_162": float(np.sqrt(162 * 0.25)),
    "pythagorean_residual_sd_wins": float(PY.groupby("season").resid.std().mean()),
    "pythagorean_exponent": 1.83, "pythagorean_n_club_seasons": int(len(PY)),
    "sd_of_wins_within_season": float(PY.groupby("season").W.std().mean()),
    "injury_luck_one_sd_wins_R1": R["E1"]["one_sd_wins"], "injury_unexpected_one_sd_wins_R1": R["E5"]["sd_unexpected_oos_wins"],
    "batting_order_context": "about 1 win per season between optimal and typical orders (Tango, Lichtman & Dolphin, The Book, 2007; "
                             "page not verified): the expected value of a decision, not the SD of a shock; context only",
    "platoon": "dropped from external use (unpublished source)",
    "source": "Stats API schedule results (games_flat.csv), 2015-2025 excluding 2020"}

# ================================================================================================ R6
rb = np.random.default_rng(SEED)
cl = sorted(T.tid.unique()); byc = {c: T[T.tid == c] for c in cl}


def sd_stat(D):
    return float(D.groupby("season").war_lost.std().mean())


def e2_stat(D):
    M = D.dropna(subset=["W_prev"]); lv = sorted(M.season.unique())
    X = np.column_stack([np.ones(len(M)), M.war_lost, M.team_proj, M.W_prev] + [(M.season == s).astype(float) for s in lv[1:]])
    return float(np.linalg.lstsq(X, M.W.to_numpy(float), rcond=None)[0][1])


def bca(stat, B=2000):
    th = stat(T); bs = []
    for _ in range(B):
        take = rb.integers(0, len(cl), len(cl))
        bs.append(stat(pd.concat([byc[cl[i]] for i in take], ignore_index=True)))
    bs = np.array(bs)
    from scipy.stats import norm
    z0 = norm.ppf((bs < th).mean())
    jk = np.array([stat(T[T.tid != c]) for c in cl]); jm = jk.mean()
    acc = ((jm - jk) ** 3).sum() / (6 * (((jm - jk) ** 2).sum()) ** 1.5)
    q = [norm.cdf(z0 + (z0 + z) / (1 - acc * (z0 + z))) for z in (norm.ppf(.025), norm.ppf(.975))]
    return {"est": th, "bca95": [float(np.quantile(bs, q[0])), float(np.quantile(bs, q[1]))],
            "percentile95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))], "z0": float(z0), "acceleration": float(acc), "B": B}


r6 = {"bca": {"E1_sd_within_season": bca(sd_stat), "E2_wins_per_war_lost": bca(e2_stat)}}
# P(playoffs) by format era
AT = [R["E1"]["p10"], R["E1"]["p50"], R["E1"]["p90"]]; PM = R["E3"]["team_proj_median"]


def p_era(D):
    lv = sorted(D.season.unique())
    X = np.column_stack([np.ones(len(D)), D.war_lost, D.team_proj] + [(D.season == s).astype(float) for s in lv[1:]])
    y = D.q.to_numpy(float); b = np.zeros(X.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -35, 35))); H = (X * (p * (1 - p))[:, None]).T @ X
        b = b + np.linalg.solve(H, X.T @ (y - p))
    out = []
    for v in AT:
        Xe = X.copy(); Xe[:, 1] = v; Xe[:, 2] = PM
        out.append(float(np.mean(1 / (1 + np.exp(-Xe @ b)))))
    return float(np.exp(b[1])), out


era = {}
for nm, msk in (("pre_2022_10_team_format", T.season < 2022), ("2022_plus_12_team_format", T.season >= 2022)):
    D = T[msk]; o, pr = p_era(D); bs = []
    byc2 = {c: D[D.tid == c] for c in cl}
    for _ in range(1000):
        take = rb.integers(0, len(cl), len(cl))
        try:
            bs.append(p_era(pd.concat([byc2[cl[i]] for i in take], ignore_index=True)))
        except np.linalg.LinAlgError:
            pass
    era[nm] = {"n": int(len(D)), "or_per_war_lost": o, "p_at_p10_p50_p90": pr, "war_lost_at": AT,
               "ci95_or": [float(np.quantile([x[0] for x in bs], .025)), float(np.quantile([x[0] for x in bs], .975))],
               "ci95_p": [[float(np.quantile([x[1][j] for x in bs], q)) for q in (.025, .975)] for j in range(3)], "draws": len(bs)}
r6["playoffs_by_format_era"] = era
# suspension sensitivity: Tatis 2022 (feed shows only "roster status changed" on 2022-08-12, not a suspension)
tat = S[(S.name == "Fernando Tatis Jr.") & (S.season == 2022)]
if len(tat):
    i = tat.index[0]; d = TEAM_DATES[(2022, int(S.at[i, "tid"]))]
    gm_after = int(((d >= np.datetime64("2022-08-12")) & (d <= np.datetime64(S.at[i, "end"]))).sum())
    Tt = T.copy(); m = (Tt.season == 2022) & (Tt.tid == S.at[i, "tid"])
    Tt.loc[m, "war_lost"] -= S.at[i, "rate"] * gm_after
    r6["tatis_2022_suspension_sensitivity"] = {"episode_war_lost": float(S.at[i, "war_lost"]), "games_after_2022_08_12": gm_after,
                                                "war_lost_removed": float(S.at[i, "rate"] * gm_after),
                                                "E1_sd_within_season": sd_stat(Tt), "E1_mean": float(Tt.war_lost.mean()), "E2_est": e2_stat(Tt),
                                                "note": "the public feed records the 12 Aug 2022 move only as 'roster status changed', so R1 cannot detect it; reported as a sensitivity"}
if args.covid and os.path.exists(args.covid):
    C = json.load(open(args.covid))
    r6["covid_era_blanks_kept_R1"] = {"E1_mean": C["E1"]["mean"], "E1_sd_within_season": C["E1"]["sd_within_season"],
                                      "E2_est": C["E2"]["est"], "E2_se": C["E2"]["se"], "one_sd_wins": C["E1"]["one_sd_wins"],
                                      "E3_or": C["E3"]["all"]["or_per_war_lost"], "n_episodes": C["meta"]["n_episodes_outcome_seasons"]}
OUT["R6"] = r6

# ================================================================================================ sealed vs repaired
def g(d, path):
    for k in path.split("."):
        d = d[int(k)] if isinstance(d, list) else d[k]
    return d


keys = ["E1.mean", "E1.sd_within_season", "E1.p10", "E1.p90", "E1.one_sd_wins", "E1.p10_to_p90_wins", "E2.est", "E2.se", "E2.lo", "E2.hi",
        "E3.all.or_per_war_lost", "E3.all.p_at_p10_p50_p90.0", "E3.all.p_at_p10_p50_p90.1", "E3.all.p_at_p10_p50_p90.2",
        "E3.format_2022plus.or_per_war_lost", "E4.prior_year_only.oos_r2", "E4.roster_only.oos_r2", "E4.all.oos_r2",
        "E5.sd_unexpected_oos_war", "E5.sd_unexpected_oos_wins", "E7.top1_share_mean", "E7.top3_share_mean", "E7.gini_club_seasons",
        "E8.share_of_episodes", "E8.share_of_war_lost", "E11.primary.icc1", "E11.primary.p_perm_one_sided",
        "E11.sens_roster_loso_300.icc1", "E11.sens_roster_loso_300.p_perm_one_sided", "E11.verdict",
        "E12.a_pre_aug1.wins_per_war_lost", "E12.b_in_contention.wins_per_war_lost", "E12.c_split_season.wins_per_war_lost_post_jul1"]
OUT["sealed_vs_repaired"] = {k: {"sealed": g(RS, k), "repaired": g(R, k)} for k in keys}
json.dump(OUT, open(os.path.join(RES, "phase1b_results.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print(json.dumps({k: OUT[k] for k in ("R2_preseason_control", "R5_comparators")}, indent=1, default=str)[:4000])
print(json.dumps(OUT["R3_reverse_causality_designs"]["range"], indent=1))
print(json.dumps(OUT["R4_E11_calibration"]["calibrated"], indent=1))
print(json.dumps(OUT["R4_E11_calibration"]["carry_over"], indent=1))
print(json.dumps(OUT["R6"], indent=1, default=str)[:3000])
