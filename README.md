# Injury luck in Major League Baseball, on public data

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
7.55 → 7.31 WAR, SD 3.74 → 3.60, wins per WAR lost
-0.553 → -0.579. `pipeline/phase1b_posthoc.py` adds the post hoc (exploratory) analyses
in `results/phase1b_results.json`.

**Preregistered.** The estimands (E1–E13), primary definitions, sensitivities and decision rules were sealed
before any new estimate was computed (preregistration sha256[:16] `3fd792e537b6834b`). The
preregistration document is cited here by hash; pass it with `--prereg` and `injury_luck.py` checks the hash.
Bootstrap: 2,000 club-resampled draws, seed 20260930.

**Phase 2 (the full paper).** The analyses new to the paper (P2.1–P2.8) were declared in
`PREREGISTRATION_ADDENDUM_PHASE2_2026-10-02.md` and sealed before they were computed (`SEAL_PHASE2.txt`, sha256[:16]
`6634bfeb1212f484`). The primary talent control is each club's opening-day 40-man roster
(`data_public/opening_day_40man_2015_2026.csv`, Stats API `rosterType=40Man` on the eve of each club's first game).
`pipeline/phase2.py` rebuilds the primary club-season table and stops unless it equals `results/team_season_public.csv`
within 1e-9, then writes `results/phase2_results.json` (2,000 club draws, seed 20261002).
`pipeline/phase2_posthoc_r2.py` holds the analyses added after a second internal review. They are post hoc, and
`DEVIATIONS.md` #23–27 lists them. It reruns `phase2.py` with marked substitutions, and without the departure rule it
reproduces every sealed value outside the corrected designs. The internal referee report and the reply are kept with the
study files and are available on request.


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
  phase2.py             Phase 2 (P2.1-P2.8); writes results/phase2_results.json (and team_season_phase2.csv,
                        team_season_2026_phase2.csv, which are produced by the run and not shipped)
  verify_phase2.py      independent rebuild of the Phase 2 headline values; exits 0 when every check passes
  negative_control_phase2.py  perturbs three values in a copy of the results; the verifier must fail on exactly those
  phase2_posthoc_r2.py  post hoc analyses after the Phase 2 review (club opener, departure end, extras)
  paper_figures.py      the six figures of the paper, from the results files
data_public/
  placements_public.csv the derived public injured-list census (one row per IL placement), sha16 `e5ed2129cf8218ec`
  opening_day_40man_2015_2026.csv  opening-day 40-man rosters, one row per club-season-player
results/
  injury_luck_results.json, reconciliation_public.json, figures/Figure1-3.png, verify_run.log
  phase2_results.json, phase2_posthoc_*.json, their run logs, verify_phase2*.log, figures/paper/Figure1-6.png
```

## The census

`data_public/placements_public.csv` is the public twin's census, shipped as that project publishes it: IL
placements parsed from the MLB Stats API transaction feed (`/api/v1/transactions`, sportId 1), MLB clubs only,
with start dates repaired from appearances, 60-day transfers linked, and each episode ended at the first
activation validated against the player's public appearances (Baseball Savant pitch-level data). No adjudicated
case table or curated override is used. It is built by `twin/census.py` of the public twin
(`python3 -m twin.census`, after `fetch_public_data.py`), sha16 `e5ed2129cf8218ec`. `injury_luck.py` merges placements
into episodes and never edits the census.

## Inputs you fetch yourself

Put these in `inputs/` (or point `INJURY_LUCK_INPUTS` at a folder). Every script checks the sha256[:16] below and
stops on a mismatch; a fresh pull from a live API will not match byte for byte (the feeds are revised), so set
the pins in `pipeline/paths.py` to your files and expect estimates within bootstrap error.

| file | what and where from | sha16 of the file used here |
|---|---|---|
| `fangraphs_war_2010_2025.csv` | FanGraphs season leaderboards, batting and pitching, 2010–2025, every player (no PA/IP minimum), exported and stacked with columns `season,name,team,g,pa,war,mlbamid,role,ip` (`role` = hitter or pitcher; `team` = FanGraphs abbreviation, `- - -` for multi-club seasons). FanGraphs data is licensed to its users and is **not redistributed** | `cad855bb7fd170dc` |
| `games_flat.csv` | MLB Stats API schedule (`/api/v1/schedule`, sportId 1), 2010–2026, one row per game; columns used: `season,gamePk,gameType,status,date,home,home_id,away,away_id,home_score,away_score` | `ad002536e1d8a01b` |
| `standings.csv` | MLB Stats API final standings, one row per club-season; columns used: `season,team_id,W,L,qualified,league_id` (qualified = reached the postseason) | `911f807ec5f69104` |
| `gamelogs_flat.csv` | MLB Stats API pitcher game logs (`/api/v1/people/{id}/stats?stats=gameLog&group=pitching`), 2010–2026; columns used: `player_id,season,gamePk,GS` (starter vs reliever, E9) | `08345a5d95486529` |
| `people.csv` | MLB Stats API people records; columns used: `mlbam,birth_date` (roster age) | `b34f61471c31711d` |
| `f1_team_season.csv`, `f1_results.json` | the public twin's sealed F1 outputs (`out/`, built by `python3 -m twin.framing_f1`); `injury_luck.py` rebuilds F1 and stops unless it matches to 1e-9, and carries the four sealed F1 numbers | `7eb47b3cd4fbc6d7`, `09b587a6cd01da00` |
| `txns_live.jsonl` | MLB Stats API transactions 2010-01-01 → 2026-09-29, one JSON record per line (the twin's `fetch_public_data.py`); R1 episode ends (restricted list / suspension), the preseason roster control and `reconcile_public.py` | `f65ea265e77b5735` |

## Run order

```
pip install pandas numpy scipy statsmodels matplotlib
python3 pipeline/injury_luck.py --dump-dir scratch   # about 3 minutes; scratch/ holds fWAR-derived tables, never commit it
python3 pipeline/injury_luck.py --keep-covid-era-blanks --B 3 --out scratch/covid   # sensitivity input for the next step
python3 pipeline/phase1b_posthoc.py --dump scratch --covid scratch/covid/results/injury_luck_results.json   # about 4 minutes
python3 pipeline/reconcile_public.py
python3 pipeline/injury_luck_figures.py
python3 pipeline/verify_injury_luck.py   # exits 0
python3 pipeline/phase2.py   # about 2 minutes; needs results/team_season_public.csv from injury_luck.py
python3 pipeline/verify_phase2.py   # exits 0
python3 pipeline/negative_control_phase2.py   # exits 0 when the verifier fails on the perturbed copy
python3 pipeline/phase2_posthoc_r2.py --build opener --full   # post hoc; checks that it reproduces phase2_results.json
python3 pipeline/phase2_posthoc_r2.py --build departure --full
python3 pipeline/phase2_posthoc_r2.py --build opener --extras
python3 pipeline/phase2_posthoc_r2.py --build departure --extras
python3 pipeline/paper_figures.py   # results/figures/paper/
python3 pipeline/write_readme.py
```

Python 3.10, pandas 2.3, numpy 2.2, scipy 1.15, statsmodels 0.15, matplotlib 3.10 produced the files in `results/` dated
2026-10-02. The Phase 1 files of 2026-09-30 came from Python 3.11, pandas 3.0 and numpy 2.4, and the re-run reproduced them
within 1e-9 (DEVIATIONS #17).

## Numbers you should get

From `results/injury_luck_results.json` (seasons 2015–2025, 2020 excluded as an outcome; 300 club-seasons,
7,684 episodes). CIs are 95% club-clustered bootstrap percentiles unless marked.

| estimand | value | 95% CI | JSON key |
|---|---|---|---|
| Mean WAR lost per club-season | 7.31 | 6.62 to 8.09 | `E1.mean` |
| SD across clubs within a season | 3.60 WAR | 2.94 to 4.04 | `E1.sd_within_season` |
| 10th / 90th percentile club | 3.27 / 11.86 WAR | 2.82 to 3.65 / 10.73 to 13.46 | `E1.p10, E1.p90` |
| One SD, in wins | 2.09 | 0.84 to 3.35 (joint) | `E1.one_sd_wins` |
| 10th to 90th percentile, in wins | 4.98 | 4.38 to 5.96 (fixed conversion); 2.16 to 8.56 (joint) | `E1.p10_to_p90_wins` |
| Wins per WAR lost (OLS, season FE, clustered by club) | -0.579 | -0.902 to -0.257 (cluster-robust, `E2.lo`/`E2.hi`, the interval the abstract quotes); -0.894 to -0.268 (bootstrap, `E2.ci95_bootstrap`) | `E2.est` |
| Wins per WAR lost, placements before 1 August | -0.439 | -0.785 to -0.074 | `E12.a_pre_aug1` |
| Wins per WAR lost, placements while in contention | -0.193 | -0.525 to 0.163 | `E12.b_in_contention` |
| Wins per WAR lost, Apr–Jun WAR lost on Jul–Sep wins | -0.303 | -0.699 to 0.136 | `E12.c_split_season` |
| Playoff logit, exp(coefficient) per WAR lost | 0.864 | 0.763 to 0.958 | `E3.all.or_per_war_lost` |
| P(playoffs), median-projection club, at p10 / p50 / p90 WAR lost | 45% / 34% / 19% | 31% to 59% / 23% to 44% / 9% to 31% | `E3.all.p_at_p10_p50_p90` |
| Out-of-sample R², prior year only / roster only / all preseason features | 0.258 / 0.315 / 0.364 | 0.18 to 0.48 (all) | `E4.*.oos_r2` |
| SD of the out-of-sample unexpected part | 2.91 WAR = 1.69 wins | 2.57 to 3.15 WAR | `E5` |
| Share of between-club variance not foreseeable | 64% | — | `E5.share_of_variance_unexpected` |
| Club persistence of the unexpected part: ICC (primary test) | -0.034; permutation P = 0.835 | -0.078 to 0.010 | `E11.primary` |
| E11 primary, simulation-calibrated P (post hoc) | 0.79 | — | `phase1b: R4_E11_calibration.calibrated` |
| Power of the primary at ICC 0.03 / 0.06 / 0.11 / 0.20 (simulated, post hoc) | 0.14 / 0.33 / 0.58 / 0.90 | — | `phase1b: power_primary_calibrated_critical` |
| ICC, roster-only unexpected part (sensitivity) | 0.043; P = 0.073 | -0.021 to 0.112 | `E11.sens_roster_loso_300` |
| Wins per WAR lost across reverse-causality designs (post hoc range) | -0.92 to -0.19 | — | `phase1b: R3_reverse_causality_designs.range` |
| Luck comparators: binomial SD / Pythagorean residual SD, wins | 6.36 / 4.21 | — | `phase1b: R5_comparators` |
| Worst episode / top three, share of a club-season's WAR lost | 27% / 54% | — | `E7` |
| IL open on the final regular-season day: episodes / WAR lost | 31% / 41% | — | `E8` |
| Hitters / starters / relievers, WAR lost per club-season | 2.93 / 3.17 / 1.22 | — | `E9` |

Wins per WAR lost is an association, not a causal effect. It moves toward zero in every preregistered reverse-causality variant (E12): part of the association is
late-season roster management by clubs already out of contention. The unexpected part (E5, E11) is the out-of-sample
residual of a leave-one-season-out prediction from all preseason features; E11's verdict under the declared rule:
*luck at this precision*.

**Where the WAR goes (E6, share of WAR lost; whole-word keyword families over the placement text):** Shoulder 15%; Elbow (other) 13%; Hand / wrist / finger 9%; Unstated 8%; UCL / Tommy John 8%; Knee 7%. Elbow plus shoulder: 37%.

**Episode rules (`results/reconciliation_public.json`), one rule reverted at a time from the public build as sealed (before the R1 repair):**

| variant | mean WAR lost | within-season SD | wins per WAR lost |
|---|---|---|---|
| F1 | 7.55 | 3.74 | -0.553 |
| F1 with end date counted as a game missed | 7.72 | 3.80 | -0.550 |
| F1 with COVID-era blank placements kept | 7.88 | 3.90 | -0.516 |
| F1 with activation-only ends | 9.59 | 4.59 | -0.230 |
| F1 without merging | 7.77 | 3.87 | -0.524 |


## Phase 2 numbers you should get

From `results/phase2_results.json` (the paper's primary specification) and, where marked, the post hoc files. Intervals are
95% club-bootstrap percentiles unless marked.

| quantity | value | 95% CI | source |
|---|---|---|---|
| Wins per WAR lost (opening-day control; OLS, season FE, clustered by club) | -0.633 | -0.941 to -0.325 (cluster-robust); BCa -0.984 to -0.359; wild-cluster bootstrap-t -0.968 to -0.305 | `P2_1_preseason_control.wins` |
| One SD of injury loss, in wins | 2.28 | 1.12 to 3.49 (joint) | `P2_1_preseason_control.one_sd_wins` |
| 10th to 90th percentile club, in wins | 5.44 | 2.85 to 8.82 (joint) | `P2_1_preseason_control.p10_p90_wins` |
| P(playoffs), median-projection club, at p10 / p50 / p90 WAR lost | 44% / 34% / 21% | 31% to 59% / 25% to 46% / 12% to 34% | `P2_1_preseason_control.playoffs` |
| Out-of-sample R², previous season / roster / all preseason features | 0.258 / 0.437 / 0.437 | 0.27 to 0.55 (all) | `P2_1_preseason_control.foreseeability` |
| SD of the unforeseen part, in wins | 1.74 | 0.90 to 2.51 | `P2_1_preseason_control.unexpected` |
| ICC of the unforeseen part; calibrated P | -0.025; 0.66 | -0.071 to 0.026 | `P2_5_persistence` |
| ICC at 80% power (simulated) | 0.149 | — | `P2_5_persistence.simulation.calibrated` |
| Carry-over share of WAR lost / of year-to-year covariance (post hoc / declared) | 29% / 57% | — | `P2_7_levers, P2_5_persistence` |
| Declared design range, wins per WAR lost | -0.91 to -0.11 | — | `P2_2_reverse_causality.range` |
| Activation-only end rule: wins per WAR lost / one SD in wins | -0.442 / 1.72 | — | `P2_3_duration_rule.B_activation_only` |
| 2026 out-of-sample R² (models fitted through 2025) | 0.642 | — | `P2_8_check_2026.all` |
| Post hoc: departure end, wins per WAR lost / one SD in wins | -0.719 / 2.58 | — | `phase2_posthoc_departure.json` |
| Post hoc: design range with each club's opener, without the contention designs, with the windows | -1.03 to -0.29 | — | `phase2_posthoc_opener_extras.json X2` |
| Post hoc: ICC of WAR lost net of talent only (all / carry-over / new), permutation P | 0.083 (0.005) / 0.079 (0.004) / -0.031 (0.885) | — | `phase2_posthoc_opener_extras.json X6` |
| Post hoc: club share excluded at 95% (inverted simulation) | above 0.055 | — | `phase2_posthoc_opener_extras.json X7` |

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
the primary). The paper's six figures are in `results/figures/paper/` (`pipeline/paper_figures.py`).

## License

Code: MIT (`LICENSE`). Data derived from the MLB Stats API is subject to MLB's terms of use. FanGraphs data is not
included.
