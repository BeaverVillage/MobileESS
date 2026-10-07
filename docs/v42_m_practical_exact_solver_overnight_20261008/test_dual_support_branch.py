from practical_support import *
from fractions import Fraction as F
import cold_barrier_external_controller as c
bb=c.ExactBB(dict(fixture=True),'1/2','1',dict(fixture=True));root=bb.select();bb.begin(root)
r=dict(identity=bb.state['identity'],fixing_hash=root['fixing_hash'],proof_checked=True,LP_status='OPTIMAL',certified_LB='1/2',optimal_LP_certificate_PASS=True,exact_infeasibility_PASS=False,branch_variable=0,branch_is_original_binary=True,raw_fractional_branch_value=.5,witness=None)
bb.apply(0,r);before=bb.audit()
d=dict(names=np.array(['charge_mode[0]','node_activity[0]','node_activity[1]']))
x=np.array([.4999,.16218,.25905]);support=np.array([1.846e-14,.00016744,.00015952]);chooser=c.chooser(bb,d)
assert chooser([0,1,2],x)==0 and chooser([0,1,2],x,np.zeros(3))==0
expected=chooser([0,1,2],x,support);assert expected in (1,2) and all(chooser([0,1,2],x,support)==expected for _ in range(10))
assert before==bb.audit() and bb.audit()['OPEN']==[1,2]
atomic(OUT/'DUAL_SUPPORT_BRANCH_TESTS.json',dict(PASS=True,optimize_calls=0,vanishing_support_charge_binary_not_prioritized_over_material_node_binary=True,zero_support_reverts_original_rank=True,deterministic_ranking=True,both_children_preserved=True,heuristic_score_never_prunes=True,UTC=stamp()))
print('DUAL_SUPPORT_BRANCH_TESTS_PASS_OPTIMIZE_0')
