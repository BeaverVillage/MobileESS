import numpy as np
import pytest
from v42_certificate.common import selected_arc,restore,interval,incremental,choose_case,S2,START_UB,OBJ_TOL,exact_values,next_certificate_arm
from v42_certificate.runner import acceptance

@pytest.mark.parametrize('depart,connect,want',[(65,67,True),(65,66,False),(95,96,True),(96,97,False),(58,66,False),(58,70,True)])
def test_exact_crossing_domain(depart,connect,want):assert selected_arc(('A',depart,'B',connect,None),[66,95])==want
def test_nested_integrality_and_no_pruning():
    a=[('A',58,'B',60,None),('A',65,'B',67,None),('A',95,'A',96,None)]
    names=['arc[MESS01,0]','arc[MESS01,1]','arc[MESS01,2]','charge_mode[MESS01,65]','charge_mode[MESS01,66]','Q[MESS01,A,66]']
    kinds=['B']*5+['C'];sets={n:{i for i,(v,k) in enumerate(zip(names,kinds)) if restore(v,k,n,a)} for n in ['B1','B2','B3']}
    assert sets['B1']<sets['B2']<sets['B3'] and len(names)==6
@pytest.mark.parametrize('status',[2,9,11])
def test_timeout_or_optimal_label_does_not_prove_nonmaterial(status):
    c=interval(S2-1e-4,START_UB,status);assert not c['negative_certificate'] and c['conclusion']=='INCONCLUSIVE'
def test_feasible_upper_is_negative_even_if_interrupted():assert interval(S2-.0004,S2+.0009,11)['negative_certificate']
def test_tight_high_optimum_is_positive_not_negative():
    c=interval(S2+.005,S2+.0051,2);assert c['material'] and not c['negative_certificate']
def test_S2_is_not_partial_lower_floor():assert interval(S2-.0004,START_UB,9)['lower']<S2
def test_interval_increment_is_not_raw_bound_difference():
    a=dict(lower=.5,upper=.6);b=dict(lower=.55,upper=.65);assert incremental(a,b)==dict(lower=0.,upper=.15000000000000002,exact_optima_required=False,formula='max(0,L_stronger-U_weaker) <= opt_stronger-opt_weaker <= U_stronger-L_weaker')
@pytest.mark.parametrize('which',['log','first','solution','final'])
def test_real_acceptance_needs_log_initial_incumbent_and_saved_solution(which):
    args=['Loaded user MIP start with objective 0.591281',dict(objective=START_UB),1,START_UB]
    index={'log':0,'first':1,'solution':2,'final':3}[which];args[index]=['',dict(objective=.6696),0,.6696][index]
    assert not acceptance(*args)['PASS']
def test_exact_accepted_start():assert acceptance('Loaded user MIP start with objective 0.591281',dict(objective=START_UB),1,START_UB)['PASS']
def test_inconclusive_remedy_gate():
    c=interval(S2-.0004,START_UB,9);assert choose_case({a:c for a in ['B1','B2','B3']})=='CASE_E_INCONCLUSIVE'
def test_all_negative_search_quality_case():
    c=interval(S2-.0004,S2+.0005,9);assert choose_case({a:c for a in ['B1','B2','B3']}).startswith('CASE_D')
def test_route_positive_case():
    c=interval(S2+.002,START_UB,11);assert choose_case({a:c for a in ['B1','B2','B3']}).startswith('CASE_A')
def test_complete_mapping_uses_exact_axis_order_and_preserves_binary_values():
    assert np.array_equal(exact_values(['x','y'],dict(y=1.,x=0.,supplemental=8.)),[0.,1.])
@pytest.mark.parametrize('names,source',[(['x','x'],dict(x=1.)),(['x','y'],dict(x=1.)),(['x'],dict(x=np.nan))])
def test_bad_start_mapping_rejected(names,source):
    with pytest.raises(AssertionError):exact_values(names,source)
@pytest.mark.parametrize('upper',[S2+.0005,S2+.01])
def test_stronger_feasible_upper_certifies_weaker_only_if_close(upper):
    weaker=interval(S2-.0004,upper,9);stronger=interval(S2-.0003,upper,9)
    assert weaker['negative_certificate']==stronger['negative_certificate']==(upper-S2<=.001)
def test_stronger_material_lower_bound_does_not_certify_weaker():
    stronger=interval(S2+.002,S2+.01,11);weaker=interval(S2-.0004,S2+.01,9)
    assert stronger['material'] and not weaker['material']
def test_sequential_execution_starts_only_B3():assert next_certificate_arm({},set())=='B3'
@pytest.mark.parametrize('conclusion',['CERTIFIED_NONMATERIAL','INCONCLUSIVE'])
def test_B3_not_material_stops_all_weaker_solves(conclusion):assert next_certificate_arm({'B3':dict(material=False,conclusion=conclusion)},{'B3'}) is None
def test_B3_material_unlocks_only_B2():assert next_certificate_arm({'B3':dict(material=True)},{'B3'})=='B2'
def test_B2_nonmaterial_stops_B1():assert next_certificate_arm({'B3':dict(material=True),'B2':dict(material=False)},{'B3','B2'}) is None
def test_B2_material_unlocks_B1():assert next_certificate_arm({'B3':dict(material=True),'B2':dict(material=True)},{'B3','B2'})=='B1'
