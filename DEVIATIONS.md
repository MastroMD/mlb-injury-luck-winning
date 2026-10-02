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
