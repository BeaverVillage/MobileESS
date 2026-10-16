"""B1: fresh date inputs through the existing, validated A-stage P1 algorithm.

The original canary producer, Phase I/full pricing, native persistence,
integer-type restoration, May12 acceptance and physical checker are called
directly. This module only binds dates, isolated output paths, budgets and
P1-only downstream receipts. It never imports an old point, bound or clock.
"""
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import date
from fractions import Fraction
from pathlib import Path
from time import perf_counter
import gzip
import pickle
import subprocess
import traceback

import numpy as np

from v42_pr134_b1.common import atomic, read, record,now
from .a_routing import (DayDirectory, InputDirectory, rebound, group,
                        routed_optimize, dated_acceptance, native_zero_scope,
                        ConstructionNative)

REPOSITORY = Path(__file__).resolve().parents[1]
POLICY_PATH = REPOSITORY / 'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'
P1_COMPONENTS = frozenset(('PHASE_I', 'ORIGINAL_P1', 'LOCAL_PRICING', 'INTEGER_CONTROL'))


def _paths(request):
    day = request['day']
    if (date.fromisoformat(day).isoformat() != day or not day.startswith('2025-05-')
            or request.get('arm') != 'B1'):
        raise ValueError('A_CAMPAIGN_B1_MAY_DATE_REQUIRED')
    inputs, output = (Path(request[k]).resolve() for k in ('input_folder', 'output'))
    if output.drive.upper() != 'D:':
        raise PermissionError('A_CAMPAIGN_OUTPUT_D_DRIVE_REQUIRED')
    if inputs == output or inputs.is_relative_to(output):
        raise ValueError('A_CAMPAIGN_INPUT_OUTPUT_SEPARATION_REQUIRED')
    return day, inputs, output


def _notify(progress, **value):
    if progress is not None:
        progress(value)


def _check_budget(budget, reserve=0):
    if budget is not None:
        budget.check()


def _dump_state(path, state):
    with Path(path).open('xb') as stream:
        with gzip.GzipFile(fileobj=stream, mode='wb', compresslevel=1, mtime=0) as compressed:
            pickle.dump(state, compressed, protocol=5)
    return record(path)


def _scientific_active_graph(original, job, stays, migration, domain, retained_flow, *, correction_report=None):
    """A unique engineering seed is fixed only if its full domain is fixed.

    The original graph constructor retains source-flow for singleton migration
    classes. Aggregated running classes can also have a unique initial STAY
    and a nonempty complete migration pool. Preserve their existing integer
    histogram variable instead of converting that seed into a constant.
    """
    from v42_a_stage_domain_v2.domain import graph_content_hash
    graph = original(job, stays, migration, domain, retained_flow)
    if graph.fixed and (len(domain.stays) != 1 or domain.blocks):
        old = graph
        graph = replace(old, fixed=None)
        graph.sha = graph_content_hash(graph)
        if correction_report is not None:
            correction_report(dict(uid=job.uid, old_engineering_fixed=asdict(old.fixed),
                old_active_graph_SHA=old.sha, corrected_active_graph_SHA=graph.sha,
                complete_physical_domain_SHA=domain.sha, physical_STAY=len(domain.stays),
                physical_migration=sum(len(block[-1]) for block in domain.blocks),
                events_unchanged=True, states_unchanged=True, physical_domain_unchanged=True,
                integer_class_histogram_retained=True))
    return graph


def _dated_fast_active(original, correction_report):
    """Same complete domain/activation code; route only its fixed schema flag."""
    graph_constructor = original.__globals__['_graph']
    def graph(*args, **kwargs):
        return _scientific_active_graph(graph_constructor, *args, **kwargs, correction_report=correction_report)
    return rebound(original, dict(original.__globals__, _graph=graph))


def prepare(request, progress=None):
    from .build_reuse import BuildObserver,checkpoint_memo
    output=Path(request['output'])
    with checkpoint_memo() as memo:
        observer=BuildObserver(output,progress)
        state=_prepare(dict(request,_build_observer=observer),progress)
        atomic(output/'CHECKPOINT_MEMO_PROFILE.json',dict(PASS=True,**memo.report()))
        return state


def _prepare(request, progress=None):
    """Native=0 fresh-date original model/state and complete local block roster."""
    started = perf_counter()
    from v42_pr134_b1.native import bind
    from v42_a_stage_canary import prepare as inherited
    from v42_a_stage_domain_v2.census import digest
    from v42_a_stage_domain_v2.fast_census import save_physical_cache
    from v42_a_stage_domain_v2.active import prepare_fast_active
    from .a_cache import load_current_date_physical_cache

    day, inputs, output = _paths(request)
    shared_budget = request.get('_budget')
    _check_budget(shared_budget)
    if output.exists() and any(output.iterdir()):
        raise PermissionError('A_CAMPAIGN_FRESH_PREPARE_DIRECTORY_REQUIRED')
    output.mkdir(parents=True, exist_ok=True)
    observer=request['_build_observer']
    base = output / 'STATIC/DATA'
    base.mkdir(parents=True)
    bundle = read(inputs / 'NATIVE_INPUT.json')
    if bundle.get('day') != day:
        raise ValueError('A_CAMPAIGN_BUNDLE_DAY_IDENTITY')
    read(inputs / 'WINDOWS.json')
    input_receipts = {name: record(inputs / name) for name in ('NATIVE_INPUT.json', 'WINDOWS.json')}
    _notify(progress, phase='A_FRESH_DATE_DATA', day=day, arm='B1', Native_calls=0)
    data_module, _, _, *_ = bind(bundle, inputs, base)
    import builtins
    original_print = data_module.__dict__.get('print')

    def data_progress(*values, **keywords):
        _check_budget(shared_budget)
        builtins.print(*values, **keywords)
        if values and values[0] == 'complete support':
            _notify(progress, phase='A_FRESH_DATE_DATA', day=day,
                    jobs_complete=int(values[1]), classes_complete=int(values[3]), Native_calls=0)

    data_module.print = data_progress
    try:
        with observer.stage('fresh_DATA'):
            data = data_module.prepare()
    finally:
        if original_print is None:
            del data_module.print
        else:
            data_module.print = original_print
    _check_budget(shared_budget)
    if data[0] != bundle:
        raise ValueError('A_CAMPAIGN_FRESH_DATA_BUNDLE_IDENTITY')
    identity = dict(DATA_file=record(base / 'DATA.pkl'),
                    frozen_native_input=input_receipts['NATIVE_INPUT.json'],
                    resources_sha256=digest(asdict(data[3])))
    expected_path = REPOSITORY / 'docs/v42_a_stage_v2_stress4_20261007/STATIC_SOURCE_DATA_IDENTITY.json'

    def routed_read(path):
        if Path(path) == expected_path:
            return {'dates': {day: identity}}
        return read(path)

    def load_fresh(requested_day):
        if requested_day != day:
            raise ValueError('A_CAMPAIGN_FRESH_DATA_DATE_DRIFT')
        if record(base / 'DATA.pkl') != identity['DATA_file']:
            raise ValueError('A_CAMPAIGN_FRESH_DATA_SHA_DRIFT')
        return data, base

    def own_physical_cache(requested_day, fresh_data, *ignored):
        if requested_day != day:
            raise ValueError('A_CURRENT_DATE_CACHE_REQUEST_DAY_DRIFT')
        with observer.stage('load_current_date_physical_cache/full_domain_hash'):
            try:
                value=load_current_date_physical_cache(request, fresh_data,
                    check=lambda: _check_budget(shared_budget), progress=progress)
                observer.fields.update(physical_cache_hit=value is not None,
                    physical_classes_verified=len(fresh_data[7]['classes']) if value is not None else 0)
                return value
            except (OSError,ValueError,PermissionError,KeyError) as error:
                atomic(output/'PHYSICAL_CACHE_REJECTED.json',dict(cache_hit=False,error=repr(error),
                    recompute_complete_original_domain=True,checks_skipped=False))
                return None

    def fresh_active(*args, **keywords):
        _check_budget(shared_budget)
        corrections = []
        original_domain=prepare_fast_active.__globals__['physical_domain']
        def observed_domain(*a,**kw):
            with observer.stage('physical_domain/checkpoint_records'):
                value=original_domain(*a,**kw)
            observer.fields['physical_classes_complete']+=1
            return value
        routed=rebound(prepare_fast_active,dict(prepare_fast_active.__globals__,physical_domain=observed_domain))
        with observer.stage('prepare_fast_active/active_graph'):
            active_data, domains, ledger = _dated_fast_active(routed, corrections.append)(*args, **keywords)
        atomic(output / 'ACTIVE_SCIENTIFIC_FIXED_SEMANTICS.json', dict(PASS=True,
            day=day, corrected_classes=corrections, original_fixed_guard_preserved=True,
            scientific_domain_candidates_removed=0, active_supports_changed=0,
            class_cardinality_changed=False, original_integer_types_preserved=True,
            producer=record(REPOSITORY / 'v42_a_stage_domain_v2/active.py'),
            Native_calls=0))
        # The unchanged historical cache writer replaces only the unpicklable
        # no-op callback, before inherited prepare serializes its initial state.
        save_physical_cache(day, active_data, domains, base / 'DATA.pkl', output / 'STATIC/DOMAIN')
        _check_budget(shared_budget)
        return active_data, domains, ledger

    def prepared_atomic(path, value):
        _check_budget(shared_budget)
        atomic(path, value)
        if Path(path).name == 'BUILD_PROGRESS.json':
            _notify(progress, **dict(value, arm='B1', Native_calls=0))

    def prepared_print(*values, **keywords):
        _check_budget(shared_budget)
        builtins.print(*values, **keywords)
        if values and values[0] == 'CANARY_FULL_BLOCK':
            observer.last_stage_progress_UTC=now()
            _notify(progress, phase='A_COMPLETE_NATIVE_BLOCKS', day=day,
                    classes_complete=int(values[2]), classes_required=int(values[3]), Native_calls=0)

    last_construction_progress = [0.]
    construction_phase = ['MODEL_BUILD']

    def construction_report(value=None):
        if value is not None:
            construction_phase[0] = value.get('phase', construction_phase[0])
            observer.fields['build_function']=construction_phase[0]
            observer.last_stage_progress_UTC=__import__('v42_pr134_b1.common',fromlist=['now']).now()
        now = perf_counter()
        if value is not None or now - last_construction_progress[0] >= 2:
            fields = {k: v for k, v in (value or {}).items() if k not in ('phase', 'day', 'arm', 'Native_calls')}
            fields.update(phase='A_ORIGINAL_NATIVE_CONSTRUCTION', builder_phase=construction_phase[0],
                          day=day, arm='B1', Native_calls=0,
                          preparation_wall_seconds=now - started)
            if shared_budget is not None:
                fields.update(Wall_Time=shared_budget.wall(), Native_Runtime=shared_budget.native_used)
            _notify(progress, **fields)
            last_construction_progress[0] = now

    def construction_check():
        _check_budget(shared_budget)
        construction_report()

    def construction_bind(*args, **kwargs):
        construction_check()
        answer = bind(*args, **kwargs)
        construction_check()
        return (answer[0], ConstructionNative(answer[1], construction_check, construction_report), *answer[2:])

    original_block = inherited.native_block

    def construction_block(*args, **kwargs):
        construction_phase[0] = 'COMPLETE_NATIVE_BLOCK'
        construction_check()
        result = original_block(*args, **kwargs)
        construction_check()
        return result

    def measured(function,label):
        def call(*args,**kwargs):
            with observer.stage(label):return function(*args,**kwargs)
        return call

    # No historical cached domain or rescue schedule is used. The original
    # prepare_fast_active builds this date's full hard physical domain itself.
    namespace = dict(inherited.prepare.__globals__,
                     ROOT=REPOSITORY, OUT=DayDirectory(day, output),
                     STATIC=DayDirectory(day, output / 'STATIC'), DAYS=(day,),
                     PRODUCTION=InputDirectory(day, inputs), read=routed_read,
                     load_frozen=load_fresh, load_physical_cache=own_physical_cache,
                     required_supports=lambda *a, **k: (), prepare_fast_active=fresh_active,
                     atomic=prepared_atomic, print=prepared_print,
                     bind=construction_bind, native_block=construction_block,
                     snapshot_of=measured(inherited.snapshot_of,'original_matrix_snapshot'),
                     assemble_original=measured(inherited.assemble_original,'original_matrix_assembly'),
                     build=measured(inherited.build,'complete_compact_class_assembly'))
    import gurobipy as gp
    with observer, native_zero_scope(gp, construction_check=construction_check):
        state = rebound(inherited.prepare, namespace)(day)
    state['_campaign'] = dict(day=day, arm='B1', input_folder=str(inputs),
                             output=str(output), input_receipts=input_receipts,
                             original_data=identity['DATA_file'], Native_calls=0,
                             expected_model_verification=request.get('_expected_model_verification'),
                             historical_point_bound_clock_loaded=False)
    # Make the fresh cache picklable with the existing writer. Its callback
    # supplies no physical condition and is already used by the validated code.
    _check_budget(shared_budget)
    receipt = _dump_state(output / 'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz', state)
    state['_campaign']['state_receipt'] = receipt
    verification = verify_case(state)
    atomic(output / 'A_PREPARE_RECEIPT.json', dict(
        PASS=verification['PASS'], day=day, arm='B1', state=receipt,
        scientific_input=input_receipts, verification=verification,
        preparation_wall_seconds=perf_counter() - started,
        preparation_peak_RSS_bytes=getattr(__import__('psutil').Process().memory_info(),'peak_wset',None),
        complete_original_model_builder=record(Path(inherited.__file__)),
        Native_calls=0, P2_calls=0, MESS_optimization_calls=0,
        fresh_date_generated=True, historical_point_bound_clock_loaded=False))
    _notify(progress, phase='A_STATIC_CASE_VERIFIED', day=day,
            classes=verification['classes'], Native_calls=0)
    return state


def verify_case(state):
    """Independent static identities/complete pool coverage; never optimize."""
    from v42_a_stage_domain_v2.fast_census import verify_partition
    from v42_a_stage_phase1.runner import load_cache

    authority = state['_campaign']
    day, output = authority['day'], Path(authority['output'])
    if state['data'][0]['day'] != day or authority['arm'] != 'B1':
        raise ValueError('A_CAMPAIGN_CASE_DATE_OR_ARM_DRIFT')
    for receipt in authority['input_receipts'].values():
        if record(receipt['path']) != receipt:
            raise ValueError('A_CAMPAIGN_INPUT_SHA_DRIFT')
    if record(authority['original_data']['path']) != authority['original_data']:
        raise ValueError('A_CAMPAIGN_DATA_SHA_DRIFT')
    state['reference'].require()
    state['compact'].require()
    classes = state['data'][7]['classes']
    population = [uid for members in classes.values() for uid in members]
    if len(population) != len(set(population)) or set(population) != set(state['data'][1]):
        raise ValueError('A_CAMPAIGN_ORIGINAL_JOB_CLASS_AXIS')
    if set(state['domains']) != set(state['data'][1]):
        raise ValueError('A_CAMPAIGN_COMPLETE_DOMAIN_JOB_AXIS')
    roster = read(output / 'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']
    if len(roster) != len(classes) or {r['class_id'] for r in roster} != set(classes):
        raise ValueError('A_CAMPAIGN_COMPLETE_PRICING_CLASS_AXIS')
    if len({key[:12] for key in classes}) != len(classes):
        raise ValueError('BLOCK_PATH_PREFIX_COLLISION')
    full_stay = full_migration = 0
    for entry in roster:
        uid = classes[entry['class_id']][0]
        domain = state['domains'][uid]
        if (entry['cardinality'] != len(classes[entry['class_id']])
                or entry['full_physical_STAY'] != len(domain.stays)
                or entry['full_physical_migration'] != sum(len(b[-1]) for b in domain.blocks)):
            raise ValueError('A_CAMPAIGN_COMPLETE_LOCAL_DOMAIN_CARDINALITY')
        # This is the preserved independent cache/snapshot/graph SHA verifier.
        load_cache(entry)
        full_stay += entry['full_physical_STAY']
        full_migration += entry['full_physical_migration']
    partition = verify_partition(state['ledger'])
    if state['reference'].objectives[0].name != 'rho' or state['compact'].objectives[0].name != 'rho':
        raise ValueError('A_CAMPAIGN_ORIGINAL_P1_OBJECTIVE_REQUIRED')
    axes = state['axes']
    if any(row < 0 or row >= len(state['grows']) for row in axes.values()):
        raise ValueError('A_CAMPAIGN_COUPLING_ROW_AXIS')
    gpu_axis = {(site, t) for family, site, t in axes if family == 'GPU'}
    tail = max(bound.latest_completion for bound in state['data'][2].values())
    expected_gpu = {(site, t) for site in state['data'][3].capacities for t in range(tail)}
    if gpu_axis != expected_gpu:
        raise ValueError('A_CAMPAIGN_ORIGINAL_SITE_GPU_CAPACITY_HORIZON_AXIS')
    result=dict(PASS=True, day=day, classes=len(classes), jobs=len(population),
                full_STAY=full_stay, full_migration=full_migration,
                complete_pool_partition=partition,
                original_P1=state['reference'].objective('rho').name,
                reference_snapshot_sha256=state['reference'].fingerprint(),
                compact_snapshot_sha256=state['compact'].fingerprint(),
                historical_point_bound_clock_loaded=False,
                Native_calls=0, P2_calls=0, MESS_optimization_calls=0)
    expected=authority.get('expected_model_verification')
    if expected is not None and result!=expected:
        raise ValueError('A_INDEPENDENT_PINNED_MATRIX_OBJECTIVE_RHS_BOUNDS_TYPES_DOMAIN_DRIFT')
    return result


class _NativeBudget:
    """Existing native persistence gets one account owned by the coordinator."""
    def __init__(self, shared):
        self.shared = shared
        self.component = None
        self.call_cap = None
        self.call_native_start = 0.
        self.record = {'limit_seconds': 5400, 'shared_accounting': True}
        self.last_charged = None

    def remaining(self):
        from v42_a_stage_early.native import BudgetStop
        try:
            value = self.shared.remaining()
        except Exception as error:
            if type(error).__name__ == 'BudgetStop':
                raise BudgetStop(str(error)) from error
            raise
        if self.call_cap is not None:
            value = min(value, self.call_cap - (self.shared.native_used - self.call_native_start))
        if value <= 0:
            raise BudgetStop('A_DATE_NATIVE_BUDGET_EXHAUSTED')
        return value

    def charge(self, runtime):
        # The routed optimize has already charged actual Gurobi Runtime.
        # A second charge would silently halve the available campaign budget.
        if self.last_charged is None and runtime == 0:
            return  # The inherited native scope rejected before optimize.
        if self.last_charged is None or abs(self.last_charged - runtime) > 1e-6:
            raise ValueError('A_SHARED_NATIVE_RUNTIME_ACCOUNTING_DRIFT')
        self.last_charged = None

    def accounted(self):
        return self.shared.used()


def _native(request, state, budget, progress):
    """Reuse acceptance.Native.solve, with only execution/account routing."""
    from v42_a_stage_acceptance import native as inherited
    from . import execution

    day, inputs, output = _paths(request)
    source_paths = [Path(inherited.__file__), Path(__file__),
                    REPOSITORY / 'v42_may_campaign/a_routing.py', POLICY_PATH,
                    REPOSITORY / 'v42_may_campaign/a_cache.py',
                    REPOSITORY / 'v42_a_stage_canary/phase.py',
                    REPOSITORY / 'v42_a_stage_canary/pricing.py',
                    REPOSITORY / 'v42_may12_rescue/contract.py',
                    REPOSITORY / 'v42_a_stage_practical/integer_model.py',
                    REPOSITORY / 'v42_a_stage_acceptance/physical.py',
                    REPOSITORY / 'v42_a_stage_domain_v2/execution.py']
    sources = [record(path) for path in source_paths]
    freeze_path = output / 'A_NATIVE_SOURCE_FREEZE.json'
    atomic(freeze_path, dict(PASS=True, day=day, arm='B1',
                            git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY, text=True).strip(),
                            sources=sources, inputs=state['_campaign']['input_receipts'], P2_calls=0))
    atomic(output / 'CONTINUATION_BUDGET.json', dict(
        PASS=True, native_limit=5400, wall_limit=None, final_validation_reserve=0,
        policy_version='NATIVE90_V2', accounting='MEASURED_NATIVE_RUNTIME_ONLY',
        started_monotonic=budget.started, shared_accounting=True))
    atomic(output / 'MEMORY_GUARDS_USER_OVERRIDE.json', dict(
        PASS=True, authority='REUSED_VALIDATED_A_STAGE_MEMORY_TELEMETRY_POLICY',
        finite_MemLimit=False, finite_SoftMemLimit=False,
        RAM_automatic_stop=False, allocation_cap=False, telemetry_only=True))
    facade = _NativeBudget(budget)

    def verify():
        for receipt in sources + list(state['_campaign']['input_receipts'].values()):
            if record(receipt['path']) != receipt:
                raise PermissionError('A_FROZEN_SOURCE_OR_INPUT_SHA_DRIFT')
        return read(freeze_path)

    @contextmanager
    def native_scope(model, component, budget_check):
        if component not in P1_COMPONENTS:
            raise PermissionError('A_CAMPAIGN_P1_ONLY_NATIVE_COMPONENTS')
        budget_check()
        with execution.native_scope(model, component, track='A'):
            yield

    def optimize(model, callback):
        before = budget.native_used
        try:
            return budget.native_optimize(model, callback, component=facade.component,
                                          track='A', label=facade.component,
                                          requested_seconds=facade.remaining())
        finally:
            facade.last_charged = budget.native_used - before

    namespace = dict(inherited.Native.solve.__globals__, OUT=output,
                     STATIC=output / 'STATIC/NATIVE', DAY=day, verify=verify,
                     native_scope=native_scope, guard_model_optimize=execution.guard,
                     _campaign_optimize=optimize)
    solve_original = routed_optimize(inherited.Native.solve, namespace)

    class Native:
        def __init__(self):
            self.freeze_path = freeze_path
            self.policy = read(POLICY_PATH)
            self.budget = self.parent_budget = facade
            self.native_seconds = 0.
            self.calls, self.resources, self.system_samples = [], [], []
            self.warm_point = None
            self.live_model = None

        def verify(self):
            return verify()

        def remaining(self):
            return facade.remaining()

        def solve(self, snapshot, folder, component):
            if component not in P1_COMPONENTS:
                raise PermissionError('A_CAMPAIGN_P2_AND_MESS_FORBIDDEN')
            if snapshot.objectives[0].name != ('Phi' if component == 'PHASE_I' else 'rho'):
                # Local pricing carries the inherited priced local objective.
                if component not in ('LOCAL_PRICING', 'PHASE_I'):
                    raise PermissionError('A_CAMPAIGN_ORIGINAL_RHO_ONLY')
            facade.component = component
            facade.call_cap = None
            facade.call_native_start = budget.native_used
            _notify(progress, phase=component, day=day, arm='B1',
                    Native_Runtime=budget.native_used, Wall_Time=budget.wall())
            try:
                with budget.cost('model_preparation',component+'_model_and_native_persistence'):
                    return solve_original(self, snapshot, folder, component)
            finally:
                facade.call_cap = None
                atomic(output / 'A_NATIVE_CALLS.json', dict(calls=self.calls,
                    native_seconds=self.native_seconds, shared_native_seconds=budget.native_used,
                    wall_seconds=budget.wall(), P2_calls=0, MESS_optimization_calls=0))

    return Native()


def _physical(state, inputs, output):
    from v42_a_stage_acceptance import physical as inherited
    from v42_pr134_b1.native import bind

    power = {}

    def routed_bind(bundle, ignored_inputs, ignored_output):
        answer = bind(bundle, inputs, output / 'STATIC/PHYSICAL_REPLAY')
        power.update(coeff=answer[2], power=answer[3], idle=answer[4], swing=answer[5])
        return answer

    namespace = dict(inherited.Physical.__init__.__globals__, ROOT=REPOSITORY,
                     STATIC=DayDirectory(state['data'][0]['day'], output / 'STATIC'), bind=routed_bind)

    class Physical(inherited.Physical):
        __init__ = rebound(inherited.Physical.__init__, namespace)

    return Physical, power


def _planning(state, verification, power, output):
    """Same accepted A-stage controls -> PCC/IT/GPU materialization as PR134."""
    bundle = state['data'][0]
    sites = sorted(bundle['capacities'])
    caps = np.asarray([bundle['capacities'][s] for s in sites])
    known = np.zeros((96, len(sites)))
    for uid, option in verification['selected_jobs'].items():
        for site, start, end in option['segments']:
            for slot in range(max(start, 24), min(end, 120)):
                known[slot - 24, sites.index(site)] += state['data'][1][uid].gpu
    controls, coeff = verification['controls'], power['coeff']
    if any(abs(value) > 1e-8 for c, row in zip(coeff, controls)
           for name, value in zip(c.control_names, row) if not name.startswith('aidc_load_kw')):
        raise ValueError('A_B1_ORIGINAL_MESS_PQ_NOT_ZERO')
    pcc = np.asarray([[controls[t][coeff[t].control_names.index('aidc_load_kw[' + site + ']')]
                       for site in sites] for t in range(96)])
    slopes = np.asarray([[power['power'][site, t].slope for site in sites] for t in range(96)])
    intercepts = np.asarray([[power['power'][site, t].intercept_kw for site in sites] for t in range(96)])
    it = (pcc - intercepts) / slopes
    gpu = (it - power['idle'] * caps) / power['swing']
    q = pcc * np.tan(np.arccos(.95))
    if np.any(gpu > caps + 1e-5) or np.any(gpu < known - 1e-5):
        raise ValueError('PLANNING_GPU_POWER_IDENTITY')
    np.savez_compressed(output / 'PLANNING_PHYSICAL.npz', sites=np.asarray(sites),
                        PCC_P_kw=pcc, PCC_Q_kvar=q, IT_kw=it, GPU=gpu, known_GPU=known,
                        MESS_P_kw=np.zeros((96, 4)), MESS_Q_kvar=np.zeros((96, 4)))
    return record(output / 'PLANNING_PHYSICAL.npz')


def run(request, budget, progress=None):
    """One date, fresh existing Phase I/P1/pricing/integer algorithm; P2=0."""
    from v42_a_stage_canary import phase, pricing, targeted
    from v42_a_stage_practical.integer_model import restore_types
    from v42_a_stage_phase1.core import primal_replay
    from v42_a_stage_lexfull.runner import objective_value
    from v42_a_stage_acceptance.schedule_audit import original_schedule_metrics
    from v42_may12_rescue.contract import decide

    day, inputs, output = _paths(request)
    native = None
    candidates = []
    invalid_replays = []
    result = dict(PASS=False, accepted=False, day=day, arm='B1',
                  classification='INCONCLUSIVE', P2_calls=0,
                  MESS_optimization_calls=0, all_MESS_PQ_zero=True,
                  old_point_bound_clock_loaded=False)
    try:
        _check_budget(budget)
        with budget.cost('model_preparation','A_complete_model_build'):
            state = prepare(dict(request, _budget=budget), progress)
        authority = state['_campaign']
        _check_budget(budget)
        native = _native(request, state, budget, progress)
        out = DayDirectory(day, output)
        full_pricing = rebound(pricing.full_pricing,
                               dict(pricing.full_pricing.__globals__, HISTORY=output))
        target_group = group(targeted, ('worker', 'targeted'), HISTORY=output)
        phase_group = group(phase, ('activate', 'run'), OUT=out,
                            full_pricing=full_pricing, targeted=target_group['targeted'])
        state, _, expanded, priced = phase_group['run'](native, state, day)
        state['_campaign'] = authority
        _dump_state(output / 'STATIC/P1_CLOSED_STATE.pkl.gz', state)
        exact_lb = Fraction(priced['full_domain_phase1_lower_bound'])
        classes = len(state['data'][7]['classes'])
        closure = dict(PASS=True, classes=classes,
                       complete_STAY_and_migration_coverage=priced['complete_STAY_and_migration_coverage'],
                       no_negative_omitted_block_certified=priced['no_negative_omitted_block_certified'],
                       full_pricing=record(read(output / 'P1_RESULT.json')['full_pricing']['path']))
        if not closure['no_negative_omitted_block_certified']:
            raise ValueError('A_COMPLETE_ORIGINAL_P1_PRICING_CLOSURE_REQUIRED')
        bound = dict(PASS=True, exact_LB=str(exact_lb), LB=float(exact_lb),
                     scope='FULL_ORIGINAL_DATE_P1_LP_RELAXATION',
                     restricted_native_ObjBound_not_used=True, closure=closure)
        atomic(output / 'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json', bound)
        atomic(output / 'COMPLETE_PRICING_CLOSURE.json', closure)
        _notify(progress, phase='A_ORIGINAL_INTEGER_TYPE_RESTORATION',
                day=day, Certified_Global_LB=float(exact_lb))
        _check_budget(budget)
        typed, typeproof = restore_types(state, state['global_types'])
        atomic(output / 'ORIGINAL_INTEGER_TYPE_RESTORATION.json', typeproof)
        Physical, power = _physical(state, inputs, output)
        physical = Physical(state, typed)
        contract = dated_acceptance(decide, classes)
        zero = read(output / 'PHASE_I_ZERO_CERTIFICATE.json')

        def validate(point, objective):
            rows = primal_replay(typed, point)
            iv = typed.vtypes != 'C'
            integral = float(np.max(abs(point[iv] - np.rint(point[iv])), initial=0))
            if not rows['PASS'] or integral > 1e-5:
                rejected = dict(PASS=False, original_rows=rows,
                                integral_max_residual=integral,
                                reason='ORIGINAL_INTEGER_ROW_OR_TYPE_FAILURE')
                invalid_replays.append(rejected)
                atomic(output / 'I' / ('R' + str(len(invalid_replays)) + '.json'), rejected)
                return
            verification = physical.verify(point)
            _check_budget(budget)
            if not verification['PASS']:
                invalid_replays.append(verification)
                atomic(output / 'I' / ('R' + str(len(invalid_replays)) + '.json'), verification)
                return
            upper = objective_value(typed, point, 'rho')
            values = {o.name: str(objective_value(typed, point, o.name)) for o in typed.objectives}
            metrics, residuals = original_schedule_metrics(state['data'][1], verification['selected_jobs'], values)
            if abs(float(upper) - objective) > 1e-6:
                raise ValueError('A_ORIGINAL_NATIVE_P1_OBJECTIVE_IDENTITY_FAIL')
            if upper < exact_lb:
                raise ValueError('A_CERTIFIED_LB_UB_CONFLICT')
            if candidates and upper >= Fraction(candidates[-1]['exact_UB']):
                return
            verification.update(original_job_population_verified=True,
                                original_jobs=len(state['data'][1]), original_integer_types_restored=True,
                                integral_max_residual=integral, scientific_primal_replay=rows,
                                objective_values=values, schedule_metrics=metrics,
                                schedule_objective_residuals=residuals, original_P1_objective_consistency=True,
                                no_future_information=True)
            incarnation = output / 'I' / ('V' + str(len(candidates) + 1))
            incarnation.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(str(incarnation) + '.npz', X=point)
            atomic(str(incarnation) + '.json', verification)
            atomic(output / 'ORIGINAL_PHYSICAL_REPLAY.json', verification)
            candidate = dict(PASS=True, exact_UB=str(upper), UB=float(upper),
                             exact_LB=str(exact_lb), LB=float(exact_lb),
                             original_integer_types_restored=True,
                             physical=record(str(incarnation) + '.json'),
                             point=record(str(incarnation) + '.npz'),
                             exact_objective_values=values, evaluated_P2_metrics_only=metrics)
            acceptance = contract(zero, closure, bound, candidate, verification)
            candidate.update(gap=acceptance['gap'], acceptance=acceptance)
            candidates.append(candidate)
            atomic(output / 'VALIDATED_INTEGER_INCUMBENTS.json', dict(trajectory=candidates))
            _notify(progress, phase='INTEGER_CONTROL', day=day, UB=float(upper),
                    Certified_Global_LB=float(exact_lb), Certified_Gap=acceptance['gap'])
            if acceptance['PASS'] and native.live_model is not None:
                atomic(output / 'INDEPENDENT_CERTIFIED_TARGET_STOP.json', dict(
                    PASS=True, exact_LB=str(exact_lb), exact_UB=str(upper),
                    reason='CERTIFIED_P1_ONLY_GLOBAL_GAP_TARGET_MET'))
                native.live_model.terminate()

        original_validate=validate
        def validate(*a,**kw):
            with budget.cost('integer_physical_validation','A_independent_integer_physical_replay'):
                return original_validate(*a,**kw)
        native.incumbent_callback = validate
        rec, raw = native.solve(typed, output / 'P1/INTEGER_CONTROL', 'INTEGER_CONTROL')
        if 'X' in raw:
            validate(raw['X'], rec['objective'])
        if candidates:
            best = candidates[-1]
            verification = read(best['physical']['path'])
            acceptance = best['acceptance']
            atomic(output / 'P1_ONLY_ACCEPTANCE_CONTRACT.json', acceptance)
            result.update(UB=best['UB'], LB=best['LB'], exact_UB=best['exact_UB'],
                          exact_LB=best['exact_LB'], certified_gap=best['gap'], incumbent=best)
            if acceptance['PASS']:
                _check_budget(budget)
                planning = _planning(state, verification, power, output)
                _check_budget(budget)
                freeze = dict(PASS=True, accepted=True, state='A1_P1_ONLY_ACCEPTED',
                              A1_P1_ONLY_ACCEPTED=True, A1_ACCEPTED=False, P1_only=True,
                              arm='B1', day=day, selected_jobs=verification['selected_jobs'],
                              controls=verification['controls'], globals=verification['globals'],
                              validated_original_integer_point=best['point'],
                              physical=best['physical'], planning=planning,
                              global_bound=record(output / 'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json'),
                              acceptance=record(output / 'P1_ONLY_ACCEPTANCE_CONTRACT.json'),
                              source=record(native.freeze_path), scientific_input=state['_campaign']['input_receipts'],
                              exact_objective_values=best['exact_objective_values'],
                              P2_calls=0, MESS_optimization_calls=0, all_MESS_PQ_zero=True,
                              UB=best['UB'], LB=best['LB'], certified_gap=best['gap'])
                atomic(output / 'B1_P1_FREEZE.json', freeze)
                # Schema adapter for the old materializer; full four-objective
                # A1 acceptance is explicitly false and is never asserted.
                atomic(output / 'A1_FREEZE.json', freeze)
                result.update(PASS=True, accepted=True, classification='PASS',
                              freeze=record(output / 'B1_P1_FREEZE.json'), planning=planning,
                              planning_rho_max=verification['physical']['P1_rho'])
            else:
                result['classification'] = 'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
        else:
            result.update(classification='PHYSICAL_FAILURE' if invalid_replays else
                          'TIME_LIMIT_NO_VALID_INCUMBENT' if rec['status'] in (9, 11)
                          else 'INCONCLUSIVE', native_status=rec['status'])
    except Exception as error:
        name, text = type(error).__name__, str(error)
        last_native_status = native.calls[-1]['status'] if native is not None and native.calls else None
        timed = name == 'BudgetStop' or 'BUDGET' in text or last_native_status in (9, 11)
        physical_failure = any(token in text for token in ('PHYSICAL', 'PCC', 'GPU_POWER_IDENTITY'))
        input_failure = any(token in text for token in ('INPUT', 'BUNDLE', 'DATA_SHA', 'DATE_IDENTITY'))
        result.update(classification=('TIME_LIMIT_FEASIBLE_NOT_CERTIFIED' if candidates else 'TIME_LIMIT_NO_VALID_INCUMBENT')
                      if timed else 'PHYSICAL_FAILURE' if physical_failure else 'INPUT_FAILURE' if input_failure else 'IMPLEMENTATION_FAILURE',
                      error=repr(error), traceback=traceback.format_exc(),
                      scientific_infeasibility_proven=False)
        if candidates:
            result.update(incumbent=candidates[-1], UB=candidates[-1]['UB'],
                          LB=candidates[-1]['LB'], certified_gap=candidates[-1]['gap'])
    finally:
        result.update(native_seconds=budget.native_used, wall_seconds=budget.wall(),
                      native_calls=0 if native is None else len(native.calls),
                      invalid_original_physical_replay_count=len(invalid_replays),
                      P2_calls=0, MESS_optimization_calls=0)
        output.mkdir(parents=True, exist_ok=True)
        atomic(output / 'A_RESULT.json', result)
    return result
