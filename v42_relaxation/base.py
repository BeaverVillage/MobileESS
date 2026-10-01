"""Seal inherited inputs; capture the unmodified native F3 optimum first."""
from pathlib import Path
from time import perf_counter
from collections import Counter
import csv, gzip, hashlib, json, pickle, shutil, subprocess, threading
import gurobipy as gp
import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_relaxation_strengthening'
LOCAL = ROOT.parent / 'V42_RELAXATION_LOCAL'
PRIOR = ROOT / 'docs/v42_m1_root_cut_exit'
INPUT = Path('D:/ChatGPT/Mobile ESS 2/V42_M1_ROOT_CUT_EXIT_LOCAL')
HEAD = 'c9233bd9d3977984e6de31e1d2924f10d1287a84'
UB = 0.6696147314213984
LB = 0.571849460049452
TOL = 1e-5
OBJ_TOL = 1e-7
EXPECTED = dict(binary=208312, continuous=108431, rows=954560,
                columns=316743, nonzeros=8282350, fingerprint='0x9cfd10ec')

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(p):
    return json.loads(Path(p).read_text(encoding='utf8'))

def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT/name
    tmp = p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')
    tmp.replace(p)

def table(name, rows, fields=None):
    with (OUT/name).open('w', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader(); w.writerows(rows)

def setup():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==HEAD
    OUT.mkdir(parents=True,exist_ok=True); LOCAL.mkdir(exist_ok=True)
    assert not (OUT/'PREREGISTRATION.json').exists(), 'PREREGISTRATION_ALREADY_SEALED'
    dump('PREREGISTRATION.json',dict(base_head=HEAD,base_PR=108,formulation='M1-F3',
        expected_identity=EXPECTED,UB=UB,expected_root_LB=LB,physical_tolerance=TOL,
        objective_tolerance=OBJ_TOL,fractionality_tolerance=TOL,
        LP=dict(Method=2,Threads=1),
        MIP=dict(Method=2,Threads=1,Heuristics=0,MIPFocus=3,CutPasses=-1,
                 DegenMoves=-1,Seed=20260929,MIPGap=.005,GPU=False),
        candidate_gates=dict(S1='any H1/H2/H3 violation > tolerance at baseline optimum',
            S2='fixed-root arc-energy LP certified INFEASIBLE',S3='both gates'),
        gain_categories=dict(material=.001,strong=.01,very_strong_LB=.62,target_region_LB=.65),
        canary=dict(max_runs=1,seconds=600,gate='selected delta_LB >= .001'),
        production=dict(max_runs=1,seconds=1800,cumulative_optimize_only=True,
            gate='canary BestBd - PR108 LB >= .005 OR gap <= .12 OR certified gap <= .005'),
        A1_optimize_calls=0,no_solver_search=True,STOP_before_A2=True))
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(base_head=HEAD,files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked],PASS=True))
    dump('PR108_BASE_RECEIPT.json',dict(PR=108,exact_head=HEAD,worktree=str(ROOT),
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
        inherited_evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(PRIOR.rglob('*')) if p.is_file()]))
    reused=[]
    for n in ['A1_AIDC_GRID_CONTROL_ANCHOR.json','A1_TO_M1_HANDOFF.json','A1_PROVISIONAL_CONTROL_TABLE.csv','A1_UNKNOWN_POLICY_TABLE.json','A1_AIDC_SITE_TIME_ANCHOR.csv']:
        shutil.copyfile(PRIOR/n,OUT/n)
        reused.append(dict(path=n,sha256=sha(OUT/n),PR108_sha256=sha(PRIOR/n)))
    expected=read(PRIOR/'PR107_A1_ANCHOR_REUSE.json')['data_sha256']
    assert sha(INPUT/'DATA.pkl')==expected
    start=read(PRIOR/'PR107_MIP_START_VALIDATION.json')
    assert sha(INPUT/'PR107_M1_PLAN.json')==start['source_sha256']
    for n in ['DATA.pkl','PR107_M1_PLAN.json','PR107_M1_CONTROLS.json']:
        shutil.copyfile(INPUT/n,LOCAL/n)
    from v42_bootstrap.handoff import validate_handoff
    validate_handoff(read(OUT/'A1_TO_M1_HANDOFF.json'),read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json'))
    dump('PR108_A1_ANCHOR_REUSE.json',dict(PASS=True,A1_OPTIMIZE_CALLS_THIS_TASK=0,
        A1_RERUN=False,A1_ANCHOR_REUSED=True,files=reused,data_sha256=expected,
        CC4_Runtime_handoff_unchanged=True))
    dump('PR108_MIP_START_RECEIPT.json',dict(inherited_validation=start,
        plan_sha256=sha(LOCAL/'PR107_M1_PLAN.json'),controls_sha256=sha(LOCAL/'PR107_M1_CONTROLS.json'),
        newly_validated=False,used_only_for_validation_and_start=True))

def inputs():
    assert sha(LOCAL/'DATA.pkl')==read(OUT/'PR108_A1_ANCHOR_REUSE.json')['data_sha256']
    with (LOCAL/'DATA.pkl').open('rb') as f: data=pickle.load(f)
    assert len(data[1])==1499
    bundle=data[0]; anchor=read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json')
    from v42_bootstrap.m1 import native_inputs
    sites,initial,routes,battery,_=native_inputs(bundle)
    return bundle,anchor,read(LOCAL/'PR107_M1_PLAN.json'),sites,initial,routes,battery

def stats(m):
    m.update()
    return dict(binary=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,rows=m.NumConstrs,
        columns=m.NumVars,nonzeros=m.NumNZs,fingerprint=f'0x{m.Fingerprint & 0xffffffff:08x}')

def matrix_validate(m, values):
    vv=np.asarray([values[n] for n in m.getAttr('VarName')]);a=m.getA()
    assert np.isfinite(vv).all(), 'NONFINITE_SOLUTION_VALUES'
    activity=a@vv;rhs=np.asarray(m.getAttr('RHS'));sense=np.asarray(m.getAttr('Sense'))
    assert np.isfinite(activity).all(), 'NONFINITE_ROW_ACTIVITY'
    error=np.where(sense=='=',abs(activity-rhs),np.where(sense=='<',activity-rhs,rhs-activity))
    residual=max(0.,float(error.max()),float((np.asarray(m.getAttr('LB'))-vv).max()),float((vv-np.asarray(m.getAttr('UB'))).max()))
    assert residual<=TOL, residual
    return dict(PASS=True,matrix_max_violation=residual,variables=m.NumVars,rho=values['rho_max'])

def build(optimizer, hook=None):
    from v42_m1_sparse.grid import compressed_grid
    from v42_bootstrap.m1 import OptimizeOnlyBudget
    import v42_native.mess as native
    bundle,anchor,prior,sites,initial,routes,battery=inputs();bindings=[];controls=[]
    def builder(m,p,q):
        levels,c=compressed_grid(m,bundle,anchor,p,q,'M1-F3',bindings,[])
        controls.extend(c);return levels
    def capture(m,objectives,deadline,*args,**kwargs):
        return optimizer(m,objectives,bindings,controls,(bundle,anchor,prior,sites,initial,routes,battery))
    old=native.optimize;native.optimize=capture
    try:
        kwargs={} if hook is None else dict(strengthening_hook=hook)
        return native.solve('M1',OptimizeOnlyBudget(),sites,initial,routes,battery,96,builder,**kwargs)
    finally:native.optimize=old

def baseline():
    assert not (LOCAL/'BASE_OPTIMIZE_STARTED.json').exists(), 'NO_BASE_SOLVE_RETRY'
    def optimize(m,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        from v42_native.mess import validate
        from v42_bootstrap.attribution import supplemental_physical
        from v42_bootstrap.grid import grid_report
        from v42_m1_sparse.post_validate import controls_from_plan
        bundle,anchor,prior,sites,initial,routes,battery=data
        m.setObjective(objectives[0][1]);m.update()
        values=prior['values'].copy();map_bindings(bindings,values)
        m.setAttr('Start',[values[n] for n in m.getAttr('VarName')]);m.update()
        identity=stats(m)
        dump('BASE_F3_IDENTITY.json',dict(PASS=identity==EXPECTED,observed=identity,expected=EXPECTED,optimize_calls=0))
        assert identity==EXPECTED, ('BASE_F3_IDENTITY_FAILURE',identity,EXPECTED)
        start=matrix_validate(m,values);physical=validate(prior,sites,routes,battery,96)
        extra=supplemental_physical(prior,sites,battery)
        grid=grid_report(bundle,controls_from_plan(prior,anchor),UB)
        assert physical['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS']
        receipt=read(OUT/'PR108_MIP_START_RECEIPT.json')
        receipt.update(newly_validated=True,matrix=start,physical=physical,supplement=extra,grid=grid)
        dump('PR108_MIP_START_RECEIPT.json',receipt)
        names=m.getAttr('VarName');types=m.getAttr('VType');lb=m.getAttr('LB');ub=m.getAttr('UB')
        m.setAttr('VType',[gp.GRB.CONTINUOUS]*m.NumVars);m.setAttr('LB',lb);m.setAttr('UB',ub);m.update()
        m.Params.Method=2;m.Params.Threads=1;m.Params.OutputFlag=1;m.Params.LogToConsole=0
        m.Params.LogFile=str(LOCAL/'BASE_ROOT.log')
        process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event()
        def sample():
            while not stop.wait(.25):peak[0]=max(peak[0],process.memory_info().rss)
        thread=threading.Thread(target=sample,daemon=True);thread.start();messages=[];events={}
        begin=perf_counter()
        def cb(model,where):
            elapsed=perf_counter()-begin
            if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING))
            if where==gp.GRB.Callback.BARRIER:events.setdefault('barrier_start_seconds',elapsed)
            if where==gp.GRB.Callback.SIMPLEX:events.setdefault('simplex_start_seconds',elapsed)
        (LOCAL/'BASE_OPTIMIZE_STARTED.json').write_text('{}\n')
        try:m.optimize(cb)
        finally:stop.set();thread.join(1)
        wall=perf_counter()-begin
        log=''.join(messages);(OUT/'BASE_ROOT_LP_SOLVER.display.txt').write_text(log,encoding='utf8')
        (OUT/'BASE_ROOT_LP_SOLVER.raw.gz').write_bytes(gzip.compress(log.encode(),mtime=0))
        receipt=dict(status=m.Status,optimal=m.Status==gp.GRB.OPTIMAL,
            bound=m.ObjVal if m.SolCount else None,seconds=wall,native_seconds=m.Runtime,
            iterations=m.IterCount,barrier_iterations=m.BarIterCount,peak_RSS_bytes=peak[0],
            events=events,identity=identity,settings=dict(Method=2,Threads=1),
            inherited_objective=LB,objective_tolerance=OBJ_TOL,
            reproduced=bool(m.Status==gp.GRB.OPTIMAL and abs(m.ObjVal-LB)<=OBJ_TOL))
        dump('BASE_ROOT_LP_OPTIMIZATION.json',receipt)
        assert receipt['reproduced'], 'STOP_ROOT_OBJECTIVE_NOT_REPRODUCED'
        vv=dict(zip(names,m.getAttr('X')))
        arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in routes]
        for unit in initial:
            for k in range(len(arcs)):vv.setdefault(f'arc[{unit},{k}]',0.)
            for s in sites:
                for t in range(96):
                    for prefix in ['Pch','Pdis','Q']:vv.setdefault(f'{prefix}[{unit},{s},{t}]',0.)
        allnames=list(vv)
        np.savez_compressed(OUT/'BASE_ROOT_LP_SOLUTION.npz',names=np.asarray(allnames),values=np.asarray(list(vv.values())),
            model_names=np.asarray(names),original_types=np.asarray(types),original_lb=np.asarray(lb),original_ub=np.asarray(ub))
        dump('BASE_ROOT_LP_SOLUTION_SUMMARY.json',dict(optimal=True,rho=vv['rho_max'],
            complete_model_columns=len(names),complete_with_eliminated_zero_columns=len(vv),
            solution_sha256=sha(OUT/'BASE_ROOT_LP_SOLUTION.npz'),families=dict(Counter(n.split('[')[0] for n in vv)),
            original_matrix_validation=matrix_validate(m,vv),A1_optimize_calls=0))
        print('BASE ROOT COMPLETE',receipt,flush=True)
        return None,dict(optimize_calls=1)
    build(optimize)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['setup','baseline']);a=p.parse_args()
    globals()[a.phase]()
