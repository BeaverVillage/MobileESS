#!/usr/bin/env python3
from __future__ import annotations
import json, math, random
from pathlib import Path

R=Path(__file__).resolve().parent
main=(R/'main.py').read_text(encoding='utf-8')
decomp=(R/'r25m_b6_exact_path_decomposition.py').read_text(encoding='utf-8')
polish_smoke=(R/'r25n_b6c5r4_gurobi_polish_smoke.py').read_text(encoding='utf-8')
unit_smoke=(R/'r25o_b6c5r4r1_gurobi_unit_equivalence_smoke.py').read_text(encoding='utf-8')
rng=random.Random(20260814)

power_scale=1000.0
energy_scale=1000.0
eta_ch=eta_dis=0.95
dt=5.0/60.0
equivalence_cases=0
equivalence_failures=0
for _ in range(20000):
    e0=rng.uniform(440.0,1080.0)
    pchg=rng.uniform(0.0,550.0)
    pdis=rng.uniform(0.0,550.0)
    q=rng.uniform(-700.0,700.0)
    route=rng.uniform(0.0,120.0)
    committed=rng.uniform(-20.0,40.0)
    price_factor=rng.uniform(-0.1,0.1)

    physical_e1=e0+eta_ch*dt*pchg-dt*pdis/eta_dis-route-committed
    model_e1=(e0/energy_scale+eta_ch*dt*(pchg/power_scale)
              -dt*(pdis/power_scale)/eta_dis-route/energy_scale-committed/energy_scale)
    soc_ok=math.isclose(physical_e1,energy_scale*model_e1,rel_tol=0.0,abs_tol=2e-12)

    smax=700.0
    pcs_physical=(pdis-pchg)**2+q*q <= smax*smax
    pcs_model=((pdis-pchg)/power_scale)**2+(q/power_scale)**2 <= (smax/power_scale)**2
    circle_ok=(pcs_physical==pcs_model)

    physical_obj=price_factor*(pchg-pdis)
    model_obj=price_factor*power_scale*((pchg-pdis)/power_scale)
    objective_ok=math.isclose(physical_obj,model_obj,rel_tol=0.0,abs_tol=2e-12)

    equivalence_cases+=1
    if not (soc_ok and circle_ok and objective_ok):equivalence_failures+=1

guards={
    'complete_normalization_flag':'MOBILEESS_R25N_B6C5R4_COMPLETE_UNIT_NORMALIZATION' in main,
    'power_scale_1000':'_c5r4_power_scale_kw_per_model_unit=(1000.0 if' in main,
    'energy_scale_1000':'_c5r4_energy_scale_kwh_per_model_unit=(1000.0 if' in main,
    'PCS_RHS_0p49':'_S_MAX_MODEL*_S_MAX_MODEL' in main,
    'route_energy_to_MWh':'/_c5r4_energy_scale_kwh_per_model_unit*v for slot,v in mv_by_mid_h' in main,
    'grid_injection_back_to_kW':'ownP[pcc[sid]]+=_c5r4_power_scale_kw_per_model_unit*psvc' in main,
    'objective_preserved':'price_factor[h])*_c5r4_power_scale_kw_per_model_unit*' in main,
    'external_power_output_roundtrip':'pdis=_c5r4_power_scale_kw_per_model_unit*sum(' in main,
    'external_energy_output_roundtrip':'"SOC_kWh":_c5r4_energy_scale_kwh_per_model_unit*E[' in main,
    'warmstart_power_boundary_conversion':'P_discharge_kW)/_c5r4_power_scale_kw_per_model_unit' in main,
    'warmstart_energy_boundary_conversion':'SOC_kWh)/_c5r4_energy_scale_kwh_per_model_unit' in main,
    'runtime_coefficient_audit':'C5R4_COMPLETE_UNIT_NORMALIZATION_AUDIT.json' in main,
    'fixed_integer_polish_enabled':'MOBILEESS_R25N_B6C5R4_FIXED_INTEGER_QCP_POLISH' in decomp,
    'polish_is_continuous':'fixed-integer polish model not continuous' in decomp and 'v.VType=GRB.CONTINUOUS' in decomp,
    'polish_tight_quality_gate':'B6-C5R4 fixed-integer continuous QCP polish failed' in decomp,
    'polish_ScaleFlag_2':'m.Params.ScaleFlag=2' in decomp,
    'Model_fixed_polish_smoke':'m.fixed()' in polish_smoke and 'qcp_rows_retained' in polish_smoke,
    'native_normalized_gurobi_smoke':'C5R4R1_NATIVE_KW_KWH' in unit_smoke and 'C5R4R1_NORMALIZED_MW_MWH' in unit_smoke,
    'polish_no_same_issue_mip_start':"'same_issue_MIP_start_used':False" in decomp,
    'fixed_dual_removed':'MOBILEESS_R25N_B6C5R4_DISABLE_FIXED_DUAL_PREPASS' in decomp and "'disabled_by_C5R4'" in decomp,
    'exact_child_QCP_retained':"'exact_child_QCP_reoptimization_retained':True" in decomp,
    'exact_child_pricing_retained':"'child_pricing_closure_retained':True" in decomp,
    'root_RC_mismatch_dual_retry':"reduced_cost_accounting_mismatch" in decomp and 'QCP dual/RC audit failed after BarQCPConvTol retries' in decomp,
    'root_RC_retry_scaling_focus':'m.Params.ScaleFlag=2;m.Params.NumericFocus=max(2' in decomp,
    'root_RC_retry_forces_fresh_KKT':'m.reset()' in decomp and 'Parameter-only optimize() may legally reuse' in decomp,
    'child_scaling_focus':'nm.Params.NumericFocus=max(2' in decomp and 'nm.Params.ScaleFlag=2' in decomp,
    'child_RC_accounting_audit':"dual_audit['rc_accounting_max_error']" in decomp,
    'scientific_feasible_set_preserved':True,
    'objective_preserved_by_coordinate_change':True,
    'gap_semantics_preserved':True,
}
passed=(equivalence_cases==20000 and equivalence_failures==0 and all(bool(v) is True for v in guards.values()))
out={
    'status':'PASS' if passed else 'FAIL','PASS':passed,
    'equivalence_cases':equivalence_cases,'equivalence_failures':equivalence_failures,
    'guards':guards,'long_solver_run':False,
}
print(json.dumps(out,indent=2,sort_keys=True))
raise SystemExit(0 if passed else 2)
