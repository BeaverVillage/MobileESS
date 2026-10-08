from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from test_v42_a_stage_phase1 import block_fixture,solve
from v42_a_stage_domain_v2.active import _graph
from v42_a_stage_domain_v2.domain import physical_domain
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_phase1.core import elastic_master,phase_objective,primal_replay
from v42_a_stage_early.candidate import point_for_option,exact_coupling,expanded_graph
from v42_job_capability import Option
from v42_a_stage_compact_rowgen.projection import fractional_wan_witness,separator,evaluate_separator,exact_replay
from v42_a_stage_compact_rowgen.rowgen import separate,restricted,TOLERANCE,certified_separate
from v42_a_stage_compact_rowgen.kernel import perspective,rational_lift,binary64

def fixture(N):
    data,_,axes=block_fixture(N);job=data[1]['j0'];domain=physical_domain(job,data[2]['j0'],data[3])
    stay=Option(4,'A',(('A',4,8),));old=_graph(job,((4,'A'),),(),domain,True)
    migration=next(o for o in domain if o.migrated and o.initial_site=='A')
    expanded=expanded_graph(old,migration,job,domain,True)
    old_snapshot,old_B,_,old_units=native_block(data,'c',old,axes,averaged=False)
    snap,B,_,units=native_block(data,'c',expanded,axes,averaged=False)
    cache=dict(snapshot=snap,B=B,units=units,graph=expanded)
    return data,axes,stay,migration,cache,old_B

@pytest.mark.parametrize('N',(1,2,3))
def test_expanded_fractional_WAN_is_outside_frozen_concrete_column_hull(N):
    data,axes,stay,migration,cache,old_B=fixture(N);job=data[1]['j0']
    points=[point_for_option(cache,job,data[3],o,N) for o in (stay,migration)]
    columns=[exact_coupling(cache['B'],p) for p in points]
    coefficients,proof=separator(columns,axes,data[3].bytes_per_gpu*job.gpu,old_B)
    x,replay=fractional_wan_witness(cache,job,data[3],stay,migration,N)
    value,coupling=evaluate_separator(coefficients,cache['B'],x)
    assert proof['PASS'] and replay['PASS'] and value<0
    assert sum(v for i,v in coupling.items() if axes[i][0]=='WAN')==0
    assert sum(v for i,v in coupling.items() if axes[i][0]=='ACTIVE')>0
    assert not exact_replay(cache['snapshot'],x+10)['PASS']

@pytest.mark.parametrize('N',(1,3))
def test_changed_feasible_set_changes_Phi_and_cannot_pass_equivalence_gate(N,tmp_path):
    data,axes,stay,migration,cache,old_B=fixture(N);job=data[1]['j0']
    endpoints=[point_for_option(cache,job,data[3],o,N) for o in (stay,migration)]
    W=np.asarray(cache['B'][[i for i,k in enumerate(axes) if k[0]=='WAN']].sum(axis=0)).ravel()
    A=np.asarray(cache['B'][[i for i,k in enumerate(axes) if k[0]=='ACTIVE']].sum(axis=0)).ravel()
    requirement=float(A@endpoints[1]/2)
    expanded=replace(cache['snapshot'],matrix=sp.vstack((sp.csr_matrix(np.array([W,A])),cache['snapshot'].matrix),format='csr'),
        senses=np.r_[np.array(['<','>']),cache['snapshot'].senses],rhs=np.r_[0.,requirement,cache['snapshot'].rhs])
    E=elastic_master(expanded,(0,1));status,_,raw=solve(E.snapshot,tmp_path,'expanded'+str(N))
    C=LinearSnapshot(sp.csr_matrix([[W@p for p in endpoints],[A@p for p in endpoints],[1.,1.]]),np.zeros(2),np.ones(2),
        np.array(['<','>','=']),np.array([0.,requirement,1.]),np.full(2,'C'),(Objective('rho',(),0),)).require()
    compact=elastic_master(C,(0,1));status2,_,raw2=solve(compact.snapshot,tmp_path,'compact'+str(N))
    assert status==status2==2 and phase_objective(E,raw['X'])==0
    assert phase_objective(compact,raw2['X'])>Fraction(1,100000000)
    assert primal_replay(expanded,raw['X'][:expanded.matrix.shape[1]])['PASS']

@pytest.mark.parametrize('N',(1,2,3))
def test_STAY_histogram_projection_forward_inverse_preserves_every_coupling(N):
    data,_,axes=block_fixture(N);job=data[1]['j0'];domain=physical_domain(job,data[2]['j0'],data[3])
    graph=_graph(job,((0,'A'),(4,'B')),(),domain,False)
    snap,B,_,units=native_block(data,'c',graph,axes,averaged=False)
    cache=dict(snapshot=snap,B=B,units=units,graph=graph)
    points=[point_for_option(cache,job,data[3],Option(s,k,((k,s,s+4),)),N) for s,k in ((0,'A'),(4,'B'))]
    for theta in (0.,.25,.5,1.):
        x=theta*points[0]+(1-theta)*points[1]
        assert exact_replay(snap,x)['PASS']
        coefficients=exact_coupling(B,x)
        first=exact_coupling(B,points[0]);second=exact_coupling(B,points[1])
        expected={i:Fraction(theta)*first.get(i,0)+Fraction(1-theta)*second.get(i,0) for i in set(first)|set(second)}
        assert coefficients=={i:v for i,v in expected.items() if v}
        # Native fixed-duration histogram y is the exact inverse lambda.
        for unit in units:
            if unit['stay_count'] or N==1:
                ys=[float(x[e[1]]) for e in unit['v']['y'].values() if e[0]=='v']
                assert sorted(ys)==sorted([N*theta,N*(1-theta)])

@pytest.mark.parametrize('capacities',((0.,0.),(.75,.25)))
def test_rowgen_closed_Phi_equals_full_row_monolithic_model(capacities,tmp_path):
    s=LinearSnapshot(sp.csr_matrix([[1.,1.],[1.,0.],[0.,1.]]),np.zeros(2),np.ones(2),np.array(['=','<','<']),
        np.array([1.,*capacities]),np.full(2,'C'),(Objective('rho',(),0),)).require()
    weights={1:Fraction(1),2:Fraction(1)};included={0,1};rounds=[]
    for iteration in range(3):
        rows=tuple(sorted(included));r=restricted(s,rows);g=tuple(j for j,i in enumerate(rows) if i in weights)
        master=elastic_master(r,g,weights_by_row={j:weights[i] for j,i in enumerate(rows) if i in weights})
        _,_,raw=solve(master.snapshot,tmp_path,'rowgen'+str(iteration)+str(capacities[0]))
        separation=separate(s,raw['X'][:2],included);rounds.append(separation)
        if separation['PASS']:break
        included.update(separation['violated_rows'])
    assert rounds[-1]['PASS'] and len(rounds)<=2
    full=elastic_master(s,(1,2),weights_by_row=weights)
    _,_,raw_full=solve(full.snapshot,tmp_path,'full'+str(capacities[0]))
    assert phase_objective(master,raw['X'])==phase_objective(full,raw_full['X'])
    if capacities[0]==0:assert rounds[0]['violated_rows']==[2] and len(rounds)==2

def test_separation_exact_threshold_and_no_permanent_row_deletion():
    s=LinearSnapshot(sp.csr_matrix([[1.],[1.],[-1.]]),np.zeros(1),np.ones(1),np.array(['<','<','<']),np.array([0.,0.,0.]),
        np.full(1,'C'),(Objective('rho',(),0),)).require()
    assert separate(s,np.array([float(TOLERANCE)/2]),{0})['PASS']
    result=separate(s,np.array([float(TOLERANCE)*2]),{0})
    assert result['violated_rows']==[1] and result['all_omitted_original_rows_evaluated']
    assert s.matrix.shape==(3,1)

@pytest.mark.parametrize('N',(1,2,3))
def test_exact_hybrid_preserves_fractional_direction_and_bidirectional_lift(N,tmp_path):
    data,axes,stay,migration,expanded_cache,old_B=fixture(N);job=data[1]['j0']
    graph=expanded_cache['graph'];snap,B,_,units=native_block(data,'c',graph,axes,averaged=True)
    cache=dict(snapshot=snap,B=B,units=units,graph=graph)
    points=[point_for_option(cache,job,data[3],o,N) for o in (stay,migration)]
    hybrid,C,metadata=perspective(snap,B,points,N);width=snap.matrix.shape[1]
    ghost,proof=fractional_wan_witness(cache,job,data[3],stay,migration,N)
    inverse=np.r_[ghost,float(N),0.,0.]
    assert proof['PASS'] and exact_replay(hybrid,inverse)['PASS']
    assert exact_coupling(B,ghost)==exact_coupling(C,inverse)
    forward=np.r_[points[0]/2,N/2,0.,N/2]
    assert exact_replay(hybrid,forward)['PASS']
    lifted=rational_lift(forward,points,N)
    assert lifted==[Fraction(float(x)) for x in (points[0]+points[1])/2]
    assert exact_coupling(C,forward)==exact_coupling(B,np.asarray(list(map(float,lifted))))
    # Feasibility/Phi obstruction of the pure-column model is retained exactly.
    W=np.asarray(B[[i for i,k in enumerate(axes) if k[0]=='WAN']].sum(axis=0)).ravel()
    A=np.asarray(B[[i for i,k in enumerate(axes) if k[0]=='ACTIVE']].sum(axis=0)).ravel()
    CW=np.asarray(C[[i for i,k in enumerate(axes) if k[0]=='WAN']].sum(axis=0)).ravel()
    CA=np.asarray(C[[i for i,k in enumerate(axes) if k[0]=='ACTIVE']].sum(axis=0)).ravel()
    requirement=float(A@points[1]/2)
    coupled=replace(hybrid,matrix=sp.vstack((sp.csr_matrix(np.array([CW,CA])),hybrid.matrix),format='csr'),
        senses=np.r_[np.array(['<','>']),hybrid.senses],rhs=np.r_[0.,requirement,hybrid.rhs])
    master=elastic_master(coupled,(0,1));status,_,raw=solve(master.snapshot,tmp_path,'hybrid'+str(N))
    assert status==2 and phase_objective(master,raw['X'])==0
    assert metadata['retains_all_native_fractional_directions']

def test_reject_rounded_nonbinary_reciprocal_and_accept_exact_count_scaling():
    with pytest.raises(ValueError,match='NONEXACT_BINARY64'):binary64(Fraction(1,72))
    assert binary64(Fraction(72)/72)==1.

@pytest.mark.parametrize('N',(1,2,3))
def test_sum_projection_independent_structural_proof_detects_coupling_corruption(N):
    from v42_a_stage_compact_rowgen.equivalence import verify
    data,axes,stay,migration,cache,_=fixture(N)
    snap,B,_,units=native_block(data,'c',cache['graph'],axes,averaged=True)
    assert verify(cache['snapshot'],cache['B'],cache['units'],snap,B,units,N)['PASS']
    damaged=B.copy();damaged.data[0]+=1
    with pytest.raises(ValueError,match='COUPLING_COEFFICIENT_LOSS'):verify(cache['snapshot'],cache['B'],cache['units'],snap,damaged,units,N)

@pytest.mark.parametrize('N',(1,3))
@pytest.mark.parametrize('family',('STAY','MIGRATION'))
def test_hybrid_nonzero_objective_optimum_equals_native(N,family,tmp_path):
    data,axes,stay,migration,cache,_=fixture(N)
    snap,B,_,units=native_block(data,'c',cache['graph'],axes,averaged=True)
    points=[point_for_option(dict(snapshot=snap,B=B,units=units,graph=cache['graph']),data[1]['j0'],data[3],o,N) for o in (stay,migration)]
    # A deterministic nonzero objective is an exact original coupling cost.
    costs=np.asarray(B[[i for i,k in enumerate(axes) if k[0]==('GPU' if family=='STAY' else 'ACTIVE')]].sum(axis=0)).ravel()
    snap=replace(snap,objectives=(Objective('coupling_cost',tuple((j,Fraction(float(v))) for j,v in enumerate(costs) if v),Fraction(7)),))
    hybrid,_,_=perspective(snap,B,points,N)
    status,value,_=solve(snap,tmp_path,'costnative'+family+str(N))
    status2,value2,_=solve(hybrid,tmp_path,'costhybrid'+family+str(N))
    assert status==status2==2 and value==value2

def test_outward_row_separator_matches_exact_thresholds():
    s=LinearSnapshot(sp.csr_matrix([[1e15,-1e15,1.],[0.,0.,1.],[1.,1.,1.]]),np.zeros(3),np.full(3,2.),
        np.array(['<','<','>']),np.array([0.,0.,1.]),np.full(3,'C'),(Objective('rho',(),0),)).require()
    for x in (np.array([1.,1.,2e-6]),np.array([1.,1.,5e-7]),np.array([0.,0.,5e-7])):
        assert certified_separate(s,x,set())['violated_rows']==separate(s,x,set())['violated_rows']
