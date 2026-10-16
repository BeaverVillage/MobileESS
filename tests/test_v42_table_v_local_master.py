from dataclasses import replace
from types import SimpleNamespace
from fractions import Fraction as F
import gzip,pickle,json
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_integration.table_v_local_master import reduce_state,lift_compact,map_matrix
from v42_integration.table_v_compression_adapter import source_lp_replay
from v42_integration.m_engine import file_record
from v42_integration.table_v_local_reduction import NonBinary64Projection


def state_fixture(folder):
    local=sp.csr_matrix([[1,-1,0,0],[0,0,1,0],[1,1,1,0],[2,2,0,0],[0,0,0,1]],dtype=float)
    global_matrix=sp.csr_matrix([[1,-1,-2,-3,0],[0,0,0,0,1]],dtype=float)
    A=sp.vstack((global_matrix,sp.hstack((sp.csr_matrix((5,1)),local),format='csr')),format='csr')
    source=LinearSnapshot(A,np.zeros(5),np.array([10,1,1,1,1.]),np.array(['=','<','=','=','<','<','>']),
        np.array([0,1,0,0,2,4,0.]),np.full(5,'C'),(Objective('rho',((0,F(1)),),F(0)),)).require()
    unit=dict(uid='u',id='u',members=['u'],class_key='C',optional=False,stay_count=False,
        v={'y':{j:('v',j) for j in range(4)}})
    snapshot=replace(source,matrix=local,lower=source.lower[1:],upper=source.upper[1:],senses=source.senses[2:],rhs=source.rhs[2:],vtypes=source.vtypes[1:],
        objectives=(Objective('local_price',(),F(0)),))
    block=dict(snapshot=snapshot,B=global_matrix[[0],1:].tocsr(),units=[unit],graph=SimpleNamespace(sha='graph'))
    path=folder/'old.pkl.gz'
    with gzip.open(path,'wb') as stream:pickle.dump(block,stream)
    roster=dict(records=[dict(class_id='C',cardinality=1,external_full_block_cache=file_record(path),complete_local_snapshot_sha256=snapshot.fingerprint(),
        complete_graph_sha256='graph',original_UIDs=['u'],full_physical_STAY=1,full_physical_migration=0,full_compact_blocks=0)])
    (folder/'BLOCK_PRICING_ORACLE_VERIFICATION.json').write_text(json.dumps(roster))
    units=[dict(unit,v={'y':{j:('v',j+1) for j in range(4)}})]
    descriptor=dict(units=units,known={},risk={})
    meta=dict(offset=1,width=4,kernel_columns=4,points=[],candidates=[],N=1,units=[unit],reference_units=[unit],reference_columns=[1,2,3,4])
    initial=np.array([1.5,.5,.5,0,.5])
    return dict(compact=source,reference=source,grows=(0,1),n=1,axes={('GPU','site',0):0},metas={'C':meta},prior_compact=initial,prior_original=initial,
        reference_descriptor=descriptor,scientific_descriptor=descriptor,projection_proofs=[],_table_v=dict(equivalent=dict(PASS=True)),
        _class_sum=dict(result=dict(fold=np.arange(5),scale=np.ones(5)),original_LP=source)),block


def test_whole_master_preserves_non_axis_coupling_and_original_uid_lift(tmp_path):
    state,_=state_fixture(tmp_path);old=state['compact'];new=reduce_state(state,tmp_path)
    assert new['compact'].matrix.shape==(2,3)
    assert np.array_equal(new['compact'].matrix[:2].toarray(),[[1,-3,0],[0,0,1]])
    assert np.array_equal(new['compact'].rhs[:2],old.rhs[:2]) and np.array_equal(new['compact'].senses[:2],old.senses[:2])
    assert new['axes']==state['axes'] and new['grows']==state['grows']
    assert np.array_equal(lift_compact(new,new['prior_compact']),state['prior_compact'])
    assert source_lp_replay(new,new['prior_compact'],tmp_path)['PASS']
    saved=json.loads((tmp_path/'BLOCK_PRICING_ORACLE_VERIFICATION.json').read_text())
    with gzip.open(saved['records'][0]['external_full_block_cache']['path'],'rb') as stream:cache=pickle.load(stream)
    assert cache['snapshot'].matrix.shape==(0,2) and np.array_equal(cache['B'].toarray(),[[-3,0]])
    assert old.fingerprint()==state['compact'].fingerprint()


def test_original_expanded_point_remains_identity_in_reduced_reference_coordinates(tmp_path):
    from v42_a_stage_compact_rowgen.lift import expanded_point
    state,_=state_fixture(tmp_path);new=reduce_state(state,tmp_path)
    assert np.array_equal(expanded_point(new,new['prior_compact']),new['prior_compact'])


def test_master_refuses_canonical_witness_outside_proved_alias_subspace(tmp_path):
    state,_=state_fixture(tmp_path);state['prior_compact']=state['prior_compact'].copy();state['prior_compact'][2]+=.01
    with pytest.raises(ValueError,match='WITNESS_NOT_EXACTLY'):reduce_state(state,tmp_path)


def test_sparse_global_projection_does_not_round_binary64_collision():
    with pytest.raises(NonBinary64Projection):map_matrix(sp.csr_matrix([[.1,.2]]),[0,0],1)
    assert map_matrix(sp.csr_matrix([[.5,.5,7.]]),[0,0,-1],1).toarray()[0,0]==1
    assert map_matrix(sp.csr_matrix((2,3)),[0,-1,1],2).shape==(2,2)


def test_actual_master_block_must_match_current_full_pricing_cache(tmp_path):
    state,_=state_fixture(tmp_path);matrix=state['compact'].matrix.copy();matrix.data[-1]=2
    state['compact']=replace(state['compact'],matrix=matrix);state['reference']=state['compact']
    with pytest.raises(ValueError,match='ACTUAL_MASTER_LOCAL_BLOCK'):reduce_state(state,tmp_path)
