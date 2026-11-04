"""
paper_figures_rev.py - the paper's figures as revised for the SSAC full paper (2026-11-01, DEVIATIONS #29).

Runs pipeline/paper_figures.py unchanged in its data and geometry, with marked
label-only substitutions, then numbers the figures in the order the paper first cites them. No value is recomputed.

  L1  "(lucky)" / "(unlucky)" tick labels -> "(light)" / "(heavy)"                       Figure 2 (no luck framing)
  L2  "80% power only near ICC 0.15" -> "80% power only near club share ρ = 0.15"         Figure 4B (ρ is the generating-model share)
  L3  "UCL / Tommy John" -> "UCL", "Unstated" -> "Unclassified"                           Figure 5 (no player name; most has text)
  L4  carry-over legends name players on the IL at the prior season's end                 Figures 3B and 5 (definition is by player)
  L5  "Source of year-to-year persistence" -> "Source of year-to-year covariance"          Figure 3B (the decomposed quantity)
  L6  panel A title shortened to "Carry-over share by season"                             Figure 3A (it ran into panel B's title)

Old name -> new name (order of first citation): Figure5_carry_over -> Figure3_carry_over, Figure6_families -> Figure5_families,
Figure3_luck_comparators -> Figure6_luck_comparators; Figures 1, 2 and 4 keep their numbers.

Usage: python3 pipeline/paper_figures_rev.py --results results --out results/figures/paper_rev
"""
import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--results", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

src_path = os.path.join(HERE, "paper_figures.py")
src = open(src_path).read()
SUBS = [
    ('["10th\\n(lucky)", "25th", "50th", "75th", "90th\\n(unlucky)"]', '["10th\\n(light)", "25th", "50th", "75th", "90th\\n(heavy)"]'),
    ('f"80% power only near ICC {cal[\'icc_at_80pct_power_primary\']:.2f}"', 'f"80% power only near club share ρ = {cal[\'icc_at_80pct_power_primary\']:.2f}"'),
    ('ax.set_yticks(yy); ax.set_yticklabels(F.family, color=INK)',
     'ax.set_yticks(yy); ax.set_yticklabels([{"UCL / Tommy John": "UCL", "Unstated": "Unclassified"}.get(f, f) for f in F.family], color=INK)'),
    ('label="From injuries open at the prior season\'s end"', 'label="From players on the IL at the prior season\'s end"'),
    ('label="Carried-over injuries"', 'label="Carry-over (players on the IL at the prior season\'s end)"'),
    ('a2.set_title("B  Source of year-to-year persistence")', 'a2.set_title("B  Source of year-to-year covariance")'),
    ('a1.set_title("A  Players who ended last season on the IL")', 'a1.set_title("A  Carry-over share by season")'),
]
for old, new in SUBS:
    n = src.count(old)
    if n != 1:
        sys.exit(f"substitution target found {n} times: {old[:70]}")
    src = src.replace(old, new)

RENAME = {"Figure1_spread_in_wins.png": "Figure1_spread_in_wins.png", "Figure2_playoff_probability.png": "Figure2_playoff_probability.png",
          "Figure5_carry_over.png": "Figure3_carry_over.png", "Figure4_persistence.png": "Figure4_persistence.png",
          "Figure6_families.png": "Figure5_families.png", "Figure3_luck_comparators.png": "Figure6_luck_comparators.png"}
with tempfile.TemporaryDirectory() as tmp:
    sys.argv = [src_path, "--results", a.results, "--out", tmp]
    exec(compile(src, src_path, "exec"), {"__name__": "__main__", "__file__": src_path})
    made = sorted(os.listdir(tmp))
    if sorted(RENAME) != made:
        sys.exit(f"unexpected figure set {made}")
    os.makedirs(a.out, exist_ok=True)
    for old, new in RENAME.items():
        shutil.copyfile(os.path.join(tmp, old), os.path.join(a.out, new))
print("figures written to", a.out, sorted(RENAME.values()))
