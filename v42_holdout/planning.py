"""Exact inherited Planning anchor/sensitivity equations, new May inputs only."""
import os
import sys
import numpy as np
from .common import *
from v42_regcontrol.authority import source,compile_verified,assert_inventory
from v42_regcontrol.runner import background
from v42_thermal.authority import arm_contract

def generate(day):
    require_may(day); dest=destination(day)
    if (dest/'PLANNING_FREEZE.json').exists(): raise ValueError('SEALED_PLAN_OVERWRITE_FORBIDDEN')
    m=source(); assets=m['assets']; native_source=assets.master.parents[1]
    pcc=assets.pcc
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    from dayahead.run_v16_3_voltage_candidate import _anchor_and_sensitivity_day
    from dayahead.v40e.mapping import corrected_mapping
    plan_path=dest/'PLANNING_PHYSICAL.npz'; plan=np.load(plan_path); pq=plan['PCC_P_kw']
    f=read(RAW/day/'aemo_forecast.json')
    bg=background(f['timestamps_96'],f['demand_mw_96'],f['pv_mw_96'])
    previous=Path.cwd()
    odd,_,before=compile_verified(); odd.Basic.ClearAll()
    try:
        binding=build_full_grid_binding(assets=native_source/'opendss_assets',contract=native_source/'power_v70_p4f_contract',
            demand_mw_96=f['demand_mw_96'],rooftop_pv_mw_96=f['pv_mw_96'],aidc_plan_kw_96x12=pq,
            pcc_asset=pcc,background_binding=bg)
        anchor_path=dest/'MAY_D1_VOLTAGE_RESPONSE.npz'
        with corrected_mapping():
            _anchor_and_sensitivity_day(pcc.parents[3],native_source,bg,pq.tolist(),binding,day,anchor_path,True)
    finally: os.chdir(previous)
    anchor=np.load(anchor_path); controls=np.zeros_like(anchor['anchor_control']); controls[:,:12]=pq
    if not np.array_equal(controls,anchor['anchor_control']): raise ValueError('B0_REFERENCE_ANCHOR_DRIFT')
    v2=anchor['anchor_v_squared']+np.einsum('tc,tcn->tn',controls-anchor['anchor_control'],anchor['sensitivity'])
    constant=anchor['anchor_v_squared']-np.einsum('tc,tcn->tn',anchor['anchor_control'],anchor['sensitivity'])
    reconstructed=constant+np.einsum('tc,tcn->tn',controls,anchor['sensitivity'])
    if not np.allclose(v2,reconstructed,atol=1e-12,rtol=0): raise ValueError('AFFINE_EQUATION_DRIFT')
    if not np.all(anchor['capacitor_states']==1): raise ValueError('PLANNING_FIXED_CAP_STATE_DRIFT')
    np.savez_compressed(dest/'V_PLAN.npz',node_names=anchor['node_names'],V_squared=v2,V_PLAN=np.sqrt(v2),
        voltage_constant=constant,primary_band=np.array([.95,1.05]))
    odd,_,after=compile_verified(); odd.Basic.ClearAll()
    if before!=after: raise ValueError('PLANNING_SOURCE_PARAMETER_DRIFT')
    write(dest,'PLANNING_FREEZE.json',dict(day=day,reference=record(dest/'REFERENCE.json'),physical_arrays=record(plan_path),
        voltage=record(dest/'V_PLAN.npz'),response=record(anchor_path),planning_input=record(INPUT/'BUNDLE'/day_folder(day)/'PLANNING_INPUT_BUNDLE.json'),
        coefficients=record(INPUT/'BUNDLE'/day_folder(day)/'C1_PLANNING_COEFFICIENTS.csv'),
        plan_representation='squared_pu converted with sqrt',primary_band=[.95,1.05],margin_pu=0,
        same_affine_equation_as_PR125=True,no_Actual_read=True,Actual_PQ_repair=0,optimizer_calls=0,
        source_parameter_integrity=True,source_before=before,source_after=after,
        native_RegControls_autonomous_per_slot=True,FD_tap_fixed_only_for_local_derivatives=True,
        capacitors_fixed_ON=True,CapControl_count=0,freeze_before_Actual_truth=True,**arm_contract('B0')))
    print(day,'Planning freeze; Vmin/Vmax',float(np.sqrt(v2).min()),float(np.sqrt(v2).max()),flush=True)

def main():
    source_freeze(); results=[]
    for day in DAYS:
        generate(day); results.append(record(destination(day)/'PLANNING_FREEZE.json'))
        write(OUT,'PLANNING_PROGRESS.json',dict(completed_days=len(results),freezes=results))
    write(OUT,'ALL_MAY_PLANNING_FROZEN.json',dict(PASS=True,days=DAYS,freezes=results,
        Actual_truth_loaded=False,Actual_electrical_outcomes_read=False,Actual_weather_values_read=False))

if __name__=='__main__': main()
