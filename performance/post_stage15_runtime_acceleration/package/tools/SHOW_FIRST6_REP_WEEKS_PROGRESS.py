#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path('/home/jaewon/mobile_ess_work/frozen_artifacts/B_FIRST6_REP_WEEKS_ACTUAL_CURRENT')
WEEKS=['W02_2025-01-13','W07_2025-02-17','W10_2025-03-10','W17_2025-04-28','W18_2025-05-05','W25_2025-06-23']
METHODS=['M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE','M2_FIXED30_MOBILE','M3_EVENT30_NO_LOCAL_REPAIR_MOBILE','M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION']
rows=[];done=0
for week in WEEKS:
 for method in METHODS:
  d=ROOT/week/method;p=d/'progress'/('W02_PROGRESS.json' if week=='W02_2025-01-13' else f'{week}_PROGRESS.json');fail=d/'FAILURE.json';final=d/'RUNTIME_CHARACTERIZATION.json'
  if final.is_file():status='PASS';completed=2016
  elif fail.is_file():status='FAIL_CLOSED';completed=0
  elif p.is_file():
   x=json.loads(p.read_text());status=x.get('status','RUNNING');completed=int(x.get('completed',0) or 0)
  else:status='NOT_STARTED';completed=0
  done+=completed;rows.append({'week':week,'method':method.split('_',1)[0],'status':status,'completed':completed,'required':2016})
print(json.dumps({'status':'PASS' if done==6*4*2016 else 'RUNNING_OR_NOT_STARTED','completed_issue_runs':done,
                  'required_issue_runs':6*4*2016,'weeks':rows},indent=2))
