"""Release the sealed full-MILP successor only after real validation and Forecast31.

Only Forecast coefficients and already independently qualified B0 results carry
forward. Every B2/B1/B3 policy solve starts in an empty new attempt namespace.
"""
from pathlib import Path
import sys, copy, shutil, subprocess, math
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import read,record,atomic,sha,digest,now
from v42_common_campaign.authority import source_files,singleton
from v42_common_mess import VERSION
from v42_svr11 import DAYS
from v42_svr11.processes import live
OLD=Path(r'D:\v42_svr11_may_20261011_13')
ROOT=Path(r'D:\v42_svr11_may_20261011_14')
DEV=Path(r'D:\v42_svr11_full_milp_development_20261011')
GIB=1024**3
REVIEWED={'v42_b2_build_authority_v13/builder.py','v42_b3_joint/policy.py',
    'v42_common_campaign/__init__.py','v42_common_campaign/b2.py',
    'v42_common_mess/__init__.py','v42_common_mess/engine.py','v42_common_mess/model.py',
    'v42_pr134_b1/native.py','v42_svr11/authority.py','v42_svr11/controller.py','v42_svr11/milp_release.py'}


def readiness():
    old=read(OLD/'CAMPAIGN_MANIFEST.json');seal=read(DEV/'SOURCE_SEAL.json')
    sources=source_files()
    if sources!=seal['sources'] or digest(sources)!=seal['source_SHA']:
        raise PermissionError('EPOCH14_SEALED_SCIENCE_DRIFT')
    for key,value in old['execution_sources'].items():
        if sha(Path(old['code_root'])/key)!=value:raise PermissionError('EPOCH13_SCIENCE_DRIFT:'+key)
    changes={k for k in set(sources)|set(old['execution_sources'])
        if sources.get(k)!=old['execution_sources'].get(k)}
    if changes!=REVIEWED:raise PermissionError('EPOCH14_UNREVIEWED_CHANGE:'+repr(changes))
    request=read(OLD/'MODEL_PRECOMPUTE_REQUEST.json')
    if not request.get('campaign_resume_held_for_V2_schema_binding_repair'):
        raise PermissionError('EPOCH13_POLICY_HOLD_MUST_REMAIN')
    ledger=read(OLD/'MODEL_PRECOMPUTE_LEDGER.json')
    if any(ledger['dates'][d]['status']!='PASS' for d in DAYS):
        return dict(ready=False,reason='WAITING_FORECAST31',counts=ledger['counts'])
    if any(live(p) for p in ledger.get('active_workers',[])):
        return dict(ready=False,reason='WAITING_MODEL_WORKERS_NATURAL_EXIT')
    process=OLD/'MODEL_PRECOMPUTE_PROCESS.json';ready=OLD/'MODEL_PRECOMPUTE_READY.json'
    if not ready.exists() or (process.exists() and live(read(process))):
        return dict(ready=False,reason='WAITING_MODEL_COORDINATOR_FINAL_AUDIT_AND_EXIT')
    completed=read(ready)
    if not (completed['PASS'] and completed['source_SHA']==old['execution_SHA']
            and completed['successful_models']==31 and completed['failed_models']==0
            and completed['Native_optimizer_calls']==completed['Actual_calls']==0):
        raise PermissionError('EPOCH13_FINAL_MODEL_READY_PROOF_REQUIRED')
    results={}
    for day in ('2025-05-16','2025-05-18'):
        p=DEV/'dates/B2'/day/'attempts/phase2_01/RESULT.json'
        if not p.exists():return dict(ready=False,reason='WAITING_REAL_FULL_MILP_VALIDATION',day=day)
        results[day]=record(p)
    return dict(ready=True,sources=sources,source_SHA=digest(sources),changes=sorted(changes),
        real_validation=results,old=old)


def link_or_check(origin,target):
    origin=Path(origin);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if sha(origin)!=sha(target):raise PermissionError('EPOCH14_IMMUTABLE_COPY_DRIFT:'+str(target))
    else:target.hardlink_to(origin)
    return dict(original=record(origin),linked=record(target))


def validation_contract(state):
    normalized={}
    for day,receipt in state['real_validation'].items():
        if record(receipt['path'])!=receipt:raise PermissionError('REAL_VALIDATION_ORIGIN_RESULT_DRIFT')
        value=copy.deepcopy(read(receipt['path']))
        if value.get('PASS') is not True:
            raise PermissionError('SVR11_GLOBAL_FULL_MILP_REAL_VALIDATION_INCOMPLETE:'+day)
        for row in value['Phase2_rows']:
            thin=row['original_model_identity'];full=record(thin['path'])
            if (set(thin) not in ({'path','sha256'},{'path','sha256','bytes'})
                    or any(full.get(k)!=v for k,v in thin.items())):
                raise PermissionError('REAL_VALIDATION_IDENTITY_SHA_OR_SCHEMA_DRIFT')
            row['original_model_identity']=full
        value['receipt_schema_normalization']=dict(original_result=receipt,
            changed_fields=['Phase2_rows[*].original_model_identity.bytes'],
            original_sha_matches=True,Native_calls=0,Runtime_and_UB_unchanged=True,
            production_results_promoted=0,normalizer=record(__file__))
        path=DEV/'normalized_receipts'/(day+'.json');atomic(path,value);normalized[day]=record(path)
    result=dict(source_SHA=state['source_SHA'],algorithm_version=VERSION,
        A1_A2_algorithms_changed=False,M_native_limit_seconds=1800,
        real_validation=normalized,original_real_validation=state['real_validation'],
        development_results_promoted=0,UTC=now())
    atomic(ROOT/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json',result)
    from v42_svr11.milp_release import validate
    receipt=validate(ROOT,state['sources'])
    peaks=[]
    for r in normalized.values():
        v=read(r['path']);memory=v['memory']
        peaks.extend([memory['peak_RSS_bytes'],memory['peak_private_commit_bytes']])
        for row in v['Phase2_rows']:
            identity=read(row['original_model_identity']['path'])
            peaks.extend([identity['memory_after']['RSS_bytes'],identity['memory_after']['private_bytes']])
    reservation=max(7*GIB,math.ceil((max(peaks)+GIB)/GIB)*GIB)
    return receipt,reservation,max(peaks)


def raw_and_hardware(state):
    old=state['old'];links=[];receipts={}
    (ROOT/'hardware').mkdir(parents=True,exist_ok=True)
    for p in (OLD/'hardware').iterdir():
        if p.is_file():shutil.copyfile(p,ROOT/'hardware'/p.name)
    for day,refs in old['input_receipts'].items():
        dest=ROOT/'raw'/day;dest.mkdir(parents=True,exist_ok=True)
        for r in refs:
            if record(r['path'])!=r:raise PermissionError('EPOCH13_RAW_RECEIPT_DRIFT')
            p=dest/Path(r['path']).name
            if p.name=='OPERATIONS_TEMPLATE_B2.json':
                value=read(r['path']);value['current_day_folder']=str(dest);atomic(p,value)
            else:links.append(link_or_check(r['path'],p))
        receipts[day]=[record(p) for p in sorted(dest.iterdir()) if p.is_file()]
    atomic(ROOT/'RAW_INPUT_RECEIPTS.json',receipts)
    atomic(ROOT/'RAW_INPUT_ORIGINS.json',old['origins'])
    atomic(ROOT/'SELECTIVE_REUSE_LEDGER.json',dict(PASS=True,raw_NTFS_hardlinks=links,
        mutable_files_hardlinked=0,old_policy_solution_reuse=0,original_files_deleted=0,UTC=now()))
    hp=ROOT/'hardware/HARDWARE.json';hardware=read(hp)
    atomic(ROOT/'hardware/PROVISIONAL_IMPLEMENTATION_FREEZE.json',hardware)
    hardware.update(source_SHA=state['source_SHA'],source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),source_release_UTC=now(),
        provisional_receipt=record(ROOT/'hardware/PROVISIONAL_IMPLEMENTATION_FREEZE.json'))
    atomic(hp,hardware)
    validation=read(OLD/'MODEL_VALIDATION_RELEASE_CONTRACT.json')
    validation.update(source_SHA=state['source_SHA'],model_code_SHA=state['sources']['v42_svr11/model.py'],
        optimizer_only_successor=True,Forecast_and_LDC_science_sources_bitwise_unchanged=True,
        previous_scientific_release=record(OLD/'MODEL_VALIDATION_RELEASE_CONTRACT.json'),UTC=now())
    atomic(ROOT/'MODEL_VALIDATION_RELEASE_CONTRACT.json',validation)
    # Predecessor policy dispatcher was never started. Its model workers must
    # be naturally finished; the earlier suspended Source12 remains untouched.
    atomic(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),source_SHA=old['execution_SHA'],
        monitor_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),scientific_model_change=True,
        physical_equipment_change=False,qualified_completed_dates_reused=True,
        reason='Original-equivalent unrestricted MILP continuation and strict V2 certificate dispatch; B2/B1/B3 all fresh Native0; only Forecast and B0 preserved',
        all_old_results_preserved=True,model_workers_naturally_finished=True,UTC=now()))
    atomic(ROOT/'B3_SOURCE_SEAL.json',dict(schema='B3_AUTONOMOUS_SOURCE_SEAL_V1',
        root=str(SOURCE),source_sha=state['source_SHA'],files=state['sources']))
    return receipts


def forecast_contract(state,receipts):
    old=state['old'];days={};links=[]
    # Each immutable authority must inspect its own source bytes. Importing
    # the Source14 guard while checking a Source13 manifest would correctly
    # reject it; recheck origin models in a separate Source13 read-only process.
    origin_check=ROOT/'FORECAST_ORIGIN_REVALIDATION.json'
    program="\n".join([
        'from pathlib import Path', 'import sys',
        'sys.path.insert(0,'+repr(str(Path(old['code_root'])/'tools'))+')',
        'from svr11_model_precompute import check_model',
        'from v42_pr134_b1.common import read,atomic,record,now',
        'from v42_svr11 import DAYS',
        'root=Path('+repr(str(OLD))+')',
        "m=read(root/'CAMPAIGN_MANIFEST.json')",
        'evidence={day:check_model(root,m,day) for day in DAYS}',
        'atomic('+repr(str(origin_check))+',dict(PASS=True,source_SHA=m["execution_SHA"],'
            'evidence=evidence,Native_optimizer_calls=0,Actual_calls=0,UTC=now()))'])
    result=subprocess.run([sys.executable,'-B','-X','utf8','-c',program],cwd=old['code_root'],
        text=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        atomic(ROOT/'FORECAST_ORIGIN_REVALIDATION_ERROR.json',dict(returncode=result.returncode,
            stdout=result.stdout,stderr=result.stderr,Native_calls=0,UTC=now()))
        raise PermissionError('EPOCH13_FORECAST_READ_ONLY_REVALIDATION_FAILED')
    validated=read(origin_check)
    if not validated['PASS'] or validated['source_SHA']!=old['execution_SHA']:
        raise PermissionError('EPOCH13_FORECAST_REVALIDATION_SOURCE_DRIFT')
    for day in DAYS:
        certificate=validated['evidence'][day]
        if record(certificate['path'])!=certificate:raise PermissionError('EPOCH13_FORECAST_CERTIFICATE_DRIFT')
        # Source14 changes no Forecast-generation or electrical-model byte.
        excluded={'OPERATIONS_TEMPLATE_B1.json','OPERATIONS_TEMPLATE_B2.json'}
        axes=[{Path(r['path']).name:(r['sha256'],r['bytes']) for r in refs
               if Path(r['path']).name not in excluded}
              for refs in (old['input_receipts'][day],receipts[day])]
        if axes[0]!=axes[1]:raise PermissionError('EPOCH14_FORECAST_INPUT_DIFFERENT:'+day)
        origin=OLD/'models'/day;dest=ROOT/'models'/day;slots={}
        for t in range(96):
            p=origin/f'SLOT_{t:02d}.json';v=read(p)
            if v['day']!=day or v['source_SHA']!=old['execution_SHA'] or record(v['data']['path'])!=v['data']:
                raise PermissionError('EPOCH13_MODEL_SLOT_DRIFT')
            slots[str(t)]=dict(original_checkpoint=record(p),original_data=v['data'],
                generation_source_SHA=v.get('generation_source_SHA',v['source_SHA']))
        for p in sorted(origin.rglob('*')):
            if not p.is_file():continue
            target=dest/p.relative_to(origin)
            if p.suffix=='.npz':links.append(link_or_check(p,target))
            else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        days[day]=dict(slots=slots,certificate=certificate,
            forecast_anchor={n:record(origin/'FORECAST_ANCHOR'/n)
                for n in ('B0_NEW_PLANNING_GENERATION.json','PLANNING_PHYSICAL.npz')})
    contract=dict(PASS=True,generation_source_SHA=old['execution_SHA'],generation_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),
        validation_source_SHA=state['source_SHA'],days=days,mathematical_electrical_model_changed=False,
        Forecast_generation_sources_bitwise_unchanged=True,Native_policy_results_reused=0,
        Actual_inputs_read_by_model=0,Planning_tap_or_queue_transferred_to_Actual=False,
        reused_complete_slots=2976,previous_policy_optimization_reuse=0,coefficient_NTFS_hardlinks=links,
        source_changes_reviewed=state['changes'],UTC=now())
    contract['origin_independent_revalidation']=record(origin_check)
    p=ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json';atomic(p,contract);ref=record(p)
    for day in DAYS:
        dest=ROOT/'models'/day;v=read(dest/'ELECTRICAL_CERTIFICATE.json')
        coefficients=record(dest/'COEFFICIENTS.npz')
        v.update(source_SHA=state['source_SHA'],generation_source_SHA=v.get('generation_source_SHA',old['execution_SHA']),
            coefficient_certificate_origin_source_SHA=old['execution_SHA'],
            physical_slot_generation_SHA_by_slot={t:s['generation_source_SHA'] for t,s in days[day]['slots'].items()},
            model_reused=True,regenerated_in_current_execution_epoch=False,
            validation_source_SHA=state['source_SHA'],
            original_generation_certificate=days[day]['certificate'],revalidation_contract=ref,
            reused_forecast_slot_provenance=ref,output=coefficients)
        v['outputs']={k:coefficients for k in v['outputs']}
        atomic(dest/'ELECTRICAL_CERTIFICATE.json',v)
        for t in range(96):
            p=dest/f'SLOT_{t:02d}.json';v=read(p)
            v.update(source_SHA=state['source_SHA'],generation_source_SHA=days[day]['slots'][str(t)]['generation_source_SHA'],
                reused=True,revalidation_contract=ref,data=record(dest/f'SLOT_{t:02d}.npz'))
            atomic(p,v)
    return ref


def b0_and_empty_policies(state,manifest):
    from v42_svr11.controller import initial
    from verify_svr11_handoff37 import audit_date
    old=state['old'];origin=read(OLD/'CAMPAIGN_LEDGER.json');ledger=initial()
    for day in DAYS:
        row=copy.deepcopy(origin['dates']['B0/'+day]);validation=audit_date(OLD,old,row)
        if row['status']!='PASS' or not validation['PASS']:raise PermissionError('EPOCH14_B0_INDEPENDENT_PASS_REQUIRED')
        evidence=list(validation['evidence'])+[record(OLD/'CAMPAIGN_MANIFEST.json'),
            record(ROOT/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json')]
        proof=dict(schema='SVR11_COMPLETED_RESULT_REUSE_V1',PASS=True,arm='B0',day=day,
            origin_root=str(OLD),execution_source_SHA=validation['execution_source_SHA'],
            validation_source_SHA=state['source_SHA'],equipment_SHA=read(manifest['hardware']['path'])['equipment_SHA'],
            original_result=row['result'],original_result_SHA=row['result_SHA'],validation=validation,
            evidence=evidence,changed_sources_reviewed=state['changes'],B0_physical_science_bitwise_unchanged=True,
            validator=record(__file__),Native_calls=0,AC_calls=0,original_result_bytes_changed=False,UTC=now())
        p=ROOT/'reuse'/(day+'_B0.json');atomic(p,proof)
        row.update(reused=True,reuse_proof=record(p),execution_source_SHA=proof['execution_source_SHA'],
            validation_source_SHA=state['source_SHA'],retry_pending=False)
        ledger['dates']['B0/'+day]=row
    for key,row in ledger['dates'].items():
        if row['arm']=='B0':continue
        previous=origin['dates'][key]
        row.update(previous_epoch_attempts=copy.deepcopy(previous.get('attempts',[])),
            previous_epoch_results=copy.deepcopy(previous.get('terminal_history',[])),
            previous_epoch_Native_Runtime=previous.get('Native_Runtime'),
            old_optimization_reused=False,fresh_Native_zero_required=True)
    ledger.update(policy='B2',source_SHA=state['source_SHA'],UTC=now())
    atomic(ROOT/'CAMPAIGN_LEDGER.json',ledger)


def release():
    state=readiness()
    if not state['ready']:print(state);return False
    ROOT.mkdir(exist_ok=True)
    with singleton(ROOT/'FULL_MILP_RELEASE.lock'):
        if (ROOT/'FULL_MILP_SUCCESSOR_READY.json').exists():
            from v42_svr11.authority import verify
            verify(ROOT/'CAMPAIGN_MANIFEST.json');return True
        if (ROOT/'SUPERVISOR_PROCESS.json').exists() and live(read(ROOT/'SUPERVISOR_PROCESS.json')):
            raise PermissionError('EPOCH14_RELEASE_CANNOT_REWRITE_ACTIVE_CAMPAIGN')
        full,reservation,peak=validation_contract(state)
        receipts=raw_and_hardware(state);forecast=forecast_contract(state,receipts)
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
            forecast_precompute_origin_ready=record(OLD/'MODEL_PRECOMPUTE_READY.json'),
            forecast_precompute_origin_ledger=record(OLD/'MODEL_PRECOMPUTE_LEDGER.json'),
            Forecast_precomputation_wall_external_to_policy_dates=True,
            full_MILP_measured_peak_bytes=peak,optimization_results_reused=0,B2_all31_fresh_Native_zero=True,
            same_Forecast_31_shared_by_B1_B2_B3=True,qualified_same_scientific_release_reuse=False,
            user_latest_20261011_B2_from_May01=True,UTC=now())
        atomic(ROOT/'CAMPAIGN_MANIFEST.json',m)
        from v42_svr11.authority import verify
        verify(ROOT/'CAMPAIGN_MANIFEST.json');b0_and_empty_policies(state,m)
        from svr11_model_precompute import check_model
        for day in DAYS:check_model(ROOT,m,day)
        from svr11_monitor_ui import ui_files
        atomic(ROOT/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),
            scientific_source_unchanged=True,Native_calls=0,UTC=now()))
        atomic(ROOT/'FULL_MILP_SUCCESSOR_READY.json',dict(PASS=True,root=str(ROOT),source_SHA=state['source_SHA'],
            manifest=record(ROOT/'CAMPAIGN_MANIFEST.json'),full_MILP_validation=full,Forecast31_PASS=True,
            B0_qualified_preserved=31,B2_fresh_zero_start=True,healthy_workers_terminated=0,UTC=now()))
        print('FULL_MILP_SUCCESSOR_READY',state['source_SHA'],reservation)
        return True


if __name__=='__main__':
    if sys.argv[1]=='readiness':print({k:v for k,v in readiness().items() if k not in ('old','sources')})
    elif sys.argv[1]=='release':release()
    else:raise ValueError('UNKNOWN_RELEASE_MODE')
