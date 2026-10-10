"""Exact source/root/PID/create-time adoption; live science is never killed."""
from pathlib import Path
import os,psutil
from v42_pr134_b1.common import read,process,atomic,now

def allowed_worker_cwds(code_root):
    """DSS Compile/Redirect transiently changes the OS cwd to audited assets."""
    from v42_common_campaign.authority import ROOT
    if Path(code_root).resolve()!=ROOT:
        raise PermissionError('SVR11_GLOBAL_WORKER_CODE_ROOT_DRIFT')
    from v42_regcontrol.authority import source
    assets=source()['assets']
    return {ROOT}|{Path(getattr(assets,key)).resolve().parent for key in ('master','pcc','ratings','phase_pv')}

def verify_worker_cwd(cwd,code_root):
    if Path(cwd).resolve() not in allowed_worker_cwds(code_root):
        raise PermissionError('SVR11_GLOBAL_WORKER_CHECKOUT_DRIFT')

def live(receipt):
    try:
        p=psutil.Process(receipt['PID'])
        return abs(p.create_time()-receipt['create_time'])<.01 and p.cmdline()==receipt['command'] and p.is_running()
    except (psutil.Error,KeyError):return False

def identity(p=None):
    p=p or psutil.Process()
    return dict(PID=p.pid,create_time=p.create_time(),command=p.cmdline(),cwd=p.cwd(),CPU_seconds=sum(p.cpu_times()[:2]),UTC=now())

def workers(root,source):
    found=[]
    for p in psutil.process_iter(['pid','name']):
        try:
            if (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
            args=p.cmdline();module=args[args.index('-m')+1] if '-m' in args else ''
            if module!='v42_svr11.worker':continue
            r=read(args[-1])
            if Path(r['root']).resolve()!=Path(root).resolve() or r['source_SHA']!=source:
                raise PermissionError('SVR11_GLOBAL_OTHER_EPOCH_WORKER_ACTIVE')
            verify_worker_cwd(p.cwd(),r['code_root'])
            found.append(dict(identity(p),arm=r['arm'],day=r['day'],worker_slot=r['worker_slot'],request=str(Path(args[-1]).resolve())))
        except psutil.Error:continue
    return found

def assert_peers(request):
    peers=workers(request['root'],request['source_SHA']);keys=set();slots=set()
    for p in peers:
        key=(p['arm'],p['day'])
        if key in keys or p['worker_slot'] in slots or p['arm']!=request['arm']:
            raise PermissionError('SVR11_GLOBAL_DUPLICATE_DAY_SLOT_OR_POLICY')
        keys.add(key);slots.add(p['worker_slot'])
    if len(peers)>(3 if request['arm']=='B2' else 1):raise PermissionError('SVR11_GLOBAL_WORKER_COUNT_EXCEEDED')
    for p in psutil.process_iter(['pid','name']):
        try:
            if p.pid==os.getpid() or (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
            args=p.cmdline();module=args[args.index('-m')+1] if '-m' in args else ''
            if module.endswith('.worker') and module.startswith(('v42_common_campaign','v42_autonomous_b','v42_may_campaign','v42_pr134_b1','v42_a_stage','v42_m1_')):
                raise PermissionError('SVR11_GLOBAL_HISTORICAL_SCIENTIFIC_WORKER_ACTIVE:'+str(p.pid))
        except psutil.Error:continue
    return peers

