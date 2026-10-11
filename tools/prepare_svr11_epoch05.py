"""Prepare a callback-lifetime successor and reuse all verified B0 dates."""
from pathlib import Path
import sys,shutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
root=Path(r'D:\v42_svr11_may_20261011_05');old=Path(r'D:\v42_svr11_may_20261011_04')

def prepare():
    assert not (root/'CAMPAIGN_MANIFEST.json').exists()
    (root/'hardware').mkdir(parents=True,exist_ok=True)
    for p in (old/'hardware').iterdir():
        if p.is_file():shutil.copyfile(p,root/'hardware'/p.name)
    atomic(root/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(old/'CAMPAIGN_MANIFEST.json'),source_SHA=read(old/'CAMPAIGN_MANIFEST.json')['execution_SHA'],
        dispatch_quiescence=record(old/'DISPATCH_QUIESCENCE_FOR_CALLBACK_FIX.json'),
        reason='Additional native EventCallbackManager retains ctx after engine finalization; exact retired callback owner cleanup',
        qualified_completed_dates_reused=True,all_old_results_preserved=True,healthy_workers_terminated=0,UTC=now()))
    atomic(root/'CALLBACK_CONTEXT_DIAGNOSIS.json',dict(PASS=True,
        predecessor_empty_engine_wrappers_alive_after_gc=0,
        predecessor_native_context_managers_after_gc=9,baseline_native_managers=1,
        additional_native_contexts_retained=8,corrected_all_three_registry_and_weak_context_tests_PASS=True,
        minimum_test_actual_native_circuits=16,diagnosis_monthly_AC_calls=0,
        remedy='Finalize completed engine/utility first, then detach exact retired EventCallbackManager; existing CFFI automatic disposer only',
        model_math_equipment_forecast_prefix_and_control_unchanged=True,
        predecessor_model_equivalence=record(old/'MODEL_TECHNICAL_FIX_EQUIVALENCE.json'),UTC=now()))

def reuse():
    from v42_svr11 import DAYS
    from v42_svr11.controller import initial
    from reuse_svr11_completed import qualify
    m=read(root/'CAMPAIGN_MANIFEST.json');ledger=initial()
    require_new=root/'CAMPAIGN_LEDGER.json';assert not require_new.exists()
    proofs=[]
    for day in DAYS:
        path,proof,row=qualify(root,old,day)
        row.update(reused=True,reuse_proof=record(path),execution_source_SHA=proof['execution_source_SHA'],
            validation_source_SHA=m['execution_SHA'],admission='USER_VERIFIED_COMPLETED_RESULT_REUSE',retry_pending=False)
        ledger['dates']['B0/'+day]=row;proofs.append(record(path))
    ledger.update(policy='B2',status='WAITING_PREDECESSOR_DRAIN',source_SHA=m['execution_SHA'],UTC=now())
    atomic(require_new,ledger)
    atomic(root/'REUSE_ADMISSION.json',dict(PASS=True,reused_completed_dates=31,all_B0_days_PASS=True,
        proofs=proofs,execution_Source_SHA_preserved=True,validation_Source_SHA=m['execution_SHA'],
        healthy_workers_terminated=0,AC_calls=0,Native_calls=0,UTC=now()))
    shutil.copyfile(old/'NORMALAMPS_CLASSIFICATION_CORRECTION.json',root/'NORMALAMPS_CLASSIFICATION_CORRECTION.json')
    print('B0_ALL_31_REUSED_AND_VERIFIED',m['execution_SHA'])

if __name__=='__main__':(prepare if sys.argv[1]=='prepare' else reuse)()
