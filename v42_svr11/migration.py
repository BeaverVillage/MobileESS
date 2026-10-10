"""Drain the immutable predecessor without killing science; start one new epoch."""
from pathlib import Path
import sys,subprocess,psutil
from v42_pr134_b1.common import read,record,sha,atomic,now
from v42_common_campaign.authority import ROOT,singleton
from .authority import verify
from .processes import live,identity,allowed_worker_cwds

def predecessors(root,m):
    if record(root/'PREDECESSOR_DRAIN_CONTRACT.json')!=m['predecessor_drain_contract']:
        raise PermissionError('SVR11_GLOBAL_PREDECESSOR_CONTRACT_DRIFT')
    receipt=read(root/'PREDECESSOR_DRAIN_CONTRACT.json')
    oldpath=Path(receipt['manifest']['path'])
    if record(oldpath)!=receipt['manifest']:
        raise PermissionError('SVR11_GLOBAL_PREDECESSOR_MANIFEST_DRIFT')
    old=read(oldpath);oldroot=Path(old['root']).resolve();oldcode=Path(old['code_root']).resolve()
    if 'monitor_manifest' in receipt and record(receipt['monitor_manifest']['path'])!=receipt['monitor_manifest']:
        raise PermissionError('SVR11_GLOBAL_PREDECESSOR_MONITOR_MANIFEST_DRIFT')
    quiescence=None
    if 'dispatch_quiescence' in receipt:
        q=receipt['dispatch_quiescence']
        if record(q['path'])!=q:raise PermissionError('SVR11_GLOBAL_DISPATCH_QUIESCENCE_DRIFT')
        quiescence=read(q['path'])
        if (Path(quiescence['root']).resolve()!=oldroot or quiescence['source_SHA']!=old['execution_SHA']
            or not quiescence.get('new_dispatch_quiesced') or quiescence['worker_terminated']!=0):
            raise PermissionError('SVR11_GLOBAL_DISPATCH_QUIESCENCE_BINDING_DRIFT')
    if old['execution_SHA']!=receipt['source_SHA'] or oldroot==root or oldcode==ROOT:
        raise PermissionError('SVR11_GLOBAL_PREDECESSOR_BINDING_DRIFT')
    # Validate predecessor byte identity without executing its frozen buggy guard.
    for name,expected in old['execution_sources'].items():
        if sha(oldcode/name)!=expected:
            raise PermissionError('SVR11_GLOBAL_PREDECESSOR_SOURCE_DRIFT')
    found=[];old_supervisors=[]
    asset_cwds=allowed_worker_cwds(ROOT)-{ROOT}
    for p in psutil.process_iter(['pid','name']):
        try:
            if (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
            args=p.cmdline();module=args[args.index('-m')+1] if '-m' in args else ''
            if module=='v42_svr11.controller' and Path(args[-1]).resolve()==oldroot:
                me=identity(p)
                quiesced=bool(quiescence and live(quiescence['process']) and p.pid==quiescence['process']['PID'])
                old_supervisors.append(dict(me,dispatch_quiesced=quiesced));continue
            if module!='v42_svr11.worker':continue
            r=read(args[-1]);rroot=Path(r['root']).resolve()
            if rroot==root and r['source_SHA']==m['execution_SHA']:continue
            if rroot!=oldroot or r['source_SHA']!=old['execution_SHA'] or Path(r['code_root']).resolve()!=oldcode:
                raise PermissionError('SVR11_GLOBAL_UNRELATED_WORKER_ACTIVE_DURING_MIGRATION')
            if Path(p.cwd()).resolve() not in {oldcode}|asset_cwds:
                raise PermissionError('SVR11_GLOBAL_PREDECESSOR_WORKER_CHECKOUT_DRIFT')
            found.append(dict(identity(p),arm=r['arm'],day=r['day'],request=record(args[-1])))
        except psutil.Error:continue
    return receipt,old,found,old_supervisors

def check(root,monitor_only=False):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json')
    with singleton(root/'MIGRATION.lock'):
        receipt,old,peers,supervisors=predecessors(root,m)
        dispatchers=[p for p in supervisors if not p.get('dispatch_quiesced')]
        status='WAITING_PREDECESSOR_DRAIN' if peers or dispatchers else 'PREDECESSOR_DRAIN_COMPLETE'
        state=dict(schema='SVR11_SAFE_EPOCH_MIGRATION_V1',status=status,source_SHA=m['execution_SHA'],root=str(root),
            predecessor_manifest=receipt['manifest'],predecessor_source_SHA=old['execution_SHA'],
            predecessor_monitor_manifest=receipt.get('monitor_manifest',receipt['manifest']),
            predecessor_workers=peers,predecessor_supervisors=supervisors,
            healthy_workers_terminated=0,scientific_results_promoted=0,UTC=now())
        atomic(root/'MIGRATION_STATUS.json',state)
        if peers or dispatchers:return state
        oldroot=Path(old['root']);isolated=oldroot/'SOURCE_EPOCH_SUCCESSOR_ISOLATION.json'
        if not isolated.exists():
            results=[record(p) for p in sorted((oldroot/'dates').rglob('RESULT.json'))]
            atomic(isolated,dict(state,reason='Classifier and transient DSS cwd guard corrected in immutable successor',
                old_ledger=record(oldroot/'CAMPAIGN_LEDGER.json'),all_prior_results=results,
                original_results_and_ledger_preserved=True,new_epoch_all_124_recalculated=False,
                qualified_completed_dates_reused=True))
        # Only the obsolete read-only HTTP process is stopped after workers drain.
        monitor_root=Path(read(state['predecessor_monitor_manifest']['path'])['root'])
        mp=monitor_root/'MONITOR_PROCESS.json';monitor=read(mp) if mp.exists() else {}
        if live(monitor):
            command=monitor['command']
            if not any('svr11_monitor_ui.py' in a or a=='v42_svr11.monitor' for a in command):
                raise PermissionError('SVR11_GLOBAL_PREDECESSOR_MONITOR_IDENTITY_DRIFT')
            psutil.Process(monitor['PID']).terminate()
            try:psutil.Process(monitor['PID']).wait(timeout=10)
            except psutil.NoSuchProcess:pass
        script=ROOT/'tools/svr11_monitor_ui.py'
        ui=read(root/'MONITOR_UI_RELEASE.json')
        if ui['files']!=[record(script),record(ROOT/'assets/svr11_monitor.html')]:
            raise PermissionError('SVR11_GLOBAL_MIGRATION_UI_RELEASE_DRIFT')
        args=[sys.executable,'-B','-X','utf8',str(script),'watchdog',str(root)]
        if monitor_only:args.append('--monitor-only')
        subprocess.run(args,cwd=ROOT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        state.update(status='SUCCESSOR_WATCHDOG_INVOKED',predecessor_isolation=record(isolated),UTC=now())
        atomic(root/'MIGRATION_STATUS.json',state)
        return state

if __name__=='__main__':
    try:check(sys.argv[1],'--monitor-only' in sys.argv)
    except PermissionError as error:
        if 'PROCESS_LEASE_ALREADY_OWNED' not in str(error):raise
