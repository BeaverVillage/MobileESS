"""Read-only reconstruction of unchanged Actual inputs from frozen DA decisions."""
from binding import *
import numpy as np, pandas as pd
from dayahead.paper_analysis.storage import canonical
from types import FunctionType

def save(path,value):
    # Use the existing authoritative Timestamp/NumPy serializer for raw job records.
    common.save(path,json.loads(canonical(value)))

def configure_read_only(day):
    from v41r4_electrical import configure
    module = configure(day)
    import dayahead.v41r3.authority as r3
    wrapped = r3.scale_background
    closure = dict(zip(wrapped.__code__.co_freevars, wrapped.__closure__))
    original = closure['original_scale'].cell_contents
    actual_scale = FunctionType(original.__code__,dict(original.__globals__,SCALE=OUT/'common_inputs'/day),original.__name__,original.__defaults__,original.__closure__)
    def scale(background, stage):
        if stage == 'DAYAHEAD':
            return wrapped(background, stage)
        assert stage == 'ACTUAL'
        keys = sorted(set().union(*(set(r) for r in background.gross_p_kw_96)))
        values = dict(bus_phase_keys=np.array([b+'::'+p for b,p in keys]))
        for name, field in [('gross_P_kw','gross_p_kw_96'),('gross_Q_kvar','gross_q_kvar_96'),('PV_P_kw','pv_generation_kw_96')]:
            values[name] = np.asarray([[r.get(k,0.) for k in keys] for r in getattr(background,field)])
        old = ROOT/'frozen_artifacts/v41r4_may/audit'/day/'inputs/ORIGINAL_ACTUAL_BACKGROUND.npz'
        target = OUT/'common_inputs'/day/'inputs/ORIGINAL_ACTUAL_BACKGROUND.npz'
        if old.exists():
            prior = arrays(old)
            assert set(prior)==set(values) and all(np.array_equal(prior[k],v) for k,v in values.items())
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(target,**values)
        else:
            prior=arrays(target)
            assert all(np.array_equal(prior[k],v) for k,v in values.items())
        result=actual_scale(background,stage)
        assert result.evidence['alpha_BG']==1.15 and result.pv_generation_kw_96==background.pv_generation_kw_96
        return result
    r3.scale_background=scale
    return module

def prepare(day, policy, ctx, eta, da, independent_audit):
    from v41r4_loop_runtime import verify_old_or_current
    decision, receipt = verify_old_or_current(day,policy)
    from dayahead.v41.execution import SOURCE_REPO, bind
    from dayahead.v41.data import issue_time
    from dayahead.v40d_actual.inputs import observations
    from dayahead.v40d_actual.exogenous import load as load_exogenous
    from dayahead.v40d_actual.rack_dispatch import Rack
    from dayahead.v41.actual_dispatch import replay_jobs,power_from_execution,persist
    from dayahead.v41r2.authority import capacity
    from dayahead.v41.scientific_archive import scalar_frame
    import dayahead.v40d_actual.mobility_inputs as mobility
    from dayahead.v40d_actual.mess_replay import replay_commands
    folder=OUT/'common_inputs'/day/policy
    folder.mkdir(parents=True,exist_ok=True)
    assert not (folder/'READY.json').exists(), 'COMMON_INPUT_ALREADY_CREATED'
    before={str(p):sha(p) for p in (RUN/day/policy/'dayahead').rglob('*') if p.is_file()}
    save(folder/'DA_FRESH_INPUT_SNAPSHOT.json',before)
    bind(ctx,Path(decision['ML_snapshot']['path']),decision['ML_snapshot']['sha256'])
    obs=observations(SOURCE_REPO/'dayahead/artifacts/v40d_actual_realized_replay')
    _, details=capacity()
    racks=[Rack(r['aidc_id'],r['rack_pool_id'],int(r['compatibility_GPU_limit'])) for r in details['rack_authority']['logical_Rack_pools']]
    jobs=replay_jobs(decision['AIDC_decision'],obs,issue_time=issue_time(day),site_capacity=ctx.capacity.site_capacity,racks=racks,wan=ctx.wan)
    save(folder/'ACTUAL_JOB_REPLAY.json',jobs)
    persist(folder,jobs,obs,issue_time(day),ctx.capacity.site_capacity,racks)
    assert jobs['capacity_audit']['status']=='PASS'
    exo=load_exogenous(SOURCE_REPO,day)
    save(folder/'ACTUAL_EXOGENOUS_AUTHORITY.json',exo['authority'])
    power=power_from_execution(ROOT,jobs,ctx.capacity.site_capacity,exo['weather'])
    np.savez_compressed(folder/'ACTUAL_AIDC_POWER.npz',**{k:power[k] for k in ('occupancy','IT','PCC_P','PCC_Q')})
    ef=exo['weather'].reset_index(drop=True).copy()
    ef.insert(0,'timestamp',pd.to_datetime(exo['timestamps'],utc=True));ef.insert(0,'slot',range(96))
    ef['demand_MW']=exo['demand_mw'];ef['PV_MW']=exo['pv_mw']
    (folder/'authority').mkdir(exist_ok=True)
    ef.to_parquet(folder/'authority/ACTUAL_EXOGENOUS_96.parquet',index=False)
    def eta_replay(*args,**kwargs):
        kwargs.update(e_min=da.energy_min_kwh,e_max=da.energy_max_kwh,pcs_kva=da.pcs_kva,eta_charge=eta['eta_charge'],eta_discharge=eta['eta_discharge'],dt_hours=da.interval_hours)
        return replay_commands(*args,**kwargs)
    def audit(commands,moves,executed,initial_energy,initial_states):
        return independent_audit(dict(frozen_commands=commands,moves=moves,initial_energy=initial_energy,initial_states=initial_states),executed,eta,da)
    mobility.replay_commands=eta_replay;mobility.audit_mess=audit
    mess=mobility.actual_mobility(SOURCE_REPO,dict(day=day,case='B3',final_PQ_source=str(RUN/day/policy/'dayahead/FROZEN_MESS_COMMANDS.json')))
    scalar_frame(mess['frame'].to_dict('records')).to_parquet(folder/'ACTUAL_MESS_TIMESERIES.parquet',index=False)
    saved={k:v for k,v in mess.items() if k not in ('frame','p','q','locations')}
    save(folder/'ACTUAL_MESS_AUDIT.json',saved)
    from dayahead.paper_analysis.storage import digest as execution_digest
    identity=execution_digest(dict(decision=receipt['decision_SHA'],jobs=jobs['job_ledger']))
    old=RUN/day/policy/'actual'
    historical=(old/'ACTUAL_RECEIPT.json').exists()
    regression={}
    if historical:
        original=arrays(old/'ACTUAL_AIDC_POWER.npz')
        regression['AIDC_arrays_bit_identical']=all(np.array_equal(original[k],power[k]) for k in original)
        oldexo=pd.read_parquet(old/'authority/ACTUAL_EXOGENOUS_96.parquet').sort_values('slot')
        regression['exogenous_bit_identical']=all(np.array_equal(oldexo[k].to_numpy(),ef[k].to_numpy()) for k in ('demand_MW','PV_MW')) and pd.to_datetime(oldexo.timestamp,utc=True).tolist()==pd.to_datetime(ef.timestamp,utc=True).tolist()
        regression['grid_schedule_identity']=read(old/'grid/OPENDSS_SUMMARY.json')['schedule_sha256']==identity
        original_mess=read(old/'ACTUAL_MESS_AUDIT.json')
        # Source reference metadata may contain extra 'exists' fields. Physical route/timing rows may not differ.
        def physical_moves(rows):
            return [{k:v for k,v in r.items() if k not in ('frozen_command_source','actual_traffic_source')} for r in rows]
        regression['moves_identical']=physical_moves(original_mess['moves'])==physical_moves(saved['moves'])
        regression['commands_identical']=original_mess['frozen_commands']==saved['frozen_commands']
        assert all(regression.values()),('COMMON_ACTUAL_REGRESSION_FAILED',day,policy,regression)
        save(folder/'COMMON_BINDING_REGRESSION.json',dict(status='PASS',checks=regression,old_root=str(old)))
    # H4 is reporting only and never passed to the Q controller.
    if historical:
        score=read(old/'ACTUAL_RESULT.json')['frozen_future_workload_score']
    else:
        from dayahead.v41.actual import realized_workload
        wp=OUT/'common_inputs'/day/'workload';wp.mkdir(exist_ok=True)
        wfile=wp/'REALIZED_WORKLOAD.json'
        if not wfile.exists():save(wfile,realized_workload(day,wp))
        workload=read(wfile)
        head=np.array(read(RUN/day/policy/'dayahead/PLANNING_RESULT.json')['reserve']['H_available_GPUh'])
        actual=np.array(workload['H4_actual_GPUh'])
        score=dict(realized_H4_GPUh=actual.tolist(),frozen_headroom_GPUh=head.tolist(),realized_shortfall_GPUh=np.maximum(actual-head,0).tolist(),future_scheduling_calls=0)
    save(folder/'H4_SCORE.json',score)
    assert all(sha(p)==h for p,h in before.items()), 'UPSTREAM_CHANGED_DURING_INPUT_REBUILD'
    save(folder/'READY.json',dict(status='PASS',historical_Actual_available=historical,identity=identity,decision_SHA=receipt['decision_SHA'],regression=regression,eta_charge=.95,eta_discharge=.95,scheduling_optimizer_calls=0))
    return folder
