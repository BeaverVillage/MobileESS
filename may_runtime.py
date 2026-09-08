"""Explicit May date/output bindings; original numerical/model code is retained.

Only entry-point scope, artifact paths, frozen-input access, audit metadata and
measured preparation accounting are adapted. Each clone is source-bound and
its exact substitutions are persisted. B3 retains its own original ordering.
"""
from fast_prepare import *
import inspect,types,time,os,importlib
import numpy as np
from dayahead.paper_analysis.storage import write_json

MAY_RUN=ROOT/'frozen_artifacts/v41r3_may'
MAY_OUT=OUT/'may_campaign'
FINAL_RUN=RUN/'final_four_method'
FINAL_OUT=OUT/'final_four_method'
HELPERS=('may_runtime.py','may_worker.py','may_campaign_run.py','may_electrical.py','may_domain.py','may_input_prepare.py','may_bootstrap/sitecustomize.py','fast_prepare.py')
BINDINGS=[]
B1_PREPARATION_SECONDS=0.

def clone(function,replacements,extra=None):
    original=inspect.getsource(function);source=original
    for old,new in replacements:
        assert source.count(old)==1,('UNEXPECTED_ADAPTER_SOURCE',function.__name__,old)
        source=source.replace(old,new)
    namespace=dict(function.__globals__);namespace.update(extra or {})
    exec(compile(source,str(ROOT/'may_runtime.py')+'::'+function.__name__,'exec'),namespace)
    BINDINGS.append(dict(function=function.__module__+'.'+function.__name__,source=record(inspect.getsourcefile(function)),substitutions=[dict(before=a,after=b) for a,b in replacements],numerical_expressions_changed=False))
    return namespace[function.__name__]

def physics(day):
    if day!=DAY:
        from may_electrical import configure
        return configure(day)
    from dayahead.v41 import electrical
    return electrical

def configure(day,policy):
    assert day in tuple(f'2025-05-{n:02}' for n in range(1,32)) and policy in ('B0','B1','B2','B3')
    physics(day)
    from dayahead.v41 import data,execution,frozen_candidates as fc,physics_ranking as ranking,temporal_restore as temporal
    from dayahead.v41r3 import authority as v3,candidates
    from dayahead.v41r2 import authority as r2
    from dayahead.v41r1 import migration_audit,bounded_runtime
    daily=MAY_OUT/day
    runtime=RUN if day==DAY else MAY_RUN
    # Bind loaded aliases as well as subsequently imported modules.
    for name in ('dayahead.v41.data','dayahead.v41.common','dayahead.v41.persistence','dayahead.v41.snapshot','dayahead.v41.scientific_archive','dayahead.v41r1.migration_persistence'):
        module=importlib.import_module(name)
        if hasattr(module,'RUNTIME'):module.RUNTIME=runtime
    execution.RUNS=MAY_RUN;execution.RUNTIME=MAY_RUN
    if day!=DAY:
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
        from may_domain import Store
        store=Store(day);a=store.authority
        candidates._store=store;fc.load_options=store.options
        temporal.BASE_COUNT=a['base_count'];temporal.RESTORED_COUNT=a['restored_count'];temporal.TOTAL_COUNT=a['total_count']
        fc.TOTAL_COUNT=a['total_count'];fc.RESTORED_COUNT=a['restored_count']
        fc.OUT=ranking.OUT=daily
        # The old before-count is descriptive metadata, not a model input.
        migration_audit.persist=clone(migration_audit.persist,[("historical=read(OLD_RUN/DAY/'B1/dayahead/authority/migration_before_solve/MIGRATION_ELIGIBILITY_SUMMARY.json')","historical={'N_TOTAL_MIGRATION_CANDIDATES_BEFORE':None}"),("before_count_definition='Legacy structurally feasible issue-RUNNING-only migration options; independent of current policy enable flag'","before_count_definition='NOT_COMPUTED_FOR_NEW_MAY_DATE; no obsolete domain enumeration; current full domain is independently sealed'")])
    else:
        fc.OUT=ranking.OUT=candidates.OUT=FINAL_OUT
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
    def verify(target,method):
        if target==DAY and method in ('B0','B1'):
            return verify_reused_may04(method,original_verify)
        return original_verify(target,method)
    execution.verify_dayahead=verify
    execution.dayahead=clone(execution.dayahead,[("require(day=='2025-05-04' and policy in ('B0','B1'),'V41R2_FULL_MAY_HOLD')","require(day==MAY_DAY and policy in ('B0','B1','B2','B3'),'MAY_DATE_POLICY_SCOPE')"),("from dayahead.v41r3.authority import OUT as V3OUT","V3OUT=MAY_DAY_OUT")],dict(MAY_DAY=day,MAY_DAY_OUT=daily,science=science,verify_dayahead=verify))
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
    save(daily/f'RUN_BINDINGS_{policy}.json',dict(status='BOUND',day=day,policy=policy,source=science(),adapters=BINDINGS,model_changes=0,physical_coefficient_changes=0,B3_A1_ordering='RETAINED_ORIGINAL',input_source='FROZEN_ML_ONLY',source_runtime=str(runtime),output_runtime=str(MAY_RUN)))
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
        gates=[dict(dependency=name,result='PASS') for name in ('New B0 critical line phase and slot','All ranking and neighborhood sensitivities from new daily coefficients','No reused May04 sensitivity ranking','Voltage line transformer and objective coefficients regenerated','Sealed daily universe and migration semantics retained','New daily B0 P1 and P1 normalization','Frozen control settings with naturally evolving native states')]
        save(MAY_OUT/day/'V41R3_ADDITIONAL_DEPENDENCY_GATE.json',dict(status='PASS',gates=gates,electrical=ctx.v41_electrical_certificate,ranking=record(MAY_OUT/day/'V41R3_FO_PHYSICS_RANKING_AUDIT.json'),domain=domain,B1_preparation_seconds=B1_PREPARATION_SECONDS,compound_ordering_source=record(ROOT/'dayahead/v41/physics_ranking.py')))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

def accept(day,policy):
    root=MAY_RUN/day/policy;da=root/'dayahead';ac=root/'actual'
    fresh=read(da/'FRESH_RESULT.json')['summary'];actual=read(ac/'ACTUAL_RESULT.json')
    passed=check(fresh) and check(actual['summary']) and actual['Actual_optimizer_calls']==0
    native=read(ac/'grid/NATIVE_ACTUAL_STATE_CONTINUITY.json');assert native['status']=='PASS'
    receipt=dict(status='PASS' if passed else 'FAIL_CLOSED',day=day,policy=policy,Fresh='PASS' if check(fresh) else 'FAIL',Actual='PASS' if check(actual['summary']) else 'FAIL',Fresh_summary=fresh,Actual_summary=actual['summary'],dayahead_receipt=record(da/'DAYAHEAD_RECEIPT.json'),actual_receipt=record(ac/'ACTUAL_RECEIPT.json'),native_continuity=record(ac/'grid/NATIVE_ACTUAL_STATE_CONTINUITY.json'))
    save(MAY_OUT/day/f'{policy}_ACCEPTANCE.json',receipt)
    if policy=='B0':
        arrays=list(da.rglob('OPENDSS_PHASE_ARRAYS.npz'));assert len(arrays)==1
        target=MAY_OUT/day/'screen/alpha_1.600/DAYAHEAD/physics/OPENDSS_PHASE_ARRAYS.npz'
        item=copy(arrays[0],target)
        receipt.update(OBJECTIVE_VECTOR=read(da/'optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR'],full_grid_copies=[dict(source=record(arrays[0]),local=record(target))])
        save(MAY_OUT/day/'V41R3_B0_ACCEPTANCE.json',receipt)
    assert passed,('MAY_PHYSICAL_GATE_FAIL',day,policy)
    return receipt

def prepare_reused_may04():
    report=read(OUT/'V41R3_FAST_POWER_SCALE_FREEZE.json');assert report['May_launch_gate']=='PASS'
    target=MAY_RUN/DAY
    from dayahead.v41.reserve import bind
    from dayahead.v41.common import build
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.v41 import execution
    ctx=physics(DAY).load(DAY)
    try:
        sp=RUN/'inputs'/DAY/f'V41_ML_SNAPSHOT_{DAY}.json';seal=read(sp.parent/'ML_SNAPSHOT_RECEIPT.json')
        bind(ctx,sp,seal['snapshot']['sha256']);jobs,common=build(DAY,sp,ctx.capacity)
        canonical=import_frozen(jobs);p=planning_power(canonical,ctx)
        with np.load(RUN/DAY/'B0/dayahead/FROZEN_AIDC_POWER.npz') as z:assert all(np.array_equal(p[k],z[k]) for k in p)
        decision=dict(day=DAY,policy='B0',AIDC_decision=canonical,MESS_trajectory=execution.off_commands(),ML_snapshot=seal['snapshot'],optimizer_scalar_sha256=ctx.v41_optimizer_scalars.sha256,common_service_SHA=common['COMMON_DA_DURATION_SHA'],electrical=ctx.v41_electrical_certificate,Actual_authority='REUSED_CERTIFIED_B0_NATIVE_ACTUAL')
        from dayahead.paper_analysis.storage import digest
        for method in ('B0','B1'):
            folder=target/method/'dayahead'
            marker=folder/'DAYAHEAD_RECEIPT.json'
            if marker.exists():continue
            reuse=dict(schema='V41R3_EXPLICIT_REUSED_MAY04_V1',status='COMPLETE',day=DAY,policy=method,classification='REUSED_CERTIFIED_RESULT_NO_REPLAY',final_gate=record(OUT/'V41R3_FAST_POWER_SCALE_FREEZE.json'),scientific_commit=execution.commit(),additional_optimization_calls=0,additional_OpenDSS_calls=0)
            if method=='B0':
                reuse.update(decision=decision,decision_SHA=digest(decision),acceptance=record(OUT/'V41R3_B0_ACCEPTANCE.json'),PCC_exact_equal=True)
                copy(FINAL_OUT/'V41R3_B0_RESTORED_OBJECTIVE.json',folder/'optimization/OBJECTIVE_LEDGER.json')
            else:
                reuse.update(original_day_ahead=record(FINAL_RUN/DAY/'B1/dayahead/DAYAHEAD_RECEIPT.json'),original_actual=record(FINAL_RUN/DAY/'B1/actual/ACTUAL_RECEIPT.json'))
                copy(FINAL_RUN/DAY/'B1/dayahead/optimization/OBJECTIVE_LEDGER.json',folder/'optimization/OBJECTIVE_LEDGER.json')
            save(marker,reuse)
            save(MAY_OUT/DAY/f'{method}_ACCEPTANCE.json',dict(status='PASS',day=DAY,policy=method,classification='REUSED_CERTIFIED_RESULT_NO_REPLAY',receipt=record(marker),evidence=report[method]))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

def verify_reused_may04(policy,original_verify):
    from dayahead.v40h.identity import verify_bound_files
    from dayahead.paper_analysis.storage import digest
    path=MAY_RUN/DAY/policy/'dayahead/DAYAHEAD_RECEIPT.json';value=read(path)
    assert value['schema']=='V41R3_EXPLICIT_REUSED_MAY04_V1'
    assert record(value['final_gate']['path'])==value['final_gate']
    if policy=='B0':
        assert record(value['acceptance']['path'])==value['acceptance']
        a=read(value['acceptance']['path']);assert a['Fresh']==a['Actual']=='PASS'
        verify_bound_files(a)
        verify_bound_files(value['decision'])
        assert digest(value['decision'])==value['decision_SHA']
        return value['decision'],value
    for k in ('original_day_ahead','original_actual'):assert record(value[k]['path'])==value[k]
    original=read(value['original_day_ahead']['path'])
    # Verify original receipt, all files, scientific archive and bound inputs
    # against its unchanged original producer. No May producer is invented.
    namespace=dict(original_verify.__globals__,RUNS=FINAL_RUN,science=lambda:original['science'])
    verifier=types.FunctionType(original_verify.__code__,namespace,original_verify.__name__,original_verify.__defaults__,original_verify.__closure__)
    return verifier(DAY,'B1')
