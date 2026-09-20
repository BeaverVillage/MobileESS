"""Verify recovered source and exercise runtime boundaries without a solver."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
DOC=REPO/'docs/ieee123_per_mess'
EXPECTED_BUDGET_SHA='acd4009e12a104f42981fc8dfca900a3fd9cf05507df421c44e232ba168b2bb4'
EXPECTED_CONTRACT_SHA='f5967c1efd50f356b91b23ebc53542f75375e7fe53e629d2faeff86499edb2f9'


def verify():
    manifest=json.loads((DOC/'SOURCE_RECOVERY.json').read_text(encoding='utf-8'))
    actual={p.relative_to(HERE/'production').as_posix() for p in (HERE/'production').rglob('*') if p.is_file()}
    assert actual=={r['path'] for r in manifest['files']},'UNMANIFESTED_OR_MISSING_SOURCE'
    parsed=0
    for row in manifest['files']:
        path=HERE/'production'/row['path'];data=path.read_bytes()
        assert hashlib.sha256(data).hexdigest()==row['sha256'],row['path']
        assert len(data)==row['bytes'],row['path']
        if path.suffix=='.py':ast.parse(data.decode('utf-8'),filename=str(path));parsed+=1
    source=HERE/'production/v41r4/v41r4_per_mess_budget.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED_BUDGET_SHA
    spec=importlib.util.spec_from_file_location('recovered_budget',source)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.CONTRACT_SHA==EXPECTED_CONTRACT_SHA
    now=[0.0]
    b=m.DepthBudget('2025-05-08','B2',4,clock=lambda:now[0]);m.ACTIVE=b
    calls=[]
    class Future:
        def result(self):return 'completed'
    class Executor:
        def submit(self,fn,item):
            calls.append(item);now[0]+=20;return Future()
    now[0]=890
    # One already admitted atomic call may finish after 900; next is forbidden.
    try:list(m.budget_pool(Executor)().map(lambda x:x,[1,2]))
    except m.BudgetExpired:pass
    else:raise AssertionError('NEXT_CALL_WAS_NOT_BLOCKED')
    assert calls==[1] and b.elapsed==910
    assert b.snapshot()['soft_budget_overrun_seconds']==10
    now[0]=1200
    b2=m.DepthBudget('2025-05-09','B3',1,clock=lambda:now[0]);m.ACTIVE=b2
    assert b2.elapsed==0,'DEPTH_BUDGET_NOT_INDEPENDENT'
    now[0]=1300
    m.finish_depth([])
    assert b2.available(),'EARLY_COMPLETION_WAITED_FOR_FULL_BUDGET'
    now[0]=2100
    try:b2.check('NEXT_SOLVER_CALL')
    except m.BudgetExpired:pass
    else:raise AssertionError('EXACT_DEADLINE_NOT_ENFORCED')
    # Only transformer-polygon retention mismatches are recoverable here.
    # A true fatal validation exception must still escape observe().
    import sys,types
    fake=types.ModuleType('v41r4_exact_cache');fake.certified=lambda value:True
    dispatch={'candidate':types.SimpleNamespace(candidate_id='test'), 'objective':0.5}
    m.ACTIVE=m.DepthBudget('2025-05-08','B2',4,clock=lambda:0)
    m.ACTIVE.context={'route_table':None};m.ACTIVE.parent=types.SimpleNamespace(state_sha256='parent')
    with patch.dict(sys.modules,{'v41r4_exact_cache':fake}),patch.object(m,'dispatch_trajectory',return_value=None):
        with patch.object(m,'certified_child',side_effect=m.RestrictedPolygonRejection({'status':'PASS'},{'status':'FAIL'})):
            m.observe(({},dispatch,None,None,None))
        assert m.ACTIVE.retention_rejections==1 and not m.ACTIVE.pool
        with patch.object(m,'certified_child',side_effect=ValueError('PHYSICAL_FAIL')):
            try:m.observe(({},dispatch,None,None,None))
            except ValueError as error:assert str(error)=='PHYSICAL_FAIL'
            else:raise AssertionError('GENUINE_FAILURE_SWALLOWED')
    return dict(status='PASS',source_files=len(actual),python_files_parsed=parsed,
        historical_budget_sha_match=True,contract_sha=EXPECTED_CONTRACT_SHA,
        boundary_scenarios=['atomic_overrun','no_next_call','independent_depth',
            'early_completion','exact_deadline','reject_polygon_child','propagate_fatal'],
        production_execution=False,optimizer_calls=0,
        unavailable_validation=['original full production dependencies and datasets',
            'historical solver/integration and May05/May08 candidate replay reruns'])


if __name__=='__main__':
    result=verify()
    print(json.dumps(result,indent=2))
