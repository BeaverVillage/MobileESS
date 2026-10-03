"""Reuse immutable PR133 M1 builders; redirect only namespace and thread policy."""
import gc
import json
import threading
import time
from .common import ROOT,OUT,LOCAL,configure,write,sha
from .resources import Timeline,exclusive_gate

ALIASES={
    'INTEGRATED_M1_MATRIX_CENSUS.json':'M1_SINGLE_THREAD_MATRIX_CENSUS.json',
    'INTEGRATED_M1_DUPLICATE_PROOF.json':'M1_SINGLE_THREAD_DUPLICATE_PROOF.json',
    'INTEGRATED_M1_DUPLICATE_MAP.csv':'M1_SINGLE_THREAD_DUPLICATE_MAP.csv',
    'ROOT_LP_EQUIVALENCE.json':'M1_SINGLE_THREAD_ROOT_LP_EQUIVALENCE.json',
    'M1_START_COMPATIBILITY.json':'M1_SINGLE_THREAD_START_COMPATIBILITY.json',
    'M1_ROOT_PATH_TIMELINE.json':'M1_SINGLE_THREAD_ROOT_TIMELINE.json',
    'M1_SOLVE_RESULT.json':'M1_SINGLE_THREAD_SOLVE_RESULT.json',
    'M1_CERTIFICATE.json':'M1_SINGLE_THREAD_CERTIFICATE.json',
}

def aliases():
    for original,target in ALIASES.items():
        source=OUT/original
        if source.exists():(OUT/target).write_bytes(source.read_bytes())

def adapter():
    configure()
    import v42_integrated.governance as governance
    import v42_integrated.a1 as a1
    import v42_integrated.build as build
    import v42_integrated.solve as solve
    import v42_integrated.monitor as monitor
    configure() # Legacy a1 import declares its old cache environment; restore ours.
    governance.OUT=OUT
    a1.LOCAL=LOCAL;build.LOCAL=LOCAL;solve.LOCAL=LOCAL
    build.OUT=OUT;solve.OUT=OUT
    solve.LP_POLICY=dict(solve.LP_POLICY,Threads=1)
    solve.MIP_POLICY=dict(solve.MIP_POLICY,Threads=1)
    return build,solve,monitor

def p2(solve,telemetry,p1):
    """Keep P1 certificate immutable; lock its UB before energy then count."""
    import gurobipy as gp
    import numpy as np
    from v42_integrated.matrix import audit
    from v42_two.contract import COMPONENT_EPS
    objective=json.loads((OUT/'M1_OBJECTIVE_CONTRACT.json').read_text(encoding='utf8'))
    exclusive_gate('M1_P2_before_model')
    m=solve.model('reduced');variables={v.VarName:v for v in m.getVars()}
    m.addConstr(variables['rho_max']<=p1['UB'],name='P2_exact_P1_UB_lock')
    expression=gp.LinExpr([objective['movement_energy_coefficients'][name] for name in objective['movement_energy_coefficients']],[variables[name] for name in objective['movement_energy_coefficients']])
    count=gp.quicksum(variables[name] for name in objective['movement_count_variables'])
    with np.load(LOCAL/'M1_FINAL_POINT.npz') as z:m.setAttr('Start',m.getVars(),z['values'].tolist())
    results=[];finished=False;physical=None
    try:
        for name,expr in (('movement_energy',expression),('movement_count',count)):
            exclusive_gate('M1_P2_'+name)
            for key,value in solve.MIP_POLICY.items():m.setParam(key,value)
            m.Params.LogFile=str(OUT/('M1_P2_'+name+'.log'))
            m.setObjective(expr);telemetry.active_model=m;telemetry.sample('P2_'+name+':before_optimize')
            monitor=solve.Monitor(checkpoint=False)
            m.optimize(monitor);telemetry.sample('P2_'+name+':immediately_after_optimize')
            entry=dict(component=name,status=m.Status,runtime=m.Runtime,objective=m.ObjVal if m.SolCount else None,bound=solve.finite(m.ObjBound),gap=m.MIPGap if m.SolCount else None,Threads=m.Params.Threads,Method=m.Params.Method,NodeMethod=m.Params.NodeMethod,Crossover=m.Params.Crossover,callback_errors=monitor.errors)
            if not m.SolCount:results.append(entry);break
            point=np.array(m.getAttr('X'));A,d=solve.full_arrays();matrix=audit(A,d,point,integral=True,tolerance=1e-8);physical=solve.physical(point,d)
            rho=float(point[variables['rho_max'].index])
            entry.update(matrix_audit=matrix,physical_audit=physical,P1_rho=rho,P1_no_degradation=rho<=p1['UB']+1e-8)
            results.append(entry)
            write('M1_SINGLE_THREAD_P2_RESULT.json',dict(accepted=False,passes=results,P1_certificate_preserved=True,P1_UB_lock=p1['UB'],P2_order=['movement_energy','movement_count']))
            if m.Status!=gp.GRB.OPTIMAL or not matrix['PASS'] or not physical['PASS'] or not entry['P1_no_degradation'] or monitor.errors or telemetry.policy_violations:break
            m.addConstr(expr<=m.ObjVal+COMPONENT_EPS,name='P2_lexicographic_lock_'+name)
            if name=='movement_count':
                finished=True
                np.savez_compressed(LOCAL/'M1_P2_FINAL_POINT.npz',names=d['names'],values=point)
        result=dict(accepted=finished,passes=results,P1_certificate_preserved=True,P1_UB_lock=p1['UB'],P1_lock_slack=0.,movement_energy=physical['movement_energy'] if physical else None,movement_count=physical['movement_count'] if physical else None,P2_order=['movement_energy','movement_count'],new_P1_optimization_calls=0,optimization_calls=len(results),settings=solve.MIP_POLICY)
        write('M1_SINGLE_THREAD_P2_RESULT.json',result)
        return result
    finally:
        telemetry.active_model=None;m.dispose()

def run():
    configure()
    freeze=json.loads((OUT/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json').read_text(encoding='utf8'))
    if not freeze.get('PASS'):raise ValueError('A1_ACCEPTED_FREEZE_REQUIRED')
    exclusive_gate('M1_before_build')
    telemetry=Timeline('M1');build,solve,monitor=adapter()
    import gurobipy as gp
    gp.setParam('Threads',1)
    class ResourceMonitor(monitor.Monitor):
        def __init__(self,checkpoint=True):
            super().__init__(checkpoint=checkpoint);self.recorded=set()
        def __call__(self,m,where):
            before=len(self.events);first=self.first_incumbent
            super().__call__(m,where)
            try:
                for event in self.events[before:]:
                    telemetry.sample(event['event'],event['time'])
                if first is None and self.first_incumbent is not None:telemetry.sample('first_incumbent',self.first_incumbent)
            except Exception as error:self.errors.append(repr(error));m.terminate()
    solve.Monitor=ResourceMonitor
    original_model=solve.model
    def model(kind):
        exclusive_gate('M1_'+kind+'_before_model_read')
        m=original_model(kind);m.Params.Threads=1;telemetry.active_model=m
        telemetry.sample('after_'+kind+'_model_read');return m
    solve.model=model
    result=None;p2_result=None;status='NOT_RUN';error=None
    try:
        from v42_integrated.import_guard import selected_imports
        from v42_integrated.contract import physical_authority
        with selected_imports(),physical_authority():
            build.run();telemetry.sample('after_model_build');aliases();gc.collect()
            start=json.loads((OUT/'M1_START_COMPATIBILITY.json').read_text(encoding='utf8'))
            if start.get('reused'):
                import numpy as np
                with np.load(LOCAL/'M1_START.npz') as z:point=z['values']
                _,columns=solve.full_arrays();independent=solve.physical(point,columns)
                start['independent_physical_audit']=independent
                if not independent['PASS']:
                    start.update(reused=False,status='REJECTED',reason='INDEPENDENT_NEW_AUTHORITY_PHYSICAL_AUDIT_FAILED')
                write('M1_START_COMPATIBILITY.json',start);aliases()
            full=solve.lp('full');telemetry.active_model=None;telemetry.sample('after_full_LP');gc.collect()
            reduced=solve.lp('reduced');telemetry.active_model=None;telemetry.sample('after_reduced_LP');gc.collect()
            if not solve.check_lp(full,reduced):
                status='ROOT_LP_GATE_FAILED';return False
            result=solve.mip();telemetry.active_model=None
            status=result['status_name'];aliases()
            certificate=json.loads((OUT/'M1_CERTIFICATE.json').read_text(encoding='utf8'))
            write('M1_SINGLE_THREAD_P1_CERTIFICATE.json',certificate)
            if certificate['M1_ACCEPTED'] and not telemetry.policy_violations:
                p2_result=p2(solve,telemetry,result)
                certificate['P1_ACCEPTED']=True
                certificate['P2_execution']=p2_result
                certificate['M1_ACCEPTED']=p2_result['accepted'] and not telemetry.policy_violations
                write('M1_CERTIFICATE.json',certificate)
                write('M1_SINGLE_THREAD_CERTIFICATE.json',certificate)
            return bool(certificate['M1_ACCEPTED'])
    except Exception as exception:
        memory=isinstance(exception,MemoryError) or getattr(exception,'errno',None)==10001
        error=dict(type=type(exception).__name__,message=str(exception),error_code=getattr(exception,'errno',None),memory_failure=memory,infeasibility_proven=False)
        status='NATIVE_OUT_OF_MEMORY' if memory else 'EXECUTION_STOP'
        write('M1_SINGLE_THREAD_ROOT_CAUSE.json',error)
        if result is None:write('M1_SOLVE_RESULT.json',dict(status=status,UB=None,LB=None,gap=None,incumbent_exists=False,error=error,M1_ACCEPTED=False))
        write('M1_CERTIFICATE.json',dict(status=status,M1_ACCEPTED=False,UB=result['UB'] if result else None,LB=result['LB'] if result else None,gap=result['gap'] if result else None,error=error,old_certificate='SUPERSEDED_NOT_USED'))
        print('M1_SINGLE_THREAD_STOP',error,flush=True)
        return False
    finally:
        telemetry.active_model=None
        summary=telemetry.close(status);aliases()
        if p2_result is None:write('M1_SINGLE_THREAD_P2_RESULT.json',dict(status='NOT_RUN',reason='P1_NOT_ACCEPTED_OR_PRECONDITION_FAILED',movement_energy=None,movement_count=None))
        write('M1_SINGLE_THREAD_EXECUTION_RECEIPT.json',dict(status=status,resource_summary=summary,P1_result_generated=result is not None,P2_result_generated=p2_result is not None,error=error,old_bounds_used=False,PR133_source_files_edited=False))

if __name__=='__main__':run()
