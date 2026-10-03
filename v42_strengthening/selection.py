from .common import OUT,SOURCE,SCIENCE,REF,BASE,BASE_LB,UB_REF,write,read,sha,material,once
from .analysis import graph_inputs
from .lp import cold_model
import numpy as np
import gurobipy as gp

def select():
    results={}
    for name,file in [('CUT_A','CUT_A_ROOT_RESULT.json'),('SOC_ENVELOPE','STRENGTHENING_B_ROOT_RESULT.json'),('SOC_FLOW_EXTENDED','SOC_FLOW_FULL_ROOT_RESULT.json')]:
        path=OUT/file
        results[name]=read(path) if path.exists() else dict(status='NOT_RUN',reason='STAGE_NOT_REACHED')
    eligible=[(name,r) for name,r in results.items() if r.get('selected') and r.get('exact_integer_equivalence_PASS') and r.get('material')]
    winner='BASE'
    if eligible:
        winner=max(eligible,key=lambda p:(p[1]['objective'],-p[1]['fractional_census']['fractionality_mass'],-p[1]['matrix_growth']['after']['nnz']))[0]
    candidate=results.get(winner)
    lb=candidate['objective'] if candidate else BASE_LB
    selection=dict(selected_candidate=winner,selected_root_LB=lb,
        selected_matrix=candidate['matrix_growth']['after'] if candidate else dict(rows=886017,columns=316743,binaries=208312,nnz=8447855),
        material_improvement=material(lb)['material'],diagnostic_gap=material(lb),
        selected_fractional_mass=candidate['fractional_census']['fractionality_mass'] if candidate else read(OUT/'M1_ROOT_FRACTIONAL_SUMMARY.json')['fractionality_mass'],
        exact_integer_equivalence_PASS=True,physical_semantics_identical=True,
        candidate_results={name:{k:v for k,v in r.items() if k!='fractional_census'} for name,r in results.items()},
        selection_order=['exact integer projection','identical physical semantics','strongest material root LB','fractional mass','matrix/runtime'],
        ineffective_candidates_adopted=False,production_base_source_modified=False,canary_authorized=material(lb)['material'])
    write('M1_STRENGTHENING_SELECTION.json',selection)
    if not selection['canary_authorized']:
        write('M1_STRENGTHENED_MIP_CANARY.json',dict(status='NOT_RUN',reason='NO_SELECTED_MATERIAL_ROOT_IMPROVEMENT',optimization_calls=0,
              first_nonroot=None,first_branch=None,LB=None,UB=None,gap=None,old_UB_reference_used_as_certificate=False))
        (OUT/'M1_STRENGTHENED_MIP_CANARY.log').write_text('NOT_RUN: selected root LP lacks material improvement. No MIP optimize call.\n',encoding='utf8')
    return selection

def install_selected(model,selection):
    name=selection['selected_candidate']
    sites,initial,arcs,battery,_=graph_inputs()
    if name=='BASE':return
    if name=='CUT_A':
        from .cuts import add_A
        return add_A(model,sites,initial,battery.p_limit)
    if name=='SOC_ENVELOPE':
        from .envelopes import state_rows,add_envelopes
        return add_envelopes(model,state_rows(dict(names=np.asarray(model.getAttr('VarName'))),sites,initial,arcs,battery))
    if name=='SOC_FLOW_EXTENDED':
        from .flow import add_flow
        return add_flow(model,sites,initial,arcs,battery)
    raise ValueError('UNKNOWN_SELECTED_CANDIDATE')

def canary():
    import time
    from .resources import gate
    from v42_cutpass.monitor import Monitor,start_receipt
    from v42_integrated.matrix import arrays,audit
    from v42_degen.identity import inputs
    from v42_postsolve.contract import audit_point
    selection=read(OUT/'M1_STRENGTHENING_SELECTION.json')
    if not selection['canary_authorized']:return
    gp.setParam('Threads',1)
    m,A,d=cold_model()
    try:
        install_selected(m,selection)
        B,e=arrays(m)
        reference=__import__('pathlib').Path(__file__).resolve().parents[1]/'docs/v42_m1_degenmoves_zero_start_v1/RAW_POINTS/ZERO_ACTION_CANDIDATE.npz'
        with np.load(reference) as z:
            assert np.array_equal(z['names'],d['names'])
            start=list(z['values']);values=dict(zip(map(str,d['names']),start))
        _,_,arcs,_,_=graph_inputs()
        for name in e['names'][len(start):]:
            prefix,suffix=str(name).split('[',1)
            assert prefix=='energy_flow'
            u,k=suffix[:-1].split(',');k=int(k)
            start.append(values[f'arc[{u},{k}]']*values[f'SOC[{u},{arcs[k][1]}]'])
        start=np.asarray(start)
        validation=audit(B,e,start,integral=True,tolerance=1e-6)
        assert validation['PASS']
        policy=dict(read(REF/'M1_CUTPASSES1_SOLVE_RESULT.json')['settings'],TimeLimit=600)
        for key,value in policy.items():m.setParam(key,value)
        m.Params.LogFile=(OUT.relative_to(__import__('pathlib').Path.cwd())/'M1_STRENGTHENED_MIP_CANARY.log').as_posix()
        m.setAttr('Start',m.getVars(),start.tolist());m.update()
        gate('canary_before_optimize');once('MIP_CANARY')
        monitor=Monitor(m.getVars(),checkpoint=False)
        begin=time.perf_counter();m.optimize(monitor);wall=time.perf_counter()-begin
        LB=float(m.ObjBound) if abs(m.ObjBound)<1e100 and m.Status in (2,9,11) and not monitor.errors else None
        UB=None;audited=None
        if m.SolCount:
            full_A,full_d,*_=inputs()
            point=np.asarray(m.getAttr('X'))
            numerical=audit_point('M1',full_A,full_d,point[:len(d['names'])])
            extended=audit(B,e,point,integral=True,tolerance=1e-6)
            import v42_integrated.solve as solve
            from v42_integrated.contract import physical_authority
            previous=(solve.OUT,solve.LOCAL,solve.write)
            solve.OUT=OUT;solve.LOCAL=SOURCE;solve.write=write
            (OUT/'INTEGRATED_A1_FREEZE.json').write_bytes((SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json').read_bytes())
            try:
                with physical_authority():physical=solve.physical(point[:len(d['names'])],full_d)
            finally:solve.OUT,solve.LOCAL,solve.write=previous
            passed=bool(numerical['NUMERICAL_AUDIT_PASS'] and extended['PASS'] and physical['PASS'])
            audited=dict(PASS=passed,numerical=numerical,extended=extended,physical=physical,native_terminal_solver_incumbent=True)
            if passed:UB=numerical['objective']
            np.savez_compressed(OUT/'CANARY_TERMINAL_SOLUTION.npz',names=e['names'],values=point)
        gap=None if LB is None or UB is None else (UB-LB)/abs(UB)
        times=monitor.times
        bounds=[r['last_MIP_observation']['LB'] for r in monitor.trace if r['last_MIP_observation'] and r['last_MIP_observation']['LB'] is not None]
        progression=bool(LB is not None and len(bounds)>1 and max(bounds)-min(bounds)>1e-8)
        branch=times['first_nonroot'] is not None or times['first_branch'] is not None
        verdict='SUCCESS' if branch and progression else 'PARTIAL' if selection['material_improvement'] else 'FAILED'
        write('M1_STRENGTHENED_MIP_CANARY.json',dict(status=verdict,selected_candidate=selection['selected_candidate'],
              native_status=m.Status,runtime=m.Runtime,optimize_wall_seconds=wall,optimization_calls=1,
              settings=policy,first_nonroot=times['first_nonroot'],first_branch=times['first_branch'],
              first_branch_directly_unexposed=True,root_processing_complete=times['root_processing_complete'],
              node_count=m.NodeCount,solver_incumbents=m.SolCount,LB=LB,UB=UB,gap=gap,
              validated_bound_progression=progression,incumbent_audit=audited,timeline=monitor.json(),
              Start_validation=validation,Start_binding=start_receipt(monitor.start_messages),
              zero_action_is_diagnostic_reference_only=True,old_UB_reference_used_as_certificate=False,
              production_calls=0,callback_errors=monitor.errors))
    finally:m.dispose()

if __name__=='__main__':
    select();canary()
