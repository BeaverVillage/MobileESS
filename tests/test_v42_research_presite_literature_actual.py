"""Small guard-order fixtures; real replay evidence is stored separately."""
from types import SimpleNamespace

import pytest

from v42_integration.research_presite_literature_actual import LiteratureReleasePolicy,run_literature_variant


@pytest.mark.parametrize('site,gpu,compatible,expected',[
    ('B',1,['A'],'SOURCE_SITE_INCOMPATIBLE'),
    ('B',9,['A','B'],'RACK_GANG_INCOMPATIBLE'),
    ('B',1,['A','B'],'CURRENT_GPU_CAPACITY')])
def test_data_and_QoS_are_not_evaluated_before_failed_GPU_rack_compatibility(site,gpu,compatible,expected):
    class ForbiddenProvider:
        def propose(self,*a,**kw):raise AssertionError('DATA_QOS_WAS_EVALUATED_OUT_OF_ORDER')
    p=object.__new__(LiteratureReleasePolicy)
    p._current_resource_ledger=SimpleNamespace(current_gpu_use=lambda *a,**kw:{'A':0,'B':8})
    p.packet=SimpleNamespace(rack_compatibility={'A':[8],'B':[8]},capacities={'A':8,'B':8})
    p.initial={'U':{'basic_site':'A'}};p.research=ForbiddenProvider()
    row=p._candidate(dict(uid='U',gpu=gpu,compatible_sites=compatible),site,0,changing=True)
    assert row['reason']==expected and row['data_QoS_AC']=='NOT_EVALUATED'
    assert row['research_data_contract'] is None and not row['feasible']


def test_proxy_contract_cannot_enter_literature_actual_runner(tmp_path):
    with pytest.raises(ValueError):
        run_literature_variant({},'C1',tmp_path/'must_not_exist',spec={'scenario':'R2'},proof_records=[],slots=16)
    assert not (tmp_path/'must_not_exist').exists()
