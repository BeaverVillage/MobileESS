"""Scenario AC coefficients, using frozen producer equations for 12 AIDC axes.

MESS columns are explicitly inactive placeholders. This certificate is valid
only when all MESS controls are zero; it cannot authorize a B2/B3 solver.
"""
from pathlib import Path
from dataclasses import replace
from copy import copy
import ast, inspect, sys, os, time, json
import numpy as np
import calibrate as c
import support, physical
sys.path.insert(0,str(c.ROOT))
RUN=support.RUN
DAY=support.DAY

def producer(fn, namespace, sensitivity_name):
    tree=ast.parse(inspect.getsource(fn));changed=0
    for node in ast.walk(tree):
        if isinstance(node,ast.For) and isinstance(node.iter,ast.Call) and isinstance(node.iter.func,ast.Name) and node.iter.func.id=='enumerate':
            if isinstance(node.iter.args[0],ast.Name) and node.iter.args[0].id=='controls' and any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='_apply_control' for statement in node.body for x in ast.walk(statement)):
                node.iter.args[0]=ast.Subscript(value=ast.Name(id='controls',ctx=ast.Load()),slice=ast.Slice(upper=ast.Constant(12)),ctx=ast.Load());changed+=1
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==sensitivity_name for t in node.targets):
            for call in ast.walk(node.value):
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='empty':call.func.attr='zeros'
    assert changed==1,('PRODUCER_SCOPE_DRIFT',fn.__name__,changed)
    ast.fix_missing_locations(tree)
    source=ast.unparse(tree)+'\n'
    target=c.OUT/('B1_ONLY_'+fn.__name__+'.py')
    if target.exists():assert target.read_text(encoding='utf-8')==source
    else:target.write_text(source,encoding='utf-8')
    ns=dict(namespace);exec(compile(tree,str(target),'exec'),ns)
    return ns[fn.__name__],c.record(target)

def identity(label):
    return dict(scenario=label,day=DAY,authority=c.record(c.OUT/'V41R4_PREMAY_EMPIRICAL_UNCERTAINTY_AUTHORITY.json'),
        scenario_arrays=c.record(RUN/'scenarios'/f'{label}.npz'),source=c.record(__file__),
        generators=[c.record(c.ROOT/'dayahead'/n) for n in ('run_v16_3_voltage_candidate.py','run_v16_3_correction.py','v28r2/electrical_subproblem.py','v40e/mapping.py')])

def generate(label,nominal):
    from dayahead import run_v16_3_voltage_candidate as voltage,run_v16_3_correction as current
    from dayahead.v40i.electrical import Meter
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead.v28r2.electrical_subproblem import slot_coefficients
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.paper_analysis.storage import write_json,write_npz
    from dayahead.v40h.numerical_context import FIELDS
    from dayahead.v40a.invariants import digest
    run=RUN/'e'/label
    assert not run.exists(),'PRESERVE_EXISTING_SCENARIO_GENERATION'
    run.mkdir(parents=True);before=identity(label);write_json(run/'PRE_GENERATION_IDENTITY.json',before)
    bg=support.background(label)
    pcc=np.array([v.anchor[:12] for v in nominal.coefficients]);assert all(np.count_nonzero(v.anchor[12:])==0 for v in nominal.coefficients)
    binding,assets=physical.binding(bg,pcc);src=assets.master.parent.parent
    vp=run/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{DAY}.npz'
    meters={k:Meter(k,run) for k in ('voltage','current')}
    vns=dict(vars(voltage));vns['_compile']=meters['voltage'].compiled(voltage._compile)
    cns=dict(vars(current));cns['_compile']=meters['current'].compiled(current._compile)
    vf,vsrc=producer(voltage._anchor_and_sensitivity_day,vns,'h')
    cf,csrc=producer(current._generate_current_day,cns,'sensitivity')
    started=time.perf_counter();previous=Path.cwd()
    try:
        with corrected_mapping():
            print('GENERATE',label,'voltage',flush=True)
            vr=vf(SOURCE_DATA_REPOSITORY,src,bg,pcc.tolist(),binding,DAY,vp)
            print('GENERATE',label,'current',flush=True)
            cr=cf(SOURCE_DATA_REPOSITORY,src,run,DAY,({'plan_kw_96x12':pcc.tolist()},None,bg,binding,vp,None))
    finally:os.chdir(previous)
    ip=run/'data'/f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{DAY}.npz'
    assert all(m.count==2401 and m.nonconverged==0 for m in meters.values())
    coeff=[]
    with np.load(vp) as v,np.load(ip) as i:
        assert not np.count_nonzero(v['sensitivity'][:,12:]) and not np.count_nonzero(i['current_sensitivity_pu_per_control'][:,12:])
        for t in range(96):
            x=slot_coefficients((None,None,bg,binding,None,None),v,i,t)
            assert x.control_names==nominal.coefficients[t].control_names and x.branch_names==nominal.coefficients[t].branch_names
            assert x.branch_limits==nominal.coefficients[t].branch_limits and x.transformer_ratings==nominal.coefficients[t].transformer_ratings
            assert np.array_equal(x.flow_p_matrix,nominal.coefficients[t].flow_p_matrix) and np.array_equal(x.flow_q_matrix,nominal.coefficients[t].flow_q_matrix)
            coeff.append(x)
    pp=run/'PLANNING_COEFFICIENTS.npz'
    arrays={k:np.array([getattr(x,k) for x in coeff]) for k in FIELDS}
    assert all(np.isfinite(a).all() for a in arrays.values())
    write_npz(pp,**arrays,anchor=np.array([x.anchor for x in coeff]),coefficient_SHAs=np.array([x.coefficient_sha256 for x in coeff]))
    tx=np.array([j for j,n in enumerate(coeff[0].branch_names) if n.startswith('transformer.')])
    tp=run/'TRANSFORMER_COEFFICIENTS.npz'
    write_npz(tp,current_constant=arrays['current_constant'][:,tx],current_matrix=arrays['current_matrix'][:,:,tx],
        flow_p_constant=arrays['flow_p_constant'][:,tx],flow_q_constant=arrays['flow_q_constant'][:,tx],
        flow_p_matrix=arrays['flow_p_matrix'][:,tx],flow_q_matrix=arrays['flow_q_matrix'][:,tx])
    assert identity(label)==before
    certificate=dict(status='PASS',scenario=label,day=DAY,inputs=before,outputs={k:c.record(p) for k,p in [('voltage',vp),('current',ip),('planning',pp),('transformer',tp)]},
        measured_SolveSnap_calls={k:m.count for k,m in meters.items()},nonconverged_calls=0,
        generation_seconds=time.perf_counter()-started,operating_point_ac_anchors_new=True,AIDC_sensitivity_axes_generated=12,
        inactive_MESS_control_axes=48,inactive_axis_placeholder='ZERO; MESS MUST BE OFF',valid_policies=['B0','B1'],
        static_branch_ratings_and_topological_flow_matrices_exact_equal_S0=True,
        projected_background_P_Q_PV_bound=True,producer_scope_sources=[vsrc,csrc],
        original_perturbation_equations_and_step_sizes_unchanged=True,ML_execution_count=0,historical_OpenDSS_calls=0,
        B0_only_operating_point=True,May04_Actual_read_count=0)
    write_json(run/'CERTIFICATE.json',certificate)
    print('COEFFICIENT_PASS',label,certificate['generation_seconds'],flush=True)
    return certificate

def load_scenarios():
    from dayahead.v41.electrical import load
    from dayahead.v40h.numerical_context import FIELDS
    nominal=load(DAY);contexts={'S0':nominal}
    for label in ('S1','S2'):
        cert=c.read(RUN/'e'/label/'CERTIFICATE.json');assert cert['status']=='PASS' and cert['inputs']==identity(label)
        for r in cert['outputs'].values():support.verify(r)
        with np.load(cert['outputs']['planning']['path']) as z:
            co=tuple(replace(nominal.coefficients[t],**{k:z[k][t].copy() if k!='branch_limits' else tuple(z[k][t]) for k in FIELDS},coefficient_sha256=str(z['coefficient_SHAs'][t])) for t in range(96))
        ctx=copy(nominal);ctx.coefficients=co
        v=np.load(cert['outputs']['voltage']['path']);i=np.load(cert['outputs']['current']['path'])
        legacy=list(nominal.electrical.legacy_context);legacy[2]=support.background(label);legacy[3],_=physical.binding(legacy[2],np.array([x.anchor[:12] for x in co]));legacy[4]=Path(cert['outputs']['voltage']['path'])
        ctx.electrical=replace(nominal.electrical,legacy_context=tuple(legacy),voltage=v,current=i,voltage_path=Path(cert['outputs']['voltage']['path']),current_path=Path(cert['outputs']['current']['path']))
        contexts[label]=ctx
    return contexts

def main():
    from dayahead.v41.electrical import load
    assert c.read(c.OUT/'V41R4_MAY04_SCENARIO_PREFLIGHT.json')['status']=='PASS'
    nominal=load(DAY)
    results={}
    for label in ('S1','S2'):results[label]=generate(label,nominal)
    certificate=dict(status='PASS',day=DAY,S0=dict(status='EXACT_VALID_REUSE',certificate=nominal.v41_electrical_certificate),
        scenarios={k:c.record(RUN/'e'/k/'CERTIFICATE.json') for k in results},
        scenario_generation_seconds=sum(r['generation_seconds'] for r in results.values()),
        scenario_generation_SolveSnap_calls=sum(sum(r['measured_SolveSnap_calls'].values()) for r in results.values()),
        historical_optimization_calls=0,historical_OpenDSS_calls=0,ML_execution_count=0,MESS='OFF',valid_policies=['B0','B1'],FULL_MAY='HOLD')
    c.save('V41R4_SCENARIO_ELECTRICAL_CERTIFICATE.json',certificate)
    nominal.electrical.voltage.close();nominal.electrical.current.close()

if __name__=='__main__':main()
