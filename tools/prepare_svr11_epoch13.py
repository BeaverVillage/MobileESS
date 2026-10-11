"""Exact Forecast performance successor; healthy predecessor workers drain."""
from pathlib import Path
import sys,shutil,copy,json,subprocess
import psutil
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import read,record,atomic,now,sha,digest
from v42_common_campaign.authority import source_files
from v42_svr11.processes import live
from reuse_svr11_completed import normalized_reviewed_model
OLD=Path(r'D:\v42_svr11_may_20261011_12')
ROOT=Path(r'D:\v42_svr11_may_20261011_13')
DIAG=Path(r'D:\v42_svr11_model_performance_20261011')
DOCS=SOURCE/'docs/v42_svr11_forecast_fastpath_20261011'
Q='DISPATCH_QUIESCENCE_FOR_FORECAST_FASTPATH.json'

def proof():
    old=read(OLD/'CAMPAIGN_MANIFEST.json');sources=source_files()
    changes={k for k in set(sources)|set(old['execution_sources']) if sources.get(k)!=old['execution_sources'].get(k)}
    assert changes=={'v42_svr11/model.py'}
    before=Path(old['code_root'])/'v42_svr11/model.py';after=SOURCE/'v42_svr11/model.py'
    assert normalized_reviewed_model(before.read_text())==normalized_reviewed_model(after.read_text())
    v=read(DIAG/'VALIDATION.json')
    assert v['PASS'] and len(v['setters'])==31 and sum(a['slots'] for a in v['setters'])==2976
    assert all(a['bitwise_IEEE_values'] for a in v['setters'])
    assert len(v['native'])==5 and all(a['all121responses_bitwise_equal'] and a['all9coefficient_fields_bitwise_equal']
        and a['controller_taps_queue_clock_and_solve_counts_equal'] for a in v['native'])
    assert v['Actual_inputs_used']==v['tap_settings_changes']==v['independent_context_reuse']==v['solves_skipped']==v['official_workers_modified']==0
    g=read(DIAG/'GENERATOR_CONNECTION/GENERATOR_CONNECTION_VALIDATION.json')
    assert g['PASS'] and g['candidate_source_SHA']==digest(sources) and g['model_source']==record(after) and all(g['fields'].values())
    DOCS.mkdir(parents=True,exist_ok=True)
    for name in ('PROFILE.json','PROFILE.txt','VALIDATION.json','INTERLEAVED_BENCHMARK.json','profile_probes.py','exact_fastpath.py','validate_fastpath.py','benchmark_interleaved.py','check_generator_connection.py'):
        shutil.copyfile(DIAG/name,DOCS/name)
    shutil.copyfile(DIAG/'GENERATOR_CONNECTION/GENERATOR_CONNECTION_VALIDATION.json',DOCS/'GENERATOR_CONNECTION_VALIDATION.json')
    v=dict(PASS=True,generation_source_SHA=old['execution_SHA'],successor_source_SHA=digest(sources),
        source_before=record(before),source_after=record(after),changed_scientific_sources=sorted(changes),
        strict_reviewed_model_AST_identical=True,all31_forecast_96_slot_inputs_bitwise_equal=True,
        representative_real_DSS_121_responses_and_coefficients_bitwise_equal=True,
        all_native_solve_counts_timestamps_and_auto_control_commands_identical=True,
        physical_model_objective_integer_domain_constraints_budgets_changed=False,
        equipment_SHA=read(old['hardware']['path'])['equipment_SHA'],Actual_inputs_read=0,
        qualified_completed_dates_and_models_reusable=True,
        evidence={name:record(DOCS/name) for name in ('VALIDATION.json','INTERLEAVED_BENCHMARK.json','GENERATOR_CONNECTION_VALIDATION.json','REGRESSION.json')},
        scope='2976 exact Forecast setter streams, strict model AST, five 121-response prefixes and real generator connection; not global voltage safety certification.',UTC=now())
    assert read(DOCS/'REGRESSION.json')['exit_code']==0
    atomic(DOCS/'EQUIVALENCE.json',v);ROOT.mkdir(exist_ok=True)
    atomic(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json',v)
    print('EXACT_FORECAST_EQUIVALENCE_PASS',digest(sources))

def validate_proof():
    v=read(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json')
    assert v['PASS'] and v['successor_source_SHA']==digest(source_files())
    for r in list(v['evidence'].values())+[v['source_before'],v['source_after']]:assert record(r['path'])==r
    return v

def origin_workers():
    import prepare_svr11_epoch10 as helper
    helper.SOURCE=SOURCE;helper.OLD=OLD
    return helper.origin_workers()

def quiesce():
    validate_proof();old=read(OLD/'CAMPAIGN_MANIFEST.json')
    for k,v in old['execution_sources'].items():assert sha(Path(old['code_root'])/k)==v
    sup=read(OLD/'SUPERVISOR_PROCESS.json');assert live(sup) and sup['source_SHA']==old['execution_SHA']
    assert not (OLD/Q).exists();p=psutil.Process(sup['PID']);assert p.status()!=psutil.STATUS_STOPPED
    peers=origin_workers();p.suspend()
    atomic(OLD/Q,dict(PASS=True,process=sup,root=str(OLD),source_SHA=old['execution_SHA'],new_dispatch_quiesced=True,
        worker_terminated=0,current_workers_preserved=peers,equivalence=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        reason='Exact Forecast setter/measurement cache; only dispatch pauses; healthy Workers finish naturally; qualified same-science results preserve execution SHA/runtime.',UTC=now()))
    assert all(live(v) for v in peers);print('DISPATCH_QUIESCED_HEALTHY_WORKERS_PRESERVED',len(peers))

def prepare():
    validate_proof();assert not (ROOT/'CAMPAIGN_MANIFEST.json').exists()
    (ROOT/'hardware').mkdir(parents=True,exist_ok=True)
    for p in (OLD/'hardware').iterdir():
        if p.is_file():shutil.copyfile(p,ROOT/'hardware'/p.name)
    atomic(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),source_SHA=read(OLD/'CAMPAIGN_MANIFEST.json')['execution_SHA'],
        dispatch_quiescence=record(OLD/Q),equivalence=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        reason='Exact Forecast setter and terminal measurement performance change; unchanged science/equipment; all original evidence retained.',
        physical_equipment_change=False,scientific_model_change=False,all_old_results_preserved=True,qualified_completed_dates_reused=True,UTC=now()))
    old=read(OLD/'CAMPAIGN_MANIFEST.json');receipts={};links=[]
    for day,refs in old['input_receipts'].items():
        dest=ROOT/'raw'/day;dest.mkdir(parents=True,exist_ok=True)
        for r in refs:
            assert record(r['path'])==r;p=dest/Path(r['path']).name;assert not p.exists()
            if p.name=='OPERATIONS_TEMPLATE_B2.json':
                v=read(r['path']);v['current_day_folder']=str(dest);atomic(p,v)
            else:
                p.hardlink_to(r['path']);assert record(p)['sha256']==r['sha256'];links.append(dict(original=r,linked=record(p)))
        receipts[day]=[record(p) for p in sorted(dest.iterdir()) if p.is_file()]
    atomic(ROOT/'RAW_INPUT_RECEIPTS.json',receipts);atomic(ROOT/'RAW_INPUT_ORIGINS.json',old['origins'])
    atomic(ROOT/'SELECTIVE_REUSE_LEDGER.json',dict(PASS=True,raw_NTFS_hardlinks=links,
        mutable_files_hardlinked=0,pre_scientific_repair_final_coefficient_reuse=0,
        exact_Source12_completed_model_reuse_requires_contract=True,original_files_deleted=0,UTC=now()))
    validation=read(OLD/'MODEL_VALIDATION_RELEASE_CONTRACT.json')
    validation.update(source_SHA=digest(source_files()),model_code_SHA=source_files()['v42_svr11/model.py'],
        exact_performance_equivalence=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        original_scientific_release_SHA=old['execution_SHA'],performance_generator_connection=record(DOCS/'GENERATOR_CONNECTION_VALIDATION.json'),
        numerical_evidence_execution_SHA_unchanged=True,UTC=now())
    atomic(ROOT/'MODEL_VALIDATION_RELEASE_CONTRACT.json',validation)
    print('IMMUTABLE_RAW_AND_RELEASE_CONTRACT_READY')

def finish():
    validate_proof();peers=origin_workers()
    if peers:print('WAITING_PREDECESSOR_DRAIN',len(peers));return False
    import prepare_svr11_epoch07 as helper
    helper.root=ROOT;helper.old=OLD
    if not (ROOT/'CAMPAIGN_MANIFEST.json').exists():
        shutil.copyfile(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json',ROOT/'COEFFICIENT_IO_EQUIVALENCE.json')
        helper.freeze_slots()
        m=release_exact()
    else:
        from v42_svr11.authority import verify
        m=verify(ROOT/'CAMPAIGN_MANIFEST.json')
    if (ROOT/'CAMPAIGN_LEDGER.json').exists():
        from reuse_svr11_completed import admit_before_first_dispatch
        from preserve_svr11_terminal_failures import admit
        admit(ROOT,OLD);admit_before_first_dispatch(ROOT)
        seal_ready(m)
        return True
    # Original scientific repair still requires all 124 outcomes. Equivalent
    # Source12 outcomes retain their original execution source and fresh AC.
    from v42_svr11.controller import initial
    from reuse_svr11_completed import qualify,admit_before_first_dispatch
    ledger=initial()
    for day in old_days():
        p,v,row=qualify(ROOT,OLD,day)
        row.update(reused=True,reuse_proof=record(p),execution_source_SHA=v['execution_source_SHA'],validation_source_SHA=m['execution_SHA'],retry_pending=False)
        ledger['dates']['B0/'+day]=row
    contract=read(ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json');origin=read(OLD/'CAMPAIGN_LEDGER.json')
    for day,value in contract['days'].items():
        dest=ROOT/'models'/day;(dest/'FORECAST_ANCHOR').mkdir(parents=True,exist_ok=True)
        for name,r in value['forecast_anchor'].items():
            assert record(r['path'])==r;shutil.copyfile(r['path'],dest/'FORECAST_ANCHOR'/name)
        for slot,r in value['slots'].items():
            data=dest/f'SLOT_{int(slot):02d}.npz';assert record(r['original_data']['path'])==r['original_data'];shutil.copyfile(r['original_data']['path'],data)
            v=read(r['original_checkpoint']['path']);v.update(source_SHA=m['execution_SHA'],generation_source_SHA=r['generation_source_SHA'],
                reused=True,data=record(data),revalidation_contract=m['model_checkpoint_reuse_contract'])
            atomic(dest/f'SLOT_{int(slot):02d}.json',v)
        oldrow=origin['dates']['B2/'+day];history=list(oldrow.get('previous_epoch_attempts',[]))
        if oldrow.get('request'):
            history.append(record(oldrow['request']));result=Path(read(oldrow['request'])['result'])
            if result.exists():history.append(record(result))
        ledger['dates']['B2/'+day].update(previous_epoch_attempts=history,previous_epoch_Native_Runtime=oldrow.get('Native_Runtime'),
            previous_epoch_runtime_pending=oldrow['status']=='RUNNING',reused_forecast_model_slots=len(value['slots']))
    ledger.update(policy='B2',source_SHA=m['execution_SHA'],UTC=now());atomic(ROOT/'CAMPAIGN_LEDGER.json',ledger)
    from preserve_svr11_terminal_failures import admit
    admit(ROOT,OLD);admit_before_first_dispatch(ROOT)
    atomic(ROOT/'REUSE_ADMISSION.json',dict(PASS=True,reused_completed_dates=sum(bool(r.get('reused')) for r in read(ROOT/'CAMPAIGN_LEDGER.json')['dates'].values()),
        completed_model_slots_reused=sum(len(v['slots']) for v in contract['days'].values()),original_execution_SHA_and_Runtime_preserved=True,
        healthy_workers_terminated=0,Native_calls=0,AC_calls=0,UTC=now()))
    seal_ready(m)
    print('EXACT_FORECAST_SUCCESSOR_READY',m['execution_SHA']);return True

def seal_ready(m):
    from svr11_monitor_ui import ui_files
    atomic(ROOT/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),scientific_source_unchanged=True,Native_calls=0,UTC=now()))
    atomic(ROOT/'EXACT_FORECAST_SUCCESSOR_READY.json',dict(PASS=True,root=str(ROOT),source_SHA=m['execution_SHA'],
        manifest=record(ROOT/'CAMPAIGN_MANIFEST.json'),healthy_workers_terminated=0,predecessor_workers=0,
        mathematical_model_changed=False,UTC=now()))

def release_exact():
    """Same scientific campaign, distinct immutable execution/provenance."""
    from v42_svr11.model_release import validate
    from v42_svr11.authority import verify
    assert not (ROOT/'CAMPAIGN_MANIFEST.json').exists()
    sources=source_files();source_sha=digest(sources)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    hp=ROOT/'hardware/HARDWARE.json';h=read(hp)
    atomic(ROOT/'hardware/PROVISIONAL_IMPLEMENTATION_FREEZE.json',h)
    h.update(source_SHA=source_sha,source_commit=commit,source_release_UTC=now(),
        provisional_receipt=record(ROOT/'hardware/PROVISIONAL_IMPLEMENTATION_FREEZE.json'))
    atomic(hp,h)
    atomic(ROOT/'B3_SOURCE_SEAL.json',dict(schema='B3_AUTONOMOUS_SOURCE_SEAL_V1',root=str(SOURCE),source_sha=source_sha,files=sources))
    m=copy.deepcopy(read(OLD/'CAMPAIGN_MANIFEST.json'))
    m.update(root=str(ROOT),code_root=str(SOURCE),run_id='SVR11_FINAL_MAY_'+ROOT.name,
        execution_sources=sources,execution_SHA=source_sha,source_commit=commit,
        scientific_model_validation=validate(ROOT,sources),hardware=record(hp),
        scenario=record(ROOT/'hardware/SCENARIO.json'),thermal=record(ROOT/'hardware/THERMAL.json'),
        input_receipts=read(ROOT/'RAW_INPUT_RECEIPTS.json'),origins=read(ROOT/'RAW_INPUT_ORIGINS.json'),
        implementation=dict(version=m['implementation']['version'],sources=sources),builder_original_sources=sources,
        predecessor_drain_contract=record(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json'),
        model_checkpoint_reuse_contract=record(ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json'),
        fresh_all_124_physical_results_required=False,
        all_124_outcomes_since_Source12_scientific_repair_required=True,
        scientific_campaign_origin_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),
        qualified_same_scientific_release_reuse=True,previous_epoch_optimization_results_promoted=0,
        previous_epoch_AC_PASS_promoted=0,pre_scientific_repair_results_promoted=0,
        previous_epoch_promotion_counter_scope='Scientific changes before Source12; exact Source12 reuse counted in REUSE_ADMISSION with original execution SHA.',
        mathematical_model_changed=False,performance_equivalence=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        unused_probe_EventLog_receipt_copy=False,UTC=now())
    atomic(ROOT/'CAMPAIGN_MANIFEST.json',m);verify(ROOT/'CAMPAIGN_MANIFEST.json');return m

def arm_pending():
    validate_proof()
    atomic(ROOT/'PENDING_EXACT_FORECAST_RELEASE.json',dict(PASS=True,root=str(ROOT),code_root=str(SOURCE),
        source_SHA=digest(source_files()),prepare_tool=record(Path(__file__)),
        proof=record(ROOT/'FORECAST_ALLOCATION_CACHE_EQUIVALENCE.json'),
        predecessor=record(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json'),healthy_workers_must_finish_naturally=True,UTC=now()))

def pending_release(root):
    from v42_common_campaign.authority import singleton
    assert Path(root).resolve()==ROOT
    v=read(ROOT/'PENDING_EXACT_FORECAST_RELEASE.json')
    assert v['PASS'] and Path(v['root'])==ROOT and Path(v['code_root'])==SOURCE and v['source_SHA']==digest(source_files())
    for key in ('prepare_tool','proof','predecessor'):assert record(v[key]['path'])==v[key]
    with singleton(ROOT/'EXACT_FORECAST_RELEASE.lock'):
        if (ROOT/'EXACT_FORECAST_SUCCESSOR_READY.json').exists():return True
        return finish()

def old_days():
    from v42_svr11 import DAYS
    return DAYS

if __name__=='__main__':{'proof':proof,'quiesce':quiesce,'prepare':prepare,'finish':finish,'arm_pending':arm_pending}[sys.argv[1]]()
