"""dollars_bref.py - injury loss in salary dollars (post hoc, exploratory, 2026-11-04; DEVIATIONS #31).

Salary paid to players while they were on the injured list, per club-season, from Baseball-Reference season salaries
(the published war_daily_bat.txt and war_daily_pitch.txt, downloaded to --src if absent; not redistributed). A player-season
with no Baseball-Reference salary takes the same player's salary in the previous season, else the next season (at least
the league minimum), else the league minimum. Games missed / 162 of the season salary counts as paid while on the IL.
Carry-over episodes are those of players whose episode was open on the final regular-season day of the previous outcome
season (2019 for 2021, as declared in the addendum). Writes results/dollars_bref_2026-11-04.json (aggregates only).

Needs results/stints_public_2015_2025.csv and scratch/episodes_all_2012_2025.csv from `injury_luck.py --dump-dir scratch`.
usage: python3 pipeline/dollars_bref.py [--src inputs]
"""
import argparse, json, os, urllib.request
import numpy as np, pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser(); ap.add_argument("--src", default=os.path.join(REPO, "inputs")); a = ap.parse_args()
for f in ("war_daily_bat.txt", "war_daily_pitch.txt"):
    if not os.path.exists(os.path.join(a.src, f)):
        urllib.request.urlretrieve(f"https://www.baseball-reference.com/data/{f}", os.path.join(a.src, f))
MIN = {2014: 500000, 2015: 507500, 2016: 507500, 2017: 535000, 2018: 545000, 2019: 555000, 2020: 563500, 2021: 570500,
       2022: 700000, 2023: 720000, 2024: 740000, 2025: 760000, 2026: 780000}
PREV_OF = {2015: 2014, 2016: 2015, 2017: 2016, 2018: 2017, 2019: 2018, 2021: 2019, 2022: 2021, 2023: 2022, 2024: 2023, 2025: 2024}
GOOD = [2015, 2016, 2017, 2018, 2019, 2023, 2024]  # seasons in which >= 93% of opening-day projected talent has a listed salary
b = pd.read_csv(os.path.join(a.src, "war_daily_bat.txt"), low_memory=False, na_values=["NULL"])
p = pd.read_csv(os.path.join(a.src, "war_daily_pitch.txt"), low_memory=False, na_values=["NULL"])
sal = pd.concat([b[["mlb_ID", "year_ID", "salary"]], p[["mlb_ID", "year_ID", "salary"]]]).dropna()
sal["mlb_ID"] = sal.mlb_ID.astype(int); SAL = sal.groupby(["mlb_ID", "year_ID"]).salary.max().to_dict()


def salary(pid, s):
    v = SAL.get((pid, s))
    if v is not None:
        return v, "listed"
    for d in (-1, 1):
        v = SAL.get((pid, s + d))
        if v is not None:
            return max(v, MIN[s]), "adjacent_season"
    return MIN[s], "league_minimum"


S = pd.read_csv(os.path.join(REPO, "results", "stints_public_2015_2025.csv"))
E = pd.read_csv(os.path.join(REPO, "scratch", "episodes_all_2012_2025.csv"), parse_dates=["end"])
last = E.groupby("season").end.max()   # episodes are clipped to the season, so the latest end is the final regular-season day
openp = set(zip(E.loc[E.end >= E.season.map(last), "mlbid"], E.loc[E.end >= E.season.map(last), "season"]))
S["carry"] = [(m, PREV_OF[s]) in openp for m, s in zip(S.mlbid, S.season)]
S[["sal", "sal_src"]] = [salary(int(m), int(s)) for m, s in zip(S.mlbid, S.season)]
tot = S.groupby(["mlbid", "season"]).games_missed.transform("sum")
S["paid_il"] = S.sal * np.minimum(S.games_missed, 162) / 162 * np.where(tot > 162, 162 / tot, 1.0)
R = pd.read_csv(os.path.join(REPO, "data_public", "opening_day_40man_2015_2026.csv")).drop_duplicates(["season", "club_id", "mlbam"])
R = R[R.season.isin(S.season.unique())]
R["sal"] = [salary(int(m), int(s))[0] for m, s in zip(R.mlbam, R.season)]
pay = R.groupby(["season", "club_id"]).sal.sum().rename("payroll_od40").reset_index().rename(columns={"club_id": "tid"})
cs = S.groupby(["season", "tid"]).agg(paid_il=("paid_il", "sum"), war_lost=("war_lost", "sum")).reset_index()
cs = cs.merge(S[S.carry].groupby(["season", "tid"]).paid_il.sum().rename("paid_il_carry").reset_index(), how="left").fillna({"paid_il_carry": 0}).merge(pay, how="left")


def summ(d):
    dm = d.assign(x=d.paid_il - d.groupby("season").paid_il.transform("mean"), y=d.war_lost - d.groupby("season").war_lost.transform("mean"))
    return {"club_seasons": int(len(d)), "paid_il_mean_musd": d.paid_il.mean() / 1e6, "paid_il_sd_musd": d.paid_il.std() / 1e6,
            "paid_il_p10_p90_musd": [d.paid_il.quantile(.1) / 1e6, d.paid_il.quantile(.9) / 1e6],
            "share_of_opening_day_40man_salary": d.paid_il.sum() / d.payroll_od40.sum(), "carry_over_share_of_paid_il": d.paid_il_carry.sum() / d.paid_il.sum(),
            "paid_il_per_war_lost_musd": d.paid_il.sum() / d.war_lost.sum() / 1e6, "corr_with_war_lost_within_season": float(dm[["x", "y"]].corr().iloc[0, 1])}


out = {"meta": {"label": "post hoc, exploratory; Baseball-Reference season salaries (war_daily files), not redistributed",
                "rule": "games missed / 162 of the season salary; missing salary -> previous, else next season (>= minimum) -> league minimum",
                "salary_source_share_of_paid_il": S.groupby("sal_src").paid_il.sum().div(S.paid_il.sum()).to_dict(),
                "salary_source_share_of_episodes": S.sal_src.value_counts(normalize=True).to_dict(), "good_coverage_seasons": GOOD},
       "all_outcome_seasons": summ(cs), "good_coverage_seasons": summ(cs[cs.season.isin(GOOD)]),
       "by_season": {int(s): {"paid_il_mean_musd": g.paid_il.mean() / 1e6, "share_of_opening_day_40man_salary": g.paid_il.sum() / g.payroll_od40.sum()}
                     for s, g in cs.groupby("season")}}
# opening-day roster players who ended the previous outcome season on the IL: salary committed and the share of it paid while on the IL
R["carry"] = [(m, PREV_OF[s]) in openp for m, s in zip(R.mlbam, R.season)]
pil = S.groupby(["mlbid", "season"]).paid_il.sum().to_dict(); R["paid_il"] = [pil.get((m, s), 0.0) for m, s in zip(R.mlbam, R.season)]
ncs = R.groupby(["season", "club_id"]).ngroups
for nm, m in (("ended_previous_season_on_il", R.carry), ("other_roster_players", ~R.carry)):
    g = R[m]
    out[f"opening_day_roster_{nm}"] = {"player_seasons": int(len(g)), "salary_per_club_season_musd": g.sal.sum() / ncs / 1e6,
                                       "share_of_salary_paid_while_on_il": g.paid_il.sum() / g.sal.sum()}
json.dump(out, open(os.path.join(REPO, "results", "dollars_bref_2026-11-04.json"), "w"), indent=1, default=float)
print(json.dumps(out["all_outcome_seasons"], default=float))
