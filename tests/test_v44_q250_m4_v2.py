"""Small original builder/matrix and scope checks; no simulation/optimization."""
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from v44 import q250_m4_v2 as policy,barrier,serial_m2
from v44.common import atomic,digest,record,read


@pytest.fixture
def permit(tmp_path):
    value=barrier.validate()
    value.update(Q250_M4_overlay=policy.overlay(),Q250_M4_policy_sha=digest(policy.overlay()))
    path=tmp_path/'PERMIT.json';atomic(path,value);return path


def capture(stage,adapted):
    import v42_native.mess as native
    from v42_integrated.matrix import arrays
    battery=native.Battery(440.,1080.,760.,760.,300.,400.,.95,.95)
    routes=[native.RouteArc('AB','A','B',0,1,1,1.,'a'*64)]
    deadline=SimpleNamespace(stage=stage,check=lambda:None)
    snapshots=[]
    def take(model,*a,**k):
        model.update();snapshots.append(arrays(model));return None,{}
    def grid(model,p,q):
        return [('rho',0.),('reserve_shortfall',0.)]
    solve=policy.native_adapter(native.solve) if adapted else native.solve
    # Match the actual original build_case: patch the module only AFTER the
    # adapted solve has been created. The constructor must still capture.
    with patch.object(native,'optimize',take):
        result,_=solve(stage,deadline,('A','B'),{'MESS01':'A','MESS02':'B'},routes,battery,2,grid)
    assert result is None
    return snapshots[0],(('A','B'),{'MESS01':'A','MESS02':'B'},
        [('A',0,'A',1,None),('A',1,'A',2,None),('B',0,'B',1,None),('B',1,'B',2,None),('A',0,'B',1,routes[0])],battery,None)


@pytest.mark.parametrize('stage',['M1','M2'])
def test_original_full_domain_only_changes_q_bounds_and_connected_coefficients(stage):
    (A,d),graph=capture(stage,False);(B,e),_=capture(stage,True)
    for key in d:
        if key not in ('lower','upper'):assert np.array_equal(d[key],e[key]),key
    q=np.asarray([str(n).startswith('Q[') for n in d['names']])
    assert q.any() and np.all(d['lower'][q]==-400.) and np.all(d['upper'][q]==400.)
    assert np.all(e['lower'][q]==-250.) and np.all(e['upper'][q]==250.)
    assert np.array_equal(d['lower'][~q],e['lower'][~q])
    assert np.array_equal(d['upper'][~q],e['upper'][~q])
    delta=(A-B).tocoo()
    assert delta.nnz==2*q.sum()
    assert all(str(e['row_names'][i]) in ('connected_Qmax','connected_Qmin') for i in delta.row)
    assert all(str(e['names'][j]).startswith('arc[') for j in delta.col)
    assert np.all(np.abs(delta.data)==150.)
    # A historical +/-343 kvar witness is outside the new FULL variable box.
    j=np.flatnonzero(q)[0]
    assert e['upper'][j]<343. and e['lower'][j]>-343.
    assert graph[3].pcs_kva==400. and graph[3].p_limit==300.


def test_beam_vertices_intersect_q_cap_without_reducing_p_or_pcs():
    from v44.frozen.v43_mess.library import load
    load()
    (A,d),graph=capture('M1',True)
    points=policy.pcs_vertices(SimpleNamespace(original_A=A,original_d=d,graph=graph))
    assert np.max(np.abs(points[:,1]))<=250.+1e-10
    assert np.isclose(points[:,1].max(),250.) and np.isclose(points[:,1].min(),-250.)
    assert np.isclose(points[:,0].max(),300.) and np.isclose(points[:,0].min(),-300.)
    assert any(np.isclose(points[:,1],250.) & (np.abs(points[:,0])>1.))


@pytest.mark.parametrize('arm,stage',[('B2','M1'),('B3','M1'),('B3','M2')])
def test_m_four_thread_scope_restores_every_original_source(arm,stage):
    from v44.frozen.v43_mess.library import load
    import v42_native.mess as native
    from v42_may_campaign_native90 import budget,execution
    modules=load();engine=modules['m_engine'];k48=modules['table_v_k48'];c=modules['m_candidates']
    before=(engine.APPROVED_JOINT_PARAMETERS,k48.ORIGINAL_NATIVE_PARAMETERS,
        budget.DateBudget.native_optimize,execution.guard,native.solve,c.pcs_vertices,engine.export_plan)
    pins=[record(m.__file__) for m in (native,budget,execution,engine,k48,c,serial_m2)]
    request=dict(day='2025-05-02',arm=arm,stage=stage,Threads=4,worker_slot=1)
    with policy.m_threads(request) as params,policy.q_domain():
        assert params['Joint']['Threads']==params['K48']['Threads']==4
        assert params['Joint']['Method']==params['K48']['Method']==2
        assert params['Joint']['MIPGap']==.03
        assert native.solve is not before[4]
        assert c.pcs_vertices is policy.pcs_vertices
        assert [record(p['path']) for p in pins]==pins
    assert (engine.APPROVED_JOINT_PARAMETERS,k48.ORIGINAL_NATIVE_PARAMETERS,
        budget.DateBudget.native_optimize,execution.guard,native.solve,c.pcs_vertices,engine.export_plan)==before


def test_q_scope_restores_cache_authority_across_b3_m1_then_m2():
    from v44.frozen.v43_mess.library import load
    c=load()['m_candidates'];original=c.pcs_vertices
    with patch.object(c,'_v43_original_grid_context',lambda:None,create=True),\
         patch.object(c,'_v43_original_vertices',original,create=True):
        for _ in range(2):
            with policy.q_domain():assert c._v43_original_vertices is policy.pcs_vertices
            assert c._v43_original_vertices is original


def test_first_cache_install_does_not_leave_q_authority_in_a_scope(monkeypatch):
    from v44.frozen.v43_mess.library import load
    c=load()['m_candidates'];original=c.pcs_vertices
    monkeypatch.delattr(c,'_v43_original_grid_context',raising=False)
    monkeypatch.delattr(c,'_v43_original_vertices',raising=False)
    with policy.q_domain():
        # The same capture made by performance.install on its first M Case.
        monkeypatch.setattr(c,'_v43_original_grid_context',lambda:None,raising=False)
        monkeypatch.setattr(c,'_v43_original_vertices',c.pcs_vertices,raising=False)
        assert c._v43_original_vertices is policy.pcs_vertices
    assert c._v43_original_vertices is original
    with policy.q_domain():assert c._v43_original_vertices is policy.pcs_vertices
    assert c._v43_original_vertices is original


def test_case_sha_binds_changed_full_domain_and_policy(tmp_path,monkeypatch):
    from v44.frozen.v43_mess import library
    (A,d),graph=capture('M1',True)
    monkeypatch.setattr(library,'current_identity',lambda c:None)
    old=dict(original_matrix_sha='a'*64,original_domain_sha='b'*64)
    case=SimpleNamespace(original_d=d,graph=graph,identity=old,case_sha=digest(old),output=tmp_path)
    prior=case.case_sha;policy.bind_case(case,dict(Q250_M4_policy_sha='c'*64))
    assert case.case_sha!=prior and case.case_sha==digest(case.identity)
    assert case.identity['Q_operating_limit_kvar']==250.
    assert read(tmp_path/'Q250_FULL_DOMAIN_AUDIT.json')['Q_columns']>0
    d['upper'][np.flatnonzero(np.char.startswith(d['names'].astype(str),'Q['))[0]]=400.
    with pytest.raises(ValueError):policy.bind_case(case,dict(Q250_M4_policy_sha='c'*64))


@pytest.mark.parametrize('arm,stage',[('B1','A1'),('B3','A2'),('B0','ACTUAL'),('B2','ACTUAL')])
def test_non_m_scopes_keep_one_thread_and_original_native_builder(permit,arm,stage):
    import v42_native.mess as native
    from v44 import campaign
    original=native.solve
    case=dict(day='2025-05-02',arm=arm,worker_slot=1,case_root='D:/test_only')
    with policy.install(permit):
        assert campaign.stage_request(case,stage)['Threads']==1
        assert native.solve is original
        with pytest.raises(PermissionError):
            with policy.m_threads(dict(case,stage=stage,Threads=4)):pass


def test_stage_policy_and_tampered_q_limit_rejected(permit):
    from v44 import campaign
    case=dict(day='2025-05-02',arm='B3',worker_slot=1,case_root='D:/test_only')
    with policy.install(permit):
        assert campaign.stage_request(case,'M1')['Threads']==4
        assert campaign.stage_request(case,'M2')['Threads']==4
    value=read(permit);value['Q250_M4_overlay']['Q_operating_limit_kvar']=400.
    value['Q250_M4_policy_sha']=digest(value['Q250_M4_overlay']);atomic(permit,value)
    with pytest.raises(PermissionError):policy.validate(permit)


def test_plan_guard_rejects_bad_commands_without_clipping():
    plan={'Q_kvar':{'MESS01':[-250.,250.,0.]}}
    assert policy.check_plan(plan)['commands_clipped'] is False
    for bad in (343.,-343.,float('nan'),float('inf')):
        value={'Q_kvar':{'MESS01':[bad]}}
        with pytest.raises(ValueError):policy.check_plan(value)
        assert value['Q_kvar']['MESS01'][0] is bad


def test_no_old_m_checkpoint_and_single_worker_schedule(permit,monkeypatch):
    from v44 import worker
    from v44.config import B2_ORDER,MAIN_ORDER
    original=worker.m_stage
    monkeypatch.setattr(worker,'m_stage',lambda r,a:pytest.fail('old checkpoint reached native stage'))
    request=dict(day='2025-05-01',arm='B2',stage='M1',worker_slot=1,Threads=4,resume_parent='old')
    with policy.install(permit):
        with pytest.raises(PermissionError):worker.m_stage(request,{})
    states={};seen=[]
    while task:=serial_m2.assignments(states,[]):
        assert len(task)==1 and not serial_m2.assignments(states,task)
        row=task[0];key=(row['day'],row['arm']);seen.append(key);states[key]='COMPLETE'
    assert seen==list(B2_ORDER)+list(MAIN_ORDER)
