"""
posthoc_r4.py - post hoc analyses for the SSAC full paper, fourth round (2026-11-03). Not part of any sealed plan.

Reads the pinned club-season table (v2_public/results/team_season_phase2.csv), the public episode table
(stints_public_2015_2025.csv) and the sealed results JSON, and writes v2_public/results/posthoc_r4_2026-11-03.json.
Every model is the paper's primary wins model (OLS of W on the stated terms, the opening-day projection, the previous
season's wins and season fixed effects, club-clustered SE, the 270 club-seasons with a previous season) unless stated.

  Y1  carry-over against new injuries: wins per WAR lost for the part known at the previous season's end and the rest
  Y2  concentration: WAR lost from the club-season's largest episode against the rest
  Y3  curvature: a squared term in WAR lost, and the slope above and below the median
  Y4  talent interaction: does a WAR lost go with more wins lost on a stronger roster?
  Y5  the next season: WAR lost in season t against wins in t+1, net of wins and talent in t+1
  Y6  playoff shortfall: non-qualifying club-seasons that finished within their above-median injury loss (in wins) of the
      last wild card in their league, with the heaviest injury seasons listed
  Y7  worked examples from the sealed coefficients (a projected 3-WAR player missing half a season)

Usage: python3 posthoc_r4.py --results <v2_public/results> [--out <json>]
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

ap = argparse.ArgumentParser()
ap.add_argument("--results", required=True)
ap.add_argument("--out", default=None)
a = ap.parse_args()
OUT_PATH = a.out or os.path.join(a.results, "posthoc_r4_2026-11-03.json")

T = pd.read_csv(os.path.join(a.results, "team_season_phase2.csv"))
S = pd.read_csv(os.path.join(a.results, "stints_public_2015_2025.csv"))
J = json.load(open(os.path.join(a.results, "phase2_results.json")))
P21 = J["P2_1_preseason_control"]
B = abs(P21["wins"]["est"])                       # wins per WAR lost, primary (magnitude)
assert len(T) == 300 and T.season.nunique() == 10
M = T.dropna(subset=["W_prev"]).copy()
assert len(M) == 270
R = {"label": "post hoc, fourth round (2026-11-03); nothing here was declared in advance", "n_wins_model": int(len(M))}


def clus(formula, df, terms):
    f = smf.ols(formula, df).fit(cov_type="cluster", cov_kwds={"groups": df.tid})
    ci = f.conf_int()
    out = {t: {"est": float(f.params[t]), "lo_cluster": float(ci.loc[t, 0]), "hi_cluster": float(ci.loc[t, 1]), "p": float(f.pvalues[t])} for t in terms}
    out["n"] = int(f.nobs); out["r2"] = float(f.rsquared)
    return out, f


def wald_equal(f, t1, t2):
    r = np.zeros(len(f.params)); r[list(f.params.index).index(t1)] = 1; r[list(f.params.index).index(t2)] = -1
    return float(f.wald_test(r, use_f=False, scalar=True).pvalue)


# ---- Y0 the primary, reproduced here as a gate --------------------------------------------------------------------
y0, f0 = clus("W ~ war_lost + team_proj_od + W_prev + C(season)", M, ["war_lost"])
assert abs(y0["war_lost"]["est"] - P21["wins"]["est"]) < 1e-9, "primary wins model not reproduced"
R["Y0_primary_reproduced"] = {"wins_per_war_lost": y0["war_lost"]["est"], "sealed": P21["wins"]["est"]}

# ---- Y1 carry-over against new injuries ------------------------------------------------------------------------------
assert np.allclose(M.wl_carry + M.wl_new, M.war_lost)
y1, f1 = clus("W ~ wl_carry + wl_new + team_proj_od + W_prev + C(season)", M, ["wl_carry", "wl_new"])
y1["wald_equal_slopes_p"] = wald_equal(f1, "wl_carry", "wl_new")
y1["share_of_war_lost_carry"] = float(M.wl_carry.sum() / M.war_lost.sum())
R["Y1_carry_vs_new"] = y1

# ---- Y2 concentration: the largest episode against the rest --------------------------------------------------------
SO = S[S.season.isin(T.season.unique())]
top = SO.sort_values("war_lost", ascending=False).groupby(["season", "tid"]).head(1).set_index(["season", "tid"]).war_lost
M = M.set_index(["season", "tid"])
M["wl_top1"] = top.reindex(M.index).fillna(0.0).to_numpy()
M = M.reset_index()
assert (M.wl_top1 <= M.war_lost + 1e-9).all()
M["wl_rest"] = M.war_lost - M.wl_top1
y2, f2 = clus("W ~ wl_top1 + wl_rest + team_proj_od + W_prev + C(season)", M, ["wl_top1", "wl_rest"])
y2["wald_equal_slopes_p"] = wald_equal(f2, "wl_top1", "wl_rest")
y2["top1_share_mean"] = float((M.wl_top1 / M.war_lost).mean())
R["Y2_concentration"] = y2

# ---- Y3 curvature ----------------------------------------------------------------------------------------------------
M["wl_c"] = M.war_lost - M.war_lost.mean()
M["wl_c2"] = M.wl_c ** 2
y3, f3 = clus("W ~ wl_c + wl_c2 + team_proj_od + W_prev + C(season)", M, ["wl_c", "wl_c2"])
med = float(M.war_lost.median())
M["wl_above"] = np.maximum(M.war_lost - med, 0.0)
y3b, f3b = clus("W ~ war_lost + wl_above + team_proj_od + W_prev + C(season)", M, ["war_lost", "wl_above"])
R["Y3_curvature"] = {"quadratic": y3, "hinge_at_median": {"median_war_lost": med, "slope_below": y3b["war_lost"],
                     "slope_change_above": y3b["wl_above"], "slope_above_est": y3b["war_lost"]["est"] + y3b["wl_above"]["est"], "n": y3b["n"]}}

# ---- Y4 talent interaction --------------------------------------------------------------------------------------------
M["tp_c"] = M.team_proj_od - M.team_proj_od.mean()
M["wl_x_tp"] = M.war_lost * M.tp_c
y4, f4 = clus("W ~ war_lost + tp_c + wl_x_tp + W_prev + C(season)", M, ["war_lost", "wl_x_tp"])
q25, q75 = M.team_proj_od.quantile([.25, .75])
y4["slope_at_projection_p25"] = y4["war_lost"]["est"] + y4["wl_x_tp"]["est"] * float(q25 - M.team_proj_od.mean())
y4["slope_at_projection_p75"] = y4["war_lost"]["est"] + y4["wl_x_tp"]["est"] * float(q75 - M.team_proj_od.mean())
y4["projection_sd"] = float(M.team_proj_od.std())
R["Y4_talent_interaction"] = y4

# ---- Y5 the next season -----------------------------------------------------------------------------------------------
PREV = {2016: 2015, 2017: 2016, 2018: 2017, 2019: 2018, 2021: 2019, 2022: 2021, 2023: 2022, 2024: 2023, 2025: 2024}
N = T.set_index(["season", "tid"])
rows = []
for (s, c), r in N.iterrows():
    if s in PREV and (PREV[s], c) in N.index:
        p = N.loc[(PREV[s], c)]
        rows.append({"season": s, "tid": c, "W_next": r.W, "tp_next": r.team_proj_od, "W_t": p.W, "wl_t": p.war_lost, "wl_next": r.war_lost})
D5 = pd.DataFrame(rows)
y5, f5 = clus("W_next ~ wl_t + W_t + tp_next + C(season)", D5, ["wl_t"])
y5b, _ = clus("W_next ~ wl_t + wl_next + W_t + tp_next + C(season)", D5, ["wl_t", "wl_next"])
R["Y5_next_season"] = {"war_lost_t_on_wins_t_plus_1": y5, "with_next_season_war_lost": y5b}

# ---- Y6 playoff shortfall ------------------------------------------------------------------------------------------------
# League and division membership are fixed over 2015-2025 (no realignment since 2013). Both are checked against the data:
# each division holds five clubs, each league-season holds exactly five qualifiers through 2021 and six from 2022, and the
# club with the most wins in every division-season qualified.
DIV = {"ALE": {110, 111, 147, 139, 141}, "ALC": {145, 114, 116, 118, 142}, "ALW": {117, 108, 133, 136, 140},
       "NLE": {144, 146, 121, 143, 120}, "NLC": {112, 113, 158, 134, 138}, "NLW": {109, 115, 119, 135, 137}}
T["division"] = T.tid.map({c: d for d, cs in DIV.items() for c in cs})
assert T.division.notna().all() and (T.groupby(["season", "division"]).size() == 5).all()
T["league"] = T.division.str[:2]
nq = T.groupby(["season", "league"]).q.sum()
for (s, lg), n in nq.items():
    assert n == (6 if s >= 2022 else 5), f"{s} {lg}: {n} qualifiers"
T["div_max_W"] = T.groupby(["season", "division"]).W.transform("max")
T["div_winner"] = (T.W == T.div_max_W) & (T.q == 1)
assert (T.groupby(["season", "division"]).div_winner.sum() >= 1).all(), "every division's top club qualified"
wc_cut = T[(T.q == 1) & ~T.div_winner].groupby(["season", "league"]).W.min().rename("W_cut")
assert len(wc_cut) == 2 * T.season.nunique()
T = T.join(wc_cut, on=["season", "league"])
T["wl_med_season"] = T.groupby("season").war_lost.transform("median")
T["wins_assoc_above_median"] = (T.war_lost - T.wl_med_season) * B
miss = T[T.q == 0].copy()
miss["shortfall"] = miss.W_cut - miss.W                  # wins short of the last wild card; 0 is a tie lost on the tiebreak
within = miss[(miss.wins_assoc_above_median > 0) & (miss.wins_assoc_above_median >= miss.shortfall)]
R["Y6_playoff_shortfall"] = {
    "non_qualifying_club_seasons": int(len(miss)),
    "with_above_median_war_lost": int((miss.wins_assoc_above_median > 0).sum()),
    "within_association_of_last_wild_card": int(len(within)),
    "of_which_ties_at_zero_shortfall": int((within.shortfall == 0).sum()),
    "clear_shortfall_covered": int((within.shortfall > 0).sum()),
    "per_season_mean": float(len(within) / T.season.nunique()),
    "by_season": {int(s): int(n) for s, n in within.groupby("season").size().items()},
    "definition": "non-qualifying club-seasons with WAR lost above the season median whose WAR lost above the median, times the primary wins "
                  "coefficient, is at least their shortfall in wins from the last wild card in their league that season (the lowest-win qualifier "
                  "that did not win its division); a shortfall of 0 is a tie lost on the tiebreak. An association, not a count of places lost.",
}
heavy = T.assign(wins_above=T.wins_assoc_above_median).sort_values("wins_above", ascending=False).head(10)
R["Y6_heaviest_club_seasons"] = [{"season": int(r.season), "club": r.club, "war_lost": float(r.war_lost), "wins_above_median": float(r.wins_above),
                                  "qualified": int(r.q), "W": int(r.W), "shortfall": (int(r.W_cut - r.W) if r.q == 0 else None)} for r in heavy.itertuples()]
R["Y6_heaviest_club_seasons_note"] = "shortfall is wins short of the last wild card in the club's league that season"

# ---- Y7 worked examples from the sealed coefficients --------------------------------------------------------------------
pp = P21["playoffs"]
p50 = pp["p_at_p10_p50_p90"][1]
slope = float(np.log(pp["or"]))
ex_war = 3.0 * 0.5                                  # a projected 3-WAR player missing half of 162 games
R["Y7_examples"] = {
    "example_projected_war": 3.0, "example_share_of_season_missed": 0.5, "example_war_lost": ex_war,
    "example_wins": ex_war * B,
    "playoff_points_per_war_lost_at_median": float(100 * p50 * (1 - p50) * abs(slope)),
    "example_playoff_points": float(100 * p50 * (1 - p50) * abs(slope) * ex_war),
    "note": "wins use the primary coefficient; playoff points use the pooled logit slope at the median-club probability",
}

json.dump(R, open(OUT_PATH, "w"), indent=1)
print("wrote", OUT_PATH)
for k in ("Y1_carry_vs_new", "Y2_concentration", "Y4_talent_interaction", "Y6_playoff_shortfall", "Y7_examples"):
    print(k, json.dumps({kk: vv for kk, vv in R[k].items() if kk not in ("definition", "note", "by_season")}, indent=None)[:600])
print("Y3", json.dumps(R["Y3_curvature"]["hinge_at_median"])[:400])
print("Y5", json.dumps(R["Y5_next_season"]["war_lost_t_on_wins_t_plus_1"]["wl_t"]))
