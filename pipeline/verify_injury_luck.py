"""
verify_injury_luck.py — independent second implementation for injury_luck_results.json (Prompt 21 §4 step 4).

Imports nothing from injury_luck.py or the twin. Rebuilds the public episodes from placements_public.csv with its
own (interval-union) code, its own game counting and Marcel projection, then recomputes and checks:
  E1 mean / within-season SD / p10 / p90;  E2 wins per WAR lost (statsmodels formula API, club-clustered);
  E4 leave-one-season-out OOS R2 for the three models (statsmodels);  E7 top-1 / top-3 share and Gini;
  E11 primary ICC(1) point estimate (variance-components form);  and a hand walk of the five largest episodes
  (placements -> dates -> schedule games -> prior-season fWAR and exposure -> WAR lost), each printed.
Exit 0 when every check passes; exit 1 otherwise.

Phase 1b (DEVIATIONS.md #10): when the results JSON says meta.episode_rule == "r1", the verifier applies its own
implementation of the R1 episode-end repair (first MLB pitching appearance; first pre-2015 season with games played;
restricted-list / suspension / ineligible transaction; games missed + games played <= team games) and additionally
checks that no player-season has games missed + FanGraphs games played above team games.

Usage (from the repository root): python3 pipeline/verify_injury_luck.py [--results <injury_luck_results.json>]
Inputs resolve through pipeline/paths.py (data_public/ and inputs/). Public-repository copy: paths only changed.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import resolve  # noqa: E402  (path lookup only; no estimation code is shared with injury_luck.py)

ap = argparse.ArgumentParser()
ap.add_argument("--results", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "injury_luck_results.json"))
a = ap.parse_args()
J = json.load(open(a.results))
TOL = 1e-6
fails, n_checks = [], 0


def check(name, got, want, tol=TOL):
    global n_checks
    n_checks += 1
    ok = (got is None and want is None) or (abs(float(got) - float(want)) <= tol * max(1.0, abs(float(want))))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: recomputed {float(got):.10g} vs JSON {float(want):.10g}")
    if not ok:
        fails.append(name)


OUT_SEASONS = {2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025}
# ---------------------------------------------------------------------------------------------- schedule
g = pd.read_csv(resolve("Postseason_Injury_Risk/data/games_flat.csv"), usecols=["gamePk", "season", "gameType", "status", "date", "home_id", "away_id"])
g = g.query("gameType == 'R' and status in ['Final', 'Completed Early']").copy()
g["date"] = pd.to_datetime(g["date"])
club_games = pd.concat([g[["season", "date", "home_id"]].set_axis(["season", "date", "tid"], axis=1),
                        g[["season", "date", "away_id"]].set_axis(["season", "date", "tid"], axis=1)])
first_day = g.groupby("season")["date"].min(); last_day = g.groupby("season")["date"].max()
cg = {k: v["date"].sort_values().to_numpy() for k, v in club_games.groupby(["season", "tid"])}


def n_games(season, tid, d0, d1):
    arr = cg[(season, tid)]
    return int(((arr >= np.datetime64(d0)) & (arr <= np.datetime64(d1))).sum())


# ---------------------------------------------------------------------------------------------- episodes (interval union)
pl = pd.read_csv(resolve("Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv"), parse_dates=["il_start", "il_end"])
pl = pl.loc[pl["covid_era_blank"] == False].copy()  # noqa: E712
fg = pd.read_csv(resolve("_staging_tmp/fangraphs_war_2010_2025.csv")).dropna(subset=["mlbamid"])
fg["mlbamid"] = fg.mlbamid.astype(int)
RULE = J.get("meta", {}).get("episode_rule", "sealed")
if RULE == "r1":
    # independent R1: candidate end dates per placement, earliest wins, never later than the census end
    logs = pd.read_csv(resolve("Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv"), usecols=["player_id", "gamePk", "date"])
    logs = logs[logs.gamePk.isin(g.gamePk)]
    logs["date"] = pd.to_datetime(logs["date"])
    cand = []
    m = pl[["txn_id", "mlbam", "il_start"]].merge(logs.rename(columns={"player_id": "mlbam"}), on="mlbam")
    cand.append(m[m.date > m.il_start].groupby("txn_id").date.min())
    played = fg.loc[fg.g.fillna(0) > 0, ["mlbamid", "season"]].drop_duplicates()
    m = pl[["txn_id", "mlbam", "il_start"]].merge(played.rename(columns={"mlbamid": "mlbam"}), on="mlbam")
    m = m[(m.season > m.il_start.dt.year) & (m.season <= 2014)]
    cand.append(m.groupby("txn_id").season.min().map(first_day))
    feed = pd.read_json(resolve("Sweeper_Injury_Risk/data/txns_live.jsonl"), lines=True)
    feed["pid"] = feed.person.map(lambda d: d.get("id") if isinstance(d, dict) else None)
    txt = feed.description.fillna("").str.lower()
    hit = (txt.str.contains("restricted list") & txt.str.contains("placed")) | txt.str.contains(r"\bsuspended\b") | txt.str.contains("declared ineligible")
    sus = feed.loc[hit & feed.pid.notna(), ["pid", "effectiveDate", "date"]].copy()
    sus["d"] = pd.to_datetime(sus.effectiveDate.fillna(sus.date))
    m = pl[["txn_id", "mlbam", "il_start"]].merge(sus.rename(columns={"pid": "mlbam"}).astype({"mlbam": int}), on="mlbam")
    cand.append(m[m.d > m.il_start].groupby("txn_id").d.min())
    c = pd.concat([x.rename(i) for i, x in enumerate(cand)], axis=1).min(axis=1)
    new_end = pl.txn_id.map(c)
    pl["il_end"] = np.where(new_end.notna() & (pl.il_end.isna() | (new_end < pl.il_end)), new_end, pl.il_end)
    pl["il_end"] = pd.to_datetime(pl.il_end)
eps = []
for season in sorted(first_day.index):
    if season < 2012 or season > 2025:
        continue
    lo, hi = first_day[season], last_day[season]
    q = pl[(pl.il_start.dt.year >= season - 1) & (pl.il_start.dt.year <= season) & (pl.il_start <= hi)].copy()
    q["e"] = q.il_end - pd.Timedelta(days=1)
    q.loc[q.il_end.isna(), "e"] = hi
    q = q[q.il_end.isna() | (q.il_end >= lo)]
    q["s"] = q.il_start.where(q.il_start > lo, lo)
    q["e"] = q.e.where(q.e < hi, hi)
    q = q[q.e >= q.s].sort_values(["mlbam", "club_id", "s", "e"])
    # new episode when the start is > 1 day after the running max end of the same player-club
    q["runmax"] = q.groupby(["mlbam", "club_id"])["e"].transform(lambda x: x.cummax().shift())
    q["new"] = q.runmax.isna() | (q.s > q.runmax + pd.Timedelta(days=1))
    q["eid"] = q.new.cumsum()
    e = q.groupby("eid").agg(mlbam=("mlbam", "first"), tid=("club_id", "first"), s=("s", "min"), e=("e", "max"), name=("name", "first"),
                             placed=("il_start", "min"))
    e["season"] = season
    eps.append(e)
E = pd.concat(eps, ignore_index=True)
E["gm"] = [n_games(s, t, x, y) for s, t, x, y in zip(E.season, E.tid, E.s, E.e)]
gp = fg.groupby(["mlbamid", "season"]).g.max()
if RULE == "r1":
    # cross-club overlap: the end of an episode is capped at the day before the earliest start among the player's
    # episodes at other clubs that were placed later the same season; an episode left empty is removed
    Q = E.reset_index().merge(E.reset_index()[["index", "mlbam", "season", "tid", "s", "placed"]], on=["mlbam", "season"], suffixes=("", "_o"))
    Q = Q[(Q.tid_o != Q.tid) & ((Q.placed_o > Q.placed) | ((Q.placed_o == Q.placed) & (Q.tid_o > Q.tid)))]
    cap = Q.groupby("index").s_o.min() - pd.Timedelta(days=1)
    E["e"] = E.e.where(~E.index.isin(cap.index) | (E.e <= E.index.map(cap)), E.index.map(cap))
    E = E[E.e >= E.s].copy()
    E["gm"] = [n_games(s, t, x, y) for s, t, x, y in zip(E.season, E.tid, E.s, E.e)]
    # games-played cap: trim club games from the end of the player's latest episodes of that season
    E = E.sort_values(["mlbam", "season", "s", "tid"]).reset_index(drop=True)
    for (pid, season), idx in E.groupby(["mlbam", "season"]).groups.items():
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
    eps = [E[E.season == y].drop(columns=["gm", "placed"]) for y in sorted(E.season.unique())]
chk_gp = E.groupby(["mlbam", "season"]).gm.sum().reset_index()
chk_gp["g"] = [0 if pd.isna(gp.get((p, y))) else gp.get((p, y)) for p, y in zip(chk_gp.mlbam, chk_gp.season)]
n_over = int((chk_gp.gm + chk_gp.g > np.where(chk_gp.season == 2020, 60, 162)).sum())
print(f"player-seasons 2012-2025 with games missed + games played > team games: {n_over}")

# ---------------------------------------------------------------------------------------------- Marcel
pw = fg.groupby(["mlbamid", "season"])["war"].sum()
gm_ps = E.groupby(["mlbam", "season"])["gm"].sum()
expo = {k: max((60 if k[1] == 2020 else 162) - gm_ps.get(k, 0), 1) for k in pw.index}


def marcel(pid, s, K=100, floor=True):
    """floor=True for WAR lost; the roster projection (team_proj) sums the unfloored rate, as framing_f1.py does."""
    num = den = 0.0
    for w, lag in ((5, 1), (4, 2), (3, 3)):
        k = (pid, s - lag)
        if k in pw.index:
            num += w * pw[k]; den += w * expo[k]
    return max(num / (den + K), 0.0) if floor else num / (den + K)


E = E[E.season.isin(OUT_SEASONS)].copy()
E["wl"] = [marcel(p, s) * n for p, s, n in zip(E.mlbam, E.season, E.gm)]
CS = E.groupby(["season", "tid"]).wl.sum().rename("war_lost").reset_index()
stand = pd.read_csv(resolve("Postseason_Injury_Risk/data/standings.csv"))[["season", "team_id", "W"]].rename(columns={"team_id": "tid"})
CS = CS.merge(stand, on=["season", "tid"])
ABBR_T = {"ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112, "CHW": 145, "CIN": 113, "CLE": 114, "COL": 115, "DET": 116,
          "HOU": 117, "KCR": 118, "LAA": 108, "LAD": 119, "MIA": 146, "FLA": 146, "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147,
          "OAK": 133, "ATH": 133, "PHI": 143, "PIT": 134, "SDP": 135, "SEA": 136, "SFG": 137, "STL": 138, "TBR": 139, "TEX": 140,
          "TOR": 141, "WSN": 120}
r = fg[fg.season.isin(OUT_SEASONS)].assign(tid=lambda d: d.team.map(ABBR_T)).dropna(subset=["tid"]).drop_duplicates(["mlbamid", "season", "tid"])
r["pj"] = [marcel(p, s, floor=False) * 162 for p, s in zip(r.mlbamid, r.season)]
CS = CS.merge(r.groupby(["season", "tid"]).pj.sum().rename("proj").reset_index(), on=["season", "tid"], how="left")
CS = CS.sort_values(["tid", "season"])
CS["prevW"] = CS.groupby("tid").W.shift(); CS["prevWL"] = CS.groupby("tid").war_lost.shift()
check("n club-seasons", len(CS), 300, 0)
if RULE == "r1":
    check("R1: player-seasons with games missed + games played > team games", n_over, 0, 0)

# E1
check("E1.mean", CS.war_lost.mean(), J["E1"]["mean"])
check("E1.sd_within_season", CS.groupby("season").war_lost.std().mean(), J["E1"]["sd_within_season"])
check("E1.p10", CS.war_lost.quantile(.1), J["E1"]["p10"])
check("E1.p90", CS.war_lost.quantile(.9), J["E1"]["p90"])
# E2
m = smf.ols("W ~ war_lost + proj + prevW + C(season)", data=CS.dropna(subset=["prevW"])).fit(cov_type="cluster", cov_kwds={"groups": CS.dropna(subset=["prevW"]).tid})
check("E2.est", m.params["war_lost"], J["E2"]["est"])
check("E2.se (cluster)", m.bse["war_lost"], J["E2"]["se"])
# E4 (features: roster age and prior-season IL days, rebuilt here)
ppl = pd.read_csv(resolve("Postseason_Injury_Risk/data/people.csv"), usecols=["mlbam", "birth_date"], parse_dates=["birth_date"])
r = r.merge(ppl.rename(columns={"mlbam": "mlbamid"}), on="mlbamid", how="left")
r["age"] = (pd.to_datetime(r.season.astype(str) + "-06-30") - r.birth_date).dt.days / 365.25
Eall = pd.concat(eps, ignore_index=True)
Eall["days"] = (Eall.e - Eall.s).dt.days + 1
pdays = Eall.groupby(["mlbam", "season"]).days.sum()
r["prev_days"] = [pdays.get((p, s - 1), 0.0) for p, s in zip(r.mlbamid, r.season)]
r["w"] = r.pj.clip(lower=0.01)
r["age_f"] = r.groupby(["season", "tid"]).age.transform(lambda x: x.fillna(x.mean()))
feat = r.groupby(["season", "tid"]).apply(lambda d: pd.Series({"age_w": (d.age_f * d.w).sum() / d.w.sum(), "days_w": (d.prev_days * d.w).sum() / d.w.sum()}), include_groups=False).reset_index()
CS = CS.merge(feat, on=["season", "tid"], how="left")
SP = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
Q = CS[CS.season.isin(SP)].copy()
forms = {"prior_year_only": "war_lost ~ prevWL", "roster_only": "war_lost ~ proj + age_w + days_w", "all": "war_lost ~ prevWL + proj + age_w + days_w"}
for nm, fm in forms.items():
    num = den = 0.0
    for s in SP:
        tr, te = Q[Q.season != s], Q[Q.season == s]
        fit = smf.ols(fm, data=tr).fit()
        num += ((te.war_lost - fit.predict(te)) ** 2).sum(); den += ((te.war_lost - tr.war_lost.mean()) ** 2).sum()
        if nm == "all":
            Q.loc[te.index, "u"] = te.war_lost - fit.predict(te)
    check(f"E4.{nm}.oos_r2", 1 - num / den, J["E4"][nm]["oos_r2"])
# E11 primary ICC(1): variance-components form on season-demeaned residuals
Q["ud"] = Q.u - Q.groupby("season").u.transform("mean")
k, n = Q.tid.nunique(), len(SP)
grand = Q.ud.mean()
ssb = n * ((Q.groupby("tid").ud.mean() - grand) ** 2).sum()
ssw = ((Q.ud - Q.groupby("tid").ud.transform("mean")) ** 2).sum()
msb, msw = ssb / (k - 1), ssw / ((k - 1) * (n - 1))
s2_club = (msb - msw) / n
check("E11.primary.icc1", s2_club / (s2_club + msw), J["E11"]["primary"]["icc1"])
# E7
E = E.merge(CS[["season", "tid", "war_lost"]], on=["season", "tid"])
E["share"] = E.wl / E.war_lost
E["rk"] = E.groupby(["season", "tid"]).wl.rank(ascending=False, method="first")
check("E7.top1_share_mean", E[E.rk == 1].share.sum() / 300, J["E7"]["top1_share_mean"])
check("E7.top3_share_mean", E[E.rk <= 3].share.sum() / 300, J["E7"]["top3_share_mean"])
x = np.sort(CS.war_lost.to_numpy()); cum = np.cumsum(x)
check("E7.gini", 1 - 2 * (cum / cum[-1]).sum() / len(x) + 1 / len(x), J["E7"]["gini_club_seasons"])

# hand walk of the five largest episodes
print("\nHand walk, five largest episodes (JSON E7.top_episodes):")
for ep in J["E7"]["top_episodes"][:5]:
    pid, s, tid = int(ep["mlbid"]), int(ep["season"]), int(ep["tid"])
    rows = pl[(pl.mlbam == pid) & (pl.club_id == tid) & (pl.il_start.dt.year.isin([s - 1, s]))].sort_values("il_start")
    lo, hi = first_day[s], last_day[s]
    rows = rows[(rows.il_start <= hi) & (rows.il_end.isna() | (rows.il_end >= lo))]
    ss = [max(x, lo) for x in rows.il_start]
    ee = [hi if pd.isna(y) else min(y - pd.Timedelta(days=1), hi) for y in rows.il_end]
    i0 = ss.index(pd.Timestamp(ep["start"]))  # the JSON start selects the chain; its length is recomputed
    st_, en_ = ss[i0], ee[i0]
    for x, y in zip(ss[i0 + 1:], ee[i0 + 1:]):
        if x <= en_ + pd.Timedelta(days=1):
            en_ = max(en_, y)
    games = n_games(s, tid, st_, en_)
    prior = [(s - lag, round(float(pw.get((pid, s - lag), np.nan)), 3), expo.get((pid, s - lag))) for lag in (1, 2, 3)]
    rate = marcel(pid, s)
    print(f"  {ep['name']} {s} club {tid}: placements {', '.join(d.strftime('%Y-%m-%d') for d in rows.il_start)}; "
          f"episode {st_.date()} to {en_.date()}; {games} club games; prior fWAR/exposure {prior}; rate {rate:.5f}/game; WAR lost {rate * games:.3f}")
    check(f"hand walk {ep['name']} {s} games", games, ep["games_missed"], 0)
    check(f"hand walk {ep['name']} {s} WAR lost", rate * games, ep["war_lost"])

print(f"\n{n_checks - len(fails)} of {n_checks} checks passed")
if os.environ.get("VERIFY_DUMP"):
    CS.to_csv(os.environ["VERIFY_DUMP"], index=False)
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("verify_injury_luck: OK")
if os.environ.get("VERIFY_DUMP"):
    CS.to_csv(os.environ["VERIFY_DUMP"], index=False)
