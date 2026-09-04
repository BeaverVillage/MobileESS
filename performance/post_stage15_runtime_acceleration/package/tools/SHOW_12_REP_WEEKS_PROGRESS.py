#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_12_REP_WEEKS_ACTUAL_FINAL_R20")
WEEKS=[
 "W02_2025-01-13","W07_2025-02-17","W10_2025-03-10",
 "W17_2025-04-28","W18_2025-05-05","W25_2025-06-23",
 "W26_2025-06-30","W32_2025-08-11","W38_2025-09-22",
 "W41_2025-10-13","W44_2025-11-03","W51_2025-12-22",
]
METHODS=["M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE","M2_FIXED30_MOBILE",
         "M3_EVENT30_NO_LOCAL_REPAIR_MOBILE","M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"]
rows=[];done=0
for week in WEEKS:
 for method in METHODS:
  directory=ROOT/week/method
  progress_name="W02_PROGRESS.json" if week=="W02_2025-01-13" else f"{week}_PROGRESS.json"
  progress=directory/"progress"/progress_name
  if (directory/"RUNTIME_CHARACTERIZATION.json").is_file():status="PASS";completed=2016
  elif (directory/"FAILURE.json").is_file():status="FAIL_CLOSED";completed=0
  elif progress.is_file():
   try:
    value=json.loads(progress.read_text(encoding="utf-8"));status=value.get("status","RUNNING")
    completed=int(value.get("completed",0) or 0)
   except (json.JSONDecodeError,OSError,ValueError,TypeError):status="PROGRESS_READ_RETRY";completed=0
  else:status="NOT_STARTED";completed=0
  done+=completed;rows.append({"week":week,"method":method.split("_",1)[0],
                               "status":status,"completed":completed,"required":2016})
required=12*4*2016
print(json.dumps({"status":"PASS" if done==required else "RUNNING_OR_NOT_STARTED",
                  "completed_issue_runs":done,"required_issue_runs":required,"weeks":rows},indent=2))
