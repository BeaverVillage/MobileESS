"""Reconstruct electrical reporting from individual solver P/Q, without repair."""
import shutil
import numpy as np
from v42_root.common import *
from .build import inputs
from v42_native.mess import validate
from v42_bootstrap.grid import grid_report
from v42_bootstrap.attribution import supplemental_physical,analyze
def controls_from_plan(plan,anchor):
    vv=plan['values'];units=plan['initial_sites'];rows=[]
    for t in range(96):
        row=[]
        for i,name in enumerate(anchor['control_names']):
            site=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):row.append(float(anchor['controls'][t][i]))
            elif name.startswith('mess_p_kw'):row.append(sum(vv[f'Pdis[{u},{site},{t}]']-vv[f'Pch[{u},{site},{t}]'] for u in units))
            elif name.startswith('mess_q_kvar'):row.append(sum(vv[f'Q[{u},{site},{t}]'] for u in units))
            else:raise ValueError(name)
        rows.append(row)
    return rows
def run():
    bundle,anchor,prior,sites,initial,routes,battery=inputs()
    old=read(LOCAL/'PR106_M1_CONTROLS.json');reconstructed=controls_from_plan(prior,anchor)
    old_delta=float(np.max(np.abs(np.array(old)-reconstructed)));assert old_delta<=1e-5
    prior_grid=grid_report(bundle,reconstructed,prior['values']['rho_max']);assert prior_grid['PASS']
    receipt=read(OUT/'PR106_M1_INCUMBENT_RECEIPT.json');receipt.update(controls_reconstructed_from_individual_PQ=True,control_reconstruction_max_delta=old_delta,reconstructed_grid=prior_grid);dump('PR106_M1_INCUMBENT_RECEIPT.json',receipt)
    plan=read(LOCAL/'M1/FINAL_PLAN.json');native_controls=read(LOCAL/'M1/CONTROLS.json');physical_controls=controls_from_plan(plan,anchor)
    delta=float(np.max(np.abs(np.array(native_controls)-physical_controls)))
    # A numerical equality residual is audited, never repaired in the plan.
    physical=validate(plan,sites,routes,battery,96);extra=supplemental_physical(plan,sites,battery);grid=grid_report(bundle,physical_controls,plan['values']['rho_max'])
    initial_pass=all(abs(plan['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)
    physical.update(extra,initial_SOC_PASS=initial_pass,grid_PASS=grid['PASS'],individual_PQ_controls_reconstructed=True,injection_equality_max_residual=delta,AIDC_anchor_unchanged=True)
    physical['PASS']=physical['PASS'] and extra['charge_mode_and_connection_PASS'] and initial_pass and grid['PASS'] and delta<=1e-5
    grid.update(individual_PQ_controls_reconstructed=True,injection_equality_max_residual=delta,no_PQ_or_route_or_SOC_repair=True)
    shutil.copyfile(LOCAL/'M1/CONTROLS.json',LOCAL/'M1/CONTROLS_NATIVE_AUX.json');atomic(LOCAL/'M1/CONTROLS.json',physical_controls)
    shutil.copyfile(OUT/'M1_OPTIMIZATION.json',OUT/'M1_OPTIMIZATION_NATIVE_RAW.json');shutil.copyfile(OUT/'M1_ROBUST_VOLTAGE_REPORT.json',OUT/'M1_ROBUST_VOLTAGE_NATIVE_AUX_REPORT.json')
    dump('M1_PHYSICAL_VALIDATION.json',physical);dump('M1_ROBUST_VOLTAGE_REPORT.json',grid)
    opt=read(OUT/'M1_OPTIMIZATION.json');opt.update(physical_PASS=physical['PASS'],robust_grid_PASS=grid['PASS'],accepted=opt['complete'] and physical['PASS'] and grid['PASS'],post_run_PQ_reconstruction_only=True,PQ_plan_values_changed=False)
    dump('M1_OPTIMIZATION.json',opt)
    analyze(bundle,anchor,plan,sites,routes,battery)
    block=read(OUT/'PR105_BLOCKER_M1_RESOLUTION.json');block.update(M1_ACCEPTED=opt['accepted'],PR106_incumbent_voltage_pu=1.0407128548060747,no_PQ_repair=True);dump('PR105_BLOCKER_FINAL_CHECK.json',block)
    dump('PHYSICAL_CONTROL_RECONSTRUCTION_RECEIPT.json',dict(PASS=delta<=1e-5,PR106_prior_delta=old_delta,new_injection_equality_max_residual=delta,plan_sha256=sha(LOCAL/'M1/FINAL_PLAN.json'),native_aux_control_sha256=sha(LOCAL/'M1/CONTROLS_NATIVE_AUX.json'),physical_control_sha256=sha(LOCAL/'M1/CONTROLS.json'),solver_PQ_route_SOC_unchanged=True,repair=False,optimize_calls=0))
    print('POST VALIDATION',physical['PASS'],grid['PASS'],delta,flush=True)
if __name__=='__main__':run()
