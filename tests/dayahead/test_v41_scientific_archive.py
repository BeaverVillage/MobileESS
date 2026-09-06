from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.grid_archive import full_axis, persist, axis
from dayahead.v41.scientific_archive import document, native, artifact_entry, verify_manifest, seal, SCHEMA, delta_table


def test_complete_cartesian_time_topology_and_missing_critical_slot():
    frame=pd.DataFrame([dict(slot=t,line='critical' if i==0 else 'other',phase='A') for t in range(96) for i in range(2)])
    full_axis(frame,['line','phase'],[('critical','A'),('other','A')])
    bad=frame.copy(); bad.loc[frame.index[0],'slot']=95
    with pytest.raises(ValueError,match='AXIS'): full_axis(bad,['line','phase'],[('critical','A'),('other','A')])
    with pytest.raises(ValueError): full_axis(frame.iloc[1:],['line','phase'],[('critical','A'),('other','A')])


def grid_fixture():
    from dayahead.v28r2.opendss_results import OpenDSSResult
    v=np.ones((96,2)); v[83,1]=.947; v[12,0]=1.051
    amps=np.tile([[10.,20.]],(96,1)); amps[87,0]=110.
    ratios=amps/100; tx=np.full((96,2),np.nan); tx[:,1]=.2
    result=OpenDSSResult('2025-05-01','ACTUAL','B0','snapshot',('bus.1','bus.2'),('A','B'),
        ('line.l','transformer.t'),('A','B'),('line','transformer'),np.ones(96,dtype=bool),v,amps,ratios,tx,
        np.tile([[2.,1.]],(96,1)),np.ones((96,7)),np.zeros((96,4),int),'test',1.)
    observed=dict(voltage_angles=np.tile([[0.,-120.]],(96,1)).tolist(),system=np.tile([[-30.,-5.]],(96,1)).tolist(),
        branch=[dict(line_id=name,from_bus='up',to_bus='down',phase=phase,current_limit_A=100.,P_flow_kW=10.,Q_flow_kvar=1.)
                for t in range(96) for name,phase in [('line.l','A'),('transformer.t','B')]])
    return result,observed


def test_complete_electrical_tables_reconstruct_physical_extrema(tmp_path):
    from dayahead.v41.persistence import table
    result,observed=grid_fixture(); original=result.voltage_pu.copy()
    components=tmp_path/'components.parquet'; table(components,pd.DataFrame(dict(slot=range(96),P_net_kw=28.,Q_net_kvar=4.)))
    v,b,s=persist(tmp_path/'grid','2025-05-01','B0','Actual',result,observed,components)
    assert len(v)==len(b)==192 and len(s)==96
    assert np.array_equal(result.voltage_pu,original)
    assert v.voltage_pu.min()==result.summary['Vmin_pu'] and v.voltage_pu.max()==result.summary['Vmax_pu']
    assert s.rho_max.max()==result.summary['rho_max_AC']==1.1
    assert b.loc[b.loading_pu.idxmax(),'slot']==87
    assert v.loc[v.voltage_pu.idxmin(),'slot']==83
    assert s.voltage_violation_count.sum()==result.summary['voltage_violation_count']
    for name in ('BUS_PHASE_VOLTAGES.parquet','BRANCH_PHASE_CURRENTS.parquet','FEEDER_SYSTEM_96.parquet'):
        assert pd.read_parquet(tmp_path/'grid'/name).shape[0] in (96,192)


def test_missing_grid_observation_is_a_failure(tmp_path):
    r,o=grid_fixture(); o['voltage_angles']=o['voltage_angles'][:-1]
    with pytest.raises(ValueError,match='COVERAGE'): persist(tmp_path,'2025-05-01','B0','Actual',r,o,tmp_path/'none')


def test_manifest_readback_orphans_missing_and_corruption(tmp_path):
    p=tmp_path/'trajectory.parquet'; pd.DataFrame(dict(slot=range(96),power_kW=np.arange(96)/3)).to_parquet(p,index=False)
    entry=artifact_entry(p,tmp_path,'A0')
    document(tmp_path/'SCIENTIFIC_MANIFEST.json',dict(schema=SCHEMA,status='PASS',artifacts=[entry]))
    verify_manifest(tmp_path/'SCIENTIFIC_MANIFEST.json')
    extra=tmp_path/'unregistered.json'; write_json(extra,{'summary_only':True})
    with pytest.raises(ValueError,match='ORPHAN'): verify_manifest(tmp_path/'SCIENTIFIC_MANIFEST.json')
    extra.unlink(); f=pd.read_parquet(p); f.loc[95,'power_kW']=999.; f.to_parquet(p,index=False)
    with pytest.raises(ValueError,match='DRIFT'): verify_manifest(tmp_path/'SCIENTIFIC_MANIFEST.json')


def test_summary_and_solver_pass_cannot_mark_a_phase_complete(tmp_path):
    write_json(tmp_path/'SOLVER.json',dict(status='OPTIMAL',objective=.2))
    with pytest.raises(ValueError,match='REQUIRED_SCIENTIFIC_FILE_MISSING'): seal(tmp_path,'dayahead')
    assert not (tmp_path/'SCIENTIFIC_MANIFEST.json').exists()


def test_comparison_requires_identical_site_time_axis(tmp_path):
    d=pd.DataFrame(dict(slot=range(96),site='s',P=np.arange(96,dtype=float)))
    a=d.copy(); a.P+=1
    frame=delta_table(tmp_path,'difference.parquet',d,a,['slot','site'],['P'])
    assert (frame.P_delta==1).all()
    with pytest.raises(ValueError,match='AXIS'): delta_table(tmp_path,'missing.parquet',d,a.iloc[1:],['slot','site'],['P'])


def test_nested_stage_payload_roundtrips_dataclasses_without_changing_them(tmp_path):
    @dataclass(frozen=True)
    class State:
        slots:tuple
    value=State(({'stage':'M1','p_kw':np.float64(3.)},))
    before=deepcopy(value)
    document(tmp_path/'STAGE.json',dict(A0={'jobs':[]},M1=value,A1={'jobs':[]},MF=value))
    assert value==before
    assert read(tmp_path/'STAGE.json')['M1']==native(value)


def test_actual_cannot_open_inputs_without_verified_day_ahead(monkeypatch):
    from dayahead.v41 import execution
    from dayahead.v40d_actual import inputs
    opened=[]
    monkeypatch.setattr(inputs,'observations',lambda *a:opened.append(True))
    def denied(*args): raise RuntimeError('MISSING_VERIFIED_FREEZE')
    monkeypatch.setattr(execution,'verify_dayahead',denied)
    with pytest.raises(RuntimeError,match='MISSING_VERIFIED_FREEZE'): execution.actual('2025-05-01','B0')
    assert opened==[]


def test_observed_solver_preserves_values_and_freeze_ledger(tmp_path):
    import gurobipy as gp
    from dayahead.v41.solver_observer import observe
    original=gp.Model.optimize
    with gp.Model() as m:
        m.Params.OutputFlag=0; m.Params.Threads=4
        x=m.addVar(vtype=gp.GRB.INTEGER,lb=1,ub=5)
        m.setObjective(x)
        with observe(tmp_path,'A0'):
            m.optimize(); first=x.X
            m.addConstr(x==first,name='PRIMARY_EXACT_VALUE_LOCK')
            m.setObjective(-x); m.optimize()
        assert x.X==first==1 and gp.Model.optimize is original
    passes=[read(p) for p in sorted(tmp_path.glob('*.json'))]
    assert len(passes)==2 and all(p['stage']=='A0' for p in passes)
    assert passes[1]['active_freeze_constraints'][0]['name']=='PRIMARY_EXACT_VALUE_LOCK'
    assert all('node_count' in p and 'iteration_count' in p and p['configuration']['Threads']==4 for p in passes)
    assert all('observation_error' not in p for p in passes)


def test_all_four_mess_have_exact_96_slot_state_and_route_rows(tmp_path):
    from dayahead.v41.scientific_archive import mess
    from dayahead.v41.execution import off_commands
    commands=off_commands(); before=deepcopy(commands)
    frame=mess(tmp_path,'2025-05-01',commands)
    assert len(frame)==384 and frame.mess_id.nunique()==4
    assert len(pd.read_parquet(tmp_path/'DISCRETE_STATES.parquet'))==384
    assert read(tmp_path/'FROZEN_ROUTE_DISCRETE.json')['route_discrete_SHA']
    assert commands==before
    with pytest.raises(ValueError): mess(tmp_path/'incomplete','2025-05-01',commands[:-1])


def test_actual_input_manifest_has_frozen_boundary_and_source_hashes(tmp_path,monkeypatch):
    from dayahead.v41 import scientific_archive as archive
    from dayahead.v41.persistence import table
    from dayahead.v41.preflight import record
    monkeypatch.setattr(archive,'SOURCE_REPO',tmp_path/'source')
    da=tmp_path/'unit/dayahead'; ac=tmp_path/'unit/actual'
    document(da/'JOINT_FREEZE_RECEIPT.json',dict(DayAhead_decision_SHA='frozen',Actual_data_opened=False))
    document(ac/'ACTUAL_BOUNDARY_RECEIPT.json',dict(decision_SHA='frozen'))
    document(da/'authority/COMMON_INPUT_IDENTITY.json',dict(ML_snapshot_hash='ml'))
    document(da/'authority/AUTHORITY_MANIFEST.json',dict(policy='B0'))
    source=tmp_path/'source/dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet'
    observations={'one':dict(id='one',start_time=pd.Timestamp('2025-05-01T00:00:00Z'),end_time=pd.Timestamp('2025-05-01T01:00:00Z'),gpus_requested=1)}
    table(source,pd.DataFrame(observations.values()))
    exo=dict(weather=pd.DataFrame(dict(t_wb_c=[20.]*96,rh_pct=[50.]*96)),demand_mw=np.ones(96),pv_mw=np.zeros(96),authority={'synthetic_unit_test':record(source)})
    contributors=table(tmp_path/'contributors.parquet',pd.DataFrame(dict(job_id=['two'],GPU_service_GPUh=[2.])))
    workload={'source_membership':dict(daily_slice=contributors,authority=record(source))}
    decision=dict(AIDC_decision=[dict(job_uid='one')]); moves={'moves':[]}
    archive.actual_inputs(ac,'2025-05-01',decision,da,observations,exo,moves,workload)
    manifest=read(ac/'authority/ACTUAL_SOURCE_MANIFEST.json')
    assert manifest['runtime']['slice']['rows']==1 and manifest['exogenous']['slice']['rows']==96
    assert manifest['verified_joint_freeze']==record(da/'JOINT_FREEZE_RECEIPT.json')
    assert manifest['runtime']['source']==record(source)
    assert 'ACTUAL' in manifest['role'] and not list(da.rglob('ACTUAL*'))


def test_stage_snapshots_contain_inputs_allowed_frozen_and_decision_hashes(tmp_path,monkeypatch):
    from dayahead.v41 import scientific_archive as archive,grid_archive
    from tests.dayahead.test_v40g_segments import context96
    import dayahead.v40g_segments.canonical as canonical_module
    from dayahead.v41.execution import off_commands
    ctx,job=context96(); ctx.day='2025-05-01'; ctx.v41_ml_snapshot_sha256='same'
    monkeypatch.setattr(canonical_module,'planning_power',lambda jobs,c:dict(pcc=np.zeros((96,12))))
    monkeypatch.setattr(grid_archive,'planning',lambda *a,**k:None)
    # Existing toy coefficients expose one station; use zero-command states
    # without a service connection for this purely observational stage test.
    commands=off_commands()
    for c in commands:c['service_id']=None
    before=None
    for name in ('A0_OUTPUT','M1_INPUT','M1_OUTPUT','A1_INPUT','A1_OUTPUT','MF_INPUT','MF_OUTPUT','JOINT_FREEZE'):
        before=archive.stage(tmp_path,name,[job],commands,context=ctx,allowed=['registered stage fields'],frozen=['ML','RUNNING'],previous=before)
        saved=read(tmp_path/'optimization/stages'/f'{name}.json')
        assert saved['ML_snapshot_hash']=='same' and saved['AIDC_identity']==before['AIDC_identity']
        assert saved['frozen']==['ML','RUNNING'] and len(saved['MESS_commands'])==384


def test_atomic_republication_closes_source_before_replace(tmp_path,monkeypatch):
    from dayahead.v41.scientific_archive import republish_atomic
    from dayahead.paper_analysis import storage
    path=tmp_path/'durable.bin'; original=bytes(range(256))*4096; path.write_bytes(original)
    replace=storage.os.replace; opened=[]; original_open=Path.open
    def tracked_open(self,*args,**kwargs):
        stream=original_open(self,*args,**kwargs)
        if self==path: opened.append(stream)
        return stream
    def checked_replace(source,destination):
        assert all(s.closed for s in opened)
        return replace(source,destination)
    monkeypatch.setattr(Path,'open',tracked_open); monkeypatch.setattr(storage.os,'replace',checked_replace)
    republish_atomic(path)
    assert path.read_bytes()==original and not list(tmp_path.glob('*.tmp'))


def test_fixed_route_travel_comparison_and_empty_fleet(tmp_path):
    from dayahead.v41.scientific_archive import travel_comparisons
    command=dict(mess_id='m1',slot=4,departure_slot=4,route_link_ids='["a", "b"]',
        route_safe_eta_sec=1200.,connection_ready_slot=7,energy_safe_kwh=2.)
    move=dict(mess_id='m1',departure_slot=4,route_link_ids=['a','b'],actual_eta_seconds=900.,
        actual_arrival_slot=5.,actual_connection_ready_slot=6,actual_travel_energy_kWh=1.5)
    frame=travel_comparisons(tmp_path/'travel',pd.DataFrame([command]),[move])
    assert frame.travel_seconds_delta.iloc[0]==-300. and frame.mobility_energy_kWh_delta.iloc[0]==-.5
    assert pd.read_parquet(tmp_path/'travel/MESS_TRAVEL_DELTAS.parquet').equals(frame)
    with pytest.raises(ValueError,match='ROUTE_CHANGED'):
        travel_comparisons(tmp_path/'bad',pd.DataFrame([command]),[{**move,'route_link_ids':['b','a']}])
    empty=travel_comparisons(tmp_path/'empty',pd.DataFrame([{**command,'departure_slot':None}]),[])
    assert len(empty)==0 and empty.travel_seconds_actual.sum()==0
