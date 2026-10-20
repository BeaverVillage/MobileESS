"""Model receipts; only original voltage-row right-hand sides may differ."""
from pathlib import Path
import numpy as np
from v44.common import atomic,now,digest
from .voltage_policy import authority


def verify_state_policy(state,output,controller=None):
    atlas=state['atlas'];s=state['compact'];nodes=len(atlas['node_names'])
    if len(atlas['voltage_lower_rows'])!=96*nodes or len(atlas['voltage_upper_rows'])!=96*nodes:
        raise ValueError('R027_ALL_VOLTAGE_NODE_PHASE_SLOT_ROWS_REQUIRED')
    atomic(Path(output)/'A2_MODEL_VOLTAGE_POLICY.json',dict(UTC=now(),PASS=True,policy=authority(),policy_sha=digest(authority()),
        compact_fingerprint=s.fingerprint(),reference_fingerprint=state['reference'].fingerprint(),
        lower_rows=len(atlas['voltage_lower_rows']),upper_rows=len(atlas['voltage_upper_rows']),
        all_node_phase_slots_covered=True,PhaseI_P1_integer_share_same_snapshot=True,
        initial_state_built_fresh=True,old_A2_model_active_rows_dual_or_clock_imported=False,
        initial_voltage_band=[.95,1.05],conditional_execution=controller.report() if controller else None))


def compare(strict,relaxed,approved_rows):
    a=strict['compact'];b=relaxed['compact'];delta=a.matrix-b.matrix;delta.eliminate_zeros()
    assert a.matrix.shape==b.matrix.shape and delta.nnz==0
    for key in ('lower','upper','senses','vtypes'):
        assert np.array_equal(getattr(a,key),getattr(b,key)),key
    assert a.objectives==b.objectives
    changed=np.flatnonzero(a.rhs!=b.rhs)
    assert set(map(int,changed))==set(map(int,approved_rows))
    lower=np.intersect1d(changed,relaxed['atlas']['voltage_lower_rows']);upper=np.intersect1d(changed,relaxed['atlas']['voltage_upper_rows'])
    assert len(lower)+len(upper)==len(changed)
    assert np.allclose(b.rhs[lower]-a.rhs[lower],-.009475,atol=1e-11,rtol=0)
    assert np.allclose(b.rhs[upper]-a.rhs[upper],.010525,atol=1e-11,rtol=0)
    return dict(PASS=True,identical_matrix=True,identical_bounds_types_senses=True,identical_P1_objectives=True,
        changed_rhs_rows=len(changed),voltage_lower_rows=len(lower),voltage_upper_rows=len(upper),
        lower_rhs_delta_pu_squared=-.009475,upper_rhs_delta_pu_squared=.010525,
        only_A2_voltage_rhs_changed=True,strict_fingerprint=a.fingerprint(),relaxed_fingerprint=b.fingerprint())
