"""
verify_phase2.py - independent check of results/phase2_results.json (addendum PREREGISTRATION_ADDENDUM_PHASE2_2026-10-02.md, §4).

Imports nothing from the pipeline (injury_luck.py, phase1b_posthoc.py, phase2.py). It rebuilds the R1 episodes 2012-2026
with its own interval-union code (the verify_injury_luck.py method), its own schedule counting and Marcel projection,
reads the opening-day 40-man rosters itself, and recomputes:
  team_proj_od for every one of the 330 club-seasons (2015-2019, 2021-2026);
  the P2.1 wins coefficient and its club-clustered SE (statsmodels formula API), the P2.1 playoff OR, one SD in wins;
  the P2.1 "all" leave-one-season-out OOS R2 and the ICC(1) of its residual (variance-components form);
  the carry-over share of WAR lost and the carry-over share of the year-to-year covariance;
  the all-player depth reserve (p90 - p50 of club-season WAR lost, in WAR and in wins);
  the 2026 out-of-sample R2 of the "all" model fitted on the 240 club-seasons.
Exit 0 when every check passes, 1 otherwise. --results points at a (possibly perturbed) copy for the negative control.

Usage (library):    python3 verify_phase2.py --root "<MLB Total Research>" [--results <phase2_results.json>]
Usage (repository): python3 pipeline/verify_phase2.py [--results <phase2_results.json>]
"""
import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=None)
ap.add_argument("--results", default=os.path.join(os.path.dirname(HERE), "results", "phase2_results.json"))
a = ap.parse_args()
if a.root:
    def F(rel):
        return os.path.join(a.root, rel)
else:  # inside the public repository: inputs/ (or $INJURY_LUCK_INPUTS) and data_public/
    REPO = os.path.dirname(HERE)
    INP = os.environ.get("INJURY_LUCK_INPUTS", os.path.join(REPO, "inputs"))

    def F(rel):
        base = os.path.basename(rel)
        return os.path.join(REPO, "data_public", base) if base in ("placements_public.csv", "opening_day_40man_2015_2026.csv") else os.path.join(INP, base)
J = json.load(open(a.results))
RES_DIR = os.path.dirname(os.path.abspath(a.results))
fails, n_checks = [], 0


def check(name, got, want, tol=1e-6):
    global n_checks
    n_checks += 1
    ok = abs(float(got) - float(want)) <= tol * max(1.0, abs(float(want)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: recomputed {float(got):.10g} vs JSON {float(want):.10g}")
    if not ok:
        fails.append(name)


OUT = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
SP = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
PREV = {2015: 2014, 2016: 2015, 2017: 2016, 2018: 2017, 2019: 2018, 2021: 2019, 2022: 2021, 2023: 2022, 2024: 2023, 2025: 2024, 2026: 2025}
# ------------------------------------------------------------------------------------------------ schedule
g = pd.read_csv(F("Postseason_Injury_Risk/data/games_flat.csv"), usecols=["gamePk", "season", "gameType", "status", "date", "home_id", "away_id"])
g = g.query("gameType == 'R' and status in ['Final', 'Completed Early']").copy()
g["date"] = pd.to_datetime(g["date"])
cgm = pd.concat([g[["season", "date", "home_id"]].set_axis(["season", "date", "tid"], axis=1),
                 g[["season", "date", "away_id"]].set_axis(["season", "date", "tid"], axis=1)])
first_day = g.groupby("season")["date"].min(); last_day = g.groupby("season")["date"].max()
cg = {k: v["date"].sort_values().to_numpy() for k, v in cgm.groupby(["season", "tid"])}


def n_games(season, tid, d0, d1):
    arr = cg[(season, tid)]
    return int(((arr >= np.datetime64(d0)) & (arr <= np.datetime64(d1))).sum())


# ------------------------------------------------------------------------------------------------ R1 episodes, interval union
pl = pd.read_csv(F("Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv"), parse_dates=["il_start", "il_end"])
pl = pl.loc[pl["covid_era_blank"] == False].copy()  # noqa: E712
fg = pd.read_csv(F("_staging_tmp/fangraphs_war_2010_2025.csv")).dropna(subset=["mlbamid"])
fg["mlbamid"] = fg.mlbamid.astype(int)
logs = pd.read_csv(F("Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv"), usecols=["player_id", "gamePk", "date"])
logs = logs[logs.gamePk.isin(g.gamePk)]; logs["date"] = pd.to_datetime(logs["date"])
cand = []
m = pl[["txn_id", "mlbam", "il_start"]].merge(logs.rename(columns={"player_id": "mlbam"}), on="mlbam")
cand.append(m[m.date > m.il_start].groupby("txn_id").date.min())
played = fg.loc[fg.g.fillna(0) > 0, ["mlbamid", "season"]].drop_duplicates()
m = pl[["txn_id", "mlbam", "il_start"]].merge(played.rename(columns={"mlbamid": "mlbam"}), on="mlbam")
m = m[(m.season > m.il_start.dt.year) & (m.season <= 2014)]
cand.append(m.groupby("txn_id").season.min().map(first_day))
feed = pd.read_json(F("Sweeper_Injury_Risk/data/txns_live.jsonl"), lines=True)
feed["pid"] = feed.person.map(lambda d: d.get("id") if isinstance(d, dict) else None)
txt = feed.description.fillna("").str.lower()
hit = (txt.str.contains("restricted list") & txt.str.contains("placed")) | txt.str.contains(r"\bsuspended\b") | txt.str.contains("declared ineligible")
sus = feed.loc[hit & feed.pid.notna(), ["pid", "effectiveDate", "date"]].copy()
sus["d"] = pd.to_datetime(sus.effectiveDate.fillna(sus.date))
m = pl[["txn_id", "mlbam", "il_start"]].merge(sus.rename(columns={"pid": "mlbam"}).astype({"mlbam": int}), on="mlbam")
cand.append(m[m.d > m.il_start].groupby("txn_id").d.min())
c = pd.concat([x.rename(i) for i, x in enumerate(cand)], axis=1).min(axis=1)
new_end = pl.txn_id.map(c)
pl["il_end"] = pd.to_datetime(np.where(new_end.notna() & (pl.il_end.isna() | (new_end < pl.il_end)), new_end, pl.il_end))
eps = []
for season in sorted(first_day.index):
    if season < 2012 or season > 2026:
        continue
    lo, hi = first_day[season], last_day[season]
    q = pl[(pl.il_start.dt.year >= season - 1) & (pl.il_start.dt.year <= season) & (pl.il_start <= hi)].copy()
    q["e"] = q.il_end - pd.Timedelta(days=1)
    q.loc[q.il_end.isna(), "e"] = hi
    q = q[q.il_end.isna() | (q.il_end >= lo)]
    q["s"] = q.il_start.where(q.il_start > lo, lo)
    q["e"] = q.e.where(q.e < hi, hi)
    q = q[q.e >= q.s].sort_values(["mlbam", "club_id", "s", "e"])
    q["runmax"] = q.groupby(["mlbam", "club_id"])["e"].transform(lambda x: x.cummax().shift())
    q["new"] = q.runmax.isna() | (q.s > q.runmax + pd.Timedelta(days=1))
    q["eid"] = q.new.cumsum()
    e = q.groupby("eid").agg(mlbam=("mlbam", "first"), tid=("club_id", "first"), s=("s", "min"), e=("e", "max"), placed=("il_start", "min"))
    e["season"] = season
    eps.append(e)
E = pd.concat(eps, ignore_index=True)
E["tid"] = E.tid.astype(int)
Q = E.reset_index().merge(E.reset_index()[["index", "mlbam", "season", "tid", "s", "placed"]], on=["mlbam", "season"], suffixes=("", "_o"))
Q = Q[(Q.tid_o != Q.tid) & ((Q.placed_o > Q.placed) | ((Q.placed_o == Q.placed) & (Q.tid_o > Q.tid)))]
cap = Q.groupby("index").s_o.min() - pd.Timedelta(days=1)
E["e"] = E.e.where(~E.index.isin(cap.index) | (E.e <= E.index.map(cap)), E.index.map(cap))
E = E[E.e >= E.s].copy()
E["gm"] = [n_games(s, t, x, y) for s, t, x, y in zip(E.season, E.tid, E.s, E.e)]
gp = fg.groupby(["mlbamid", "season"]).g.max()
E = E.sort_values(["mlbam", "season", "s", "tid"]).reset_index(drop=True)
for (pid, season), idx in E.groupby(["mlbam", "season"]).groups.items():
    if season == 2026:
        continue
    over = E.loc[idx, "gm"].sum() + (0 if pd.isna(gp.get((pid, season))) else gp.get((pid, season))) - (60 if season == 2020 else 162)
    for i in list(idx)[::-1]:
        if over <= 0:
            break
        cut = min(E.at[i, "gm"], over); over -= cut
        E.at[i, "gm"] = E.at[i, "gm"] - cut
        if E.at[i, "gm"] > 0:
            arr = cg[(season, E.at[i, "tid"])]
            E.at[i, "e"] = pd.Timestamp(arr[(arr >= np.datetime64(E.at[i, "s"])) & (arr <= np.datetime64(E.at[i, "e"]))][int(E.at[i, "gm"]) - 1])
        else:
            E.at[i, "e"] = E.at[i, "s"]
E["days"] = (E.e - E.s).dt.days + 1
# ------------------------------------------------------------------------------------------------ Marcel
pw = fg.groupby(["mlbamid", "season"])["war"].sum()
gm_ps = E.groupby(["mlbam", "season"])["gm"].sum()
expo = {k: max((60 if k[1] == 2020 else 162) - gm_ps.get(k, 0), 1) for k in pw.index}
PW = pw.to_dict()


def marcel(pid, s, K=100):
    num = den = 0.0
    for w, lag in ((5, 1), (4, 2), (3, 3)):
        k = (pid, s - lag)
        if k in PW:
            num += w * PW[k]; den += w * expo[k]
    return max(num / (den + K), 0.0)


E["open_end"] = E.e >= E.season.map(last_day)
openset = set(zip(E.loc[E.open_end, "mlbam"], E.loc[E.open_end, "season"]))
EO = E[E.season.isin(OUT + [2026])].copy()
EO["wl"] = [marcel(p, s) * n for p, s, n in zip(EO.mlbam, EO.season, EO.gm)]
EO["carry"] = [(p, PREV[s]) in openset for p, s in zip(EO.mlbam, EO.season)]
CS = EO.groupby(["season", "tid"]).agg(war_lost=("wl", "sum")).reset_index()
CS = CS.merge(EO[EO.carry].groupby(["season", "tid"]).wl.sum().rename("carry").reset_index(), how="left").fillna({"carry": 0.0})
# ------------------------------------------------------------------------------------------------ opening-day roster
ro = pd.read_csv(F("IL_Team_Burden/v2_public/data_public/opening_day_40man_2015_2026.csv")).drop_duplicates(["season", "club_id", "mlbam"])
ppl = pd.read_csv(F("Postseason_Injury_Risk/data/people.csv"), usecols=["mlbam", "birth_date"], parse_dates=["birth_date"])
ro = ro.merge(ppl, on="mlbam", how="left")
ro["pj"] = [marcel(p, s) * 162 for p, s in zip(ro.mlbam, ro.season)]
ro["age"] = (pd.to_datetime(ro.season.astype(str) + "-06-30") - ro.birth_date).dt.days / 365.25
pdays = E.groupby(["mlbam", "season"]).days.sum()
ro["prev_days"] = [pdays.get((p, s - 1), 0.0) for p, s in zip(ro.mlbam, ro.season)]
ro["w"] = ro.pj.clip(lower=0.01)
ro["age_f"] = ro.groupby(["season", "club_id"]).age.transform(lambda x: x.fillna(x.mean()))
feat = ro.groupby(["season", "club_id"]).apply(lambda d: pd.Series({"proj_od": d.pj.sum(), "age_od": (d.age_f * d.w).sum() / d.w.sum(),
                                                                     "days_od": (d.prev_days * d.w).sum() / d.w.sum()}), include_groups=False).reset_index()
feat = feat.rename(columns={"club_id": "tid"})
CS = CS.merge(feat, on=["season", "tid"], how="left")
check("club-seasons with a roster", CS.proj_od.notna().sum(), 330, 0)
ts = pd.concat([pd.read_csv(os.path.join(RES_DIR, "team_season_phase2.csv"))[["season", "tid", "team_proj_od"]],
                pd.read_csv(os.path.join(RES_DIR, "team_season_2026_phase2.csv"))[["season", "tid", "team_proj_od"]]])
cmp_ = CS.merge(ts, on=["season", "tid"])
check("team_proj_od, 330 club-seasons: max abs difference", float((cmp_.proj_od - cmp_.team_proj_od).abs().max()), 0.0, 1e-6)
# ------------------------------------------------------------------------------------------------ P2.1
P21 = J["P2_1_preseason_control"]
st = pd.read_csv(F("Postseason_Injury_Risk/data/standings.csv"))[["season", "team_id", "W", "qualified"]].rename(columns={"team_id": "tid"})
T = CS[CS.season.isin(OUT)].merge(st, on=["season", "tid"]).sort_values(["tid", "season"])
T["q"] = T.qualified.astype(str).str.lower().isin(["true", "1"]).astype(int)
T["prevW"] = T.groupby("tid").W.shift(); T["prevWL"] = T.groupby("tid").war_lost.shift(); T["prevC"] = T.groupby("tid").carry.shift()
check("n club-seasons (outcome)", len(T), 300, 0)
M = T.dropna(subset=["prevW"])
fw = smf.ols("W ~ war_lost + proj_od + prevW + C(season)", data=M).fit(cov_type="cluster", cov_kwds={"groups": M.tid})
b = fw.params["war_lost"]
check("P2.1 wins per WAR lost", b, P21["wins"]["est"])
check("P2.1 wins SE (club-clustered)", fw.bse["war_lost"], P21["wins"]["se_cluster"])
sdw = T.groupby("season").war_lost.std().mean()
check("P2.1 one SD in wins", sdw * abs(b), P21["one_sd_wins"]["est"])
fl = smf.logit("q ~ war_lost + proj_od + C(season)", data=T).fit(disp=0)
check("P2.1 playoff OR per WAR lost", np.exp(fl.params["war_lost"]), P21["playoffs"]["or"])
# median-projection club at the p10 and p90 of WAR lost, averaged over seasons
for j, qq in ((0, .1), (2, .9)):
    X = T.assign(war_lost=T.war_lost.quantile(qq), proj_od=T.proj_od.median())
    check(f"P2.1 P(playoffs) at p{int(qq * 100)}", fl.predict(X).groupby(T.season).first().mean(), P21["playoffs"]["p_at_p10_p50_p90"][j])
# OOS R2 (all) and the ICC(1) of its residual
Q = T[T.season.isin(SP)].copy()
num = den = 0.0
for s in SP:
    tr, te = Q[Q.season != s], Q[Q.season == s]
    fit = smf.ols("war_lost ~ prevWL + proj_od + age_od + days_od", data=tr).fit()
    num += ((te.war_lost - fit.predict(te)) ** 2).sum(); den += ((te.war_lost - tr.war_lost.mean()) ** 2).sum()
    Q.loc[te.index, "u"] = te.war_lost - fit.predict(te)
check("P2.1 OOS R2 (all features)", 1 - num / den, P21["foreseeability"]["all"]["oos_r2"])
Q["ud"] = Q.u - Q.groupby("season").u.transform("mean")
k, n = Q.tid.nunique(), len(SP)
ssb = n * ((Q.groupby("tid").ud.mean() - Q.ud.mean()) ** 2).sum()
ssw = ((Q.ud - Q.groupby("tid").ud.transform("mean")) ** 2).sum()
msb, msw = ssb / (k - 1), ssw / ((k - 1) * (n - 1))
s2 = (msb - msw) / n
check("P2.5 ICC(1) of the unforeseen part", s2 / (s2 + msw), J["P2_5_persistence"]["primary"]["icc1"])
# ------------------------------------------------------------------------------------------------ carry-over
check("P2.7 carry-over share of WAR lost", T.carry.sum() / T.war_lost.sum(), J["P2_7_levers"]["a_carry_over"]["carry_share"]["est"])
Y = T.dropna(subset=["prevWL"]).copy()
for v in ("war_lost", "carry", "prevWL"):
    Y[v + "_d"] = Y[v] - Y.groupby("season")[v].transform("mean")
check("P2.5 carry-over share of the year-to-year covariance", (Y.carry_d * Y.prevWL_d).sum() / (Y.war_lost_d * Y.prevWL_d).sum(),
      J["P2_5_persistence"]["carry_over_decomposition"]["carry_share_of_cov"]["est"])
# ------------------------------------------------------------------------------------------------ depth reserve
res_ = T.war_lost.quantile(.9) - T.war_lost.quantile(.5)
check("P2.7 all-player depth reserve (WAR)", res_, J["P2_7_levers"]["b_depth"]["all"]["reserve_war"]["est"])
check("P2.7 all-player depth reserve (wins)", res_ * abs(b), J["P2_7_levers"]["b_depth"]["all"]["reserve_wins"]["est"])
# ------------------------------------------------------------------------------------------------ 2026
T26 = CS[CS.season == 2026].merge(T[T.season == 2025][["tid", "war_lost"]].rename(columns={"war_lost": "prevWL"}), on="tid")
fit = smf.ols("war_lost ~ prevWL + proj_od + age_od + days_od", data=Q).fit()
check("P2.8 2026 OOS R2 (all features, fitted through 2025)",
      1 - ((T26.war_lost - fit.predict(T26)) ** 2).sum() / ((T26.war_lost - Q.war_lost.mean()) ** 2).sum(),
      J["P2_8_check_2026"]["all"]["oos_r2_2026"])
top = J["P2_8_check_2026"]["ranking"][0]
T26["u"] = T26.war_lost - fit.predict(T26)
n_checks += 1
best = T26.sort_values("u", ascending=False).iloc[0]
ok = abs(best.u - top["unexpected"]) < 1e-6
print(f"{'PASS' if ok else 'FAIL'}  P2.8 2026 top unexpected club-season: recomputed {best.u:.6f} vs JSON {top['unexpected']:.6f} ({top['club']})")
if not ok:
    fails.append("2026 top")
print(f"\n{n_checks - len(fails)} of {n_checks} checks passed")
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("verify_phase2: OK")
