from pathlib import Path
import json,hashlib,shutil,time
OUT=Path(__file__).absolute().parent
SRC=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
EXT=OUT.parent/'B3_2ROUND_EXTENSION'
OLD=SRC/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
subset=SRC/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2/acceleration_audit/FINAL_GATES_AUTHORITY_THREE_DAY_SUPERSEDED.json'
days=sorted({r[0] for r in read(subset)['days']})
assert days==['2025-05-01','2025-05-02','2025-05-12']
cases=[];protected={}
for day in days:
 for policy in ('B0','B1','B2','B3'):
  actual=EXT/'production_v4_corrected/actual' if policy=='B3' else OLD
  ci=actual/'common_inputs'/day/policy
  snapshot=read(ci/'DA_FRESH_INPUT_SNAPSHOT.json')
  joints=[Path(p) for p in snapshot if Path(p).name=='FROZEN_JOINT_DECISION.json'];assert len(joints)==1
  joint=joints[0];assert sha(joint)==snapshot[str(joint)]
  ready=read(ci/'READY.json');assert ready['decision_SHA']==read(joint)['decision_SHA']
  da=joint.parent;stage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
  grid=actual/'replays'/day/policy/stage
  assert read(grid/'OPENDSS_SUMMARY.json')['convergence_count']==96
  inputs=list(ci.glob('*.json'))+list(ci.glob('*.npz'))+list(ci.glob('*.parquet'))+list((ci/'authority').glob('*.parquet'))
  inputs += [joint,da/'DAYAHEAD_RECEIPT.json',grid/'OPENDSS_SUMMARY.json',grid/'OPENDSS_PHASE_ARRAYS.npz']
  inputs += [p for p in (da/'fresh').glob('*') if p.is_file()]
  for p in inputs:protected[str(p)]=sha(p)
  cases.append(dict(day=day,policy=policy,common_inputs=str(ci),dayahead=str(da),old_grid=str(grid),
                    decision_sha256=sha(joint),authority='PAPER_FINAL_B3_2ROUND' if policy=='B3' else 'FINAL_V41R4_BASE_POLICY'))
for name in ('qsafe.py','common.py'):
 target=OUT/'inherited'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(OLD/'frozen_code'/name,target)
for name in ('robust_search.py','cached_engine.py','METHOD_FREEZE.json','BATTERY_EFFICIENCY_AUTHORITY.json'):
 shutil.copyfile(OLD/name,OUT/'inherited'/name)
for p in (OUT/'inherited').iterdir():protected[str(OLD/('frozen_code/'+p.name if p.name in ('common.py','qsafe.py') else p.name))]=sha(p)
save(OUT/'INPUT_AUTHORITY.json',dict(status='FROZEN',days=days,policies=['B0','B1','B2','B3'],cases=cases,
 subset_source=str(subset),subset_sha256=sha(subset),subset_note='Historical frozen three-day gate later superseded by smaller acceleration audit; its existing date membership is reused by current explicit 3-day authorization.',
 paper_final_source=str(EXT/'paper_export_20260917/EXTRACTION_MANIFEST.json'),protected_files=protected,
 Planning_optimizer_calls=0,created=time.time()))
save(OUT/'EXECUTION_CONTRACT.json',dict(controller_revision='QFIRST_MINP_CAUSAL_V1_20260920',threads=4,
 semantics=['Q-first','minimal current-slot delta P for unresolved hard limits','causal energy recovery'],
 preserve=['AIDC','routes','locations','availability','DA charge/discharge commitment','Planning','Fresh'],
 future_Actual_in_controller=False,global_P_optimality_claim=False,runtime_isolated=True,
 IEEE8500_controller_copy_required_identical_SHA256=True))
print(json.dumps({'days':days,'cases':len(cases),'protected_files':len(protected)}))
