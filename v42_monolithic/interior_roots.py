"""Final, terminal-status-only numerical fallback; no basis crossover, tighter gap.

All prior evidence remains visible. This is LP certification, never candidate
MIP parameter selection: the original paired 600s policy is unchanged.
"""
import sys,re,time
import numpy as np
from scipy import sparse
import gurobipy as gp
from .common import *
from .prepare import SETTINGS
from .build import LOCAL,stats
from .experiment import load_compact,Telemetry,attr,check_freeze
from .resources import snapshot,PeakMemory
POLICY=dict(SETTINGS,Method=2,Crossover=0,BarConvTol=1e-11,TimeLimit=1800)
def preregister():
    assert not (OUT/'ROOT_LP_BARRIER_ORIGINAL.json').exists() and not (OUT/'ROOT_LP_BARRIER_COMPACT.json').exists()
    dump('ROOT_LP_INTERIOR_PREREGISTRATION.json',dict(utc=stamp(),source_sha256=sha(Path(__file__)),policy=POLICY,
        reason='Observed crossover basis drop and very large primal/dual infeasibilities, after a near-optimal barrier point; registration precedes crossover terminal outcomes',
        activation='Only crossover pair has at least one nonoptimal/missing primal result. Any pair with both OPTIMAL and projection mismatch is a hard STOP.',
        pair=['ROOT_LP_INTERIOR_ORIGINAL','ROOT_LP_INTERIOR_COMPACT'],fresh=True,LP_only=True,
        previous_methods_attempted='Same dual simplex, then barrier WITH crossover. No-crossover is used only when these do not yield a terminal certification.',
        objective_tolerance_unchanged=1e-8,material_criteria_unchanged=True,canary_policy_unchanged=SETTINGS,
        primal_mapping_required=True,no_MIP_parameter_sweep=True,production=False))
def one(label,compact):
    check_freeze();snapshot(label)
    with PeakMemory() as peak,gp.Env(params={'OutputFlag':0}) as env:
        start=time.perf_counter();m=load_compact(env) if compact else original(env);build=time.perf_counter()-start;domain=stats(m)
        m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update();assert m.NumIntVars==0
        for k,v in POLICY.items():m.setParam(k,v)
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/(label+'.log'))
        telemetry=Telemetry(label);start=time.perf_counter();m.optimize(telemetry);wall=time.perf_counter()-start
        assert not telemetry.errors,telemetry.errors
        log=(OUT/(label+'.log')).read_text(encoding='utf8',errors='replace');pre=re.search(r'Presolve time:\s*([\d.]+)s',log)
        result=dict(label=label,utc=stamp(),status=m.Status,terminal_optimal=m.Status==gp.GRB.OPTIMAL,
            objective=attr(m,'ObjVal') if m.SolCount else None,settings=POLICY,solver_version=list(gp.gurobi.version()),domain_before_relaxation=domain,
            all_binaries_relaxed=True,root_integer_variables=m.NumIntVars,worker_build_seconds=build,wall_seconds=wall,solver_runtime=m.Runtime,
            presolve_seconds=None if pre is None else float(pre[1]),simplex_iterations=attr(m,'IterCount'),barrier_iterations=attr(m,'BarIterCount'),
            Kappa=attr(m,'Kappa'),KappaExact=attr(m,'KappaExact'),basis_available=False,
            peak_worker_RSS_bytes=peak.peak,peak_solver_memory_GB=telemetry.max_solver_memory,
            warnings=[s for s in log.splitlines() if 'warning' in s.lower() or 'numerical trouble' in s.lower()],
            log_sha256=sha(OUT/(label+'.log')),resource_receipt='RESOURCE_'+label+'.json',fresh_no_start=True,
            strengthening='Identical sealed F3; no S2 rows; inherited global LB retained')
        if m.SolCount:
            from v42_certificate.common import matrix_validation
            v=np.array(m.getAttr('X'));result['matrix_validation']=matrix_validation(m,v)
            pi=np.array(m.getAttr('Pi'));rc=np.array(m.getAttr('RC'));c=np.array(m.getAttr('Obj'))
            residual=c-m.getA().T@pi-rc
            result['dual_stationarity_max_absolute_residual']=float(np.max(abs(residual)))
            result['dual_stationarity_note']='Diagnostic only; a floating stationarity residual is not presented as an exact rational dual certificate. Solver OPTIMAL and tight registered tolerances plus independent primal mappings are required.'
            np.savez_compressed(LOCAL/(label+'_SOLUTION.npz'),names=np.array(m.getAttr('VarName')),values=v,Pi=pi,RC=rc)
        dump(label+'.json',result);m.dispose();return result
def run():
    p=read('ROOT_LP_INTERIOR_PREREGISTRATION.json');assert p['source_sha256']==sha(Path(__file__)) and p['policy']==POLICY
    a=read('ROOT_LP_BARRIER_ORIGINAL.json');b=read('ROOT_LP_BARRIER_COMPACT.json')
    assert not (a.get('terminal_optimal') and b.get('terminal_optimal')),'CROSSOVER_OPTIMAL_MISMATCH_HARD_STOP_OR_ALREADY_PASSED'
    primary=read('ROOT_LP_EQUIVALENCE_PRIMARY.json');assert not primary['PASS']
    a=one('ROOT_LP_INTERIOR_ORIGINAL',False);b=one('ROOT_LP_INTERIOR_COMPACT',True)
    result=dict(PASS=False,selected_original_artifact='ROOT_LP_INTERIOR_ORIGINAL.json',selected_compact_artifact='ROOT_LP_INTERIOR_COMPACT.json',
        primary_result_artifact='ROOT_LP_EQUIVALENCE_PRIMARY.json',crossover_original_artifact='ROOT_LP_BARRIER_ORIGINAL.json',crossover_compact_artifact='ROOT_LP_BARRIER_COMPACT.json',
        method=2,Crossover=0,BarConvTol=1e-11,preregistration_sha256=sha(OUT/'ROOT_LP_INTERIOR_PREREGISTRATION.json'),
        objective_difference=None,identical_strengthening=True,inherited_global_LB=LB,
        rationale='Nonterminal numeric fallback only; all prior evidence preserved, no optimal mismatch bypass, original MIP/material policy unchanged.')
    if a['terminal_optimal'] and b['terminal_optimal']:
        with np.load(LOCAL/'ROOT_LP_INTERIOR_ORIGINAL_SOLUTION.npz') as z:x=z['values']
        with np.load(LOCAL/'ROOT_LP_INTERIOR_COMPACT_SOLUTION.npz') as z:y=z['values']
        from v42_certificate.common import matrix_validation
        with gp.Env(params={'OutputFlag':0}) as env:
            o=original(env);n=load_compact(env);f=matrix_validation(n,sparse.load_npz(LOCAL/'FORWARD_F.npz')@x);r=matrix_validation(o,sparse.load_npz(LOCAL/'INVERSE_T.npz')@y)
            delta=abs(a['objective']-b['objective']);result.update(objective_difference=delta,original_to_compact=f,compact_to_original=r,
                original_objective=a['objective'],compact_objective=b['objective'],same_threads=True,same_method=True)
            result['PASS']=bool(delta<=1e-8 and f['PASS'] and r['PASS'] and a['matrix_validation']['PASS'] and b['matrix_validation']['PASS'])
            o.dispose();n.dispose()
    dump('ROOT_LP_EQUIVALENCE.json',result);return result
if __name__=='__main__':
    if sys.argv[1]=='preregister':preregister()
    elif sys.argv[1]=='run':print(run(),flush=True)
    else:raise ValueError(sys.argv[1])
