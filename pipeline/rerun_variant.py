"""rerun_variant.py - rerun the whole pipeline on a different set of inputs, without editing the sealed scripts
(post hoc, 2026-11-04; DEVIATIONS #31).

Copies this repository to --work, points the copy at --inputs, and, in the copy only, turns each input pin whose file
differs from the pinned file into a recorded hash, so that the scripts run instead of stopping. When the schedule or the
WAR file differs from the pinned one, the F1 reproduction gate of injury_luck.py is reported instead of enforced (it can
only pass on the sealed inputs). Then it runs the README run order and pipeline/posthoc_r4.py, and writes
<work>/results/. Used for the three reruns of DEVIATIONS #31: a fresh Stats API pull with the pinned schedule's games
(fetch_inputs.py --emulate-pinned), the corrected schedule (fetch_inputs.py), and Baseball-Reference WAR (bwar_input.py).

usage: python3 pipeline/rerun_variant.py --inputs <folder> --work <new folder> [--B 2000]
"""
import argparse, hashlib, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
ap = argparse.ArgumentParser()
ap.add_argument("--inputs", required=True); ap.add_argument("--work", required=True); ap.add_argument("--B", type=int, default=2000)
a = ap.parse_args()
if os.path.exists(a.work):
    sys.exit(f"{a.work} exists; give a new folder")
shutil.copytree(REPO, a.work, ignore=shutil.ignore_patterns(".git", "inputs", "scratch", "__pycache__"))
INP = os.path.abspath(a.inputs)
sys.path.insert(0, HERE); import paths  # noqa: E402


def sha16(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()[:16]


changed = []
for key, (loc, name, pin, req) in paths.FILES.items():
    if loc != "inputs" or pin is None:
        continue
    p = os.path.join(INP, name)
    if os.path.exists(p) and sha16(p) != pin:
        changed.append((key, name, pin))
print("inputs that differ from the pinned files:", [n for _, n, _ in changed])
for scr in os.listdir(os.path.join(a.work, "pipeline")):
    if not scr.endswith(".py"):
        continue
    q = os.path.join(a.work, "pipeline", scr); s = s0 = open(q).read()
    for key, name, pin in changed:
        s = s.replace(f'"{key}": "{pin}"', f'"{key}": None')
        s = s.replace(f'("inputs", "{name}", "{pin}"', f'("inputs", "{name}", None')
    if scr == "injury_luck.py" and any(n in ("games_flat.csv", "fangraphs_war_2010_2025.csv") for _, n, _ in changed):
        s = s.replace('    sys.exit(f"F1 GATE FAIL: max abs diff {maxdiff}")', '    print(f"F1 GATE (rerun variant, reported not enforced): max abs diff {maxdiff}")')
        s = s.replace('    sys.exit(f"F1 GATE FAIL: NaN pattern {c}")', '    print(f"F1 GATE (rerun variant): NaN pattern differs {c}")')
    if s != s0:
        open(q, "w").write(s)
env = dict(os.environ, INJURY_LUCK_INPUTS=INP)
B = str(a.B)
STEPS = [("injury_luck", ["pipeline/injury_luck.py", "--dump-dir", "scratch", "--B", B]),
         ("covid", ["pipeline/injury_luck.py", "--keep-covid-era-blanks", "--B", "3", "--out", "scratch/covid"]),
         ("phase1b", ["pipeline/phase1b_posthoc.py", "--dump", "scratch", "--covid", "scratch/covid/results/injury_luck_results.json"]),
         ("phase2", ["pipeline/phase2.py", "--B", B]),
         ("r2_opener", ["pipeline/phase2_posthoc_r2.py", "--build", "opener", "--full", "--B", B]),
         ("r2_departure", ["pipeline/phase2_posthoc_r2.py", "--build", "departure", "--full", "--B", B]),
         ("r2_opener_extras", ["pipeline/phase2_posthoc_r2.py", "--build", "opener", "--extras"]),
         ("r2_departure_extras", ["pipeline/phase2_posthoc_r2.py", "--build", "departure", "--extras"]),
         ("posthoc_r4", ["pipeline/posthoc_r4.py", "--results", "results"])]
for nm, cmd in STEPS:
    with open(os.path.join(a.work, "results", f"rerun_{nm}.log"), "w") as log:
        r = subprocess.run([sys.executable] + cmd, cwd=a.work, env=env, stdout=log, stderr=subprocess.STDOUT)
    print(f"{nm}: exit {r.returncode}", flush=True)
    if r.returncode:
        sys.exit(f"stopped at {nm}; see {a.work}/results/rerun_{nm}.log")
print("done:", os.path.join(a.work, "results"))
