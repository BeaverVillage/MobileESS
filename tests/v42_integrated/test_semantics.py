"""The 24 requested semantic gates plus negative numerical/callback controls."""
import ast,json
from pathlib import Path
import numpy as np
import pytest
import gurobipy as gp
from scipy import sparse
from v42_integrated import contract as c
from v42_integrated.governance import ROOT,OUT,NORMALAMPS,BASE,sha
from v42_native.voltage import Stage,voltage_for
from v42_thermal.authority import current_authority,denominators

@pytest.fixture(scope='module')
def thermal():return current_authority()

def test_01_zero_margin():assert c.MARGIN_PU==0
def test_02_planning_band():
    for s in (Stage.A1,Stage.M1,Stage.A2,Stage.M2):
        v=voltage_for(s);assert (v.lower_pu,v.upper_pu)==(.95,1.05)
        assert (v.lower_squared,v.upper_squared)==(.9025,1.1025)
def test_03_old_band_not_executable_M1_authority():
    tree=ast.parse((ROOT/'v42_native/voltage.py').read_text())
    assert not {0.955,1.045,.005}&{n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,(float,int))}
def test_04_current_normalamps(thermal):
    assert np.array_equal(denominators([r['branch_phase'] for r in thermal['rows']]),[r['NormalAmps'] for r in thermal['rows']])
def test_05_complete_44_120(thermal):
    assert len(thermal['rows'])==120 and len({r['transformer'] for r in thermal['rows']})==44
def test_06_kVA_independent_unchanged(thermal):
    original=json.loads((ROOT/'docs/v42_transformer_normalamps_contract/SOURCE_COMPILED_NORMALAMPS_AUTHORITY.json').read_text())
    assert original['rows']==thermal['rows']
    source=(ROOT/'v42_native/grid.py').read_text()
    assert "name='transformer_kVA'" in source and 'c.transformer_ratings[k]' in source
def test_07_line_ratings_unchanged(thermal):
    original=json.loads((ROOT/'docs/v42_transformer_normalamps_contract/SOURCE_COMPILED_NORMALAMPS_AUTHORITY.json').read_text())
    assert original['lines']==thermal['lines']
def test_08_CTPrim_not_current(thermal):assert all(r['CTPrim_used'] is False for r in thermal['rows'])
def test_09_authority_identical(thermal):
    assert thermal['Planning']==thermal['Actual'] and thermal['transformer_current_authority_sha256']==NORMALAMPS
    with c.physical_authority() as a:assert a['transformer_current_authority_sha256']==NORMALAMPS
def test_10_seven_RegControls(thermal):assert thermal['controls']['RegControl_count']==7
def test_11_four_fixed_on(thermal):
    caps=thermal['controls']['capacitors'];assert len(caps)==4
    assert all(all(int(s)==1 for s in r['states']) for r in caps)
def test_12_no_CapControls(thermal):assert thermal['controls']['CapControl_count']==0
def test_13_no_Actual_P_repair():assert c.ACTUAL['P_repair'] is False
def test_14_no_Actual_Q_repair():assert c.ACTUAL['Q_repair'] is False
def test_15_no_full_reoptimization():
    assert c.ACTUAL['full_reoptimization'] is False
    tree=ast.parse((ROOT/'v42_native/actual.py').read_text())
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in {'optimize','repair_p','repair_q'} for n in ast.walk(tree))
def test_16_P1_scalar_rho_only():
    from v42_two.contract import mess_groups
    groups=mess_groups([('rho',17),('reserve_shortfall',99),('movement_kwh',11),('movement_count',3),('tie',5)])
    assert groups[0].components==( ('rho',17), ) and c.P1=='MIN MAX_LINE_LOADING'
def test_17_P2_energy_then_count():
    from v42_two.contract import mess_groups
    groups=mess_groups([('rho',17),('reserve_shortfall',99),('movement_kwh',11),('movement_count',3),('tie',5)])
    assert groups[1].components==( ('movement_energy',11),('movement_count',3) )

@pytest.fixture(scope='module')
def mess_model():
    from v42_native.canary import fixture,mess_grid
    import v42_native.mess as m
    from v42_native.contracts import Deadline
    sites,H,b,r=fixture();models=[];original=m.optimize
    def capture(model,*args,**kwargs):model.update();models.append(model.copy());return None,{}
    m.optimize=capture
    try:m.solve('M1',Deadline('M1',20),sites,{'M':'A'},r,b,H,mess_grid)
    finally:m.optimize=original
    model=models[0]
    yield model
    model.dispose()
def test_18_route_decisions(mess_model):
    route=[v for v in mess_model.getVars() if v.VarName.startswith('arc[')]
    assert route and all(v.VType=='B' and v.LB==0 and v.UB==1 for v in route)
def test_19_P_Q_SOC_decisions(mess_model):
    for prefix in ('Pch[','Pdis[','Q[','SOC['):
        variables=[v for v in mess_model.getVars() if v.VarName.startswith(prefix)]
        assert variables and any(v.LB<v.UB for v in variables)
def test_20_A1_gate_precedes_M1_build(monkeypatch,tmp_path):
    import v42_integrated.build as build
    (tmp_path/'INTEGRATED_A1_FREEZE.json').write_text('{"PASS":false}')
    monkeypatch.setattr(build,'OUT',tmp_path)
    with pytest.raises(ValueError,match='A1_FREEZE_REQUIRED'):build.run()
def test_21_historical_certificate_cannot_populate_new():
    from v42_integrated.certificate import make
    identity=dict(NormalAmps_authority=NORMALAMPS,A1_freeze_sha256='a'*64)
    with pytest.raises(ValueError,match='NEW_MODEL_PROVENANCE'):make(identity,dict(UB=1,LB=.9,gap=.1,model_identity='PR131',old_certificate_used=True))
def test_22_exact_duplicates_only():
    from v42_integrated.matrix import duplicates
    A=sparse.csr_matrix([[1.,2.],[1.,2.],[2.,4.],[1.,np.nextafter(2.,3.)],[1.,2.]])
    assert duplicates(A,np.array([3.,3.,6.,3.,np.nextafter(3.,4.)]),np.array(['<']*5))[0][:2]==(1,0)
    assert len(duplicates(A,np.array([3.,3.,6.,3.,np.nextafter(3.,4.)]),np.array(['<']*5)))==1
def test_23_Runtime_CC4_no_refit():
    from v42_boundary.boundaries import load_native
    bundle,*_=load_native();assert bundle['RUNTIME_PROVIDER_READY']
    code='\n'.join(p.read_text() for p in (ROOT/'v42_integrated').glob('*.py'))
    tree=ast.parse(code)
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in {'fit','train','retrain'} for n in ast.walk(tree))
def test_24_no_future_leakage():
    import pandas as pd
    from v42_boundary.boundaries import load_native
    bundle,*_=load_native();issue=pd.Timestamp(bundle['issue_time'])
    assert all(r['known_at_issue'] and pd.Timestamp(r['submit_time'])<=issue and pd.Timestamp(r['issue_time'])==issue for r in bundle['known_population'])

def test_exact_root_events_and_checkpoint_no_inference():
    from v42_integrated.monitor import Monitor,root_gate
    monitor=Monitor();monitor.message('Root barrier log...',3)
    monitor.message('Barrier solved model in 70 iterations and 11.00 seconds',14)
    monitor.message('Root crossover log...',14.1)
    monitor.message('Root relaxation: objective 0.5, 71 iterations, 13.00 seconds',16)
    assert monitor.times['barrier_end']==14 and monitor.times['crossover_end'] is None
    assert monitor.times['root_processing_complete'] is None and root_gate(monitor.times)=='FAIL'
    monitor.times['first_nonroot_node']=590
    assert root_gate(monitor.times)=='PASS' and monitor.times['first_branch'] is None
    monitor.times['first_nonroot_node']=601
    assert root_gate(monitor.times)=='FAIL'

def test_new_all_phase_grid_binding(thermal):
    from v42_boundary.boundaries import load_native
    from v42_bootstrap.grid import coefficients
    from v42_native.grid import add_grid,GridAuthority
    bundle,*_=load_native();_,coeff=coefficients(bundle);coefficient=coeff[0]
    model=gp.Model();model.Params.OutputFlag=0;records=[]
    try:
        authority=GridAuthority(*(['b'*64]*4),.9025,1.1025,True,Stage.M1,NORMALAMPS)
        c.all_transformer_rows(add_grid,records)(model,[coefficient],[coefficient.anchor.tolist()],authority)
        model.update();rows=model.getConstrs()
        assert len(records)==120 and sum(r.ConstrName.startswith('NormalAmps[') for r in rows)==120
        assert sum(r.ConstrName=='transformer_kVA' for r in rows)==120*16
        assert sum(r.ConstrName=='voltage_lower' for r in rows)==len(coefficient.voltage_constant)
        assert all(r['authority_SHA']==NORMALAMPS for r in records)
    finally:model.dispose()

def test_canonical_sparse_grid_MPS_transport(tmp_path,thermal):
    from v42_boundary.boundaries import load_native
    from v42_bootstrap.grid import coefficients
    from v42_native.grid import GridAuthority
    from v42_m1_sparse.grid import add_compressed
    from v42_integrated.matrix import arrays,column_identity
    bundle,*_=load_native();_,coeff=coefficients(bundle);coefficient=coeff[0]
    model=gp.Model();model.Params.OutputFlag=0
    try:
        x=model.addVars(len(coefficient.control_names),lb=-10000,ub=10000)
        authority=GridAuthority(*(['b'*64]*4),.9025,1.1025,True,Stage.M1,NORMALAMPS)
        builder=lambda m,cs,controls,a:add_compressed(m,cs,controls,a,'M1-F3',[],[])
        rho=c.all_transformer_rows(builder)(model,[coefficient],[[x[i] for i in x]],authority)
        model.setObjective(rho);model.update()
        for i,row in enumerate(model.getConstrs()):row.ConstrName=f'R{i}'
        model.update();A,d=arrays(model)
        path=tmp_path/'canonical.mps';model.write(str(path));loaded=gp.read(str(path))
        try:
            B,e=arrays(loaded)
            assert column_identity(d)==column_identity(e)
            assert np.array_equal(A.indptr,B.indptr) and np.array_equal(A.indices,B.indices)
            assert np.array_equal(A.data,B.data)
            assert np.array_equal(d['rhs'],e['rhs'])
        finally:loaded.dispose()
    finally:model.dispose()

def test_historical_authority_import_hard_block():
    from v42_integrated.import_guard import SelectedOnly
    finder=SelectedOnly()
    for name in ('v42_forensic.common','v42_monolithic.formulation','v42_certificate.common','v42_benders.runner'):
        with pytest.raises(ImportError,match='SUPERSEDED_SCIENTIFIC_AUTHORITY_BLOCKED'):finder.find_spec(name)
    assert finder.find_spec('v42_native.mess') is None

def test_transport_only_seal_accepts_exact_git_blob_and_rejects_drift():
    from v42_integrated.supersession import assert_successor
    seal=json.loads((OUT/'AUTHORIZED_INTEGRATION_SUPERSESSION.json').read_text(encoding='utf8'))
    proof=json.loads((OUT/'CHECKOUT_BYTE_TRANSPORT_AUDIT.json').read_text(encoding='utf8'))['files'][0]
    row=next(r for r in seal['files'] if r['path']==proof['path'])
    assert assert_successor(row['path'],row['current_sha256'])
    assert assert_successor(row['path'],row['base_sha256'])
    with pytest.raises(AssertionError,match='UNSEALED_INTEGRATION_SUCCESSOR'):
        assert_successor(row['path'],'0'*64)
