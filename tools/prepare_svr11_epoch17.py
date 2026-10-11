"""Release a new immutable campaign only after one completed Root180 probe."""
from pathlib import Path
import copy, math, subprocess, sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import atomic,read,record,digest,now,sha
from v42_common_campaign.authority import source_files
from v42_common_mess import VERSION
from v42_svr11 import DAYS
from v42_svr11.milp_release import _validate_root180
OLD=Path(r'D:\v42_svr11_may_20261011_16')
ROOT=Path(r'D:\v42_svr11_may_20261011_17')
DEV=Path(r'D:\v42_root180_development_20261011')
GIB=1024**3


def qualified_b0_ledger(state,manifest,science_receipt):
    """Rebind qualified B0 validation, preserving its original execution."""
    from v42_svr11.controller import initial
    from verify_svr11_handoff37 import audit_date,require
    from reuse_svr11_completed import verify_reuse
    from prepare_svr11_epoch15 import preserved_science
    ledger=initial();previous=read(OLD/'CAMPAIGN_LEDGER.json')
    checked_receipts={};checked_origins={};audits=[]
    def checked(receipt):
        path=receipt['path']
        if path not in checked_receipts:checked_receipts[path]=record(path)
        require(checked_receipts[path]==receipt,'ROOT180_B0_PROTECTED_BYTE_DRIFT:'+path)
        return receipt
    def origin(root):
        root=Path(root).resolve();path=root/'CAMPAIGN_MANIFEST.json'
        if str(root) not in checked_origins:
            receipt=record(path);value=read(path)
            require(Path(value['root']).resolve()==root and
                value['execution_SHA']==digest(value['execution_sources']),
                'ROOT180_B0_ORIGIN_SOURCE_DIGEST')
            for name,expected in value['execution_sources'].items():
                require(sha(Path(value['code_root'])/name)==expected,
                    'ROOT180_B0_ORIGIN_SOURCE_DRIFT:'+name)
            preserved=preserved_science(value,state['sources'])
            checked_origins[str(root)]=(value,receipt,preserved)
        return checked_origins[str(root)]
    def input_axis(value,day):
        excluded={'OPERATIONS_TEMPLATE_B1.json','OPERATIONS_TEMPLATE_B2.json',
            'NATIVE_INPUT_TEMPLATE_B1.json','NATIVE_INPUT_TEMPLATE_B2.json'}
        axis={}
        for receipt in value['input_receipts'][day]:
            if Path(receipt['path']).name in excluded:continue
            checked(receipt);name=Path(receipt['path']).name
            require(name not in axis,'ROOT180_B0_DUPLICATE_RAW_AXIS')
            axis[name]=(receipt['sha256'],receipt['bytes'])
        require({'ACTUAL_INPUT_BUNDLE.json','PLANNING_INPUT_BUNDLE.json',
            'POWER_AUTHORITY.json','WINDOWS.json'}<=set(axis),'ROOT180_B0_RAW_AXIS_INCOMPLETE')
        return axis
    checked(science_receipt)
    predecessor_receipt=record(OLD/'CAMPAIGN_MANIFEST.json');checked(predecessor_receipt)
    for day in DAYS:
        row=copy.deepcopy(previous['dates']['B0/'+day])
        require(row['status']=='PASS' and row['arm']=='B0' and row['day']==day,
            'ROOT180_QUALIFIED_B0_REQUIRED')
        require(row.get('reused') is True,'ROOT180_B0_QUALIFIED_REUSE_PROOF_REQUIRED')
        inherited_receipt=checked(row['reuse_proof']);inherited=read(inherited_receipt['path'])
        proof_root=Path(inherited_receipt['path']).resolve().parent.parent
        bound,origin_receipt,preserved=origin(proof_root)
        # Source16 inherited Source15's receipt. Validate it under its actual
        # owning manifest before creating an independently owned Source17 one.
        validation=verify_reuse(proof_root,bound,row)
        for receipt in validation['evidence']:checked(receipt)
        result_receipt=checked(record(row['result']));result=read(row['result'])
        require(result_receipt['sha256']==row['result_SHA'] and result['PASS'] is True
            and result['status']=='PASS' and result['source_SHA']==inherited['execution_source_SHA']
            and result['identity']['arm']=='B0' and result['identity']['day']==day
            and result.get('Native_optimizer_calls')==0 and result.get('Native_Runtime')==0,
            'ROOT180_B0_ORIGINAL_EXECUTION_IDENTITY')
        require(validation['PASS'] is True and validation['arm']=='B0' and validation['day']==day
            and validation['result_SHA']==row['result_SHA']
            and validation.get('Native_Runtime')==0
            and validation['namespaces']['ACTUAL']['slots']==96
            and validation['namespaces']['ACTUAL']['Full_AC_Physical_PASS'] is True,
            'ROOT180_B0_INDEPENDENT_96_SLOT_PASS_REQUIRED')
        physical=[]
        for value in (bound,state['old'],manifest):
            for key in ('hardware','scenario','thermal'):checked(value[key]);physical.append(value[key])
            hardware=read(value['hardware']['path'])
            require(hardware['equipment_SHA']==inherited['equipment_SHA']
                and hardware['SVR_count']==11,'ROOT180_B0_EQUIPMENT_DIFFERENT')
            require(value['scenario']['sha256']==bound['scenario']['sha256']
                and value['thermal']['sha256']==bound['thermal']['sha256']
                and value.get('postoptimization_DayAhead_Fresh_AC')==bound.get('postoptimization_DayAhead_Fresh_AC')
                and value.get('original_transformer_current_authority')==bound.get('original_transformer_current_authority'),
                'ROOT180_B0_PHYSICAL_CONTRACT_DIFFERENT')
        axes=[input_axis(value,day) for value in (bound,state['old'],manifest)]
        require(axes[0]==axes[1]==axes[2],'ROOT180_B0_RAW_INPUT_DIFFERENT')
        changes=sorted(name for name in set(bound['execution_sources'])|set(state['sources'])
            if bound['execution_sources'].get(name)!=state['sources'].get(name))
        evidence=list(validation['evidence'])+[origin_receipt,predecessor_receipt,science_receipt,
            record(ROOT/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json'),result_receipt]+physical
        evidence.extend(receipt for value in (bound,state['old'],manifest)
            for receipt in value['input_receipts'][day]
            if Path(receipt['path']).name not in {'OPERATIONS_TEMPLATE_B1.json',
                'OPERATIONS_TEMPLATE_B2.json','NATIVE_INPUT_TEMPLATE_B1.json','NATIVE_INPUT_TEMPLATE_B2.json'})
        evidence=list({receipt['path']:receipt for receipt in evidence}.values())
        for receipt in evidence:checked(receipt)
        proof=dict(schema='SVR11_COMPLETED_RESULT_REUSE_V1',PASS=True,arm='B0',day=day,
            origin_root=str(OLD),inherited_reuse_proof=inherited_receipt,
            execution_source_SHA=inherited['execution_source_SHA'],validation_source_SHA=manifest['execution_SHA'],
            equipment_SHA=inherited['equipment_SHA'],original_result=row['result'],
            original_result_SHA=row['result_SHA'],original_result_bytes=result_receipt['bytes'],
            changed_sources_reviewed=changes,B0_physical_science_bitwise_unchanged=True,
            protected_source_files=preserved['files'],raw_input_axis=axes[2],
            validation=validation,evidence=evidence,validator=record(Path(__file__)),Native_calls=0,AC_calls=0,
            original_result_bytes_changed=False,original_execution_relabelled=False,UTC=now())
        path=ROOT/'reuse'/(day+'_B0.json');atomic(path,proof)
        row.update(reused=True,reuse_proof=record(path),execution_source_SHA=proof['execution_source_SHA'],
            validation_source_SHA=manifest['execution_SHA'],retry_pending=False,
            continued_from_qualified_B0_manifest=predecessor_receipt)
        ledger['dates']['B0/'+day]=row
        audit=audit_date(ROOT,manifest,row)
        require(audit['PASS'] is True and audit['source_SHA']==manifest['execution_SHA']
            and audit['execution_source_SHA']==proof['execution_source_SHA'],
            'ROOT180_B0_CURRENT_HANDOFF_AUDIT_REQUIRED')
        audits.append(dict(day=day,PASS=True,proof=record(path),original_result=result_receipt,
            execution_source_SHA=proof['execution_source_SHA'],validation_source_SHA=manifest['execution_SHA']))
    # initial() leaves B2/B1/B3 unexecuted with empty attempt histories.
    require(all(row['status']=='NOT_EXECUTED' and not row['attempts'] for row in ledger['dates'].values()
        if row['arm']!='B0'),'ROOT180_POLICY_NATIVE_ZERO_REQUIRED')
    ledger.update(policy='B2',source_SHA=manifest['execution_SHA'],UTC=now())
    atomic(ROOT/'B0_CURRENT_EPOCH_REUSE_VALIDATION.json',dict(PASS=True,source_SHA=manifest['execution_SHA'],
        verified_PASS=len(audits),total=31,dates=audits,original_result_bytes_changed=False,
        original_execution_relabelled=False,Native_calls=0,AC_calls=0,UTC=now()))
    return ledger


def release():
    sources=source_files();source=digest(sources);old=read(OLD/'CAMPAIGN_MANIFEST.json')
    from root180_completion import require_completed
    require_completed(read(DEV/'ROOT180_VALIDATION.json'))
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
        unchanged_physical_and_A_science=record(ROOT/'UNCHANGED_PHYSICAL_AND_A_SCIENCE.json'),
        memory_reservation_basis='Measured Source17 construction and Root180 RSS/private commit peak plus 1 GiB, rounded up to GiB with 7 GiB minimum; actual RAM and commit delay new admission only',
        representative_root180_validation=record(DEV/'ROOT180_VALIDATION.json'),UTC=now())
    # Old validation references describe discarded B2 optimizations and do not
    # belong in this independent release's execution contract.
    for key in ('minimal_current_exact_c3a_validation','performance_equivalence',
                'user_latest_no_proof_restart_May01_and_May02'):
        manifest.pop(key,None)
    # Complete independent B0 reuse qualification before immutable publication.
    ledger=qualified_b0_ledger(state,manifest,record(ROOT/'UNCHANGED_PHYSICAL_AND_A_SCIENCE.json'))
    from v42_svr11.authority import verify
    candidate=ROOT/'RELEASE_VALIDATION_CANDIDATE.json';atomic(candidate,manifest);verify(candidate)
    atomic(ROOT/'CAMPAIGN_LEDGER.json',ledger)
    atomic(ROOT/'CAMPAIGN_MANIFEST.json',manifest)
    from svr11_monitor_ui import ui_files
    atomic(ROOT/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),Native_calls=0,UTC=now()))
    from v42_svr11.authority import verify
    verify(ROOT/'CAMPAIGN_MANIFEST.json')
    atomic(ROOT/'EXACT_ROOT180_SUCCESSOR_READY.json',dict(PASS=True,source_SHA=source,
        fresh_B2_from_May01=True,old_optimization_results_reused=0,dispatch_started=False,
        B0_qualified_preserved=31,B0_current_reuse_validation=record(ROOT/'B0_CURRENT_EPOCH_REUSE_VALIDATION.json'),UTC=now()))
    print(dict(root=str(ROOT),source_SHA=source,worker_reservation_bytes=reserve,ready=True))


if __name__=='__main__':release()
