"""Add explicit conditional RMP metadata after the original27 preparation."""
from pathlib import Path
import argparse,copy,json,sys
sys.path.insert(0,'D:/MobileESS_v42_autonomous')
from v42_b2_seed_recovery_v19.common import read,record,atomic,now,digest
from v42_autonomous import recovery

p=argparse.ArgumentParser()
p.add_argument('--lease-token',required=True)
p.add_argument('--prepare-exit-code',required=True,type=int,choices=(0,))
args=p.parse_args()
root=Path('D:/v42_may_restart_20261010_02')
old_validation=root/'autonomous/V36_VERIFIED_REPAIR_VALIDATION.json'
old_prepared=root/'autonomous/V36_ZERO_START_RETRY_PREPARATION.json'
new_validation=root/'autonomous/V36_VERIFIED_REPAIR_VALIDATION_02.json'
new_prepared=root/'autonomous/V36_ZERO_START_RETRY_PREPARATION_02.json'
assert not new_validation.exists() and not new_prepared.exists()
recovery.assert_lease(root,args.lease_token)
assert args.prepare_exit_code==0
old_v_record=record(old_validation);old_p_record=record(old_prepared)
assert old_p_record['sha256']=='35e43065bcfe3fc5012bac3109c555a4f571a11583b0aa2972613c9d0b989814'
v=read(old_validation);prepared=read(old_prepared)
assert v['PASS'] is True and prepared['PASS'] is True
assert prepared['validation']==old_v_record
assert v['repair_source_SHA']=='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
assert v['RMP_Method']==1
for key in recovery.REQUIRED_VALIDATION:assert v[key] is True
assert len(v['source_files'])==99 and len(v['original_source_files'])==1007
assert all(record(row['path'])==row for key in ('source_files','original_source_files','sparse_required_additional_assets') for row in v[key])
manifest_record=prepared['deployment'];assert record(manifest_record['path'])==manifest_record
manifest=read(manifest_record['path'])
assert manifest['execution_SHA']==v['repair_source_SHA'] and len(manifest['execution_sources'])==99
assert digest(manifest['execution_sources'])==v['repair_source_SHA']
assert prepared['all_27_sealed_request_native_denied_admissions_PASS'] is True
assert prepared['all_27_actual_m_dispatch_canonical_budget_descriptor_admissions_PASS'] is True
assert prepared['all_27_current_source_cache_and_RMP_factory_admissions_PASS'] is True
assert prepared['all_27_current_source_price_seed_unmodified_production_factory_admissions_PASS'] is True
assert prepared['Native_optimize_calls']==0 and prepared['model_constructions']==0
requests=prepared['requests_by_day_and_slot']
assert set(requests)=={'2025-05-'+str(day).zfill(2) for day in range(1,10)}
for day,slots in requests.items():
    assert set(slots)=={'1','2','3'}
    for slot,row in slots.items():
        assert record(row['path'])==row
        request=read(row['path'])
        assert request['day']==day and request['worker_slot']==int(slot)
        assert request['manifest_SHA']==manifest_record['sha256']
        assert request['implementation_SHA']==v['repair_source_SHA']
        assert request['previous_attempts']==[] and request['restart_from_zero'] is True
        assert request['native_budget_seconds']==5400 and request['Threads']==1 and request['P2_calls']==0
        assert request['wall_budget_seconds'] is None and request['target_gap']==.03
        assert request['reset_authorization']==manifest['reset_authorization']
        assert record(request['reset_authorization']['path'])==request['reset_authorization']
        assert not Path(request['output']).exists()
helpers={
    'build_v36_validation_template.py':'3c7499660720a9cb1304ba5f446896565bb8d0d66b16170096db93c0bc9fdd82',
    'freeze_sparse_v36.py':'dcb9eb24777d82a8fa46ef31bc474c3d6db0a5f79983fbb35dfe78fa2c4104ba',
    'smoke_sparse_v36.py':'a563fbbbf91c385b021b94f4711560f343a0b6bf93d3714deb5d37ff74f07269',
    'prepare_verified_v36_zero_start_retries.py':'028534cb8dd97f9f555975b955939b5bc4bb758cc99f4de3447989300b87ef76'}
original_helpers={name:record(root/'autonomous'/name) for name in helpers}
assert all(original_helpers[name]['sha256']==value for name,value in helpers.items())
new_v=copy.deepcopy(v);new_v.pop('RMP_Method')
new_v.update(UTC=now(),historical_validation_with_ambiguous_RMP_Method=old_v_record,
    original_RMP_budget_entry_Method=1,eligible_current_complete_start_RMP_Native_Method=0,
    cold_ineligible_or_nonfeasible_RMP_fallback_Method=1,
    RMP_Method_policy='Original Method1 admission; only exact installed complete same-current P/D and sealed original plus Native-scaled rows/bounds within literal original1e-9 permit Method0 at the original single30-second Native boundary. Otherwise Method1. No tolerance/math/budget/call/authority change.',
    metadata_finalizer_source_script=record(__file__),original_executed_helper_records=original_helpers,
    metadata_only_correction=True,original27_request_proofs_and_manifest_bytes_unchanged=True,
    actual_Source36_Native_performance_pending=True,actual_Source36_Global_Gap_PASS_pending=True)
atomic(new_validation,new_v)
new_p=copy.deepcopy(prepared)
new_p.update(UTC=now(),validation=record(new_validation),original_preparation=old_p_record,
    original_validation=old_v_record,metadata_finalizer_source_script=record(__file__),
    metadata_only_correction=True,original_prepare_exit_code_confirmed_by_operator=args.prepare_exit_code,
    original27_request_proofs_and_manifest_bytes_unchanged=True,admissions_rerun_by_metadata_finalizer=False,
    new_Native_calls_or_models_by_metadata_finalizer=0)
atomic(new_prepared,new_p)
assert record(old_validation)==old_v_record and record(old_prepared)==old_p_record
assert record(manifest_record['path'])==manifest_record
assert all(record(row['path'])==row for slots in requests.values() for row in slots.values())
assert all(record(row['path'])==row for row in original_helpers.values())
print(json.dumps(dict(PASS=True,validation=record(new_validation),preparation=record(new_prepared),
    original27_requests_manifest_helpers_validation_preparation_preserved=True,
    queue_or_process_or_Git_changes=0,Native_optimize_calls=0,model_constructions=0)))
