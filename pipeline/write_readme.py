"""Write README.md from results/injury_luck_results.json and results/reconciliation_public.json.

Every number in the README comes from those two files; nothing is typed by hand.
Usage (from the repository root): python3 pipeline/write_readme.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

REPO = paths.REPO
R = json.load(open(os.path.join(REPO, "results", "injury_luck_results.json")))
REC = json.load(open(os.path.join(REPO, "results", "reconciliation_public.json")))
PH = json.load(open(os.path.join(REPO, "results", "phase1b_results.json")))
CAL = PH["R4_E11_calibration"]["calibrated"]; RNG = PH["R3_reverse_causality_designs"]["range"]; C5 = PH["R5_comparators"]
S1 = E1_sealed = R["E1"]["sealed_F1"]
E1, E2, E3, E4, E5, E7, E8, E9, E11, E12 = (R[k] for k in ("E1", "E2", "E3", "E4", "E5", "E7", "E8", "E9", "E11", "E12"))
ci = lambda v, f="{:.2f}": f"{f.format(v[0])} to {f.format(v[1])}" if v else "—"  # noqa: E731
pct = lambda v: f"{100 * v:.0f}%"  # noqa: E731
H = R["meta"]["inputs_sha16"]
census_sha = paths.sha16(paths.resolve("Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv"))
p3 = E3["all"]["p_at_p10_p50_p90"]; p3c = E3["all"]["ci95_bootstrap"]
oat = REC["one_at_a_time_from_F1"]

rows = [
    ("Mean WAR lost per club-season", f"{E1['mean']:.2f}", ci(E1["ci95"]["mean"]), "E1.mean"),
    ("SD across clubs within a season", f"{E1['sd_within_season']:.2f} WAR", ci(E1["ci95"]["sd_within_season"]), "E1.sd_within_season"),
    ("10th / 90th percentile club", f"{E1['p10']:.2f} / {E1['p90']:.2f} WAR", f"{ci(E1['ci95']['p10'])} / {ci(E1['ci95']['p90'])}", "E1.p10, E1.p90"),
    ("One SD, in wins", f"{E1['one_sd_wins']:.2f}", ci(E1["ci95"]["one_sd_wins_joint"]) + " (joint)", "E1.one_sd_wins"),
    ("10th to 90th percentile, in wins", f"{E1['p10_to_p90_wins']:.2f}", ci(E1["ci95"]["p10_to_p90_wins"]) + " (fixed conversion); " + ci(E1["ci95"]["p10_to_p90_wins_joint"]) + " (joint)", "E1.p10_to_p90_wins"),
    ("Wins per WAR lost (OLS, season FE, clustered by club)", f"{E2['est']:.3f}", f"{E2['lo']:.3f} to {E2['hi']:.3f} (cluster-robust, `E2.lo`/`E2.hi`, the interval the abstract quotes); {ci(E2['ci95_bootstrap'], '{:.3f}')} (bootstrap, `E2.ci95_bootstrap`)", "E2.est"),
    ("Wins per WAR lost, placements before 1 August", f"{E12['a_pre_aug1']['wins_per_war_lost']:.3f}", ci(E12["a_pre_aug1"]["ci95"], "{:.3f}"), "E12.a_pre_aug1"),
    ("Wins per WAR lost, placements while in contention", f"{E12['b_in_contention']['wins_per_war_lost']:.3f}", ci(E12["b_in_contention"]["ci95"], "{:.3f}"), "E12.b_in_contention"),
    ("Wins per WAR lost, Apr–Jun WAR lost on Jul–Sep wins", f"{E12['c_split_season']['wins_per_war_lost_post_jul1']:.3f}", ci(E12["c_split_season"]["ci95"], "{:.3f}"), "E12.c_split_season"),
    ("Playoff logit, exp(coefficient) per WAR lost", f"{E3['all']['or_per_war_lost']:.3f}", ci(p3c["or"], "{:.3f}"), "E3.all.or_per_war_lost"),
    ("P(playoffs), median-projection club, at p10 / p50 / p90 WAR lost", f"{pct(p3[0])} / {pct(p3[1])} / {pct(p3[2])}",
     " / ".join(f"{pct(p3c[k][0])} to {pct(p3c[k][1])}" for k in ("p10", "p50", "p90")), "E3.all.p_at_p10_p50_p90"),
    ("Out-of-sample R², prior year only / roster only / all preseason features",
     f"{E4['prior_year_only']['oos_r2']:.3f} / {E4['roster_only']['oos_r2']:.3f} / {E4['all']['oos_r2']:.3f}", ci(E4["all"]["ci95"]) + " (all)", "E4.*.oos_r2"),
    ("SD of the out-of-sample unexpected part", f"{E5['sd_unexpected_oos_war']:.2f} WAR = {E5['sd_unexpected_oos_wins']:.2f} wins", ci(E5["ci95"]["sd_war"]) + " WAR", "E5"),
    ("Share of between-club variance not foreseeable", pct(E5["share_of_variance_unexpected"]), "—", "E5.share_of_variance_unexpected"),
    ("Club persistence of the unexpected part: ICC (primary test)", f"{E11['primary']['icc1']:.3f}; permutation P = {E11['primary']['p_perm_one_sided']:.3f}",
     ci(E11["primary"]["ci95_icc1"], "{:.3f}"), "E11.primary"),
    ("E11 primary, simulation-calibrated P (post hoc)", f"{CAL['primary_p_calibrated']:.2f}", "—", "phase1b: R4_E11_calibration.calibrated"),
    ("Power of the primary at ICC 0.03 / 0.06 / 0.11 / 0.20 (simulated, post hoc)",
     " / ".join(f"{CAL['power_primary_calibrated_critical'][k]:.2f}" for k in ("0.03", "0.06", "0.11", "0.2")), "—", "phase1b: power_primary_calibrated_critical"),
    ("ICC, roster-only unexpected part (sensitivity)", f"{E11['sens_roster_loso_300']['icc1']:.3f}; P = {E11['sens_roster_loso_300']['p_perm_one_sided']:.3f}",
     ci(E11["sens_roster_loso_300"]["ci95_icc1"], "{:.3f}"), "E11.sens_roster_loso_300"),
    ("Wins per WAR lost across reverse-causality designs (post hoc range)", f"{RNG['most_negative'][1]:.2f} to {RNG['least_negative'][1]:.2f}", "—", "phase1b: R3_reverse_causality_designs.range"),
    ("Luck comparators: binomial SD / Pythagorean residual SD, wins", f"{C5['binomial_sd_wins_500_team_162']:.2f} / {C5['pythagorean_residual_sd_wins']:.2f}", "—", "phase1b: R5_comparators"),
    ("Worst episode / top three, share of a club-season's WAR lost", f"{pct(E7['top1_share_mean'])} / {pct(E7['top3_share_mean'])}", "—", "E7"),
    ("IL open on the final regular-season day: episodes / WAR lost", f"{pct(E8['share_of_episodes'])} / {pct(E8['share_of_war_lost'])}", "—", "E8"),
    ("Hitters / starters / relievers, WAR lost per club-season",
     " / ".join(f"{E9['mean_war_lost_per_club_season'][g]:.2f}" for g in ("hitter", "starter", "reliever")), "—", "E9"),
]
fam = R["E6"]["families"][:6]

md = f"""# Injury luck in Major League Baseball, on public data

How much does injury luck move an MLB club's season, how much of it could be seen before the season, and is any
of the rest a persistent club effect? This repository rebuilds every estimate from public inputs: the MLB Stats
API (transactions, schedules, standings, game logs, people) and FanGraphs season WAR (not redistributed; see
*Inputs you fetch yourself*). It measures availability, not ability, and says nothing about any player's future.

**Repaired after review (Phase 1b).** An independent review found that placements from before 2015, when public
appearance dates are not available, could run through seasons the player played. Rule R1 (`injury_luck.py
--episode-rule r1`, the default) ends a placement at the player's first MLB pitching appearance, at the opening day of
the first pre-2015 season he played, or at a restricted-list / suspension transaction; stops one player being counted on
two clubs' lists at once; and caps games missed so that games missed + games played never exceed team games. The build
as sealed is still run first and must reproduce the sealed public build to 1e-9. Sealed → repaired: mean
{S1['mean']:.2f} → {E1['mean']:.2f} WAR, SD {S1['sd_within_season']:.2f} → {E1['sd_within_season']:.2f}, wins per WAR lost
{S1['wins_per_war_lost']['est']:.3f} → {E2['est']:.3f}. `pipeline/phase1b_posthoc.py` adds the post hoc (exploratory) analyses
in `results/phase1b_results.json`.

**Preregistered.** The estimands (E1–E13), primary definitions, sensitivities and decision rules were sealed
before any new estimate was computed (preregistration sha256[:16] `{R['meta']['prereg']['sha16']}`). The
preregistration document is cited here by hash; pass it with `--prereg` and `injury_luck.py` checks the hash.
Bootstrap: {R['E13']['B']:,} club-resampled draws, seed {R['E13']['seed']}.

## Layout

```
pipeline/
  paths.py              where each input lives (data_public/ or inputs/); no absolute paths anywhere
  injury_luck.py        episodes -> WAR lost -> E1-E13, bootstrap; writes results/injury_luck_results.json
                        (and results/team_season_public.csv, results/stints_public_2015_2025.csv, which are
                        produced by the run and not shipped in this repository)
  reconcile_public.py   how much each episode rule moves the headline values (one rule reverted at a time,
                        relative to the build as sealed)
  phase1b_posthoc.py    post hoc analyses after review (preseason control, reverse-causality designs, calibrated
                        E11 null and power, luck comparators, BCa, format eras); writes results/phase1b_results.json
  injury_luck_figures.py  Figures 1-3 from the JSON
  verify_injury_luck.py independent second implementation: E1, E2, E4, E7, E11 point estimate, hand walk of the
                        five largest episodes; exits 0 when every check passes
  write_readme.py       this file, from the JSON
data_public/
  placements_public.csv the derived public injured-list census (one row per IL placement), sha16 `{census_sha}`
results/
  injury_luck_results.json, reconciliation_public.json, figures/Figure1-3.png, verify_run.log
```

## The census

`data_public/placements_public.csv` is the public twin's census, shipped as that project publishes it: IL
placements parsed from the MLB Stats API transaction feed (`/api/v1/transactions`, sportId 1), MLB clubs only,
with start dates repaired from appearances, 60-day transfers linked, and each episode ended at the first
activation validated against the player's public appearances (Baseball Savant pitch-level data). No adjudicated
case table or curated override is used. It is built by `twin/census.py` of the public twin
(`python3 -m twin.census`, after `fetch_public_data.py`), sha16 `{census_sha}`. `injury_luck.py` merges placements
into episodes and never edits the census.

## Inputs you fetch yourself

Put these in `inputs/` (or point `INJURY_LUCK_INPUTS` at a folder). Every script checks the sha256[:16] below and
stops on a mismatch; a fresh pull from a live API will not match byte for byte (the feeds are revised), so set
the pins in `pipeline/paths.py` to your files and expect estimates within bootstrap error.

| file | what and where from | sha16 of the file used here |
|---|---|---|
| `fangraphs_war_2010_2025.csv` | FanGraphs season leaderboards, batting and pitching, 2010–2025, every player (no PA/IP minimum), exported and stacked with columns `season,name,team,g,pa,war,mlbamid,role,ip` (`role` = hitter or pitcher; `team` = FanGraphs abbreviation, `- - -` for multi-club seasons). FanGraphs data is licensed to its users and is **not redistributed** | `{H['_staging_tmp/fangraphs_war_2010_2025.csv']}` |
| `games_flat.csv` | MLB Stats API schedule (`/api/v1/schedule`, sportId 1), 2010–2026, one row per game; columns used: `season,gamePk,gameType,status,date,home,home_id,away,away_id,home_score,away_score` | `{H['Postseason_Injury_Risk/data/games_flat.csv']}` |
| `standings.csv` | MLB Stats API final standings, one row per club-season; columns used: `season,team_id,W,L,qualified,league_id` (qualified = reached the postseason) | `{H['Postseason_Injury_Risk/data/standings.csv']}` |
| `gamelogs_flat.csv` | MLB Stats API pitcher game logs (`/api/v1/people/{{id}}/stats?stats=gameLog&group=pitching`), 2010–2026; columns used: `player_id,season,gamePk,GS` (starter vs reliever, E9) | `{H['Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv']}` |
| `people.csv` | MLB Stats API people records; columns used: `mlbam,birth_date` (roster age) | `{H['Postseason_Injury_Risk/data/people.csv']}` |
| `f1_team_season.csv`, `f1_results.json` | the public twin's sealed F1 outputs (`out/`, built by `python3 -m twin.framing_f1`); `injury_luck.py` rebuilds F1 and stops unless it matches to 1e-9, and carries the four sealed F1 numbers | `{H['Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_team_season.csv']}`, `{H['Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_results.json']}` |
| `txns_live.jsonl` | MLB Stats API transactions 2010-01-01 → 2026-09-29, one JSON record per line (the twin's `fetch_public_data.py`); R1 episode ends (restricted list / suspension), the preseason roster control and `reconcile_public.py` | `{REC['meta']['inputs_sha16']['Sweeper_Injury_Risk/data/txns_live.jsonl']}` |

## Run order

```
pip install pandas numpy scipy statsmodels matplotlib
python3 pipeline/injury_luck.py --dump-dir scratch   # about 3 minutes; scratch/ holds fWAR-derived tables, never commit it
python3 pipeline/injury_luck.py --keep-covid-era-blanks --B 3 --out scratch/covid   # sensitivity input for the next step
python3 pipeline/phase1b_posthoc.py --dump scratch --covid scratch/covid/results/injury_luck_results.json   # about 4 minutes
python3 pipeline/reconcile_public.py
python3 pipeline/injury_luck_figures.py
python3 pipeline/verify_injury_luck.py   # exits 0
python3 pipeline/write_readme.py
```

Python 3.11, pandas 3.0, numpy 2.4, statsmodels 0.15, matplotlib 3.10 (the versions that produced `results/`).

## Numbers you should get

From `results/injury_luck_results.json` (seasons 2015–2025, 2020 excluded as an outcome; {R['meta']['n_club_seasons']} club-seasons,
{R['meta']['n_episodes_outcome_seasons']:,} episodes). CIs are 95% club-clustered bootstrap percentiles unless marked.

| estimand | value | 95% CI | JSON key |
|---|---|---|---|
""" + "\n".join(f"| {a} | {b} | {c} | `{d}` |" for a, b, c, d in rows) + f"""

Wins per WAR lost is an association, not a causal effect. It moves toward zero in every preregistered reverse-causality variant (E12): part of the association is
late-season roster management by clubs already out of contention. The unexpected part (E5, E11) is the out-of-sample
residual of a leave-one-season-out prediction from all preseason features; E11's verdict under the declared rule:
*{E11['verdict']}*.

**Where the WAR goes (E6, share of WAR lost; whole-word keyword families over the placement text):** """ + "; ".join(
    f"{f['family']} {pct(f['share_war_lost'])}" for f in fam) + f""". Elbow plus shoulder: {pct(R['E6']['elbow_plus_shoulder_share'])}.

**Episode rules (`results/reconciliation_public.json`), one rule reverted at a time from the public build as sealed (before the R1 repair):**

| variant | mean WAR lost | within-season SD | wins per WAR lost |
|---|---|---|---|
""" + "\n".join(f"| {k} | {v['mean']:.2f} | {v['sd_within_season']:.2f} | {v['wins_per_war_lost']:.3f} |" for k, v in oat.items()) + f"""

## What differs from the study run

* The study also estimated a disattenuated wins-per-WAR sensitivity and walked a non-public IL list into the public
  build to explain the gap between the two. Both read a non-public source and are not in this repository; every other
  key of the results file is identical to the study run.
* E10: the platoon value comes from unpublished companion work and is not reported here. Comparators that are
  like-for-like with an SD of luck (binomial and Pythagorean-residual SDs) are in `results/phase1b_results.json`.

## Figures

`results/figures/Figure1_war_lost_distribution.png` (WAR lost per club-season, league p10–p90),
`Figure2_playoff_probability.png` (P(playoffs) against WAR lost for the median-projection club, bootstrap band),
`Figure3_persistence.png` (unexpected WAR lost in season t against t−1; ICC with its null band, simulation-calibrated for
the primary).

## License

Code: MIT (`LICENSE`). Data derived from the MLB Stats API is subject to MLB's terms of use. FanGraphs data is not
included.
"""
open(os.path.join(REPO, "README.md"), "w").write(md)
print(len(md.split()), "words")
