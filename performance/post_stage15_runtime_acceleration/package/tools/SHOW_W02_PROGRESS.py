#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_PILOT_CURRENT")
LOG=Path("/home/jaewon/mobile_ess_work/logs/B_W02_4POLICY_ACTUAL_PILOT_CURRENT")
POLICIES=["M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE","M2_FIXED30_MOBILE","M3_EVENT30_NO_LOCAL_REPAIR_MOBILE","M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"]
rows=[]
for p in POLICIES:
 d=ROOT/p
 prog=d/"progress/W02_PROGRESS.json"
 fail=d/"FAILURE.json"
 rt=d/"RUNTIME_CHARACTERIZATION.json"
 if rt.is_file():
  x=json.loads(rt.read_text());status="PASS";completed=2016;last=5471
 elif fail.is_file():
  x=json.loads(fail.read_text());status="FAIL_CLOSED";completed=None;last=None
 elif prog.is_file():
  x=json.loads(prog.read_text());status=x.get("status");completed=x.get("completed");last=x.get("last_issue")
 else:
  status="NOT_STARTED";completed=0;last=None
 rows.append({"policy":p,"status":status,"completed":completed,"last_issue":last,
              "log":str(LOG/f"{p}.log")})
print(json.dumps({"delivery_root":str(ROOT),"policies":rows},indent=2))
