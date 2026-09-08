"""Isolated corrected-search outputs; retain original preparation and policies."""
from fast_prepare import *
import time,types,inspect,textwrap,os
from copy import deepcopy
import numpy as np
from dayahead.paper_analysis.storage import write_json

BASE_RUN=ROOT/'frozen_artifacts/v41r4_may'
BASE_OUT=BASE_RUN/'audit'
PREVIOUS_RUN=BASE_RUN/'search_time_v3'
PREVIOUS_OUT=PREVIOUS_RUN/'audit'
MAY_RUN=BASE_RUN/'loop_wall_v4'
MAY_OUT=MAY_RUN/'audit'
LOGS=ROOT/'logs/v41r4_may/loop_wall_v4'
HELPERS=('v41r4_loop_budget.py','v41r4_loop_runtime.py','v41r4_loop_worker.py','v41r4_loop_campaign.py','v41r4_loop_detached.py')

def ranking_cache(day):
    for root in (PREVIOUS_OUT,BASE_OUT):
        if (root/day/'V41R3_RANKING_PHYSICS.npz').exists():return root/day
    return BASE_OUT/day


def verify_old_or_current(day,policy,expected_current=None):
    from dayahead.v41 import execution
    from dayahead.v40h.identity import verify_manifest
    path=MAY_RUN/day/policy/'dayahead/DAYAHEAD_RECEIPT.json'
    receipt=read(path)
    producer=MAY_OUT/day/f'PRODUCER_{policy}.json'
    expected=expected_current
    if expected is None:
        retained=MAY_OUT/day/f'REUSED_DA_PRODUCER_{policy}.json'
        expected=read(retained)['science'] if retained.exists() else read(producer)['science'] if producer.exists() else read(BASE_OUT/'MAY_CAMPAIGN_RELEASE.json')['source']
    assert expected is not None and receipt['science']==expected, 'UNAPPROVED_DA_PRODUCER'
    verify_manifest(expected)
    # The unmodified verifier is retained before installing this runtime.
    fn=types.FunctionType(VERIFY.__code__,dict(VERIFY.__globals__,RUNS=MAY_RUN,science=lambda:expected))
    return fn(day,policy)


from dayahead.v41.execution import verify_dayahead as VERIFY


def configure(day,policy):
    import v41r4_runtime as old
    import v41r4_b3_equivalent as a1
    from dayahead.v41 import execution,physics_ranking as ranking
    from dayahead.v41r1 import bounded_runtime,bounded_solver
    from dayahead.v40h.identity import manifest
    from v41r4_loop_budget import LoopBudget,install,VERSION
    old.MAY_RUN=MAY_RUN;old.MAY_OUT=MAY_OUT
    a1.MAY_RUN=MAY_RUN;a1.MAY_OUT=MAY_OUT
    a1.HELPERS=tuple(dict.fromkeys((*a1.HELPERS,*HELPERS)))
    original_rank_init=ranking.Ranking.__init__
    ex=a1.configure(day,policy) if policy=='B3' else old.configure(day,policy)
    prior_science=execution.science
    def science():
        prior=prior_science()
        return manifest([Path(r['path']) for r in prior['files']]+[ROOT/p for p in HELPERS],ROOT)
    # B1 and B3 intentionally have separate producer manifests. B0/B2 retain
    # their original immutable producers and are verified as such.
    def verify(target,method):
        if method in ('B0','B2'):expected=None
        elif method==policy:expected=science()
        else:
            expected=read(MAY_OUT/target/f'PRODUCER_{method}.json')['science']
        return verify_old_or_current(target,method,expected)
    execution.science=science;execution.verify_dayahead=verify
    # Execution's day entry is a scoped clone with private globals.
    f=execution.dayahead
    execution.dayahead=types.FunctionType(f.__code__,dict(f.__globals__,science=science,verify_dayahead=verify),f.__name__,f.__defaults__,f.__closure__)
    install()
    original_activate=bounded_runtime.activate
    def activate(ctx,method,out):
        value=original_activate(ctx,method,out)
        if method=='B1':
            previous=ctx.v41_policy_budget;ctx.v41_policy_budget=LoopBudget(1800.)
            for row in previous.calls:ctx.v41_policy_budget.charge(row['seconds'],row['stage'])
        p=Path(out)/'POLICY_DAY_COMPUTE_START.json';r=read(p)
        if method in ('B1','B3'):
            r.update(search_budget_contract=VERSION,actual_AIDC_search_budget_seconds=1800,
                AIDC_budget_basis='Continuous F&O loop wall clock from first stage entry',
                loop_ranking_validation_persistence_overhead_charged=True,one_time_model_preparation_excluded=True,
                stage_stop='Original P1-P5 wall-clock allocations; repeat all no-improvement sweeps until deadline',
                automatic_repeat_after_stagnation=False,May_authority=record(MAY_OUT/'MAY_CAMPAIGN_RELEASE_V4.json'))
            write_json(p,r)
        return value
    bounded_runtime.activate=activate
    if policy=='B3':
        from dayahead.v40h import feedback
        original_feedback=feedback.solve_feedback
        def feedback_search(current,mess,ctx):
            previous=bounded_solver.PolicyBudget;bounded_solver.PolicyBudget=LoopBudget
            try:return original_feedback(current,mess,ctx)
            finally:bounded_solver.PolicyBudget=previous
        feedback.solve_feedback=feedback_search
    original_finish=bounded_runtime.finish
    def finish(ctx,out):
        original_finish(ctx,out)
        if policy not in ('B1','B3'):return
        budget=ctx.v41_policy_budget if policy=='B1' else ctx.v41_a1_budget
        assert isinstance(budget,LoopBudget)
        assert budget.used==1800. and budget.loop_stopped is not None, 'AIDC_SEARCH_LOOP_ENDED_BEFORE_1800_SECONDS'
        assert len(budget.stages)==5, 'LEXICOGRAPHIC_STAGE_COUNT_CHANGED'
        report=budget.report();p=Path(out)/'POLICY_DAY_COMPUTE_REPORT.json';value=read(p)
        value.update(AIDC_search=report,AIDC_search_loop_wall_seconds=budget.used,
            effective_search_budget_seconds=1800,search_budget_contract=VERSION,
            optimization_seconds_semantics='B1: continuous loop wall clock; B3: original M1/MF budget plus independent A1 loop wall clock',
            per_stage_termination=[dict(stage=s['stage'],reason=s['termination_reason'],
                complete_no_improvement_sweeps_after_last_material=s.get('complete_no_improvement_sweeps_after_last_material',0)) for s in budget.stages],
            automatic_repeat_after_stagnation=False)
        write_json(p,value);write_json(Path(out)/'SEARCH_LOOP_WALL_CLOCK_AUDIT.json',report)
    bounded_runtime.finish=finish
    if policy=='B1' and (ranking_cache(day)/'V41R3_RANKING_PHYSICS.npz').exists():
        # Reuse existing exact sensitivities, rebuilding only the transient
        # option-index arrays which were not serialized by the old release.
        source=textwrap.dedent(inspect.getsource(original_rank_init)).replace('alpha_1.600','alpha_1.150')
        start=source.index('    self.S=np.empty(');end=source.index('    order=sorted(',start)
        replacement="    with np.load(CACHED_RANKING) as cached:self.S=cached['S'].copy()\n    assert self.S.shape==(96,len(line),12)\n"
        source=source[:start]+replacement+source[end:]
        ns=dict(original_rank_init.__globals__,OUT=MAY_OUT/day,CACHED_RANKING=ranking_cache(day)/'V41R3_RANKING_PHYSICS.npz')
        exec(compile(source,__file__+'::cached_ranking_init','exec'),ns)
        ranking.Ranking.__init__=ns['__init__']
    producer=MAY_OUT/day/f'PRODUCER_{policy}.json'
    if producer.exists():assert read(producer)['science']==science()
    else:save(producer,dict(status='BOUND',day=day,policy=policy,science=science(),budget_contract=VERSION))
    return ex


def prepare_ranking(day,started=None):
    import v41r4_runtime as old
    from dayahead.v41 import physics_ranking as ranking
    from dayahead.v41.common import build
    from dayahead.v41.reserve import bind
    from dayahead.v41.snapshot import create
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from v41r4_electrical import configure as physics
    before=time.perf_counter()
    previous=ranking_cache(day)/'V41R3_FO_PHYSICS_RANKING_AUDIT.json'
    if not previous.exists():
        from v41r4_loop_budget import adapted
        fn=adapted(old.prepare_ranking,[("assert B1_PREPARATION_SECONDS<1800,'DAILY_PREPARATION_EXHAUSTS_BUDGET'",'assert B1_PREPARATION_SECONDS>=0')])
        fn(day,started);old.B1_PREPARATION_SECONDS=fn.__globals__['B1_PREPARATION_SECONDS']
        return
    ctx=physics(day).load(day)
    try:
        path,seal=create(day);bind(ctx,path,seal['snapshot']['sha256'])
        jobs,_=build(day,path,ctx.capacity);prior=read(previous)
        assert prior['electrical']==ctx.v41_electrical_certificate and prior['status']=='PASS'
        domain=read(BASE_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')
        ranking.INSTANCE=ranking.Ranking(ctx,jobs,planning_power(import_frozen(jobs),ctx))
        r=ranking.INSTANCE
        assert r.count==domain['total_count']==prior['candidate_count']
        assert r.domain_digest.hexdigest()==domain['candidate_set_SHA']==prior['candidate_set_SHA']
        assert dict(line=r.line[r.jstar],phase=r.phase[r.jstar],slot=r.tstar)==prior['critical']
        for name in ('V41R3_FO_PHYSICS_RANKING_AUDIT.json','V41R3_RANKING_PHYSICS.npz',
            'V41R3_B0_RESTORED_OBJECTIVE.json','V41R3_ADDITIONAL_DEPENDENCY_GATE.json'):
            copy(ranking_cache(day)/name,MAY_OUT/day/name)
        old.B1_PREPARATION_SECONDS=max(1e-9,time.perf_counter()-before)
        save(MAY_OUT/day/'PREPARATION_REUSE_AUDIT.json',dict(status='PASS',
            candidate_universe_exact=True,ranking_unchanged=True,coefficient_generation_calls=0,
            reused_sensitivities=record(ranking_cache(day)/'V41R3_RANKING_PHYSICS.npz'),
            reused_domain=record(BASE_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json'),
            reused_electrical=ctx.v41_electrical_certificate,
            transient_metadata_rehydration_seconds=old.B1_PREPARATION_SECONDS,charged_search_seconds=0,
            serialized_model_note='MPS retained; Python factor/decoder/validator bindings must be reconstructed without changing the model'))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()


def recovery(day):
    os.environ.pop('V41_FO_RECOVERY_PLAN',None)
    save(MAY_OUT/day/'B1_COLD_START_AUTHORITY.json',dict(status='FROZEN',
        initialization='Same-day B0 reference; no previous B1 incumbent',
        B0=record(MAY_RUN/day/'B0/dayahead/DAYAHEAD_RECEIPT.json'),previous_B1_reuse=False))
    return None



def install_reports():
    import v41r4_report as reports
    import v41r4_readback_v2 as reader
    reports.MAY_RUN=reader.MAY_RUN=MAY_RUN;reports.MAY_OUT=reader.MAY_OUT=MAY_OUT
    reader.install()
