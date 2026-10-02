"""
make_figures.py - Figures 1-6 of the injury-luck paper, drawn only from the results files (no model is refitted here).

  Figure1_spread_in_wins.png          club-season injury loss relative to the median club-season, in wins (p10, p90 marked)
  Figure2_playoff_probability.png     P(playoffs) for a median-projection club by percentile of injury loss, pooled and by format
  Figure3_luck_comparators.png        SD of a season's wins across clubs: game-to-game randomness, its run-sequencing part,
                                      all injury loss and the injury loss not predicted before Opening Day
  Figure4_persistence.png             (A) unforeseen part, season t vs t-1, in wins; (B) observed ICC against its calibrated null
  Figure5_carry_over.png              (A) share of injury loss from players who ended the previous season on the IL;
                                      (B) year-to-year persistence split
  Figure6_families.png                share of injury loss by injury family, carry-over part marked

Inputs: {phase2_results.json, injury_luck_results.json, phase1b_results.json, team_season_phase2.csv} in the results folder
(v2_public/results in the study library, results/ in the public repository, where team_season_phase2.csv is written by
pipeline/phase2.py and not shipped).
Wins or percentiles on every axis; no WAR-lost level is printed. One y-axis per panel.
Usage: python3 make_figures.py [--results <results folder>] [--out <figure folder>]
Defaults: library v2_public/results -> paper/figures; repository results/ -> results/figures/paper.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
_LIB = os.path.join(HERE, "..", "v2_public", "results")
ap.add_argument("--results", default=_LIB if os.path.isdir(_LIB) else os.path.join(HERE, "..", "results"))
ap.add_argument("--out", default=os.path.join(HERE, "figures") if os.path.isdir(_LIB) else os.path.join(HERE, "..", "results", "figures", "paper"))
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
J = json.load(open(os.path.join(a.results, "phase2_results.json")))
R = json.load(open(os.path.join(a.results, "injury_luck_results.json")))
P1 = json.load(open(os.path.join(a.results, "phase1b_results.json")))
T = pd.read_csv(os.path.join(a.results, "team_season_phase2.csv"))
P21, P25, P26, P27 = J["P2_1_preseason_control"], J["P2_5_persistence"], J["P2_6_families_slots"], J["P2_7_levers"]
BW = P21["conversion_abs"]  # wins per WAR lost, magnitude (paper primary)

BLUE, BLUE_L, BLUE_D, ORANGE, GREY = "#2a78d6", "#86b6ef", "#1c5cab", "#eb6834", "#9a9893"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e0", "#ffffff"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "figure.facecolor": SURF,
                     "axes.facecolor": SURF, "savefig.facecolor": SURF, "axes.titlesize": 10, "axes.titleweight": "bold",
                     "axes.titlelocation": "left", "legend.frameon": False, "legend.fontsize": 8})


def style(ax, grid="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(length=0)
    if grid:
        getattr(ax, f"{grid}axis").grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(os.path.join(a.out, name), dpi=300, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    print("wrote", name)


# ---- Figure 1: spread of injury loss in wins ------------------------------------------------------------------------
x = (T.war_lost - T.war_lost.median()) * BW
p10, p90 = (np.quantile(T.war_lost, .1) - T.war_lost.median()) * BW, (np.quantile(T.war_lost, .9) - T.war_lost.median()) * BW
fig, ax = plt.subplots(figsize=(6.4, 3.2))
bins = np.arange(np.floor(x.min()), np.ceil(x.max()) + 0.5, 0.5)
cnts, _, _ = ax.hist(x, bins=bins, color=BLUE, edgecolor=SURF, linewidth=1.0)
top = cnts.max()
ax.set_ylim(0, top * 1.42)
for v, lab in ((p10, "10th percentile"), (p90, "90th percentile")):
    ax.axvline(v, color=INK2, linewidth=1, linestyle=(0, (3, 2)))
    ax.text(v + 0.12, top * 1.36, lab, va="top", ha="left", fontsize=8, color=INK2)
ax.annotate("", xy=(p90, top * 1.13), xytext=(p10, top * 1.13), arrowprops=dict(arrowstyle="<->", color=INK, linewidth=1))
ax.text((p10 + p90) / 2, top * 1.16, f"{P21['p10_p90_wins']['est']:.1f} wins", ha="center", va="bottom", fontsize=9,
        color=INK, fontweight="bold")
ax.set_xlabel("Wins lost to the injured list, relative to the median club-season")
ax.set_ylabel("Club-seasons")
style(ax)
ax.set_title("A club's injury season, in wins")
save(fig, "Figure1_spread_in_wins.png")

# ---- Figure 2: P(playoffs) by percentile of injury loss -------------------------------------------------------------
C = P21["figure_curve"]
pc = np.array(C["percentiles"])
fig, ax = plt.subplots(figsize=(6.4, 3.6))
ax.fill_between(pc, 100 * np.array(C["all_lo"]), 100 * np.array(C["all_hi"]), color=BLUE, alpha=0.12, linewidth=0, label="95% CI, all seasons")
ax.plot(pc, 100 * np.array(C["pre"]), color=GREY, linewidth=1.5, linestyle=(0, (4, 2)), marker="s", markersize=3.5, label="2015–2021, 10-club format")
ax.plot(pc, 100 * np.array(C["post"]), color=ORANGE, linewidth=1.5, linestyle=(0, (4, 2)), marker="^", markersize=4, label="2022–2025, 12-club format")
ax.plot(pc, 100 * np.array(C["all"]), color=BLUE, linewidth=2.2, label="All seasons")
for pct, v in zip((10, 50, 90), P21["playoffs"]["p_at_p10_p50_p90"]):
    ax.plot([pct], [100 * v], marker="o", markersize=7, color=BLUE, markeredgecolor=SURF, markeredgewidth=1.5, zorder=4)
    ax.annotate(f"{100 * v:.0f}%", (pct, 100 * v), xytext=(0, 34), textcoords="offset points", ha="center", va="bottom", fontsize=9,
                fontweight="bold", color=INK, bbox=dict(boxstyle="round,pad=0.15", fc=SURF, ec="none", alpha=0.9), zorder=5,
                arrowprops=dict(arrowstyle="-", color=INK2, linewidth=0.8, shrinkA=0, shrinkB=5))
ax.set_xticks([10, 25, 50, 75, 90]); ax.set_xticklabels(["10th\n(lucky)", "25th", "50th", "75th", "90th\n(unlucky)"])
ax.set_xlim(4, 96); ax.set_ylim(0, 75)
ax.set_xlabel("Percentile of injury loss among club-seasons")
ax.set_ylabel("Playoff probability (%)")
h, l = ax.get_legend_handles_labels()
order = [l.index("All seasons"), l.index("95% CI, all seasons"), l.index("2015–2021, 10-club format"), l.index("2022–2025, 12-club format")]
ax.legend([h[i] for i in order], [l[i] for i in order], loc="upper right")
style(ax)
ax.set_title("Playoff probability for a median-projection club")
save(fig, "Figure2_playoff_probability.png")

# ---- Figure 3: injury loss beside game-to-game randomness -------------------------------------------------------------------------------------
C5 = P1["R5_comparators"]
labels = ["Game-to-game randomness", "…of which run sequencing", "Injury loss, all", "…not predicted before Opening Day"]
vals = [C5["binomial_sd_wins_500_team_162"], C5["pythagorean_residual_sd_wins"], P21["one_sd_wins"]["est"], P21["unexpected"]["sd_wins"]["est"]]
cis = [None, None, P21["one_sd_wins"]["ci95_joint"], P21["unexpected"]["sd_wins"]["ci95"]]
cols = [GREY, GREY, BLUE, BLUE_L]
y = np.arange(4)[::-1]
fig, ax = plt.subplots(figsize=(6.4, 2.6))
ax.barh(y, vals, color=cols, height=0.55, edgecolor=SURF)
for yi, v, c_ in zip(y, vals, cis):
    if c_:
        ax.errorbar([v], [yi], xerr=[[v - c_[0]], [c_[1] - v]], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
    ax.text((c_[1] if c_ else v) + 0.12, yi, f"{v:.1f}", va="center", fontsize=9, fontweight="bold", color=INK)
ax.set_yticks(y); ax.set_yticklabels(labels, color=INK)
ax.set_xlabel("Standard deviation of a season's wins across clubs (wins)")
ax.set_xlim(0, 7.6)
style(ax, grid="x")
ax.set_title("Injury loss beside game-to-game randomness")
save(fig, "Figure3_luck_comparators.png")

# ---- Figure 4: persistence ------------------------------------------------------------------------------------------
SP = J["meta"]["seasons_foreseeability"]
U = T[T.season.isin(SP)].pivot_table(index="tid", columns="season", values="unexpected_p2")
U = (U - U.mean()) * BW
pairs = [(s - 1, s) for s in SP if s - 1 in SP]
xa = np.concatenate([U[s0].to_numpy() for s0, _ in pairs]); ya = np.concatenate([U[s1].to_numpy() for _, s1 in pairs])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 3.3), gridspec_kw={"width_ratios": [1, 1.05]})
lim = np.ceil(max(np.abs(xa).max(), np.abs(ya).max()))
a1.axhline(0, color=GRID, linewidth=0.8); a1.axvline(0, color=GRID, linewidth=0.8)
a1.scatter(xa, ya, s=16, color=BLUE, alpha=0.75, edgecolor=SURF, linewidth=0.6)
a1.set_xlim(-lim, lim); a1.set_ylim(-lim, lim); a1.set_aspect("equal")
a1.set_xlabel("Unforeseen injury loss, season t − 1 (wins)"); a1.set_ylabel("Unforeseen injury loss, season t (wins)")
a1.text(0.03, 0.03, f"r = {P25['primary']['yoy_r']:.2f}, {P25['primary']['yoy_pairs']} club pairs".replace("-", "−"), transform=a1.transAxes, va="bottom", fontsize=8, color=INK2)
style(a1, grid=None)
a1.set_title("A  Same club, consecutive seasons")
cal = P25["simulation"]["calibrated"]
edges = np.array(cal["null_primary_hist_edges"]); cnt = np.array(cal["null_primary_hist"])
a2.bar(edges[:-1], cnt, width=np.diff(edges), align="edge", color=GREY, alpha=0.55, edgecolor=SURF, linewidth=0.6, label="Simulated null (no club effect)")
a2.axvline(cal["primary_null_q95"], color=INK2, linewidth=1, linestyle=(0, (3, 2)), label="Null 95th percentile")
pcal = ("%.2f" % cal["primary_p_calibrated"]).lstrip("0")
a2.axvline(cal["primary_observed"], color=BLUE, linewidth=2.2, label=f"Observed ICC {cal['primary_observed']:.2f}, calibrated P = {pcal}".replace("-", "−"))
a2.set_xlabel("Intraclass correlation of the unforeseen part"); a2.set_ylabel("Simulated panels")
a2.set_ylim(0, cnt.max() * 1.75)
# legend on an opaque box of the surface colour, so the observed line cannot run through its text
from matplotlib.lines import Line2D
hh, ll = a2.get_legend_handles_labels()
hh.append(Line2D([], [], color="none")); ll.append(f"80% power only near ICC {cal['icc_at_80pct_power_primary']:.2f}")
lg_ = a2.legend(hh, ll, loc="upper right", fontsize=7, frameon=True, facecolor=SURF, edgecolor=SURF, framealpha=1.0, borderaxespad=0.0)
lg_.set_zorder(5)
style(a2)
a2.set_title("B  Observed against the calibrated null")
fig.tight_layout(w_pad=2.0)
save(fig, "Figure4_persistence.png")

# ---- Figure 5: carry-over -------------------------------------------------------------------------------------------
cs = P26["carry_share_by_season"]
seasons = sorted(int(s) for s in cs)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 3.0), gridspec_kw={"width_ratios": [1.5, 1]})
a1.bar(range(len(seasons)), [100 * cs[str(s)] for s in seasons], color=[BLUE_L if s == 2021 else BLUE for s in seasons], width=0.6, edgecolor=SURF)
i21 = seasons.index(2021)
a1.text(i21, 100 * cs["2021"] + 1.2, "vs '19", ha="center", va="bottom", fontsize=7, color=INK2)  # 2021 is measured against 2019
a1.axhline(100 * P27["a_carry_over"]["carry_share"]["est"], color=INK2, linewidth=1, linestyle=(0, (3, 2)),
           label=f"All seasons, {100 * P27['a_carry_over']['carry_share']['est']:.0f}%")
a1.legend(loc="upper left", fontsize=7.5)
a1.set_xticks(range(len(seasons))); a1.set_xticklabels([f"'{str(s)[2:]}" for s in seasons])
a1.set_ylabel("Share of injury loss (%)"); a1.set_xlabel("Season (2020 not an outcome season)")
a1.set_ylim(0, 50)
style(a1)
a1.set_title("A  Players who ended last season on the IL")
D = P25["carry_over_decomposition"]
sc, sn = D["slope_carry"]["est"], D["slope_new"]["est"]
a2.barh([0], [sc], color=BLUE_D, height=0.45, edgecolor=SURF, label="Carried-over injuries")
a2.barh([0], [sn], left=[sc], color=BLUE_L, height=0.45, edgecolor=SURF, label="New injuries")
a2.text(sc / 2, 0, f"{100 * D['carry_share_of_cov']['est']:.0f}%", ha="center", va="center", color="white", fontsize=9, fontweight="bold")
a2.text(sc + sn / 2, 0, f"{100 * (1 - D['carry_share_of_cov']['est']):.0f}%", ha="center", va="center", color=INK, fontsize=9, fontweight="bold")
a2.set_yticks([]); a2.set_xlim(0, max(0.6, sc + sn + 0.05)); a2.set_ylim(-0.6, 0.9)
a2.set_xlabel("Slope of this season's loss on last season's")
a2.legend(loc="upper left", ncol=1, fontsize=7.5)
style(a2, grid="x")
a2.set_title("B  Source of year-to-year persistence")
fig.tight_layout(w_pad=2.0)
save(fig, "Figure5_carry_over.png")

# ---- Figure 6: families -------------------------------------------------------------------------------------------
F = pd.DataFrame(P26["families"]).sort_values("share_war_lost")
fig, ax = plt.subplots(figsize=(6.4, 4.4))
yy = np.arange(len(F))
car = 100 * F.share_war_lost * F.carry_share; new = 100 * F.share_war_lost * (1 - F.carry_share)
ax.barh(yy, car, color=BLUE_D, height=0.62, edgecolor=SURF, label="From injuries open at the prior season's end")
ax.barh(yy, new, left=car, color=BLUE_L, height=0.62, edgecolor=SURF, label="From new injuries")
for yi, tot in zip(yy, 100 * F.share_war_lost):
    ax.text(tot + 0.25, yi, f"{tot:.0f}%", va="center", fontsize=8, color=INK)
ax.set_yticks(yy); ax.set_yticklabels(F.family, color=INK)
ax.set_xlabel("Share of all injury loss, 2015–2025 (%)")
ax.legend(loc="lower right", fontsize=7.5)
style(ax, grid="x")
ax.set_title("Where the loss sits, by injury family")
save(fig, "Figure6_families.png")
