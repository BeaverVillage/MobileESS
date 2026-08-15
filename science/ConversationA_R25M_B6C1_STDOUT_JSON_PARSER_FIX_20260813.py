# B6-C1 wrapper parser fix
# Purpose: Gurobi may emit license/banner lines before the program JSON.
# Scientific model/solver lifecycle is unchanged.

import json

def parse_final_json_object(stdout: str):
    starts = [i for i, ch in enumerate(stdout) if ch == "{"]
    for i in reversed(starts):
        try:
            obj = json.loads(stdout[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    raise ValueError("No complete JSON object found in solver stdout")

# Replace:
#     smoke = json.loads(sm.stdout)
# with:
#     smoke = parse_final_json_object(sm.stdout)
