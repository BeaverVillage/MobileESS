"""Complete the scale grid with AC-validated local MESS reoptimization."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for scale in (1.75, 2.0):
    commands = [
        ["stage_c_one_local.py", "0", "B2", str(scale), "1"],
        ["stage_c_one_local.py", "0", "B3", str(scale), "100"],
        ["stage_c_q_repair_trial.py", "0", "B3", str(scale), "100", "350", "87"],
    ]
    for args in commands:
        print("START", *args, flush=True)
        result = subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]],
                                cwd=HERE.parent, check=False)
        print("END", *args, result.returncode, flush=True)
        if result.returncode:
            break
