# Deviations from PREREGISTRATION_INJURY_LUCK_2026-09-30.md (sealed 3fd792e537b6834b)

Each entry: what, why, and whether any output had been seen. None changes a primary estimate or a decision rule.

1. **E9 group rule — changed after output had been seen (coding defect).** The preregistration says a player with
   both a hitter and a pitcher row in the FanGraphs export is a hitter. The export carries a hitter row for every
   pitcher (12,298 of 12,298 pitcher player-seasons), so the rule as written made every pitcher a hitter; a debug run
   (B = 20) showed E9 with all WAR lost under "hitter". Rule used: a player with a pitcher row and fewer than 100 PA in
   his hitter row that season is a pitcher; otherwise a hitter (409 player-seasons with both roles have ≥ 100 PA).
   Only E9 depends on it. Seen before the change: every E1–E12 point value from the B = 20 debug run.

2. **Debug runs before the final run.** `injury_luck.py` was run with B = 20 and B = 5 while debugging; all point
   estimates were visible. The only code change after those runs is #1. The reported results are from one run with
   B = 2,000 (`results/injury_luck_run.log`).

3. **E1 wins intervals — addition, decided while writing the code, before any output.** The preregistration converts
   WAR to wins with the fixed F1 coefficient. Each wins quantity also carries a `_joint` interval in which the
   conversion uses each draw's own coefficient, so coefficient uncertainty propagates. The fixed-conversion interval
   is kept as declared.

4. **Reconciliation step 2 (COVID rule) on the list side — decided before the waterfall was run.** The preregistration
   names the step "COVID-era blank rule". The third-party list has no blank-note stints in 2020–2022; it labels
   COVID stints in the note instead. Its analogue of F1 dropping COVID-era blank placements is dropping COVID-labelled
   stints (note matches covid / coronavirus / health and safety), which is what step 2 does. Only counts of such
   notes had been looked at.

5. **Reconciliation step 3 (activation-only ends) — decided before the waterfall was run.** Activations are taken from
   the pinned feed (`txns_live.jsonl`, `f65ea265e77b5735`) with the census's own activation pattern, without the
   census's year-typo repair. On placements the census closed by activation, the rebuilt rule reproduces the census
   end date for `reconciliation.json: meta.activation_rule_match_on_census_activation_rows` of rows.

6. **Disattenuation reading — interpretation added after output had been seen; value unchanged.** The preregistered
   λ = cov(F1ᵣ, v1ᵣ) / var(F1ᵣ) mixes the scale difference between the builds with measurement noise, so β / λ is in
   v1 units. It is reported as declared (`E2.disattenuated.beta_disattenuated`); the IV estimate in F1 units and a
   scale-plus-noise decomposition are reported beside it (`reconciliation.json: attenuation`). Both use the
   third-party list and are labelled not public-data-only.

7. **Verifier defect fixed before its result was recorded.** The first verifier run floored the roster projection at
   zero; `framing_f1.py` floors only the rate used for WAR lost, not the roster projection. The verifier was corrected
   to match the sealed F1 code. No pipeline value changed.

8. **Figure 2 band — addition.** The P(playoffs) band along the WAR-lost grid uses 1,000 club-bootstrap draws with seed
   20260931 (`figure_support.playoff_curve`), separate from the 2,000 E13 draws, which give the intervals quoted in text.

9. **E11 limitation — found after fitting; nothing changed.** See `PHASE1_STATUS.md`: the primary residual conditions on
   the club's prior-year WAR lost, which pushes within-club residual correlation below zero even without a club
   effect, so the primary permutation test is conservative. Any calibrated null computed later is post hoc.

## Phase 1b (2026-09-30), in answer to `REVIEWER2_REPORT.md`

**What had been seen before every Phase 1b change:** all Phase 1 output (`results/injury_luck_results.json` as sealed and
run, now kept as `results/injury_luck_results_sealed.json` and in `pre_repair/`), `RECONCILIATION.md`, and the whole of
the reviewer's report and re-analyses (`REVIEWER2_REPORT.md`, including the reviewer's post hoc numbers). The
preregistration is not edited. Sealed values are reported beside every repaired value (`results/phase1b_results.json:
sealed_vs_repaired`, `E1.sealed_F1`, `E2.sealed_F1`). Two kinds of change: **defect repairs** (a data bug; the
repaired value becomes the corrected primary, the sealed value is shown beside it) and **post hoc analyses** (labelled
exploratory everywhere; they never replace a preregistered estimate).

10. **R1 — episode-end repair (DEFECT REPAIR; changes the primary).** The census ends a placement at its first
    activation or first public appearance; public appearance dates start in 2015, so placements from 2010–14 ran until
    the player's first 2015 game even when he had played in between (reviewer M1: 97 / 69 / 53 contradictory
    player-seasons in 2012 / 13 / 14; e.g. a pitcher with 195 IP charged with 160 missed games, inflating his Marcel
    rate through a 2-game exposure). Rule (`injury_luck.py --episode-rule r1`, now the default): a placement ends at the
    earliest of the census end; the player's first regular-season MLB pitching appearance after the start (Stats API
    pitcher game logs, 2010–2026); the opening day of the first season after the start year, up to 2014, in which he has
    FanGraphs games; the first feed transaction placing him on the restricted list, suspending him or declaring him
    ineligible. Then an episode at one club ends the day before the same player's later-placed episode at another club
    begins (found while verifying R1: a player carried on two clubs' lists at once, e.g. signed as a free agent while
    injured, was counted twice); an episode wholly covered is dropped. Last, games missed are trimmed from the end of a
    player-season's latest episodes so that games missed + FanGraphs games played <= team games. The sealed build is
    still run first and must reproduce F1 to 1e-9 before the repair is applied. Contradictory player-seasons (reviewer
    definition): 2012–14 from 219 to 0; every season 0. The pinned feed (`txns_live.jsonl`, f65ea265e77b5735, already in
    the prereg data table) becomes an input of `injury_luck.py`. Under R1, E1 and E2 are recomputed rather than carried,
    and the wins conversion uses the repaired E2 coefficient (the prereg fixed the F1 coefficient; that value is shown
    beside it). The E3 evaluation points are the repaired p10 / p50 / p90.
11. **R1 — the 2022 suspension case (SENSITIVITY, not in the rule).** The feed records that 12 Aug 2022 move only as
    "roster status changed", which cannot be read as a suspension without hand adjudication; R1 therefore leaves the
    episode as the census builds it, and `phase1b_results.json: R6.tatis_2022_suspension_sensitivity` removes the 48
    games after 12 Aug 2022.
12. **Verifier updated independently for R1.** `verify_injury_luck.py` implements R1 with its own code (merges,
    set operations, its own feed parse) when the results say `episode_rule = r1`, and adds a check that no player-season
    has games missed + games played above team games. Its first R1 run failed 11 checks; the cause was the cross-club
    double counting in #10, which the pipeline then handled explicitly. Output had been seen.
13. **E11 reporting (correction of a claim, not of a value).** The prereg interpretation sentence "a persistent club
    component larger than ICC 0.110 is ruled out at 80% power" does not hold for the primary residual (reviewer M5).
    It is replaced everywhere by the simulation-calibrated power (R4). The Spearman–Brown value is not reported when the
    split-half r is <= 0 (`split_half_spearman_brown: null`). Figure 3 no longer draws an MDE line.
14. **Post hoc analyses (EXPLORATORY), `pipeline/phase1b_posthoc.py` -> `results/phase1b_results.json`:** R2 preseason
    talent control (opening-day organisation roster from the public feed; the Stats API roster endpoint was blocked,
    HTTP 403); R3 reviewer designs (duration fixed at the family median, contention split, opening-day vs in-season) and
    the wins range; R4 simulation-calibrated null and power for E11 (seed 20260937) and the carry-over decomposition; R5
    luck-type comparators (binomial and Pythagorean SDs); R6 BCa intervals, P(playoffs) by format era, COVID-era-blank
    sensitivity (`injury_luck.py --keep-covid-era-blanks`, R1 rule), the 2022 suspension sensitivity.
15. **Public outputs.** `war_lost_v1` (third-party-derived) is no longer written to `team_season_public.csv`. The
    unpublished platoon value is dropped from anything external (it stays in the study JSON as `E10.platoon_one_spot`,
    labelled unpublished). Figure 2 title reads "OR (per WAR lost)".
16. **Scratch tables.** `injury_luck.py --dump-dir` writes the player-season exposure table (contains fWAR) and the
    2012–2025 episodes for the post hoc script; they are not published.

## Phase 2 (2026-10-02), against `PREREGISTRATION_ADDENDUM_PHASE2_2026-10-02.md` (sealed `6634bfeb1212f484`)

**What had been seen before the Phase 2 code ran:** §1 of the addendum. Every entry below says whether Phase 2 output had
been seen.

17. **Gate re-run (addendum §2), log hygiene.** `injury_luck.py` and `phase1b_posthoc.py` gained a warnings formatter that
    prints script base names instead of absolute paths, and the Phase 1b note on the roster endpoint was reworded. Both
    scripts were re-run on the pinned inputs. Every value in `injury_luck_results.json` and `phase1b_results.json` equals the
    published file within 1e-9, bootstrap intervals included. Three things differ, and none is a value: `meta.runtime_s`;
    `E10.platoon_one_spot.source_sha16`, because the unpublished platoon source file changed upstream while its two values
    did not (E10 platoon is not used externally); and the reworded note. In `team_season_public.csv` the three residual columns
    differ by at most 2.2e-14 (floating point on a different machine). The previous files are kept in `pre_phase2/`. No
    Phase 2 output had been seen.
18. **`SEAL.txt` wording.** The phrase that named the build environment was replaced by "before sealing". The hash, the time and the list of
    what had been seen are unchanged. This is log hygiene only, and no output was involved.
19. **Development runs before the reported run.** `phase2.py` ran twice while it was being written, with B = 10 and B = 60 and
    40 null panels. All point values were visible. One code edit preceded the first run (the gate's column comparison was
    simplified), and no code changed after any output had been seen. The reported values come from one run on the author's
    machine with B = 2,000, 1,000 null panels and 9,999 wild-cluster replications (`results/phase2_run.log`).
20. **Seeds and evaluation points not fixed by the addendum.** These were decided while the code was written, before any
    output.
    - The P2.5 permutation test uses seed 20261003.
    - Under P2.3 each rule's P(playoffs) is evaluated at that rule's own p10 and p90 of WAR lost and its own median
      team_proj_od.
    - The P2.2 split-season design uses the 270 rows with a previous-season win total, as E12c did.
    - The bootstrap draws for every Phase 2 statistic are fixed up front from seed 20261002 (a 2,000 × 30 matrix of club
      indices).
21. **Descriptive additions, no output seen.** `P2_7_levers.a_carry_over.n_open_prev_on_roster_mean`;
    `P2_1_preseason_control.figure_curve` (P(playoffs) at the 5th to 95th percentiles of WAR lost, pooled and by format, for
    Figure 2); and the null-distribution histogram in `P2_5_persistence.simulation.calibrated`, for Figure 4.
22. **Independent verifier.** `verify_phase2.py` re-implements the R1 episodes (interval union, the
    `verify_injury_luck.py` method), the Marcel projection, the opening-day control and every checked model. Its first run
    passed 17 of 17 checks. `negative_control_phase2.py` perturbs three values in a copy of the results, and the verifier fails
    on exactly those three.

## Phase 2 review (2026-10-02), post hoc

**What had been seen:** every Phase 2 output, the full paper draft and the second internal referee report
(`REVIEWER2_REPORT_PHASE2.md`). Everything in this section is post hoc. No sealed value was re-fitted or overwritten, and
`results/phase2_results.json` is unchanged. The point-by-point reply is `REVIEWER2_RESPONSE_PHASE2.md`, written from the
results files by `pipeline/write_r2_response.py`.

23. **Harness.** `pipeline/phase2_posthoc_r2.py` reads `pipeline/phase2.py` from disk and executes it with four marked
    substitutions. S1 dates Opening Day by each club's first game. S2 adds the departure end. S3 skips the gate, only under
    S2. S4 renames the outputs, so the sealed files are never opened for writing. Seeds, the 2,000 × 30 club-draw matrix,
    the null panels and the wild-cluster weights are those of the sealed run. With S1 alone, every value outside the
    S1-touched keys equals `phase2_results.json` (the script checks this and stops otherwise). The reported runs were made on
    the author's machine (`results/phase2_posthoc_*_run.log`). The same four files had been produced earlier on a second
    machine and agreed apart from run times.
24. **Opening Day for designs (f) and (g) (S1, correction).** The addendum's design (g) splits placements "dated on or
    before Opening Day" from in-season onsets. The code, copied from Phase 1b, used the league's first game. In 2019, 2024
    and 2025 that game was an international opening series about a week before most clubs played. The corrected values are
    in `results/phase2_posthoc_opener.json`. The paper reports them as post hoc rows of Table 3 beside the sealed rows, and
    the declared range is still reported.
25. **Departure end (S2, sensitivity).** An IL placement also ends at the first transaction after it began in which the
    player leaves the placing club. That covers trades, waiver claims, Rule 5 selections, contract purchases, returns, loans,
    releases, election of free agency, retirement, deaths, designation for assignment, outright assignment and waivers. A
    placement from season y is not charged in season y+1 when that club's opening-day 40-man roster for y+1 does not list
    the player. The rule applies to rule A and rule B for 2012–2026, so the projections are rebuilt. The output is
    `results/phase2_posthoc_departure.json`. It is reported as a sensitivity, and the paper's primary is unchanged.
26. **Point analyses (`--extras`)** go to `results/phase2_posthoc_{opener,departure}_extras.json`:
    - shutdown-free windows (wins before 1 August or 1 September on WAR lost before the same date);
    - design coefficients and a post hoc range, which drops (c) and both terms of (e) and adds the windows;
    - talent-control variants and the ratio to the projection's coefficient (club draws of the sealed run);
    - the foreseeability decomposition, with the projected WAR already on the IL at the club's first game;
    - the carry-over split by timing and diagnosis family, and 2021 measured against 2020;
    - persistence net of talent only (seed 20261009 for 4,000 within-season permutations), and of the residual with the
      opening-day IL feature (seed 20261011);
    - the inverted simulation, rule A only, with 500 panels per value at seed 20261005;
    - playoff probabilities at percentiles conditional on the median projection, and the playoff model with the previous
      season's wins;
    - checks of the opening-day control (leak candidates, rows without fWAR, the zero floor, later acquisitions);
    - rank agreement across projections;
    - the 2026 interval over clubs, single-season R², leave one club out;
    - the open-on-final-day stress test, season-demeaned visibility R², the depth interaction and the variance shares.
27. **Paper text and figures.**
    - Wins and playoff quantities are worded as associations.
    - "Spread" became "variance" where R² is meant.
    - The carry-over quantity is defined as WAR lost by players who ended the previous season on the IL.
    - Section 5 became "Planning quantities".
    - The comparators no longer call all injury loss "luck".
    - Figure 3 and Figure 5A were relabelled, and Figure 5A marks 2021.
    - Table 5 drops its power rows (they are in Table S4) and gains the inverted bound and the net-of-talent panel.
    - Tables S6 and S7 are new.
    - The verifier (`paper/verify_paper.py`) checks every new value against the post hoc files.
28. **Reconciliation before publication (2026-10-02, no value re-fitted).**
    - **Workload citation.** The addendum names the companion key `D.C3_cum_ext_days_per_30`, which gives HR 1.19
      (1.06–1.33) and is not adjusted for cumulative regular-season workload. The companion paper and its abstract report the
      adjusted model, `D.C3_cum_ext_days_per_30_net_of_cumulative_regular_season`, which gives 1.19 (1.06–1.34). The paper keeps
      the declared key and prints the adjusted value beside it. The build checks the companion file's hash against the one the
      sealed run recorded.
    - **Repository link.** SSAC's final review is blind, so the paper no longer prints the repository URL. The link goes on the
      submission form.
    - **Seal sentence.** It now says that the hashes reached a public repository only after the analyses had run.

29. **Revision of the paper for the SSAC full paper (2026-11-01), post hoc, no value re-fitted.** What had been seen: every
    results file and an internal review of 2026-10-12. Corrections to the paper's text: the Phase 1b organisation-roster values
    are printed beside the P2.1 primary, as §P2.1 of the addendum requires (wins per WAR lost −0.60, playoff logit slope
    −0.117); the corrected declared range (#24, −1.03 to −0.11) is quoted; the 2022–2025 realised-roster playoff row is labelled
    preregistered (`E3.format_2022plus`); the persistence statistic is named ICC(3,1) (the preregistration's ICC(1)); rounding is
    half-up, which moves one printed value (permutation-test rejections at ρ = 0.15, 70% → 71%, 141 of 200 panels). Post hoc
    quantities added from the review: the unclassified-family split and net-of-talent dependence by lag
    (`pipeline/audit/review_posthoc_2026-10-12.py` → `results/review_posthoc_2026-10-12.json`), days against value, the UCL share
    by family source, slopes by roster slot, the run-scale check, the trend in WAR lost and berths moved per season
    (`pipeline/audit/explore.py` → `results/explore_2026-10-12.json`, on the tables of `pipeline/audit/indep_recompute.py`).
    Figures are relabelled only and renumbered by first citation (`pipeline/paper_figures_rev.py`, which runs
    `pipeline/paper_figures.py` unchanged with label substitutions → `results/figures/paper_rev/`); `pipeline/paper_figures.py`
    still writes the v1 figures to `results/figures/paper/`.

30. **The paper restructured around three findings, with new post hoc analyses (2026-11-03), no sealed value re-fitted.**
    `pipeline/posthoc_r4.py` → `results/posthoc_r4_2026-11-03.json`, each an OLS on the 270 club-seasons of the wins model with
    the primary's controls and club-clustered intervals: Y1 carry-over against new-injury WAR lost (−0.74 and −0.55 wins per WAR,
    equal slopes not rejected, P = .57); Y2 the club-season's largest episode against the rest (−0.13 and −0.77, P = .35); Y3
    curvature; Y4 interaction with the opening-day projection; Y5 next-season wins given the earlier season's wins and the next
    season's projection and WAR lost (0.12, −0.19 to 0.42); Y6 non-qualifying club-seasons within their above-median injury loss
    of the last wild card (6 of 192, 2 of them ties) and the ten heaviest injury seasons; Y7 a worked example.

31. **Fresh public rebuild, the schedule fixed at the source, Baseball-Reference WAR, Steamer and ZiPS, the Opening Day IL and
    salary dollars (2026-11-04), post hoc, no sealed value re-fitted.** The sealed values remain the paper's primary; everything below is a check or an addition.
    - **Fresh rebuild.** `pipeline/fetch_inputs.py` rebuilds every Stats API input from the public API (schedule, standings,
      pitcher game logs, people, transactions); `pipeline/rerun_variant.py` reruns the README run order and `posthoc_r4.py` on
      any input folder without editing the sealed scripts (in its copy, pins of rebuilt files become recorded hashes). With the
      pinned schedule's games (`--emulate-pinned`) the sealed F1 club-season table is reproduced to 7e-15 and every wins and
      playoff value is reproduced exactly. Values built on roster or player age (the foreseeability models, the persistence
      statistics and their simulations, the age-adjusted projection) move slightly because a fresh pull of people records gives a
      few different birth dates: foreseeability R² 0.4373 → 0.4378, unforeseen SD 1.741 → 1.740 wins, ICC −0.0249 → −0.0252
      (displayed −0.02 → −0.03), calibrated P .664 → .666, single-season R² by at most 0.003, simulated power by at most 0.015. `audit/indep_recompute.py` passes 32 of 32 checks on the fresh pull, `audit/review_posthoc_2026-10-12.py`
      reproduces 51 of 51 values and `posthoc_r4.py` 148 of 148; `audit/explore.py` reproduces every value the paper quotes
      (the roster-age model X7 moves by up to 0.03). Results: `results/rerun_2026-11-04/fresh_pull_pinned_schedule/`.
    - **Schedule.** The schedule file the sealed results were built from kept the postponed record of each postponed or
      suspended game and dropped its make-up, because both share a gamePk: 667 regular-season games 2010–2026 (up to 15 per
      club-season). `fetch_inputs.py` keeps the make-up (39,772 games, equal game for game and date for date to an independent
      rebuild). Rerun on the corrected schedule (`results/rerun_2026-11-04/corrected_schedule/`), every headline value moves
      within its interval: wins per WAR lost −0.633 → −0.634, one SD of injury loss 2.28 → 2.35 wins, playoff probability
      44% → 21% unchanged between the 10th and 90th percentiles, foreseeability R² 0.437 → 0.437, ICC −0.025 (P = .78), carry-over
      28.6% → 28.4% of WAR lost and 0.39 per projected WAR, games missed per episode 49.4 → 50.2, declared design range
      −0.91 to −0.11 → −0.89 to −0.10, carry-over against new-injury wins per WAR −0.76 and −0.54 (P = .51).
    - **Baseball-Reference WAR** (`pipeline/bwar_input.py`, the published war_daily files in the FanGraphs input layout) for both
      the projection and WAR lost (`results/rerun_2026-11-04/baseball_reference_war/`): wins per WAR lost −0.594 (cluster-robust
      −0.851 to −0.338), one SD 2.13 wins, playoff probability 48% → 23%, foreseeability R² 0.454 (2026: 0.668), ICC −0.046
      (permutation P = .93), carry-over 28.5% of WAR lost and 0.39 per projected WAR, declared design range −0.80 to −0.03,
      carry-over against new-injury wins per WAR −0.84 and −0.41 (P = .20). Club-season WAR lost correlates 0.95 between the two
      WAR sources and player-season WAR 0.91.
    - **Steamer and ZiPS as the talent control.** Archived Steamer and ZiPS preseason projections (FanGraphs, available to
      members; licensed and not in this repository) were summed over each opening-day 40-man roster, negative projections
      set to zero and players without a projection counted as zero (36 and 126 of 13,419 roster rows), and replace the
      opening-day projection `team_proj_od`; WAR lost keeps the Marcel valuation (`pipeline/rerun_variant.py
      --projection-sums <csv> --projection-column steamer_pos|zips_pos`; results without the projections in
      `results/rerun_2026-11-04/steamer_control/` and `zips_control/`). Steamer and ZiPS: wins per WAR lost −0.351
      (cluster-robust −0.627 to −0.075) and −0.421 (−0.680 to −0.162), one SD 1.26 and 1.52 wins, playoff probability
      38% → 29% and 38% → 24%, foreseeability R² 0.39 and 0.42 (2026: 0.58 and 0.67), ICC −0.037 (P = .87) and −0.046
      (P = .92), declared design range −0.81 to 0.07 and −0.58 to 0.04, carry-over against new-injury wins per WAR −0.26 and
      −0.42 (P = .67) and −0.50 and −0.37 (P = .70); carry-over share and slope are unchanged. With the primary control kept
      beside them, −0.570 and −0.700 (`pipeline/posthoc_r5.py --projections`). Holding the primary control fixed, the Steamer
      club projection is 0.23 WAR lower per projected WAR on the Opening Day IL (0.13 to 0.34), ZiPS 0.05 (−0.19 to 0.30);
      under the Steamer control the WAR lost by those players is not associated with wins (−0.15, −0.61 to 0.31) and the rest
      is (−0.54, −1.12 to 0.03); under ZiPS −0.47 and −0.38. The paper reports this range as the dependence of the size of the
      association on the talent model.
    - **Projected WAR on the IL at Opening Day** (`pipeline/posthoc_r5.py` → `results/posthoc_r5_2026-11-04.json`, written on
      the fresh-pull inputs, where its R² values differ from the X4 values in `results/` by less than 0.001). The X4 feature of
      `phase2_posthoc_r2.py` (opening-day 40-man players with an episode at their club covering its first game): leave-one-
      season-out R² 0.438 → 0.581, a gain in each of the eight held-out seasons (0.04 to 0.23; club-bootstrap interval of the
      pooled gain 0.06 to 0.22), 0.483 on its own, 0.565 under a stricter definition (placement dated and announced by the
      first game of the corrected schedule), and 2026 0.643 → 0.571, so the gain did not carry to 2026; 0.48 WAR lost per
      projected WAR on the Opening Day IL beyond the declared features (cluster-robust 0.34 to 0.62). The carry-over slope
      0.39 splits into 0.77 (0.69 to 0.85) for carry-over players still on the IL at Opening Day and 0.20 (0.12 to 0.27) for
      those healthy by then; the first group holds 36% of the carry-over projected WAR and 67% of the carry-over loss. In the
      primary wins model, WAR lost by players on the IL at Opening Day (34% of WAR lost) and the rest go with −0.66 (−1.06 to
      −0.26) and −0.60 (−1.16 to −0.05) wins per WAR.
    - **In the paper.** The Opening Day IL analyses enter Sections 4.3 and 5, the abstract and the discussion with a new Table
      S4; the reruns enter Section 4.5, the limitations and a new Table S9; the salary conversion two sentences of Section 5;
      the fresh rebuild the reproducibility statement. Supplementary tables are renumbered by first citation.
    - **Dollars** (`pipeline/dollars_bref.py` → `results/dollars_bref_2026-11-04.json`, Baseball-Reference season salaries; a
      missing salary takes the adjacent season's, else the league minimum; 76% of the dollars rest on listed salaries). Salary
      attributable to IL time averaged $27.3M a club-season (10th–90th percentile $10.5M–$52.0M), 19% of the opening-day 40-man
      salary (the numerator includes players acquired after Opening Day; opening-day 40-man players alone drew 17% of their
      salary while on the IL) and $3.7M per WAR lost; 30% of it went to carry-over episodes, including carry-over players no
      longer on the opening-day roster. Prorating by games missed inherits the long public end rule, so the levels are probably
      high; insurance recoveries are not netted out. Of the salary committed at Opening
      Day to players who ended the previous season on the IL ($16.9M per club-season), 39% was paid while they were on the IL,
      against 15% for the rest of the roster. In the seasons with near-complete salary coverage (2015–2019, 2023, 2024) the
      figures are $26.7M, 19% and $3.7M per WAR.
    - `pipeline/compare_headlines.py` writes `results/rerun_2026-11-04/headline_comparison.md` (published values beside the five
      reruns).
