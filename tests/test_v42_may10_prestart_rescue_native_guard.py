import pytest
from v42_may10_prestart_rescue.native import authorize_case
from v42_may10_prestart_rescue.bench import cutoff
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from types import SimpleNamespace as NS
from v42_may10_prestart_rescue import execution as rescue
from v42_a_stage_domain_v2.execution import guard_model_optimize,require_action_authorized


def test_fixed_native_cases_reject_extra_changed_reordered_or_repeated_solve():
    case=dict(name='B1_COMPACT_MIP',snapshot_sha256='verified',seconds=480,relax=False,presolve=-1)
    plan=dict(cases=[case])
    assert authorize_case(plan,case['name'],'verified',480,False,-1,[])==case
    for args in (('OTHER','verified',480,False,-1,[]),
                 (case['name'],'changed',480,False,-1,[]),
                 (case['name'],'verified',480,False,1,[]),
                 (case['name'],'verified',481,False,-1,[]),
                 (case['name'],'verified',480,False,-1,[case])):
        with pytest.raises(PermissionError):authorize_case(plan,*args)


def test_cutoff_retains_original_query_and_adds_integer_objective_partition():
    s=LinearSnapshot(sp.csr_matrix([[2.,1.]]),np.zeros(2),np.full(2,100.),
        np.array(['<']),np.array([200.]),np.full(2,'I'),
        (Objective('prestart_relocation',((0,Fraction(1)),(1,Fraction(1)))),)).require()
    restricted=cutoff(s)
    assert np.array_equal(restricted.matrix.toarray(),[[2,1],[1,1]])
    assert list(restricted.senses)==['<','<'] and list(restricted.rhs)==[200,59]
    assert restricted.objectives==s.objectives


def test_native_scope_connects_backstop_but_other_models_days_and_production_stay_blocked(monkeypatch):
    monkeypatch.setattr('v42_may10_prestart_rescue.native.verify_sources',lambda:dict(PASS=True))
    monkeypatch.setattr(rescue,'read',lambda _:dict(PASS=True,cols=2,rows=1,nnz=2))
    m=NS(_v42_a_stage_day='2025-05-10',NumVars=2,NumConstrs=1,NumNZs=2,
        Params=NS(Threads=1,MemLimit=float('inf'),SoftMemLimit=float('inf')))
    with rescue.native_scope(m,'B0_SOURCE_LP',lambda:None):
        guard_model_optimize(m)
        assert require_action_authorized('2025-05-10')=='2025-05-10'
        with pytest.raises(PermissionError):guard_model_optimize(NS(_v42_a_stage_day='2025-05-10'))
        for action in ('P1','P2','PLANNING_FREEZE','ACTUAL','FRESH_AC'):
            with pytest.raises(PermissionError):require_action_authorized('2025-05-10',action)
        with pytest.raises(PermissionError):require_action_authorized('2025-05-12')
    with pytest.raises(PermissionError):guard_model_optimize(m)
