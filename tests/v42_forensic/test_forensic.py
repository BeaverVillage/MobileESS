import pytest
from v42_forensic.common import selected_arc,F3,UB
from v42_forensic.classification import classify

@pytest.mark.parametrize('arc,window,expected',[
    (('A',1,'B',4,object()),(2,3),True),
    (('A',0,'B',2,object()),(2,3),False),
    (('A',3,'B',5,object()),(2,3),True),
    (('A',4,'B',5,object()),(2,3),False),
    (('A',2,'A',3,None),(2,3),True),
    (('A',1,'A',2,None),(2,3),False)])
def test_window_arc_boundaries(arc,window,expected):assert selected_arc(arc,*window)==expected

def arms(gain=0,negative=False):return [dict(name=n,LB_gain=gain,negative_certificate=negative) for n in ['R_ROUTE_ONLY','R_ACTIVE','R_BUFFER']]

def test_stalled_partial_bounds_are_inconclusive():assert classify(arms(),UB)['ROOT_CAUSE_CLASS']=='CASE_E_INCONCLUSIVE'
def test_ub_improvement_with_uncertified_lb_negatives_stays_inconclusive():assert classify(arms(),UB-.006)['ROOT_CAUSE_CLASS']=='CASE_E_INCONCLUSIVE'
def test_negative_upper_certificate_and_improved_ub_are_ub_evidence():assert classify(arms(negative=True),UB-.006)['ROOT_CAUSE_CLASS']=='CASE_B_UB_DOMINATED'
def test_both_positive_tracks_are_mixed():assert classify(arms(.002),UB-.006)['ROOT_CAUSE_CLASS']=='CASE_C_MIXED'
def test_large_lb_gain_is_positive_without_negative_certificates():assert classify(arms(.02),UB)['ROOT_CAUSE_CLASS']=='CASE_A_LB_DOMINATED'
def test_two_certified_window_negatives_support_broader_coupling():assert classify(arms(negative=True),UB)['ROOT_CAUSE_CLASS']=='CASE_D_GLOBAL_BROADER_COUPLING'
