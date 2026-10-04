"""Bounded synthetic evidence only. Run explicitly with python -m ...fixtures."""
import os
for _name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'

from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone

import numpy as np
from scipy.sparse import csr_matrix

from .contracts import BASE_HEAD, Candidate, DiscoverySnapshot, RuntimeFlags, canonical, digest
from .validation import DiscoveryController, OriginalBlockValidator, validate_batches, validate_candidate
from .audit import AuditAuthority, AuditCache, AuditReceipt, audit_plan, make_authority
from .rmp import PersistentRMP, RMPRows, RMPColumn, build_rmp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_dw_runtime_acceleration'


def write(name, value, directory=OUT):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                           allow_nan=False) + '\n', encoding='utf8', newline='\n')


def snapshot(iteration=1):
    return DiscoverySnapshot.create(iteration, (0.,), (0.,), (10.,)*4, (20.,)*4, .3, 40.)


def pricing_fixture(unit=0):
    """Ten-selector synthetic domain and 96-slot idle route using REAL PR143 audits.

    This is a tiny physical plan, not a production matrix or pricing problem.
    A selector chooses one legal reactive-power profile at the first slot.
    """
    from v42_dw_resume.audit import Block, pure_binary_equalities
    from v42_native.mess import Battery
    b = Block.__new__(Block)
    b.unit = 'MESS%02d' % (unit+1)
    u = b.unit
    costs = [12., 8., 7., 6., 5., 4., 3., 2., 1., 0.]
    names = ['selector[%s,%d]' % (u, i) for i in range(10)]
    for prefix in ('arc', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q'):
        for t in range(96):
            if prefix in ('Pch', 'Pdis', 'Q'):
                names.append('%s[%s,S,%d]' % (prefix, u, t))
            else:
                names.append('%s[%s,%d]' % (prefix, u, t+1 if prefix == 'SOC' else t))
    n = len(names)
    template = np.zeros(n)
    template[10:106] = 1.
    template[202:298] = 1.
    lower, upper = template.copy(), template.copy()
    lower[:10], upper[:10] = 0., 1.
    qix = names.index('Q[%s,S,0]' % u)
    lower[qix], upper[qix] = 0., .9
    objective = np.zeros(n)
    objective[:10] = costs
    types = np.full(n, 'C', dtype='U1')
    types[:202] = 'B'
    A = np.zeros((2, n))
    A[0, :10] = 1.
    A[1, :10] = -np.arange(10)/10
    A[1, qix] = 1.
    b.A = csr_matrix(A)
    b.B = csr_matrix(([1.], ([0], [qix])), shape=(1, n))
    b.d = dict(names=np.asarray(names), rhs=np.array([1., 0.]), sense=np.array(['=', '=']),
               lower=lower, upper=upper, types=types, objective=objective,
               constant=np.array(0.), row_names=np.array(['select_one', 'reactive_profile_binding']))
    b.columns = np.arange(n)
    b.mask = types != 'C'
    b.route_mask = pure_binary_equalities(b.A, b.d)
    b.sites, b.initial = ('S',), {u: 'S'}
    b.arcs = [('S', t, 'S', t+1, None) for t in range(96)]
    b.battery = Battery(0., 2., 1., 1., 1., 1., 1., 1., .25)
    validator = OriginalBlockValidator(unit, b, b.A, b.d, b.route_mask)
    points = []
    for i in range(10):
        x = template.copy()
        x[i] = 1.
        x[qix] = i/10
        points.append(tuple(x))
    return validator, points


def toy_authority(validator):
    sources = [ROOT/p for p in ('v42_dw_resume/audit.py', 'v42_integrated/matrix.py',
        'v42_native/mess.py', 'v42_bootstrap/attribution.py', 'v42_dw_runtime/validation.py')]
    b = validator.block
    return make_authority(BASE_HEAD, [(b.A, b.d), (b.B, {})], b.d['names'], b.d['row_names'],
        b''.join(p.read_bytes() for p in sources),
        dict(sites=b.sites, initial=b.initial, arcs=b.arcs, battery=asdict(b.battery)),
        dict(affine=1e-6, bounds=1e-8, route=1e-8, integer_pattern='exact', true_RC=-1e-7,
             physical_original=1e-5))


def early_stop_proof(environment):
    import gurobipy as gp
    validator, points = pricing_fixture()
    snap = snapshot()
    flags = RuntimeFlags(DW_DISCOVERY_EARLY_STOP=True)
    valid = [validate_candidate(Candidate(0, x, 1, snap.dual_SHA), snap, validator) for x in points]
    assert sum(r.accepted for r in valid) == 9
    assert not valid[0].accepted and valid[0].search_RC < 0 and valid[0].true_RC > 0
    runs = []
    for early in (True, False):
        b = validator.block
        model = gp.Model('DW_RUNTIME_PRICE_TOY', env=environment)
        try:
            for key, value in dict(OutputFlag=0, Threads=1, TimeLimit=5., FeasibilityTol=1e-8,
                                   IntFeasTol=1e-8, OptimalityTol=1e-8).items():
                model.setParam(key, value)
            x = model.addMVar(len(b.columns), lb=b.d['lower'], ub=b.d['upper'],
                             obj=b.d['objective'], vtype=b.d['types'])
            model.addMConstr(b.A, x, b.d['sense'], b.d['rhs'])
            model.ObjCon = -20.
            model.update()
            variables = model.getVars()
            # Multiple legal complete MIP starts trigger native improving incumbents.
            # They do not remove or fix any point in the toy pricing domain.
            model.NumStart = len(points)
            for i, point in enumerate(points):
                model.Params.StartNumber = i
                model.setAttr('Start', variables, point)
            model.update()
            controller = DiscoveryController('DISCOVERY', 0, snap, validator, flags)
            arrivals = []
            def callback(native, where):
                if where == gp.GRB.Callback.MIPSOL:
                    values = native.cbGetSolution(variables)
                    result = validate_candidate(Candidate(0, values, 1, snap.dual_SHA), snap, validator)
                    arrivals.append(asdict(result))
                    if early:
                        controller.observe(values, native, float(native.cbGet(gp.GRB.Callback.MIPSOL_OBJ)))
            identity = dict(rows=model.NumConstrs, columns=model.NumVars, nnz=model.NumNZs,
                            lower=model.getAttr('LB'), upper=model.getAttr('UB'),
                            matrix=b.A.toarray().tolist(), objective=model.getAttr('Obj'),
                            senses=model.getAttr('Sense'), rhs=model.getAttr('RHS'))
            start = time.perf_counter()
            model.optimize(callback)
            elapsed = time.perf_counter() - start
            receipt = controller.terminal_receipt(model.Status)
            legal = all(r.accepted for r in controller.accepted.values())
            runs.append(dict(path='early' if early else 'continued', status=int(model.Status),
                callback_arrivals=arrivals, receipt=receipt, all_added_columns_legal=legal,
                identity_SHA=digest(identity), optimize_seconds=elapsed,
                native_runtime_seconds=float(model.Runtime),
                quota_request_callback_index=len(controller.results) if early else None,
                native_callbacks_after_quota_request=len(arrivals)-len(controller.results) if early else None,
                native_objective=float(model.ObjVal) if model.SolCount else None,
                Threads=int(model.Params.Threads), TimeLimit=float(model.Params.TimeLimit)))
        finally:
            model.dispose()
    assert runs[0]['status'] == gp.GRB.INTERRUPTED
    assert runs[0]['receipt']['accepted_count'] == 4
    assert runs[0]['receipt']['STOP_REASON'] == 'DISCOVERY_QUOTA_FILLED'
    assert runs[1]['status'] == gp.GRB.OPTIMAL
    assert runs[0]['identity_SHA'] == runs[1]['identity_SHA']
    return dict(PASS=True, full_domain_trajectories=10, valid_true_negative_trajectories=9,
                smoothed_only_candidate_rejected=True, globally_best_four_required=False,
                native_MIPSOL_multiple_incumbents=True, fixture_scope='synthetic; original PR143 physical validators',
                production_pricing_calls=0, runs=runs)


def validation_proof():
    snap = snapshot()
    validators, batches = {}, {}
    for unit in range(4):
        validator, points = pricing_fixture(unit)
        validators[unit] = validator
        fractional = tuple((a+b)/2 for a, b in zip(points[1], points[2]))
        physical_bad = list(points[1])
        physical_bad[validator.block.d['names'].tolist().index('Q[%s,S,0]' % validator.block.unit)] = 2.
        batches[unit] = [Candidate(unit, x, 1, snap.dual_SHA)
                         for x in points + [points[1], fractional, tuple(physical_bad)]]
        batches[unit].append(Candidate(unit, points[2], 0, snap.dual_SHA))
    sequential = validate_batches(batches, snap, validators, RuntimeFlags())
    started = time.perf_counter()
    parallel = validate_batches({u: tuple(reversed(b)) for u, b in reversed(list(batches.items()))},
                                snap, validators, RuntimeFlags(DW_PARALLEL_VALIDATION=True))
    wall = time.perf_counter() - started
    assert parallel == sequential
    rows = [asdict(r) for r in sequential]
    return dict(PASS=True, exact_equality=True, workers=4, worker_type='threads; Python only; no solver',
                bounded_candidates=sum(map(len, batches.values())), canonical_results_SHA=digest(rows),
                parallel_wall_seconds=wall, accepted_SHA_set=sorted({r.trajectory_SHA for r in parallel if r.accepted}),
                rejected_SHA_set=sorted({r.trajectory_SHA for r in parallel if not r.accepted}),
                exact_fields=['accepted/rejected SHA', 'reasons', 'true_RC', 'search_RC', 'physical_residuals'],
                canonical_results=rows)


def cache_proof(directory):
    validator, points = pricing_fixture()
    snap = snapshot()
    result = validate_candidate(Candidate(0, points[1], 1, snap.dual_SHA), snap, validator)
    authority = toy_authority(validator)
    cache = AuditCache()
    receipt = AuditReceipt.issue(result, authority, datetime.now(timezone.utc).isoformat(), 'lane-c-toy')
    cache.add(receipt)
    assert cache.lookup(receipt.trajectory_SHA, authority) is receipt
    flags = RuntimeFlags(DW_INCREMENTAL_AUDIT=True)
    plan = audit_plan('DISCOVERY', [receipt.trajectory_SHA], [], authority, cache, flags)
    assert plan['columns_to_full_audit'] == [] and plan['current_RMP_point_required']
    invalidations = []
    for field in asdict(authority):
        changed = replace(authority, **{field: 'a'*64 if getattr(authority, field) != 'a'*64 else 'b'*64})
        assert cache.lookup(receipt.trajectory_SHA, changed) is None
        forced = audit_plan('DISCOVERY', [receipt.trajectory_SHA], [], changed, cache, flags)
        assert forced['columns_to_full_audit'] == [receipt.trajectory_SHA]
        invalidations.append(dict(changed=field, invalidated=True, full_reaudit_forced=True))
    checkpoint = directory/'DW_AUDIT_RECEIPTS_TOY.json'
    cache.save(checkpoint)
    loaded = AuditCache.load(checkpoint)
    assert loaded.lookup(receipt.trajectory_SHA, authority) == receipt
    # Same physical receipt is valid, but RC becomes positive under the next true dual.
    next_snap = DiscoverySnapshot.create(2, (0.,), (0.,), (0.,)*4, (20.,)*4, .3, 0.)
    refreshed = validate_candidate(Candidate(0, points[1], 2, next_snap.dual_SHA), next_snap, validator)
    assert not refreshed.accepted and refreshed.true_RC > 0
    return dict(PASS=True, receipt=asdict(receipt), receipt_key=receipt.key, equal_authority_reused=True,
                invalidations=invalidations, disk_roundtrip_exact=True,
                current_RC_recomputed_after_dual_change=True, refreshed_RC=refreshed.true_RC,
                discovery_plan=plan, certification_plan=audit_plan('CERTIFICATION', [receipt.trajectory_SHA],
                   [], authority, cache, flags), no_historical_RC_reuse=True)


def rmp_fixture_data():
    rows = RMPRows(('capacity', 'convexity_MESS01', 'convexity_MESS02'), (1., 1., 1.), ('<', '=', '='), .125)
    batches = [
        (RMPColumn('seed01', (0., 1., 0.), 3.), RMPColumn('seed02', (0., 0., 1.), 4.)),
        (RMPColumn('lambda01a', (1., 1., 0.), 1.),),
        (RMPColumn('lambda02a', (.5, 0., 1.), 2.5),),
        (RMPColumn('lambda01b', (.25, 1., 0.), .75),),
    ]
    return rows, batches


def close_enough(left, right, tolerance=1e-8):
    return bool(np.allclose(left, right, atol=tolerance, rtol=0.))


def rmp_proof(environment, directory):
    rows, batches = rmp_fixture_data()
    persistent = None
    registry, iterations, timings = [], [], []
    try:
        for iteration, batch in enumerate(batches):
            started = time.perf_counter()
            registry.extend(batch)
            # Python registry reconstruction is measured separately from Gurobi model build.
            fresh_rows = RMPRows(**json.loads(canonical(asdict(rows))))
            fresh_columns = [RMPColumn(**json.loads(canonical(asdict(c)))) for c in registry]
            python_seconds = time.perf_counter() - started
            started = time.perf_counter()
            fresh = build_rmp(fresh_rows, fresh_columns, RuntimeFlags(), environment=environment)
            build_seconds = time.perf_counter() - started
            try:
                fresh_identity = fresh.identity()
                fresh_result = fresh.solve()
            finally:
                fresh.close()
            started = time.perf_counter()
            persistent = build_rmp(rows, registry, RuntimeFlags(DW_PERSISTENT_RMP=True),
                                   persistent=persistent, environment=environment)
            update_seconds = time.perf_counter() - started
            retained_identity = persistent.identity()
            retained_result = persistent.solve()
            assert retained_identity == fresh_identity
            for field in ('objective', 'solution', 'duals'):
                assert close_enough(retained_result[field], fresh_result[field]), (iteration, field)
            iterations.append(dict(iteration=iteration, PASS=True, identity=retained_identity,
                                   fresh=fresh_result, persistent=retained_result,
                                   solution_and_duals_tolerance=1e-8))
            timings.append(dict(iteration=iteration, fresh_python_reconstruction=python_seconds,
                fresh_Gurobi_build=build_seconds, fresh_optimize=fresh_result['optimize_seconds'],
                persistent_initial_build=update_seconds if iteration == 0 else None,
                persistent_add_column_update=update_seconds if iteration else None,
                persistent_optimize=retained_result['optimize_seconds'],
                fresh_native_runtime=fresh_result['native_runtime_seconds'],
                persistent_native_runtime=retained_result['native_runtime_seconds']))
        checkpoint = directory/'DW_RMP_REGISTRY_TOY.json'
        persistent.checkpoint(checkpoint)
        identity_before = persistent.identity()
        result_before = iterations[-1]['persistent']
        persistent.close()
        persistent = None
        rebuilt = PersistentRMP.restart(checkpoint, environment=environment)
        try:
            after_identity, after = rebuilt.identity(), rebuilt.solve()
            assert after_identity == identity_before
            assert all(close_enough(after[k], result_before[k]) for k in ('objective', 'solution', 'duals'))
        finally:
            rebuilt.close()
        restart = dict(PASS=True, simulated_restart='dispose prior model; reload authoritative disk registry',
                       process_restart_verified=False, registry_SHA=json.loads(checkpoint.read_text())['registry_SHA'],
                       identity_exact=True, objective_duals_solution_equivalent=True, recovered=after)
        return (dict(PASS=True, iterations=iterations, warm_basis_selected=False, no_basis_import=True),
                dict(PASS=True, scope='toy only; no production speed extrapolation', seconds=timings,
                     reset_before_every_optimize=True, LPWarmStart=0,
                     wall_timing_includes_bounded_guard_sampling=True,
                     native_Runtime_recorded_separately=True), restart)
    finally:
        if persistent is not None:
            persistent.close()


def certification_proof():
    from .contracts import certification_settings
    from v42_dw_bound.certificate import corrected, receipt
    snap = DiscoverySnapshot.create(7, (2.,), (-3.,), (10.,)*4, (20.,)*4, .3, 40.)
    flags = RuntimeFlags(True, True, True, True)
    paths = {kind: certification_settings(kind, snap, flags)
             for kind in ('CERTIFICATION', 'FINAL_CERTIFICATION')}
    for settings in paths.values():
        assert settings['search_dual'] == snap.true_dual
        assert settings['convexity_dual'] == snap.convexity_dual
        assert settings['dual_SHA'] == snap.dual_SHA
        assert not settings['early_quota_terminate'] and not settings['incremental_pool_audit']
        assert settings['global_BestBd_required'] and not settings['smoothed_certificate']
    lower, exact, beta, delta = corrected(Fraction(10), [0.]*4, [-1., 0., 1., -2.])
    assert all(b <= Fraction(v)-Fraction(1e-8) for b, v in zip(beta, [-1., 0., 1., -2.]))
    assert lower <= float(exact) and exact == Fraction(10) + sum(min(Fraction(0), b) for b in beta)
    interrupted = [dict(ObjBound=-1., valid_bound=False, native_status=11)]*4
    rejected = receipt(1, 1, None, [0.]*4, snap.dual_SHA, Fraction(10), {}, interrupted, 20., None, None)
    assert not rejected['certified'] and rejected['L_corr'] is None
    return dict(PASS=True, paths=paths, corrected_LB=lower, exact_LB=str(exact),
                interrupted_quota_receipt_cannot_certify=True, exact_original_corrected_function_executed=True,
                certification_production_code_modified=False)


def baseline_audit():
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    checkpoint_path = 'docs/v42_m1_dw_throughput_optimization/DW_THROUGHPUT_CHECKPOINT_LATEST.json'
    checkpoint = json.loads((ROOT/checkpoint_path).read_text(encoding='utf8'))
    assert len(checkpoint['pool']) == 1158
    modified = git('diff', BASE_HEAD, '--name-only').splitlines()
    assert all(p.startswith(('v42_dw_runtime/', 'tests/v42_dw_runtime/', 'docs/v42_m1_dw_runtime_acceleration/'))
               for p in modified)
    paths = ['v42_dw_throughput/worker.py', 'v42_dw_throughput/run.py', 'v42_dw_resume/audit.py',
             'v42_dw_root/models.py', 'v42_dw_root/run.py', 'v42_dw_bound/certificate.py',
             'v42_native/mess.py', 'v42_bootstrap/attribution.py', checkpoint_path]
    bindings = []
    for path in paths:
        expected_blob = git('rev-parse', BASE_HEAD+':'+path)
        local_blob = git('hash-object', '--path='+path, path)
        assert local_blob == expected_blob
        bindings.append(dict(path=path, git_blob=expected_blob,
                             local_file_SHA256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()))
    return dict(PASS=True, base_SHA=BASE_HEAD, PR143_exact_head=True,
        retained_checkpoint_columns=1158, checkpoint_pool_SHA=digest(checkpoint['pool']),
        audit_scope='source/registry byte identity; no full scientific matrix load or historical physical revalidation',
        authority=dict(actual_4way_pricing='PR142 observed PASS; not rerun', Threads=1, RAM_floor_GiB=1,
                       warm_basis_selected=False, smoothing='Discovery only', true_RC_threshold=-1e-7,
                       max_columns_per_MESS=4, max_columns_per_round=16), preserved_bindings=bindings)


def main():
    import gurobipy as gp
    from .testing import bounded_solver_calls
    OUT.mkdir(parents=True, exist_ok=True)
    write('DW_RUNTIME_BASE_AUDIT.json', baseline_audit())
    started = time.perf_counter()
    # One sequential process, one active optimize at a time. Never use production entrypoints.
    with bounded_solver_calls() as measured, gp.Env(empty=True) as environment:
        environment.setParam('OutputFlag', 0)
        environment.setParam('Threads', 1)
        environment.start()
        early = early_stop_proof(environment)
        write('DW_EARLY_STOP_FIXTURE.json', early)
        write('DW_PARALLEL_VALIDATOR_EQUIVALENCE.json', validation_proof())
        write('DW_AUDIT_CACHE_INVALIDATION_TEST.json', cache_proof(OUT))
        equivalence, timing, restart = rmp_proof(environment, OUT)
        write('DW_PERSISTENT_RMP_EQUIVALENCE.json', equivalence)
        write('DW_PERSISTENT_RMP_TIMING_TOY.json', timing)
        write('DW_PERSISTENT_RMP_RESTART_TEST.json', restart)
    write('DW_CERTIFICATION_FIREWALL_TEST.json', certification_proof())
    write('DW_BOUNDED_RESOURCE_RECEIPT.json', dict(PASS=True, Threads=1,
        max_concurrent_Gurobi_processes=1, max_concurrent_optimize=1, per_fixture_TimeLimit=5.,
        maximum_allowed_fixture_seconds=30., production_M1_calls=0, full_scale_Arc_LP_calls=0,
        production_RMP_calls=0, production_pricing_calls=0, production_OpenDSS_calls=0,
        May_production_calls=0, wall_seconds=time.perf_counter()-started,
        validator_workers=4, validator_scope='14 synthetic candidates per MESS',
        full_pytest_deferred=True, memory_stress=False, solver_calls=measured['calls'],
        peak_sampled_RSS_bytes=measured['peak_sampled_RSS'],
        minimum_sampled_available_RAM=measured['minimum_sampled_available_RAM'],
        observed_all_solver_calls_bounded=all(c['wall_seconds'] <= 30 for c in measured['calls']),
        sample_scope='own process before/after solver calls; unsampled peaks not claimed'))
    print('Lane C bounded fixtures: PASS')


if __name__ == '__main__':
    main()
