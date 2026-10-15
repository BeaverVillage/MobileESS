"""Static audit safeguards without constructing or solving a native model."""
import numpy as np
import pytest
from scipy import sparse

from tools.audit_v42_isolated_frozen_tracks import literal_box_contradictions,phase_review,prohibit_native


def test_interrupted_barrier_timestamp_is_not_extra_wall_or_infeasibility_proof():
    log="Presolve time: 12.97s\nBarrier performed 19 iterations in 26.22 seconds\nTime limit reached\nRoot relaxation: time limit, 0 iterations, 9.83 seconds\nExplored 1 nodes"
    r=phase_review(log)
    assert r["Presolve_seconds"]==[12.97]
    assert r["Root_Barrier_completion_cumulative_Native_seconds"]==[26.22]
    assert r["interrupted_Root_relaxation_reported_seconds"]==[9.83]
    assert r["Root_relaxation_completed"] is False and r["time_limit_is_infeasibility_proof"] is False


def test_static_box_check_catches_literal_contradiction_but_never_certifies_feasibility():
    A=sparse.csr_matrix([[1.],[-1.],[1.],[0.]])
    r=literal_box_contradictions(A,np.array([0.]),np.array([1.]),np.array([2.,.1,1.,1.]),np.array([">",">","<","="]))
    assert r["box_only_contradiction_rows"]==[0,1,3]
    assert r["no_box_contradiction_is_not_feasibility_proof"] is True


def test_outward_ulp_enclosure_and_unbounded_rows_do_not_invent_contradictions():
    r=literal_box_contradictions(sparse.csr_matrix([[10.,0.],[0.,1.]]),np.array([.1,-1e100]),
        np.array([.1,1e100]),np.array([1.,0.]),np.array(["=","="]))
    assert r["box_only_contradiction_count"]==0 and r["nonfinite_enclosure_rows"]==1


def test_all_three_forbidden_native_entrypoints_are_restored_after_guard():
    import gurobipy as gp
    old={n:getattr(gp.Model,n) for n in ("optimize","presolve","computeIIS")}
    with prohibit_native() as attempts:
        for n in old:
            with pytest.raises(RuntimeError,match="NATIVE0_ONLY"):getattr(gp.Model,n)(None)
        assert len(attempts)==3
    assert all(getattr(gp.Model,n) is value for n,value in old.items())
