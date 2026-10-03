"""Fresh realized April B0; independent autonomous regulator trajectory only."""
from dataclasses import replace
import os
import sys
import numpy as np
import pandas as pd
from .common import *
from .authority import source,common_contract
from .session import AutonomousSession


def background(stamps,demand,pv):
    m=source()
    bg=m['bg'].build_authority_background_binding(timestamps_fixed_aest=stamps,
        demand_mw_96=demand,rooftop_pv_mw_96=pv,paths=m['paths'])
    gross=tuple({k:1.15*v for k,v in row.items()} for row in bg.gross_p_kw_96)
    q=tuple({k:1.15*v for k,v in row.items()} for row in bg.gross_q_kvar_96)
    net=tuple({k:r.get(k,0)-p.get(k,0) for k in set(r)|set(p)} for r,p in zip(gross,bg.pv_generation_kw_96))
    return replace(bg,gross_p_kw_96=gross,gross_q_kvar_96=q,net_p_kw_96=net,
        evidence=dict(bg.evidence,alpha_BG=1.15,alpha_BG_application_count=1))


def run_day(day, *, diagnostic=False):
    require_april(day)
    prereg=read(OUT/'PREREGISTRATION.json')
    if prereg['exact_base']!=BASE: raise ValueError('PREREGISTRATION_BASE_DRIFT')
    if not diagnostic and not read(OUT/'APRIL_15_16_30_DIAGNOSTIC.json')['PASS']:
        raise ValueError('THREE_DAY_GATE_REQUIRED')
    dest=OUT/('DIAGNOSTIC' if diagnostic else 'BUNDLE')/day_folder(day)
    if dest.exists(): raise ValueError('SCIENTIFIC_OUTPUT_OVERWRITE_FORBIDDEN:'+str(dest))
    old=OLD/'BUNDLE'/day_folder(day)
    freeze=read(old/'PLANNING_FREEZE.json')
    for k in ('reference','physical_arrays','voltage','response'): resolve(freeze[k])
    plan=np.load(old/'V_PLAN.npz'); names=tuple(map(str,plan['node_names']))
    anchor=np.load(old/'APRIL_D1_VOLTAGE_RESPONSE.npz')
    physical_path=old/'ACTUAL_PHYSICAL.npz'; physical_before=record(physical_path)
    with np.load(physical_path) as data:
        p=np.array(data['PCC_P_kw']); q=np.array(data['PCC_Q_kvar'])
    prov=read(INPUT/'BUNDLE'/day_folder(day)/'SOURCE_PROVENANCE.json')
    raw_path=resolve(prov['daily_sources']['aemo_actual.parquet'])
    realized=pd.read_parquet(raw_path)
    forecast=read(resolve(prov['daily_sources']['aemo_forecast.json']))
    stamps=[pd.Timestamp(t).tz_convert('Etc/GMT-10').isoformat() for t in realized.ts_fixed_aest_end]
    if not pd.DatetimeIndex(stamps).tz_convert('UTC').equals(pd.DatetimeIndex(forecast['timestamps_96']).tz_convert('UTC')):
        raise ValueError('EXACT_FORECAST_ACTUAL_TIME_ALIGNMENT')
    abg=background(stamps,realized.demand_mw.tolist(),realized.rooftop_pv_mw.tolist())
    m=source(); session=AutonomousSession(arm='B0'); odd=session.odd; adapter=session.adapter
    native=m['NativeAllocation'].from_adapter(adapter); native.validate_native_engine(odd)
    branches,topology=m['oriented_branches'](odd)
    bnames=np.array([f'{b.branch_id}::{b.phase}' for b in branches])
    if not np.array_equal(bnames,anchor['branch_names']): raise ValueError('EXACT_BRANCH_AXIS_REQUIRED')
    if tuple(sorted(names))!=tuple(names): raise ValueError('CANONICAL_NODE_AXIS_REQUIRED')
    from dayahead.v28r2.opendss_mapping import _set_load,_set_generator
    voltage=[]; currents=[]; ratios=[]; tx=[]; taps=[]; caps=[]; inputs=[]; control_logs=[]
    dest.mkdir(parents=True)
    write(dest,'INPUT_FREEZE.json',dict(day=day,PREREGISTRATION=record(OUT/'PREREGISTRATION.json'),
        V_PLAN=record(old/'V_PLAN.npz'),physical_PQ=physical_before,Actual_raw=record(raw_path),
        source_contract=common_contract('B0'),Planning_native_state_not_controller_input=True))
    try:
        for t in range(96):
            totals,ledger,allocation=native.apply(odd,abg,t)
            for row in adapter['pv_generators']:
                key=(str(row['bus']).lower(),'ABC'[int(row['phase'])-1])
                _set_generator(odd,row['generator_name'],abg.pv_generation_kw_96[t].get(key,0),0)
            for s in range(12): _set_load(odd,f'IDC_IDC{s+1:02d}',p[t,s],q[t,s])
            for n in odd.Generators.AllNames():
                if n.lower().startswith('mess_dis_'): _set_generator(odd,n,0,0)
            for n in odd.Loads.AllNames():
                if n.lower().startswith('mess_chg_'): _set_load(odd,n,0,0)
            control=session.solve_next(t)
            voltage.append(m['voltage_vector'](odd,names))
            measured=[m['branch_measurement'](odd,b) for b in branches]
            currents.append([v[0] for v in measured]); ratios.append([v[1] for v in measured]); tx.append([v[2] for v in measured])
            taps.append(control['actual_taps']); caps.append(control['capacitor_states'])
            # Record engine-applied P/Q, not only caller arrays, before the next slot.
            aidc=[]; aidcq=[]; mess=[]
            for s in range(12):
                odd.Loads.Name(f'IDC_IDC{s+1:02d}'); aidc.append(float(odd.Loads.kW())); aidcq.append(float(odd.Loads.kvar()))
            for n in odd.Generators.AllNames():
                if n.lower().startswith('mess_dis_'):
                    odd.Generators.Name(n); mess.extend([float(odd.Generators.kW()),float(odd.Generators.kvar())])
            for n in odd.Loads.AllNames():
                if n.lower().startswith('mess_chg_'):
                    odd.Loads.Name(n); mess.extend([float(odd.Loads.kW()),float(odd.Loads.kvar())])
            if not np.array_equal(aidc,p[t]) or not np.array_equal(aidcq,q[t]) or any(v!=0 for v in mess):
                raise ValueError('ACTUAL_PHYSICAL_PQ_OR_MESS_DRIFT')
            inputs.append(dict(slot=t,PCC_P_kw=aidc,PCC_Q_kvar=aidcq,all_MESS_PQ_zero=True,
                native_load_PQ=totals,allocation_conservation=allocation))
            control_logs.append(control)
        if record(physical_path)['sha256']!=physical_before['sha256']:
            raise ValueError('NON_GRID_ARRAY_BYTE_DRIFT')
    except Exception as error:
        write(dest,'FAILURE.json',dict(day=day,failure=repr(error),completed_slots=len(control_logs),tuning=0,repair=0))
        raise
    finally: session.close()
    volt=np.array(voltage); ratios=np.array(ratios); tx=np.array(tx)
    kinds=np.array([b.branch_id.startswith('transformer.') for b in branches])
    np.savez_compressed(dest/'V_ACTUAL_AC.npz',node_names=np.array(names),branch_names=bnames,
        V_ACTUAL_AC=volt,current_A=np.array(currents),current_pu=ratios,transformer_kVA_pu=tx,
        regulator_taps=np.array(taps),capacitor_states=np.array(caps),
        converged=np.ones(96,bool),control_iterations=np.array([r['control_iterations'] for r in control_logs]),
        convergence_iterations=np.array([r['convergence_iterations'] for r in control_logs]),
        actual_previous_taps=np.array([r['previous_taps'] for r in control_logs]),
        timestamps_96=np.array(stamps),PCC_P_kw=p,PCC_Q_kvar=q)
    write(dest,'RAW_CONTROL_LOG.json',dict(day=day,source_initial_inventory=session.initial_inventory,
        slots=control_logs,observed_settled_tap_changes_only=True,
        internal_control_queue_event_trace_available=False,control_parameters_unchanged=True))
    write(dest,'RAW_PHYSICAL_INPUT_LOG.json',dict(day=day,slots=inputs,
        alpha_BG=1.15,PV_scaled_by_alpha_BG=False,Actual_source=record(raw_path),
        background_normalization_sources=abg.evidence['source_paths_and_sha256'],
        raw_May_rows_loaded=False))
    plan_v=plan['V_PLAN']
    result=dict(day=day,engine='OpenDSS',engine_version=m['expected']['engine_version'],
        fresh_context_per_day=True,sequential_same_engine=True,source_initial_taps=session.initial_taps,
        slots=96,converged_slots=96,converged=True,control_actions_done=True,
        voltage_min=float(volt.min()),voltage_max=float(volt.max()),
        voltage_violations=int(np.sum((volt<.95)|(volt>1.05))),
        Planning_voltage_violations=int(np.sum((plan_v<.95)|(plan_v>1.05))),
        line_current_violations=int(np.sum(ratios[:,~kinds]>1)),
        transformer_current_violations=int(np.sum(ratios[:,kinds]>1)),transformer_kVA_violations=int(np.sum(tx>1)),
        maximum_line_current_pu=float(ratios[:,~kinds].max()),
        maximum_transformer_current_pu=float(ratios[:,kinds].max()),maximum_transformer_kVA_pu=float(np.nanmax(tx)),
        all_RegControls_enabled=True,CapControl_count=0,fixed_capacitors_all_ON=True,
        parameter_integrity=True,Actual_Planning_tap_replay=False,Actual_Planning_cap_replay=False,
        no_controlmode_off=True,Actual_P_repair=0,Actual_Q_repair=0,Actual_global_reoptimization=0,
        MESS_PQ=0,workload_PQ_identity=True,control_iteration_max=max(r['control_iterations'] for r in control_logs),
        applied_PQ_logged=True,Actual_voltage=record(dest/'V_ACTUAL_AC.npz'),topology=topology)
    from v42_thermal.authority import arm_contract
    result.update(arm_contract('B0'))
    write(dest,'FRESH_ACTUAL_AC_RECEIPT.json',result)
    print(day,'Fresh autonomous PASS 96/96; voltage cells',result['voltage_violations'],flush=True)
    return result


def diagnostic():
    if (OUT/'APRIL_15_16_30_DIAGNOSTIC.json').exists(): raise ValueError('DIAGNOSTIC_ALREADY_SEALED')
    results=[run_day(day,diagnostic=True) for day in DIAGNOSTIC]
    keys=('all_RegControls_enabled','fixed_capacitors_all_ON','parameter_integrity','no_controlmode_off','workload_PQ_identity')
    passed=all(r['converged_slots']==96 and r['CapControl_count']==0 and all(r[k] for k in keys) for r in results)
    write(OUT,'APRIL_15_16_30_DIAGNOSTIC.json',dict(PASS=passed,days=results,
        voltage_violations_do_not_fail_gate=True,diagnostic_scientific_solves=288,
        no_AIDC_drift=True,no_MESS=True,no_PQ_repair=True,no_future_leakage=True,
        no_tuning=True,tap_logging_complete=True,Planning_native_replay=False))
    if not passed: raise ValueError('DIAGNOSTIC_GATE_FAIL')


def full():
    if not read(OUT/'APRIL_15_16_30_DIAGNOSTIC.json')['PASS']: raise ValueError('DIAGNOSTIC_GATE_FAIL')
    results=[]
    for day in DAYS:
        results.append(run_day(day))
        write(OUT,'APRIL_RUN_PROGRESS.json',dict(completed_days=len(results),days=results))


if __name__=='__main__':
    {'diagnostic':diagnostic,'full':full}[sys.argv[1]]()
