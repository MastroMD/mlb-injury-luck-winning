"""
injury_luck_figures.py — the three candidate figures (Prompt 21 §4 step 5), drawn only from
results/injury_luck_results.json and results/team_season_public.csv.

  Figure1_war_lost_distribution.png   WAR lost per club-season (300), p10-p90 league band
  Figure2_playoff_probability.png     P(playoffs) vs WAR lost, median-projection club, bootstrap band
  Figure3_persistence.png             (a) unexpected WAR lost, season t vs t-1; (b) ICC with permutation-null band

One y-axis per panel. (Public-repository copy: output folder results/figures.) Club/estimate colour #2a78d6; league reference and null bands in neutral grey.
Usage (from the repository root): python3 pipeline/injury_luck_figures.py [--out <folder>]
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = ap.parse_args()
R = json.load(open(os.path.join(a.out, "results", "injury_luck_results.json")))
_pb = os.path.join(a.out, "results", "phase1b_results.json")
CAL = json.load(open(_pb))["R4_E11_calibration"] if os.path.exists(_pb) else None
T = pd.read_csv(os.path.join(a.out, "results", "team_season_public.csv"))
FIG = os.path.join(a.out, "results", "figures"); os.makedirs(FIG, exist_ok=True)

BLUE, GREY, BAND, INK, INK2, GRID, SURF = "#2a78d6", "#9a9893", "#e4e3df", "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "figure.facecolor": SURF, "axes.facecolor": SURF})


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(os.path.join(FIG, name), dpi=200, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)


# ---------------------------------------------------------------- Figure 1
E1 = R["E1"]
fig, ax = plt.subplots(figsize=(7, 4))
ax.axvspan(E1["p10"], E1["p90"], color=BAND, zorder=0, lw=0)
bins = np.arange(0, np.ceil(T.war_lost.max()) + 1, 1.0)
ax.hist(T.war_lost, bins=bins, color=BLUE, rwidth=0.86, zorder=2)
for v, lab in ((E1["p10"], f"p10 {E1['p10']:.1f}"), (E1["p90"], f"p90 {E1['p90']:.1f}")):
    ax.axvline(v, color=GREY, lw=1, zorder=1)
    ax.text(v, ax.get_ylim()[1] * 0.97, lab, ha="center", va="top", color=INK2, fontsize=9, backgroundcolor=SURF)
style(ax)
ax.set_xlabel("WAR lost to the injured list per club-season (public feed)")
ax.set_ylabel("Club-seasons")
ax.set_title(f"Mean {E1['mean']:.1f} WAR; SD across clubs within a season {E1['sd_within_season']:.1f} WAR "
             f"(≈ {E1['one_sd_wins']:.1f} wins)", loc="left", fontsize=10.5)
ax.text(0, -0.2, "300 club-seasons, 2015–2025 excluding 2020. Grey band: league 10th–90th percentile.",
        transform=ax.transAxes, color=INK2, fontsize=8.5)
save(fig, "Figure1_war_lost_distribution.png")

# ---------------------------------------------------------------- Figure 2
pc = R["figure_support"]["playoff_curve"]; E3 = R["E3"]["all"]
x = np.array(pc["war_lost_grid"])
fig, ax = plt.subplots(figsize=(7, 4))
ax.fill_between(x, pc["lo"], pc["hi"], color=BAND, lw=0, zorder=0)
ax.plot(x, pc["p"], color=BLUE, lw=2, solid_capstyle="round", zorder=2)
for v, p, lab in zip(E3["war_lost_at"], E3["p_at_p10_p50_p90"], ("p10", "p50", "p90")):
    ax.scatter([v], [p], s=48, color=BLUE, edgecolor=SURF, linewidth=2, zorder=3)
    ax.annotate(f"{lab}: {p * 100:.0f}%", (v, p), xytext=(6, 8), textcoords="offset points", color=INK, fontsize=9)
style(ax)
ax.set_ylim(0, max(pc["hi"]) * 1.05)
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
ax.set_xlabel("WAR lost to the injured list in the season")
ax.set_ylabel("P(playoffs), median-projection club")
ax.set_title(f"OR (per WAR lost) {E3['or_per_war_lost']:.2f} "
             f"(95% CI {E3['ci95_bootstrap']['or'][0]:.2f}–{E3['ci95_bootstrap']['or'][1]:.2f})", loc="left", fontsize=10.5)
ax.text(0, -0.2, f"Logit with season fixed effects and roster projection; grey band: club-bootstrap 95% interval ({pc['draws']} draws).",
        transform=ax.transAxes, color=INK2, fontsize=8.5)
save(fig, "Figure2_playoff_probability.png")

# ---------------------------------------------------------------- Figure 3
SP = R["E4"]["seasons"]
U = T[T.season.isin(SP)].pivot_table(index="tid", columns="season", values="unexpected_oos")
U = U - U.mean(axis=0)
pairs = [(s - 1, s) for s in SP if s - 1 in SP]
xa = np.concatenate([U[s0].to_numpy() for s0, _ in pairs]); ya = np.concatenate([U[s1].to_numpy() for _, s1 in pairs])
E11 = R["E11"]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.1, 1]})
lim = np.ceil(max(np.abs(xa).max(), np.abs(ya).max())) + 1
ax1.axhline(0, color=GRID, lw=1); ax1.axvline(0, color=GRID, lw=1)
ax1.scatter(xa, ya, s=22, color=BLUE, alpha=0.75, edgecolor=SURF, linewidth=0.8, zorder=2)
ax1.set_xlim(-lim, lim); ax1.set_ylim(-lim, lim); ax1.set_aspect("equal")
style(ax1); ax1.xaxis.grid(True, color=GRID, linewidth=0.8)
ax1.set_xlabel("Unexpected WAR lost, season t−1"); ax1.set_ylabel("Unexpected WAR lost, season t")
ax1.set_title(f"(a) Year to year r = {E11['primary']['yoy_r']:.2f} ({E11['primary']['yoy_pairs']} club pairs)", loc="left", fontsize=10.5)
rows = [("Primary: out-of-sample\nunexpected part", E11["primary"], "calibrated"),
        ("Sensitivity: roster-only\nout-of-sample residual", E11["sens_roster_loso_300"], "perm"),
        ("Sensitivity: roster-only\nin-sample residual", E11["sens_roster_insample_300"], "perm")]
for i, (lab, e, kind) in enumerate(rows):
    y = len(rows) - 1 - i
    q95 = CAL["calibrated"]["primary_null_q95"] if (kind == "calibrated" and CAL) else e["null_q95"]
    p_ = CAL["calibrated"]["primary_p_calibrated"] if (kind == "calibrated" and CAL) else e["p_perm_one_sided"]
    ax2.fill_betweenx([y - 0.3, y + 0.3], 0, q95, color=BAND, lw=0, zorder=0)
    ax2.plot(e["ci95_icc1"], [y, y], color=BLUE, lw=2, solid_capstyle="round", zorder=2)
    ax2.scatter([e["icc1"]], [y], s=48, color=BLUE, edgecolor=SURF, linewidth=2, zorder=3)
    ax2.annotate(f"ICC {e['icc1']:.3f}, {'calibrated' if kind == 'calibrated' and CAL else 'permutation'} P = {p_:.2f}", (e["icc1"], y),
                 xytext=(0, 10), textcoords="offset points", ha="center", color=INK, fontsize=8.5)
ax2.axvline(0, color=GREY, lw=1)
ax2.set_yticks(range(len(rows))); ax2.set_yticklabels([r[0] for r in rows][::-1], fontsize=8.5)
ax2.set_ylim(-0.6, len(rows) - 0.3)
style(ax2); ax2.yaxis.grid(False); ax2.xaxis.grid(True, color=GRID, linewidth=0.8)
ax2.set_xlabel("Intraclass correlation of clubs across seasons")
ax2.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(5))
ax2.set_title("(b) Club persistence, with the null band", loc="left", fontsize=10.5)
if CAL:
    pw = CAL["calibrated"]["power_primary_calibrated_critical"]; pa = CAL["calibrated"]["power_sensA_calibrated_critical"]
    note = (f"Season-demeaned. Grey band in (b): 0 to the one-sided 95th percentile of the null — for the primary, a simulation-calibrated "
            f"null ({CAL['n_panels']['0.0']:,} panels; post hoc),\nbecause the permutation null does not hold for a residual that conditions on the club's "
            f"prior year; for the sensitivities, the permutation null (clubs shuffled within season). Line: club-bootstrap 95% CI.\n"
            f"Power at ICC 0.11 (simulated): primary {pw['0.11']:.2f}, roster-only residual {pa['0.11']:.2f}; at ICC 0.20: {pw['0.2']:.2f} and {pa['0.2']:.2f}.")
else:
    note = "Season-demeaned. Grey band in (b): 0 to the 95th percentile of the permutation null (clubs shuffled within season); line: club-bootstrap 95% CI."
fig.text(0.01, -0.09, note, color=INK2, fontsize=8)
fig.tight_layout()
save(fig, "Figure3_persistence.png")
print("figures written to", FIG)
