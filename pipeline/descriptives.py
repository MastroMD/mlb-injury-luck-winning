"""descriptives.py - injury loss in plain units (post hoc, 2026-11-04; DEVIATIONS #31).

Per valuation, the club-season distribution of WAR lost (mean, median, 10th and 90th percentiles, by season), its carry-over
and new-injury parts, the league total, and the same quantities converted to wins with that valuation's wins coefficient and
to free-agent dollars at the cost of a win in free agency (FanGraphs, "What Are Teams Paying For A Win In Free Agency? 2026
Edition", Clemens, 24 Feb 2026: guaranteed money over Steamer-projected WAR, 2025 dollars; overall $/WAR 10.62M on average
over 2020-2026 and 11.23M for 2026). The dollar conversion is in Steamer-projected units, so it is exact only for the Steamer
valuation and approximate for the others. Reductions (10%, 25%) are arithmetic on the association, not estimates of what a
programme achieves; the persistence result finds no club with a durable reduction.

Reads a club-season table (season, war_lost; wl_carry if present) and that run's phase2_results.json. Aggregates only.
usage: python3 pipeline/descriptives.py --label primary --team-season results/team_season_public.csv --results results/phase2_results.json
       [--out results/descriptives_2026-11-04.json]   (the JSON holds one entry per label; rerun adds or replaces one)
"""
import argparse, json, os
import numpy as np, pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--label", required=True); ap.add_argument("--team-season", required=True); ap.add_argument("--results", required=True)
ap.add_argument("--out", default=os.path.join(REPO, "results", "descriptives_2026-11-04.json"))
a = ap.parse_args()
DPW = {"fangraphs_2020_2026_average": 10.62, "fangraphs_2026": 11.23}
SOURCE = "FanGraphs, What Are Teams Paying For A Win In Free Agency? 2026 Edition (Clemens, 2026-02-24), $M per Steamer-projected WAR, 2025 dollars"
T = pd.read_csv(a.team_season)
J = json.load(open(a.results))
P = J["P2_1_preseason_control"]
b = abs(P["wins"]["est"]); lo, hi = abs(P["wins"]["hi_cluster"]), abs(P["wins"]["lo_cluster"])
carry = J["P2_7_levers"]["a_carry_over"]["carry_share"]["est"]
seasons = sorted(int(s) for s in T.season.unique())
x = T.war_lost
by = T.groupby("season").war_lost.mean()
early = [s for s in seasons if s <= 2019]; late = [s for s in seasons if s >= 2023]
sd_within = float(P["sd_war_within_season"]) if "sd_war_within_season" in P else float(P["one_sd_wins"]["est"] / b)
n_clubs = int(T.groupby("season").size().iloc[0])
d = {"meta": {"valuation": a.label, "club_seasons": int(len(T)), "seasons": seasons, "clubs_per_season": n_clubs, "wins_per_war_lost": b, "wins_per_war_lost_ci": [lo, hi],
              "carry_share": carry, "source_dollars": SOURCE, "dollars_per_war": DPW},
     "war_lost": {"mean": float(x.mean()), "median": float(x.median()), "p10": float(x.quantile(.1)), "p90": float(x.quantile(.9)), "max": float(x.max()),
                  "sd_within_season": sd_within, "p90_minus_p10": float(x.quantile(.9) - x.quantile(.1)),
                  "new_injury_mean": float((1 - carry) * x.mean()), "carry_over_mean": float(carry * x.mean()),
                  "by_season_mean": {str(k): float(v) for k, v in by.items()},
                  "early_seasons": early, "early_mean_range": [float(by[early].min()), float(by[early].max())],
                  "late_seasons": late, "late_mean_range": [float(by[late].min()), float(by[late].max())],
                  "league_per_season": float(n_clubs * x.mean()), "league_total": float(x.sum())}}
if "wl_carry" in T:
    d["war_lost"]["carry_over_mean_from_table"] = float(T.wl_carry.mean())
w = d["war_lost"]
d["wins"] = {k: float(b * w[k]) for k in ("mean", "median", "p10", "p90", "max", "sd_within_season", "p90_minus_p10", "new_injury_mean", "carry_over_mean", "league_per_season")}
d["wins"]["mean_ci"] = [float(lo * w["mean"]), float(hi * w["mean"])]
d["wins"]["league_per_season_ci"] = [float(lo * w["league_per_season"]), float(hi * w["league_per_season"])]
d["dollars_musd"] = {rate: {k: float(v * w[k]) for k in ("mean", "p10", "p90", "sd_within_season", "p90_minus_p10", "new_injury_mean", "league_per_season")} for rate, v in DPW.items()}
d["reductions"] = {}
for r in (0.10, 0.25):
    d["reductions"][f"{int(100 * r)}pct_of_all_loss"] = {"war_per_club": float(r * w["mean"]), "wins_per_club": float(b * r * w["mean"]), "war_league": float(r * w["league_per_season"]),
                                                       "wins_league": float(b * r * w["league_per_season"]), "wins_league_ci": [float(lo * r * w["league_per_season"]), float(hi * r * w["league_per_season"])],
                                                       "musd_per_club": {rate: float(v * r * w["mean"]) for rate, v in DPW.items()}, "musd_league": {rate: float(v * r * w["league_per_season"]) for rate, v in DPW.items()}}
    d["reductions"][f"{int(100 * r)}pct_of_new_injury_loss"] = {"war_per_club": float(r * w["new_injury_mean"]), "wins_per_club": float(b * r * w["new_injury_mean"]),
                                                              "wins_league": float(b * r * n_clubs * w["new_injury_mean"]), "musd_per_club": {rate: float(v * r * w["new_injury_mean"]) for rate, v in DPW.items()},
                                                              "musd_league": {rate: float(v * r * n_clubs * w["new_injury_mean"]) for rate, v in DPW.items()}}
out = json.load(open(a.out)) if os.path.exists(a.out) else {}
out[a.label] = d
json.dump(out, open(a.out, "w"), indent=1)
print(f"{a.label}: WAR lost mean {w['mean']:.2f} (p10 {w['p10']:.1f}, p90 {w['p90']:.1f}), wins {d['wins']['mean']:.2f}, league {w['league_per_season']:.0f} WAR / {d['wins']['league_per_season']:.0f} wins, "
      f"${d['dollars_musd']['fangraphs_2020_2026_average']['mean']:.0f}M per club, ${d['dollars_musd']['fangraphs_2020_2026_average']['league_per_season']:,.0f}M league -> {a.out}")
