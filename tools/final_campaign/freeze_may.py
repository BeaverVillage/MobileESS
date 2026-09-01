#!/usr/bin/env python3
"""Create the one immutable May preexecution freeze after April 30/30 PASS."""
from __future__ import annotations
import hashlib,json,os,subprocess
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]; APRIL=REPO/"frozen_artifacts/v28_april_full_month_preflight/APRIL_FULL_MONTH_PREFLIGHT_PASS.json"; OUT=REPO/"frozen_artifacts/v28_may_final_science"
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->int:
    if not APRIL.is_file() or not json.loads(APRIL.read_text(encoding="utf-8")).get("APRIL_FULL_MONTH_PREFLIGHT_PASS"): raise SystemExit("MAY_REQUIRES_APRIL_30_OF_30_PASS")
    OUT.mkdir(parents=True,exist_ok=True); artifact=REPO/"dayahead/artifacts/v28_final_dayahead_actual"
    files={p.relative_to(REPO).as_posix():sha(p) for p in sorted(artifact.rglob("*")) if p.is_file()}
    payload={"artifact_id":"MAY_FINAL_SCIENCE_PREEXECUTION_FREEZE_V1","git_head":subprocess.check_output(("git","rev-parse","HEAD"),cwd=REPO,text=True).strip(),"files":files,"day_workers":2,"gurobi_threads":4,"resolution_minutes":15,"slots_per_day":96,"cases":["B0","B1","B2","B3"],"actual_reoptimization_calls":0,"event_trigger_calls":0,"local_repair_calls":0}
    path=OUT/"MAY_FINAL_SCIENCE_PREEXECUTION_FREEZE.json"; tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,path); identity=sha(path); (OUT/"MAY_FINAL_SCIENCE_PREEXECUTION_FREEZE.sha256").write_text(identity+"  MAY_FINAL_SCIENCE_PREEXECUTION_FREEZE.json\n",encoding="ascii"); print(identity); return 0
if __name__=="__main__": raise SystemExit(main())
