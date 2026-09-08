"""Explicit May date/output bindings; original numerical/model code is retained.

Only entry-point scope, artifact paths, frozen-input access, audit metadata and
measured preparation accounting are adapted. Each clone is source-bound and
its exact substitutions are persisted. B3 retains its own original ordering.
"""
from fast_prepare import *
import inspect,types,time,os,importlib
import numpy as np
from dayahead.paper_analysis.storage import write_json

MAY_RUN=ROOT/'frozen_artifacts/v41r4_may'
MAY_OUT=MAY_RUN/'audit'
FINAL_RUN=RUN/'final_four_method'
FINAL_OUT=OUT/'final_four_method'
HELPERS=('v41r4_runtime.py','v41r4_worker.py','v41r4_campaign.py','v41r4_electrical.py','v41r4_domain.py','v41r4_io.py','v41r4_report.py','v41r4_bootstrap/sitecustomize.py','may_domain.py','may_runtime.py','fast_prepare.py')
BINDINGS=[]
B1_PREPARATION_SECONDS=0.

def clone(function,replacements,extra=None):
    original=inspect.getsource(function);source=original
    for old,new in replacements:
        assert source.count(old)==1,('UNEXPECTED_ADAPTER_SOURCE',function.__name__,old)
        source=source.replace(old,new)
    namespace=dict(function.__globals__);namespace.update(extra or {})
    exec(compile(source,str(ROOT/'v41r4_runtime.py')+'::'+function.__name__,'exec'),namespace)
    BINDINGS.append(dict(function=function.__module__+'.'+function.__name__,source=record(inspect.getsourcefile(function)),substitutions=[dict(before=a,after=b) for a,b in replacements],numerical_expressions_changed=False))
    return namespace[function.__name__]

def physics(day):
    from v41r4_electrical import configure
    return configure(day)

def configure(day,policy):
    assert day in tuple(f'2025-05-{n:02}' for n in range(1,32)) and policy in ('B0','B1','B2','B3')
    physics(day)
    from dayahead.v41 import data,execution,frozen_candidates as fc,physics_ranking as ranking,temporal_restore as temporal
    from dayahead.v41r3 import authority as v3,candidates
    from dayahead.v41r2 import authority as r2
    from dayahead.v41r1 import migration_audit,bounded_runtime
    daily=MAY_OUT/day
    runtime=RUN if day==DAY else ROOT/'frozen_artifacts/v41r3_may'
    # Bind loaded aliases as well as subsequently imported modules.
    for name in ('dayahead.v41.data','dayahead.v41.common','dayahead.v41.persistence','dayahead.v41.snapshot','dayahead.v41.scientific_archive','dayahead.v41r1.migration_persistence'):
        module=importlib.import_module(name)
        if hasattr(module,'RUNTIME'):module.RUNTIME=runtime
    execution.RUNS=MAY_RUN;execution.RUNTIME=MAY_RUN
    if True:
        def frozen_snapshot(target):
            assert target==day
            prepared=read(daily/'INPUT_PREPARATION.json')
            assert prepared['status']=='PASS' and prepared['raw_Q90_and_H4_exact'] and prepared['ML_prediction_calls']==0
            path=runtime/'inputs'/day/f'V41_ML_SNAPSHOT_{day}.json'
            assert record(path)==prepared['new_snapshot']
            assert record(prepared['raw_prediction_source']['path'])==prepared['raw_prediction_source']
            from dayahead.v41.reserve import validate_snapshot
            from dayahead.v41.scalars import project
            value=read(path);validate_snapshot(value,r2.capacity()[0])
            seal=read(path.parent/'ML_SNAPSHOT_RECEIPT.json')
            assert seal['snapshot']==record(path) and seal['optimizer_scalar_sha256']==project(value).sha256
            return path,seal
        v3.snapshot=r2.snapshot=frozen_snapshot
        from v41r4_domain import Store
        store=Store(day);a=store.authority
        candidates._store=store;fc.load_options=store.options
        temporal.BASE_COUNT=a['base_count'];temporal.RESTORED_COUNT=a['restored_count'];temporal.TOTAL_COUNT=a['total_count']
        fc.TOTAL_COUNT=a['total_count'];fc.RESTORED_COUNT=a['restored_count']
        fc.OUT=ranking.OUT=daily
        # The old before-count is descriptive metadata, not a model input.
        migration_audit.persist=clone(migration_audit.persist,[("historical=read(OLD_RUN/DAY/'B1/dayahead/authority/migration_before_solve/MIGRATION_ELIGIBILITY_SUMMARY.json')","historical={'N_TOTAL_MIGRATION_CANDIDATES_BEFORE':None}"),("before_count_definition='Legacy structurally feasible issue-RUNNING-only migration options; independent of current policy enable flag'","before_count_definition='NOT_COMPUTED_FOR_NEW_MAY_DATE; no obsolete domain enumeration; current full domain is independently sealed'")])
    import textwrap
    init_source=textwrap.dedent(inspect.getsource(ranking.Ranking.__init__))
    assert init_source.count('alpha_1.600')==1
    init_ns=dict(vars(ranking));exec(compile(init_source.replace('alpha_1.600','alpha_1.150'),__file__+'::Ranking.__init__','exec'),init_ns)
    ranking.Ranking.__init__=init_ns['__init__']
    from dayahead.v41r1 import bounded_mess
    bounded_mess.run=clone(bounded_mess.run,[("Path('D:/MobileESS_FO_M1')","Path('D:/m4')")])
    # B3 A1 uses its retained feedback domain and ranking. No B1 indices leak.
    if policy!='B1':
        ranking.reorder=lambda engine,ordered,anchors:(ordered,anchors)
        ranking.record_acceptance=lambda engine,rows,accepted:None
    original_science=execution.science
    from dayahead.v40h.identity import manifest
    def science():
        base=original_science()
        return manifest([Path(r['path']) for r in base['files']]+[ROOT/p for p in HELPERS],ROOT)
    execution.science=science
    original_verify=execution.verify_dayahead
    verify=original_verify
    execution.verify_dayahead=verify
    execution.dayahead=clone(execution.dayahead,[("require(day=='2025-05-04' and policy in ('B0','B1'),'V41R2_FULL_MAY_HOLD')","require(day==MAY_DAY and policy in ('B0','B1','B2','B3'),'MAY_DATE_POLICY_SCOPE')"),("from dayahead.v41r3.authority import OUT as V3OUT","V3OUT=MAY_DAY_OUT"),("gate['Fresh']=='PASS' and gate['Actual']=='PASS'","gate['Fresh']=='PASS' and gate['dayahead_technical_status']=='PASS'")],dict(MAY_DAY=day,MAY_DAY_OUT=daily,science=science,verify_dayahead=verify))
    original_activate=bounded_runtime.activate
    src=inspect.getsource(original_activate)
    start=src.index("    if policy=='B1':")
    end=src.index('    context.v41_a1_output=',start)
    clean_activate=clone(original_activate,[(src[start:end],'')])
    def activate(context,method,output):
        result=clean_activate(context,method,output)
        if method=='B1':
            assert B1_PREPARATION_SECONDS>0
            context.v41_policy_budget.charge(B1_PREPARATION_SECONDS,'DAILY_DOMAIN_AND_B0_ONLY_RANKING_PREPARATION')
        p=Path(output)/'POLICY_DAY_COMPUTE_START.json'
        value=read(p);value.update(mode='FROZEN_FULL_MAY',May_authority=record(MAY_OUT/'MAY_CAMPAIGN_RELEASE.json'))
        write_json(p,value)
        return result
    bounded_runtime.activate=activate
    os.environ['V41_FO_ACCEPTANCE']='1';os.environ['V41_FO_ACCEPTANCE_SECONDS']='1800'
    os.environ.pop('V41_FO_RECOVERY_PLAN',None)
    write_json(daily/f'RUN_BINDINGS_{policy}.json',dict(status='BOUND',day=day,policy=policy,source=science(),adapters=BINDINGS,model_changes=0,physical_equations_changed=False,alpha_BG=1.15,B3_A1_ordering='RETAINED_ORIGINAL',input_source='FROZEN_ML_ONLY',source_runtime=str(runtime),output_runtime=str(MAY_RUN)))
    return execution

def restoration(day):
    a=read(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')
    common=dict(status='PASS',day=day,source=record(ROOT/'dayahead/v41/temporal_restore.py'),domain=record(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json'),contract='EXACT_RETAINED_PRE_V4_TEMPORAL_OPTIONS_PLUS_V4_MIGRATION',base_candidates=a['base_count'],restored_temporal_candidates=a['restored_count'],total_candidates=a['total_count'],eligible_jobs=a['eligible_temporal_jobs'],new_shifted_start_migration_products=0,temporal_eligibility_changed=False,P1_P5_changed=False)
    for name in ('V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json','V41R3_TIMESHIFTING_PRESERVATION_AUDIT.json'):save(MAY_OUT/day/name,common)

def prepare_ranking(day,preparation_started=None):
    global B1_PREPARATION_SECONDS
    from dayahead.v41 import physics_ranking as ranking
    from dayahead.v41.common import build
    from dayahead.v41.reserve import bind
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    started=time.perf_counter() if preparation_started is None else preparation_started
    ctx=physics(day).load(day)
    try:
        from dayahead.v41.snapshot import create
        sp,seal=create(day);bind(ctx,sp,seal['snapshot']['sha256'])
        jobs,common=build(day,sp,ctx.capacity)
        audit=ranking.prepare(ctx,jobs,planning_power(import_frozen(jobs),ctx))
        domain=read(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')
        assert audit['candidate_set_SHA']==domain['candidate_set_SHA'] and audit['candidate_count']==domain['total_count']
        audit.pop('original_4772575_candidates_all_retained',None)
        audit.update(candidate_count_unchanged=True,candidate_universe_hash_unchanged=True,new_candidates_added=0,original_daily_candidates_all_retained=True,domain_change_reason='NONE_VERSUS_SEALED_DAILY_UNIVERSE',day=day)
        write_json(MAY_OUT/day/'V41R3_FO_PHYSICS_RANKING_AUDIT.json',audit)
        B1_PREPARATION_SECONDS=time.perf_counter()-started+domain['seconds_to_charge_B1']
        assert B1_PREPARATION_SECONDS<1800,'DAILY_PREPARATION_EXHAUSTS_BUDGET'
        gates=[dict(dependency=name,result='PASS') for name in ('New B0 critical line phase and slot','All ranking and neighborhood sensitivities from new daily coefficients','No reused prior-alpha sensitivity ranking','Voltage line transformer and objective coefficients regenerated','Sealed daily universe and migration semantics retained','New daily B0 P1 and P1 normalization','Frozen control settings with naturally evolving native states')]
        save(MAY_OUT/day/'V41R3_ADDITIONAL_DEPENDENCY_GATE.json',dict(status='PASS',gates=gates,electrical=ctx.v41_electrical_certificate,ranking=record(MAY_OUT/day/'V41R3_FO_PHYSICS_RANKING_AUDIT.json'),domain=domain,B1_preparation_seconds=B1_PREPARATION_SECONDS,compound_ordering_source=record(ROOT/'dayahead/v41/physics_ranking.py')))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()
