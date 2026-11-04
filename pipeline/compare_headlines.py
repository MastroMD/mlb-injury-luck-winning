"""compare_headlines.py - the paper's headline values side by side for several results folders (post hoc, 2026-11-04).

usage: python3 pipeline/compare_headlines.py name=<results folder> [name=<results folder> ...] [--md <out.md>]
Reads phase2_results.json and, when present, posthoc_r4_2026-11-03.json in each folder."""
import json, os, sys
def H(res):
    J = json.load(open(f"{res}/phase2_results.json")); P = J["P2_1_preseason_control"]; L = J["P2_7_levers"]; Pe = J["P2_5_persistence"]
    o = {"wins per WAR lost": P["wins"]["est"], "  cluster lo": P["wins"]["lo_cluster"], "  cluster hi": P["wins"]["hi_cluster"],
         "one SD, wins": P["one_sd_wins"]["est"], "p10-p90, wins": P["p10_p90_wins"]["est"],
         "P(playoffs) p10": P["playoffs"]["p_at_p10_p50_p90"][0], "P(playoffs) p50": P["playoffs"]["p_at_p10_p50_p90"][1], "P(playoffs) p90": P["playoffs"]["p_at_p10_p50_p90"][2],
         "playoff OR per WAR lost": P["playoffs"]["or"],
         "foreseeability OOS R2": P["foreseeability"]["all"]["oos_r2"], "2026 OOS R2": J["P2_8_check_2026"]["all"]["oos_r2_2026"],
         "unforeseen SD, wins": P["unexpected"]["sd_wins"]["est"] if isinstance(P["unexpected"]["sd_wins"], dict) else P["unexpected"]["sd_wins"],
         "ICC primary": Pe["primary"]["icc1"], "ICC perm P": Pe["primary"]["p_perm_one_sided"], "ICC calibrated P": Pe["simulation"]["calibrated"]["primary_p_calibrated"],
         "carry-over share of WAR lost": L["a_carry_over"]["carry_share"]["est"], "carry-over WAR per projected WAR": L["a_carry_over"]["C_on_V_slope"]["est"],
         "carry share of yoy covariance": Pe["carry_over_decomposition"]["carry_share_of_cov"]["est"],
         "design range most negative": J["P2_2_reverse_causality"]["range"]["most_negative"][1], "design range least negative": J["P2_2_reverse_causality"]["range"]["least_negative"][1],
         "games missed per episode": J["P2_3_duration_rule"]["A_primary"]["games_missed_per_episode"], "mean WAR lost": J["P2_3_duration_rule"]["A_primary"]["mean_war"],
         "90th-pct reserve, WAR": L["b_depth"]["all"]["reserve_war"]["est"]}
    r4 = f"{res}/posthoc_r4_2026-11-03.json"
    if os.path.exists(r4):
        Y = json.load(open(r4))
        o.update({"carry-over wins per WAR (Y1)": Y["Y1_carry_vs_new"]["wl_carry"]["est"], "new-injury wins per WAR (Y1)": Y["Y1_carry_vs_new"]["wl_new"]["est"],
                  "Y1 equal-slopes P": Y["Y1_carry_vs_new"]["wald_equal_slopes_p"], "next-season wins on WAR lost (Y5)": Y["Y5_next_season"]["with_next_season_war_lost"]["wl_t"]["est"]})
    return o
if __name__ == "__main__":
    args = sys.argv[1:]; md = None
    if "--md" in args:
        i = args.index("--md"); md = args[i + 1]; args = args[:i] + args[i + 2:]
    rows = [H(c.split("=", 1)[1]) for c in args]; names = [c.split("=", 1)[0] for c in args]
    print(f"{'quantity':38s}" + "".join(f"{n:>22s}" for n in names))
    for k in rows[0]:
        print(f"{k:38s}" + "".join(f"{(r.get(k, float('nan'))):22.4f}" for r in rows))
    if md:
        with open(md, "w") as fh:
            fh.write("| quantity | " + " | ".join(names) + " |\n|---|" + "---|" * len(names) + "\n")
            for k in rows[0]:
                fh.write(f"| {k.strip()} | " + " | ".join(f"{r.get(k, float('nan')):.4f}" for r in rows) + " |\n")
