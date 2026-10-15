"""Native0 regression for current-case LP cache and original-source routing."""
from dataclasses import replace
from types import SimpleNamespace
from fractions import Fraction
import copy

import numpy as np
import pytest
import scipy.sparse as sp

from v42_integration import table_v_compression as compression
from v42_integration import table_v_compression_adapter as adapter
from v42_integration.table_v_compression_verify import verify_sum,verify_redundancy
from test_v42_table_v_class_aggregation import fixture


def test_zero_column_fixed_uid_is_preserved_in_universal_projection():
    source,descriptor,data,semantic=fixture()
    jobs=dict(data[1],fixed=None);prep=dict(data[7],classes=dict(data[7]['classes'],fixed=['fixed']))
    data=(data[0],jobs,*data[2:7],prep)
    descriptor=dict(descriptor,units=descriptor['units']+[dict(uid='fixed',id='fixed',class_key='fixed',v=dict(y={('site',24):('c',1.)}))])
    semantic=dict(groups=dict(semantic['groups'],fixed=['fixed']))
    result=compression.compress_lp(source,descriptor,data,semantic)
    proof=verify_sum(source,result)
    assert proof['PASS'] and proof['UIDs']==3
    assert any(r['members']==['fixed'] and r['width']==0 for r in result['records'])


def test_named_zero_coupling_row_is_retained():
    source,_,_,_=fixture()
    source=replace(source,matrix=sp.vstack((source.matrix,sp.csr_matrix((1,3))),format='csr'),
        rhs=np.r_[source.rhs,1.],senses=np.concatenate((source.senses,['<'])))
    reduced,receipt=compression.redundant_rows(source,protected_rows=[3])
    assert 3 in receipt['retained_rows'] and 3 not in receipt['constant_tautologies']
    assert verify_redundancy(source,reduced,receipt)['PASS']


def test_scaled_descriptor_retains_sum_lane_and_uid_members():
    descriptor=dict(units=[dict(uid='a',id='a',class_key='old',optional=False,stay_count=False,
        v={'y':{('A',24):('v',1)},'f0':{('A',25):('e',1.,np.asarray([1]),np.asarray([-1.]))}})],known={},risk={})
    rows=[dict(class_id='math',members=['a','b','c'],cardinality=3)]
    target=adapter.compressed_descriptor(descriptor,rows,np.asarray([0,1]))['units'][0]
    assert target['members']==['a','b','c'] and target['summed_identical_continuous_lanes']==3
    assert target['v']['f0']['A',25][1]==3.
    assert target['v']['f0']['A',25][3][0]==-1.
    assert not target['optional'] and not target['stay_count']


def test_compression_refuses_different_source_case_before_any_model(tmp_path,monkeypatch):
    from v42_integration import table_v_dw as dw
    monkeypatch.setattr(dw,'audit_source_domain',lambda context:dict(PASS=True))
    context=dict(manifest=dict(identity={'case_sha':'new'}))
    captured=dict(case_sha='old',source_identity={'case_sha':'old'})
    with pytest.raises(ValueError,match='CURRENT_SOURCE_CASE'):
        adapter.prepare_exact_dw(context,SimpleNamespace(case_sha='new'),[None]*7,tmp_path,captured=captured)


def test_complete_kernel_rebuild_cannot_drop_or_change_a_graph():
    source,_,data,_=fixture()
    graphs={u:SimpleNamespace(sha=u) for u in data[1]}
    data=(*data[:5],graphs,data[6],data[7])
    state=dict(reference=source,grows=(0,),n=1,axes={},data=data)
    rebuild=adapter.complete_kernel_rebuilder(state)
    assert rebuild(source,(0,),1,{},data,{}, {},[])['reference'] is source
    modified=(*data[:5],dict(graphs,u0=SimpleNamespace(sha='drift')),data[6],data[7])
    with pytest.raises(ValueError,match='DOMAIN_OR_MATRIX_DRIFT'):
        rebuild(source,(0,),1,{},modified,{}, {},[])
