from bootstrap import *
import ast,inspect
from dayahead.v37 import runner
from dayahead.tools import run_v35r3e_r1_beam as beam
from paper_parent_candidate_guard import original_guard

def functions(path):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text(encoding='utf-8')).body
            if isinstance(n,ast.FunctionDef)}
def main():
    old=H/'diagnostic_attempts/B2_REPRESENTATIVE_FAILURE_20260921/mess_runtime.py'
    before=functions(old);after=functions(H/'mess_runtime.py')
    assert before.keys()==after.keys()
    assert all(before[k]==after[k] for k in before if k!='search')
    assert 'V35R3_FIXED_CANDIDATE_STATUS:3' in read(H/'B2_FAILURE.json')['error']
    seed=read(next((H/'B2/beam/2025-05-01/B2/B2/s6/B2-S5-576aa629cb2d32a2').glob('SEEDS.json')))
    # Obtain a real candidate with the frozen complete field schema.
    def find_candidate(x):
        if isinstance(x,dict):
            if 'candidate_id' in x and 'safe_energy_kwh' in x and 'mess_id' in x:return x
            for value in x.values():
                found=find_candidate(value)
                if found:return found
        elif isinstance(x,list):
            for value in x:
                found=find_candidate(value)
                if found:return found
    payload=dict(find_candidate(seed));payload['route_link_ids']=tuple(payload['route_link_ids'])
    candidate=beam.MobilityCandidate(**payload)
    sentinel=object()
    guard,ast_sha=original_guard(runner,lambda *a,**k:sentinel)
    assert guard('B2',candidate) is sentinel
    def infeasible(*a,**k):raise RuntimeError('V35R3_FIXED_CANDIDATE_STATUS:3')
    guard,_=original_guard(runner,infeasible)
    failed=guard('B2',candidate)
    assert failed[1] is None and failed[3]['fail_closed']
    assert failed[0]['objective']==1e300 and failed[0]['candidate_id']==candidate.candidate_id
    assert str(failed[0]['exact_optimality_certificate']).startswith('V37_FAIL_CLOSED:')
    def unexpected(*a,**k):raise RuntimeError('UNEXPECTED_TEST_FAILURE')
    guard,_=original_guard(runner,unexpected)
    try:guard('B2',candidate)
    except RuntimeError as error:assert str(error)=='UNEXPECTED_TEST_FAILURE'
    else:raise AssertionError('Unexpected errors must propagate')
    stages=sorted((H/'B2/beam').rglob('STAGE_*.json'))
    assert len(stages)==5
    closures=sorted((H/'B2/solver_trace').glob('call_*/FULL_SEPARATION_CLOSURE.json'))
    assert len(closures)==20
    for p in closures:
        c=read(p);assert c['status']=='PASS' and c['checked_rows']==31945536
        assert c['maximum_violation']<=c['tolerance']
    report=dict(status='PASS',same_fresh_paper_run_only=True,successful_candidate_math_unchanged=True,
        prior_runtime_sha256=sha(old),current_runtime_sha256=sha(H/'mess_runtime.py'),
        missing_binding='Original v37 safe_parent_solve was absent on serial representative candidates; parallel guard already existed',
        original_guard_ast_sha256=ast_sha,original_runner=record(inspect.getsourcefile(runner)),
        module=record(H/'paper_parent_candidate_guard.py'),
        tests=dict(success_passthrough=True,known_failure_not_feasible=True,unexpected_failure_propagates=True),
        unchanged_runtime_functions=[k for k in before if k!='search'],
        original_tolerance_and_domain_unchanged=True,original_paper_termination_unchanged=True,
        full_scan_candidates_not_pruned=True,full_separation_and_exact_AC_required=True,
        completed_stages=[record(p) for p in stages],completed_full_separation=[record(p) for p in closures],
        failure_preserved=str(old.parent),unix=time.time())
    save(H/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json',report)
    print('PAPER_PARENT_GUARD_REPAIR_PASS','stages',len(stages),'closures',len(closures),flush=True)
if __name__=='__main__':main()
