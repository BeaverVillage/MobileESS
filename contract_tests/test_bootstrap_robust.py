import copy
from types import SimpleNamespace
import numpy as np
import pytest
from v42_native.voltage import Stage,voltage_for,authority_sha,require_planning
from v42_native.grid import GridAuthority

@pytest.mark.parametrize('stage',list(Stage))
def test_explicit_stage_bands(stage):
    v=voltage_for(stage)
    expected=(.95,1.05) if stage in (Stage.A1,Stage.ACTUAL) else (.955,1.045)
    assert (v.lower_pu,v.upper_pu)==expected
    assert v.lower_squared==pytest.approx(v.lower_pu**2,abs=1e-15)
    assert v.upper_squared==pytest.approx(v.upper_pu**2,abs=1e-15)
    if stage!=Stage.ACTUAL:
        assert GridAuthority(*['a'*64]*4,v.lower_squared,v.upper_squared,True,stage=stage).validate() is None

@pytest.mark.parametrize('bad',[None,'A1','M1','A2','Actual','bootstrap',1])
def test_stage_not_inferred_from_strings(bad):
    with pytest.raises(ValueError,match='VOLTAGE_STAGE_REQUIRED'):voltage_for(bad)

def test_missing_and_wrong_stage_band_fail():
    with pytest.raises(ValueError):GridAuthority(*['a'*64]*4,.9025,1.1025,True).validate()
    for s in (Stage.M1,Stage.A2,Stage.M2):
        with pytest.raises(ValueError):require_planning(.9025,1.1025,s)
    with pytest.raises(ValueError):require_planning(.912025,1.092025,Stage.A1)
    with pytest.raises(ValueError):require_planning(.9025,1.1025,Stage.ACTUAL)

def test_new_handoff_requires_bootstrap_stage_and_digest():
    from v42_bootstrap.handoff import validate_handoff
    from v42_native.contracts import digest
    a=dict(voltage_authority_sha256=authority_sha(Stage.A1),controls=[[2,0,0]])
    h=dict(accepted=True,known_jobs=1499,physical_PASS=True,unknown_individual_jobs_fabricated=False,anchor_digest=digest(a))
    assert validate_handoff(h,a)
    b=dict(a,voltage_authority_sha256=authority_sha(Stage.A2));h['anchor_digest']=digest(b)
    with pytest.raises(ValueError,match='A1_ANCHOR_VOLTAGE_DRIFT'):validate_handoff(h,b)

def test_voltage_necessary_condition_uses_full_mess_pq_bounds():
    from v42_bootstrap.preflight import voltage_intervals
    c=SimpleNamespace(control_names=['aidc_load_kw[S]','mess_p_kw[S]','mess_q_kvar[S]'],voltage_constant=np.array([1.101]),voltage_matrix=np.array([[0.],[.001],[.001]]))
    a=dict(controls=[[1,0,0]]*96);b=SimpleNamespace(p_limit=100,pcs_kva=120)
    result=voltage_intervals([c]*96,a,['S'],{'U':'S'},[],b)
    assert result['PASS'] and 'necessary, not sufficient' in result['bound_semantics']
    c.voltage_matrix[:]=0
    failed=voltage_intervals([c]*96,a,['S'],{'U':'S'},[],b)
    assert not failed['PASS'] and failed['impossible_count']==96
    assert failed['strongest_contradiction']['required_upper_change_pu']>0

@pytest.mark.parametrize('stage,source_stage',[(Stage.M1,Stage.A1),(Stage.M2,Stage.A2)])
def test_future_m2_and_m1_grid_require_correct_fixed_anchor(monkeypatch,tmp_path,stage,source_stage):
    import gurobipy as gp
    import v42_bootstrap.grid as grid
    from v42_native.contracts import digest
    master=tmp_path/'master.dss';master.write_text('frozen')
    names=['aidc_load_kw[S]','mess_p_kw[S]','mess_q_kvar[S]']
    coeff=[SimpleNamespace(slot=t,control_names=names,coefficient_sha256='a'*64,
                           voltage_constant=np.array([1.]),voltage_matrix=np.array([[-.001],[.001],[.001]]),
                           branch_names=[],branch_limits=[],transformer_ratings=[],anchor=np.zeros(3),
                           flow_p_constant=np.zeros(0),flow_q_constant=np.zeros(0),flow_p_matrix=np.zeros((0,3)),
                           flow_q_matrix=np.zeros((0,3)),current_matrix=np.zeros((3,0)),current_constant=np.zeros(0)) for t in range(96)]
    cert=dict(input_identity=dict(identity=dict(inputs=dict(OpenDSS_master=dict(path=str(master))))))
    monkeypatch.setattr(grid,'coefficients',lambda b:(cert,coeff))
    anchor=dict(voltage_authority_sha256=authority_sha(source_stage),control_names=names,controls=[[1.,0.,0.]]*96)
    before=digest(anchor)
    with gp.Model() as model:
        model.Params.OutputFlag=0
        p={('S',t):model.addVar(lb=-2,ub=2,name=f'P[{t}]') for t in range(96)}
        q={('S',t):model.addVar(lb=-2,ub=2,name=f'Q[{t}]') for t in range(96)}
        levels,ctrl=grid.frozen_grid(model,dict(capacities={'S':80},battery={}),anchor,p,q,stage=stage)
        model.update()
        assert all(row[0]==1. for row in ctrl) and digest(anchor)==before
        assert model.NumVars==193 and model.NumConstrs==192
        assert all(not v.VarName.startswith(('known','anonymous','CC4','AIDC')) for v in model.getVars())
        wrong=dict(anchor,voltage_authority_sha256=authority_sha(Stage.M1))
        with pytest.raises(ValueError,match='MESS_AIDC_ANCHOR_STAGE_DRIFT'):
            grid.frozen_grid(model,dict(capacities={'S':80},battery={}),wrong,p,q,stage=stage)

def test_independent_charge_mode_and_connection_checks():
    from v42_bootstrap.attribution import supplemental_physical
    v={}
    for t in range(96):
        v[f'charge_mode[U,{t}]']=0.
        for prefix in ('Pch','Pdis','Q'):v[f'{prefix}[U,S,{t}]']=0.
    best=dict(values=v,initial_sites={'U':'S'},chosen_arcs={'U':list(range(96))})
    b=SimpleNamespace(p_limit=10)
    assert supplemental_physical(best,['S'],b)['charge_mode_and_connection_PASS']
    v['Pch[U,S,0]']=1.
    assert not supplemental_physical(best,['S'],b)['charge_mode_and_connection_PASS']
    v['charge_mode[U,0]']=1.
    assert supplemental_physical(best,['S'],b)['charge_mode_and_connection_PASS']
    best['chosen_arcs']['U'].remove(0)
    assert not supplemental_physical(best,['S'],b)['charge_mode_and_connection_PASS']

def test_handoff_exports_saved_linexpr_and_numpy_state_without_optimize(monkeypatch,tmp_path):
    import csv
    import gurobipy as gp
    import v42_bootstrap.handoff as export
    from v42_root.common import atomic,read
    monkeypatch.setattr(export,'OUT',tmp_path)
    monkeypatch.setattr(export,'dump',lambda name,obj:atomic(tmp_path/name,obj))
    def write_table(name,rows):
        with (tmp_path/name).open('w',encoding='utf8',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    monkeypatch.setattr(export,'table',write_table)
    names=['aidc_load_kw[S]','mess_p_kw[S]','mess_q_kvar[S]']
    monkeypatch.setattr(export,'coefficients',lambda bundle:({},[SimpleNamespace(control_names=names)]))
    jobs={str(i):SimpleNamespace(state='known',reference_start=24,reference_site='S',gpu=1) for i in range(1499)}
    selected={uid:dict(start=24,initial_site='S',segments=[['S',24,25]],checkpoint=-1,physical_checkpoint_seconds=0,
                      destination='S',transfer_start=-1,transfer_end=-1,restart_end=-1,wan=[]) for uid in jobs}
    bundle=dict(capacities={'S':80});bindings=dict(known={('S',t+24):0. for t in range(96)},risk={('S',t+24):1. for t in range(96)},timing={})
    with gp.Model() as model:
        model.Params.OutputFlag=0;x=model.addVar();model.update()
        expr=3*x+1
        bindings['timing']=dict(work=np.array([2.,3.]),value=expr,realized=False)
        proxy=SimpleNamespace(getVarByName=lambda name:x)
        controls=[[expr,0.,0.]]*96
        def forbidden(*args,**kwargs):raise AssertionError('export invoked optimize')
        monkeypatch.setattr(gp.Model,'optimize',forbidden)
        export.materialize(proxy,(bundle,jobs,{},None,{},None,None,dict(classes={str(i):[] for i in range(117)})),
                           bindings,controls,selected,dict(PASS=True),dict(complete=True),dense=np.array([2.]))
    anchor=read(tmp_path/'A1_AIDC_GRID_CONTROL_ANCHOR.json');policy=read(tmp_path/'A1_UNKNOWN_POLICY_TABLE.json')
    assert anchor['controls']==[[7.,0.,0.]]*96
    assert policy['temporal_and_report_state']==dict(work=[2.,3.],value=7.,realized=False)
    assert policy['individual_future_jobs']==[]
