"""Idempotent ownership check/recovery. Never kill a healthy worker."""
from pathlib import Path
import sys,subprocess,urllib.request
from v42_pr134_b1.common import read,atomic,now
from v42_common_campaign.authority import ROOT,singleton
from .authority import verify
from .processes import live,identity,workers

def launch(module,root,extra=()):
    root=Path(root);log=root/(module.rsplit('.',1)[-1]+'_STDOUT.log')
    with log.open('ab') as stream:
        return subprocess.Popen([sys.executable,'-B','-X','utf8','-m',module,str(root),*extra],cwd=ROOT,
            stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def check(root,port=8796,monitor_only=False):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json');actions=[]
    with singleton(root/'WATCHDOG.lock'):
        supervisor_path=root/'SUPERVISOR_PROCESS.json';supervisor=read(supervisor_path) if supervisor_path.exists() else {}
        ledger=read(root/'CAMPAIGN_LEDGER.json') if (root/'CAMPAIGN_LEDGER.json').exists() else {}
        # Process liveness, command, create time and source determine adoption;
        # elapsed Native time or stale timestamp alone never permits termination.
        if not monitor_only and not live(supervisor) and ledger.get('status')!='COMPLETE':
            if ledger.get('status')=='GLOBAL_SYSTEM_ERROR':
                actions.append('GLOBAL_SYSTEM_ERROR_REQUIRES_DIAGNOSIS; healthy workers preserved')
            else:
                # Close launch/receipt window with actual module+root inventory.
                import psutil
                owned=[]
                for p in psutil.process_iter(['pid','name']):
                    try:
                        args=p.cmdline()
                        if '-m' in args and args[args.index('-m')+1]=='v42_svr11.controller' and Path(args[-1]).resolve()==root:
                            if Path(p.cwd()).resolve()!=ROOT:raise PermissionError('SVR11_GLOBAL_SUPERVISOR_CHECKOUT_DRIFT')
                            owned.append(identity(p))
                    except psutil.Error:continue
                if len(owned)>1:raise PermissionError('SVR11_GLOBAL_DUPLICATE_SUPERVISOR')
                if owned:
                    atomic(supervisor_path,dict(owned[0],root=str(root),source_SHA=m['execution_SHA']));actions.append('ADOPTED_SUPERVISOR')
                else:
                    p=launch('v42_svr11.controller',root);actions.append('STARTED_SUPERVISOR:'+str(p.pid))
        monitor_path=root/'MONITOR_PROCESS.json';monitor=read(monitor_path) if monitor_path.exists() else {}
        if not live(monitor):
            p=launch('v42_svr11.monitor',root,('--port',str(port)));actions.append('STARTED_MONITOR:'+str(p.pid))
        peers=workers(root,m['execution_SHA'])
        value=dict(schema='V42_SVR11_WATCHDOG_RECEIPT_V1',root=str(root),source_SHA=m['execution_SHA'],UTC=now(),actions=actions,
            supervisor=supervisor,active_workers=peers,healthy_workers_terminated=0,Native_ledger_reset=0)
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state',timeout=5) as response:
                import json
                actual=json.load(response);value.update(monitor_HTTP=response.status,monitor_source_SHA=actual['source_SHA'])
                if actual['source_SHA']!=m['execution_SHA']:raise PermissionError('SVR11_GLOBAL_MONITOR_EPOCH_DRIFT')
        except (OSError,ValueError) as error:value['monitor_HTTP_error']=repr(error)
        atomic(root/'WATCHDOG_LAST_RUN.json',value);return value

if __name__=='__main__':
    try:check(sys.argv[1],monitor_only='--monitor-only' in sys.argv[2:])
    except PermissionError as error:
        if 'PROCESS_LEASE_ALREADY_OWNED' not in str(error):raise
