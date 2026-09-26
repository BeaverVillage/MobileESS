"""Original V41R4 AIDC semantics with explicit IEEE8500 electrical ports.

This reconstruction release deliberately has no executable optimization entry.
Production activation requires a later separately authorized preflight/release.
"""
import ast,contextlib,copy,hashlib,inspect,types
from pathlib import Path
import numpy as np
from frozen_binding import ROOT,HOME,read,record,sha,save,option_reader,EXPECTED
STUDY=dict(day='2025-05-01',source_pu=1.0400,Vreg_V=123.5,alpha8500=.54688,CAPBank3='OFF',AIDC_wall_clock_seconds=14400)

def production_entry(*args,**kwargs):
    raise RuntimeError('BINDING_RECONSTRUCTION_ONLY_PRODUCTION_OPTIMIZATION_NOT_AUTHORIZED')

def electrical_port_contract():
    inventory=read(HOME/'PCC_OVERLAY_INVENTORY.json')
    by={(r['PCC_role'],r['location_id']):r for r in inventory}
    aidc=[f'AIDC{i:02}' for i in range(1,13)];services=[f'IDC{i:02}' for i in range(1,13)]+[f'STA{i:02}' for i in range(1,13)]
    rows=[]
    for i,s in enumerate(aidc):
        r=by['AIDC',s];assert r['rating_kva']==1500 and r['phases']==3
        rows.append(dict(axis=i,role='AIDC',logical=s,host=r['host_bus'],PCC=r['PCC_bus'],control_name=f'aidc_load_kw[{s}]',reactive='FROZEN_PF_TAN_TIMES_P_NOT_NEW_AIDC_Q_DECISION'))
    for k,q in enumerate(('p_kw','q_kvar')):
        for j,s in enumerate(sorted(services)):
            location='A'+s if s.startswith('IDC') else s;r=by['MESS',location]
            assert r['rating_kva']==750 and r['phases']==3
            rows.append(dict(axis=12+24*k+j,role='MESS',logical=s,location_id=location,host=r['host_bus'],PCC=r['PCC_bus'],control_name=f'mess_{q}[{s}]'))
    assert len(rows)==60 and len({r['control_name'] for r in rows})==60
    return dict(classification='AUTHORIZED_ELECTRICAL_DIFFERENCE',settings=STUDY,control_axis=rows,AIDC_decisions='Original first 12 PCC active power variables; Q follows original PF.',MESS_service_alias='Road IDCxx is mapped to electrical AIDCxx only at the PCC boundary.',numerical_coefficient_reuse_from_stopped_production=False,numerical_coefficient_payload_in_this_release=None,numerical_grid_and_AC_validation='NOT_PERFORMED_IN_BINDING_RECONSTRUCTION',production_execution_allowed=False)

def validate_electrical_payload(ctx):
    """Future numerical payload must expose the existing V41R4 coefficient API."""
    contract=electrical_port_contract();names=tuple(r['control_name'] for r in contract['control_axis'])
    assert len(ctx.coefficients)==96
    required=('voltage_constant','voltage_matrix','current_constant','current_matrix','flow_p_constant','flow_p_matrix','flow_q_constant','flow_q_matrix','branch_names','branch_limits','transformer_ratings','anchor','coefficient_sha256')
    for c in ctx.coefficients:
        assert tuple(c.control_names)==names
        for key in required:assert hasattr(c,key),key
        assert np.shape(c.voltage_matrix)==(60,len(c.voltage_constant))
        assert np.shape(c.current_matrix)==(60,len(c.branch_names))
        assert np.shape(c.flow_p_matrix)==np.shape(c.flow_q_matrix)==(len(c.branch_names),60)
        assert len(c.anchor)==60
    return contract

def compile_B1(ctx):
    from dayahead.v40g import optimizer
    # Function bytecode and source unchanged; only the frozen input port differs.
    f=types.FunctionType(optimizer.solve.__code__,dict(optimizer.solve.__globals__,options=option_reader(ctx)),optimizer.solve.__name__,optimizer.solve.__defaults__,optimizer.solve.__closure__)
    f.__kwdefaults__=copy.deepcopy(optimizer.solve.__kwdefaults__)
    return f

def compile_A1(ctx):
    from dayahead.v40g import optimizer
    from v41r4_b3_equivalent import make_solver
    f=make_solver(optimizer.solve)
    f.__globals__['options']=option_reader(ctx)
    return f

def compile_objectives(ctx):
    from dayahead.v41 import objectives
    f=types.FunctionType(objectives.evaluate.__code__,dict(objectives.evaluate.__globals__,options=option_reader(ctx)),objectives.evaluate.__name__,objectives.evaluate.__defaults__,objectives.evaluate.__closure__)
    f.__kwdefaults__=copy.deepcopy(objectives.evaluate.__kwdefaults__)
    return f

def compile_A1_seed():
    from dayahead.v41r1.feasible_seed import complete_start
    from v41r4_b3_equivalent import make_seed
    f=make_seed(complete_start)
    f.__globals__['seed_assignment']=validated_B1_assignment
    return f

def validated_B1_assignment(model,ctx):
    """Require fresh final B1 evidence supplied by the new run, never old output."""
    bundle=ctx.ieee8500_final_B1_seed
    assert bundle['status'] in ('FINAL_B1_INDEPENDENTLY_VALIDATED','FINAL_B3_A1_INDEPENDENTLY_VALIDATED')
    assert bundle['candidate_stream_sha256']==EXPECTED
    assert bundle['binding_gate_sha256']==sha(HOME/'IEEE8500_V41R4_AIDC_BINDING_PASS.json')
    allowed=Path(ctx.new_production_root).resolve()
    assert allowed==HOME.resolve() and read(HOME/'PRODUCTION_AUTHORIZATION.json')['authorized'] is True
    paths=[]
    for key in ('assignment','variable_names'):
        r=bundle[key];p=Path(r['path']).resolve();assert p.is_relative_to(allowed) and sha(p)==r['sha256'];paths.append(p)
    with np.load(paths[1],allow_pickle=False) as z:assert z['names'].tolist()==model.getAttr('VarName',model.getVars())
    with np.load(paths[0],allow_pickle=False) as z:values=z['values'].copy()
    assert len(values)==model.NumVars
    ctx.v41_a1_seed_checkpoint=bundle['assignment']
    return values

def wall_clock_budget(clock=None):
    """Original continuous LoopBudget; only total allocation is 14,400 s."""
    from v41r4_loop_budget import LoopBudget
    b=LoopBudget(1800.,clock=clock)
    assert b.loop_started is None and b.used==0
    b.total=14400.;b.stage_deadline=14400.
    return b

@contextlib.contextmanager
def original_solver_binding(ctx,role,output):
    """Assemble original B1/A1 engines; caller must not invoke during this stage."""
    assert role in ('B1','B3_A1')
    from dayahead.v41r1 import bounded_solver,feasible_seed
    from v41r4_loop_budget import engine
    prior=(bounded_solver.BoundedLex,feasible_seed.complete_start,getattr(ctx,'v41_policy_budget',None))
    ctx.v41_policy_budget=wall_clock_budget()
    bounded_solver.BoundedLex=engine
    if role=='B3_A1':feasible_seed.complete_start=compile_A1_seed()
    try:
        with bind_frozen_domain(ctx,output):yield compile_B1(ctx) if role=='B1' else compile_A1(ctx)
    finally:bounded_solver.BoundedLex,feasible_seed.complete_start,ctx.v41_policy_budget=prior

@contextlib.contextmanager
def bind_frozen_domain(ctx,output):
    """Bind already-materialized full tuples without regenerating options."""
    from dayahead.v41 import frozen_candidates as fc,temporal_restore as tr
    old=(fc.options,fc.CandidateManifest,tr.BASE_COUNT,tr.RESTORED_COUNT,tr.TOTAL_COUNT)
    manifest=read(ROOT/'frozen_artifacts/v41r4_may/audit/2025-05-01/domain/combined/V41R1_FULL_CANDIDATE_MANIFEST.json')
    metadata={r['job_id']:r for r in manifest['jobs']}
    class FrozenManifest:
        def __init__(self,folder,day,policy):assert day==ctx.day;self.seen=set()
        def add(self,row,opts):
            uid=row['job_uid'];assert row==ctx.references[uid] and opts==ctx.options[uid] and uid not in self.seen;self.seen.add(uid);return metadata[uid]
        def finish(self):assert self.seen==set(ctx.options);return copy.deepcopy(manifest)
    fc.options=option_reader(ctx);fc.CandidateManifest=FrozenManifest
    tr.BASE_COUNT=7382225;tr.RESTORED_COUNT=181464;tr.TOTAL_COUNT=7563689
    try:
        with tr.activate():yield
    finally:fc.options,fc.CandidateManifest,tr.BASE_COUNT,tr.RESTORED_COUNT,tr.TOTAL_COUNT=old
