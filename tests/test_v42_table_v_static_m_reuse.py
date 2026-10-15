"""A cache must not introduce an old incumbent or silently change its source."""
import gzip,json,pickle
from pathlib import Path
import numpy as np
import pytest
from v42_integration.m_static_reuse import load_verified_case
from v42_integration.m_engine import file_record
from v42_may_campaign_native90.m_model import CampaignMCase


def fixture(tmp_path,case):
    path=tmp_path/'CASE.pkl.gz'
    with gzip.open(path,'wb') as stream:pickle.dump(case,stream)
    source=tmp_path/'source.txt';source.write_text('source',encoding='utf8')
    report=dict(status='PASS',Native_calls=0,FULL_UB_certified=False,blocked_Native_attempts=[],
        seedless_iterations=[dict(pool_sha=str(i),charge_modes=384,MIP_Start_present=False) for i in (1,2)],
        K16=dict(PASS=True),verified_static_case_cache=file_record(path),current_source_records=[file_record(source)])
    p=tmp_path/'RESULT.json';p.write_text(json.dumps(report),encoding='utf8')
    return p,source,report


def empty_case():
    return CampaignMCase(None,{},None,{},None,None,'',{},None,None,{}, {},{},[],Path('.'))


def test_changed_dynamic_source_cannot_enter_production_cache(tmp_path):
    p,source,_=fixture(tmp_path,empty_case());source.write_text('different',encoding='utf8')
    with pytest.raises(ValueError,match='CURRENT_DYNAMIC_NATIVE0_SOURCE'):
        load_verified_case(file_record(p),None,None,None,tmp_path/'OUT')


def test_modified_pickle_is_rejected_before_loading(tmp_path):
    p,_,report=fixture(tmp_path,empty_case());Path(report['verified_static_case_cache']['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='CACHE_BYTES_DRIFT'):
        load_verified_case(file_record(p),None,None,None,tmp_path/'OUT')


@pytest.mark.parametrize('old_data',['point','pool'])
def test_old_point_or_pool_cannot_become_seedless_cache(tmp_path,old_data):
    case=empty_case()
    if old_data=='point':case.point=np.array([1.])
    else:case.mess_search_state=dict(reservoir={'old':'paths'})
    p,_,_=fixture(tmp_path,case)
    with pytest.raises(ValueError,match='UNSOLVED_CASE|NO_HEURISTIC_POOL'):
        load_verified_case(file_record(p),None,None,None,tmp_path/'OUT')
    assert not (tmp_path/'OUT').exists()
