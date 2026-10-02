"""Where every input lives. Nothing in this repository uses an absolute path.

The pipeline scripts name their inputs by the logical keys below (the relative paths of the original build, kept
so that the input hashes recorded in results/injury_luck_results.json keep their names). Each key resolves to
  * data_public/placements_public.csv   (shipped: the derived public injured-list census),
  * data_public/opening_day_40man_2015_2026.csv   (shipped: opening-day 40-man rosters, Phase 2), or
  * a file in the inputs folder you fill yourself (see README, "Inputs you fetch yourself"):
    $INJURY_LUCK_INPUTS if set, else <repo>/inputs/.
"""
import hashlib
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.environ.get("INJURY_LUCK_INPUTS", os.path.join(REPO, "inputs"))

# logical key -> (location, file name, sha256[:16] of the file the published results were built from, required?)
FILES = {
    "Tracking_Forecast_Injury_Synthesis/public_twin/out/placements_public.csv": ("data_public", "placements_public.csv", "e5ed2129cf8218ec", True),
    "Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_team_season.csv": ("inputs", "f1_team_season.csv", "7eb47b3cd4fbc6d7", True),
    "Tracking_Forecast_Injury_Synthesis/public_twin/out/f1_results.json": ("inputs", "f1_results.json", "09b587a6cd01da00", True),
    "_staging_tmp/fangraphs_war_2010_2025.csv": ("inputs", "fangraphs_war_2010_2025.csv", "cad855bb7fd170dc", True),
    "Postseason_Injury_Risk/data/games_flat.csv": ("inputs", "games_flat.csv", "ad002536e1d8a01b", True),
    "Postseason_Injury_Risk/data/standings.csv": ("inputs", "standings.csv", "911f807ec5f69104", True),
    "Postseason_Injury_Risk/data/inputs/gamelogs_flat.csv": ("inputs", "gamelogs_flat.csv", "08345a5d95486529", True),
    "Postseason_Injury_Risk/data/people.csv": ("inputs", "people.csv", "b34f61471c31711d", True),
    "Sweeper_Injury_Risk/data/txns_live.jsonl": ("inputs", "txns_live.jsonl", "f65ea265e77b5735", True),    # R1 episode ends; reconcile_public.py
    "Hot_Hand_Bat_Tracking/repo/results/paper_results.json": ("inputs", "paper_results.json", None, False),  # optional (E10 platoon)
    "IL_Team_Burden/v2_public/data_public/opening_day_40man_2015_2026.csv": ("data_public", "opening_day_40man_2015_2026.csv", "3a4a5b25d1420e1e", True),  # Phase 2 control
}


def resolve(key):
    loc, name, _, _ = FILES[key]
    return os.path.join(REPO, "data_public", name) if loc == "data_public" else os.path.join(INPUTS, name)


def sha16(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()[:16]
