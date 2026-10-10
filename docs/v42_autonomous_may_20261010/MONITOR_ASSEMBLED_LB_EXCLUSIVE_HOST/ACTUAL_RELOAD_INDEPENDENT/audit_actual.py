"""Read-only saved evidence, process, socket and HTTP audit; no model imports."""
from pathlib import Path
from datetime import datetime,timezone
from fractions import Fraction
import hashlib,json,math,traceback,urllib.request
import psutil

ROOT=Path('D:/v42_may_restart_20261010_02');HERE=Path(__file__).resolve().parent
SCIENCE='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
def rec(path):
    path=Path(path);h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=h.hexdigest())
def read(path):return json.loads(Path(path).read_bytes())
def copy(path,name):
    path=Path(path);out=HERE/name;assert not out.exists();out.write_bytes(path.read_bytes())
    return rec(out)
def identity(pid):
    p=psutil.Process(pid)
    return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def exact(saved):
    now=rec(saved['path']);assert now['bytes']==saved['bytes'] and now['sha256']==saved['sha256'];return now
def save(name,value):
    path=HERE/name;assert not path.exists();path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');return rec(path)

r=dict(PASS=False,UTC=datetime.now(timezone.utc).isoformat(),Native_optimize_calls=0,model_constructions=0,
       model_or_case_or_scientific_matrix_imports=0,process_mutations=0,helper_executions=0,queue_or_controller_mutations=0,
       final_scientific_PASS_claimed=False)
try:
    producer=ROOT/'autonomous/MONITOR_ASSEMBLED_LB_RELOAD_VERIFICATION.json'
    assert rec(producer)['sha256']=='2ddf814f6e276d9fec51d87ae1b2a30373b0fd747e687e511d16428622d96034'
    verification=read(producer);assert verification['PASS'] is True
    before_rec=exact(verification['before']);before=read(before_rec['path'])
    assert verification['verification_continued_read_only_after_helper03_stale_metadata_psutil_NoSuchProcess'] is True
    assert verification['continuation_helper_process_mutations']==0
    assert verification['scientific_worker_terminate_calls']==verification['supervisor_terminate_calls']==verification['Native_optimize_calls']==verification['model_constructions']==0
    failure=ROOT/'autonomous/MONITOR_ASSEMBLED_LB_RELOAD_METADATA_RACE_FAILURE_03.json'
    assert rec(failure)['sha256']=='d4c3f2dfebdc76e759793995f745e4d5d5a30bcbe7f3eaac448a82fa65d82701'
    assert rec(ROOT/'autonomous/verify_owned_monitor_assembled_lb_04.py')['sha256']=='535f91b42a1c6991a90bfa165185f2490662537d34929a7a4c8e0f636aa3d055'
    rawrefs=dict(producer=copy(producer,'PRODUCER_VERIFICATION_EXACT_COPY.json'),
                 before=copy(before_rec['path'],'PRODUCER_BEFORE_EXACT_COPY.json'),
                 failure03=copy(failure,'PRODUCER_METADATA_RACE_FAILURE03_EXACT_COPY.json'))
    host=identity(105976);assert host==verification['monitor']
    assert read(ROOT/'AUTONOMOUS_MONITOR_SERVER.json')['process']=={k:v for k,v in host.items() if k!='cwd'}
    listeners=[dict(PID=c.pid,address=list(c.laddr),status=c.status) for c in psutil.net_connections(kind='inet')
               if c.status=='LISTEN' and c.laddr.port==8794]
    assert {c['PID'] for c in listeners}=={105976}
    assert set(before['monitors'])=={'7340','102084'}
    assert not any(psutil.pid_exists(pid) for pid in (7340,102084))
    supervisor=identity(107788);assert supervisor==before['supervisor']==verification['supervisor']
    cpraw=(ROOT/'SUPERVISOR_STATE.json').read_bytes();cp=json.loads(cpraw)
    rawrefs['checkpoint']=save('CURRENT_CHECKPOINT_READONLY_SNAPSHOT.json',cp)
    expectedkeys={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
    assert set(before['workers'])==set(cp['workers'])==expectedkeys
    observations={}
    for key,saved in before['workers'].items():
        proc=identity(saved['process']['PID']);assert proc==saved['process']
        current=cp['workers'][key]
        assert current['PID']==proc['PID'] and current['created']==proc['created'] and current['command']==proc['command']
        requestrecord=exact(saved['request']);request=read(requestrecord['path'])
        assert Path(current['request']).resolve()==Path(requestrecord['path']).resolve()
        assert Path(proc['cwd']).resolve()==Path('D:/v42run35')
        assert request['implementation_SHA']==SCIENCE and request['previous_attempts']==[] and request['native_budget_seconds']==5400
        assert request['arm']=='B2' and key=='B2/'+request['day']
        baseline=read(exact(saved['ledger_snapshot'])['path']);rawrefs[key+'_baseline']=copy(saved['ledger_snapshot']['path'],key.replace('/','_')+'_BASELINE_NATIVE_EXACT_COPY.json')
        ledgraw=Path(saved['original_ledger']).read_bytes();ledger=json.loads(ledgraw)
        path=HERE/(key.replace('/','_')+'_CURRENT_NATIVE_RAW.json');assert not path.exists();path.write_bytes(ledgraw)
        rawrefs[key+'_current']=rec(path)
        assert ledger['calls'][:len(baseline['calls'])]==baseline['calls']
        assert ledger['measured_Native_Runtime']>=saved['measured_Native_Runtime']
        assert ledger['P2_calls']==0 and ledger['Native_ceiling_seconds']==5400
        observations[key]=dict(process=proc,request=requestrecord,attempt=request['attempt_id'],
            source=SCIENCE,completed_native_prefix_calls=len(baseline['calls']),current_completed_calls=len(ledger['calls']),
            current_measured_Native_Runtime=ledger['measured_Native_Runtime'],prefix_preserved=True,inflight=ledger.get('inflight'))
    sources=[exact(item) for item in before['sources']]
    assert sources==verification['sources']
    lease=read(ROOT/'REPAIR_LEASE.json');assert lease['token']==verification['lease_token'] and lease['state']=='RELEASED'
    with urllib.request.urlopen('http://127.0.0.1:8794/api/status',timeout=5) as response:
        assert response.status==200;api_raw=response.read()
    api=json.loads(api_raw);api_path=HERE/'CURRENT_API_STATUS_RAW.json';assert not api_path.exists();api_path.write_bytes(api_raw);rawrefs['API']=rec(api_path)
    assert api['supervisor_alive'] is True and api['live_worker_count']==3
    rows=api['rows'][:3];assert {row['day'] for row in rows}=={'2025-05-01','2025-05-02','2025-05-03'}
    bounds=[]
    for row in rows:
        key='B2/'+row['day'];worker=row['B2'];obs=observations[key]
        assert worker['source_SHA']==SCIENCE and worker['current_attempt']==obs['attempt']
        bound=worker['bounds'];assert bound['status']=='CERTIFIED' and bound['scope']=='ORIGINAL_FULL_GLOBAL'
        assert bound['LB']>0 and worker['error'] is None
        req=read(obs['request']['path']);output=Path(req['output']).resolve()
        case=read(output/'SCIENTIFIC_CASE_IDENTITY.json');assert case['day']==row['day'] and case['arm']=='B2'
        ub=bound['evidence']['UB'];lb=bound['evidence']['LB']
        assert lb['schema']=='CURRENT_ASSEMBLED_ORIGINAL_EXACT_LB'
        for item in (ub,lb):
            assert Path(item['path']).resolve().is_relative_to(output)
            assert rec(item['path'])['sha256']==item['sha256']
        lower=read(lb['path']);upper=read(ub['path']);cert=lower['independent_exact_certificate']
        assert lower['PASS'] is True and cert['PASS'] is True and upper['PASS'] is True
        assert lower['case_sha']==cert['case_sha']==upper['case_sha']==case['case_sha']
        assert lower['scope']=='FULL_ORIGINAL_C3A_SIGNED_LAGRANGIAN_LP_DUAL'
        assert cert['status']=='EXACT_STORED_RATIONAL_BOUND_CERTIFIED' and cert['original_checker_byte_preserved'] is True
        assert lower['native_rounded_price_objectives_used_as_proof'] is False
        assert lower['restricted_master_objective_used_as_Global_LB'] is False and lower['Native_MIP_ObjBound_used_as_exact_Global_LB'] is False
        assert lower['Native_optimize_calls']==0 and cert['native_objective_used'] is False and cert['native_BestBd_used'] is False
        U=Fraction(ub['exact']);L=Fraction(lb['exact']);assert U>0 and L<=U
        assert L==Fraction(lower['exact_Global_LB'])==Fraction(cert['exact_bound'])
        assert math.isclose(bound['gap'],float((U-L)/abs(U)),rel_tol=0,abs_tol=1e-15)
        frontier=read(output/'frontier/CURRENT_CERTIFIED_STATE.json')
        assert frontier['case_sha']==case['case_sha'] and Fraction(frontier['exact_UB'])<=U and Fraction(frontier['exact_LB'])>=L
        bounds.append(dict(day=row['day'],attempt=obs['attempt'],source=SCIENCE,UB=bound['UB'],LB=bound['LB'],gap=bound['gap'],
                           status='CERTIFIED',case_sha=case['case_sha'],LB_receipt=rec(lb['path']),UB_receipt=rec(ub['path']),
                           exact_UB=str(U),exact_LB=str(L),exact_gap=str((U-L)/abs(U)),live_frontier_may_have_advanced=True))
    freeze=read(ROOT/'autonomous/V35_SPARSE_IMMUTABLE_FREEZE.json')
    frozen=[exact(item) for item in freeze['source_files']];assert len(frozen)==1111
    rawrefs['frozen_source_records']=save('FROZEN35_ALL1111_CURRENT_SOURCE_RECORDS.json',frozen)
    os_snapshot=save('CURRENT_OS_READONLY_SNAPSHOT.json',dict(UTC=datetime.now(timezone.utc).isoformat(),monitor=host,listeners=listeners,
                     prior_display_PIDs_absent=[7340,102084],supervisor=supervisor,workers=observations,lease=lease,sources=sources))
    r.update(PASS=True,producer=rec(producer),before=before_rec,raw_refs=rawrefs,OS_snapshot=os_snapshot,monitor=host,
             only_listener105976=True,supervisor107788_unchanged=True,exact_three_science_workers_and_requests_unchanged=True,
             completed_Native_prefixes_preserved=True,current_rows=bounds,lease_released=True,all1111_frozen_source_SHAs_match=True,
             exact_helper03_failure_preserved=rec(failure),helper03_outcome='EXIT1_AFTER_TWO_DISPLAY_TERMINATIONS_AND_REPLACEMENT_LAUNCH_OLD7340_METADATA_NoSuchProcess',
             helper04_outcome='READ_ONLY_CONTINUATION_PASS_NO_ADDITIONAL_PROCESS_MUTATIONS',
             failure03_traceback_provenance='Root copied actual tool output verbatim; not claimed redirected OS raw-stderr file',
             limitations=['Existing certified receipt/hash/source/current-case/exact-bound verification only; no fresh matrix checker replay.',
                          'Saved/current display gaps exceed3%; Actual/Fresh/final scientific PASS remains unproved.','No GUI rendering verification.'])
except BaseException as error:r.update(error=repr(error),traceback=traceback.format_exc())
path=HERE/'MONITOR_EXCLUSIVE_HOST_ACTUAL_RELOAD_INDEPENDENT_READONLY_AUDIT.json'
assert not path.exists();path.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=rec(path),error=r.get('error'),rows=r.get('current_rows')),indent=2))
raise SystemExit(0 if r['PASS'] else 1)
