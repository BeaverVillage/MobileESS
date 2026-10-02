"""One sequential, gated monolithic benchmark lane. Never launches production."""
import math,re,time,sys
import numpy as np
from scipy import sparse
import gurobipy as gp
from .common import *
from .prepare import SETTINGS
from .build import LOCAL,stats
from .resources import snapshot,PeakMemory

def clean_number(value):
    return None if value is None or not math.isfinite(float(value)) or abs(value)>=gp.GRB.INFINITY/2 else float(value)
def attr(m,key):
    try:return clean_number(m.getAttr(key))
    except (gp.GurobiError,AttributeError):return None
def load_compact(env):
    A=sparse.load_npz(LOCAL/'COMPACT_A.npz')
    with np.load(LOCAL/'COMPACT_DATA.npz',allow_pickle=False) as z:d={k:z[k] for k in z.files}
    m=gp.Model('V42_COMPACT_MONOLITHIC',env=env)
    v=m.addMVar(len(d['names']),lb=d['lower'],ub=d['upper'],vtype=d['types'].tolist());m.update();m.setAttr('VarName',m.getVars(),d['names'].tolist())
    m.addMConstr(A,v,d['sense'],d['rhs']);m.setObjective(d['objective']@v+float(d['objcon']),gp.GRB.MINIMIZE);m.update()
    assert (m.getA()!=A).nnz==0
    assert np.array_equal(m.getAttr('RHS'),d['rhs']) and np.array_equal(m.getAttr('LB'),d['lower']) and np.array_equal(m.getAttr('UB'),d['upper'])
    return m
class Telemetry:
    def __init__(self,label):self.label=label;self.last=-30;self.trace=[];self.first_incumbent=None;self.open_nodes=None;self.presolve_last=None;self.root_first=None;self.max_solver_memory=None;self.errors=[]
    def __call__(self,m,where):
        if where==gp.GRB.Callback.POLLING:return
        try:
            t=m.cbGet(gp.GRB.Callback.RUNTIME)
            self.max_solver_memory=m.cbGet(gp.GRB.Callback.MAXMEMUSED)
            if where==gp.GRB.Callback.PRESOLVE:self.presolve_last=t
            if where==gp.GRB.Callback.MIPSOL and self.first_incumbent is None:self.first_incumbent=dict(seconds=t,objective=m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
            if where==gp.GRB.Callback.MIPNODE and self.root_first is None:self.root_first=dict(seconds=t,nodes=m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT),status=m.cbGet(gp.GRB.Callback.MIPNODE_STATUS))
            if where==gp.GRB.Callback.MIP:
                self.open_nodes=m.cbGet(gp.GRB.Callback.MIP_NODLFT)
                if t-self.last>=30:
                    self.last=t;d=dict(seconds=t,nodes=m.cbGet(gp.GRB.Callback.MIP_NODCNT),open_nodes=self.open_nodes,
                        UB=clean_number(m.cbGet(gp.GRB.Callback.MIP_OBJBST)),LB=clean_number(m.cbGet(gp.GRB.Callback.MIP_OBJBND)),simplex_iterations=m.cbGet(gp.GRB.Callback.MIP_ITRCNT))
                    self.trace.append(d);dump('LIVE_'+self.label+'.json',dict(trace=self.trace));print(self.label,d,flush=True)
            elif where==gp.GRB.Callback.SIMPLEX and t-self.last>=30:
                self.last=t;d=dict(seconds=t,iterations=m.cbGet(gp.GRB.Callback.SPX_ITRCNT),objective=clean_number(m.cbGet(gp.GRB.Callback.SPX_OBJVAL)),primal_infeasibility=m.cbGet(gp.GRB.Callback.SPX_PRIMINF),dual_infeasibility=m.cbGet(gp.GRB.Callback.SPX_DUALINF))
                self.trace.append(d);dump('LIVE_'+self.label+'.json',dict(trace=self.trace));print(self.label,d,flush=True)
        except Exception as e:
            self.errors.append(str(e));m.terminate()
def check_freeze():
    f=read('MODEL_FREEZE.json');assert sha(ROOT.parent/'THRESHOLD_LOCAL/F3.mps')==f['original_MPS_sha256']
    assert all(sha(LOCAL/p)==s for p,s in f['maps'].items())
    e=read('EXECUTION_FREEZE.json');assert all(sha(ROOT/p)==s for p,s in e['source_sha256'].items())
    preserve()
def run(label,root=False,compact=False):
    check_freeze();resource=snapshot(label)
    prereg=read('PREREGISTRATION.json');limit=prereg['root_seconds_each'] if root else prereg['canary_seconds_each']
    with PeakMemory() as peak,gp.Env(params={'OutputFlag':0}) as env:
        start=time.perf_counter();m=load_compact(env) if compact else original(env);build_seconds=time.perf_counter()-start
        frozen_stats=stats(m)
        with np.load(LOCAL/'AXIS_START.npz',allow_pickle=False) as z:
            names=z['compact_names' if compact else 'original_names'];values=z['compact_values' if compact else 'original_values']
            original_names=z['original_names']
        assert np.array_equal(m.getAttr('VarName'),names)
        if root:m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update()
        else:m.setAttr('Start',m.getVars(),values.tolist())
        for k,v in SETTINGS.items():m.setParam(k,v)
        m.Params.TimeLimit=limit;m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/(label+'.log'))
        telemetry=Telemetry(label);start=time.perf_counter();m.optimize(telemetry);wall=time.perf_counter()-start
        assert not telemetry.errors,telemetry.errors
        log=(OUT/(label+'.log')).read_text(encoding='utf8',errors='replace')
        presolve=re.search(r'Presolve time:\s*([\d.]+)s',log);rootlog=re.search(r'Root relaxation: objective ([\d.e+\-]+), (\d+) iterations, ([\d.]+) seconds',log)
        warnings=[line for line in log.splitlines() if 'warning' in line.lower() or 'numerical trouble' in line.lower()]
        start_messages=[line for line in log.splitlines() if 'MIP start' in line]
        start_accepted=any('Loaded user MIP start with objective' in line for line in start_messages)
        result=dict(label=label,created_utc=stamp(),status=m.Status,solver_version=list(gp.gurobi.version()),settings=dict(SETTINGS,TimeLimit=limit),
            model=frozen_stats,worker_build_seconds=build_seconds,full_formulation_build_seconds=read('COMPACT_MODEL_STATS.json')['total_compact_build_seconds'] if compact else read('COMPACT_MODEL_STATS.json')['original_read_seconds'],
            wall_seconds=wall,solver_runtime=m.Runtime,presolve_seconds=None if not presolve else float(presolve[1]),
            root_LP=None if not rootlog else dict(objective=float(rootlog[1]),iterations=int(rootlog[2]),seconds=float(rootlog[3])),
            root_first_callback=telemetry.root_first,first_incumbent=telemetry.first_incumbent,
            objective=attr(m,'ObjVal') if m.SolCount else None,BestBd=attr(m,'ObjBound') if not root else None,
            relative_gap=attr(m,'MIPGap') if not root else None,nodes_processed=attr(m,'NodeCount'),open_nodes=telemetry.open_nodes,
            simplex_iterations=attr(m,'IterCount'),Kappa=attr(m,'Kappa'),KappaExact=attr(m,'KappaExact'),
            peak_worker_RSS_bytes=peak.peak,peak_solver_memory_GB=telemetry.max_solver_memory,
            warnings=warnings,start_messages=start_messages,start_accepted=start_accepted if not root else None,
            branch_variable_families=None,branch_family_availability='Standard callback reports node counts; selected branching variable family is not exposed here.',
            telemetry=telemetry.trace,resource_receipt='RESOURCE_'+label+'.json',log_sha256=sha(OUT/(label+'.log')),
            strengthening='Identical unstrengthened F3; inherited stronger global LB retained separately')
        if m.SolCount:
            solution=np.array(m.getAttr('X'));np.savez_compressed(LOCAL/(label+'_SOLUTION.npz'),names=names,values=solution)
            from v42_certificate.common import matrix_validation,original_validation
            result['matrix_validation']=matrix_validation(m,solution)
            if root:result['terminal_optimal']=m.Status==gp.GRB.OPTIMAL
            else:
                inverse=sparse.load_npz(LOCAL/'INVERSE_T.npz')@solution if compact else solution
                result['independent_physical_validation']=original_validation(original_names,inverse)
                result['validated_UB']=result['objective'] if result['matrix_validation']['PASS'] and result['independent_physical_validation']['valid_new_UB'] else None
                result['valid_LB']=max(LB,result['BestBd']) if result['BestBd'] is not None else LB
                retained_UB=min(UB,result['validated_UB']) if result['validated_UB'] is not None else UB
                result['retained_valid_UB']=retained_UB;result['valid_global_gap']=(retained_UB-result['valid_LB'])/abs(retained_UB)
                result['P1_CANARY_ACCEPTED']=bool(result['validated_UB'] is not None and result['valid_global_gap']<=.005)
        dump(label+'.json',result);m.dispose();preserve();return result
def roots():
    assert read('FIXTURE_PATH_CENSUS.json')['PASS'] and read('BINARY_REDUCTION_REPORT.json')['PASS'] and read('MIP_START_PHYSICAL_VALIDATION.json')['PASS']
    a=run('ROOT_LP_ORIGINAL',root=True);b=run('ROOT_LP_COMPACT',root=True,compact=True)
    result=dict(PASS=False,objective_difference=None,identical_strengthening=True,inherited_global_LB=LB,
        strengthening_note='S2 LB is stronger than the unstrengthened F3 root. F3 root agreement is tested against F3, not against S2.',fresh_solves=2)
    if a.get('terminal_optimal') and b.get('terminal_optimal'):
        from v42_certificate.common import matrix_validation
        with np.load(LOCAL/'ROOT_LP_ORIGINAL_SOLUTION.npz') as z:x=z['values']
        with np.load(LOCAL/'ROOT_LP_COMPACT_SOLUTION.npz') as z:y=z['values']
        forward=sparse.load_npz(LOCAL/'FORWARD_F.npz');inverse=sparse.load_npz(LOCAL/'INVERSE_T.npz')
        with gp.Env(params={'OutputFlag':0}) as env:
            o=original(env);n=load_compact(env);f=matrix_validation(n,forward@x);r=matrix_validation(o,inverse@y)
            result.update(objective_difference=abs(a['objective']-b['objective']),original_to_compact=f,compact_to_original=r,
                original_objective=a['objective'],compact_objective=b['objective'],same_threads=True,same_method=True)
            result['PASS']=bool(result['objective_difference']<=1e-8 and f['PASS'] and r['PASS'] and a['matrix_validation']['PASS'] and b['matrix_validation']['PASS'])
            o.dispose();n.dispose()
    dump('ROOT_LP_EQUIVALENCE.json',result);return result
def canaries():
    assert read('ROOT_LP_EQUIVALENCE.json')['PASS'],'ROOT_GATE_FAIL'
    a=run('CANARY_ORIGINAL_600S');b=run('CANARY_COMPACT_600S',compact=True)
    start_gate=a['start_accepted'] and b['start_accepted']
    physical=a.get('validated_UB') is not None and b.get('validated_UB') is not None
    gap_improvement=(a['valid_global_gap']-b['valid_global_gap'])/a['valid_global_gap'] if a['valid_global_gap']>0 else 0.
    bound_improvement=b['valid_LB']-a['valid_LB'];material=gap_improvement>=.20 or bound_improvement>=.001
    promising=bool(start_gate and physical and material)
    result=dict(PASS=True,same_MIP_start_accepted=start_gate,physical_validation_PASS=physical,
        relative_gap_reduction=gap_improvement,valid_LB_improvement=bound_improvement,material_computational_improvement=material,promising=promising,
        original=dict(UB=a.get('validated_UB'),LB=a['valid_LB'],gap=a['valid_global_gap'],nodes=a['nodes_processed']),
        compact=dict(UB=b.get('validated_UB'),LB=b['valid_LB'],gap=b['valid_global_gap'],nodes=b['nodes_processed']),
        resource_comparison='Same machine and solver settings, sequential same lane; resource receipts disclose other jobs. Wall-time ratios are conditional on recorded workload; no controlled cross-run baseline claim.',
        historical_speedup_claim=False,root_relaxation_equivalent=True,production_1800_run=False)
    dump('CANARY_COMPARISON.json',result);return result
def main():
    mode=sys.argv[1]
    if mode=='freeze':
        dump('EXECUTION_FREEZE.json',dict(utc=stamp(),commit=git('rev-parse','HEAD'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
            source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'v42_monolithic').glob('*.py'))},
            optimization_order=read('PREREGISTRATION.json')['order']));return
    if mode=='roots':roots()
    elif mode=='canaries':canaries()
    else:raise ValueError(mode)
if __name__=='__main__':main()
