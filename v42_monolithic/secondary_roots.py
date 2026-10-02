"""Preregistered terminal-status-only fallback: paired fresh barrier with crossover.

Primary simplex evidence is preserved. A primary optimal projection mismatch is
a hard stop and never eligible for fallback. No MIP policy or material criterion
is changed. This module has no MILP/canary/production optimization entry point.
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

POLICY=dict(SETTINGS,Method=2,Crossover=1,TimeLimit=1800)
def preregister():
    assert not (OUT/'ROOT_LP_ORIGINAL.json').exists() and not (OUT/'ROOT_LP_COMPACT.json').exists(),'SECONDARY_POLICY_MUST_PRECEDE_PRIMARY_TERMINAL_OUTCOMES'
    dump('ROOT_LP_SECONDARY_PREREGISTRATION.json',dict(utc=stamp(),commit=git('rev-parse','HEAD'),
        reason='Cold same-method simplex has not reached primal feasibility; terminal-only conditional fallback registered before either primary terminal result',
        activation='At least one primary simplex LP not OPTIMAL or missing feasible primal. NEVER bypass an OPTIMAL objective or mapped-feasibility mismatch.',
        policy=POLICY,order=['ROOT_LP_BARRIER_ORIGINAL','ROOT_LP_BARRIER_COMPACT'],fresh=True,LP_only=True,
        no_crossover_barrier=False,preserve_all_primary_evidence=True,canonical_equivalence_artifact_can_reference_secondary_pair=True,
        source_sha256=sha(Path(__file__)),material_criteria_unchanged=True,canary_settings_unchanged=SETTINGS,
        no_MILP_solve=True,production=False,absolute_speedup_comparison_across_methods=False))

def one(label,compact):
    check_freeze();snapshot(label)
    with PeakMemory() as peak,gp.Env(params={'OutputFlag':0}) as env:
        start=time.perf_counter();m=load_compact(env) if compact else original(env);build=time.perf_counter()-start;model_stats=stats(m)
        m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update()
        for k,v in POLICY.items():m.setParam(k,v)
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/(label+'.log'))
        telemetry=Telemetry(label);start=time.perf_counter();m.optimize(telemetry);wall=time.perf_counter()-start
        assert not telemetry.errors,telemetry.errors
        log=(OUT/(label+'.log')).read_text(encoding='utf8',errors='replace');pre=re.search(r'Presolve time:\s*([\d.]+)s',log)
        result=dict(label=label,utc=stamp(),status=m.Status,terminal_optimal=m.Status==gp.GRB.OPTIMAL,
            objective=attr(m,'ObjVal') if m.SolCount else None,settings=POLICY,solver_version=list(gp.gurobi.version()),model=model_stats,
            worker_build_seconds=build,wall_seconds=wall,solver_runtime=m.Runtime,presolve_seconds=None if pre is None else float(pre[1]),
            simplex_iterations=attr(m,'IterCount'),barrier_iterations=attr(m,'BarIterCount'),Kappa=attr(m,'Kappa'),KappaExact=attr(m,'KappaExact'),
            peak_worker_RSS_bytes=peak.peak,peak_solver_memory_GB=telemetry.max_solver_memory,
            warnings=[s for s in log.splitlines() if 'warning' in s.lower() or 'numerical trouble' in s.lower()],
            log_sha256=sha(OUT/(label+'.log')),resource_receipt='RESOURCE_'+label+'.json',fresh_no_start=True,
            strengthening='Identical sealed F3, no S2 additions; inherited stronger global LB retained')
        if m.SolCount:
            from v42_certificate.common import matrix_validation
            v=np.array(m.getAttr('X'));result['matrix_validation']=matrix_validation(m,v)
            np.savez_compressed(LOCAL/(label+'_SOLUTION.npz'),names=np.array(m.getAttr('VarName')),values=v)
        dump(label+'.json',result);m.dispose();return result
def run():
    p=read('ROOT_LP_SECONDARY_PREREGISTRATION.json');assert p['source_sha256']==sha(Path(__file__)) and p['policy']==POLICY
    a=read('ROOT_LP_ORIGINAL.json');b=read('ROOT_LP_COMPACT.json');primary=read('ROOT_LP_EQUIVALENCE.json')
    assert not primary['PASS'],'PRIMARY_PASSED_NO_SECONDARY_NEEDED'
    assert not (a.get('terminal_optimal') and b.get('terminal_optimal')),'PRIMARY_OPTIMAL_MISMATCH_HARD_STOP'
    dump('ROOT_LP_EQUIVALENCE_PRIMARY.json',primary)
    a=one('ROOT_LP_BARRIER_ORIGINAL',False);b=one('ROOT_LP_BARRIER_COMPACT',True)
    result=dict(PASS=False,selected_original_artifact='ROOT_LP_BARRIER_ORIGINAL.json',selected_compact_artifact='ROOT_LP_BARRIER_COMPACT.json',
        primary_result_artifact='ROOT_LP_EQUIVALENCE_PRIMARY.json',primary_simplex_nonterminal=True,
        method=2,Crossover=1,secondary_preregistration_sha256=sha(OUT/'ROOT_LP_SECONDARY_PREREGISTRATION.json'),
        objective_difference=None,identical_strengthening=True,inherited_global_LB=LB,
        rationale='Only numeric terminal-status fallback. Primary evidence preserved, no optimal mismatch bypass, no changed MIP/material policy.',fresh_solves=4)
    if a['terminal_optimal'] and b['terminal_optimal']:
        with np.load(LOCAL/'ROOT_LP_BARRIER_ORIGINAL_SOLUTION.npz') as z:x=z['values']
        with np.load(LOCAL/'ROOT_LP_BARRIER_COMPACT_SOLUTION.npz') as z:y=z['values']
        from v42_certificate.common import matrix_validation
        with gp.Env(params={'OutputFlag':0}) as env:
            o=original(env);n=load_compact(env)
            f=matrix_validation(n,sparse.load_npz(LOCAL/'FORWARD_F.npz')@x);r=matrix_validation(o,sparse.load_npz(LOCAL/'INVERSE_T.npz')@y)
            delta=abs(a['objective']-b['objective']);result.update(objective_difference=delta,original_to_compact=f,compact_to_original=r,
                original_objective=a['objective'],compact_objective=b['objective'],same_threads=True,same_method=True)
            result['PASS']=bool(delta<=1e-8 and f['PASS'] and r['PASS'] and a['matrix_validation']['PASS'] and b['matrix_validation']['PASS'])
            o.dispose();n.dispose()
    dump('ROOT_LP_EQUIVALENCE.json',result)
    return result
if __name__=='__main__':
    if sys.argv[1]=='preregister':preregister()
    elif sys.argv[1]=='run':print(run(),flush=True)
    else:raise ValueError(sys.argv[1])
