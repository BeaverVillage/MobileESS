"""Resumable exact-AC diagnostics; every case has a fresh MESS P/Q solve."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
cases = [(0, "B2", s, 10) for s in (1.25, 1.5, 1.75, 2.0)]
cases += [(0, "B3", s, 30) for s in (1.25, 1.5, 1.75, 2.0)]
for index, policy, scale, radius in cases:
    command = [sys.executable, str(HERE / "stage_c_one_local.py"),
               str(index), policy, str(scale), str(radius)]
    print("START", index, policy, scale, radius, flush=True)
    result = subprocess.run(command, cwd=HERE.parent, check=False)
    print("END", index, policy, scale, radius, result.returncode, flush=True)
