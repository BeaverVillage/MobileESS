import numpy as np
from types import SimpleNamespace
import pytest
from v42_threshold.common import T,S2,MATRIX_TOL,INTEGER_TOL,THRESHOLD_MARGIN,threshold_guard,classify,original_UB_eligible
from v42_threshold.routes import closest_path,path_validation

def test_exact_decimal_threshold():
    assert repr(T)=='0.5732125039436496' and abs(T-S2-.001)<1e-16

@pytest.mark.parametrize('rho,expected',[(T-.0001,True),(T-THRESHOLD_MARGIN,True),(T-THRESHOLD_MARGIN/2,False),(T,False),(T+1e-9,False),(float('nan'),False)])
def test_numerical_threshold_guard(rho,expected):
    assert threshold_guard(rho,rho,0.,0.,True,True)==expected

@pytest.mark.parametrize('matrix,integer,physics,grid',[(1e-4,0.,True,True),(0.,1e-5,True,True),(0.,0.,False,True),(0.,0.,True,False)])
def test_unsafe_feasibility_never_certified(matrix,integer,physics,grid):
    assert not threshold_guard(T-.01,T-.01,matrix,integer,physics,grid)

def test_recomputed_loading_above_epigraph_rejected():
    assert not threshold_guard(T-.01,T-.009,0.,0.,True,True)

@pytest.mark.parametrize('status',[2,9,11,12,4,13])
def test_no_validated_point_cannot_become_negative(status):
    assert classify(None,status)=='B3_INCONCLUSIVE'

def test_unrestricted_proven_infeasibility_positive():assert classify(None,3)=='B3_POSITIVE_CERTIFIED'
def test_fixed_route_infeasible_cannot_prove_B3():assert classify(None,3,exact_model=False)=='B3_INCONCLUSIVE'
def test_independently_validated_witness_negative_even_at_time_limit():assert classify({'threshold_certificate_PASS':True},9)=='B3_NEGATIVE_CERTIFIED'
def test_invalid_native_point_not_certificate():assert classify({'threshold_certificate_PASS':False},2)=='B3_INCONCLUSIVE'
def test_fractional_partial_point_cannot_be_original_UB():assert not original_UB_eligible({'B3_feasible_PASS':True},.2)
def test_integral_but_infeasible_point_cannot_be_original_UB():assert not original_UB_eligible({'B3_feasible_PASS':False},0.)

def test_root_nearest_route_uses_full_legal_graph():
    travel=SimpleNamespace(source='A',depart=0,destination='B',arrive=1,connect=1,energy_kwh=0.)
    graph=[('A',0,'A',1,None),('A',1,'A',2,None),('A',0,'B',1,travel),('B',1,'B',2,None)]
    route,score=closest_path(graph,'A',{0:.1,1:.1,2:.9,3:.9},2)
    assert route==[2,3] and abs(score-1.8)<1e-12 and path_validation(graph,'A',route,2)['PASS']

@pytest.mark.parametrize('route',[[0],[1,0],[0,0],[99]])
def test_broken_route_candidate_rejected(route):
    graph=[('A',0,'A',1,None),('A',1,'A',2,None)]
    assert not path_validation(graph,'A',route,2)['PASS']
