"""
indep_recompute.py - independent recomputation of the injury-loss headline values for the 2026-10-12 accuracy audit.

Written from the paper's own description (its Data and Methods sections and the sealed Phase 2 addendum), not from the
pipeline: it imports nothing from pipeline/, uses its own episode builder (interval arithmetic on placement dates),
its own Marcel projection, and statsmodels for the models. Compares every value with the club-season table and the
results JSON and prints a PASS/FAIL line per check.

Usage: python3 indep_recompute.py <repo root with data_public/ and inputs/> <results dir>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

ROOT, RES = sys.argv[1], sys.argv[2]
OUT = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
PREV = {s: (2019 if s == 2021 else s - 1) for s in OUT + [2026]}
FORE = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
J = json.load(open(f"{RES}/phase2_results.json"))
checks = []


def ck(name, mine, ref, tol):
    ok = (abs(mine - ref) <= tol) if (mine is not None and ref is not None and np.isfinite(mine) and np.isfinite(ref)) else False
    checks.append((name, ok, mine, ref))
    print(f"{'PASS' if ok else 'FAIL'}  {name:62s} mine={mine:.6g}  json={ref:.6g}")


# ---------------------------------------------------------------- inputs
G = pd.read_csv(f"{ROOT}/inputs/games_flat.csv")
G = G[(G.gameType == "R") & G.status.isin(["Final", "Completed Early"])].copy()
G["date"] = pd.to_datetime(G.date)
sched = defaultdict(list)
for s, d, h, a in zip(G.season, G.date, G.home_id, G.away_id):
    sched[(s, h)].append(d); sched[(s, a)].append(d)
sched = {k: np.array(sorted(v), dtype="datetime64[ns]") for k, v in sched.items()}
first_day = G.groupby("season").date.min().to_dict(); last_day = G.groupby("season").date.max().to_dict()

PL = pd.read_csv(f"{ROOT}/data_public/placements_public.csv", parse_dates=["il_start", "il_end"])
PL = PL[~PL.covid_era_blank].copy()
FG = pd.read_csv(f"{ROOT}/inputs/fangraphs_war_2010_2025.csv").dropna(subset=["mlbamid"])
FG["pid"] = FG.mlbamid.astype(int)
GL = pd.read_csv(f"{ROOT}/inputs/gamelogs_flat.csv", usecols=["player_id", "season", "date", "gamePk", "GS"])
GL = GL[GL.gamePk.isin(set(G.gamePk))]
GL["date"] = pd.to_datetime(GL.date)
ST = pd.read_csv(f"{ROOT}/inputs/standings.csv")
PE = pd.read_csv(f"{ROOT}/inputs/people.csv", usecols=["mlbam", "birth_date"])
BIRTH = dict(zip(PE.mlbam, pd.to_datetime(PE.birth_date, errors="coerce")))
ROS = pd.read_csv(f"{ROOT}/data_public/opening_day_40man_2015_2026.csv").drop_duplicates(["season", "club_id", "mlbam"])

# restricted list / suspension / ineligible transactions (paper Section 2, R1)
rx = re.compile(r"placed .* on the restricted list|\bsuspended\b|declared ineligible", re.I)
susp = defaultdict(list)
with open(f"{ROOT}/inputs/txns_live.jsonl") as fh:
    for line in fh:
        t = json.loads(line)
        if rx.search(t.get("description") or ""):
            p = (t.get("person") or {}).get("id")
            if p:
                susp[int(p)].append(pd.Timestamp(t.get("effectiveDate") or t.get("date")))

# ---------------------------------------------------------------- R1 placement ends
first_app = GL.groupby("player_id").date.apply(lambda s: np.sort(s.unique()))
fg_seasons = FG[FG.g.fillna(0) > 0].groupby("pid").season.apply(lambda s: sorted(set(s)))


def r1_end(pid, start, census_end):
    c = [census_end] if pd.notna(census_end) else []
    a = first_app.get(pid)
    if a is not None:
        later = a[a > np.datetime64(start)]
        if len(later):
            c.append(pd.Timestamp(later[0]))
    for y in fg_seasons.get(pid, []):
        if start.year < y <= 2014:
            c.append(first_day[y]); break
    for d in sorted(susp.get(pid, [])):
        if d > start:
            c.append(d); break
    return min(c) if c else pd.NaT


PL["end_r1"] = [r1_end(p, s, e) for p, s, e in zip(PL.mlbam, PL.il_start, PL.il_end)]


# ---------------------------------------------------------------- episodes per season
def ngames(s, tid, a, b):
    d = sched.get((s, tid))
    if d is None or b < a:
        return 0
    return int(((d >= np.datetime64(a)) & (d <= np.datetime64(b))).sum())


rows = []
for s in range(2012, 2027):
    if s not in first_day:
        continue
    a, b = first_day[s], last_day[s]
    x = PL[(PL.il_start <= b) & (PL.end_r1.fillna(b) >= a) & PL.il_start.dt.year.isin([s - 1, s])].copy()
    x["st"] = x.il_start.where(x.il_start > a, a)
    x["en"] = (x.end_r1.fillna(b + pd.Timedelta(days=1)) - pd.Timedelta(days=1))
    x["en"] = x.en.where(x.en < b, b)
    x = x[x.en >= x.st].sort_values(["mlbam", "club_id", "st"])
    for (pid, tid), g in x.groupby(["mlbam", "club_id"]):
        cur = None
        for st, en, dx, il0 in zip(g.st, g.en, g.dx.fillna("").astype(str), g.il_start):
            if cur and st <= cur["en"] + pd.Timedelta(days=1):
                cur["en"] = max(cur["en"], en); cur["dx_all"] += " || " + dx; cur["n_pl"] += 1
            else:
                if cur:
                    rows.append(cur)
                cur = dict(season=s, pid=int(pid), tid=int(tid), st=st, en=en, dx=dx, il0=il0, dx_all=dx, n_pl=1)
        rows.append(cur)
E = pd.DataFrame(rows)
# cross-club overlap: an episode ends the day before the same player's later-placed episode at another club begins
E = E.sort_values(["pid", "season", "il0", "tid"]).reset_index(drop=True)
keep = np.ones(len(E), bool)
for (pid, s), ix in E.groupby(["pid", "season"]).groups.items():
    ix = list(ix)
    if E.loc[ix, "tid"].nunique() < 2:
        continue
    for u, i in enumerate(ix):
        later = [E.at[j, "st"] for j in ix[u + 1:] if E.at[j, "tid"] != E.at[i, "tid"]]
        if later:
            cut = min(later) - pd.Timedelta(days=1)
            if E.at[i, "en"] > cut:
                if cut < E.at[i, "st"]:
                    keep[i] = False
                else:
                    E.at[i, "en"] = cut
E = E[keep].reset_index(drop=True)
E["gm"] = [ngames(s, t, a, b) for s, t, a, b in zip(E.season, E.tid, E.st, E.en)]
# games-played cap: games missed + FanGraphs games played <= team games (162; 60 in 2020); trim latest episodes first
gp = FG.groupby(["pid", "season"]).g.max().to_dict()
for (pid, s), ix in E.groupby(["pid", "season"]).groups.items():
    if s == 2026:
        continue
    g_ = gp.get((pid, s), 0); g_ = 0 if pd.isna(g_) else g_
    excess = E.loc[ix, "gm"].sum() + g_ - (60 if s == 2020 else 162)
    for i in sorted(ix, key=lambda i: (E.at[i, "st"], E.at[i, "tid"]), reverse=True):
        if excess <= 0:
            break
        cut_n = min(E.at[i, "gm"], excess); E.at[i, "gm"] -= cut_n; excess -= cut_n
        d = sched[(s, E.at[i, "tid"])]; d = d[(d >= np.datetime64(E.at[i, "st"])) & (d <= np.datetime64(E.at[i, "en"]))]
        E.at[i, "en"] = pd.Timestamp(d[E.at[i, "gm"] - 1]) if E.at[i, "gm"] > 0 else E.at[i, "st"]
E["days"] = (E.en - E.st).dt.days + 1

# ---------------------------------------------------------------- Marcel projection (eq. 1)
F = FG.groupby(["pid", "season"]).war.sum()
gm_ps = E.groupby(["pid", "season"]).gm.sum()
EXP = {}
for (p, s), w in F.items():
    EXP[(p, s)] = (w, max(1, (60 if s == 2020 else 162) - gm_ps.get((p, s), 0)))


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
lastd = {s: last_day[s] for s in last_day}
open_prev = set((p, s) for p, s, en in zip(E.pid, E.season, E.en) if en == lastd[s])
EO["carry"] = [(p, PREV[s]) in open_prev for p, s in zip(EO.pid, EO.season)]
T = EO.groupby(["season", "tid"]).agg(episodes=("pid", "size"), gm=("gm", "sum"), wl=("wl", "sum"), il_days=("days", "sum")).reset_index()
T = T.merge(EO[EO.carry].groupby(["season", "tid"]).wl.sum().rename("wl_carry").reset_index(), how="left").fillna({"wl_carry": 0})
T["wl_new"] = T.wl - T.wl_carry

# opening-day projection and preseason features (eq. 3)
days_ps = E.groupby(["pid", "season"]).days.sum().to_dict()
feat = []
for (s, tid), g in ROS.groupby(["season", "club_id"]):
    if s not in OUT:
        continue
    ids = g.mlbam.astype(int).tolist()
    proj = np.array([rate(p, s) * 162 for p in ids]); w = np.clip(proj, 0.01, None)
    ages = np.array([((pd.Timestamp(f"{s}-06-30") - BIRTH[p]).days / 365.25) if (p in BIRTH and pd.notna(BIRTH[p])) else np.nan for p in ids])
    ages = np.where(np.isfinite(ages), ages, np.nanmean(ages))
    ilp = np.array([days_ps.get((p, s - 1), 0.0) for p in ids])
    V = sum(pr for p, pr in zip(ids, proj) if (p, PREV[s]) in open_prev)
    feat.append(dict(season=s, tid=tid, tp_od=proj.sum(), age_od=np.average(ages, weights=w), ilp_od=np.average(ilp, weights=w), V=V))
T = T.merge(pd.DataFrame(feat), on=["season", "tid"], how="left")
T = T.merge(ST[["season", "team_id", "W", "qualified"]].rename(columns={"team_id": "tid"}), on=["season", "tid"], how="left")
T["q"] = T.qualified.astype(str).str.lower().isin(["true", "1"]).astype(int)
T = T.sort_values(["tid", "season"])
T["W_prev"] = T.groupby("tid").W.shift(1); T["wl_prev"] = T.groupby("tid").wl.shift(1)
T["wl_new_prev"] = T.groupby("tid").wl_new.shift(1)

# ---------------------------------------------------------------- compare the club-season table with the pipeline's
P2 = pd.read_csv(f"{RES}/team_season_phase2.csv")
M = P2.merge(T, on=["season", "tid"])
ck("club-seasons", len(T), 300, 0)
ck("episodes in outcome seasons", len(EO), J["meta"]["n_episodes_outcome_seasons"], 0)
ck("max |WAR lost - pipeline| over 300 club-seasons", float((M.wl - M.war_lost).abs().max()), 0.0, 1e-6)
ck("max |games missed - pipeline|", float((M.gm - M.games_missed).abs().max()), 0.0, 0)
ck("max |opening-day projection - pipeline|", float((M.tp_od - M.team_proj_od).abs().max()), 0.0, 1e-6)
ck("max |roster age - pipeline|", float((M.age_od - M.roster_age_od).abs().max()), 0.0, 1e-6)
ck("max |roster prior IL days - pipeline|", float((M.ilp_od - M.roster_il_days_prev_od).abs().max()), 0.0, 1e-6)
ck("max |carry-over WAR lost - pipeline|", float((M["wl_carry_y"] - M["wl_carry_x"]).abs().max()), 0.0, 1e-6)
ck("games missed per episode", EO.gm.mean(), J["P2_3_duration_rule"]["A_primary"]["games_missed_per_episode"], 1e-9)

# ---------------------------------------------------------------- models (statsmodels, written from Methods eqs 4-9)
P21 = J["P2_1_preseason_control"]
D = T[T.W_prev.notna()].copy()
fit = smf.ols("W ~ wl + tp_od + W_prev + C(season)", D).fit(cov_type="cluster", cov_kwds={"groups": D.tid})
b = fit.params["wl"]; lo, hi = fit.conf_int().loc["wl"]
ck("wins per WAR lost (eq. 4)", b, P21["wins"]["est"], 1e-9)
ck("wins per WAR lost, cluster lower 95% (normal)", lo, P21["wins"]["lo_cluster"], 2e-3)
ck("wins per WAR lost, cluster upper 95% (normal)", hi, P21["wins"]["hi_cluster"], 2e-3)
ck("n, wins model", len(D), P21["wins"]["n"], 0)
sdw = T.groupby("season").wl.std().mean()
ck("within-season SD of WAR lost (mean of 10 season SDs, ddof 1)", sdw, P21["sd_war_within_season"], 1e-9)
ck("one SD in wins", sdw * abs(b), P21["one_sd_wins"]["est"], 1e-9)
ck("p10 to p90 in wins", (T.wl.quantile(.9) - T.wl.quantile(.1)) * abs(b), P21["p10_p90_wins"]["est"], 1e-9)
lg = smf.logit("q ~ wl + tp_od + C(season)", T).fit(disp=0)
ck("playoff exp(logit coefficient) per WAR lost (eq. 5)", float(np.exp(lg.params["wl"])), P21["playoffs"]["or"], 1e-6)
tmed = T.tp_od.median(); seasons = sorted(T.season.unique())
probs = []
for qq in (.1, .5, .9):
    l_ = T.wl.quantile(qq)
    probs.append(np.mean([lg.predict(pd.DataFrame({"wl": [l_], "tp_od": [tmed], "season": [s]}))[0] for s in seasons]))
for k, nm in enumerate(("p10", "p50", "p90")):
    ck(f"P(playoffs) at {nm} (eq. 6)", probs[k], P21["playoffs"]["p_at_p10_p50_p90"][k], 1e-6)


def loso(df, cols, y="wl", demean=False):
    df = df[df.season.isin(FORE)].copy()
    if demean:
        for c in cols + [y]:
            df[c] = df[c] - df.groupby("season")[c].transform("mean")
    sse = sst = 0.0; res = pd.Series(index=df.index, dtype=float)
    for s in FORE:
        tr, te = df[df.season != s], df[df.season == s]
        m = sm.OLS(tr[y], sm.add_constant(tr[cols])).fit()
        p_ = m.predict(sm.add_constant(te[cols], has_constant="add"))
        sse += ((te[y] - p_) ** 2).sum(); sst += ((te[y] - (0.0 if demean else tr[y].mean())) ** 2).sum()
        res.loc[te.index] = te[y] - p_
    return 1 - sse / sst, res


FEATS = ["tp_od", "age_od", "ilp_od"]
r2_all, u = loso(T, ["wl_prev"] + FEATS)
ck("LOSO R2, all features (eq. 7)", r2_all, P21["foreseeability"]["all"]["oos_r2"], 1e-9)
ck("LOSO R2, previous season only", loso(T, ["wl_prev"])[0], P21["foreseeability"]["prior"]["oos_r2"], 1e-9)
ck("LOSO R2, roster features only", loso(T, FEATS)[0], P21["foreseeability"]["roster"]["oos_r2"], 1e-9)
ck("LOSO R2, season-demeaned", loso(T, ["wl_prev"] + FEATS, demean=True)[0], P21["foreseeability"]["all"]["oos_r2_season_demeaned"], 1e-9)
T.loc[u.index, "u"] = u
TU = T[T.season.isin(FORE)]
sdu = TU.groupby("season").u.std().mean()
ck("SD of unforeseen part, wins", sdu * abs(b), P21["unexpected"]["sd_wins"]["est"], 1e-9)


def icc31(df, col):
    Y = df.pivot_table(index="tid", columns="season", values=col).to_numpy(float)
    Y = Y - Y.mean(0, keepdims=True); k, n = Y.shape
    cm = Y.mean(1); msb = n * ((cm - Y.mean()) ** 2).sum() / (k - 1)
    mse = ((Y - cm[:, None]) ** 2).sum() / ((k - 1) * (n - 1))   # season means already removed
    return (msb - mse) / (msb + (n - 1) * mse)


ck("ICC of the unforeseen part (eq. 9)", icc31(TU, "u"), J["P2_5_persistence"]["primary"]["icc1"], 1e-9)
ck("carry-over share of WAR lost", T.wl_carry.sum() / T.wl.sum(), J["P2_7_levers"]["a_carry_over"]["carry_share"]["est"], 1e-9)
Mx = T[T.wl_prev.notna()].copy()
dm = lambda c: (Mx[c] - Mx.groupby("season")[c].transform("mean")).to_numpy()  # noqa: E731
ck("carry-over share of year-to-year covariance (eq. 8)", np.mean(dm("wl_carry") * dm("wl_prev")) / np.mean(dm("wl") * dm("wl_prev")),
   J["P2_5_persistence"]["carry_over_decomposition"]["carry_share_of_cov"]["est"], 1e-9)
ck("mean projected WAR on the IL at prior season end (V)", Mx.V.mean(), J["P2_7_levers"]["a_carry_over"]["V_mean_war"]["est"], 1e-9)
ck("all-player depth reserve (p90 - p50), WAR", T.wl.quantile(.9) - T.wl.quantile(.5), J["P2_7_levers"]["b_depth"]["all"]["reserve_war"]["est"], 1e-9)
ck("share of episodes open on final day", float((EO.en == EO.season.map(lastd)).mean()), J["P2_3_duration_rule"]["A_primary"]["share_episodes_open_final_day"], 1e-9)
ck("share of WAR lost open on final day", float(EO.loc[EO.en == EO.season.map(lastd), "wl"].sum() / EO.wl.sum()), J["P2_3_duration_rule"]["A_primary"]["share_war_lost_open_final_day"], 1e-9)

E.to_csv(f"{RES}/../audit_episodes_all.csv", index=False)
T.to_csv(f"{RES}/../audit_team_season.csv", index=False)
nf = sum(1 for c in checks if not c[1])
print(f"\n{len(checks)} checks, {nf} failed")
sys.exit(1 if nf else 0)
