"""Lane C only: tiny native solver fixtures + original audits on synthetic points."""
from dataclasses import FrozenInstanceError, asdict, replace
import json

import gurobipy as gp
import numpy as np
import pytest

from v42_dw_runtime.contracts import (Candidate, DiscoverySnapshot, RuntimeFlags,
                                     STOP_REASON, canonical, certification_settings)
from v42_dw_runtime.validation import DiscoveryController, validate_candidate, validate_batches
from v42_dw_runtime.audit import AuditCache, AuditReceipt, execute_audit_tiers, make_authority
from v42_dw_runtime.rmp import PersistentRMP, build_rmp
from v42_dw_runtime.fixtures import (baseline_audit, cache_proof, certification_proof, early_stop_proof,
    pricing_fixture, rmp_fixture_data, rmp_proof, snapshot, toy_authority, validation_proof)


@pytest.fixture(scope='module')
def native_proofs(tmp_path_factory):
    path = tmp_path_factory.mktemp('lane_c')
    with gp.Env(empty=True) as env:
        env.setParam('OutputFlag', 0)
        env.setParam('Threads', 1)
        env.start()
        early = early_stop_proof(env)
        equivalence, timing, restart = rmp_proof(env, path)
    return dict(early=early, equivalence=equivalence, timing=timing, restart=restart)


def test_native_early_stop_only_legal_columns(native_proofs):
    proof = native_proofs['early']
    assert proof['PASS'] and proof['valid_true_negative_trajectories'] > 4
    early = proof['runs'][0]
    assert early['all_added_columns_legal']
    assert len(early['receipt']['accepted_SHAs']) == len(set(early['receipt']['accepted_SHAs'])) == 4
    added = set(early['receipt']['accepted_SHAs'])
    assert all(r['accepted'] and r['true_RC'] <= -1e-7 and
               json.loads(r['physical_residuals_json'])['integral']
               for r in early['callback_arrivals'] if r['trajectory_SHA'] in added)


def test_native_quota_interrupted_is_not_optimal(native_proofs):
    early, continued = native_proofs['early']['runs']
    assert early['status'] == 11 and continued['status'] == 2
    assert early['receipt']['STOP_REASON'] == STOP_REASON
    assert not any(early['receipt'][key] for key in
                   ('pricing_optimality_claimed', 'valid_bound', 'no_negative_certificate', 'pricing_convergence'))
    assert early['identity_SHA'] == continued['identity_SHA']


def test_smoothed_only_negative_never_accepted(native_proofs):
    observations = native_proofs['early']['runs'][0]['callback_arrivals']
    bad = [r for r in observations if r['search_RC'] < 0 and r['true_RC'] > 0]
    assert bad and all(not r['accepted'] and 'TRUE_RC_NOT_NEGATIVE' in r['reasons'] for r in bad)


def test_snapshot_is_deeply_immutable_and_detached():
    true = np.array([0.])
    snap = DiscoverySnapshot.create(1, true, (0.,), (10.,)*4, (20.,)*4, .3, 40.)
    true[0] = 100.
    assert snap.true_dual == (0.,)
    with pytest.raises(FrozenInstanceError):
        snap.alpha = .5
    with pytest.raises(TypeError):
        snap.true_dual[0] = 1
    with pytest.raises(ValueError, match='SHA mismatch'):
        replace(snap, dual_SHA='0'*64)


@pytest.mark.parametrize('iteration,sha', [(0, None), (1, '0'*64)])
def test_stale_true_dual_rejected(iteration, sha):
    validator, points = pricing_fixture()
    snap = snapshot()
    result = validate_candidate(Candidate(0, points[1], iteration, sha or snap.dual_SHA), snap, validator)
    assert not result.accepted and 'STALE_TRUE_DUAL' in result.reasons


def test_no_raw_capture_quota_or_duplicate_retained_quota():
    validator, points = pricing_fixture()
    snap = snapshot()
    class Native:
        stops = 0
        def terminate(self): self.stops += 1
    native = Native()
    flags = RuntimeFlags(DW_DISCOVERY_EARLY_STOP=True)
    retained = validator.trajectory_sha(points[1])
    controller = DiscoveryController('DISCOVERY', 0, snap, validator, flags, [retained])
    for _ in range(8):
        controller.observe(points[0], native)
        controller.observe(points[1], native)
    assert not controller.accepted and not native.stops
    for _ in range(8):
        controller.observe(points[2], native)
    assert len(controller.accepted) == 1 and not native.stops
    for x in points[3:6]: controller.observe(x, native)
    assert len(controller.accepted) == 4 and native.stops == 1
    controller.observe(points[6], native)
    assert len(controller.accepted) == 4 and native.stops == 1


def test_integrality_and_physical_failures_do_not_fill_quota():
    validator, points = pricing_fixture()
    snap = snapshot()
    fractional = tuple((a+b)/2 for a,b in zip(points[1], points[2]))
    result = validate_candidate(Candidate(0, fractional, 1, snap.dual_SHA), snap, validator)
    assert not result.accepted and 'NONINTEGRAL' in result.reasons
    bad = list(points[1])
    bad[validator.block.d['names'].tolist().index('Q[MESS01,S,0]')] = 2.
    result = validate_candidate(Candidate(0, bad, 1, snap.dual_SHA), snap, validator)
    assert not result.accepted and 'PHYSICAL_INFEASIBLE' in result.reasons


def test_callback_errors_fail_closed_and_search_objective_must_match():
    validator, points = pricing_fixture()
    class Native:
        def terminate(self): pass
    controller = DiscoveryController('DISCOVERY', 0, snapshot(), validator,
                                     RuntimeFlags(DW_DISCOVERY_EARLY_STOP=True))
    result = controller.observe(points[1], Native(), observed_objective=-100.)
    assert not result.accepted and 'SEARCH_OBJECTIVE_MISMATCH' in result.reasons
    controller.observe(points[2], Native())
    assert len(controller.accepted) == 1
    controller.observe((1.,), Native())
    assert controller.errors and not controller.accepted
    assert controller.stop_reason == 'CALLBACK_VALIDATION_ERROR'


def test_parallel_and_sequential_identical_reasons_RC_residuals():
    assert validation_proof()['exact_equality']


def test_parallel_validation_never_solves(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Validation must not optimize')
    monkeypatch.setattr(gp.Model, 'optimize', forbidden)
    validator, points = pricing_fixture()
    snap = snapshot()
    result = validate_batches({0: [Candidate(0, points[1], 1, snap.dual_SHA)]}, snap, {0: validator},
                              RuntimeFlags(DW_PARALLEL_VALIDATION=True))
    assert result[0].accepted


def test_incremental_cache_exact_SHA_invalidation_and_RC_refresh(tmp_path):
    proof = cache_proof(tmp_path)
    assert proof['equal_authority_reused'] and proof['no_historical_RC_reuse']
    assert len(proof['invalidations']) == 7 and all(r['invalidated'] for r in proof['invalidations'])
    assert proof['current_RC_recomputed_after_dual_change'] and proof['refreshed_RC'] > 0


def test_audit_receipt_immutable_and_disk_integrity(tmp_path):
    validator, points = pricing_fixture()
    snap = snapshot()
    result = validate_candidate(Candidate(0, points[1], 1, snap.dual_SHA), snap, validator)
    receipt = AuditReceipt.issue(result, toy_authority(validator), '2026-10-04T00:00:00Z', 'test')
    cache = AuditCache()
    cache.add(receipt)
    with pytest.raises(FrozenInstanceError): receipt.true_RC = -1.
    with pytest.raises(ValueError, match='overwritten'): cache.add(replace(receipt, run_id='other'))
    path = tmp_path/'receipt.json'
    cache.save(path)
    payload = json.loads(path.read_text())
    payload['receipts'][0]['max_residual'] = 123
    path.write_text(canonical(payload))
    with pytest.raises(ValueError, match='identity mismatch'): AuditCache.load(path)


def test_tier_execution_reuses_only_valid_physical_receipts(tmp_path):
    validator, points = pricing_fixture()
    snap = snapshot()
    authority = toy_authority(validator)
    receipts = [AuditReceipt.issue(validate_candidate(Candidate(0,x,1,snap.dual_SHA), snap,validator),
                                  authority, 'now', 'test') for x in points[1:3]]
    cache = AuditCache()
    cache.add(receipts[0])
    lookup = {r.trajectory_SHA: r for r in receipts}
    called = []
    def column_audit(sha):
        called.append(sha)
        return lookup[sha]
    result = execute_audit_tiers('DISCOVERY', list(lookup), [receipts[1].trajectory_SHA], authority,
        cache, RuntimeFlags(DW_INCREMENTAL_AUDIT=True), lambda: dict(PASS=True), column_audit)
    assert called == [receipts[1].trajectory_SHA] and result['PASS']
    called.clear()
    execute_audit_tiers('CERTIFICATION', list(lookup), [], authority, cache,
        RuntimeFlags(DW_INCREMENTAL_AUDIT=True), lambda: dict(PASS=True), column_audit)
    assert set(called) == set(lookup)
    with pytest.raises(ValueError, match='Current RMP'):
        execute_audit_tiers('DISCOVERY', list(lookup), [], authority, cache, RuntimeFlags(),
                           lambda: dict(PASS=False), column_audit)


def test_persistent_and_rebuild_matrix_primal_dual_equivalence(native_proofs):
    for iteration in native_proofs['equivalence']['iterations']:
        assert iteration['PASS']
        identity = iteration['identity']
        assert identity['row_count'] == 3 and identity['nnz'] > 0
        assert identity['model_sense'] == 1 and set(identity['types']) == {'C'}
        assert all(np.allclose(iteration['fresh'][field], iteration['persistent'][field], atol=1e-8, rtol=0)
                   for field in ('objective','solution','duals'))
        assert iteration['persistent']['LPWarmStart'] == 0


def test_persistent_restart_registry_authority(native_proofs):
    assert native_proofs['restart']['identity_exact']
    assert native_proofs['restart']['objective_duals_solution_equivalent']
    assert native_proofs['restart']['recovered']['solution_state_reset']


def test_persistent_update_rejects_nonappend_registry_and_tampering(tmp_path):
    rows, batches = rmp_fixture_data()
    with gp.Env(empty=True) as env:
        env.setParam('OutputFlag', 0)
        env.start()
        model = PersistentRMP(rows, batches[0], environment=env)
        try:
            with pytest.raises(ValueError, match='authority changed'):
                build_rmp(rows, tuple(reversed(batches[0])), RuntimeFlags(DW_PERSISTENT_RMP=True), model)
            path = tmp_path/'registry.json'
            model.checkpoint(path)
        finally:
            model.close()
        data = json.loads(path.read_text())
        data['registry']['columns'][0]['objective'] = 100.
        path.write_text(canonical(data))
        with pytest.raises(ValueError, match='SHA mismatch'): PersistentRMP.restart(path, environment=env)


def test_no_warm_basis_policy_and_timing_separated(native_proofs):
    assert not native_proofs['equivalence']['warm_basis_selected']
    assert native_proofs['timing']['LPWarmStart'] == 0
    for row in native_proofs['timing']['seconds']:
        assert row['fresh_python_reconstruction'] >= 0 and row['fresh_Gurobi_build'] >= 0
        assert row['fresh_optimize'] >= 0 and row['persistent_optimize'] >= 0


@pytest.mark.parametrize('kind', ['CERTIFICATION', 'FINAL_CERTIFICATION'])
def test_certification_has_no_quota_and_true_unstabilized_dual(kind):
    validator, points = pricing_fixture()
    class Native:
        def terminate(self): raise AssertionError('Certification must not quota terminate')
    controller = DiscoveryController(kind, 0, snapshot(), validator, RuntimeFlags(True, True, True, True))
    for point in points: assert controller.observe(point, Native()) is None
    assert not controller.enabled and not controller.accepted
    settings = certification_settings(kind, snapshot(), RuntimeFlags(True, True, True, True))
    assert not settings['early_quota_terminate'] and settings['global_BestBd_required']
    assert settings['search_dual'] == snapshot().true_dual


def test_original_corrected_LB_and_interrupted_receipt_firewall():
    assert certification_proof()['interrupted_quota_receipt_cannot_certify']


def test_feature_flags_default_off_and_independent():
    assert not any(asdict(RuntimeFlags()).values())
    flags = RuntimeFlags.from_environment(dict(DW_INCREMENTAL_AUDIT='true'))
    assert flags.DW_INCREMENTAL_AUDIT and not flags.DW_DISCOVERY_EARLY_STOP
    with pytest.raises(ValueError): RuntimeFlags.from_environment(dict(DW_PERSISTENT_RMP='maybe'))


def test_original_sources_domain_checkpoint_unchanged():
    proof = baseline_audit()
    assert proof['PASS'] and proof['retained_checkpoint_columns'] == 1158


def test_native_time_limit_guard():
    rows, batches = rmp_fixture_data()
    with pytest.raises(ValueError, match='<=30'): PersistentRMP(rows, batches[0], time_limit=31.)


@pytest.mark.parametrize('change', ['matrix', 'row_axis', 'variable_axis', 'validator', 'tolerance', 'physical'])
def test_authority_builder_detects_real_input_changes(change):
    validator, _ = pricing_fixture()
    b = validator.block
    matrix, rows, variables = b.A.copy(), b.d['row_names'].copy(), b.d['names'].copy()
    source, physical, tolerance = b'validator-v1', dict(pcs=1.), dict(affine=1e-6)
    def authority():
        from v42_dw_runtime.contracts import BASE_HEAD
        return make_authority(BASE_HEAD, [(matrix, b.d)], variables, rows, source, physical, tolerance)
    before = authority()
    if change == 'matrix': matrix.data[0] += 1e-12
    if change == 'row_axis': rows = rows[::-1].copy()
    if change == 'variable_axis': variables = variables[::-1].copy()
    if change == 'validator': source = b'validator-v2'
    if change == 'tolerance': tolerance = dict(affine=1e-5)
    if change == 'physical': physical = dict(pcs=2.)
    assert authority().key != before.key


def test_nonfinite_candidate_rejected_without_solver():
    validator, points = pricing_fixture()
    bad = list(points[1])
    bad[0] = float('nan')
    result = validate_candidate(Candidate(0, bad, 1, snapshot().dual_SHA), snapshot(), validator)
    assert not result.accepted and 'NONFINITE_TRAJECTORY' in result.reasons
