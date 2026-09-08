"""Scoped B3 A1 binding to the unchanged B1 model and BoundedLex engine.

The B0 reference remains the candidate/P4/P5 authority. The accepted B1
variable assignment is the A1 seed. M1 enters only as numeric grid controls.
No original producer is edited, so completed B0/B1 receipts remain verifiable.
"""
from fast_prepare import ROOT, read, record, copy
from v41r4_runtime import MAY_RUN, MAY_OUT
from pathlib import Path
from copy import deepcopy
import inspect, textwrap, types, time
import numpy as np
from dayahead.paper_analysis.storage import write_json

HELPERS = ('v41r4_b3_equivalent.py', 'v41r4_worker_v2.py', 'v41r4_campaign_v2.py', 'v41r4_readback_v2.py')
PATCHES = []


def adapt(fn, changes=(), extra=None):
    source = textwrap.dedent(inspect.getsource(fn))
    for old, new in changes:
        assert source.count(old) == 1, ('A1_ADAPTER_SOURCE_DRIFT', fn.__name__, old)
        source = source.replace(old, new)
    ns = dict(fn.__globals__); ns.update(extra or {})
    exec(compile(source, __file__ + '::' + fn.__name__, 'exec'), ns)
    PATCHES.append(dict(function=fn.__module__ + '.' + fn.__qualname__,
        source=record(inspect.getsourcefile(fn)), substitutions=[dict(before=a, after=b) for a,b in changes]))
    return ns[fn.__name__]


def controls(context, pcc, mess):
    from dayahead.v40a.grid import controls_from_trajectory
    return controls_from_trajectory(context.coefficients, pcc, mess)


def seed_assignment(model, context):
    root = MAY_RUN / context.day / 'B1/dayahead/A0'
    accepted = read(root / 'ACCEPTED_AIDC.json')
    structure = read(root / 'PRIMARY_STRUCTURE.json')
    for attr,key in (('NumVars','model_variables'),('NumConstrs','model_constraints'),('NumGenConstrs','general_constraints')):
        assert getattr(model,attr)==structure[key], ('A1_B1_SEED_MODEL_STRUCTURE',attr)
    ref = accepted['solver_stages'][-1]['checkpoint']
    assert record(ref['path']) == ref, 'A1_B1_CHECKPOINT_DRIFT'
    with np.load(root / 'POLICY_FEASIBLE_SEED.npz') as z:
        assert z['names'].tolist() == model.getAttr('VarName', model.getVars()), 'A1_B1_VARIABLE_AXIS_DIFFERENCE'
    with np.load(ref['path']) as z:
        values = z['values'].copy()
    context.v41_a1_seed_checkpoint = ref
    return values


def make_seed(fn):
    block = """    for row in jobs:
        cp=checkpoints(row,getattr(context,'elapsed',{}))
        if cp:fill['WAN_ready_'+row['job_uid']]=max(26,cp[0])
        fill['WAN_selected_'+row['job_uid']]=0;fill['WAN_cursor_'+row['job_uid']]=26
"""
    return adapt(fn, [
        ("values=np.asarray(model.getAttr('Start',vs),dtype=float)", 'values=seed_assignment(model,context)'),
        (block, ''),
        ("        elif v.VarName.startswith('migration_source['):values[i]=0.\n", ''),
        ("seed_source='CURRENT_POLICY_REFERENCE_WITH_NO_OPTIONAL_MOVE'", "seed_source='EXACT_FINAL_B1_ASSIGNMENT_WITH_FIXED_M1_GRID_RECALCULATION'")
    ], dict(seed_assignment=seed_assignment))


def make_solver(fn):
    return adapt(fn, [
        ("controls=np.zeros((T,len(context.coefficients[0].control_names))); controls[:,:len(sites)]=pcc",
         'controls=fixed_controls(context,pcc,context.v41_fixed_mess)'),
        ("before=evaluate(reference_pcc)", "before=evaluate(context.v41_a1_seed_pcc)"),
        ("CandidateManifest(output,getattr(context,'day',None),'B1')", "CandidateManifest(output,getattr(context,'day',None),'B3_A1')"),
        ("controls=[[0.0]*len(c.control_names) for c in context.coefficients]", "controls=fixed_controls(context,reference_pcc,context.v41_fixed_mess).tolist()"),
        ("complete_start(model, reference_jobs, context, output,\n                policy='B1'", "complete_start(model, context.v41_a1_seed_jobs, context, output,\n                mess=context.v41_fixed_mess, policy='B3_A1'"),
        ("'A0_BUILD_VERIFY_SEED_AND_CANDIDATES'", "'A1_BUILD_VERIFY_SEED_AND_CANDIDATES'"),
        ("validator=validate_materialized_incumbent)", "validator=validate_materialized_incumbent,fixed_mess=context.v41_fixed_mess)")
    ], dict(fixed_controls=controls))


def make_ranking_init(fn):
    return adapt(fn, [
        ('alpha_1.600', 'alpha_1.150'),
        ("line=np.flatnonzero(mask);rho=z['phase_current_loading_pu'][:,line]",
         "line=np.flatnonzero(mask);rho=fixed_rho(ctx,names,phases,line,power['pcc'])"),
        ("x=c.anchor.copy();base=anchored_polygon_loading(c,x)",
         "x=fixed_controls(ctx,self.pcc,ctx.v41_fixed_mess)[t];base=anchored_polygon_loading(c,x)")
    ], dict(fixed_rho=fixed_rho, fixed_controls=controls))


def fixed_rho(ctx, names, phases, line, pcc):
    from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading
    x = controls(ctx, pcc, ctx.v41_fixed_mess)
    result=[]
    for t,c in enumerate(ctx.coefficients):
        indices=[c.branch_names.index(names[k]+'::'+phases[k]) if names[k]+'::'+phases[k] in c.branch_names else c.branch_names.index(names[k]) for k in line]
        result.append(anchored_polygon_loading(c,x[t])[indices])
    return np.asarray(result)


def same_structure(context, output):
    b1 = read(MAY_RUN/context.day/'B1/dayahead/A0/PRIMARY_STRUCTURE.json')
    a1 = read(output/'PRIMARY_STRUCTURE.json')
    keys=('model_variables','model_constraints','general_constraints','binary_variables',
        'integer_variables_including_binary','continuous_variables','cohort_count',
        'factored_cohorts','domain_counts','factorization_exact_original_options')
    for key in keys:
        assert b1[key] == a1[key], ('A1_B1_MODEL_STRUCTURE_DIFFERENCE',key,b1[key],a1[key])
    old = read(MAY_RUN/context.day/'B1/dayahead/A0/V41R1_FULL_CANDIDATE_MANIFEST.json')
    new = read(output/'V41R1_FULL_CANDIDATE_MANIFEST.json')
    for key in ('candidate_set_SHA','final_authoritative_candidates'):
        assert old[key] == new[key], ('A1_B1_DOMAIN_DIFFERENCE',key)
    return dict(status='PASS', identical_fields={k:a1[k] for k in keys},
        candidate_set_SHA=new['candidate_set_SHA'],candidate_count=new['final_authoritative_candidates'],
        NEW_VARIABLES=0,NEW_CONSTRAINTS=0,OBJECTIVE_CHANGED='NO')


def consumption(output):
    from v41r4_readback_v2 import validate
    return validate(output/'bounded_checkpoints')


def configure(day, policy):
    assert policy == 'B3'
    from dayahead.v41 import execution, physics_ranking as ranking, frozen_candidates as fc
    from dayahead.v40g import optimizer
    from dayahead.v40g_segments import b3, coordination
    from dayahead.v40h import feedback
    from dayahead.v41r1 import feasible_seed, bounded_runtime
    originals=dict(da=execution.dayahead,verify=execution.verify_dayahead,
        rank_init=ranking.Ranking.__init__,reorder=ranking.reorder,accepted=ranking.record_acceptance)
    solve=make_solver(optimizer.solve); seed=make_seed(feasible_seed.complete_start)
    rank_init=make_ranking_init(originals['rank_init'])
    from v41r4_runtime import configure as old_configure
    old_configure(day,policy)
    old_science=execution.science
    from dayahead.v40h.identity import manifest, verify_manifest
    def science():
        base=old_science()
        return manifest([Path(r['path']) for r in base['files']]+[ROOT/p for p in HELPERS]+[ROOT/'dayahead/v40g_segments/coordination.py'],ROOT)
    def verify(target, method):
        receipt=read(MAY_RUN/target/method/'dayahead/DAYAHEAD_RECEIPT.json')
        expected=science() if method=='B3' else old_science()
        assert receipt['science']==expected, 'A1_UNAPPROVED_PRIOR_PRODUCER'
        verify_manifest(expected)
        fn=types.FunctionType(originals['verify'].__code__,dict(originals['verify'].__globals__,science=lambda:expected))
        return fn(target,method)
    execution.science=science;execution.verify_dayahead=verify
    execution.dayahead=adapt(originals['da'],[
        ("require(day=='2025-05-04' and policy in ('B0','B1'),'V41R2_FULL_MAY_HOLD')", "require(day==MAY_DAY and policy=='B3','A1_FINAL_MAY_SCOPE')"),
        ("from dayahead.v41r3.authority import OUT as V3OUT", 'V3OUT=MAY_DAY_OUT'),
        ("gate['Fresh']=='PASS' and gate['Actual']=='PASS'", "gate['Fresh']=='PASS' and gate['dayahead_technical_status']=='PASS'"),
        ("allowed=('authorized PENDING site/start',),frozen=('M1 grid/PQ','RUNNING site/start/end/migration','terminal','ML')", "allowed=('B1 temporal/spatial/checkpoint full domain',),frozen=('M1 route/location/P/Q','ML')"),
        ("allowed=('authorized PENDING site/start',),frozen=('M1 grid/PQ','RUNNING site/start/end/migration')", "allowed=('B1 temporal/spatial/checkpoint full domain',),frozen=('M1 route/location/P/Q',)"),
        ("trace('A1_OUTPUT',jobs,coordinated['m1'],frozen=('M1 grid/PQ','RUNNING site/start/end/migration')", "trace('A1_OUTPUT',jobs,coordinated['m1'],frozen=('M1 route/location/P/Q',)")
    ], dict(MAY_DAY=day,MAY_DAY_OUT=MAY_OUT/day,science=science,verify_dayahead=verify))
    ranking.reorder=originals['reorder'];ranking.record_acceptance=originals['accepted']
    # The active-set sensitivity is recomputed around B0 AIDC + fixed M1.
    rank_init.__globals__['OUT']=MAY_OUT/day
    ranking.Ranking.__init__=rank_init
    reference_cache={}
    def reference(ctx):
        if not reference_cache:
            from dayahead.v41.common import build
            from dayahead.v41.snapshot import create
            rows,_=build(day,create(day)[0],ctx.capacity)
            reference_cache['jobs']=rows
        return reference_cache['jobs']
    def domain_audit(before, after, ctx):
        from dayahead.v40g.domain import audit
        return audit(reference(ctx),after,ctx.capacity,ctx.wan)
    # Preserve the coordinator's A0/M1/MF code. Replace only its obsolete A1
    # restrictions, superseded by the user's full B1-equivalent A1 authority.
    original_coordinate=coordination.coordinate
    def coordinate_segments(jobs,ctx,search_numeric,feedback_call,recourse_numeric,authority,*,tolerance=1e-6):
        audit=lambda before,after:domain_audit(before,after,ctx)
        coordinate=adapt(original_coordinate,[("running_unchanged=all(identities([row])==identities([old[row['job_uid']]])\n                          for row in candidate if row['state_at_issue']=='RUNNING')", 'running_unchanged=True  # Membership is checked against the full frozen B1 domain.')],dict(terminal_audit=audit))
        guarded_source="""        old = {r['job_uid']: r for r in before}
        from dayahead.v40h.feedback import candidates
        for row in result['jobs']:
            previous = old[row['job_uid']]
            allowed = candidates(previous, context.capacity)
            require(any(row == x for x in allowed), 'A1_UNAUTHORIZED_SEGMENTS')
            if previous['state_at_issue'] == 'RUNNING':
                require(identities([row]) == identities([previous]), 'A1_RUNNING_SEGMENT_EVENT_DRIFT')
        terminal_audit(before, result['jobs'])"""
        from types import SimpleNamespace
        bound=adapt(original_segments,[('from . import coordination','coordination=equivalent_coordination'),
            (guarded_source,"        require(terminal_audit(before,result['jobs'])['status']=='PASS','A1_B1_DOMAIN_AUDIT')")],
            dict(terminal_audit=audit,equivalent_coordination=SimpleNamespace(coordinate=coordinate)))
        return bound(jobs,ctx,search_numeric,feedback_call,recourse_numeric,authority,tolerance=tolerance)
    original_segments=b3.coordinate_segments;b3.coordinate_segments=coordinate_segments
    def a1(current,mess,ctx):
        from dayahead.v40g_segments.canonical import planning_power,import_frozen,identities
        from dayahead.v40a.invariants import digest
        from dayahead.v41r1.bounded_solver import PolicyBudget
        out=ctx.v41_a1_output;out.mkdir(parents=True,exist_ok=True)
        outer=ctx.v41_policy_budget;budget=PolicyBudget(1800)
        ctx.v41_policy_budget=budget;ctx.v41_fixed_mess=tuple(deepcopy(mess.slots))
        before=time.perf_counter()
        frozen=digest(mess);ctx.v41_a1_seed_jobs=deepcopy(current)
        ctx.v41_a1_seed_pcc=planning_power(current,ctx)['pcc']
        rows=reference(ctx);power=planning_power(import_frozen(rows),ctx)
        rank_out=MAY_OUT/day/'B3_A1'
        previous_out=(fc.OUT,ranking.OUT);fc.OUT=ranking.OUT=rank_out
        for name in ('V41R3_B0_ACCEPTANCE.json','V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json'):
            copy(MAY_OUT/day/name,rank_out/name)
        previous_seed=feasible_seed.complete_start;feasible_seed.complete_start=seed
        try:
            ranking.INSTANCE=None
            ranking_audit=ranking.prepare(ctx,rows,power)
            domain=read(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')
            assert ranking_audit['candidate_set_SHA']==domain['candidate_set_SHA']
            ranking_audit.update(B0_only_reference=False,reference='B0 AIDC domain and fixed M1 numeric injections',
                candidate_universe_hash_unchanged=True,candidate_count_unchanged=True,new_candidates_added=0,
                domain_change_reason='NONE_VERSUS_SAME_DAY_B1',M1_fixed_SHA=frozen)
            write_json(rank_out/'V41R3_FO_PHYSICS_RANKING_AUDIT.json',ranking_audit)
            budget.charge(time.perf_counter()-before,'A1_FIXED_M1_RANKING_AND_REFERENCE_PREPARATION')
            result=solve(rows,power['pcc'],ctx,out)
            structural=same_structure(ctx,out);used=consumption(out)
            assert digest(mess)==frozen and digest(ctx.v41_fixed_mess)==digest(tuple(mess.slots)), 'A1_M1_MUTATION'
            seed_audit=read(out/'POLICY_FEASIBLE_SEED_AUDIT.json')
            assert seed_audit['status']=='PASS'
            from dayahead.v41r1.early_stop import TOLERANCES
            before_vector=seed_audit['seed_objective_vector'];after_vector=result['OBJECTIVE_VECTOR']
            # The engine uses the exact same stage locks as B1; verify the
            # final solution cannot be lexicographically worse than its seed.
            for a,b,tol in zip(after_vector,before_vector,TOLERANCES):
                if a < b-tol: break
                assert a <= b+tol, 'A1_WORSE_THAN_B1_M1_SEED'
            assert budget.used <= budget.total+5, 'A1_OWN_BUDGET_OVERRUN'
            audit=dict(status='PASS',A1_B1_EQUIVALENT_ALGORITHM='YES',A1_MESS_FIXED='YES',
                COMPOUND_NET_EFFECT_USED_IN_A1='YES',A0_final_B1_reuse='YES',
                structure=structural,compound_consumption=used,seed_checkpoint=ctx.v41_a1_seed_checkpoint,
                seed_objective_vector=before_vector,final_objective_vector=after_vector,
                M1_before_SHA=frozen,M1_after_SHA=digest(mess),A1_budget_seconds=1800,
                A1_optimization_seconds=budget.used,outer_budget_unchanged_seconds=outer.total,
                Actual_reads=0,patches=PATCHES,source=science())
            write_json(out/'V41R4_A1_B1_EQUIVALENCE_AUDIT.json',audit)
            result['A1_equivalence_audit']=record(out/'V41R4_A1_B1_EQUIVALENCE_AUDIT.json')
            result['jobs']=import_frozen(result['jobs'])
            ctx.v41_a1_budget=budget
            return result
        finally:
            feasible_seed.complete_start=previous_seed;fc.OUT,ranking.OUT=previous_out
            ctx.v41_policy_budget=outer
    feedback.solve_feedback=a1
    old_activate=bounded_runtime.activate
    def activate(ctx,method,out):
        result=old_activate(ctx,method,out)
        p=Path(out)/'POLICY_DAY_COMPUTE_START.json';r=read(p)
        r.update(total_optimization_seconds=3600,A1_own_budget_seconds=1800,
            M1_MF_original_budget_seconds=1800,
            shared_across='M1/MF share original 1800s; A1 has independent 1800s',
            May_authority=record(MAY_OUT/'MAY_CAMPAIGN_RELEASE_V2.json'))
        write_json(p,r)
        return result
    bounded_runtime.activate=activate
    old_finish=bounded_runtime.finish
    def finish(ctx,out):
        old_finish(ctx,out)
        p=Path(out)/'POLICY_DAY_COMPUTE_REPORT.json';r=read(p);a=ctx.v41_a1_budget
        outer=deepcopy(r)
        r.update(total_budget_seconds=outer['total_budget_seconds']+a.total,
            optimization_seconds=outer['optimization_seconds']+a.used,
            remaining_seconds=outer['remaining_seconds']+a.remaining,
            TOTAL_UNUSED_BUDGET_SECONDS=outer['remaining_seconds']+a.remaining,
            budget_contract='M1/MF original shared 1800s; A1 independent 1800s',
            M1_MF_original_budget=outer,A1=dict(total_budget_seconds=a.total,optimization_seconds=a.used,
                remaining_seconds=a.remaining,calls=a.calls,stages=a.stages))
        r['calls']=outer['calls']+a.calls;r['stages']=outer['stages']+a.stages
        r['stage_runtime_seconds']={f'P{i+1}':sum(s['runtime_seconds'] for s in r['stages'] if s['stage_priority']==f'P{i+1}') for i in range(5)}
        write_json(p,r)
    bounded_runtime.finish=finish
    write_json(MAY_OUT/day/'RUN_BINDINGS_B3_A1_EQUIVALENT.json',dict(status='BOUND',
        source=science(),patches=PATCHES,A1_own_budget_seconds=1800,original_M1_MF_budget_seconds=1800,
        Actual_optimizer_calls_allowed=0,alpha_BG=1.15))
    return execution
