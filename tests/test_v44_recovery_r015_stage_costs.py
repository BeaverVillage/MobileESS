import json
from types import SimpleNamespace
import pytest
from v44_recovery_r015.stage_costs import install
from v44 import worker
from v44.svr12 import SVR12CurrentAC

def pool():return SimpleNamespace(report=lambda:dict(record_lookups=1,bytes_hashed=3,mapped_record_seconds=.1,unknown_path_original_IO_calls=0))

@pytest.mark.parametrize('arm',['B0','B1','B2','B3'])
def test_original_stage_calls_once_and_fresh_nested_count_unchanged(monkeypatch,tmp_path,arm):
    called=[];result={'PASS':True}
    for name in ['reference','a_stage','m_stage']:
        def call(*args,_name=name,**kwargs):called.append(_name);return result
        monkeypatch.setattr(worker,name,call)
    def fresh(oracle,rows):called.append('fresh');return result
    monkeypatch.setattr(SVR12CurrentAC,'full_fresh_probe',fresh)
    def actual(request):
        called.append('actual');assert SVR12CurrentAC.full_fresh_probe(object(),[1]*120) is result;return result
    monkeypatch.setattr(worker,'actual',actual)
    case=dict(case_root=str(tmp_path),day='2025-05-01',arm=arm)
    with install(case,pool()):
        assert worker.reference('2025-05-01',tmp_path) is result
        for stage in ['A1','M1','A2','M2','ACTUAL']:
            function=worker.a_stage if stage.startswith('A') and stage!='ACTUAL' else worker.actual if stage=='ACTUAL' else worker.m_stage
            assert function(dict(stage=stage,output=str(tmp_path/stage))) is result
    assert called==['reference','a_stage','m_stage','a_stage','m_stage','actual','fresh']
    rows=[json.loads(line) for line in (tmp_path/'R015_STAGE_COST_PROFILE.jsonl').read_text(encoding='utf8').splitlines()]
    assert [r['stage'] for r in rows]==['REFERENCE','A1','M1','A2','M2','FRESH','ACTUAL']
    assert rows[-2]['slots']==120 and rows[-1]['includes_nested_independent_Fresh']

def test_original_exception_preserved_and_wrapper_restored(monkeypatch,tmp_path):
    error=ValueError('scientific failure')
    def actual(request):raise error
    monkeypatch.setattr(worker,'actual',actual)
    with pytest.raises(ValueError) as caught:
        with install(dict(case_root=str(tmp_path),day='2025-05-01',arm='B0'),pool()):worker.actual(dict(stage='ACTUAL'))
    assert caught.value is error and worker.actual is actual
