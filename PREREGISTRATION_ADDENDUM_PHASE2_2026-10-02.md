# Preregistration addendum, Phase 2: injury luck in MLB on public data (full paper)

**Written and sealed 2026-10-02, before any Phase 2 quantity is computed.** The sha256[:16] of this file is recorded in
`SEAL_PHASE2.txt` with the UTC time. It adds estimands to the sealed preregistration
`PREREGISTRATION_INJURY_LUCK_2026-09-30.md` (`3fd792e537b6834b`) and amends nothing in it. Every later departure goes in
`DEVIATIONS.md` under "Phase 2", with a statement of whether any output had been seen. Program: Prompt 23 §3.

## 1. What had been seen before sealing

- Everything listed in §1 of the sealed preregistration.
- All Phase 1 and Phase 1b output: `results/injury_luck_results.json` (R1-repaired primary), `results/injury_luck_results_sealed.json`,
  `results/phase1b_results.json`, `RECONCILIATION.md`, `REVIEWER2_REPORT.md` (including the reviewer's post hoc numbers) and
  `REVIEWER2_RESPONSE.md`. In particular these Phase 1b values, which bear on Phase 2, are known:
  - R2, organisation roster on Opening Day rebuilt from the transaction feed: wins per WAR lost −0.595 (SE 0.167); playoff OR
    per WAR lost 0.890; correlation with the realised-roster projection 0.92.
  - R3 designs and their range (−0.92 to −0.19 wins per WAR lost) on the realised-roster control.
  - R4 calibrated null and power for E11 on the realised-roster features (80% power near ICC 0.17); carry-over 29% of WAR lost;
    carry-over R² 0.25 and new-injury R² 0.06 on the club's prior-year WAR lost.
  - R6 P(playoffs) by format era on the realised-roster control.
  - The activation-only end rule on the sealed (pre-R1) build: mean 9.59, within-season SD 4.59, wins per WAR lost −0.230
    (`RECONCILIATION.md`, step 3). Nothing under R1.
  - E1.K_sensitivity and E2.K_sensitivity (K = 50 and 200, realised-roster control).
- **Opening-day rosters (new input, ids only).** `data_public/opening_day_40man_2015_2026.csv`: for each of the 30 clubs and each
  season 2015–2019 and 2021–2026, the MLB Stats API roster `teams/{club}/roster?rosterType=40Man&date=<D>`, where D is the day
  before the club's first scheduled regular-season game in `games_flat.csv`. The 40Man roster type returns the 40-man roster
  and players on the 60-day injured list. 330 club-seasons, 13,454 rows, 37 to 46 players per club-season, sha256[:16]
  `3a4a5b25d1420e1e`, retrieved 2026-10-02 and checked against a SHA-256 of each season's rows computed at retrieval. Only
  row counts and the retrieval checksums were looked at. The file was not joined to any projection, injury or outcome.
- **2026 coverage, descriptively.** The pinned inputs already hold the 2026 regular season: `placements_public.csv` (859 placements
  dated 2026), `games_flat.csv` (2,430 scheduled 2026 games, of which 2,401 Final or Completed Early, the same postponement
  pattern as 2022–2025), Stats API pitcher game logs through 2026-09-27, and the feed through 2026-09-29. `standings.csv` and the
  FanGraphs export end in 2025. No 2026 WAR lost, projection or episode count had been computed.
- **Not seen:** any quantity built with the opening-day rosters; any age-adjusted projection; any quantity under the
  activation-only rule with the R1 repair; any group-level or family-level foreseeability; the carry-over decomposition of the
  year-to-year covariance; any Phase 2 lever quantity; any 2026 quantity.

## 2. Gate before any Phase 2 estimate

`injury_luck.py` (R1, B = 2,000) and `phase1b_posthoc.py` are re-run on the pinned inputs with their log output stripped of
absolute paths. Every point value in the regenerated `injury_luck_results.json` and `phase1b_results.json` must equal the
published files within 1e-9 (input-file hashes excepted). If not, stop and log it.

## 3. Phase 2 estimands

Seed 20261002 unless stated. Every interval is a 95% club-clustered percentile bootstrap (2,000 draws; the 30 clubs resampled with
replacement; every model refitted and every quantile and LOSO fold recomputed in each draw) unless stated. Episodes are the R1
episodes (DEVIATIONS #10) unless P2.3 says otherwise. "Wins" conversions use the magnitude of the P2.1 wins coefficient
(§3.1); the conversion with the preregistered coefficient is reported beside it.

### P2.1 Preseason talent control (referee M3) — the paper's primary specification

- **Roster.** The opening-day 40-man roster above (duplicates within a club-season counted once).
- **Control.** `team_proj_od` = Σ over the roster of max(Marcel rate, 0) × 162, with the same Marcel as the primary (fWAR,
  weights 5/4/3, exposure from the R1 episodes, K = 100, nothing from season S). Players with no fWAR in S−1 to S−3 contribute 0.
- **Preseason roster features.** `roster_age_od` and `roster_il_days_prev_od`, defined as the preregistered `roster_age_w` and
  `roster_il_days_prev_w` but weighted over the opening-day roster (weights max(projection, 0.01); a missing birth date takes the
  roster mean; prior-season days from the R1 episodes of all clubs, 2014 and 2020 included).
- **Wins (paper primary).** OLS of W on war_lost + team_proj_od + W_prev + season fixed effects, SE clustered by club, n 270.
  Reported with the cluster-robust CI, the percentile bootstrap CI, a BCa interval (jackknife over clubs for the acceleration),
  and a wild-cluster bootstrap-t interval (unrestricted residuals, Rademacher weights by club, 9,999 replications, seed 20261004).
- **Wins conversions (paper primary).** One SD in wins = within-season SD of war_lost × |β_P2.1|; p10 → p90 in wins likewise.
  Joint intervals use each draw's own coefficient.
- **Playoffs (paper primary).** Logit of qualification on war_lost + team_proj_od + season fixed effects, 300 rows. OR per WAR
  lost; P(playoffs) for a club at the median team_proj_od, averaged over the season effects, at the R1 p10, p50 and p90 of
  war_lost. The same model fitted separately in 2015–2021 (10-club format, 180 rows) and 2022–2025 (12-club format, 120 rows),
  evaluated at the same points with the pooled median team_proj_od.
- **Foreseeability (paper primary).** Leave-one-season-out OOS R² (v1 formula) on the 240 club-seasons of the preregistered E4,
  for: prior year only (war_lost_prev); preseason roster only (team_proj_od, roster_age_od, roster_il_days_prev_od); all
  (union). Season-demeaned variant beside it. `unexpected_p2` = war_lost − the LOSO prediction of the "all" model; its
  within-season SD in WAR and wins.
- **Beside every P2.1 value:** the preregistered realised-roster value and the Phase 1b organisation-roster value (both already
  computed; shown, not refitted).
- **Fallback.** If the roster file fails its hash or covers fewer than 330 club-seasons, the organisation roster of Phase 1b R2
  becomes the paper's primary control and the paper says so.

### P2.2 Reverse causality, cleaned (referee M4)

With team_proj_od in place of team_proj, each design reports the wins coefficient with cluster-robust and bootstrap CIs:
(a) P2.1 primary; (b) episodes starting before 1 August; (c) in-contention episodes only (start < 10 games behind the last
playoff spot, the preregistered E12b proxy); (d) April–June placements and July–September wins (controls team_proj_od, W_prev,
W before 1 July, games on or after 1 July, season fixed effects); (e) two terms, in-contention and out-of-contention WAR lost;
(f) in-season onsets before 1 August with duration fixed at the diagnosis-family median of games missed (capped at the club's
games remaining); (g) two terms, WAR lost from placements dated on or before Opening Day and from in-season onsets.
**Range** = minimum and maximum over (a), (b), (c), (d), the in-contention term of (e), (f) and the in-season term of (g). The
out-of-contention term of (e) and the opening-day term of (g) are reported but excluded from the range (selection on the outcome;
not an in-season shock). Playoff OR for (b) and (c). No causal reading is drawn from any design.

### P2.3 Duration rule (referee M2)

Two episode-end rules, everything else identical:
- **Rule A (primary):** the census end (first activation or first public game back) with the full R1 repair.
- **Rule B (activation only):** the end is the first feed "Status Change" transaction after the start whose description contains
  "activated" or "reinstated" and none of paternity, bereavement, restricted, reserve list, inactive, suspension, military (the
  `reconcile_v1_public.py` pattern); then the R1 steps except the pitcher-appearance step (first season played before 2015,
  restricted list or suspension, cross-club overlap, games-played cap).
Under each rule the whole build is redone (episodes, exposures, Marcel, team_proj_od, the club-season table). Reported side by
side: within-season SD of war_lost (WAR, build-specific), one SD and p10 → p90 in wins, the P2.1 wins coefficient, the P2.1 OR
and P(playoffs) at p10 and p90, games missed per episode, and the share of episodes and of WAR lost from episodes open on the
final regular-season day. Bootstrap CIs for the wins quantities and the coefficient.

### P2.4 Projection sensitivity (referee minor 2)

Four projections: Marcel with K = 50, 100, 200, and an age-adjusted Marcel (K = 100, rate × [1 + 0.006 (29 − age)] below age 29
and × [1 + 0.003 (29 − age)] from 29, age on 30 June of season S, factor 1 when the birth date is missing). Under each, war_lost
and team_proj_od are both rebuilt with that projection. Reported: mean and within-season SD of war_lost (WAR), the P2.1 wins
coefficient and one SD in wins, with bootstrap CIs for the last two.

### P2.5 Persistence, extended (referee M5)

- (a) The E11 statistic on `unexpected_p2`: ICC(1) of the season-demeaned values, 30 clubs × 8 seasons; within-season permutation
  P (2,000 permutations); REML ICC; year-to-year r; split-half r (Spearman–Brown only when r > 0); bootstrap CI of ICC(1).
- (b) Simulation-calibrated null and power with the preseason features, as Phase 1b R4: the data-generating process is the
  in-sample fit of war_lost on the preseason roster features plus season effects, residuals permuted within season, plus a club
  effect √ρ σ u_club with √(1 − ρ) on the residual; the club's prior-year WAR lost is rebuilt from the simulated values; each panel
  goes through the exact LOSO and ICC(1) pipeline. ρ ∈ {0, 0.03, 0.06, 0.11, 0.15, 0.20, 0.25}; 1,000 panels at ρ = 0 and 500 at
  each other ρ; seed 20261003. Calibrated P = (1 + #{null ≥ observed}) / (1 + 1,000). Power at the calibrated 95th percentile;
  the ICC at 80% power by linear interpolation on the grid. Type-I rate of the permutation test on the first 200 null panels
  (200 permutations each).
- (c) The same for the preseason-roster-only LOSO residual over 300 club-seasons.
- (d) **Carry-over decomposition of year-to-year persistence.** Over the 270 club-seasons with a previous outcome season, after
  demeaning each variable within season: cov(WL_t, WL_prev) = cov(C_t, WL_prev) + cov(N_t, WL_prev), where C_t is WAR lost from
  episodes of players whose public episode was open on the final regular-season day of the previous outcome season (any club;
  the Phase 1b definition) and N_t = WL_t − C_t. Reported: the carry-over share of the covariance; the slopes of WL_t, C_t and
  N_t on WL_prev; r(N_t, N_prev); bootstrap CIs.
- **Statement rule.** If the calibrated P of (a) is ≥ .05, the paper says no stable club component was detected and gives the
  ICC at 80% power. If it is < .05, the paper says the unforeseen part persists within clubs under the preseason control and
  reports its size in WAR. Neither is a new confirmatory test; E11 as sealed remains the only one.

### P2.6 Families and roster slots (descriptive)

- Per family (taxonomy v1.1 on the first-placement diagnosis): episodes, share of WAR lost, WAR per episode, share of the family's
  WAR lost that is carry-over, share from episodes open on the final day.
- Per group (hitter, starter, reliever; the E9 rule with DEVIATIONS #1): mean WAR lost per club-season, share, carry-over share,
  open-on-final-day share; and foreseeability, the LOSO OOS R² (240 rows) of the group's club-season WAR lost on the group's own
  prior-year WAR lost plus team_proj_od, roster_age_od and roster_il_days_prev_od, with the within-season SD of the group's
  unexpected part. Bootstrap CIs for the group quantities.

### P2.7 What a club can act on (decision levers)

- (a) **Carry-over visibility.** V_t = Σ over players on the club's opening-day 40-man in season t whose public episode was open on
  the final regular-season day of the previous outcome season of their Marcel rate × 162. Reported: carry-over share of WAR lost;
  mean V_t; OLS of C_t on V_t (270 rows): slope and R²; LOSO OOS R² of C_t and of WL_t on V_t alone; bootstrap CIs.
- (b) **Depth as insurance.** For hitters, starters, relievers and all players: p50 and p90 of club-season WAR lost over the 300
  club-seasons; reserve = p90 − p50, in WAR and in wins; the unforeseen reserve, p90 − p50 of the group's unexpected part from
  P2.6 (240 rows); the sum of the three group reserves beside the all-player reserve. Bootstrap CIs.
- (c) **Workload accumulation.** Cited from companion work only (`Postseason_Injury_Risk/Postseason_results.json`,
  `D.C3_cum_ext_days_per_30`: HR per 30 days of cumulative extended rest-of-season workload, 2025 endpoint). No new computation.
- No lever built on a within-season warning sign (companion work found none in public data).

### P2.8 2026 out-of-sample check (a check, not a refit)

- The 2026 club-seasons are built with the primary rule from the pinned inputs. The games-played cap is not applied in 2026
  (no 2026 FanGraphs games); the pitcher-appearance step uses the 2026 game logs.
- Features: war_lost_prev = 2025 WAR lost; team_proj_od, roster_age_od and roster_il_days_prev_od from the 2026 opening-day
  rosters and 2025 episodes.
- The three P2.1 foreseeability models are fitted once on the 240 club-seasons of §P2.1 and used to predict 2026; nothing is
  refitted with 2026 data. Reported: the realised 2026 OOS R² (sum of squares about the training mean, the v1 formula) and its
  season-demeaned version (benchmark the 2026 mean), the 2026 mean and SD of WAR lost and of the unexpected part, and the
  2026 club ranking by unexpected WAR lost. No wins or playoff model for 2026 (2026 standings are not in the pinned inputs).

## 4. Decision rules and multiplicity

- The paper's primary specification is P2.1. The preregistered E2, E3, E4 and E5 values (realised roster) are reported beside the
  P2.1 values in the headline table and are never replaced or refitted.
- No new hypothesis test. P-values in P2.5 are reported as descriptions of persistence under the declared statement rule.
- Every Phase 2 number in the paper comes from `results/phase2_results.json`, written by `pipeline/phase2.py`.
- `pipeline/verify_phase2.py`, which imports nothing from the pipeline, recomputes from the inputs: team_proj_od for every
  club-season, the P2.1 wins coefficient and OR, the P2.1 "all" OOS R², the ICC(1) of `unexpected_p2`, the carry-over share and
  covariance share, the all-player depth reserve, and the 2026 OOS R². It must exit 0, and a perturbed copy of the results must
  make it fail.
