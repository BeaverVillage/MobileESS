from fractions import Fraction
import numpy as np
import pytest
from test_v42_a_stage_phase1 import block_fixture,solve
from v42_a_stage_phase1.producer import native_block,price_snapshot
from v42_a_stage_phase1.oracle import corrected_certificate
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_domain_v2.domain import physical_domain
from v42_a_stage_early.candidate import point_for_option,physical_price
from v42_a_stage_residual.query import migration_query,select
from v42_a_stage_residual.recovery import migration_options
from v42_a_stage_residual.budget import Budget
from v42_a_stage_residual.native import BudgetStop
from v42_a_stage_residual.execution import authorize,guard

@pytest.mark.parametrize('N',(1,2,3))
def test_query_covers_every_original_physical_path_and_kind(N,tmp_path):
    data,graph,axes=block_fixture(N);job=data[1]['j0']
    domain=physical_domain(job,data[2]['j0'],data[3])
    snapshot,B,_,units=native_block(data,'c',graph,axes)
    cache=dict(snapshot=snapshot,B=B,units=units,graph=graph)
    queries={k:migration_query(cache,N,k) for k in ('STAY','MIGRATION')}
    count={'STAY':0,'MIGRATION':0}
    for option in domain:
        point=point_for_option(cache,job,data[3],option,N)
        kind='MIGRATION' if option.migrated else 'STAY'
        assert primal_replay(snapshot,point)['PASS']
        assert primal_replay(queries[kind],point)['PASS']
        assert not primal_replay(queries['STAY' if option.migrated else 'MIGRATION'],point)['PASS']
        count[kind]+=1
    assert min(count.values())>0
    for kind,query in queries.items():
        delta=query.matrix[:-1]-snapshot.matrix;delta.eliminate_zeros()
        assert delta.nnz==0 and np.array_equal(query.rhs[:-1],snapshot.rhs)
        pi=np.array([((j*17)%11-5)/8 for j in range(len(axes))])
        status,_,raw=solve(price_snapshot(query,B,pi),tmp_path,kind+str(N))
        assert status==2 and corrected_certificate(query,B,pi,raw['Pi'])['PASS']

@pytest.mark.parametrize('N',(1,3))
@pytest.mark.parametrize('potential',(Fraction(10000),Fraction(-10000),Fraction(0)))
def test_compact_recovery_exactly_matches_exhaustive_physical_pricing(N,potential):
    data,graph,axes=block_fixture(N);job=data[1]['j0'];domain=physical_domain(job,data[2]['j0'],data[3])
    indices={k:j for j,k in enumerate(axes)};pi=np.array([((j*17)%11-5)/8 for j in range(len(axes))])
    epsilon=Fraction(1,100000000);stats={}
    expected={repr(o):physical_price(o,job,data[4]['j0'],data[0],indices,pi,N,potential)[0] for o in domain if o.migrated}
    expected={k:v for k,v in expected.items() if v < -epsilon}
    actual={repr(o):v for o,v in migration_options(job,data[4]['j0'],data[0],domain,indices,pi,N,potential,set(),epsilon,Budget(),stats)}
    assert actual==expected and stats['full_physical_scan']
    if potential<0:assert stats['nonnegative_blocks_pruned']>0 and stats['paths_evaluated']==0

def candidates(kind,n,score):
    return [dict(kind=kind,class_id='c'+str(j),coefficient_sha256=kind+str(j),residual_score=score,price=Fraction(-1),identity=(kind,j)) for j in range(n)]

def test_stay_cannot_crowd_out_migration_and_no_fill_before_completion():
    pool=candidates('STAY',80,100)+candidates('MIGRATION',40,-100)
    with pytest.raises(PermissionError):select(pool,False)
    chosen=select(pool,True)
    assert len(chosen)==64 and sum(c['kind']=='MIGRATION' for c in chosen)==32

def test_fill_after_completed_migration_and_exact_duplicate_effect():
    pool=candidates('STAY',80,100)+candidates('MIGRATION',3,-100)
    # Use different class/effect identities across kinds in this fixture.
    for c in pool:
        if c['kind']=='MIGRATION':c['class_id']='mig'+c['class_id']
    chosen=select(pool+pool,True)
    assert len(chosen)==64 and sum(c['kind']=='MIGRATION' for c in chosen)==3
    assert chosen==select(list(reversed(pool)),True)

def test_single_cumulative_budget_and_authorized_scope():
    budget=Budget();budget.charge(1200)
    with pytest.raises(BudgetStop):budget.remaining()
    assert authorize('2025-05-19','FEASIBILITY_LP')=='2025-05-19'
    for day,action in [('2025-05-17','OPTIMIZE'),('2025-05-19','P1')]:
        with pytest.raises(PermissionError):authorize(day,action)
    with pytest.raises(PermissionError):guard(object(),'2025-05-19')
