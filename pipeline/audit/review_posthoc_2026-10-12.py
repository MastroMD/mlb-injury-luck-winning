"""
review_posthoc_2026-10-12.py - 2 post hoc descriptive quantities raised by the 2026-10-12 internal review.
Neither changes any estimate; both qualify wording. Inputs are the repository's published result tables (no new episode build).

  U1  The "Unstated" family is every episode whose first-placement diagnosis text matched no keyword of taxonomy v1.1.
      Split its WAR lost into (a) blank diagnosis text and (b) text the taxonomy did not classify.
  U2  Net-of-talent dependence by lag. Residualize club-season WAR lost (total, carry-over, new) on team_proj_od + season
      effects (in-sample OLS, the X6 definition), then correlate the same club's residuals k outcome seasons apart
      (2019 -> 2021 counts as 1 apart, as in every carry-over quantity of the paper). A stable club effect gives similar
      correlations at every lag; carried players give a correlation concentrated at lag 1.

Usage: python3 review_posthoc_2026-10-12.py <repo results dir> <out json>
"""
import json
import sys

import numpy as np
import pandas as pd

RES, OUT = sys.argv[1:3]
S = pd.read_csv(f"{RES}/stints_public_2015_2025.csv")
T = pd.read_csv(f"{RES}/team_season_phase2.csv")
out = {"script": "review_posthoc_2026-10-12.py", "status": "post hoc (second cold read, 2026-10-12)"}

# U1 ------------------------------------------------------------------------------------------------------------------
tot = S.war_lost.sum()
U = S[S.family == "Unstated"]
blank = U.dx.isna() | (U.dx.astype(str).str.strip() == "")
ex = U[~blank].sort_values("war_lost", ascending=False).dx.str.strip().str.rstrip(".").head(12).tolist()
out["U1_unclassified"] = {"share_war_lost": float(U.war_lost.sum() / tot), "episodes": int(len(U)),
                          "blank_text": {"episodes": int(blank.sum()), "share_war_lost": float(U.war_lost[blank].sum() / tot)},
                          "text_not_classified": {"episodes": int((~blank).sum()), "share_war_lost": float(U.war_lost[~blank].sum() / tot),
                                                  "largest_examples": ex},
                          "check_family_share_equals_P2_6": None}
J = json.load(open(f"{RES}/phase2_results.json"))
fam = {f["family"]: f for f in J["P2_6_families_slots"]["families"]}
out["U1_unclassified"]["check_family_share_equals_P2_6"] = bool(abs(fam["Unstated"]["share_war_lost"] - U.war_lost.sum() / tot) < 1e-9)

# U2 ------------------------------------------------------------------------------------------------------------------
seasons = sorted(T.season.unique()); pos = {s: i for i, s in enumerate(seasons)}


def lags(col):
    M = T.copy()
    D = pd.get_dummies(M.season, drop_first=True).to_numpy(float)
    Z = np.column_stack([np.ones(len(M)), M.team_proj_od.to_numpy(float), D])
    y = M[col].to_numpy(float)
    M["r"] = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
    M["i"] = M.season.map(pos)
    W = M.pivot_table(index="tid", columns="i", values="r")
    res = {}
    for k in range(1, len(seasons)):
        a, b = [], []
        for t in range(len(seasons) - k):
            a += list(W[t]); b += list(W[t + k])
        res[k] = (float(np.corrcoef(a, b)[0, 1]), len(a))
    far = [k for k in res if k >= 3]
    # pooled correlation over all pairs >= 3 apart
    a, b = [], []
    for k in far:
        for t in range(len(seasons) - k):
            a += list(W[t]); b += list(W[t + k])
    return {"r_lag1": res[1][0], "pairs_lag1": res[1][1], "r_lag2": res[2][0], "pairs_lag2": res[2][1],
            "r_lag3plus_pooled": float(np.corrcoef(a, b)[0, 1]), "pairs_lag3plus": len(a),
            "r_by_lag": {str(k): v[0] for k, v in res.items()}}


out["U2_net_of_talent_by_lag"] = {nm: lags(col) for nm, col in (("total", "war_lost"), ("carry", "wl_carry"), ("new", "wl_new"))}
json.dump(out, open(OUT, "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k.startswith("U")}, indent=1)[:2500])
