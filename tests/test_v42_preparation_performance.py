"""Numerical equivalence of sparse interval assembly and proof reuse."""
from fractions import Fraction as Q
import numpy as np
import pytest
from v42_ultracompact.independent_interval import interval


def dense_reference(vectors, ts, reach, points, limit):
    # Previous independent verifier's exhaustive-coordinate arithmetic.
    U, _, N = reach.shape
    def enclose(x):
        y=float(x)
        return (y if Q(y)<=x else np.nextafter(y,-np.inf),
                y if Q(y)>=x else np.nextafter(y,np.inf))
    pl=np.zeros((len(vectors),U,N));ph=pl.copy();ql=pl.copy();qh=pl.copy();common=pl.copy()
    for k,v in enumerate(vectors):
        for u in range(U):
            for s in range(N):
                pd=v.get((3*u+1)*N+s,Q(0));qq=v.get((3*u+2)*N+s,Q(0));ch=v.get(3*u*N+s,Q(0))
                pl[k,u,s],ph[k,u,s]=enclose(pd);ql[k,u,s],qh[k,u,s]=enclose(qq)
                common[k,u,s]=enclose(max(Q(0),ch+pd)*limit)[1]
    values=np.zeros_like(pl)
    for x,y in points:
        xl,xh=enclose(x);yl,yh=enclose(y)
        p=np.nextafter(np.maximum.reduce([pl*xl,pl*xh,ph*xl,ph*xh]),np.inf)
        q=np.nextafter(np.maximum.reduce([ql*yl,ql*yh,qh*yl,qh*yh]),np.inf)
        values=np.maximum(values,np.nextafter(p+q,np.inf))
    values=np.nextafter(values+common,np.inf);result=np.zeros(len(vectors))
    for u in range(U):
        result=np.nextafter(result+np.max(np.where(reach[u,np.asarray(ts)],values[:,u,:],0),axis=1),np.inf)
    return result


@pytest.mark.parametrize('density',[0.,.05,.5,1.])
def test_sparse_interval_matches_exhaustive_binary64_program(density):
    rng=np.random.default_rng(701)
    U,N,H,K=4,5,6,31
    reach=rng.random((U,H,N))>.4
    points={(Q(3,7),Q(-2,3)),(Q(-11,3),Q(7,9)),(Q(0),Q(0))}
    vectors=[{j:Q(int(rng.integers(-100,100)),int(rng.integers(1,100)))
              for j in range(U*3*N) if rng.random()<density} for _ in range(K)]
    # Include exact charge/discharge cancellation and explicit zero entries.
    vectors[0]={0:Q(1,3),N:-Q(1,3),2*N:Q(0)}
    ts=rng.integers(0,H,size=K);limit=Q(300)
    for vs in (vectors,[{k:-v for k,v in row.items()} for row in vectors]):
        old=dense_reference(vs,ts,reach,points,limit)
        new=interval(vs,ts,reach,points,limit)
        assert np.array_equal(old.view(np.uint64),new.view(np.uint64))


def test_proof_reuse_keeps_current_rows_and_reports_substeps(monkeypatch):
    from v42_ultracompact import current
    from tests.test_v42_current_exact_c3a import fixture
    ultra,graph,_,_=fixture()
    calls=[];original=current.vertices
    def vertices(planes):
        calls.append(tuple(planes));return original(planes)
    monkeypatch.setattr(current,'vertices',vertices)
    events=[]
    candidate=current.reduce_current_c3a(ultra.original,ultra.original_data,graph,
                                       events.append,physical_original=(ultra.physical_original,ultra.physical_original_data))
    assert candidate.proof['PASS']
    assert len(calls)==len(set(calls))
    assert np.array_equal(candidate.row_ids,ultra.row_ids)
    assert candidate.bounds==ultra.bounds
    assert events[-1]['phase']=='M_CURRENT_EXACT_C3A_COMPLETE'
    assert any(e['phase']=='M_CURRENT_EXACT_C3A_VERIFY_BOUNDS' for e in events)
