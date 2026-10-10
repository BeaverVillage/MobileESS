"""Capture a fixed read-only artifact boundary; do not import campaign code."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

REPO=Path(r'D:\MobileESS_v42_autonomous')
ROOT=Path(r'D:\v42_may_restart_20261010_02')
SOURCE=Path(r'D:\v42_source36_actual_transition_independent_audit_20261010_01')
WATCH=ROOT/'autonomous/source36_actual_watch'
OUT=Path(__file__).resolve().parent
BASE=REPO/'docs/v42_autonomous_may_20261010'
DEST=BASE/'SOURCE36_FIRST_ACTUAL_TRANSITIONS'
S35='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
S36='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'

def utc():return datetime.now(timezone.utc).isoformat()
def raw_record(path,raw):return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def record(path):return raw_record(path,Path(path).read_bytes())
def parse(raw):return json.loads(raw.decode('utf-8-sig'))
def read(path):return parse(Path(path).read_bytes())
def write(path,obj):
    assert not path.exists(),str(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    return record(path)
def hashes(paths):return {str(p):record(p)['sha256'] for p in paths}

def main():
    assert not DEST.exists(),'NEW_PACKAGE_ALREADY_EXISTS'
    start=utc()
    m36=read(ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json')
    original={str(REPO/p):sha for p,sha in m36['builder_original_sources'].items()}
    execution={str(REPO/p):sha for p,sha in m36['execution_sources'].items()}
    freezes={v:{r['path']:r['sha256'] for r in read(ROOT/f'autonomous/V{v}_SPARSE_IMMUTABLE_FREEZE.json')['source_files']} for v in ('35','36')}
    protected_before=dict(original1007=hashes(original),execution99=hashes(execution),
        frozen={v:hashes(paths) for v,paths in freezes.items()})
    assert len(original)==1007 and len(execution)==99
    assert protected_before['original1007']==original and protected_before['execution99']==execution
    assert all(len(rows)==1111 and protected_before['frozen'][v]==rows for v,rows in freezes.items())
    old_inventories=hashes(sorted(BASE.rglob('SHA_INVENTORY*.json')))
    captures={}
    def capture(source,relative,scope):
        assert relative not in captures
        raw=Path(source).read_bytes()
        if Path(source).suffix.lower()=='.json':parse(raw)
        captures[relative]=dict(raw=raw,source=raw_record(source,raw),captured_UTC=utc(),scope=scope)
        return parse(raw) if Path(source).suffix.lower()=='.json' else raw
    original_paths=sorted(p for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    watch_paths=sorted(p for p in WATCH.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for p in original_paths:capture(p,'INDEPENDENT_TRANSITION_AUDIT/'+p.relative_to(SOURCE).as_posix(),'fixed selected original producer paths; producer can append later')
    for p in watch_paths:capture(p,'ROOT_READONLY_WATCH/'+p.relative_to(WATCH).as_posix(),'fixed selected watch paths; watch can append later')
    hourly=ROOT/'autonomous/CODEX_HOURLY_AUTOMATION_VERIFICATION_20261010T014402.json'
    hourly_data=capture(hourly,'HOURLY_CONFIGURATION/'+hourly.name,'historical saved configuration verification')
    for p in [ROOT/'B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json',ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json',
        ROOT/'autonomous/V35_SPARSE_IMMUTABLE_FREEZE.json',ROOT/'autonomous/V36_SPARSE_IMMUTABLE_FREEZE.json']:
        capture(p,'SOURCE_MANIFESTS/'+p.name,'immutable manifest and frozen source map')
    def get(p):return parse(captures['INDEPENDENT_TRANSITION_AUDIT/'+p]['raw'])
    def exact_ref(ref):
        p=Path(ref['path'])
        if p.is_relative_to(SOURCE):entry=captures['INDEPENDENT_TRANSITION_AUDIT/'+p.relative_to(SOURCE).as_posix()]['source']
        else:entry=record(p)
        assert all(entry[k]==ref[k] for k in ('bytes','sha256')),ref
        return entry
    baseline=get('SOURCE36_TRANSITION_INITIAL_BASELINE_RECEIPT.json')
    assert captures['INDEPENDENT_TRANSITION_AUDIT/SOURCE36_TRANSITION_INITIAL_BASELINE_RECEIPT.json']['source']['sha256']=='50bd205932035323071c1b8458b389ad5ddfc823ae4aaef749d1e6f12f925506'
    assert baseline['observed_transition_event_count']==0 and baseline['transition_event_PASS'] is None
    clarification=get('BASELINE_CHECKPOINT_BYTE_PROVENANCE_CLARIFICATION.json')
    assert 'reserialized' in clarification['original_BASELINE_CHECKPOINT_RAW_json_is']
    exact_ref(clarification['additive_current_checkpoint_exact_byte_copy'])
    state=get('OBSERVED_EVENT_STATE.json')
    assert state['RMP_pre']=={} and state['RMP_complete']=={} and state['terminal36']=={},'NEW_EVENT_REQUIRES_NEW_BOUNDARY_AND_CLAIMS'
    expected_terminal={
      '2025-05-01':('d3f96dc1517b70a010b3793e8a8b7e2906d8ffa837d1ac6a26578a342a995158',5400.2660002708435,65),
      '2025-05-02':('489681e90deac36c1d387cd5c596393cc09f8aa65fefc4dd9eda33e42b6ff354',5400.247000455856,56),
      '2025-05-03':('2e8bc8b8f9e178055e0e96bd79928a8515d504ee68d35dcd51ff8e0678e130c0',5400.24299955368,63)}
    terminals={}
    for day,(sha,measured,count) in expected_terminal.items():
        ref=state['terminal35']['B2/'+day];assert exact_ref(ref)['sha256']==sha
        event=get(Path(ref['path']).relative_to(SOURCE).as_posix())
        assert event['kind']=='SOURCE35_TERMINAL' and event['identity']['day']==day and event['source']==S35
        assert event['actual_worker_result_PASS'] is False and event['actual_worker_status']=='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
        assert event['measured_Native']==measured and event['completed_Native_calls']==count and event['cumulative_Native_unknown'] is False
        for r in event['raw_refs'].values():exact_ref(r)
        result=get(Path(event['raw_refs']['result']['path']).relative_to(SOURCE).as_posix())
        request=get(Path(event['raw_refs']['request']['path']).relative_to(SOURCE).as_posix())
        ledger=get(Path(event['raw_refs']['ledger']['path']).relative_to(SOURCE).as_posix())
        prior=get('B2_'+day+'_SOURCE35_BASELINE_NATIVE_RAW.json')
        assert result['PASS'] is False and result['status']==event['actual_worker_status'] and result['source_SHA']==S35
        assert result['identity']==event['identity'] and request['implementation_SHA']==S35
        assert ledger['Native_ceiling_seconds']==5400 and ledger['P2_calls']==0 and ledger['measured_Native_Runtime']==measured
        assert ledger['calls'][:len(prior['calls'])]==prior['calls']
        assert len([c for c in ledger['calls'] if c.get('status')=='FINISHED'])==count
        for p,name in [(Path(event['result_source']['path']),'RESULT.json'),(Path(request['result']).parent/'NATIVE_RUNTIME_LEDGER.json','NATIVE_RUNTIME_LEDGER.json'),
            (Path(event['result_source']['path']).parent/'request.json','request.json')]:
            capture(p,'CURRENT_ORIGINAL_READS/SOURCE35_TERMINAL/'+day+'/'+name,'sequential current original terminal read, not an atomic current snapshot')
        assert captures['CURRENT_ORIGINAL_READS/SOURCE35_TERMINAL/'+day+'/RESULT.json']['source']['sha256']==event['result_source']['sha256']
        assert captures['CURRENT_ORIGINAL_READS/SOURCE35_TERMINAL/'+day+'/NATIVE_RUNTIME_LEDGER.json']['source']['sha256']==event['raw_refs']['ledger']['sha256']
        terminals[day]=dict(receipt=ref,actual_worker_status=event['actual_worker_status'],actual_worker_PASS=False,
            known_Native_Runtime=measured,completed_Native_calls=count,Native_budget_seconds=5400,unchanged_completed_baseline_prefix=True)
    expected_births={
      'repair_b2_v36_01_s3':('fe3fa0645f12111876b09fd5f12ac52d71df898673e8a601148d003ed017617b','2025-05-01',91368,1),
      'repair_b2_v36_01_s1':('5478b58435696af1abaf90e729351aff50eaa54da3be73c77ee662da4a53e137','2025-05-02',107404,2),
      'fresh_b2_v36_01':('2afacc108b80825cf2cb2cf18422e01b488bb4d65561903ea953ed40ab63b7c1','2025-05-10',61988,0)}
    births={}
    for attempt,(sha,day,pid,streak) in expected_births.items():
        ref=state['birth36'][attempt];assert exact_ref(ref)['sha256']==sha
        event=get(Path(ref['path']).relative_to(SOURCE).as_posix())
        assert event['identity']['day']==day and event['identity']['attempt_id']==attempt and event['process']['PID']==pid
        assert event['process']['cwd']==r'D:\v42run36' and event['original_manifest99_source']==S36
        assert event['Native0_observed'] is True and event['measured_Native_at_first_observation']==0 and event['remaining_Native_at_first_observation']==5400
        assert event['observation']['retry_streak']['B2']==streak
        for r in event['raw_refs'].values():exact_ref(r)
        request=get(Path(event['raw_refs']['request']['path']).relative_to(SOURCE).as_posix())
        assert request['implementation_SHA']==S36 and request['native_budget_seconds']==5400 and request['P2_calls']==0 and request['Threads']==1
        if attempt.startswith('fresh'):
            assert 'previous_attempts' not in request and event['previous_attempts'] is None and event['previous_attempts_field_present'] is False
            assert event['cold_manifest_day_has_no_prior_attempt'] is True
        else:assert request['previous_attempts']==[] and request['restart_from_zero'] is True
        births[day]=dict(receipt=ref,PID=pid,attempt_id=attempt,Native0_observed=True,remaining_Native_at_birth=5400,
            actual_retry_streak=streak,previous_attempts_field_present='previous_attempts' in request)
    first_dir=Path(state['birth36']['repair_b2_v36_01_s3']['path']).parent
    first=get((first_dir/'FIRST_ACTUAL_RETRY_ACTIVATION_COUNTER_RECEIPT.json').relative_to(SOURCE).as_posix())
    ordinary_dir=Path(state['birth36']['fresh_b2_v36_01']['path']).parent
    addendum_path=ordinary_dir/'ACTUAL_TWO_RETRY_THEN_ORDINARY_AND_MAY03_PENDING_RECEIPT.json'
    assert captures['INDEPENDENT_TRANSITION_AUDIT/'+addendum_path.relative_to(SOURCE).as_posix()]['source']['sha256']=='40ca8f9a9ffce8a517589fab411b1fe3183ba1a65e4c091955f8f0192b8eeae5'
    addendum=get(addendum_path.relative_to(SOURCE).as_posix())
    assert addendum['counter_before_second_retry_observation']==2 and addendum['counter_after_ordinary_observation']==0
    assert addendum['current_worker_dates']==['2025-05-01','2025-05-02','2025-05-10']
    row=addendum['May03_actual_retry_queue_row']
    assert row['date']=='2025-05-03' and row['retry_priority']==1000 and row['verification_status']=='READY_VERIFIED_REPAIR'
    assert row['new_worker_PID'] is None and row['retry_attempt_id'] is None
    error_ref=state['errors']["KeyError('previous_attempts')"]
    assert exact_ref(error_ref)['sha256']=='baabccf91b7a1f30c7cd1fdaf52b6ccb2037c6c8dd1c066e8b1ad6b225ae66ce'
    error=get(Path(error_ref['path']).relative_to(SOURCE).as_posix())
    assert error['PASS'] is False and error['error']=="KeyError('previous_attempts')"
    readyfailure=get('EXTERNAL_ORDINARY_ADDENDUM_READY_LABEL_FAILURE_01.json')
    assert readyfailure['PASS'] is False and readyfailure['exit_code']==1 and readyfailure['raw_OS_redirect_file_claimed'] is False
    assert captures['INDEPENDENT_TRANSITION_AUDIT/observe_events.py']['source']['sha256']=='f3028086f8a4d72f00f0e22b95f28bd3a2defc1eac616a7aa13f9967b69e86ce'
    assert captures['INDEPENDENT_TRANSITION_AUDIT/OBSERVER_ORDINARY_SCHEMA_AND_DATE_ATTEMPT_KEY_CORRECTION.json']['source']['sha256']=='c79f1f6ba2200fe3bd4fc42d28c09f1a834793cc39a7ddb0261108cf33e91488'
    watch_events=[]
    for p in watch_paths:
        if p.name!='OBSERVATION.json':continue
        relative='ROOT_READONLY_WATCH/'+p.relative_to(WATCH).as_posix()
        event=parse(captures[relative]['raw'])
        assert event['source_SHA']==S36 and event['day'] in ('2025-05-01','2025-05-02')
        for ref in event['files']:
            raw=captures['ROOT_READONLY_WATCH/'+Path(ref['path']).relative_to(WATCH).as_posix()]['source']
            assert all(raw[k]==ref[k] for k in ('bytes','sha256'))
        watch_events.append(dict(day=event['day'],event=event['event'],UTC=event['UTC'],receipt=captures[relative]['source']))
    assert hourly_data['actual_scheduled_run_observed'] is False and hourly_data['recent_run_records']==[]
    assert hourly_data['database']['status']=='ACTIVE'
    current_cp=capture(ROOT/'SUPERVISOR_STATE.json','CURRENT_ORIGINAL_READS/SUPERVISOR_STATE.json','sequential current checkpoint, not an atomic snapshot')
    for name in ('RECOVERY_QUEUE.json','SUPERVISOR_HEARTBEAT.json','SUPERVISOR_PROCESS.json'):
        capture(ROOT/name,'CURRENT_ORIGINAL_READS/'+name,'sequential current raw control observation only')
    currents={}
    for day,birth in births.items():
        worker=current_cp['workers']['B2/'+day]
        assert worker['PID']==birth['PID'] and worker['source_SHA']==S36
        request=capture(worker['request'],'CURRENT_ORIGINAL_READS/SOURCE36_RUNNING/'+day+'/request.json','sequential current request')
        ledger_path=Path(worker['request']).parent/'NATIVE_RUNTIME_LEDGER.json'
        ledger=capture(ledger_path,'CURRENT_ORIGINAL_READS/SOURCE36_RUNNING/'+day+'/NATIVE_RUNTIME_LEDGER.json','sequential growing Native ledger prefix; not final runtime')
        assert ledger['Native_ceiling_seconds']==5400 and ledger['P2_calls']==0
        finished=[c for c in ledger['calls'] if c.get('status')=='FINISHED']
        checked=[]
        for event in watch_events:
            if event['day']!=day:continue
            parent=Path(event['receipt']['path']).parent
            key='ROOT_READONLY_WATCH/'+(parent/'NATIVE_RUNTIME_LEDGER.json').relative_to(WATCH).as_posix()
            if key not in captures:continue
            historical=parse(captures[key]['raw'])
            for i,c in enumerate(historical['calls']):
                if c.get('status')=='FINISHED':
                    assert ledger['calls'][i]==c,'COMPLETED_WATCH_NATIVE_PREFIX_DRIFT'
            checked.append(event['event'])
        for path in (Path(request['progress']),Path(worker['request']).parent/'HEARTBEAT.json'):
            if path.exists():capture(path,'CURRENT_ORIGINAL_READS/SOURCE36_RUNNING/'+day+'/'+path.name,'sequential growing current progress/heartbeat')
        rmp_seen=[c for c in ledger['calls'] if 'RESTRICTED_MASTER' in c.get('label','')]
        assert rmp_seen==[],'ACTUAL_RMP_REQUIRES_UPDATED_PACKAGE_CLAIMS'
        currents[day]=dict(PID=worker['PID'],attempt_id=request['attempt_id'],ledger_UTC=ledger.get('UTC'),
            measured_Native_at_individual_read=ledger['measured_Native_Runtime'],completed_Native_calls_at_read=len(finished),
            completed_watch_prefix_unchanged=True,verified_watch_events=checked,actual_RMP_call_observed=False,
            current_terminal_result_exists=Path(request['result']).exists(),final_runtime_or_scientific_PASS_inferred=False)
        assert not currents[day]['current_terminal_result_exists'],'ACTUAL_TERMINAL_REQUIRES_UPDATED_PACKAGE_CLAIMS'
    protected_after=dict(original1007=hashes(original),execution99=hashes(execution),
        frozen={v:hashes(paths) for v,paths in freezes.items()})
    assert protected_before==protected_after
    assert old_inventories==hashes(old_inventories)
    review=dict(schema='V42_SOURCE36_FIRST_ACTUAL_TRANSITIONS_READONLY_DOC_REVIEW_V1',UTC_start=start,UTC_end=utc(),
        artifact_integrity_verified=True,scope='byte/identity/saved-event consistency only; no scientific certification',
        source35_terminal=terminals,source36_actual_births=births,actual_B2_retry_counter_sequence=[1,2,0],
        May03_at_ordinary_event=dict(verification_status=row['verification_status'],retry_priority=1000,new_worker_PID=None),
        ordinary_schema_field_omission_preserved=True,external_observer_failures_preserved=True,
        baseline_reserialized_checkpoint_not_mislabeled_exact_source_bytes=True,
        watch_events=watch_events,current_sequential_reads=currents,
        hourly_receipt=captures['HOURLY_CONFIGURATION/'+hourly.name]['source'],actual_hourly_run_observed=False,
        first_RMP_event_observed_in_fixed_capture=False,Source36_performance_benefit_observed=False,Source36_final_scientific_PASS_observed=False,
        protected_start=protected_before,protected_end=protected_after,previous_inventories=old_inventories,
        model_constructions=0,Native_optimize_calls=0,checker_replays=0,new_tests=0,production_mutations=0,Git_mutations=0,
        limitations=['Fixed selected path and byte boundary only; both producer directories may append or update cursor/script later.',
        'Each raw file has its own read UTC; no atomic current runtime, control, process or queue snapshot is asserted.',
        'Zero Native birth and actual counter transition do not establish convergence, usable Pi, certified gap or final PASS.',
        'Saved full-LP method6/status11/SolCount0 records concern the original full LP; they do not measure the Source36 RMP repair benefit.',
        'Absent previous_attempts is preserved as omitted; the corrected event distinguishes null/field presence from effective empty history.',
        'The READY-label failure stderr is a copied actual-tool transcript, not a raw OS redirected stderr file.'])
    review_record=write(OUT/'SOURCE36_FIRST_ACTUAL_TRANSITIONS_READONLY_DOC_REVIEW.json',review)
    # All dependent validations completed before creating this new package.
    DEST.mkdir(parents=True)
    provenance=[]
    for relative,item in captures.items():
        dest=DEST/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(item['raw'])
        copied=record(dest);assert all(copied[k]==item['source'][k] for k in ('bytes','sha256'))
        provenance.append(dict(package_relative_path=relative,source_at_capture=item['source'],captured_UTC=item['captured_UTC'],
            scope=item['scope'],package_copy=copied))
    for p,relative in [(Path(review_record['path']),'INDEPENDENT_DOC_REVIEW/SOURCE36_FIRST_ACTUAL_TRANSITIONS_READONLY_DOC_REVIEW.json'),
        (Path(__file__),'INDEPENDENT_DOC_REVIEW/package_transitions.py')]:
        dest=DEST/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
        provenance.append(dict(package_relative_path=relative,source_at_capture=record(p),captured_UTC=utc(),scope='external read-only package producer/review',package_copy=record(dest)))
    README='''# Source36 first actual transitions: fixed read-only capture

The package preserves the initial baseline, all three Source35 terminal events,
the actual Source36 May01 and May02 repair births and May10 ordinary birth,
and actual B2 retry streak 1 then 2 then ordinary 0. May03 remains
READY_VERIFIED_REPAIR at priority1000 with no new PID in the saved ordinary
event. This observes the first bounded fairness transition, not future dispatch.

Source35 May01/02/03 all ended TIME_LIMIT_FEASIBLE_NOT_CERTIFIED with PASS=false.
Their measured Native times are 5400.2660002708435 / 5400.247000455856 /
5400.24299955368 seconds, with 65 / 56 / 63 completed calls. The original
requested ceiling remains5400; small measured overruns are preserved literally.
No failed result is promoted to scientific PASS.

Source36 births have real zero ledgers and fresh5400 remaining budgets.
The ordinary May10 request omits previous_attempts; its bytes remain omitted,
and the corrected event explicitly records field absence and null separately
from effective empty history. The initial external KeyError, prospective RMP
nested-source correction, ordinary/date+attempt observer correction and
canonical READY-label addendum harness failure are retained. The READY failure
is copied actual-tool stderr text, not a raw OS redirected stderr file.

Root watch raw birth/first completed Native/full-LP entry observations and the
014402 hourly configuration verification are included. Completed watch Native
prefixes match the later sequential ledger reads. Full LP method6 completion
with status11/SolCount0 is not a measurement of the Source36 RMP repair.
No first RMP call/event or Source36 final result existed in this capture;
usable Pi, repair performance, Global Gap and final FULL/Actual/Fresh PASS
remain pending. Saved ACTIVE hourly configuration does not establish a run.

Each selected source file has its own capture UTC, exact bytes and SHA.
Only this package's selected scope is sealed. The two live producer folders
can gain later events, and mutable cursors/scripts can change; no claim that
their entire future contents are sealed is made. Current raw control, queue,
progress and Native prefixes were read sequentially, not atomically. Initial
BASELINE_CHECKPOINT_RAW was reserialized; its original clarification and
separate exact-byte additive checkpoint copy are both preserved.

Original1007, repository execution99 and frozen Source35/36 each1111 were
hashed before and after; prior documentation inventories are unchanged.
No campaign source function, Native/model, checker replay, test, helper,
process/queue/lease mutation or Git command was executed by this producer.
Artifact consistency verification is not scientific certification.
'''
    (DEST/'README.md').write_bytes(README.encode('utf8'))
    (DEST/'.gitattributes').write_bytes(b'* -text\n** -text\n')
    write(DEST/'COPY_PROVENANCE.json',dict(schema='V42_FIXED_CAPTURE_EXACT_COPY_PROVENANCE_V1',UTC=utc(),
        producer_source_paths_fixed_at_UTC=start,original_selected_paths=len(original_paths),watch_selected_paths=len(watch_paths),
        source_producer_folders_can_append_later=True,source_folder_future_inventory_not_sealed=True,copies=provenance))
    files={p.relative_to(DEST).as_posix():record(p) for p in sorted(DEST.rglob('*')) if p.is_file()}
    inventory_record=write(DEST/'SHA_INVENTORY.json',dict(schema='V42_PACKAGE_SHA_INVENTORY_V1',UTC=utc(),
        files=files,inventory_self_excluded=True,scientific_PASS_claimed=False))
    for relative,ref in files.items():assert record(DEST/relative)==ref
    assert old_inventories==hashes(old_inventories)
    assert protected_after==dict(original1007=hashes(original),execution99=hashes(execution),frozen={v:hashes(paths) for v,paths in freezes.items()})
    immutable_receipts=[item for relative,item in captures.items() if relative.endswith(('EVENT_RECEIPT.json','OBSERVATION.json'))]
    for item in immutable_receipts:assert record(item['source']['path'])==item['source']
    mutable_source_status={relative:dict(source_at_capture=item['source'],source_at_seal=record(item['source']['path']),
        bytes_still_same=record(item['source']['path'])==item['source']) for relative,item in captures.items()
        if Path(relative).name in ('OBSERVED_EVENT_STATE.json','observe_events.py')}
    verification=dict(document_package_integrity_verified=True,scope='fixed raw-byte copy and event consistency only',
        UTC=utc(),package=str(DEST),inventory=inventory_record,review=review_record,files=len(files)+1,
        payload_bytes=sum(r['bytes'] for r in files.values()),exact_copy_count=len(provenance),
        original_fixed_scope_files=len(original_paths),watch_fixed_scope_files=len(watch_paths),
        prior_inventory_count=len(old_inventories),protected_original1007_execution99_D35_D36_each1111_start_end_same=True,
        mutable_producer_status_at_seal=mutable_source_status,producer_future_folder_immutability_claimed=False,
        Native_optimize_calls=0,model_constructions=0,checker_replays=0,tests=0,production_mutations=0,Git_mutations=0,
        scientific_PASS_claimed=False)
    verification_record=write(OUT/'SOURCE36_FIRST_ACTUAL_TRANSITIONS_DOC_PACKAGE_SEAL_VERIFICATION.json',verification)
    print(json.dumps(dict(verification=verification_record,inventory=inventory_record,review=review_record,
        files=verification['files'],payload_bytes=verification['payload_bytes'],copies=len(provenance),
        package=str(DEST)),ensure_ascii=False))

if __name__=='__main__':main()
