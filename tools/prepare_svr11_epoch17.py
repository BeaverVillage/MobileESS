"""Release a new immutable campaign only after one completed Root180 probe."""
from pathlib import Path
import copy, math, subprocess, sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import atomic,read,record,digest,now
from v42_common_campaign.authority import source_files
from v42_common_mess import VERSION
from v42_svr11 import DAYS
from v42_svr11.milp_release import _validate_root180
OLD=Path(r'D:\v42_svr11_may_20261011_16')
ROOT=Path(r'D:\v42_svr11_may_20261011_17')
DEV=Path(r'D:\v42_root180_development_20261011')
GIB=1024**3


def release():
    sources=source_files();source=digest(sources);old=read(OLD/'CAMPAIGN_MANIFEST.json')
    contract=dict(schema='SVR11_ROOT180_EXACT_RELEASE_V1',source_SHA=source,
        algorithm_version=VERSION,A1_A2_algorithms_changed=False,M_native_limit_seconds=1800,
        representative_root_validation=record(DEV/'ROOT180_VALIDATION.json'),
        development_results_promoted=0,UTC=now())
    _validate_root180(contract)
    from prepare_svr11_epoch15 import preserved_science
    science=preserved_science(old,sources)
    import psutil
    for process in psutil.process_iter(['name']):
        try:
            args=process.cmdline()
            if ('-m' in args and args[args.index('-m')+1]=='v42_svr11.worker'
                    and str(OLD).lower() in ' '.join(args).lower()):
                raise PermissionError('ROOT180_PREDECESSOR_WORKER_NOT_EXITED')
        except psutil.Error:continue
    if (ROOT/'CAMPAIGN_MANIFEST.json').exists():raise PermissionError('IMMUTABLE_SOURCE17_ALREADY_RELEASED')
    ROOT.mkdir(exist_ok=True)
    import prepare_svr11_epoch14 as helper
    helper.OLD=OLD;helper.ROOT=ROOT
    state=dict(old=old,sources=sources,source_SHA=source)
    inputs=helper.raw_and_hardware(state)
    import prepare_svr11_epoch16 as cache_helper
    cache_helper.OLD=OLD;cache_helper.ROOT=ROOT
    cache=cache_helper.forecast(old,sources)
    validation=read(DEV/'ROOT180_VALIDATION.json')
    authority=ROOT/'VALIDATED_CONSTRUCTION_ALGORITHM.json'
    atomic(authority,dict(source_SHA=source,construction_algorithms_unchanged=True,
        comparison_basis='Future date construction uses the identical Source17 algorithm validated on fresh May01',
        representative_root_validation=record(DEV/'ROOT180_VALIDATION.json'),
        new_security_proofs_generated_from_each_current_input=True,user_authorized_no_daily_proof=True,
        previous_source_SHA=old['execution_SHA'],old_policy_results_reused=0,UTC=now()))
    atomic(ROOT/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json',contract)
    atomic(ROOT/'UNCHANGED_PHYSICAL_AND_A_SCIENCE.json',dict(science,source_SHA=source,origin_manifest=record(OLD/'CAMPAIGN_MANIFEST.json')))
    atomic(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),monitor_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),
        source_SHA=old['execution_SHA'],dispatch_quiescence=record(OLD/'DISPATCH_QUIESCENCE_FOR_PLANNING_MODEL_REPAIR.json'),
        scientific_model_change=False,physical_equipment_change=False,optimizer_reformulation_change=True,
        qualified_completed_dates_reused=True,qualified_completed_arms_reused=['B0'],
        healthy_workers_terminated=0,old_policy_results_reused=0,
        reason='Fresh current-input exact reduction and completed Root180 validated; B2/B1/B3 all Native0',UTC=now()))
    from v42_svr11.model_release import validate as model_validate
    from v42_svr11.milp_release import validate as milp_validate
    memory=copy.deepcopy(old['B3_memory_admission'])
    peak=max(validation['memory']['peak_RSS_bytes'],validation['memory']['peak_private_commit_bytes'])
    reserve=max(7*GIB,math.ceil((peak+GIB)/GIB)*GIB)
    memory['worker_reservation_bytes'].update(M1=reserve,M2=reserve)
    manifest=copy.deepcopy(old)
    manifest.update(root=str(ROOT),code_root=str(SOURCE),run_id='SVR11_FINAL_MAY_'+ROOT.name,
        execution_sources=sources,execution_SHA=source,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),
        hardware=record(ROOT/'hardware/HARDWARE.json'),scenario=record(ROOT/'hardware/SCENARIO.json'),
        thermal=record(ROOT/'hardware/THERMAL.json'),input_receipts=inputs,
        implementation=dict(version=old['implementation']['version'],sources=sources),builder_original_sources=sources,
        scientific_model_validation=model_validate(ROOT,sources),full_milp_validation=milp_validate(ROOT,sources),
        predecessor_drain_contract=record(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json'),model_checkpoint_reuse_contract=cache,
        B2_memory_admission=memory,B3_memory_admission=memory,worker_counts=dict(B0=old['worker_counts']['B0'],B2=2,B1=1,B3=2),
        B3_stagewise_batch=True,B3_stage_worker_counts=dict(M1=2,A2=1,M2=2,ACTUAL=1),
        independent_model_proof_replay=False,validated_construction_algorithm=record(authority),
        optimization_results_reused=0,B2_all31_fresh_Native_zero=True,B1_all31_fresh_Native_zero=True,
        B3_all31_fresh_Native_zero=True,M_target_global_gap=.03,native_M_limit_seconds=1800,
        A1_A2_algorithms_changed=False,full_MILP_measured_peak_bytes=peak,
        representative_root180_validation=record(DEV/'ROOT180_VALIDATION.json'),UTC=now())
    # Old validation references describe discarded B2 optimizations and do not
    # belong in this independent release's execution contract.
    for key in ('minimal_current_exact_c3a_validation','performance_equivalence',
                'user_latest_no_proof_restart_May01_and_May02'):
        manifest.pop(key,None)
    atomic(ROOT/'CAMPAIGN_MANIFEST.json',manifest)
    from v42_svr11.controller import initial
    ledger=initial();prior=read(OLD/'CAMPAIGN_LEDGER.json')
    for day in DAYS:
        row=copy.deepcopy(prior['dates']['B0/'+day])
        if row['status']!='PASS':raise PermissionError('ROOT180_QUALIFIED_B0_REQUIRED')
        row['continued_from_qualified_B0_manifest']=record(OLD/'CAMPAIGN_MANIFEST.json')
        ledger['dates']['B0/'+day]=row
    ledger.update(policy='B2',source_SHA=source,UTC=now())
    atomic(ROOT/'CAMPAIGN_LEDGER.json',ledger)
    from svr11_monitor_ui import ui_files
    atomic(ROOT/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),Native_calls=0,UTC=now()))
    from v42_svr11.authority import verify
    verify(ROOT/'CAMPAIGN_MANIFEST.json')
    atomic(ROOT/'EXACT_ROOT180_SUCCESSOR_READY.json',dict(PASS=True,source_SHA=source,
        fresh_B2_from_May01=True,old_optimization_results_reused=0,dispatch_started=False,UTC=now()))
    print(dict(root=str(ROOT),source_SHA=source,worker_reservation_bytes=reserve,ready=True))


if __name__=='__main__':release()
