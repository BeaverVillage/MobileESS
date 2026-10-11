"""Release fresh Exact C3A policy attempts after minimal current validation.

Immutable raw inputs, electrical coefficients and qualified B0 results retain
their original execution provenance. No predecessor B2/B1/B3 result is admitted.
This helper prepares receipts only; it neither stops workers nor starts dispatch.
"""
from pathlib import Path
import sys,copy,subprocess,math,shutil
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import read,record,atomic,sha,digest,now
from v42_common_campaign.authority import source_files,singleton
from v42_common_mess import VERSION
from v42_svr11 import DAYS
from v42_svr11.processes import live

OLD=Path(r'D:\v42_svr11_may_20261011_14')
ROOT=Path(r'D:\v42_svr11_may_20261011_15')
DEV=Path(r'D:\v42_svr11_c3a_development_20261011')
GIB=1024**3
VALIDATION=DEV/'EPOCH15_MINIMAL_VALIDATION.json'
# These paths are never changed by the optimizer-only release. Any difference
# requires separate scientific qualification rather than cache reuse.
UNCHANGED_PREFIXES=('v42_a_','v42_thermal/','v42_voltage_control/')
UNCHANGED_FILES={'v42_svr11/model.py','v42_svr11/physics.py','v42_svr11/hardware.py',
    'v42_svr11/equipment.py','v42_svr11/scenario.py','v42_svr11/ldc_interval.py',
    'v42_svr11/b0.py','v42_svr11/b0_direct.py','v42_svr11/operations.py',
    'v42_svr11/freeze.py','v42_svr11/initial_context.py'}


def preserved_science(old,sources):
    original=old['execution_sources']
    protected={name for name in set(original)|set(sources)
        if name in UNCHANGED_FILES or name.startswith(UNCHANGED_PREFIXES)}
    drift=sorted(name for name in protected if original.get(name)!=sources.get(name))
    if drift:raise PermissionError('EPOCH15_UNCHANGED_PHYSICAL_OR_A_SCIENCE_DRIFT:'+repr(drift))
    return dict(PASS=True,files={name:sources[name] for name in sorted(protected)},
        electrical_model=record(SOURCE/'v42_svr11/model.py'),Native_calls=0)


def readiness():
    old=read(OLD/'CAMPAIGN_MANIFEST.json');sources=source_files()
    for key,value in old['execution_sources'].items():
        if sha(Path(old['code_root'])/key)!=value:raise PermissionError('EPOCH14_IMMUTABLE_SCIENCE_DRIFT:'+key)
    changes=sorted(k for k in set(sources)|set(old['execution_sources'])
        if sources.get(k)!=old['execution_sources'].get(k))
    preserved=preserved_science(old,sources)
    ready=read(OLD/'FULL_MILP_SUCCESSOR_READY.json')
    if not (ready['PASS'] and ready['source_SHA']==old['execution_SHA']
            and ready['Forecast31_PASS'] and ready['B0_qualified_preserved']==31):
        raise PermissionError('EPOCH14_QUALIFIED_FORECAST_AND_B0_REQUIRED')
    qpath=OLD/'DISPATCH_QUIESCENCE_FOR_PLANNING_MODEL_REPAIR.json'
    if not qpath.is_file():return dict(ready=False,reason='WAITING_SAFE_PREDECESSOR_QUIESCENCE')
    q=read(qpath)
    if not (q['new_dispatch_quiesced'] and q['source_SHA']==old['execution_SHA']
            and q.get('worker_terminated',q.get('healthy_workers_terminated'))==0):
        raise PermissionError('EPOCH14_SAFE_QUIESCENCE_REQUIRED')
    if not VALIDATION.is_file():return dict(ready=False,reason='WAITING_MINIMAL_CURRENT_C3A_VALIDATION')
    validation=read(VALIDATION)
    if not validation.get('PASS') or validation.get('source_SHA')!=digest(sources):
        raise PermissionError('EPOCH15_CURRENT_VALIDATION_SOURCE_DRIFT')
    return dict(ready=True,old=old,sources=sources,source_SHA=digest(sources),changes=changes,
        preserved_science=preserved,minimal_validation=record(VALIDATION),dispatch_quiescence=record(qpath))


def validation_contract(state):
    historical=record(OLD/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json')
    atomic(ROOT/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json',dict(
        schema='SVR11_EXACT_C3A_MINIMAL_RELEASE_V1',source_SHA=state['source_SHA'],algorithm_version=VERSION,
        A1_A2_algorithms_changed=False,M_native_limit_seconds=1800,
        minimal_current_validation=state['minimal_validation'],
        historical_full_milp_validation=dict(contract=historical,
            execution_source_SHA=state['old']['execution_SHA'],
            purpose='Historical measured full-MILP continuation/runtime evidence only',
            new_source_equivalence_claim=False,old_results_promoted=0),
        development_results_promoted=0,UTC=now()))
    from v42_svr11.milp_release import validate
    receipt=validate(ROOT,state['sources'])
    validation=read(VALIDATION);smoke=read(validation['runtime_smoke']['path'])
    memory=smoke['memory'];peak=max(memory['peak_RSS_bytes'],memory['peak_private_commit_bytes'])
    # Production also builds/replays exact reduction certificates before the
    # native clone. Include the measured fresh construction peak when that
    # process retained more memory than the recovered short smoke process.
    equivalent=read(validation['original_equivalence_validation']['path'])
    construction_memory=equivalent.get('memory',{})
    peak=max(peak,construction_memory.get('peak_RSS_bytes',0),
        construction_memory.get('peak_private_commit_bytes',0))
    # Exact C3A measured peak plus at least 1 GiB growth, conservatively bounded
    # below by the existing 7 GiB worker reservation. Admission delays new jobs.
    reservation=max(7*GIB,math.ceil((peak+GIB)/GIB)*GIB)
    return receipt,reservation,peak


def utilities():
    # Reuse reviewed byte-copy/provenance utilities in this new checkout only.
    # The immutable predecessor source is never imported or edited here.
    import prepare_svr11_epoch14 as helper
    helper.OLD=OLD;helper.ROOT=ROOT;helper.DEV=DEV
    return helper


def forecast_contract(state,receipts,helper):
    """Verify immutable bytes once, retaining the prior scientific qualification."""
    old=state['old'];days={};links=[];certificates={};seen={}
    def checked(receipt):
        key=receipt['path']
        if key not in seen:seen[key]=record(key)
        if seen[key]!=receipt:raise PermissionError('EPOCH14_FORECAST_REUSE_BYTES_DRIFT:'+key)
        return receipt
    oldhardware=read(old['hardware']['path']);newhardware=read(ROOT/'hardware/HARDWARE.json')
    if oldhardware['equipment_SHA']!=newhardware['equipment_SHA']:
        raise PermissionError('EPOCH15_FORECAST_REUSE_EQUIPMENT_DIFFERENT')
    origin_contract=checked(old['model_checkpoint_reuse_contract'])
    previous=read(origin_contract['path'])
    protected_npz={row['linked']['path']:row['linked'] for row in previous['coefficient_NTFS_hardlinks']}
    for day in DAYS:
        excluded={'OPERATIONS_TEMPLATE_B1.json','OPERATIONS_TEMPLATE_B2.json'}
        axes=[{Path(r['path']).name:(r['sha256'],r['bytes']) for r in refs
            if Path(r['path']).name not in excluded}
            for refs in (old['input_receipts'][day],receipts[day])]
        if axes[0]!=axes[1]:raise PermissionError('EPOCH15_FORECAST_INPUT_DIFFERENT:'+day)
        origin=OLD/'models'/day;dest=ROOT/'models'/day
        certificate=checked(record(origin/'ELECTRICAL_CERTIFICATE.json'));v=read(certificate['path'])
        if not (v['day']==day and v['source_SHA']==old['execution_SHA']
                and v['Actual_inputs_read']==v['tap_optimization_variables']==0
                and v['equipment_SHA']==oldhardware['equipment_SHA']
                and v['scenario_SHA']==read(old['scenario']['path'])['scenario_SHA']):
            raise PermissionError('EPOCH14_QUALIFIED_FORECAST_IDENTITY_DRIFT')
        coefficient=v['outputs']['planning_coefficients']
        if protected_npz.get(coefficient['path'])!=coefficient:
            raise PermissionError('EPOCH14_FORECAST_SEALED_COEFFICIENT_RECEIPT_DRIFT')
        checked(coefficient);slots={}
        for t in range(96):
            p=origin/f'SLOT_{t:02d}.json';slot=read(p)
            if slot['day']!=day or slot['source_SHA']!=old['execution_SHA']:
                raise PermissionError('EPOCH14_FORECAST_SLOT_IDENTITY_DRIFT')
            if protected_npz.get(slot['data']['path'])!=slot['data']:
                raise PermissionError('EPOCH14_FORECAST_SEALED_SLOT_RECEIPT_DRIFT')
            checked(slot['data'])
            slots[str(t)]=dict(original_checkpoint=record(p),original_data=slot['data'],
                generation_source_SHA=slot.get('generation_source_SHA',slot['source_SHA']))
        for p in sorted(origin.rglob('*')):
            if not p.is_file() or p.suffix=='.lock':continue
            target=dest/p.relative_to(origin)
            if p.suffix=='.npz':links.append(helper.link_or_check(p,target))
            else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        days[day]=dict(slots=slots,certificate=certificate,
            forecast_anchor={name:record(origin/'FORECAST_ANCHOR'/name)
                for name in ('B0_NEW_PLANNING_GENERATION.json','PLANNING_PHYSICAL.npz')})
        certificates[day]=certificate
    origin_check=ROOT/'FORECAST_ORIGIN_REVALIDATION.json'
    atomic(origin_check,dict(PASS=True,source_SHA=old['execution_SHA'],evidence=certificates,
        byte_and_provenance_revalidation_only=True,prior_numerical_qualification_retained=True,
        numerical_all31_comparison_repeated=False,origin_sealed_checkpoint_reuse_contract=origin_contract,
        Native_optimizer_calls=0,Actual_calls=0,UTC=now()))
    contract=dict(PASS=True,generation_source_SHA=old['execution_SHA'],
        generation_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),validation_source_SHA=state['source_SHA'],days=days,
        mathematical_electrical_model_changed=False,Forecast_generation_sources_bitwise_unchanged=True,
        Native_policy_results_reused=0,Actual_inputs_read_by_model=0,
        Planning_tap_or_queue_transferred_to_Actual=False,reused_complete_slots=2976,
        previous_policy_optimization_reuse=0,coefficient_NTFS_hardlinks=links,
        source_changes_reviewed=state['changes'],origin_independent_revalidation=record(origin_check),UTC=now())
    path=ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json';atomic(path,contract);ref=record(path)
    for day in DAYS:
        dest=ROOT/'models'/day;v=read(dest/'ELECTRICAL_CERTIFICATE.json');coefficient=record(dest/'COEFFICIENTS.npz')
        v.update(source_SHA=state['source_SHA'],generation_source_SHA=v.get('generation_source_SHA',old['execution_SHA']),
            coefficient_certificate_origin_source_SHA=old['execution_SHA'],
            physical_slot_generation_SHA_by_slot={t:s['generation_source_SHA'] for t,s in days[day]['slots'].items()},
            model_reused=True,regenerated_in_current_execution_epoch=False,validation_source_SHA=state['source_SHA'],
            original_generation_certificate=days[day]['certificate'],revalidation_contract=ref,
            reused_forecast_slot_provenance=ref,output=coefficient)
        v['outputs']={k:coefficient for k in v['outputs']};atomic(dest/'ELECTRICAL_CERTIFICATE.json',v)
        for t in range(96):
            p=dest/f'SLOT_{t:02d}.json';v=read(p)
            v.update(source_SHA=state['source_SHA'],generation_source_SHA=days[day]['slots'][str(t)]['generation_source_SHA'],
                reused=True,revalidation_contract=ref,data=record(dest/f'SLOT_{t:02d}.npz'))
            atomic(p,v)
    return ref


def release():
    state=readiness()
    if not state['ready']:print(state);return False
    ROOT.mkdir(exist_ok=True)
    with singleton(ROOT/'EXACT_C3A_RELEASE.lock'):
        if (ROOT/'EXACT_C3A_SUCCESSOR_READY.json').exists():
            from v42_svr11.authority import verify
            verify(ROOT/'CAMPAIGN_MANIFEST.json');return True
        if (ROOT/'CAMPAIGN_MANIFEST.json').exists():
            raise PermissionError('EPOCH15_IMMUTABLE_MANIFEST_ALREADY_RELEASED')
        for name in ('SUPERVISOR_PROCESS.json','MONITOR_PROCESS.json'):
            path=ROOT/name
            if path.exists() and live(read(path)):raise PermissionError('EPOCH15_CANNOT_REWRITE_ACTIVE_CAMPAIGN')
        full,reservation,peak=validation_contract(state);helper=utilities()
        receipts=helper.raw_and_hardware(state);forecast=forecast_contract(state,receipts,helper)
        predecessor=read(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json')
        predecessor.update(dispatch_quiescence=state['dispatch_quiescence'],
            scientific_model_change=False,physical_equipment_change=False,
            optimizer_reformulation_change=True,qualified_completed_dates_reused=True,
            qualified_completed_arms_reused=['B0'],healthy_workers_terminated=0,
            reason='Current-matrix proven Exact C3A and gap recovery; B2/B1/B3 fresh Native0; qualified same-equipment B0 and unchanged Forecast coefficients preserve original provenance')
        atomic(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json',predecessor)
        atomic(ROOT/'UNCHANGED_PHYSICAL_AND_A_SCIENCE.json',dict(state['preserved_science'],
            origin_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),source_SHA=state['source_SHA'],UTC=now()))
        from v42_svr11.model_release import validate
        m=copy.deepcopy(state['old']);commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
        memory=copy.deepcopy(m['B3_memory_admission']);memory['worker_reservation_bytes'].update(M1=reservation,M2=reservation)
        m.update(root=str(ROOT),code_root=str(SOURCE),run_id='SVR11_FINAL_MAY_'+ROOT.name,
            execution_sources=state['sources'],execution_SHA=state['source_SHA'],source_commit=commit,
            algorithm_version=VERSION,scientific_model_validation=validate(ROOT,state['sources']),full_milp_validation=full,
            hardware=record(ROOT/'hardware/HARDWARE.json'),scenario=record(ROOT/'hardware/SCENARIO.json'),
            thermal=record(ROOT/'hardware/THERMAL.json'),input_receipts=receipts,
            implementation=dict(version=m['implementation']['version'],sources=state['sources']),
            builder_original_sources=state['sources'],predecessor_drain_contract=record(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json'),
            model_checkpoint_reuse_contract=forecast,B2_memory_admission=memory,B3_memory_admission=memory,
            worker_counts=dict(B0=m['worker_counts']['B0'],B2=2,B1=1,B3=2),
            B3_stagewise_batch=True,B3_stage_worker_counts=dict(M1=2,A2=1,M2=2,ACTUAL=1),
            M_target_global_gap=.03,native_M_limit_seconds=1800,A1_A2_algorithms_changed=False,
            memory_wait_applies_to_new_admission_only=True,healthy_workers_may_be_terminated_for_memory=False,
            Forecast_precomputation_wall_external_to_policy_dates=True,
            full_MILP_measured_peak_bytes=peak,optimization_results_reused=0,B2_all31_fresh_Native_zero=True,
            B1_all31_fresh_Native_zero=True,B3_all31_fresh_Native_zero=True,
            B0_qualified_results_preserved=31,fresh_all_124_physical_results_required=False,
            fresh_B2_B1_B3_physical_results_required=93,
            B3_A1_reuse_requires_same_epoch_original_problem_and_input_equivalence=True,
            same_Forecast_31_shared_by_B1_B2_B3=True,qualified_same_scientific_release_reuse=False,
            minimal_current_exact_c3a_validation=state['minimal_validation'],
            unchanged_physical_and_A_science=record(ROOT/'UNCHANGED_PHYSICAL_AND_A_SCIENCE.json'),
            user_latest_20261011_B2_from_May01=True,UTC=now())
        atomic(ROOT/'CAMPAIGN_MANIFEST.json',m)
        from v42_svr11.authority import verify
        verify(ROOT/'CAMPAIGN_MANIFEST.json');helper.b0_and_empty_policies(state,m)
        from svr11_model_precompute import check_model
        # One representative numerical binding; all31 immutable cache bytes
        # and provenance were checked above, with no model regeneration.
        check_model(ROOT,m,DAYS[0])
        from svr11_monitor_ui import ui_files
        atomic(ROOT/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),
            scientific_source_unchanged=True,Native_calls=0,UTC=now()))
        atomic(ROOT/'EXACT_C3A_SUCCESSOR_READY.json',dict(PASS=True,root=str(ROOT),source_SHA=state['source_SHA'],
            manifest=record(ROOT/'CAMPAIGN_MANIFEST.json'),minimal_validation=state['minimal_validation'],
            full_MILP_validation=full,Forecast31_PASS=True,B0_qualified_preserved=31,
            B2_fresh_zero_start=True,B1_B3_fresh_zero_start=True,B2_workers=2,B3_M1_M2_workers=2,
            healthy_workers_terminated=0,dispatch_started=False,UTC=now()))
        print('EXACT_C3A_SUCCESSOR_READY',state['source_SHA'],reservation)
        return True


if __name__=='__main__':
    if sys.argv[1]=='readiness':print({k:v for k,v in readiness().items() if k not in ('old','sources','preserved_science')})
    elif sys.argv[1]=='release':release()
    else:raise ValueError('UNKNOWN_RELEASE_MODE')
