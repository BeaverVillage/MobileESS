from dataclasses import replace
import inspect
import numpy as np
import scipy.sparse as sp
import pytest
from v44_recovery_r023.sparse_couplings import CouplingParts,compile_reference,substitute


@pytest.mark.parametrize('widths',[(0,),(3,0,5),(4,2,9,1)])
def test_sparse_parts_preserve_exact_CSR_with_permuted_duplicate_axes(widths):
    rng=np.random.default_rng(451)
    prefix=sp.csr_matrix([[0.,-0.,3.],[2.,0.,0.],[0.,1.,0.],[1.,0.,0.],[0.,0.,0.],[0.,0.,2.]])
    positions=np.array([5,1,1,3],dtype=np.int64)
    parts=CouplingParts(prefix);expected=[prefix]
    for width in widths:
        rows=rng.integers(0,4,size=13) if width else np.array([],dtype=int)
        cols=rng.integers(0,width,size=13) if width else np.array([],dtype=int)
        values=rng.integers(-3,4,size=len(rows)).astype(float)
        block=sp.csr_matrix((values,(rows,cols)),shape=(4,width))
        coo=block.tocoo()
        expected.append(sp.csr_matrix((coo.data,(positions[coo.row],coo.col)),shape=(6,width)))
        parts.append(block,positions)
    actual=parts.matrix();reference=sp.hstack(expected,format='csr')
    assert actual.shape==reference.shape and actual.has_canonical_format
    for name in ('data','indices','indptr'):
        a=getattr(actual,name);b=getattr(reference,name)
        assert a.dtype==b.dtype and a.tobytes()==b.tobytes()


def test_no_class_is_exact_prefix_copy():
    prefix=sp.eye(3,format='csr');actual=CouplingParts(prefix).matrix()
    assert actual is not prefix and (actual!=prefix).nnz==0


def test_unknown_source_fails_closed():
    with pytest.raises(RuntimeError,match='SOURCE_DRIFT'):
        substitute('changed','missing','new','fixture')


def test_reference_maps_noncontiguous_global_rows_before_combining(monkeypatch):
    from v42_a_stage_phase1 import backend
    from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
    from fractions import Fraction
    objectives=tuple(Objective(k,(),Fraction(0)) for k in ('rho','migration_count','shift_magnitude','prestart_relocation'))
    base=LinearSnapshot(sp.csr_matrix(np.arange(18.).reshape(9,2)),np.zeros(2),np.ones(2),np.full(9,'<'),np.ones(9),np.full(2,'C'),objectives)
    local=LinearSnapshot(sp.csr_matrix([[1.,2.]]),np.zeros(2),np.ones(2),np.array(['=']),np.array([1.]),np.full(2,'C'),objectives)
    B=sp.csr_matrix([[3.,0.],[0.,7.]])
    stub=lambda *a,**k:(local,B,{},[])
    data=({}, {}, {}, {}, {}, {'u':None,'v':None},None,{'classes':{'a':['u'],'b':['v']}})
    monkeypatch.setattr(backend,'native_block',stub)
    args=(base,(8,2,6),2,{'second':6,'first':8},data)
    expected=backend.assemble_original(*args)
    actual=compile_reference(backend.assemble_original,stub)(*args)
    assert actual[0].fingerprint()==expected[0].fingerprint()
    assert actual[1:]==expected[1:]


def test_next_day_scope_protects_even_explicit_fresh_May02(tmp_path,monkeypatch):
    from v44 import worker
    from v44_recovery_r023 import phase_rebuild
    monkeypatch.setattr(phase_rebuild,'stage_scope',lambda request:pytest.fail('current date touched'))
    monkeypatch.setattr(worker,'a_stage',lambda request:True)
    with phase_rebuild.install():
        assert worker.a_stage(dict(day='2025-05-02',arm='B3',stage='A2',fresh_a2_parent='parent'))
