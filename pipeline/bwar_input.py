"""bwar_input.py - Baseball-Reference WAR in the column layout of the FanGraphs input (post hoc robustness, 2026-11-04).

Downloads Baseball-Reference's published war_daily_bat.txt and war_daily_pitch.txt (or reads them from --src) and writes
<out>/fangraphs_war_2010_2025.csv with the FanGraphs export's columns season,name,team,g,pa,war,mlbamid,role,ip, so that
every pipeline script runs unchanged on bWAR (pins relaxed with rerun_variant.py). One row per player-season-role; team is
the Baseball-Reference club code, or '- - -' when the player had more than one club that season (as the FanGraphs export
writes it). Hitter rows carry batting WAR for every player with a plate appearance; pitcher rows carry pitching WAR with g
left empty (as in the FanGraphs export) and ip from IPouts. Baseball-Reference data are not redistributed here.

usage: python3 pipeline/bwar_input.py --out <inputs folder for the bWAR variant> [--src <folder with the two war_daily files>]
"""
import argparse, os, urllib.request
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--src", default=None)
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
src = a.src or a.out
for f in ("war_daily_bat.txt", "war_daily_pitch.txt"):
    p = os.path.join(src, f)
    if not os.path.exists(p):
        urllib.request.urlretrieve(f"https://www.baseball-reference.com/data/{f}", p)
b = pd.read_csv(os.path.join(src, "war_daily_bat.txt"), low_memory=False, na_values=["NULL"])
pt = pd.read_csv(os.path.join(src, "war_daily_pitch.txt"), low_memory=False, na_values=["NULL"])
b = b[b.year_ID.between(2010, 2025) & b.mlb_ID.notna()]; pt = pt[pt.year_ID.between(2010, 2025) & pt.mlb_ID.notna()]


def agg(df, role):
    df = df.assign(team_ID=df.team_ID.replace({"ANA": "LAA", "TBD": "TBR"}))
    g = df.groupby(["mlb_ID", "year_ID"])
    out = pd.DataFrame({"name": g.name_common.first(), "war": g.WAR.sum(min_count=1), "nteam": g.team_ID.nunique(), "team1": g.team_ID.first()})
    if role == "hitter":
        out["g"] = g.G.sum(); out["pa"] = g.PA.sum(); out["ip"] = np.nan
    else:
        ipo = g.IPouts.sum(); out["g"] = np.nan; out["pa"] = np.nan; out["ip"] = (ipo // 3) + (ipo % 3) / 10
    out["team"] = np.where(out.nteam > 1, "- - -", out.team1); out["role"] = role
    return out.reset_index().rename(columns={"mlb_ID": "mlbamid", "year_ID": "season"})


F = pd.concat([agg(b[b.PA.fillna(0) > 0], "hitter"), agg(pt, "pitcher")])[["season", "name", "team", "g", "pa", "war", "mlbamid", "role", "ip"]]
F["mlbamid"] = F.mlbamid.astype(int); F = F.dropna(subset=["war"])
F.to_csv(os.path.join(a.out, "fangraphs_war_2010_2025.csv"), index=False)
print("bWAR rows", len(F), "player-seasons", F.groupby(["mlbamid", "season"]).ngroups, "->", os.path.join(a.out, "fangraphs_war_2010_2025.csv"))
