"""Separately sealed read-only UI; scientific epoch files remain immutable."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import sys,subprocess

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic,read,record,now

def dispatch_quiesced(root):
    root=Path(root);path=root/'DISPATCH_QUIESCENCE_FOR_PLANNING_MODEL_REPAIR.json'
    if not path.exists():return False
    q=read(path);m=read(root/'CAMPAIGN_MANIFEST.json')
    if Path(q['root']).resolve()!=root.resolve() or q['source_SHA']!=m['execution_SHA']:
        raise PermissionError('READ_ONLY_DISPATCH_QUIESCENCE_BINDING_DRIFT')
    return q.get('new_dispatch_quiesced') is True

_observed={}
def display_ledger(root):
    """Read terminated own results while preserving the suspended old ledger."""
    root=Path(root);ledger=read(root/'CAMPAIGN_LEDGER.json')
    if not dispatch_quiesced(root):return ledger
    from v42_svr11.processes import live
    m=read(root/'CAMPAIGN_MANIFEST.json')
    for row in ledger['dates'].values():
        if row['status']!='RUNNING' or live(row.get('worker',{})):continue
        request=read(row['request']);path=Path(request['result'])
        if not path.exists():continue
        key=(str(path),path.stat().st_mtime_ns,path.stat().st_size)
        if key not in _observed:_observed[key]=read(path)
        result=_observed[key]
        if result['source_SHA']!=m['execution_SHA'] or (result['day'],result['arm'])!=(row['day'],row['arm']):
            raise PermissionError('READ_ONLY_FINAL_RESULT_BINDING_DRIFT')
        row.update(recorded_ledger_status=row['status'],status=result['status'],
            observed_terminated_result=str(path),observed_result_source_SHA=result['source_SHA'],
            metrics=result.get('metrics',{}),reason=result.get('reason'),Native_Runtime=result.get('Native_Runtime'),
            wall_seconds=result.get('wall_seconds'),optimization_status=result.get('optimization_status'),AC_status=result.get('AC_status'))
    ledger.update(status='배정 중지 · Planning 모델 검증 중',intentional_dispatch_quiescence=True)
    return ledger

def ui_files():
    return [record(Path(__file__)),record(SOURCE/'assets/svr11_monitor.html')]

def verify_ui(root):
    r=read(Path(root)/'MONITOR_UI_RELEASE.json')
    if r['files']!=ui_files():raise PermissionError('READ_ONLY_MONITOR_UI_RELEASE_DRIFT')
    return r

def snapshot(root):
    # Worker heartbeat already includes the Fresh slot. Do not open the
    # physics writer's unretried *_PROGRESS.json files from this read-only UI.
    import statistics
    from v42_svr11 import ORDER
    from v42_svr11.processes import live
    from v42_svr11.anytime import solver_label
    root=Path(root);m=read(root/'CAMPAIGN_MANIFEST.json');ledger=display_ledger(root)
    rows=list(ledger['dates'].values());counts={k:sum(r['status']==k for r in rows) for k in ('PASS','FAIL','RUNNING','NOT_EXECUTED')}
    counts['completed']=counts['PASS']+counts['FAIL'];peers=[]
    for r in rows:
        if r['status']!='RUNNING' or not live(r.get('worker',{})):continue
        request=read(r['request']);path=Path(request['progress']);v=read(path) if path.exists() else {}
        science=v;results=[]
        for name in ('A_RESULT.json','M_STAGE_RESULT.json','COMMON_MESS_RESULT.json'):
            for f in Path(request['output']).rglob(name):results.append((f.stat().st_mtime,f))
        if results:science=read(max(results,key=lambda item:item[0])[1])
        phase=v.get('phase','STARTING');stage=v.get('stage')
        if stage:phase=str(stage)+' · '+phase
        fresh='대기'
        if v.get('active_OpenDSS_trajectory'):
            fresh=str(v['active_OpenDSS_trajectory'])+' '+str(v.get('OpenDSS_slot',0))+'/96'
            phase=str(v['active_OpenDSS_trajectory'])+' · Fresh AC'
        if phase=='SVR11_FORECAST_MODEL_GENERATION':phase+=' '+str(v.get('model_slot',0))+'/96'
        if len(r.get('attempts',[]))>1:phase=f"재시도 {len(r['attempts'])} · "+phase
        peers.append(dict(arm=r['arm'],day=r['day'],PID=r['worker']['PID'],phase=phase,
            optimization_status=solver_label(science) if r['arm']!='B0' else 'Native 0 · B0',
            Native_Runtime=v.get('Native_Runtime',v.get('native_runtime_seconds',v.get('measured_native_runtime',0))),
            UB=v.get('Best_Feasible_UB',v.get('verified_UB',v.get('UB',science.get('verified_UB',science.get('UB'))))),
            certified_LB=v.get('Certified_Global_LB',science.get('certified_Global_LB',science.get('LB'))),
            certified_Gap=science.get('certified_gap',v.get('Certified_Gap')) if science.get('global_gap_certified') else None,Fresh=fresh))
    migration=read(root/'MIGRATION_STATUS.json') if (root/'MIGRATION_STATUS.json').exists() else {}
    if migration.get('status')=='WAITING_PREDECESSOR_DRAIN':
        for old in migration['predecessor_workers']:
            if not live(old):continue
            request=read(old['request']['path']);path=Path(request['progress']);v=read(path) if path.exists() else {}
            phase=v.get('phase','RUNNING')
            if phase=='SVR11_FORECAST_MODEL_GENERATION':phase+=' '+str(v.get('model_slot',0))+'/96'
            peers.append(dict(arm='이전 Epoch '+old['arm'],day=old['day'],PID=old['PID'],
                phase='기존 작업 자연 종료 대기 · '+phase,
                optimization_status=solver_label(v),Native_Runtime=v.get('Native_Runtime',0),UB=None,
                certified_LB=None,certified_Gap=None,Fresh='이전 Source · 새 공식 결과에 합산하지 않음'))
    policies=[];estimate=0.;known=True
    for arm in ORDER:
        axis=[r for r in rows if r['arm']==arm];p=dict(policy=arm,**{k:sum(r['status']==k for r in axis) for k in ('PASS','FAIL','RUNNING')})
        p['remaining']=31-p['PASS']-p['FAIL']-p['RUNNING'];policies.append(p)
        durations=[r['wall_seconds'] for r in axis if r.get('wall_seconds') is not None and r['status'] in ('PASS','FAIL')]
        if p['remaining']+p['RUNNING']:
            if durations:estimate+=(p['remaining']+p['RUNNING'])*statistics.median(durations)/m['worker_counts'][arm]
            else:known=False
    errors=[]
    for r in rows:
        for old in r.get('terminal_history',[]):
            if old.get('status')=='FAIL':
                recovery='재시도 중' if r['status']=='RUNNING' else '복구됨' if r['status']=='PASS' else '보존된 이전 시도'
                errors.append(r['arm']+' '+r['day']+' ('+recovery+'): '+str(old.get('reason')))
        if r['status']=='FAIL':errors.append(r['arm']+' '+r['day']+': '+str(r.get('reason')))
    if ledger.get('error'):errors.append(ledger['error'])
    batch=ledger.get('B3_batch',{})
    return dict(status=ledger['status'],policy=ledger.get('policy'),counts=counts,workers=peers,policies=policies,dates=rows,
        B3_stage=batch.get('stage'),B3_stage_completed=batch.get('completed_dates_in_stage'),B3_memory=batch.get('memory'),
        intentional_dispatch_quiescence=bool(ledger.get('intentional_dispatch_quiescence')),
        ETA='검증 완료 후 재산정' if ledger.get('intentional_dispatch_quiescence') else f'{estimate/3600:.1f} h' if known else '측정 중',
        errors=errors[-3:],
        source_SHA=m['execution_SHA'],root=str(root),UTC=now(),
        notice=('검증된 완료 날짜 '+str(sum(bool(r.get('reused')) for r in rows))+'일 재사용 · 원본 실행 SHA/Runtime 보존 · 현재 검증 SHA 별도 기록. '
            if any(r.get('reused') for r in rows) else '')+(
            'May19–22 네 날짜는 원본 NormalAmps·kVA·전압·SVR 정격 재검증 PASS. 기존 오판정 이력은 보존합니다.'
            if (root/'NORMALAMPS_CLASSIFICATION_CORRECTION.json').exists() else ''))

def serve(root):
    from v42_svr11.authority import verify
    from v42_svr11 import monitor
    verify(Path(root)/'CAMPAIGN_MANIFEST.json');verify_ui(root)
    # This substitution occurs only in this independent read-only HTTP process.
    # No running scientific process, Python source byte or model is modified.
    monitor.PAGE=(SOURCE/'assets/svr11_monitor.html').read_text(encoding='utf8')
    monitor.snapshot=snapshot
    original_read=monitor.read
    monitor.read=lambda path:display_ledger(root) if Path(path).resolve()==(Path(root)/'CAMPAIGN_LEDGER.json').resolve() else original_read(path)
    monitor.serve(root,8796)

def watchdog(root,monitor_only=False):
    monitor_only=monitor_only or dispatch_quiesced(root)
    from v42_svr11 import watchdog as w
    verify_ui(root);original=w.launch
    def launch(module,campaign_root,extra=()):
        if module!='v42_svr11.monitor':return original(module,campaign_root,extra)
        with (Path(root)/'monitor_ui_STDOUT.log').open('ab') as log:
            return subprocess.Popen([sys.executable,'-B','-X','utf8',str(Path(__file__)),'serve',str(root)],cwd=SOURCE,
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    with patch.object(w,'launch',launch):return w.check(root,monitor_only=monitor_only)

def safeguard(root,monitor_only=False):
    monitor_only=monitor_only or dispatch_quiesced(root)
    # Scheduling calls the frozen scientific migration gate. While old science
    # drains, recover only the independent successor HTTP process.
    from v42_svr11.migration import check
    from v42_svr11.processes import live
    from v42_common_campaign.authority import singleton
    import psutil
    root=Path(root);verify_ui(root)
    # Proven lifetime-only successor changes may reuse complete predecessor
    # dates. Audit before the immutable migration can dispatch fresh Workers.
    m=read(root/'CAMPAIGN_MANIFEST.json')
    predecessor=read(m['predecessor_drain_contract']['path'])
    if (predecessor.get('qualified_completed_dates_reused',True) and
        m.get('model_probe_context_retirement')=='EXACT_COMPLETED_OWNER_AND_FINALIZED_CALLBACK_REGISTRY_DETACH_CFFI_GC'):
        from reuse_svr11_completed import admit_before_first_dispatch
        admit_before_first_dispatch(root)
    state=check(root,monitor_only)
    if state['status']!='WAITING_PREDECESSOR_DRAIN':return state
    with singleton(root/'MONITOR_RECOVERY.lock'):
        current=read(root/'MONITOR_PROCESS.json') if (root/'MONITOR_PROCESS.json').exists() else {}
        if live(current):return state
        oldroot=Path(read(state.get('predecessor_monitor_manifest',state['predecessor_manifest'])['path'])['root'])
        old=read(oldroot/'MONITOR_PROCESS.json') if (oldroot/'MONITOR_PROCESS.json').exists() else {}
        if live(old):
            if not any('svr11_monitor_ui.py' in a or a=='v42_svr11.monitor' for a in old['command']):
                raise PermissionError('READ_ONLY_PREDECESSOR_MONITOR_IDENTITY_DRIFT')
            p=psutil.Process(old['PID']);p.terminate();p.wait(timeout=10)
        with (root/'monitor_ui_STDOUT.log').open('ab') as log:
            subprocess.Popen([sys.executable,'-B','-X','utf8',str(Path(__file__)),'serve',str(root)],cwd=SOURCE,
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return state

if __name__=='__main__':
    mode,root=sys.argv[1:3]
    if mode=='release':atomic(Path(root)/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),
        scientific_source_unchanged=True,Native_calls=0,UTC=now()))
    elif mode=='serve':serve(root)
    elif mode=='watchdog':
        try:watchdog(root,'--monitor-only' in sys.argv)
        except PermissionError as error:
            if 'PROCESS_LEASE_ALREADY_OWNED' not in str(error):raise
    elif mode=='safeguard':
        try:safeguard(root,'--monitor-only' in sys.argv)
        except PermissionError as error:
            if 'PROCESS_LEASE_ALREADY_OWNED' not in str(error):raise
    else:raise ValueError('UNKNOWN_UI_MODE')
