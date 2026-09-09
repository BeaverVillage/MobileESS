from common import *
protect()
import numpy as np,pandas as pd,time
from types import SimpleNamespace
from contextlib import contextmanager
from v41r4_electrical import configure
from dayahead.v40d_actual.grid_replay import replay
from dayahead.v40d_actual.mess_replay import replay_commands
from dayahead.v40e.mapping import corrected_mapping,NativeAllocation
from dayahead.v28r2 import opendss_backend as backend
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.electrical_context import source_root,with_realized_background
from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
from qsafe import run_qsafe,q_bounds

def independent_audit(saved,rows,eta,da,q_safety=False):
    """Separate derivation; never calls project_command or its legacy audit."""
    commands={(r['mess_id'],r['slot']):r for r in saved['frozen_commands']}
    actual={(r['mess_id'],r['slot']):r for r in rows};assert set(commands)==set(actual)
    departures={(r['mess_id'],r['slot']):r for r in commands.values() if r.get('departure_slot')==r['slot']}
    moves={(m['mess_id'],m['departure_slot']):m for m in saved['moves']};assert set(moves)==set(departures)
    traffic_cache={};source_refs=[]
    for key,m in moves.items():
        c=departures[key]
        for k in ('route_link_ids','origin_service_id','destination_service_id'):assert m[k]==c[k]
        src=m['actual_traffic_source'];path=src['path']
        if path not in traffic_cache:
            assert sha(path)==src['sha256'];source_refs.append(src)
            needed=[e for other in moves.values() for e in other['link_entries']]
            f=pd.read_parquet(path,columns=['slot5','reduced_link_id','final_tt_sec'],filters=[('reduced_link_id','in',sorted({e['link_id'] for e in needed})),('slot5','in',sorted({e['entry_step5'] for e in needed}))])
            traffic_cache[path]=f.set_index(['slot5','reduced_link_id'])
        elapsed=0.
        for e in m['link_entries']:
            step=3*m['departure_slot']+int(elapsed//300);assert e['entry_step5']==step
            duration=float(traffic_cache[path].loc[(step,e['link_id']),'final_tt_sec']);assert duration==e['travel_seconds'];elapsed+=duration
        from dayahead.v33m.contracts import CONNECTION_DELAY_SECONDS
        assert elapsed==m['actual_eta_seconds']
        assert m['actual_connection_ready_slot']==m['departure_slot']+math.ceil((elapsed+CONNECTION_DELAY_SECONDS)/900)
    errors=[]
    for vehicle,initial in sorted(saved['initial_energy'].items()):
        energy=initial;location=next(s['frozen_initial_location'] for s in saved['initial_states'] if s['vehicle_id']==vehicle)
        vm=sorted((m for m in moves.values() if m['mess_id']==vehicle),key=lambda m:m['departure_slot'])
        for t in range(96):
            c=commands[vehicle,t];r=actual[vehicle,t]
            arrived=[m for m in vm if m['actual_connection_ready_slot']<=t]
            if arrived:location=arrived[-1]['destination_service_id']
            active=[m for m in vm if m['departure_slot']<=t<m['actual_connection_ready_slot']];assert len(active)<=1
            assert r['connected']==(not active) and r['actual_service_id']==(None if active else location)
            travel=moves.get((vehicle,t),{}).get('actual_travel_energy_kWh',0.)
            available=energy-travel
            assert da.energy_min_kwh-1e-9<=available<=da.energy_max_kwh+1e-9
            pcl=-(da.energy_max_kwh-available)/(eta['eta_charge']*da.interval_hours)
            pcu=(available-da.energy_min_kwh)*eta['eta_discharge']/da.interval_hours
            p=0. if active else min(max(c['p_kw'],min(0.,pcl)),max(0.,pcu))
            qlimit=math.sqrt(max(0.,da.pcs_kva**2-p*p))
            q=0. if active else min(max(c['q_kvar'],-qlimit),qlimit)
            after=available+eta['eta_charge']*max(-p,0)*da.interval_hours-max(p,0)*da.interval_hours/eta['eta_discharge']
            if q_safety:
                q=r['Q_EXEC'];assert not active or q==0.
                assert math.hypot(p,q)<=da.pcs_kva+1e-9
                from dayahead.mess_physics import pcs_inner_polygon_satisfied
                assert pcs_inner_polygon_satisfied(p,q)
            expected=dict(P_CMD=c['p_kw'],Q_CMD=c['q_kvar'],P_EXEC=p,Q_EXEC=q,energy_before_kWh=energy,travel_energy_kWh=travel,energy_after_kWh=after,SoC_before=energy/da.capacity_kwh,SoC_after=after/da.capacity_kwh)
            errors.extend(abs(r[k]-v) for k,v in expected.items());energy=after
            assert da.energy_min_kwh-1e-9<=energy<=da.energy_max_kwh+1e-9
    assert max(errors)<1e-9,max(errors)
    return dict(status='PASS',eta_authority_SHA=sha(OUT/'BATTERY_EFFICIENCY_AUTHORITY.json'),independent_max_error=max(errors),route_departure_location_verified=True,traffic_source_entries_verified=True,traffic_sources=source_refs,scheduling_optimizer_calls=0)

@contextmanager
def isolated_compile(folder):
    original=backend.compile_clean_engine
    def compile(assets):
        cwd=Path.cwd();odd,adapter=original(assets);odd.Basic.AllowChangeDir(False);odd.Basic.DataPath(str(folder));os.chdir(cwd);return odd,adapter
    backend.compile_clean_engine=compile
    try:yield
    finally:backend.compile_clean_engine=original

def actual_context(ctx,power,exo,day):
    legacy=list(ctx.electrical.legacy_context)
    if legacy[0] is None:legacy[0]={}
    base=SimpleNamespace(legacy_context=tuple(legacy),source_root=source_root(SOURCE_DATA_REPOSITORY),voltage=ctx.electrical.voltage,current=ctx.electrical.current,voltage_path=ctx.electrical.voltage_path,current_path=Path(ctx.electrical.voltage_path).with_name(f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz'))
    return with_realized_background(SOURCE_DATA_REPOSITORY,base,timestamps_96=exo['timestamps'],demand_mw_96=exo['demand_mw'],pv_mw_96=exo['pv_mw'],aidc_plan_kw_96x12=power['PCC_P'])

def main(day,policies):
    assert day in read(OUT/'START_COHORT.json')['days'];eta,da=authority()
    for stage in ('ACTUAL','DAYAHEAD'):assert (ROOT/'frozen_artifacts/v41r4_may/audit'/day/'inputs'/f'ORIGINAL_{stage}_BACKGROUND.npz').is_file()
    import dayahead.v40e.electrical as loader
    def verify_npz(p,**values):
        old=arrays(p);assert set(old)==set(values) and all(np.array_equal(old[k],v) for k,v in values.items()),str(p)
    def verify_json(p,v):assert read(p)==json.loads(json.dumps(v)),str(p)
    loader.write_npz=verify_npz;loader.write_json=verify_json
    # Cache exact Fraction-based allocation results for identical immutable
    # current-slot inputs. Original arithmetic and outputs are unchanged.
    orig_allocate=NativeAllocation.allocate;allocation_cache={}
    def allocate(self,p,q):
        key=(id(p),id(q))
        if key not in allocation_cache:allocation_cache[key]=(p,q,orig_allocate(self,p,q))
        return allocation_cache[key][2]
    NativeAllocation.allocate=allocate
    print('LOAD_CONTEXT',day,flush=True);ctx=configure(day).load(day);print('CONTEXT_READY',day,flush=True)
    # Q solver is scipy only. Any accidental scheduling optimizer invocation fails.
    import gurobipy as gp
    gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('SCHEDULING_OPTIMIZER_FORBIDDEN'))
    try:
        for policy in policies:
            folder=OUT/'replays'/day/policy
            if (folder/'COMPLETE.json').exists():continue
            folder.mkdir(parents=True,exist_ok=True);root=RUN/day/policy;ac=root/'actual'
            saved=read(ac/'ACTUAL_MESS_AUDIT.json');old=pd.read_parquet(ac/'ACTUAL_MESS_TIMESERIES.parquet');ids=sorted(old.mess_id.unique())
            def values(frame,field):return frame.pivot(index='slot',columns='mess_id',values=field).reindex(index=range(96),columns=ids).to_numpy()
            aligned=replay_commands(saved['frozen_commands'],saved['moves'],saved['initial_energy'],initial_locations={s['vehicle_id']:s['frozen_initial_location'] for s in saved['initial_states']},capacity_kwh=da.capacity_kwh,e_min=da.energy_min_kwh,e_max=da.energy_max_kwh,pcs_kva=da.pcs_kva,eta_charge=eta['eta_charge'],eta_discharge=eta['eta_discharge'],dt_hours=da.interval_hours)
            assert aligned['frozen_commands_SHA']==saved['frozen_commands_SHA']
            f=pd.DataFrame(aligned['trajectory']);audit=independent_audit(saved,aligned['trajectory'],eta,da)
            for key in ('connected','actual_service_id','frozen_service_id','P_CMD','Q_CMD'):
                assert values(old,key).tolist()==values(f,key).tolist(),('FROZEN_BINDING_DRIFT',key)
            loc=values(f,'actual_service_id').astype(object);loc[pd.isna(loc)]='TRANSIT_UNAVAILABLE';loc=loc.astype(str)
            mess=dict(p=values(f,'P_EXEC'),q=values(f,'Q_EXEC'),ids=ids,locations=loc)
            power0=arrays(ac/'ACTUAL_AIDC_POWER.npz');power={k:power0[k] for k in ('PCC_P','PCC_Q')}
            ef=pd.read_parquet(ac/'authority/ACTUAL_EXOGENOUS_96.parquet').sort_values('slot')
            exo=dict(timestamps=[t.tz_convert('Etc/GMT-10').isoformat() for t in ef.timestamp],demand_mw=ef.demand_MW.to_numpy(),pv_mw=ef.PV_MW.to_numpy())
            identity=read(ac/'grid/OPENDSS_SUMMARY.json')['schedule_sha256']
            da_decision=read(root/'dayahead/FROZEN_JOINT_DECISION.json')['decision']
            decision_commands=read(root/'dayahead/FROZEN_MESS_COMMANDS.json')['MESS_trajectory']
            routefields=('mess_id','slot','service_id','departure_slot','origin_service_id','destination_service_id','route_link_ids','connection_ready_slot','mode')
            binding=dict(AIDC_schedule_SHA=digest(da_decision['AIDC_decision']),MESS_decision_SHA=digest([{k:r.get(k) for k in routefields} for r in decision_commands]),Actual_AIDC_power_file_SHA=sha(ac/'ACTUAL_AIDC_POWER.npz'),frozen_command_SHA=saved['frozen_commands_SHA'],realized_moves_SHA=digest(saved['moves']),locations_SHA=digest(loc.tolist()),eta_authority_SHA=sha(OUT/'BATTERY_EFFICIENCY_AUTHORITY.json'),alpha_BG=1.15)
            save(folder/'ORIGINAL_ACTUAL/REFERENCE.json',dict(namespace='ORIGINAL_ACTUAL',authoritative_root=str(ac),grid_SHA=sha(ac/'grid/OPENDSS_PHASE_ARRAYS.npz'),receipt_SHA=sha(ac/'ACTUAL_RECEIPT.json')))
            mode='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_ACTUAL';bpath=folder/mode;bpath.mkdir(exist_ok=True)
            if policy in ('B2','B3'):
                by={(r['mess_id'],r['slot']):r for r in decision_commands};errors=[]
                command_error=max(max(abs(r['p_kw']-by[r['mess_id'],r['slot']]['p_kw']),abs(r['q_kvar']-by[r['mess_id'],r['slot']]['q_kvar'])) for r in saved['frozen_commands'])
                assert command_error<1e-7,('FROZEN_DA_PQ_COMMAND_MISMATCH',command_error)
                audit['frozen_DA_PQ_command_max_error']=command_error
                for r in decision_commands:
                    travel=r['energy_safe_kwh'] if r['mode']=='TRANSIT' and r['slot']==r['departure_slot'] else 0.
                    expected=r['battery_energy_kwh']+.25*eta['eta_charge']*max(-r['p_kw'],0)-.25*max(r['p_kw'],0)/eta['eta_discharge']-travel
                    final=by[r['mess_id'],r['slot']+1]['battery_energy_kwh'] if r['slot']<95 else da.terminal_energy_kwh
                    errors.append(abs(expected-final))
                assert max(errors)<1e-6; audit['DA_stored_eta95_recurrence_max_error_kWh']=max(errors)
            with corrected_mapping(),isolated_compile(bpath):b,ba=replay(ROOT,day,policy,ctx,power,exo,mess,identity,bpath)
            save(bpath/'ACTUATOR.json',dict(binding=binding,trajectory=aligned['trajectory'],independent_audit=audit))
            np.savez_compressed(bpath/'EXECUTION.npz',P_EXEC=mess['p'],Q_EXEC=mess['q'],PCC_P=power['PCC_P'],PCC_Q=power['PCC_Q'],locations=loc,energy_after=values(f,'energy_after_kWh'),SoC_after=values(f,'SoC_after'))
            if policy in ('B0','B1'):
                assert np.array_equal(mess['p'],values(old,'P_EXEC')) and np.array_equal(mess['q'],values(old,'Q_EXEC'))
                original=arrays(ac/'grid/OPENDSS_PHASE_ARRAYS.npz');new=arrays(bpath/'OPENDSS_PHASE_ARRAYS.npz')
                identical={k:bool(np.array_equal(v,original[k],equal_nan=True)) if v.dtype.kind not in 'US' else bool(np.array_equal(v,original[k])) for k,v in new.items()}
                assert all(identical.values()),('CONTROL_REPLAY_DIFFERENCE',day,policy,identical)
                save(folder/'COMPLETE.json',dict(status='PASS',kind='CONTROL_REUSE_VERIFIED',binding=binding,all_grid_arrays_bit_identical=identical,summary=b.summary,scheduling_optimizer_calls=0))
                print('CONTROL_IDENTICAL',day,policy,flush=True);continue
            cpath=folder/'ETA95_QSAFE_ACTUAL';cpath.mkdir(exist_ok=True)
            ctrajectory=FrozenTrajectory(day,'ACTUAL',policy,power['PCC_P'].copy(),power['PCC_Q'].copy(),mess['p'].copy(),mess['q'].copy(),tuple(ids),loc.copy(),identity)
            act=actual_context(ctx,power,exo,day)
            with corrected_mapping():c,events=run_qsafe(act,ctx.electrical.voltage,ctrajectory,values(f,'connected'),da,cpath)
            # One uninterrupted accepted-Q replay independently checks that the
            # clean-prefix trial method preserved native sequential behavior.
            verify_path=cpath/'CONTINUOUS_VERIFICATION';verify_path.mkdir(exist_ok=True)
            accepted_mess={**mess,'p':ctrajectory.mess_p_kw,'q':ctrajectory.mess_q_kvar}
            with corrected_mapping(),isolated_compile(verify_path):verification,vbinding=replay(ROOT,day,policy,ctx,power,exo,accepted_mess,identity,verify_path)
            verror=float(np.max(np.abs(verification.voltage_pu-c.voltage_pu)))
            ierror=float(np.max(np.abs(verification.phase_current_loading_pu-c.phase_current_loading_pu)))
            assert verror<1e-10 and ierror<1e-10 and np.array_equal(verification.regulator_taps,c.regulator_taps),('ACCEPTED_CONTINUOUS_REPLAY_MISMATCH',verror,ierror)
            save(cpath/'CONTINUOUS_VERIFICATION.json',dict(status='PASS',max_voltage_difference_pu=verror,max_phase_current_loading_difference=ierror,taps_bit_identical=True,engine_binding=vbinding))
            crows=[]
            for r in aligned['trajectory']:
                q=float(ctrajectory.mess_q_kvar[r['slot'],ids.index(r['mess_id'])])
                crows.append({**r,'Q_EXEC':q,'Q_CURTAILED':r['Q_CMD']-q,'Q_SAFE_CMD':q})
            cf=pd.DataFrame(crows)
            caudit=independent_audit(saved,crows,eta,da,q_safety=True)
            unchanged=('P_CMD','P_EXEC','P_CURTAILED','connected','actual_service_id','frozen_service_id','energy_before_kWh','travel_energy_kWh','energy_after_kWh','SoC_before','SoC_after')
            checks={key:values(f,key).tolist()==values(cf,key).tolist() for key in unchanged};assert all(checks.values())
            assert np.array_equal(ctrajectory.pcc_p_kw,power['PCC_P']) and np.array_equal(ctrajectory.pcc_q_kvar,power['PCC_Q'])
            np.savez_compressed(cpath/'EXECUTION.npz',P_EXEC=ctrajectory.mess_p_kw,Q_EXEC=ctrajectory.mess_q_kvar,PCC_P=ctrajectory.pcc_p_kw,PCC_Q=ctrajectory.pcc_q_kvar,locations=loc,energy_after=values(cf,'energy_after_kWh'),SoC_after=values(cf,'SoC_after'))
            save(cpath/'ACTUATOR.json',dict(binding=binding,trajectory=crows,independent_audit=caudit))
            save(cpath/'C_VERSUS_B_AUDIT.json',dict(status='PASS',B_binding=binding,C_binding=binding,bit_identical_fields=checks,AIDC_power_bit_identical=True,P_EXEC_bit_identical=True,SoC_energy_bit_identical=True,only_Q_actuation_may_differ=True,PCS_16face_and_exact_norm_verified=True,scheduling_optimizer_calls=0,Q_optimizer_calls=sum(e['optimizer_calls'] for e in events),no_future_actual_applied=True,native_regulators_causal_sequential=True,alpha_BG=1.15))
            save(folder/'COMPLETE.json',dict(status='PASS',kind='DIAGNOSTIC_CANDIDATE',binding=binding,ETA95_ACTUAL=b.summary,ETA95_QSAFE_ACTUAL=c.summary,intervention_slots=sum(e['status']=='Q_CORRECTED' for e in events),Q_ONLY_INFEASIBLE_slots=sum(e['status']=='Q_ONLY_INFEASIBLE' for e in events),scheduling_optimizer_calls=0))
            print('DIAGNOSTIC_COMPLETE',day,policy,c.summary['Vmax_pu'],flush=True)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

if __name__=='__main__':main(sys.argv[1],sys.argv[2:] or ['B0','B1','B2','B3'])
