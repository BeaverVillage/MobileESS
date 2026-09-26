from pathlib import Path
import json,hashlib,time
OUT=Path(__file__).absolute().parent
SRC=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
OLD=SRC/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1'
REV=SRC/'frozen_artifacts/v41r4_selective_actual_revision_v1'
EXT=OUT.parent/'B3_2ROUND_EXTENSION'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
cohort=OLD/'COHORTS.json';days=read(cohort)['full_May'];assert len(days)==31
cases=[];protected={};shared=[]
for day in days:
 for policy,variant in [('B0','COMMON'),('B1','COMMON'),('B2','COMMON'),('B3','1R'),('B3','2R')]:
  stage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
  actual=EXT/'production_v4_corrected/actual' if variant=='2R' else OLD
  if not (actual/'replays'/day/policy/stage/'OPENDSS_PHASE_ARRAYS.npz').exists():
   assert day=='2025-05-31' and policy in ('B2','B3');actual=REV
  ci=actual/'common_inputs'/day/policy;snapshot=read(ci/'DA_FRESH_INPUT_SNAPSHOT.json')
  joint=next(Path(p) for p in snapshot if Path(p).name=='FROZEN_JOINT_DECISION.json');assert sha(joint)==snapshot[str(joint)]
  ready=read(ci/'READY.json');assert ready['decision_SHA']==read(joint)['decision_SHA']
  grid=actual/'replays'/day/policy/stage
  receipts=[joint.parent/'DAYAHEAD_RECEIPT.json']
  if not receipts[0].exists():
   assert actual==REV and day=='2025-05-31'
   parent=read(joint.parent/'RESTORATION_PARENT.json')
   original=Path(parent['original']['path']);assert sha(original)==parent['original']['sha256']
   restore=SRC/'frozen_artifacts/v41r4_restoration_revision_v1'/day/policy
   assert sha(restore/'dayahead/FROZEN_JOINT_DECISION.json')==sha(joint)
   gate=read(restore/'ACCEPTANCE.json')
   assert gate['status']=='PASS' and not gate['final']['physical_violation'] and gate['new_joint']['sha256']==sha(joint)
   receipts=[original,joint.parent/'RESTORATION_PARENT.json',restore/'ACCEPTANCE.json',restore/'FINAL_EXECUTION_AUDIT.json',REV/'RESTORATION_EXECUTION_BINDING.json']
   receipts += [x for x in (restore/'dayahead/fresh').glob('*') if x.is_file()]
  inputs=[joint,*receipts,grid/'OPENDSS_SUMMARY.json',grid/'OPENDSS_PHASE_ARRAYS.npz',*ci.glob('*.json'),*ci.glob('*.npz'),*ci.glob('*.parquet'),*(ci/'authority').glob('*.parquet')]
  inputs += [p for p in (joint.parent/'fresh').glob('*') if p.is_file()]
  for p in inputs:protected[str(p)]=sha(p)
  cases.append(dict(case_id=f'{day}_{policy}_{variant}',day=day,policy=policy,round=variant,common_inputs=str(ci),dayahead=str(joint.parent),old_grid=str(grid),decision_sha256=sha(joint),authority='PAPER_FINAL_B3_2ROUND' if variant=='2R' else 'FINAL_V41R4_1ROUND'))
  if variant=='COMMON':shared.append(dict(day=day,policy=policy,one_round_joint_SHA=sha(joint),two_round_joint_SHA=sha(joint),basis='Paper final 2-round extension changes B3 only; B0/B1/B2 remain same frozen policy authority'))
(OUT/'MONTHLY_INPUT_AUTHORITY.json').write_text(json.dumps(dict(status='FROZEN',days=days,cases=cases,protected_files=protected,cohort_source=str(cohort),cohort_SHA=sha(cohort),requested_round_policy_rows=248,distinct_replays=155,shared_baseline_authority=shared,prior_3day_scope_superseded_by_user=True,created=time.time()),indent=2,ensure_ascii=False),encoding='utf-8')
print('FULL MAY:',len(days),'days;',len(cases),'distinct replays; 248 round-policy rows')
