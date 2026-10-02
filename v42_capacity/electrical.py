"""April-bound current affine voltage producer and fresh Actual AC adapter.

The current all-node response is v2_anchor + H*(control-control_anchor).
For frozen B0, all controls equal its newly generated April reference anchor.
No May coefficient/cache or historical workload decisions enter this adapter.
"""
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
import os
import sys
import numpy as np
import pandas as pd
from .common import *

CODE_ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')


def imports():
    sys.path.insert(0,str(CODE_ROOT))
    from dayahead import grid_background_v16_2 as bg
    from dayahead.run_authority_semantic_g11_v16_2 import _default_background_paths
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    from dayahead.run_v16_3_voltage_candidate import _anchor_and_sensitivity_day
    from dayahead.v40e.mapping import NativeAllocation,corrected_mapping
    from dayahead.v28r2.opendss_mapping import FeederAssets,compile_clean_engine,_set_generator,_set_load,apply_frozen_native_state
    from dayahead.v28r2.opendss_backend import _voltage_vector,_branch_measurement,_native_state
    return locals()


@lru_cache(maxsize=1)
def authority():
    p=read(PRIOR/'BUNDLE/DAY_20250401/PLANNING_INPUT_BUNDLE.json')
    meta=p['network_authority']['static_input_metadata']
    master=resolve(meta['OpenDSS_master']); pcc=resolve(meta['PCC_mapping'])
    source=master.parents[1]
    assets=imports()['FeederAssets'](master,source/'opendss_assets/Generated_Planning_Line_Ratings_u080.dss',
        source/'power_v70_p4f_contract/Generated_PhasePV.dss',source/'power_v70_p4f_contract/opendss_runtime_adapter.json',
        source/'power_v70_p4f_contract/service_node_electrical_mapping_v1.csv',pcc)
    assets.validate()
    raw_repo=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend')
    paths=imports()['_default_background_paths'](raw_repo,source)
    # Verify the current static normalization, topology and original source code
    # before creating coefficients. pv_reference is hashed only; its May rows are never loaded.
    static=[record(v) for v in vars(assets).values()]+[record(v) for v in vars(paths).values()]
    code_names=['grid_background_v16_2.py','full_ieee123_g11_v16_1.py','run_v16_3_voltage_candidate.py',
        'v40e/mapping.py','v28r2/opendss_mapping.py','v28r2/opendss_backend.py']
    code=[record(CODE_ROOT/'dayahead'/n) for n in code_names]
    lineage=read(ROOT/'docs/v42_april_port_from_may_pipeline/MAY_PIPELINE/MAY_V42_PIPELINE_MANIFEST.json')
    expected={r['path']:r['sha256'] for stage in lineage['pipeline_stages'] for r in stage.get('code',[])}
    for r in code:
        if r['path'] in expected and expected[r['path']]!=r['sha256']: raise ValueError('CURRENT_CODE_SOURCE_DRIFT')
    write(OUT,'ELECTRICAL_SOURCE_AUTHORITY.json',dict(static_sources=static,code_sources=code,
        alpha_BG=1.15,alpha_BG_application_count=1,PV_scaled_by_alpha_BG=False,
        planning_equation='v_squared_anchor + H * (controls - anchor_controls)',
        B0_controls_equal_new_April_anchor=True,May_numeric_coefficients_used=False,
        old_electrical_cache_reused=False,actual_native_states='frozen per-slot April Planning regulator/capacitor settings',
        topology_not_reduced=True,grid_rescaling=False,primary_voltage_band=[.95,1.05]))
    return source,pcc,assets,paths


def background(stamps,demand,pv):
    m=imports(); source,pcc,assets,paths=authority()
    bg=m['bg'].build_authority_background_binding(timestamps_fixed_aest=stamps,demand_mw_96=demand,
        rooftop_pv_mw_96=pv,paths=paths)
    gross=tuple({k:1.15*v for k,v in row.items()} for row in bg.gross_p_kw_96)
    q=tuple({k:1.15*v for k,v in row.items()} for row in bg.gross_q_kvar_96)
    net=tuple({k:r.get(k,0)-p.get(k,0) for k in set(r)|set(p)} for r,p in zip(gross,bg.pv_generation_kw_96))
    return replace(bg,gross_p_kw_96=gross,gross_q_kvar_96=q,net_p_kw_96=net,
        evidence=dict(bg.evidence,alpha_BG=1.15,alpha_BG_application_count=1))


def generate(day):
    m=imports(); source,pcc,assets,paths=authority(); folder=day_folder(day)
    prior=PRIOR/'BUNDLE'/folder; dest=OUT/'BUNDLE'/folder
    prov=read(prior/'SOURCE_PROVENANCE.json')
    forecast=read(resolve(prov['daily_sources']['aemo_forecast.json']))
    plan=np.load(dest/'PLANNING_PHYSICAL.npz'); pq=plan['PCC_P_kw']
    bg=background(forecast['timestamps_96'],forecast['demand_mw_96'],forecast['pv_mw_96'])
    previous=Path.cwd()
    try:
        binding=m['build_full_grid_binding'](assets=source/'opendss_assets',contract=source/'power_v70_p4f_contract',
            demand_mw_96=forecast['demand_mw_96'],rooftop_pv_mw_96=forecast['pv_mw_96'],aidc_plan_kw_96x12=pq,
            pcc_asset=pcc,background_binding=bg)
        # The original anchor constructor accepts a repository only to find PCC.
        # Resolve that static exact source without a policy wrapper or May cache.
        anchor_path=dest/'APRIL_D1_VOLTAGE_RESPONSE.npz'
        with m['corrected_mapping']():
            m['_anchor_and_sensitivity_day'](pcc.parents[3],source,bg,pq.tolist(),binding,day,anchor_path,True)
    finally: os.chdir(previous)
    anchor=np.load(anchor_path); names=tuple(map(str,anchor['node_names']))
    controls=np.zeros_like(anchor['anchor_control']); controls[:,:12]=pq
    v2=anchor['anchor_v_squared']+np.einsum('tc,tcn->tn',controls-anchor['anchor_control'],anchor['sensitivity'])
    if not np.array_equal(controls,anchor['anchor_control']): raise ValueError('B0_REFERENCE_ANCHOR_DRIFT')
    # Materialize the linear-model constant so the Planning quantity is explicit.
    constant=anchor['anchor_v_squared']-np.einsum('tc,tcn->tn',anchor['anchor_control'],anchor['sensitivity'])
    reconstructed=constant+np.einsum('tc,tcn->tn',controls,anchor['sensitivity'])
    assert np.allclose(v2,reconstructed,atol=1e-12,rtol=0)
    np.savez_compressed(dest/'V_PLAN.npz',node_names=anchor['node_names'],V_squared=v2,V_PLAN=np.sqrt(v2),
        voltage_constant=constant,primary_band=np.array([.95,1.05]))
    write(OUT,'BUNDLE/'+folder+'/PLANNING_FREEZE.json',dict(day=day,reference=record(dest/'REFERENCE.json'),
        physical_arrays=record(dest/'PLANNING_PHYSICAL.npz'),voltage=record(dest/'V_PLAN.npz'),
        response=record(anchor_path),plan_representation='squared_pu converted with sqrt',
        no_Actual_read=True,Actual_PQ_repair=0,optimizer_calls=0,DA_AC_operational_stage=False))
    # This freeze must precede opening any Actual electrical inputs.
    import subprocess
    subprocess.run([sys.executable,'-X','utf8','-m','v42_capacity.replay','--day',day],cwd=ROOT,check=True)
    actual=np.load(dest/'ACTUAL_PHYSICAL.npz'); realized=pd.read_parquet(resolve(prov['daily_sources']['aemo_actual.parquet']))
    timestamps=[pd.Timestamp(t).tz_convert('Etc/GMT-10').isoformat() for t in realized.ts_fixed_aest_end]
    if not pd.DatetimeIndex(forecast['timestamps_96']).tz_convert('UTC').equals(pd.DatetimeIndex(timestamps).tz_convert('UTC')):
        raise ValueError('EXACT_FORECAST_ACTUAL_INTERVAL_END_ALIGNMENT')
    abg=background(timestamps,realized.demand_mw.tolist(),realized.rooftop_pv_mw.tolist())
    previous=Path.cwd()
    try:
        odd,adapter=m['compile_clean_engine'](assets)
        native=m['NativeAllocation'].from_adapter(adapter)
        native.validate_native_engine(odd)
        volt=[]; currents=[]; ratios=[]; tx=[]; converged=[]; taps=[]; caps=[]
        for t in range(96):
            native.apply(odd,abg,t)
            for row in adapter['pv_generators']:
                key=(str(row['bus']).lower(),'ABC'[int(row['phase'])-1])
                m['_set_generator'](odd,row['generator_name'],abg.pv_generation_kw_96[t].get(key,0),0)
            for s in range(12): m['_set_load'](odd,f'IDC_IDC{s+1:02d}',actual['PCC_P_kw'][t,s],actual['PCC_Q_kvar'][t,s])
            for n in odd.Generators.AllNames():
                if n.lower().startswith('mess_dis_'): m['_set_generator'](odd,n,0,0)
            for n in odd.Loads.AllNames():
                if n.lower().startswith('mess_chg_'): m['_set_load'](odd,n,0,0)
            m['apply_frozen_native_state'](odd,anchor,t)
            odd.Solution.SolveSnap(); converged.append(bool(odd.Solution.Converged()))
            volt.append(m['_voltage_vector'](odd,names))
            measurements=[m['_branch_measurement'](odd,b) for b in binding.factories[0].data.branches]
            currents.append([x[0] for x in measurements]); ratios.append([x[1] for x in measurements]); tx.append([x[2] for x in measurements])
            tap,cap=m['_native_state'](odd); taps.append(tap); caps.append(cap)
        version=odd.Basic.Version(); odd.Basic.ClearAll()
    finally: os.chdir(previous)
    volt=np.array(volt); ratios=np.array(ratios); tx=np.array(tx)
    branches=binding.factories[0].data.branches; kinds=np.array([b.branch_id.startswith('transformer.') for b in branches])
    np.savez_compressed(dest/'V_ACTUAL_AC.npz',node_names=np.array(names),V_ACTUAL_AC=volt,
        branch_names=anchor['branch_names'],current_A=np.array(currents),current_pu=ratios,transformer_kVA_pu=tx,
        converged=np.array(converged),regulator_taps=np.array(taps),capacitor_states=np.array(caps))
    result=dict(day=day,engine='OpenDSS',engine_version=version,fresh_run=True,synthetic=False,slots=96,
        converged_slots=sum(converged),converged=all(converged),voltage_min=float(volt.min()),voltage_max=float(volt.max()),
        Planning_voltage_min=float(np.sqrt(v2).min()),Planning_voltage_max=float(np.sqrt(v2).max()),
        voltage_violations=int(np.sum((volt<.95)|(volt>1.05))),
        Planning_voltage_violations=int(np.sum((v2<.95**2)|(v2>1.05**2))),
        line_current_violations=int(np.sum(ratios[:,~kinds]>1)),transformer_current_violations=int(np.sum(ratios[:,kinds]>1)),
        transformer_kVA_violations=int(np.sum(tx>1)),maximum_line_current_pu=float(ratios[:,~kinds].max()),
        maximum_transformer_current_pu=float(ratios[:,kinds].max()),maximum_transformer_kVA_pu=float(np.nanmax(tx)),
        Actual_PQ_repair=0,Actual_grid_aware_schedule_repair=False,Actual_global_reoptimization=0,MESS_P=0,MESS_Q=0,
        alpha_BG=1.15,Actual_capacity_admission_queue=True,Planning_response=record(anchor_path),Actual_voltage=record(dest/'V_ACTUAL_AC.npz'))
    write(OUT,'BUNDLE/'+folder+'/FRESH_ACTUAL_AC_RECEIPT.json',result)
    return result


def main():
    gate=read(OUT/'HEAVY_EXECUTION_GATE.json')
    if not gate['PASS']: raise ValueError('HEAVY_EXECUTION_GATE_REQUIRED')
    results=[]
    for d in range(1,31):
        day=f'2025-04-{d:02d}'; print('GENERATE April Planning response + Fresh Actual',day,flush=True)
        results.append(generate(day)); print('SEALED',day,results[-1]['voltage_min'],results[-1]['voltage_max'],flush=True)
        write(OUT,'APRIL_FRESH_AC_PROGRESS.json',dict(days=results,completed_days=len(results)))


if __name__=='__main__': main()
