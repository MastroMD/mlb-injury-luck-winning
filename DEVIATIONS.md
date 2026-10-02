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
