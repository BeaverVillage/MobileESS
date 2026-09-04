#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
EXPECTED=["W02_2025-01-13","W07_2025-02-17","W10_2025-03-10","W17_2025-04-28","W18_2025-05-05","W25_2025-06-23"]

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);a=ap.parse_args()
 manifest=HERE.parent/'INITIALIZATION/INITIAL_STATES/INITIAL_STATE_MANIFEST.json'
 x=json.loads(manifest.read_text());rows=x.get('files',[])[:6]
 if [r.get('candidate_id') for r in rows]!=EXPECTED:raise RuntimeError('first-six representative-week order drift')
 checks=[]
 for r in rows:
  pre=HERE.parent/'INITIALIZATION'/r['path'];resume=HERE.parent/'INITIALIZATION'/r['production_resume_relpath']
  ok=(sha(pre)==r['file_sha256'] and sha(resume)==r['production_resume_file_sha256']
      and int(r['week_start_index'])>=0 and json.loads(resume.read_text())['sha256']==r['state_sha256'])
  if not ok:raise RuntimeError(f"initial-state authority drift {r['candidate_id']}")
  checks.append({'candidate_id':r['candidate_id'],'start_index':int(r['week_start_index']),
                 'end_index_inclusive':int(r['week_start_index'])+2015,'state_sha256':r['state_sha256'],'pass':True})
 groups=json.loads(os.popen(f"{os.sys.executable} '{HERE/'tools/CPU_AFFINITY_4X4.py'}'").read())
 if len(groups.get('groups',[]))!=4 or any(len(g)!=4 for g in groups['groups']):raise RuntimeError('4x4 CPU topology drift')
 out={'schema_version':'mobileess.post_stage15.first6_preflight.v1','status':'PASS','weeks':checks,
      'outer_processes':4,'threads_per_process':4,'week_parallelism':1,'full_week_executed':False}
 print(json.dumps(out,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
