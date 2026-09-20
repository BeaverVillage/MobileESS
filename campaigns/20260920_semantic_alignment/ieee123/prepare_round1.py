from pathlib import Path
import json,hashlib,time
OUT=Path(__file__).absolute().parent
OLD=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\frozen_artifacts\v41r4_actual_eta95_qsafe_robust_v2_perf1')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
original=read(OUT/'INPUT_AUTHORITY.json');cases=[];protected={}
for day in original['days']:
 ci=OLD/'common_inputs'/day/'B3';snapshot=read(ci/'DA_FRESH_INPUT_SNAPSHOT.json')
 joint=next(Path(p) for p in snapshot if Path(p).name=='FROZEN_JOINT_DECISION.json');assert sha(joint)==snapshot[str(joint)]
 grid=OLD/'replays'/day/'B3/ETA95_QSAFE_ACTUAL'
 for p in [joint,joint.parent/'DAYAHEAD_RECEIPT.json',grid/'OPENDSS_SUMMARY.json',grid/'OPENDSS_PHASE_ARRAYS.npz',*ci.glob('*.json'),*ci.glob('*.npz'),*ci.glob('*.parquet'),*(ci/'authority').glob('*.parquet')]:protected[str(p)]=sha(p)
 cases.append(dict(day=day,policy='B3',round='1-Round',common_inputs=str(ci),dayahead=str(joint.parent),old_grid=str(grid),decision_sha256=sha(joint),authority='FINAL_V41R4_1ROUND'))
(OUT/'ROUND1_INPUT_AUTHORITY.json').write_text(json.dumps(dict(status='FROZEN',cases=cases,protected_files=protected,days=original['days'],added_at=time.time(),reason='User explicitly requires both 1-Round and 2-Round Actual',B0_B1_B2='Same frozen decisions across round comparison; single replay referenced in both round tables'),indent=2),encoding='utf-8')
print('1-Round B3 authorities added:',len(cases))
