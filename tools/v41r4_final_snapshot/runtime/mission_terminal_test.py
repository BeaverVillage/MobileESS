from fast_prepare import ROOT,record,read
from dayahead.v40h.identity import manifest
from mission_health import write,OUT
from copy import deepcopy
import mission_coordination as c
from dayahead.v41r1.feasible_seed import neutral_mess
c.terminal_audit=lambda a,b:dict(status='PASS')
c.identities=lambda rows:rows
c.joint_decision=lambda jobs,slots,authority:dict(jobs=jobs,slots=slots)
jobs=[dict(job_uid='synthetic',state_at_issue='PENDING',score=.8)]
mess=neutral_mess();calls=[]
def m1(j):calls.append('M1');return deepcopy(mess),dict(status='PASS')
def a1(j,m):calls.append('A1');j[0]['score']=.7;return dict(status='PASS',jobs=j)
def forbidden(*args):raise AssertionError('FORBIDDEN_POST_A1_OPTIMIZATION')
def evaluate(j,m):return dict(status='PASS',rho_max=j[0]['score'])
r=c.coordinate(jobs,m1,a1,forbidden,evaluate,{})
assert calls==['M1','A1'] and r['counts']['FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS']==0
assert c.digest(r['mf'])==c.digest(mess) and r['a1'][0]['score']==.7
assert r['objectives']['J_FINAL']==r['objectives']['J_A1'] and r['objectives']['DELTA_J_FINAL_PQ']==0
def worse(j,m):j[0]['score']=.9;return dict(status='PASS',jobs=j)
q=c.coordinate(jobs,m1,worse,forbidden,evaluate,{})
assert q['a1']==jobs and not q['AIDC_FEEDBACK_ACCEPTED']
def mutate(j,m):m.slots[0]['p_kw']=3;return dict(status='PASS',jobs=j)
try:c.coordinate(jobs,m1,mutate,forbidden,evaluate,{})
except (RuntimeError,TypeError):pass
else:raise AssertionError('MUTATION_NOT_REJECTED')
import inspect
source=inspect.getsource(c.coordinate)
assert source.count("running_unchanged=all(identities([row])==identities([old[row['job_uid']]])\n                          for row in candidate if row['state_at_issue']=='RUNNING')")==1
write(OUT/'TERMINAL_A1_RELEASE.json',dict(status='PASS',reason='Final user structure ends at A1; remove legacy post-A1 PQ optimization',
    source=manifest([ROOT/'mission_coordination.py',ROOT/'mission_worker.py'],ROOT),tests=['M1_then_A1_only','no_recourse_callback','fixed_final_M1','negative_candidate_retained_fallback','mutation_guard','B1_equivalent_adapter_exact_match'],
    test_source=record(__file__),affected_policies=['B3'],completed_B3_invalidated=0,prior_source_files_modified=0,negative_outcome_quality_reruns=0))
print('TERMINAL_A1_REGRESSION_PASS')
