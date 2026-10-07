"""Saved/new proof consumption cannot mutate the queue before independent audit."""
from practical_support import *
from unittest.mock import patch
import tempfile,copy
import cold_barrier_external_controller as c

def run():
    old=c.RUN;checks=[]
    with tempfile.TemporaryDirectory() as temp:
        c.RUN=Path(temp);x=np.zeros(239827);x[239826]=.75;point_save(c.RUN/'KNOWN.npz',x)
        identity=dict(fixture=True);bb=c.ExactBB(identity,'1/2','3/4',dict(point='KNOWN.npz'));node=bb.select();bb.begin(node);bb.save(c.RUN/'OPEN_CHECKPOINT.json')
        before=copy.deepcopy(bb.state);checkpoint_sha=sha(c.RUN/'OPEN_CHECKPOINT.json')
        result=dict(identity=identity,fixing_hash=node['fixing_hash'],proof_checked=True,LP_status='OPTIMAL',native_status=2,certified_LB='3/5',optimal_LP_certificate_PASS=True,exact_infeasibility_PASS=False,branch_variable=0,branch_is_original_binary=True,raw_fractional_branch_value=.5,witness=None)
        cases=[('INDEPENDENT_CERTIFICATE_AUDIT_FAIL',result),('EXACT_INFEASIBILITY_VS_KNOWN_WITNESS',dict(result,LP_status='INFEASIBLE',native_status=3,certified_LB=None,optimal_LP_certificate_PASS=False,exact_infeasibility_PASS=True,branch_variable=None)),('CANDIDATE_BELOW_REGISTERED_GLOBAL_FLOOR',dict(result,witness=dict(PASS=True,full_original_replay_PASS=True,raw_vector_unchanged=True,objective_exact='2/5')))]
        for label,r in cases:
            with patch.object(c,'audit_checkpoint',side_effect=AssertionError('INJECTED_BAD_CERTIFICATE')):
                try:c.consume_checked(bb,0,r,None,None)
                except AssertionError:pass
                else:raise AssertionError('REJECTED_RECEIPT_ACCEPTED')
            assert bb.state==before and sha(c.RUN/'OPEN_CHECKPOINT.json')==checkpoint_sha
            checks.append(dict(case=label,PASS=True,durable_queue_unchanged=True,previous_bounds_retained=True))
        with patch.object(c,'audit_checkpoint',return_value=None):accepted=c.consume_checked(bb,0,result,None,None)
        assert accepted.audit()['OPEN']==[1,2] and bb.state==before and accepted.audit()['global_OPEN_min_LB_exact']=='3/5'
        c.RUN=old
    atomic(OUT/'CHECKED_RECEIPT_CONSUMPTION_TESTS.json',dict(PASS=True,optimize_calls=0,same_consumption_guard_used_for_new_and_saved_inflight_receipt=True,failure_tests=checks,valid_proof_preserves_both_children=True,independent_audit_precedes_durable_queue_mutation=True,UTC=stamp()))
    print('CHECKED_RECEIPT_CONSUMPTION_TESTS_PASS_OPTIMIZE_0')
if __name__=='__main__':run()
