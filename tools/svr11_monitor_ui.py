"""Separately sealed read-only UI; scientific epoch files remain immutable."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import sys,subprocess

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic,read,record,now

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
    root=Path(root);m=read(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
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
        peers.append(dict(arm=r['arm'],day=r['day'],PID=r['worker']['PID'],phase=phase,
            optimization_status=solver_label(science) if r['arm']!='B0' else 'Native 0 · B0',
            Native_Runtime=v.get('Native_Runtime',v.get('native_runtime_seconds',v.get('measured_native_runtime',0))),
            UB=v.get('Best_Feasible_UB',v.get('verified_UB',v.get('UB',science.get('verified_UB',science.get('UB'))))),
            certified_LB=v.get('Certified_Global_LB',science.get('certified_Global_LB',science.get('LB'))),
            certified_Gap=science.get('certified_gap',v.get('Certified_Gap')) if science.get('global_gap_certified') else None,Fresh=fresh))
    policies=[];estimate=0.;known=True
    for arm in ORDER:
        axis=[r for r in rows if r['arm']==arm];p=dict(policy=arm,**{k:sum(r['status']==k for r in axis) for k in ('PASS','FAIL','RUNNING')})
        p['remaining']=31-p['PASS']-p['FAIL']-p['RUNNING'];policies.append(p)
        durations=[r['wall_seconds'] for r in axis if r.get('wall_seconds') is not None and r['status'] in ('PASS','FAIL')]
        if p['remaining']+p['RUNNING']:
            if durations:estimate+=(p['remaining']+p['RUNNING'])*statistics.median(durations)/m['worker_counts'][arm]
            else:known=False
    return dict(status=ledger['status'],policy=ledger.get('policy'),counts=counts,workers=peers,policies=policies,dates=rows,
        ETA=f'{estimate/3600:.1f} h' if known else '측정 중',
        errors=[r['arm']+' '+r['day']+': '+str(r.get('reason')) for r in rows if r['status']=='FAIL'][-3:]+([ledger['error']] if ledger.get('error') else []),
        source_SHA=m['execution_SHA'],root=str(root),UTC=now())

def serve(root):
    from v42_svr11.authority import verify
    from v42_svr11 import monitor
    verify(Path(root)/'CAMPAIGN_MANIFEST.json');verify_ui(root)
    # This substitution occurs only in this independent read-only HTTP process.
    # No running scientific process, Python source byte or model is modified.
    monitor.PAGE=(SOURCE/'assets/svr11_monitor.html').read_text(encoding='utf8')
    monitor.snapshot=snapshot
    monitor.serve(root,8796)

def watchdog(root,monitor_only=False):
    from v42_svr11 import watchdog as w
    verify_ui(root);original=w.launch
    def launch(module,campaign_root,extra=()):
        if module!='v42_svr11.monitor':return original(module,campaign_root,extra)
        with (Path(root)/'monitor_ui_STDOUT.log').open('ab') as log:
            return subprocess.Popen([sys.executable,'-B','-X','utf8',str(Path(__file__)),'serve',str(root)],cwd=SOURCE,
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    with patch.object(w,'launch',launch):return w.check(root,monitor_only=monitor_only)

if __name__=='__main__':
    mode,root=sys.argv[1:3]
    if mode=='release':atomic(Path(root)/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),
        scientific_source_unchanged=True,Native_calls=0,UTC=now()))
    elif mode=='serve':serve(root)
    elif mode=='watchdog':
        try:watchdog(root,'--monitor-only' in sys.argv)
        except PermissionError as error:
            if 'PROCESS_LEASE_ALREADY_OWNED' not in str(error):raise
    else:raise ValueError('UNKNOWN_UI_MODE')
