"""posthoc_r6.py - postseason berths under median injury luck, and the season after (post hoc, 2026-11-04; DEVIATIONS #31).

A. Counterfactual berths. Every club is given its season's median WAR lost; its wins move by the primary coefficient times the
   difference (W_cf = W + b (WAR lost - season median)); division winners and wild cards are recomputed under the season's
   format (3 division winners per league, 2 wild cards through 2021 and 3 from 2022), with no tiebreakers. Reported at the
   primary coefficient and at both ends of its cluster-robust interval, with the clubs that change, the division titles that
   change, and the postseason round each displaced club reached (data_public/postseason_rounds_2015_2025.csv).
B. The season after. Next-season wins on this season's wins, this season's WAR lost (season-demeaned) and season effects,
   club-clustered; then with next season's opening-day projection added. Decile contrast net of this season's wins.
C. Injury loss in year-to-year change: the share of the variance of the change in wins between consecutive seasons that the
   change in WAR lost times the coefficient accounts for.

Reads results/team_season_phase2.csv, results/phase2_results.json, inputs/standings.csv, data_public/postseason_rounds_2015_2025.csv.
usage: python3 pipeline/posthoc_r6.py [--results results] [--out results/posthoc_r6_2026-11-04.json]
"""
import argparse, json, os
import numpy as np, pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser(); ap.add_argument("--results", default=os.path.join(REPO, "results")); ap.add_argument("--inputs", default=os.path.join(REPO, "inputs"))
ap.add_argument("--out", default=None); a = ap.parse_args()
OUT = a.out or os.path.join(a.results, "posthoc_r6_2026-11-04.json")
T = pd.read_csv(os.path.join(a.results, "team_season_phase2.csv")); J = json.load(open(os.path.join(a.results, "phase2_results.json")))
P = J["P2_1_preseason_control"]; b = abs(P["wins"]["est"]); lo, hi = abs(P["wins"]["hi_cluster"]), abs(P["wins"]["lo_cluster"])
st = pd.read_csv(os.path.join(a.inputs, "standings.csv")).rename(columns={"team_id": "tid"})
PS = pd.read_csv(os.path.join(REPO, "data_public", "postseason_rounds_2015_2025.csv"))
D = T.merge(st[["season", "tid", "league_id", "division_id", "qualified"]], on=["season", "tid"]).sort_values(["season", "tid"]).reset_index(drop=True)
D = D.merge(PS[["season", "tid", "last_round", "last_round_name", "world_series_winner", "pennant"]], on=["season", "tid"], how="left")
D["last_round"] = D.last_round.fillna(0).astype(int); D["world_series_winner"] = D.world_series_winner.fillna(False).astype(bool); D["pennant"] = D.pennant.fillna(False).astype(bool)
assert (D.qualified == (D.last_round > 0)).all(), "postseason rounds disagree with the standings' qualified flag"
WC = {s: (3 if s >= 2022 else 2) for s in D.season.unique()}
D["pct_within_season"] = D.groupby("season").war_lost.rank(pct=True)


def field(g, col):
    out = {}
    for lg, h in g.groupby("league_id"):
        div = h.loc[h.groupby("division_id")[col].idxmax()]
        for t in div.tid:
            out[t] = "division"
        for t in h[~h.tid.isin(div.tid)].nlargest(WC[int(h.season.iloc[0])], col).tid:
            out[t] = "wild_card"
    return out


res = {"meta": {"label": "post hoc (2026-11-04), DEVIATIONS #31", "wins_per_war_lost": b, "ci_cluster": [lo, hi],
                "rule": "W_cf = W + b (WAR lost - season median); division winners and 2 or 3 wild cards per league by W_cf; no tiebreakers"}}
A = {}
for lab, bb in (("primary", b), ("ci_lower", lo), ("ci_upper", hi)):
    changed = 0; seasons_changed = 0; div_changed = 0; berths = 0; detail = []; match = 0
    for s, g in D.groupby("season"):
        g = g.copy(); med = g.war_lost.median(); g["W_cf"] = g.W + bb * (g.war_lost - med)
        act, cf = field(g, "W"), field(g, "W_cf")
        berths += len(act); match += int(set(act) == set(g[g.qualified].tid))
        out_, in_ = sorted(set(act) - set(cf)), sorted(set(cf) - set(act)); changed += len(out_); seasons_changed += int(len(out_) > 0)
        for lg, h in g.groupby("league_id"):
            for dv, hh in h.groupby("division_id"):
                div_changed += int(hh.loc[hh.W.idxmax(), "tid"] != hh.loc[hh.W_cf.idxmax(), "tid"])
        gi = g.set_index("tid")
        detail.append({"season": int(s), "rule_matches_actual_field": set(act) == set(g[g.qualified].tid),
                       "out": [{"club": gi.club[t], "W": int(gi.W[t]), "war_lost": float(gi.war_lost[t]), "W_cf": float(gi.W_cf[t]), "last_round": gi.last_round_name[t] if gi.last_round[t] else None,
                                "pennant": bool(gi.pennant[t]), "world_series_winner": bool(gi.world_series_winner[t])} for t in out_],
                       "in": [{"club": gi.club[t], "W": int(gi.W[t]), "war_lost": float(gi.war_lost[t]), "W_cf": float(gi.W_cf[t])} for t in in_]})
    A[lab] = {"wins_per_war_lost": bb, "berths_total": berths, "berths_changed": changed, "seasons_with_a_change": seasons_changed, "seasons": int(D.season.nunique()),
              "division_titles_changed": div_changed, "divisions_total": int(6 * D.season.nunique()), "rule_matches_actual_field_seasons": match,
              "displaced_pennant_winners": [{"season": d["season"], "club": o["club"], "world_series_winner": o["world_series_winner"]} for d in detail for o in d["out"] if o["pennant"]],
              "displaced_world_series_winners": int(sum(o["world_series_winner"] for d in detail for o in d["out"]))}
    if lab == "primary":
        A[lab]["detail"] = detail
# postseason clubs displaced, by round reached (primary)
disp = [o | {"season": d["season"]} for d in A["primary"]["detail"] for o in d["out"]]
A["displaced_by_round_primary"] = {r: int(sum(1 for o in disp if o["last_round"] == r)) for r in ("wild_card", "division_series", "league_championship", "world_series")}
A["displaced_pennant_winners_primary"] = [{"season": o["season"], "club": o["club"], "world_series_winner": o["world_series_winner"]} for o in disp if o["pennant"]]
A["world_series_winners"] = [{"season": int(r.season), "club": r.club, "war_lost": float(r.war_lost), "percentile_within_season": float(r.pct_within_season),
                              "W": int(r.W)} for r in D[D.world_series_winner].sort_values("season").itertuples()]
_ws = D[D.world_series_winner]; _top = _ws.loc[_ws.pct_within_season.idxmax()]
A["world_series_winners_summary"] = {"n": int(D.world_series_winner.sum()), "mean_percentile_within_season": float(_ws.pct_within_season.mean()),
                                     "below_season_median": int((_ws.pct_within_season <= .5).sum()), "above_season_median": int((_ws.pct_within_season > .5).sum()),
                                     "heaviest": {"season": int(_top.season), "club": _top.club, "rank_in_season": int(D[D.season == _top.season].war_lost.rank(ascending=False)[_top.name]), "war_lost": float(_top.war_lost)},
                                     "pennant_mean_percentile": float(D[D.pennant].pct_within_season.mean()), "qualifiers_mean_percentile": float(D[D.qualified].pct_within_season.mean())}
res["A_berths"] = A

# ---- B. the season after ------------------------------------------------------------------------------------------------------------
PREV = {2016: 2015, 2017: 2016, 2018: 2017, 2019: 2018, 2021: 2019, 2022: 2021, 2023: 2022, 2024: 2023, 2025: 2024}
nxt = D[["season", "tid", "W", "team_proj_od", "war_lost"]].rename(columns={"W": "W_next", "team_proj_od": "proj_next", "war_lost": "war_lost_next"})
nxt["season"] = nxt.season.map(PREV); nxt = nxt.dropna(subset=["season"]); nxt["season"] = nxt.season.astype(int)
M = D.merge(nxt, on=["season", "tid"]).copy()
M["wl_dm"] = M.war_lost - M.groupby("season").war_lost.transform("mean"); M["dW"] = M.W_next - M.W


def ols_cl(y, X, cluster):
    X = np.asarray(X, float); y = np.asarray(y, float); beta = np.linalg.lstsq(X, y, rcond=None)[0]; e = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X); meat = np.zeros((X.shape[1], X.shape[1]))
    for c in np.unique(cluster):
        Xi = X[cluster == c]; ei = e[cluster == c]; meat += np.outer(Xi.T @ ei, Xi.T @ ei)
    G = len(np.unique(cluster)); V = XtX_inv @ meat @ XtX_inv * G / (G - 1)
    return beta, np.sqrt(np.diag(V))


seas = sorted(M.season.unique()); FE = np.column_stack([(M.season == s).astype(float) for s in seas]); cl = M.tid.to_numpy()


def model(cols):
    bb, se = ols_cl(M.W_next, np.column_stack(cols + [FE]), cl)
    return {"coef_war_lost": float(bb[0]), "se_cluster": float(se[0]), "ci95": [float(bb[0] - 1.96 * se[0]), float(bb[0] + 1.96 * se[0])], "coef_W": float(bb[1])}


B = {"n": int(len(M)), "seasons": [int(s) for s in seas],
     "W_next_on_W_and_war_lost": model([M.wl_dm, M.W]),
     "W_next_on_W_proj_this_and_war_lost": model([M.wl_dm, M.W, M.team_proj_od]),
     "W_next_on_W_proj_next_and_war_lost": model([M.wl_dm, M.W, M.proj_next])}
bb, _ = ols_cl(M.dW, np.column_stack([M.W, FE]), cl); M["dW_net"] = M.dW - np.column_stack([M.W, FE]) @ bb
q90 = M.groupby("season").war_lost.transform(lambda x: x.quantile(.9)); q10 = M.groupby("season").war_lost.transform(lambda x: x.quantile(.1))
hv, lt = M[M.war_lost >= q90], M[M.war_lost <= q10]
B["deciles_net_of_W_and_season"] = {"heavy": {"n": int(len(hv)), "dW_net": float(hv.dW_net.mean()), "W": float(hv.W.mean()), "W_next": float(hv.W_next.mean())},
                                    "light": {"n": int(len(lt)), "dW_net": float(lt.dW_net.mean()), "W": float(lt.W.mean()), "W_next": float(lt.W_next.mean())}}
B["corr_war_lost_consecutive_seasons_within_season"] = float(np.corrcoef(M.wl_dm, M.war_lost_next - M.groupby("season").war_lost_next.transform("mean"))[0, 1])
res["B_season_after"] = B

# ---- C. injury loss in year-to-year change ------------------------------------------------------------------------------------------
M["d_wl"] = M.war_lost_next - M.war_lost
dW_dm = M.dW - M.groupby("season").dW.transform("mean"); inj = -b * (M.d_wl - M.groupby("season").d_wl.transform("mean"))
res["C_year_to_year"] = {"n_pairs": int(len(M)), "sd_dW_within_season": float(dW_dm.std()), "sd_injury_component": float(inj.std()),
                         "share_of_variance": float(inj.var() / dW_dm.var()), "corr_dW_injury_component": float(np.corrcoef(dW_dm, inj)[0, 1]),
                         "note": "injury component = -b times the season-demeaned change in WAR lost between consecutive seasons"}
json.dump(res, open(OUT, "w"), indent=1, default=float)
p_ = A["primary"]
print(f"A. {p_['berths_changed']} of {p_['berths_total']} berths ({A['ci_lower']['berths_changed']} to {A['ci_upper']['berths_changed']}), {p_['seasons_with_a_change']} of {p_['seasons']} seasons, {p_['division_titles_changed']} of {p_['divisions_total']} division titles; displaced by round {A['displaced_by_round_primary']}; pennant winners displaced {A['displaced_pennant_winners_primary']}")
print("   WS winners percentile:", [(w['season'], w['club'], w['percentile_within_season']) for w in A['world_series_winners']], A['world_series_winners_summary'])
print(f"B. +{B['W_next_on_W_and_war_lost']['coef_war_lost']:.2f} (se {B['W_next_on_W_and_war_lost']['se_cluster']:.2f}); with proj_next {B['W_next_on_W_proj_next_and_war_lost']['coef_war_lost']:+.2f}; deciles {B['deciles_net_of_W_and_season']}")
print(f"C. share of year-to-year variance {res['C_year_to_year']['share_of_variance']:.2f}, corr {res['C_year_to_year']['corr_dW_injury_component']:.2f} -> {OUT}")
