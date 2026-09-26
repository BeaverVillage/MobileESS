import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent/'evidence/V41R4_May2025_raw'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
idx=read(R/'FINAL_RESULT_INDEX.json')
for e in [idx[1],idx[-1]]:
 common=R/e['final_actual'].replace('/replays/','/common_inputs/')
 jp=R/e['accepted_joint_original_path'].replace('\\','/').split('/frozen_artifacts/')[1]
 jp=R/'frozen_artifacts'/e['accepted_joint_original_path'].replace('\\','/').split('/frozen_artifacts/')[1]
 d=read(jp)['decision']; j=read(common/'ACTUAL_JOB_REPLAY.json')
 print('SAMPLE',e['day'],e['policy'],'decision keys',list(d),'jobs',len(d['AIDC_decision']))
 print('ROW',json.dumps(j['job_ledger'][0]))
 print('HEADROOM',read(jp.parent/'PLANNING_RESULT.json').keys())
 print('ACCEPTANCE',json.dumps(read(R/e['acceptance']))[:4000])
print('CONTRIBUTOR DAYS',sorted({p.parts[-5] for p in R.rglob('ACTUAL_WORKLOAD_CONTRIBUTORS.parquet')}))
sources=['dayahead/v41/actual.py','dayahead/v41/actual_dispatch.py','dayahead/v41/execution.py','dayahead/v41/reserve.py','dayahead/v41/persistence.py','dayahead/v41/data.py','dayahead/v41/scientific_archive.py','dayahead/v41r1/migration_dispatch.py','dayahead/v41/workload.py','dayahead/v40d_actual/job_replay.py']
receipt=R/'frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-01/B1/actual/ACTUAL_BOUNDARY_RECEIPT.json'
bound={f['relative_path']:f for f in read(receipt)['source']['files']}
repo=R.parents[2]/'v41r4_final_results_pr'
bindings=[]
for s in sources:
 p=repo/s;data=p.read_bytes();h=hashlib.sha256(data).hexdigest();b=bound.get(s)
 if b:assert h==b['sha256'],s
 dst=R.parents[1]/'verified_source'/s;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
 bindings.append(dict(path=s,original=str(p),copy=str(dst),sha256=h,archive_receipt=str(receipt.relative_to(R)) if b else None,hash_bound=bool(b)))
(R.parents[1]/'source_bindings.json').write_text(json.dumps(bindings,indent=2))
print('BINDINGS',bindings)
