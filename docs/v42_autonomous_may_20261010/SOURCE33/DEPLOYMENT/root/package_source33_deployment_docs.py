"""Preserve actual Source33 preparation and separate pending scientific claims."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
R=Path('D:/v42_may_restart_20261010_02');A=R/'autonomous'
D=Path('D:/MobileESS_v42_autonomous/docs/v42_autonomous_may_20261010/SOURCE33')
P=D/'DEPLOYMENT';assert not P.exists();P.mkdir(parents=True)
def rec(p):
    b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
saved=[]
def copy(src,label):
    src=Path(src);dst=P/label;dst.parent.mkdir(parents=True,exist_ok=True)
    assert not dst.exists();before=rec(src);raw=src.read_bytes()
    assert len(raw)==before['bytes'] and hashlib.sha256(raw).hexdigest()==before['sha256']
    dst.write_bytes(raw);after=rec(dst)
    assert (before['bytes'],before['sha256'])==(after['bytes'],after['sha256'])
    saved.append(dict(original=before,preserved=after));return after
for name in ['V33_VALIDATION_BINDING_TEMPLATE.json','V33_VERIFIED_REPAIR_VALIDATION.json',
    'V33_SPARSE_IMMUTABLE_FREEZE.json','V33_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json',
    'V33_ZERO_START_RETRY_PREPARATION.json','V33_ZERO_START_RETRY_DEPLOYMENT.json',
    'SOURCE33_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json',
    'SOURCE33_PRE_ENQUEUE_B2_2025-05-01_NATIVE.json','SOURCE33_PRE_ENQUEUE_B2_2025-05-02_NATIVE.json',
    'SOURCE33_PRE_ENQUEUE_B2_2025-05-03_NATIVE.json',
    'CODEX_HOURLY_AUTOMATION_VERIFICATION_20261009T223734.json',
    'build_v33_validation_template.py','freeze_sparse_v33.py','smoke_sparse_v33.py',
    'prepare_verified_v33_zero_start_retries.py','watch_source33_first_three_native.py',
    'capture_source33_pre_enqueue_continuity.py','PR_BODY_V33.md']:
    copy(A/name,'root/'+name)
copy(R/'B2_V33_ZERO_START_DEPLOYMENT_MANIFEST.json','root/B2_V33_ZERO_START_DEPLOYMENT_MANIFEST.json')
for name in ['caa98d4b4f5f436da3163557c13e96f1.ready.json',
    'caa98d4b4f5f436da3163557c13e96f1.end.json','caa98d4b4f5f436da3163557c13e96f1.json']:
    copy(R/'repair_leases'/name,'lease/'+name)
copy('D:/v42_source33_independent_review_20261010_01/SOURCE33_OPS_HELPERS_STATIC_READONLY_REVIEW.json','independent/SOURCE33_OPS_HELPERS_STATIC_READONLY_REVIEW.json')
copy('D:/v42_source33_deployment_independent_audit_20261010_01/SOURCE33_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json','independent/SOURCE33_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json')
for name in ['SOURCE32_FIRST3_INITIAL_TIMELINE_1f8d4099c96e321b.json','SOURCE32_FIRST3_INITIAL_TIMELINE_56bd9746e368071c.json']:
    copy(Path('D:/v42_source32_actual_watch_20261010')/name,'initial_build/'+name)
copy('D:/v42_source32_build_phase_independent_audit_20261010_01/SOURCE32_BUILD_PHASE_SOURCE_AND_SMALL_RECEIPT_AUDIT.json','initial_build/SOURCE32_BUILD_PHASE_SOURCE_AND_SMALL_RECEIPT_AUDIT.json')
prepared=json.loads((A/'V33_ZERO_START_RETRY_PREPARATION.json').read_bytes())
for day,slots in prepared['requests_by_day_and_slot'].items():
    for slot,row in slots.items():
        assert rec(Path(row['path']))==row
        copy(row['path'],'requests/'+day+'/'+slot+'/request.json')
index=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),schema='V42_SOURCE33_ACTUAL_FRESH_DEPLOYMENT_PRESERVATION',
    code_root='D:/v42run33',commit='dbb442f6eba9d51311681b81a063582e73227fad',
    execution_SHA='0dbd374f97febf49f0a6767d825c1e9c20d0d4084b4987707ab586ebf8521285',
    status='NINE_VERIFIED_REPAIRS_READY_WHILE_SOURCE32_FIRST3_CONTINUE',
    actual_source33_PDHG_execution_not_claimed=True,final_scientific_PASS_not_claimed=True,
    Native0_is_new_request_and_birth_requirement_not_current_Source32_Runtime=True,
    preparation_27_actual_canonical_admissions_Native_model_zero=True,
    normal_Source32_processes_and_Native_prefixes_preserved=True,
    initial_build_profile_compact_c3a_is_Compact_plus_Presolve_run_aggregate=True,
    finer_build_cause_or_speedup_not_proven=True,saved_files=saved)
p=P/'ACTUAL_DEPLOYMENT_PRESERVATION_INDEX.json';p.write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,index=rec(p),preserved_files=len(saved))))
