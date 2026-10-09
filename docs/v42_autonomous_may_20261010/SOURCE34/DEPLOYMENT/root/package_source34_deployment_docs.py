"""Preserve exact verified preparation; do not infer actual scientific success."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib
p=argparse.ArgumentParser();p.add_argument('--independent',required=True);args=p.parse_args()
R=Path('D:/v42_may_restart_20261010_02');A=R/'autonomous'
D=Path('D:/MobileESS_v42_autonomous/docs/v42_autonomous_may_20261010/SOURCE34')
P=D/'DEPLOYMENT';assert not P.exists();P.mkdir(parents=True)
def rec(p):
    b=Path(p).read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
saved=[]
def copy(src,label):
    src=Path(src);dst=P/label;dst.parent.mkdir(parents=True,exist_ok=True)
    assert not dst.exists();before=rec(src);raw=src.read_bytes()
    assert len(raw)==before['bytes'] and hashlib.sha256(raw).hexdigest()==before['sha256']
    dst.write_bytes(raw);after=rec(dst)
    assert (before['bytes'],before['sha256'])==(after['bytes'],after['sha256'])
    saved.append(dict(original=before,preserved=after));return after
for name in ['V34_VALIDATION_BINDING_TEMPLATE.json','V34_VERIFIED_REPAIR_VALIDATION.json',
    'V34_SPARSE_IMMUTABLE_FREEZE.json','V34_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json',
    'V34_ZERO_START_RETRY_PREPARATION.json','V34_ZERO_START_RETRY_DEPLOYMENT.json',
    'SOURCE34_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json',
    'SOURCE34_PRE_ENQUEUE_B2_2025-05-01_NATIVE.json','SOURCE34_PRE_ENQUEUE_B2_2025-05-02_NATIVE.json',
    'SOURCE34_PRE_ENQUEUE_B2_2025-05-03_NATIVE.json',
    'CODEX_HOURLY_AUTOMATION_VERIFICATION_20261009T230850.json',
    'build_v34_validation_template.py','freeze_sparse_v34.py','smoke_sparse_v34.py',
    'prepare_verified_v34_zero_start_retries.py','watch_source34_first_three_native.py',
    'capture_source34_pre_enqueue_continuity.py','PR_BODY_V34.md']:
    copy(A/name,'root/'+name)
copy(R/'B2_V34_ZERO_START_DEPLOYMENT_MANIFEST.json','root/B2_V34_ZERO_START_DEPLOYMENT_MANIFEST.json')
token='dd083b8daa3f407ebf4ce58d1d87e939'
for suffix in ('.ready.json','.end.json','.json'):
    copy(R/'repair_leases'/(token+suffix),'lease/'+token+suffix)
copy('D:/v42_source34_independent_review_20261010_01/SOURCE34_OPS_HELPERS_STATIC_READONLY_REVIEW.json',
    'independent/SOURCE34_OPS_HELPERS_STATIC_READONLY_REVIEW.json')
independent=json.loads(Path(args.independent).read_bytes());assert independent['PASS'] is True
copy(args.independent,'independent/'+Path(args.independent).name)
prepared=json.loads((A/'V34_ZERO_START_RETRY_PREPARATION.json').read_bytes())
for day,slots in prepared['requests_by_day_and_slot'].items():
    for slot,row in slots.items():
        assert rec(row['path'])==row
        copy(row['path'],'requests/'+day+'/'+slot+'/request.json')
copy(__file__,'root/'+Path(__file__).name)
index=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),schema='V42_SOURCE34_ACTUAL_FRESH_DEPLOYMENT_PRESERVATION',
    code_root='D:/v42run34',commit='cae08b21cb83864887e397805c0a6a8944da7f83',
    execution_SHA='dd14a820e9b65f35e13827d89143bca22e656abd10365fe5b96dd04b40160016',
    status='NINE_VERIFIED_REPAIRS_READY_WHILE_SOURCE32_FIRST3_CONTINUE',
    actual_source34_PDHG_or_RMP_execution_not_claimed=True,final_scientific_PASS_not_claimed=True,
    Native0_is_new_request_and_birth_requirement_not_current_Source32_Runtime=True,
    preparation_27_actual_canonical_admissions_Native_model_zero=True,
    normal_Source32_processes_and_Native_prefixes_preserved=True,
    original_RMP_single30s_Method1_Presolve0_and_precision_unchanged=True,
    computational_DStart_zero_is_not_Native_Pi_or_Global_bound=True,
    independent_audit_did_not_run_helpers_or_Native=True,saved_files=saved)
target=P/'ACTUAL_DEPLOYMENT_PRESERVATION_INDEX.json'
target.write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,index=rec(target),preserved_files=len(saved))))
