"""User-authorized verification-only gate override; native science frozen."""
import ast,hashlib,json,os,sys,threading,time
from pathlib import Path
import psutil
_clock=time.perf_counter
ROOT=Path.cwd();sys.path.insert(0,str(ROOT));OUT=ROOT/'docs/v42_m1_certified_arc_lp_floor_and_threshold_cg'
LANE=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/v42_may_campaign_orchestrator_pr')
FORBIDDEN=('gurobipy','opendssdirect','dss','v42_native','v42_dw_','v42_benders')
observations=[];events=[];active=[None];done=threading.Event();failure=[]
def static_mock_audit():
    files=sorted((LANE/'v42_orchestrator').glob('*.py'))+sorted((LANE/'tests/v42_orchestrator').glob('*.py'))
    assert files
    hashes={}
    for p in files:
        data=p.read_bytes();tree=ast.parse(data.decode('utf8'));hashes[p.relative_to(LANE).as_posix()]=hashlib.sha256(data).hexdigest()
        for n in ast.walk(tree):
            imports=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module or ''] if isinstance(n,ast.ImportFrom) else []
            assert not any(v.startswith(FORBIDDEN) for v in imports),str(p)
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):assert n.func.attr not in ('optimize','Optimize','Solve'),str(p)
    return hashes
def inline_readonly(code):
    try:tree=ast.parse(code)
    except SyntaxError:return False
    imports={'json','hashlib','subprocess','pathlib','os','sys'}
    calls={'Path','str','int','bool','list','dict','set','tuple','len','all','any','print','range','enumerate','zip','sum'}
    methods={'loads','read_text','read_bytes','sha256','hexdigest','items','keys','values','splitlines','startswith','as_posix','resolve','is_file','exists'}
    for n in ast.walk(tree):
        if isinstance(n,ast.Import) and any(a.name not in imports for a in n.names):return False
        if isinstance(n,ast.ImportFrom) and n.module not in imports:return False
        if isinstance(n,ast.Call):
            if isinstance(n.func,ast.Name) and n.func.id not in calls:return False
            if isinstance(n.func,ast.Attribute) and n.func.attr not in methods:
                if not (isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='check_output'):return False
                if not n.args or not isinstance(n.args[0],ast.List):return False
                args=n.args[0].elts
                if len(args)<2 or not all(isinstance(a,ast.Constant) for a in args[:2]) or args[0].value!='git' or args[1].value not in ('show','diff','status','rev-parse','ls-files','cat-file','ls-remote'):return False
    return True

def classify():
    rows=[];blocked=[]
    # Read command lines only for candidates; system-wide command-line queries
    # needlessly interfere with bounded native fixture timing.
    for p in psutil.process_iter(['pid','ppid','name']):
        if p.pid==os.getpid() or not any(t in (p.info['name'] or '').lower() for t in ('python','gurobi','pytest','opendss')):continue
        try:
            cmd=p.cmdline();cwd=Path(p.cwd());allow=False;hashes=None;maps=None;reason='Unknown/native candidate: no bypass'
            if cwd==LANE and '-m' in cmd:
                i=cmd.index('-m');tail=cmd[i+1:]
                allow=(len(tail)>=2 and tail[0]=='v42_orchestrator' and tail[1] in ('verify','mock','plan')) or (tail[:3]==['unittest','discover','-s'] and 'tests/v42_orchestrator' in tail)
            if cwd==LANE and '-c' in cmd:
                code=cmd[cmd.index('-c')+1]
                allow=inline_readonly(code) or ('from v42_orchestrator.ledger import Ledger' in code and 'gurobi' not in code.lower() and 'dss' not in code.lower() and '.optimize' not in code)
            if allow:
                hashes=static_mock_audit();reason='Reviewed sleep-only mock/unittest or AST-checked readonly Git/SHA verification; no native calls'
            elif '-c' in cmd and inline_readonly(cmd[cmd.index('-c')+1]):
                allow=True;reason='AST-checked stdlib-only readonly Git/SHA verification'
            elif 'python' in (p.info['name'] or '').lower():
                maps=[m.path for m in p.memory_maps(grouped=True) if any(t in m.path.lower() for t in ('gurobi','opendss','dss_capi','dss_python','_dss'))]
                # A native optimizer/engine cannot be executing without its
                # executable DLL/module mapped. Newly mapped unknown native
                # modules are blocked at every fixture entry and monitor tick.
                allow=not maps
                if allow:reason='Current process maps contain no Gurobi/OpenDSS/native engine; continuously resampled'
            row=dict(p.info,cmdline=cmd,cwd=str(cwd),allowed_nonheavy=allow,reason=reason,source_SHA256=hashes,native_engine_maps=maps);rows.append(row)
            if not allow:blocked.append(row)
        except psutil.NoSuchProcess:continue
        except psutil.AccessDenied:
            row=dict(p.info,allowed_nonheavy=False,reason='Unobservable candidate: no bypass');rows.append(row);blocked.append(row)
    observations.append(dict(perf=_clock(),processes=rows,heavy_or_unverified=blocked));return blocked
start=_clock();initial=classify();assert not initial,'Actual heavy/unverified other lane detected: defer, never kill'
from v42_single_thread import resources
snapshot_original=resources.snapshot
def filtered_snapshot():
    value=snapshot_original();classify();allowed={r['pid'] for r in observations[-1]['processes'] if r['allowed_nonheavy']}
    value['heavy_processes']=[r for r in value['heavy_processes'] if r['self'] or r['pid'] not in allowed];return value
resources.snapshot=filtered_snapshot
import gurobipy as gp
original_optimize=gp.Model.optimize
def native_guard(model,*a,**k):
    assert not classify(),'Other lane native/unverified candidate: own fixture deferred'
    assert active[0] is None;active[0]=model;s=_clock()
    try:return original_optimize(model,*a,**k)
    finally:events.append(dict(start=s,end=_clock(),Threads=model.Params.Threads));active[0]=None
gp.Model.optimize=native_guard
def watch():
    while not done.wait(.5):
        try:
            blocked=classify()
            if blocked and active[0] is not None:
                failure.append(dict(perf=_clock(),blocked=blocked));active[0].terminate() # ONLY own pytest fixture
        except BaseException as error:failure.append(dict(error=repr(error)))
thread=threading.Thread(target=watch,daemon=True);thread.start();code=1
try:
    from v42_arc_floor.testing import run
    code=run(sys.argv[1:])
finally:
    done.set();thread.join();gp.Model.optimize=original_optimize;resources.snapshot=snapshot_original
    value=dict(user_authorized_verification_only_override=True,scientific_source_unchanged=True,other_lane_kill_calls=0,other_lane_terminate_calls=0,exit_code=code,elapsed=_clock()-start,initial=initial,observations=observations,native_fixture_calls=events,native_fixture_nonoverlap=all(a['end']<=b['start'] for a,b in zip(events,events[1:])),actual_concurrent_heavy_native_solve=len(failure),violations=failure)
    (OUT/'FULL_PYTEST_LANE_CONCURRENCY_AUDIT.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    assert not failure,'Concurrent native candidate observed: report failure'
raise SystemExit(code)
