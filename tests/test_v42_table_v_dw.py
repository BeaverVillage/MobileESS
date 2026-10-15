"""Native0 regression: actual source phase/pricing, exact FULL aux projection."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import gzip
import json
from pathlib import Path
import pickle
from types import SimpleNamespace

import gurobipy as gp
import numpy as np
import pytest
import scipy.sparse as sp

from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.runtime_projection import finish_count
from v42_a_stage_domain_v2.stress_backend import snapshot_of
from v42_integration import table_v_dw as dw
from v42_integration.m_engine import file_record


@pytest.fixture(autouse=True)
def prohibit_all_native(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Regression must be Native0')
    for name in ('optimize','presolve','computeIIS'):monkeypatch.setattr(gp.Model,name,forbidden)


def tiny_runtime_model():
    model=gp.Model('TABLE_V_NATIVE0_RUNTIME_AUX');model.Params.OutputFlag=0
    rho=model.addVar(lb=0,ub=4,name='rho')
    y=model.addVars(2,lb=0,ub=2,vtype=gp.GRB.INTEGER,name='y')
    model.addConstr(y.sum()==2)
    count=finish_count(model,list(y.values()),2,'finish_count',direct=False)
    model.addConstr(rho>=.25*count)
    model.update()
    descriptor=dict(units=[dict(id='j'+str(i),class_key='c',optional=False,stay_count=False,
        v={'f0':{('A',0):('v',y[i].index)},'f1':{}}) for i in range(2)],
        known={},risk={})
    data=(None,None,None,None,None,None,None,{'classes':{'c':['j0','j1']}})
    return model,snapshot_of(model,[('rho',rho)]),descriptor,data,count


def test_original_runtime_equality_eliminated_exactly_without_native():
    model,base,descriptor,data,count=tiny_runtime_model()
    try:
        projected,translated,proof=dw.project_runtime_auxiliaries(model,base,
            {'Runtime_finish_counts':{('c','A',0):count}},descriptor,data)
        assert proof['PASS'] and proof['eliminated_auxiliaries']==1
        assert projected.matrix.shape==(2,3)
        assert np.array_equal(projected.matrix.toarray(),[[0,1,1],[1,-.25,-.25]])
        assert np.array_equal(projected.rhs,[2,0])
        assert projected.objective('rho').coefficients()=={0:Fraction(1)}
        assert translated['units'][0]['v']==descriptor['units'][0]['v']
    finally:model.dispose()


def test_constant_runtime_aux_stays_global_without_rounding_original_rhs():
    model=gp.Model('TABLE_V_NATIVE0_FIXED_RUNTIME_AUX');model.Params.OutputFlag=0
    try:
        rho=model.addVar(lb=0,ub=4,name='rho');y=model.addVar(vtype=gp.GRB.BINARY,name='y')
        model.addConstr(y==1)
        fixed=finish_count(model,[1.],1,'fixed_count',direct=False)
        varying=finish_count(model,[y],1,'varying_count',direct=False)
        model.addConstr(rho>=.15+.1*fixed+.2*varying);model.update()
        descriptor=dict(units=[dict(id='fixed',class_key='f',uid='f',optional=False,stay_count=False,
            v={'f0':{('A',0):('c',1.)},'f1':{}}),
            dict(id='j',class_key='c',uid='j',optional=False,stay_count=False,
            v={'f0':{('A',1):('v',y.index)},'f1':{}})],known={},risk={})
        data=(None,None,None,None,None,None,None,{'classes':{'f':['f'],'c':['j']}})
        base=snapshot_of(model,[('rho',rho)])
        projected,translated,proof=dw.project_runtime_auxiliaries(model,base,
            {'Runtime_finish_counts':{('f','A',0):fixed,('c','A',1):varying}},descriptor,data)
        assert proof['preserved_constant_Runtime_auxiliaries']==1 and proof['eliminated_auxiliaries']==1
        assert np.array_equal(projected.matrix.toarray(),[[0,0,1],[0,1,0],[1,-.1,-.2]])
        assert np.array_equal(projected.rhs,[1,1,.15])
        assert translated['units'][1]['v']['f0']['A',1]==('v',2)
        assert projected.matrix.shape==(3,3)
    finally:model.dispose()


def test_saved_runtime_capture_recovered_from_verified_original_tail_without_native():
    from v42_integration.table_v_dw_recovery import recover_runtime_bindings
    model=gp.Model('TABLE_V_NATIVE0_RUNTIME_RECOVERY');model.Params.OutputFlag=0
    try:
        rho=model.addVar(lb=0,ub=2);row=model.addConstr(rho>=0)
        y=model.addVar(vtype=gp.GRB.BINARY);model.addConstr(y==1)
        count=finish_count(model,[y],1,'finish_count',direct=False)
        model.chgCoeff(row,count,-.25);model.update()
        descriptor=dict(units=[dict(id='j',uid='j',class_key='c',optional=False,stay_count=False,
            v={'f0':{('A',0):('v',y.index)},'f1':{}})])
        data=(None,None,None,None,None,None,None,{'classes':{'c':['j']}})
        snapshot=snapshot_of(model,[('rho',rho)])
        bindings,representatives=recover_runtime_bindings(snapshot,descriptor,data)
        assert bindings['Runtime_finish_counts']=={('c','A',0):count.index}
        assert bindings['_runtime_equality_rows']==[2]
        assert representatives=={('c','A',0):'j'}
        rhs=snapshot.rhs.copy();rhs[-1]=1.
        with pytest.raises(ValueError,match='SORTED_EQUALITY_DRIFT'):
            recover_runtime_bindings(replace(snapshot,rhs=rhs),descriptor,data)
    finally:model.dispose()


def test_recovered_resource_axes_equal_original_native_binding_on_actual_tiny_builder(tmp_path,monkeypatch):
    from test_v42_a_stage_phase1 import block_fixture
    from v42_root import native
    from v42_pr134_sc.snapshot import capture
    from v42_a_stage_domain_v2.fast_backend import Backend
    from v42_integration.table_v_dw_recovery import recover_runtime_bindings,recover_coupling_rows
    data,graph,_=block_fixture(1)
    data=(*data[:5],{uid:graph for uid in data[1]},data[6],dict(data[7],domain_authority='CURRENT_D0_FIXTURE'))
    def grid(model,*args,**kwargs):
        rho=model.addVar(lb=0,ub=2,name='rho')
        return [('rho',rho),('reserve_shortfall',gp.LinExpr())],{'deviation':gp.LinExpr()},[]
    monkeypatch.setattr(native,'grid',grid)
    context=SimpleNamespace(folder=tmp_path,check=lambda:None,progress=lambda *args:None)
    model,units,levels,controls,bindings=native.build(context,data,'F2-CRA')
    try:
        snapshot=snapshot_of(model,[('rho',dict(levels)['rho'])])
        descriptor=capture(model,units,levels,controls,bindings,tmp_path/'descriptor.pkl.gz')
        runtime,representatives=recover_runtime_bindings(snapshot,descriptor,data)
        recovered=recover_coupling_rows(snapshot,descriptor,data,runtime,representatives)
        backend=Backend();backend.data=data
        assert recovered==backend._coupling_rows(model,bindings)
        assert len(runtime['Runtime_finish_counts'])==len(bindings['Runtime_finish_counts'])
        from v42_a_stage_phase1.producer import row_partition
        from v42_a_stage_phase1.backend import assemble_original
        from v42_a_stage_compact_rowgen.assembly import build
        from v42_may_build_v6.construction import ReferenceReuse,routed_compact_build
        projected,encoded,_=dw.project_runtime_auxiliaries(model,snapshot,bindings,descriptor,data)
        n=min(int(e[1]) for u in encoded['units'] for items in u['v'].values() for e in items.values() if e[0]=='v')
        rawaxes={(family.upper(),*key) if isinstance(key,tuple) else (family.upper(),'',key):row
            for (family,key),row in recovered.items()}
        # Runtime equalities were the final source rows, so retained resource
        # axes keep their original indices after this exact auxiliary removal.
        grows,_,_=row_partition(projected,encoded,n,rawaxes.values())
        reuse=ReferenceReuse(assemble_original)
        reference,_,G,_,_,axes=reuse(projected,grows,n,rawaxes,data)
        old=build(reference,G,n,axes,data,{}, {},[])
        fast=routed_compact_build(reuse)(reference,G,n,axes,data,{}, {},[])
        assert old['reference'].fingerprint()==fast['reference'].fingerprint()
        assert old['compact'].fingerprint()==fast['compact'].fingerprint()
        assert reuse.report()['exact_same_fresh_reference_hits']==1
    finally:model.dispose()


@pytest.mark.parametrize('corruption',('equality','bound'))
def test_runtime_projection_rejects_changed_original_equality_or_bound(corruption):
    model,base,descriptor,data,count=tiny_runtime_model()
    try:
        if corruption=='bound':
            upper=base.upper.copy();upper[count.index]=3;base=replace(base,upper=upper)
        else:
            matrix=base.matrix.copy().tolil();matrix[1,count.index]=2;base=replace(base,matrix=matrix.tocsr())
        with pytest.raises(ValueError,match='RUNTIME_'):
            dw.project_runtime_auxiliaries(model,base,{'Runtime_finish_counts':{('c','A',0):count}},descriptor,data)
    finally:model.dispose()


def snapshots():
    original=LinearSnapshot(sp.csr_matrix([[1.,-1.],[0.,1.]]),np.zeros(2),np.ones(2)*2,
        np.asarray(['>','=']),np.asarray([0.,1.]),np.asarray(['C','B']),
        (Objective('rho',((0,Fraction(1)),),0),))
    reference=replace(original,matrix=original.matrix[[1,0]],senses=original.senses[[1,0]],
        rhs=original.rhs[[1,0]],vtypes=np.asarray(['C','C']))
    descriptor={'units':[dict(id='j',v={'y':{('A',0):('v',1)}})]}
    return original,reference,descriptor


def test_full_math_equivalence_preserves_every_row_box_and_original_objective():
    original,reference,descriptor=snapshots()
    assert dw.verify_full_equivalence(original,descriptor,reference,descriptor,1)['PASS']
    rhs=reference.rhs.copy();rhs[0]=0
    with pytest.raises(ValueError,match='MATRIX_OBJECTIVE_DRIFT'):
        dw.verify_full_equivalence(original,descriptor,replace(reference,rhs=rhs),descriptor,1)


def test_real_source_phase_I_and_full_class_pricing_are_called_without_optimize(tmp_path,monkeypatch):
    original,_,_=snapshots();snapshot=replace(original,vtypes=np.asarray(['C','C']))
    local=LinearSnapshot(sp.csr_matrix([[1.]]),np.zeros(1),np.ones(1)*2,np.asarray(['=']),np.asarray([1.]),
        np.asarray(['C']),(Objective('local_price',(),0),))
    unit=dict(id='j',optional=False,stay_count=False,v={'y':{('A',0):('v',0)}})
    state=dict(compact=snapshot,reference=snapshot,n=1,grows=(0,),axes={('GPU','A',0):0},
        prior_compact=np.ones(2),metas={'c':dict(offset=1,width=1,kernel_columns=1,points=[],N=1,
            reference_columns=[1],reference_units=[unit],units=[unit])},
        data=None,domains=None,ledger=None,_table_v={'fixture':'ANALYTICAL_NATIVE0'})
    def prepared(context,case,built,output):
        output=Path(output);cache=output/'block.pkl.gz';graph=SimpleNamespace(sha='tiny_complete_graph')
        with gzip.open(cache,'xb') as stream:pickle.dump(dict(snapshot=local,B=sp.csr_matrix([[-1.]]),graph=graph),stream)
        roster=dict(class_id='c',full_physical_STAY=1,full_physical_migration=0,full_compact_blocks=0,
            complete_local_snapshot_sha256=local.fingerprint(),complete_graph_sha256=graph.sha,
            external_full_block_cache=file_record(cache))
        for filename,value in [('BLOCK_PRICING_ORACLE_VERIFICATION.json',{'records':[roster]}),
            ('SOURCE_DOMAIN_NATIVE0_AUDIT.json',{'PASS':True}),('ORIGINAL_FULL_DW_MATH_EQUIVALENCE.json',{'PASS':True})]:
            (output/filename).write_text(json.dumps(value),encoding='utf8')
        return state
    components=[]
    class AnalyticalNative:
        def __init__(self,*args):self.calls=[];self.native_seconds=0.
        def remaining(self):return 1.
        def solve(self,snap,folder,component):
            components.append(component);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
            if component=='PHASE_I':raw=dict(X=np.asarray([1.,1.,0.]),Pi=np.zeros(2),RC=np.asarray([0.,0.,1.]))
            elif component=='ORIGINAL_P1':raw=dict(X=np.ones(2),Pi=np.ones(2),RC=np.zeros(2))
            else:raw=dict(X=np.ones(1),Pi=np.ones(1),RC=np.zeros(1))
            self.calls.append(component)
            record=dict(status=2,native_seconds=0.,Work=0.,objective=0. if component=='PHASE_I' else 1.,snapshot_sha=snap.fingerprint())
            (folder/'NATIVE_RESULT.json').write_text(json.dumps(record),encoding='utf8')
            np.savez_compressed(folder/'RAW_ATTRIBUTES.npz',**raw)
            return record,raw
    monkeypatch.setattr(dw,'prepare_current_dw',prepared);monkeypatch.setattr(dw,'CurrentNative',AnalyticalNative)
    budget=SimpleNamespace(record_external=lambda *args,**kwargs:None)
    result=dw.execute_current_dw({},SimpleNamespace(case_sha='case',stage='A1'),[None]*6+[{'native_binding':{'matrix_sha':'same'}}],budget,tmp_path/'DW')
    assert result.get('error') is None,result
    assert components==['PHASE_I','ORIGINAL_P1','LOCAL_PRICING']
    assert result['phase_I_phi']==0. and result['LB_certified']
    assert result['Global_LB']==pytest.approx(1.) and result['Global_LB']<=1.
    assert result['full_domain_pricing_complete']
    assert result['Native_Runtime']==0. and result['P2_calls']==0
    from v42_integration.table_v_dw_reuse import replay_same_problem_dw
    replay=replay_same_problem_dw({},SimpleNamespace(case_sha='case'),
        [None]*6+[{'native_binding':{'matrix_sha':'same'}}],result,tmp_path/'REUSE')
    assert replay is not None
    assert replay['reused_pricing_certificate'] and replay['native_calls']==0
    assert replay['exact_Global_LB']==result['exact_Global_LB']
    assert components==['PHASE_I','ORIGINAL_P1','LOCAL_PRICING']
    # A saved PASS and same model SHA cannot conceal a corrupted dual.
    raw_path=tmp_path/'DW'/'P1'/'S0'/'RAW_ATTRIBUTES.npz'
    np.savez_compressed(raw_path,X=np.ones(2),Pi=np.zeros(2),RC=np.zeros(2))
    rejected=replay_same_problem_dw({},SimpleNamespace(case_sha='case'),
        [None]*6+[{'native_binding':{'matrix_sha':'same'}}],result,tmp_path/'REJECTED_REUSE')
    assert rejected is None
    assert components==['PHASE_I','ORIGINAL_P1','LOCAL_PRICING']


def test_missing_or_different_problem_lower_bound_does_not_create_gap():
    result=dict(FULL_feasible=True,objective=.8,case_sha='current',native_binding={'matrix_sha':'current'})
    for lower in (None,dict(LB_certified=True,full_domain_pricing_complete=True,Global_LB=.8,
            case_sha='old',native_binding={'matrix_sha':'old'})):
        attached=dw.attach_global_bounds(deepcopy(result),lower or {})
        assert attached['AIDC_Global_UB']==.8
        assert attached['AIDC_Global_LB'] is None and attached['AIDC_Global_Gap'] is None


def test_current_full_UB_and_certified_same_problem_DW_LB_define_gap():
    result=dict(FULL_feasible=True,objective=1.,case_sha='current',native_binding={'matrix_sha':'current'})
    lower=dict(LB_certified=True,full_domain_pricing_complete=True,Global_LB=.997,
        case_sha='current',native_binding={'matrix_sha':'current'})
    attached=dw.attach_global_bounds(result,lower)
    assert attached['AIDC_Global_Gap']==pytest.approx(.003)
    assert attached['AIDC_Global_Gap_percent']==pytest.approx(.3)
    assert attached['AIDC_Global_Gap_target']==.005


def test_zero_denominator_or_missing_UB_never_becomes_zero_global_gap():
    lower=dict(LB_certified=True,full_domain_pricing_complete=True,Global_LB=0.,case_sha='c',native_binding={})
    for feasible in (False,True):
        result=dw.attach_global_bounds(dict(FULL_feasible=feasible,objective=0.,case_sha='c',native_binding={}),lower)
        assert result['AIDC_Global_Gap'] is None
