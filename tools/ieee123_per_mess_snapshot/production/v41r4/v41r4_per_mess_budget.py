"""Independent soft deadlines around the frozen IEEE123 MESS search.

No scientific source file is edited. Function clones add control boundaries;
the frozen candidate order, certification, K fallback and pruning are retained.
"""
import functools
import hashlib
import inspect
import json
import os
import time
import types
from pathlib import Path

CONTRACT = dict(schema='IEEE123_PER_MESS_SOFT_WALL_CLOCK_V1', budget_seconds=900,
    depths=[1, 2, 3, 4], policies=['B2', 'B3-M1'], global_cap_seconds=None,
    clock='monotonic', reset='DEPTH_START_ONLY', expiry='NO_NEW_ATOMIC_ACTION',
    running_action='GRACEFUL_COMPLETION', selection='FROZEN_PRUNE_ALL_CERTIFIED_CHILDREN',
    beam_width=2, seed_width=2, K=[200, 400, 800, 'FULL'],
    full_MILP_TimeLimit=600, WorkLimit_tiers=[60, 180, 300], rho_cert_tolerance=1e-7)
CONTRACT_SHA = hashlib.sha256(json.dumps(CONTRACT, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
ACTIVE = None
INSTALLED = False
PATCHES = []


class BudgetExpired(Exception):
    pass


class GracefulStop(Exception):
    pass


class RestrictedPolygonRejection(Exception):
    """Restricted certificate is not a full-model transformer-polygon certificate."""
    def __init__(self, physical, grid):
        self.physical, self.grid = physical, grid
        super().__init__('RESTRICTED_TRANSFORMER_POLYGON_NOT_RETAINABLE')


def recovery():
    root=os.environ.get('IEEE123_MESS_SEARCH_ROOT')
    if not root:return None
    path = Path(root)/'TECHNICAL_RECOVERY.json'
    if not path.exists():return None
    from dayahead.paper_analysis.storage import read
    value=read(path)
    assert value['runtime_budget_contract_SHA']==CONTRACT_SHA
    assert value['policy']==os.environ['IEEE123_MESS_POLICY']
    assert Path(value['search_root']).resolve()==path.parent.resolve()
    return value


def recover_stage(path, execution, parents, step):
    proof=recovery()
    if not proof or str(step) not in proof['completed_stages']:return None
    from fast_prepare import record
    from dayahead.paper_analysis.storage import read
    from dayahead.v40h.cache import validate_stage
    entry=proof['completed_stages'][str(step)]
    assert record(path)==entry
    value=read(path)
    assert value['payload']['runtime_budget_contract_SHA']==CONTRACT_SHA
    validate_stage(value,execution,parents,step)
    return value['payload']


class DepthBudget:
    def __init__(self, day, policy, depth, *, clock=time.perf_counter, output=None):
        if policy not in ('B2', 'B3'): raise ValueError('UNKNOWN_MESS_POLICY')
        self.clock = clock
        self.start = clock()
        self.started_at = time.time()
        self.day, self.policy, self.depth = day, policy, depth
        self.output = Path(output) if output else None
        self.k = []
        self.evaluations = self.certified = self.stalled = self.infeasible = 0
        self.pool = {}
        self.fallbacks = []
        self.parent = None
        self.context = {}
        self.action = None
        self.exhausted = False
        self.certification_active = 0
        self.full_active = 0
        self.retention_rejections = 0

    @property
    def elapsed(self): return max(0., self.clock() - self.start)

    def available(self):
        if self.elapsed >= CONTRACT['budget_seconds']: self.exhausted = True
        return not self.exhausted

    def check(self, action):
        stop = os.environ.get('IEEE123_900_STOP_FILE')
        if stop and Path(stop).exists(): raise GracefulStop('USER_REQUESTED_GRACEFUL_STOP')
        if not self.available(): raise BudgetExpired(action)
        self.action = action
        self.publish()

    def snapshot(self, retained=(), reason=None):
        elapsed = self.elapsed
        states = list(self.pool.values())
        return dict(day=self.day, policy=self.policy, mess_index=self.depth, depth=self.depth,
            budget_seconds=900, started_at=self.started_at, elapsed_at_stop=elapsed,
            soft_budget_overrun_seconds=max(0., elapsed - 900),
            budget_event='SOFT_BUDGET_OVERRUN' if elapsed > 900 else None,
            K_stages_entered=list(self.k), FULL_entered='FULL' in self.k,
            K_stage=self.k[-1] if self.k else None, current_action=self.action,
            candidate_evaluations=self.evaluations, certified_candidate_count=self.certified,
            restricted_polygon_retention_rejections=self.retention_rejections,
            stalled_count=self.stalled, infeasible_count=self.infeasible,
            best_certified_objective_at_stop=min((s.current_planning_objective for s in states), default=None),
            retained_child_signatures=[s.state_sha256 for s in retained],
            retained_children=[dict(signature=s.state_sha256, state_id=s.beam_state_id,
                objective=s.current_planning_objective,
                movement='MOVE' if s.vehicles[-1]['natural_MOVE_count'] else 'STAY') for s in retained],
            budget_exhausted=self.exhausted or elapsed >= 900,
            stop_reason=reason, runtime_budget_contract_SHA=CONTRACT_SHA,
            runtime_implementation_SHA=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

    def publish(self, retained=(), reason=None):
        value = self.snapshot(retained, reason)
        if self.output:
            from dayahead.paper_analysis.storage import write_json
            write_json(self.output / 'PER_MESS_LIVE.json', value)
            if reason: write_json(self.output / f'PER_MESS_{self.depth:02}_COMPLETE.json', value)
        return value


def check(action):
    if ACTIVE: ACTIVE.check(action)


def clone(fn, changes, extra=None):
    source = inspect.getsource(fn)
    for before, after in changes:
        if source.count(before) != 1: raise ValueError(('PER_MESS_SOURCE_DRIFT', fn.__name__, before))
        source = source.replace(before, after)
    ns = dict(fn.__globals__, **(extra or {}))
    exec(compile(source, __file__ + '::' + fn.__name__, 'exec'), ns)
    PATCHES.append(dict(function=fn.__name__, original_SHA=hashlib.sha256(inspect.getsource(fn).encode()).hexdigest(),
        effective_SHA=hashlib.sha256(source.encode()).hexdigest(), replacements=changes))
    return ns[fn.__name__]


def dispatch_trajectory(dispatch, route_table):
    """Use the frozen extractor on an exact read-only dispatch view; no solve."""
    from dayahead.v33m.mess_trajectory import extract_mess_trajectory
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    S = types.SimpleNamespace
    c = dispatch['candidate']; mid = c.mess_id; services = route_table.service_ids
    stay, pd, pc, q, energy = {}, {}, {}, {}, {}
    moves, routes = {}, {}
    if not c.is_stay:
        key = (mid, c.departure_slot, c.origin, c.destination)
        route = route_table[c.departure_slot, c.origin, c.destination]
        if tuple(route.route_link_ids) != tuple(c.route_link_ids) or c.connection_ready_slot != c.departure_slot + route.connection_ready_slots_15min:
            raise ValueError('CERTIFIED_ROUTE_AUTHORITY_MISMATCH')
        moves[key] = S(X=1.); routes[key] = route
    for t in range(96):
        service = c.origin if c.is_stay or t < c.departure_slot else c.destination if t >= c.connection_ready_slot else None
        for s in services:
            key = (mid, t, s); active = s == service
            stay[key] = S(X=float(active))
            pd[key] = S(X=float(dispatch['p_discharge_kw'][t]) if active else 0.)
            pc[key] = S(X=float(dispatch['p_charge_kw'][t]) if active else 0.)
            q[key] = S(X=float(dispatch['q_kvar'][t]) if active else 0.)
        energy[mid, t] = S(X=float(dispatch['energy_kwh'][t]))
    block = S(model=S(SolCount=1), inputs=S(mess_ids=(mid,), horizon_slots=96,
        route_table=route_table, electrical_authority=MessElectricalAuthority.from_repository()),
        move=moves, move_route=routes, stay=stay, p_discharge=pd, p_charge=pc, q=q, energy=energy)
    return extract_mess_trajectory(block)


def certified_child(trajectory, parent, context, objective, candidate_id, certificate):
    from dayahead.v40h import beam_driver as b
    from dayahead.v40h.recourse import validate_physics
    from dayahead.v40a.grid import controls_from_trajectory, evaluate_grid
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v40h.candidate_cache import verify_full_child
    slots = tuple((*parent.trajectory_slots, *(r.to_dict() for r in trajectory.slots)))
    accumulated = MessTrajectory(tuple(b._restore_slots(slots)))
    physical = validate_physics(accumulated)
    grid = evaluate_grid(context['coefficients'], controls_from_trajectory(context['coefficients'], context['aidc'], accumulated.slots), context['nodes'])
    if physical['status'] != 'PASS' or grid['status'] != 'PASS':
        violations=grid.get('violations',{})
        if (physical['status']=='PASS' and violations.get('transformer_polygon',0)>0
                and not any(v for k,v in violations.items() if k!='transformer_polygon')):
            raise RestrictedPolygonRejection(physical,grid)
        raise ValueError(('PHYSICAL_FAIL_CERTIFIED_CHILD',physical,grid))
    # Use the very same state construction and deterministic metadata as full children.
    full = types.SimpleNamespace(trajectory=trajectory, objective=objective, planning_rho=grid['rho_max'],
        best_bound=float('inf'), mip_gap=float('inf'), mip_start_accepted=False,
        preferred_mip_start_loaded=False, termination=certificate, work_limit_tiers_attempted=(), move_binary_count=0)
    seed = dict(candidate_id=candidate_id, trajectory_signature=b.trajectory_equivalence_sha([r.to_dict() for r in trajectory.slots]),
        restricted_objective=objective, seed_index=1, dispatch=None)
    make = types.FunctionType(ORIGINAL_CHILD.__code__, dict(ORIGINAL_CHILD.__globals__, solve_integrated_mess=lambda **kw:full))
    child = make(case=context['case'], mess_id=context['mess_id'], sequence_index=context['sequence_index'],
        parent=parent, seed=seed, aidc=context['aidc'], electrical=context['electrical'],
        route_table=context['route_table'], coefficients=context['coefficients'])
    child.vehicles[-1].update(certification=certificate, physical=physical, grid=grid, full_MILP_wallclock_seconds=0.,
        runtime_budget_contract_SHA=CONTRACT_SHA)
    verify_full_child(child, parent)
    return child


def begin_depth(day, case, index, mid, parents, aidc, electrical, coefficients, route_table, root):
    global ACTIVE
    ACTIVE = DepthBudget(day, os.environ['IEEE123_MESS_POLICY'], index + 1,
        output=os.environ['IEEE123_MESS_SEARCH_ROOT'])
    proof=recovery()
    if proof and proof['resume_depth']==index+1:
        assert proof['day']==day
        consumed=float(proof['elapsed_consumed_seconds'])
        assert 0<=consumed<CONTRACT['budget_seconds']
        ACTIVE.start-=consumed;ACTIVE.started_at-=consumed
    # Node metadata is supplied by worker, avoiding a second electrical load.
    ACTIVE.context = dict(case=case, mess_id=mid, sequence_index=index, aidc=aidc,
        electrical=electrical, coefficients=coefficients, route_table=route_table, nodes=NODES)
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v40h.beam_driver import _restore_slots
    neutral = MessTrajectory(tuple(_restore_slots([r for r in NEUTRAL if r['mess_id'] == mid])))
    # Validate the existing neutral reference for every retained parent before
    # search. This never manufactures an unsearched MOVE or fills from an old beam.
    for parent in parents:
        ACTIVE.check('CERTIFY_EXISTING_NEUTRAL_FALLBACK')
        child = certified_child(neutral, parent, ACTIVE.context, parent.current_planning_objective,
            'VERIFIED_NEUTRAL_STAY', 'EXISTING_NEUTRAL_PHYSICAL_CERTIFICATE')
        ACTIVE.fallbacks.append(child)
    ACTIVE.publish()


def observe(result):
    if not ACTIVE: return
    import v41r4_exact_cache as cache
    ACTIVE.evaluations += 1
    if cache.certified(result):
        dispatch = result[1]
        try:
            child = certified_child(dispatch_trajectory(dispatch, ACTIVE.context['route_table']), ACTIVE.parent,
                ACTIVE.context, float(dispatch['objective']), dispatch['candidate'].candidate_id, 'FIXED_ROUTE_EXACT_CERTIFIED')
        except RestrictedPolygonRejection as error:
            # Keep all inherited limits. This restricted result can still seed
            # the original full MILP, but cannot itself become a retained child.
            ACTIVE.retention_rejections+=1
            if ACTIVE.output:
                from dayahead.paper_analysis.storage import write_json
                folder=ACTIVE.output/'retention_rejections'
                token=hashlib.sha256((ACTIVE.parent.state_sha256+dispatch['candidate'].candidate_id).encode()).hexdigest()
                write_json(folder/(token+'.json'),dict(candidate=dispatch['candidate'].candidate_id,
                    depth=ACTIVE.depth,parent=ACTIVE.parent.state_sha256,physical=error.physical,grid=error.grid,
                    reason=str(error),retained=False,physical_limits_unchanged=True))
            ACTIVE.publish()
            return
        key = (ACTIVE.parent.state_sha256, dispatch['candidate'].candidate_id)
        ACTIVE.pool[key] = child
        ACTIVE.certified = len(ACTIVE.pool)
    else:
        signature = str(result[0].get('exact_optimality_certificate', ''))
        if 'STALLED' in signature or 'ROUND_LIMIT' in signature: ACTIVE.stalled += 1
        else: ACTIVE.infeasible += 1
    ACTIVE.publish()


def safe_local(beam, original, **kwargs):
    from dayahead.v37 import runner
    ACTIVE.parent = kwargs['parent']
    def level(**args):
        ACTIVE.check('K_EXPANSION')
        # Progress from enumeration supplies the exact FULL label.
        return original(**args)
    prior = runner._archived_k_attempt
    runner._archived_k_attempt = lambda *a, **k:None
    try:
        ACTIVE.check('PARENT_ENUMERATION')
        return runner._run_local_with_frozen_k_fallback(beam, level, **kwargs)
    except BudgetExpired:
        return [], dict(dynamic_feasible_candidates=0, static_candidates_fail_closed_evaluated=0,
            restricted_unique_candidate_state_solves=ACTIVE.evaluations, restricted_solver_calls=ACTIVE.evaluations,
            distinct_seed_count=0, cheap_screen_wallclock_seconds=0., restricted_wallclock_seconds=0.,
            K_fallback_attempts=[dict(K=k) for k in ACTIVE.k], selected_K=ACTIVE.k[-1] if ACTIVE.k else None,
            budget_exhausted=True, runtime_budget_contract_SHA=CONTRACT_SHA)
    finally: runner._archived_k_attempt = prior


def budget_pool(base):
    class Pool(base):
        def map(self, fn, iterable, *, chunksize=1, timeout=None):
            # The frozen production pool has exactly one child. Do not prequeue
            # candidates: no pending future can start after the shared deadline.
            for item in iterable:
                check('CANDIDATE_SUBMIT')
                yield self.submit(fn, item).result()
    return Pool


def select_pool(children, width):
    if ACTIVE.available(): return children
    from dayahead.v35r3e_r1.beam import deduplicate_children
    pool = [*children, *ACTIVE.pool.values()]
    unique, _ = deduplicate_children(pool)
    if len(unique) < width:
        pool.extend(ACTIVE.fallbacks)
    if not pool: raise ValueError('NO_CERTIFIED_CHILD_OR_EXISTING_FALLBACK')
    return pool


def finish_depth(retained):
    reason = 'SEARCH_COMPLETED' if ACTIVE.available() else 'SOFT_BUDGET_EXHAUSTED'
    ACTIVE.publish(retained, reason)


def observe_full(child):
    ACTIVE.pool[('FULL_CHILD', child.state_sha256)] = child
    ACTIVE.certified = len(ACTIVE.pool)
    ACTIVE.publish()


def install(*, nodes=None, neutral=None):
    global INSTALLED, ORIGINAL_CHILD, NODES, NEUTRAL
    if nodes is not None: NODES = nodes
    if neutral is not None: NEUTRAL = neutral
    if INSTALLED:return
    INSTALLED = True
    from dayahead.v40h import beam_driver as b, mobility
    ORIGINAL_CHILD = b._make_child
    from dayahead.v40a import observability
    observability.ObservedProductionPool = budget_pool(observability.ObservedProductionPool)
    from dayahead.v41 import solver_observer
    solver_observer.ObservedPool = budget_pool(solver_observer.ObservedPool)
    # Observe completed candidates before any subsequent deadline check.
    local = clone(b._local_search, [
        ('    fixed_p, fixed_q = _fixed_maps(parent.trajectory_slots)', "    check('LOCAL_ENUMERATION')\n    fixed_p, fixed_q = _fixed_maps(parent.trajectory_slots)"),
        ('    context = build_planning_screen_context(', "    check('SCREEN_MODEL_BUILD')\n    context = build_planning_screen_context("),
        ('    screen_rows, screen_seconds = screen_dynamic_candidates(', "    check('CANDIDATE_RANKING')\n    screen_rows, screen_seconds = screen_dynamic_candidates("),
        ('    for candidate in representatives:', "    for candidate in representatives:\n        check('REPRESENTATIVE_CANDIDATE')"),
        ('        row, dispatch, _evaluation, repair, cuts = result', '        observe(result)\n        row, dispatch, _evaluation, repair, cuts = result'),
        ('        row, dispatch, _evaluation, repair, _cuts = cached_results[candidate_id]', "        check('CACHED_CANDIDATE')\n        observe(cached_results[candidate_id])\n        row, dispatch, _evaluation, repair, _cuts = cached_results[candidate_id]"),
        ('        for index, (row, dispatch, _evaluation, repair, _cuts) in enumerate(results, start=1):',
         '        for index, (row, dispatch, _evaluation, repair, _cuts) in enumerate(results, start=1):\n            observe((row, dispatch, _evaluation, repair, _cuts))')
    ], dict(check=check, observe=observe))
    def local_call(**kwargs):
        local.__globals__.update(vars(b))
        return local(**kwargs)
    b._local_search = local_call
    mobility.safe_local = safe_local
    prior_progress = b._progress
    def progress(**value):
        if ACTIVE and value.get('event') == 'CANDIDATE_SEARCH':
            label = value['search_level']
            if label not in ACTIVE.k: ACTIVE.k.append(label)
            ACTIVE.publish()
        return prior_progress(**value)
    b._progress = progress
    run = clone(b._run_case, [
        ('            _progress(event="DEPTH_START", mess_index=sequence_index + 1, beam_width=width)',
         '            begin_depth(APR01, case, sequence_index, mess_id, beam, aidc, electrical, coefficients, route_table, root)\n            _progress(event="DEPTH_START", mess_index=sequence_index + 1, beam_width=width)'),
        ('            payload = restore_stage(stage_path, execution_identity, beam, sequence_index + 1)', '            payload = recover_stage(stage_path, execution_identity, beam, sequence_index + 1)'),
        ('            for parent_index, parent in enumerate(beam, start=1):', '            for parent_index, parent in enumerate(beam, start=1):\n                if not active_available(): break'),
        ('                for seed in seeds:', '                for seed in seeds:\n                    if not active_available(): break'),
        ('                        child = _make_child(', '                        child = guarded_child('),
        ('                    verify_full_child(child, parent)', '                    if child is None: break\n                    verify_full_child(child, parent)\n                    observe_full(child)'),
        ('                        _json(child_path, child.to_dict())', '                        if child is None: break\n                        _json(child_path, child.to_dict())'),
        ('            unique, dedup = deduplicate_children(children)', '            children = select_pool(children, width)\n            unique, dedup = deduplicate_children(children)'),
        ('            trace.append(trace_row)', '            finish_depth(retained)\n            trace_row["runtime_budget_contract_SHA"] = CONTRACT_SHA\n            trace.append(trace_row)'),
        ('            write_stage(stage_path, payload, execution_identity, beam, sequence_index + 1)',
         '            payload["runtime_budget_contract_SHA"] = CONTRACT_SHA\n            trace_row["runtime_budget_contract_SHA"] = CONTRACT_SHA\n            write_stage(stage_path, payload, execution_identity, beam, sequence_index + 1)'),
        ('        _json(root / "FINAL_RESULT.json", final)', '        final["runtime_budget_contract_SHA"] = CONTRACT_SHA\n        _json(root / "FINAL_RESULT.json", final)')
    ], dict(begin_depth=begin_depth, active_available=lambda:ACTIVE.available(), guarded_child=guarded_child,
        select_pool=select_pool, finish_depth=finish_depth, observe_full=observe_full, recover_stage=recover_stage, CONTRACT_SHA=CONTRACT_SHA))
    def run_call(*args, **kwargs):
        run.__globals__.update(vars(b))
        try:return run(*args, **kwargs)
        except BaseException as error:
            if ACTIVE:
                reason = 'PHYSICAL_FAIL' if 'PHYSICAL' in str(error) else 'USER_GRACEFUL_STOP' if isinstance(error, GracefulStop) else 'SOLVER_FATAL'
                ACTIVE.publish(reason=reason)
            raise
    b._run_case = run_call
    install_solver_boundary()


def guarded_child(**kwargs):
    from dayahead.v40h import beam_driver as b
    check('FULL_MILP_BUILD')
    ACTIVE.full_active += 1
    try: return b._make_child(**kwargs)
    except BudgetExpired: return None
    finally: ACTIVE.full_active -= 1


def install_solver_boundary():
    """An already started fixed-certification is atomic; full solver passes are not queued."""
    import gurobipy as gp
    from dayahead.v41 import solver_observer
    original = solver_observer.observed
    @functools.wraps(original)
    def optimize(model, *args, **kwargs):
        if ACTIVE and ACTIVE.full_active: check('FULL_SOLVER_CALL')
        return original(model, *args, **kwargs)
    solver_observer.observed = optimize
