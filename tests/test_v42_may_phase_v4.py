from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import pytest
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from v42_a_stage_phase1.core import elastic_master, phase_objective
from v42_a_stage_early.progress import capture, inclusion_witness
from v42_may_phase_v4.phase import FrozenWeights, routed_group
from v42_may_phase_v4.a_stage import run


def snapshot(coefficient=2.):
    return LinearSnapshot(sp.csr_matrix([[coefficient], [1.]]),
        np.array([0.]), np.array([np.inf]), np.array(['=', '<']),
        np.array([1., 4.]), np.array(['C']), (Objective('rho', ((0, Fraction(1)),)),))


def test_activation_preserves_first_weights_and_original_snapshot():
    initial, expanded = snapshot(), snapshot(8.)
    frozen = FrozenWeights(initial, (0,))
    initial_hash, expanded_hash = initial.fingerprint(), expanded.fingerprint()
    old_master = elastic_master(initial, (0,))
    previous = capture(initial, {'units': []}, old_master, {'X': np.array([0., 1., 0.])})
    adaptive = elastic_master(expanded, (0,))
    with pytest.raises(ValueError, match='FROZEN_ARTIFICIAL_WEIGHT'):
        inclusion_witness(previous, expanded, {'units': []}, adaptive, 1)
    fixed = frozen.elastic_master(expanded, (0,))
    witness, mapped = inclusion_witness(previous, expanded, {'units': []}, fixed, 1)
    assert witness['PASS'] and phase_objective(fixed, mapped) == Fraction(1, 2)
    assert fixed.weights == old_master.weights and fixed.artificial_signs == old_master.artificial_signs
    assert initial.fingerprint() == initial_hash and expanded.fingerprint() == expanded_hash
    np.testing.assert_array_equal(previous['raw_X'], [0., 1., 0.])


def test_restricted_rows_keep_original_global_identity():
    frozen = FrozenWeights(snapshot(), (1,))
    subset = frozen.restricted(snapshot(64.), (1,))
    master = frozen.elastic_master(subset, (0,))
    assert master.weights == (Fraction(1, 4),)
    assert master.artificial_signs == (-1.,)


@pytest.mark.parametrize('attribute,value', [('rhs', 2.), ('senses', '>')])
def test_changed_global_authority_rejected(attribute, value):
    original = snapshot()
    frozen = FrozenWeights(original, (0,))
    changed = snapshot()
    getattr(changed, attribute)[0] = value
    with pytest.raises(ValueError, match='GLOBAL_ROW_IDENTITY_DRIFT'):
        frozen.elastic_master(changed, (0,))


def test_current_requests_cannot_activate_candidate():
    with pytest.raises(PermissionError, match='SEPARATELY_ADMITTED_PHASE_VERSION_REQUIRED'):
        run({}, None)


def test_auxiliaries_leave_original_matrix_bounds_types_and_objective_intact():
    original = snapshot(8.)
    frozen = FrozenWeights(snapshot(), (0,))
    candidate = frozen.elastic_master(original, iter((0,)))
    assert candidate.verify()
    assert candidate.original is original
    assert candidate.original.objective('rho').coefficients() == {0: Fraction(1)}
    assert (candidate.snapshot.matrix[:, :1] != original.matrix).nnz == 0
    for name in ('lower', 'upper', 'vtypes'):
        np.testing.assert_array_equal(getattr(candidate.snapshot, name)[:1], getattr(original, name))
    for name in ('rhs', 'senses'):
        np.testing.assert_array_equal(getattr(candidate.snapshot, name), getattr(original, name))


def _phase_stub(native, state, day, certified_zero_point=None):
    return elastic_master(state['expanded'], state['grows'])


def test_routing_keeps_legacy_globals_and_isolates_each_call():
    module = SimpleNamespace(run=_phase_stub, elastic_master=elastic_master)
    routed = routed_group(module, ('run',))
    state = dict(compact=snapshot(), expanded=snapshot(8.), grows=(0,))
    assert routed['run'](None, state, '2025-05-19').weights == (Fraction(1, 2),) * 2
    assert module.run(None, state, '2025-05-19').weights == (Fraction(1, 8),) * 2
    state['compact'] = snapshot(64.)
    assert routed['run'](None, state, '2025-05-20').weights == (Fraction(1, 64),) * 2
    assert module.elastic_master is elastic_master
