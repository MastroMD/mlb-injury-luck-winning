"""
negative_control_phase2.py - the verifier must FAIL on a perturbed copy of results/phase2_results.json.

Copies the results JSON and the two club-season tables to a temporary folder, perturbs three values (the P2.1 wins
coefficient +0.01, the carry-over share +0.01, the 2026 OOS R2 +0.02), runs verify_phase2.py on the copy and exits 0
only if the verifier exits 1 with exactly those three checks failing. Same arguments as verify_phase2.py.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=None)
ap.add_argument("--results", default=os.path.join(os.path.dirname(HERE), "results", "phase2_results.json"))
a = ap.parse_args()
src = os.path.dirname(os.path.abspath(a.results))
with tempfile.TemporaryDirectory() as tmp:
    for f in ("team_season_phase2.csv", "team_season_2026_phase2.csv"):
        shutil.copy(os.path.join(src, f), os.path.join(tmp, f))
    J = json.load(open(a.results))
    J["P2_1_preseason_control"]["wins"]["est"] += 0.01
    J["P2_7_levers"]["a_carry_over"]["carry_share"]["est"] += 0.01
    J["P2_8_check_2026"]["all"]["oos_r2_2026"] += 0.02
    json.dump(J, open(os.path.join(tmp, "phase2_results.json"), "w"))
    cmd = [sys.executable, os.path.join(HERE, "verify_phase2.py"), "--results", os.path.join(tmp, "phase2_results.json")]
    if a.root:
        cmd += ["--root", a.root]
    r = subprocess.run(cmd, capture_output=True, text=True)
failed = [ln for ln in r.stdout.splitlines() if ln.startswith("FAIL ")]
for ln in r.stdout.splitlines():
    if ln.startswith(("PASS", "FAIL")) or "checks passed" in ln:
        print(ln)
expect = {"P2.1 wins per WAR lost", "P2.7 carry-over share of WAR lost", "P2.8 2026 OOS R2 (all features, fitted through 2025)"}
got = {ln[6:].split(":")[0] for ln in failed}
ok = r.returncode == 1 and got == expect
print(f"\nnegative control: verifier exit {r.returncode}; failing checks {sorted(got)}")
print("NEGATIVE CONTROL: the verifier fails on the perturbed copy, as required" if ok else "NEGATIVE CONTROL FAILED")
sys.exit(0 if ok else 1)
