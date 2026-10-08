import pytest
from v42_may10_prestart_rescue.native import authorize_case
from v42_may10_prestart_rescue.bench import cutoff
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from fractions import Fraction
import numpy as np
import scipy.sparse as sp


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
