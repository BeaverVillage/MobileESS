#!/usr/bin/env python3
"""Issue April 30/30 aggregate PASS only from valid immutable day certificates."""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]; ROOT=REPO/"frozen_artifacts/v28_april_full_month_preflight"
def main()->int:
    certificates=[]; missing=[]
    for day in range(1,31):
        date=f"2025-04-{day:02d}"; path=ROOT/date/f"APRIL_DAY_CERTIFICATE_2025_04_{day:02d}.json"
        if not path.is_file(): missing.append(date); continue
        value=json.loads(path.read_text(encoding="utf-8"))
        if value.get("status")!="PASS" or value.get("certificate_sha256")!=value.get("self_check_sha256"): missing.append(date)
        else: certificates.append({"date":date,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    if missing:
        print(json.dumps({"APRIL_FULL_MONTH_PREFLIGHT_PASS":False,"valid":len(certificates),"missing_or_invalid":missing},indent=2)); return 1
    payload={"artifact_id":"APRIL_FULL_MONTH_PREFLIGHT_PASS_V1","APRIL_FULL_MONTH_PREFLIGHT_PASS":True,"valid_day_certificates":certificates,"count":30}
    path=ROOT/"APRIL_FULL_MONTH_PREFLIGHT_PASS.json"; tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,path)
    print(json.dumps(payload,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
