import copy
from pathlib import Path
import pytest
from dayahead.v40b.common import REPO,ROOT,read,digest,sha
from dayahead.v40b.reuse import build_matrix,load_historical,validate_case_files
from dayahead.v40b.supervision import reject_duplicates,inventory

def test_sealed_method_and_date_adapter():
    f=read(ROOT/'V40B_V40A_METHOD_FREEZE.json')
    assert f['method_SHA']==digest(f['identity'])
    for p,s in f['identity']['V40A_source_files'].items():assert sha(REPO/p)==s
    assert f['identity']['May_date_adapter_source_SHA']==sha(REPO/'dayahead/v40b/may_adapter.py')
    assert f['identity']['full_route_search_passes']==1
    assert f['identity']['second_route_search']==0

def test_old_b3_rejected_before_any_io():
    with pytest.raises(ValueError,match='OLD_B3_REUSE_FORBIDDEN'):load_historical('2025-05-01','B3')

def test_matrix_never_reuses_b3_even_with_approved_certificate():
    certificates={'2025-05-01:B3':{'status':'PASS'},'2025-05-01:B0':{'status':'PASS'}}
    rows=build_matrix(certificates,{c:True for c in ('B0','B1','B2','B3')})
    assert len(rows)==124 and len({(r['day'],r['case']) for r in rows})==124
    assert all(r['status']=='RUN_REQUIRED' for r in rows if r['case']=='B3')
    assert rows[0]['status']=='REUSE_CERTIFIED'
    assert all(r['status']=='RUN_REQUIRED' for r in build_matrix(certificates,{}))

def test_duplicate_orchestrator_and_date_protection():
    with pytest.raises(RuntimeError):reject_duplicates({'orchestrators':[{'pid':2}],'workers':[]},1)
    with pytest.raises(RuntimeError):reject_duplicates({'orchestrators':[],'workers':[{'day':'2025-05-01'},{'day':'2025-05-01'}]},1)
    reject_duplicates({'orchestrators':[{'pid':1}],'workers':[{'day':'2025-05-01'}]},1)

@pytest.mark.parametrize('case',['B0','B1','B2'])
def test_real_current_loader_probe_and_schema(case):
    row=next(r for r in read(ROOT/'V40B_CURRENT_LOADER_PROBE.json')['rows'] if r['day']=='2025-05-01' and r['case']==case)
    assert row['accepted'] and not row['differences']
    validated=validate_case_files(row['day'],case,Path(row['checkpoint']),Path(row['result']['root']))
    assert validated['status']=='PASS'

def test_preserved_completed_results():
    from dayahead.v40b.common import OLD,audit
    baseline=read(ROOT/'V40B_PRELAUNCH_SNAPSHOT.json')
    assert audit(OLD,baseline['old_result_hashes'])['status']=='PASS'
