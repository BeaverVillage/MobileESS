"""Explicit V39E build_day -> V37/V36 FrozenTrajectory -> native Fresh port.

The B1 fixed-decision power replay is unchanged. Current V42 autonomous
controls, realized background, and NormalAmps replace superseded bindings.
There is no Actual optimizer, trajectory repair, or MESS dispatch path.
"""
from pathlib import Path
from types import SimpleNamespace
from .common import *
from v42_a_stage_domain_v2.execution import require_action_authorized
from v42_a_stage_domain_v2.status import require_production_domain_accepted


def freeze_planning(root, day, a1_folder, output, freeze):
    require_action_authorized(day,'PLANNING_FREEZE')
    import numpy as np
    result=read(a1_folder/'A1_FREEZE.json')
    require_production_domain_accepted(result.get('domain_status'))
    if not result['PASS'] or not result['accepted'] or result['day'] != day or result['arm'] != 'B1':
        raise ValueError('NEW_ACCEPTED_A1_REQUIRED')
    with np.load(a1_folder/'PLANNING_PHYSICAL.npz') as z:
        p,q,it,gpu,sites=(z[k].copy() for k in ('PCC_P_kw','PCC_Q_kvar','IT_kw','GPU','sites'))
    pcc=[]; itr=[]; gr=[]
    for t in range(96):
        for i,s in enumerate(map(str,sites)):
            pcc.append(dict(slot=t,AIDC=s,PCC_P_kW=float(p[t,i]),PCC_Q_kvar=float(q[t,i])))
            itr.append(dict(slot=t,AIDC=s,IT_power_kW=float(it[t,i])))
            gr.append(dict(slot=t,AIDC=s,active_GPU=float(gpu[t,i])))
    decision=dict(status='PASS',arm='B1',day=day,temporal_mode='RSP',
                  site_PCC_power_trajectory=pcc,site_IT_power_trajectory=itr,site_GPU_trajectory=gr,
                  known_job_actions=result['selected_jobs'],common_initial_state_SHA256=freeze['day_input_SHA'][day],
                  temporal_schedule_SHA256=digest(result['selected_jobs']),AIDC_assignments=result['selected_jobs'],
                  capacity_GPU=sum(read(root/'inputs'/day/'NATIVE_INPUT.json')['capacities'].values()),
                  unknown_arrival_policy='ACCEPTED_V39E_FIXED_FROZEN_TRAJECTORY_NO_RESCHEDULING',
                  MESS_OFF=True,ML_OFF=False,current_V42_A1_only=True,old_freezes_reused=0)
    payload=dict(decision=decision,DA_decision_SHA256=digest(decision),identity=identity(freeze,day,'PLANNING_FREEZE'),
                 A1_receipt_source=record(a1_folder/'A1_FREEZE.json'),source_lineage='V39E campaign_adapter.build_day -> V37 -> V36')
    atomic(output/'V42_DAYAHEAD_DECISION_FREEZE.json',payload)
    return dict(PASS=True,folder=str(output),freeze=record(output/'V42_DAYAHEAD_DECISION_FREEZE.json'))


def build_day(path, expected_identity):
    """Port of V39E build_day's same frozen trajectory schema/axis semantics."""
    import numpy as np
    import pandas as pd
    from v42_regcontrol.authority import source
    source()  # Adds only the SHA-verified accepted dayahead source package.
    from dayahead.v37.aidc import AIDCTrajectory
    freeze=read(path); decision=freeze['decision']
    if freeze['identity'] != expected_identity or decision['status'] != 'PASS' or digest(decision) != freeze['DA_decision_SHA256']:
        raise ValueError('V42_NEW_DAYAHEAD_FREEZE_IDENTITY_OR_SHA')
    pcc=pd.DataFrame(decision['site_PCC_power_trajectory']).sort_values(['slot','AIDC']).reset_index(drop=True)
    if len(pcc)!=96*12 or pcc[['slot','AIDC']].duplicated().any(): raise ValueError('V39E_DA_PCC_AXIS')
    p=pcc.PCC_P_kW.to_numpy(float).reshape(96,12); q=pcc.PCC_Q_kvar.to_numpy(float).reshape(96,12)
    it=pd.DataFrame(decision['site_IT_power_trajectory']).groupby('slot').IT_power_kW.sum().to_numpy(float)
    gpu=pd.DataFrame(decision['site_GPU_trajectory']).groupby('slot').active_GPU.sum().to_numpy(float)
    power=pd.DataFrame(dict(slot=np.arange(96),N_active_GPU=gpu,N_idle_GPU=decision['capacity_GPU']-gpu,
                            P_IT_case_kW=it,aggregate_PCC_P_kW=p.sum(1),aggregate_PCC_Q_kvar=q.sum(1),AIDC_flexibility='ON'))
    ledger=pd.DataFrame([dict(job_uid=uid,**value) for uid,value in decision['known_job_actions'].items()])
    contract=digest(dict(semantics='V39E_FROZEN_DA_FIXED_REPLAY',decision_SHA256=freeze['DA_decision_SHA256'],P=p.tolist(),Q=q.tolist()))
    return AIDCTrajectory(day=decision['day'],power=power,ledger=ledger,
                          site=pcc.rename(columns={'AIDC':'AIDC_id'}),pcc_p_kw=p,pcc_q_kvar=q,
                          contract_sha256=contract,fingerprints=dict(V42_freeze_SHA256=sha(path),run_id=expected_identity['run_id']))


def actual(planning, expected_identity, output):
    require_action_authorized(expected_identity,'ACTUAL')
    import numpy as np
    aidc=build_day(planning/'V42_DAYAHEAD_DECISION_FREEZE.json',expected_identity)
    # Exact historical B1 fixed-decision materialization: no B0 FCFS replay and
    # no new causal backend policy is invented here.
    np.savez_compressed(output/'ACTUAL_FIXED_TRAJECTORY.npz',PCC_P_kw=aidc.pcc_p_kw,PCC_Q_kvar=aidc.pcc_q_kvar)
    atomic(output/'ACTUAL_FIXED_REPLAY_RECEIPT.json',dict(PASS=True,day=aidc.day,arm='B1',
        Planning_freeze=record(planning/'V42_DAYAHEAD_DECISION_FREEZE.json'),
        contract_SHA=aidc.contract_sha256,Actual_reoptimization=0,local_PQ_repair=0,global_PQ_repair=0,
        M1=0,M2=0,MESS_PQ=0,policy='V39E_FROZEN_DA_FIXED_REPLAY',
        Actual_workload_semantics='fixed accepted Planning power/service trajectory; no rescheduling from retrospective outcomes',
        realized_load_PV='source-backed Actual exogenous arrays applied only by Fresh stage',
        future_feedback_to_Planning=False,old_historical_decisions_reused=0))
    return dict(PASS=True,folder=str(output))


def fresh(root,day,planning,actual_folder,output,freeze,progress):
    require_action_authorized(day,'FRESH_AC')
    import numpy as np
    import pandas as pd
    from v42_regcontrol.authority import source,compile_verified,assert_inventory
    from v42_regcontrol.runner import background
    from v42_thermal.authority import current_authority
    if current_authority()['transformer_current_authority_sha256'] != CHECKER: raise ValueError('CHECKER_DRIFT')
    m=source()
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v28r2.opendss_mapping import _set_load,_set_generator
    from v42_capacity.common import resolve
    bundle=read(root/'inputs'/day/'NATIVE_INPUT.json'); ops=read(root/'inputs'/day/'OPERATIONS.json'); folder=Path(ops['current_day_folder'])
    prov=read(folder/'SOURCE_PROVENANCE.json'); raw_path=resolve(prov['daily_sources']['aemo_actual.parquet'])
    exo=pd.read_parquet(raw_path)
    stamps=[pd.Timestamp(t).tz_convert('Etc/GMT-10').isoformat() for t in exo.ts_fixed_aest_end]
    forecast=ops['forecast_inputs']['AEMO']
    if not pd.DatetimeIndex(stamps).tz_convert('UTC').equals(pd.DatetimeIndex(forecast['timestamps_96']).tz_convert('UTC')):
        raise ValueError('ACTUAL_EXOGENOUS_AXIS')
    bg=background(stamps,exo.demand_mw.tolist(),exo.rooftop_pv_mw.tolist())
    with np.load(actual_folder/'ACTUAL_FIXED_TRAJECTORY.npz') as z: p,q=z['PCC_P_kw'].copy(),z['PCC_Q_kvar'].copy()
    aidc=build_day(planning/'V42_DAYAHEAD_DECISION_FREEZE.json',identity(freeze,day,'PLANNING_FREEZE'))
    if not np.array_equal(p,aidc.pcc_p_kw) or not np.array_equal(q,aidc.pcc_q_kvar): raise ValueError('ACTUAL_FROZEN_POLICY_CHANGED')
    odd,adapter,initial=compile_verified()
    branches,topology=m['oriented_branches'](odd)
    nodes=tuple(sorted(n.lower() for n in odd.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in ('1','2','3')))
    odd.Basic.ClearAll()
    binding=SimpleNamespace(factories=[SimpleNamespace(data=SimpleNamespace(branches=branches))])
    context=SimpleNamespace(legacy_context=(None,None,bg,binding,None,None))
    zeros=np.zeros((96,4)); locations=tuple(tuple(('STA01','STA12','STA08','STA06')) for _ in range(96))
    trajectory=FrozenTrajectory(day,'DAYAHEAD','B1',p,q,zeros,zeros,('MESS01','MESS02','MESS03','MESS04'),locations,aidc.contract_sha256)
    voltage=dict(node_names=nodes)
    native=m['NativeAllocation'].from_adapter(adapter); logs=[]; applied=[]
    def compile_current(_assets):
        engine,ad,inventory=compile_verified(); native.validate_native_engine(engine); return engine,ad
    def apply_current(engine,ad,_context,tr,t):
        totals,ledger,allocation=native.apply(engine,bg,t)
        for row in ad['pv_generators']:
            key=(str(row['bus']).lower(),'ABC'[int(row['phase'])-1]); _set_generator(engine,row['generator_name'],bg.pv_generation_kw_96[t].get(key,0),0)
        for i in range(12): _set_load(engine,f'IDC_IDC{i+1:02d}',tr.pcc_p_kw[t,i],tr.pcc_q_kvar[t,i])
        for name in engine.Generators.AllNames():
            if name.lower().startswith('mess_dis_'): _set_generator(engine,name,0,0)
        for name in engine.Loads.AllNames():
            if name.lower().startswith('mess_chg_'): _set_load(engine,name,0,0)
        assert_inventory(m['inventory'](engine))
        applied.append(dict(slot=t,PCC_P_kw=p[t].tolist(),PCC_Q_kvar=q[t].tolist(),MESS_PQ=0,allocation=allocation))
    def controls(engine,_voltage,t):
        # No Planning-state access/setter. The original backend SolveSnap executes
        # the enabled autonomous regulators from the fresh source initial state.
        assert_inventory(m['inventory'](engine))
    original_voltage=backend._voltage_vector
    def measure_voltage(engine,axis):
        result=original_voltage(engine,axis); inventory=m['inventory'](engine); assert_inventory(inventory)
        if not engine.Solution.ControlActionsDone(): raise ValueError('CONTROL_ACTIONS_INCOMPLETE')
        logs.append(dict(slot=len(logs),taps=m['native_state'](engine)[0],caps=m['native_state'](engine)[1],
                         all_7_RegControls_enabled=True,CapControl_count=0,Planning_tap_replay=False))
        return result
    keys=('compile_clean_engine','apply_trajectory_slot','apply_frozen_native_state','_branch_measurement','_voltage_vector')
    old={k:getattr(backend,k) for k in keys}
    backend.compile_clean_engine=compile_current; backend.apply_trajectory_slot=apply_current
    backend.apply_frozen_native_state=controls; backend._branch_measurement=m['branch_measurement']; backend._voltage_vector=measure_voltage
    # Original accepted 96-slot backend body is executed without AST alteration.
    try: result=backend.run_fresh_opendss(repo=CODE,context=context,voltage=voltage,trajectory=trajectory,output=output/'fresh',progress=progress)
    finally:
        for k,v in old.items(): setattr(backend,k,v)
    atomic(output/'RAW_CONTROL_LOG.json',dict(source_initial_inventory=initial,slots=logs))
    atomic(output/'RAW_PHYSICAL_INPUT_LOG.json',dict(slots=applied,Actual_exogenous=record(raw_path)))
    summary=dict(result.summary)
    atomic(output/'FRESH_RESULT.json',dict(summary=summary,converged=bool(np.all(result.convergence)),
                                         checker_SHA=CHECKER,NormalAmps_current=True,Planning_tap_replay=False,
                                         local_PQ_repair=0,global_PQ_repair=0,Actual_reoptimization=0,all_MESS_PQ_zero=True))
    return dict(PASS=True,folder=str(output),summary=summary,converged=bool(np.all(result.convergence)))
