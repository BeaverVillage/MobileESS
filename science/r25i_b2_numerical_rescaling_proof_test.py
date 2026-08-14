#!/usr/bin/env python3
from pathlib import Path
import ast, io, json, math, random, tarfile, tempfile
import numpy as np

R=Path(__file__).resolve().parent
MAIN=R/'main.py'
S=MAIN.read_text()
ast.parse(S)
SCALE=1000.0
checks={}
checks['flag_present']='MOBILEESS_R25I_B2_NUMERICAL_RESCALING' in S
checks['requires_b1']='R25I B2 exact numerical rescaling requires frozen R25H B1 certificate-focused foundation' in S
checks['flow_scale_1000']='(1000.0 if r25i_b2_numerical_rescaling else 1.0)' in S
checks['balance_scaled']='(ownP[n]+float(_cp))/_r25i_flow_scale_kw_per_model_unit' in S and '(ownQ[n]+float(_cq))/_r25i_flow_scale_kw_per_model_unit' in S
checks['voltage_coeff_scaled']='_r25i_voltage_flow_coeff=(0.002*_r25i_flow_scale_kw_per_model_unit)' in S
checks['reference_flow_scaled']='float(refFP[n])/_r25i_flow_scale_kw_per_model_unit' in S and 'float(refFQ[n])/_r25i_flow_scale_kw_per_model_unit' in S
checks['thermal_limit_scaled']='float(ll)/_r25i_flow_scale_kw_per_model_unit' in S
checks['runtime_audit']='ConversationA_R25I_B2_EXACT_NUMERICAL_RESCALING_AUDIT.json' in S
checks['external_units_unchanged']='"external_physical_power_units":"kW/kvar"' in S
checks['opendss_units_unchanged']='"Fresh_Exact_OpenDSS_interface_units_changed":False' in S

# Algebraic equivalence over randomized branch-flow/balance cases.
rng=random.Random(2502)
max_balance_err=max_voltage_err=max_thermal_err=0.0
for _ in range(10000):
    own=rng.uniform(-4000,4000); cp=rng.uniform(-4000,4000)
    child=[rng.uniform(-6,6) for _ in range(rng.randrange(0,5))] # model MW
    lhs_mw=(own+cp)/SCALE+sum(child)
    lhs_kw=own+cp+sum(v*SCALE for v in child)
    max_balance_err=max(max_balance_err,abs(lhs_kw/SCALE-lhs_mw))

    r=10**rng.uniform(-6,-1); x=10**rng.uniform(-3,-0.5)
    Pk=rng.uniform(-6000,6000); Qk=rng.uniform(-6000,6000)
    Pref=rng.uniform(-6000,6000); Qref=rng.uniform(-6000,6000)
    pdev=rng.uniform(-20,20)
    du_kw=pdev-0.002*(r*(Pk-Pref)+x*(Qk-Qref))
    du_mw=pdev-(0.002*SCALE)*(r*(Pk/SCALE-Pref/SCALE)+x*(Qk/SCALE-Qref/SCALE))
    max_voltage_err=max(max_voltage_err,abs(du_kw-du_mw))

    lim=rng.uniform(100,6000)
    old=(Pk*Pk+Qk*Qk)/(lim*lim)
    new=((Pk/SCALE)**2+(Qk/SCALE)**2)/((lim/SCALE)**2)
    max_thermal_err=max(max_thermal_err,abs(old-new))

checks['random_balance_equivalence']=max_balance_err < 1e-12
checks['random_voltage_equivalence']=max_voltage_err < 1e-12
checks['random_thermal_circle_equivalence']=max_thermal_err < 1e-12

# Use the frozen actual BUILD7AR2 coefficient artifact to quantify the known tiny grid coefficient source.
arc=R/'embedded/BUILD7AR2_PASS.tar.gz'
actual={}
with tarfile.open(arc,'r:gz') as t:
    member=next(m for m in t.getmembers() if m.name.endswith('BUILD7_GRID_LINEAR_COEFFICIENTS.npz'))
    data=t.extractfile(member).read()
with np.load(io.BytesIO(data),allow_pickle=False) as z:
    rr=np.asarray(z['r_ohm'],dtype=float)
    xx=np.asarray(z['x_ohm'],dtype=float)
    lim=np.asarray(z['line_apparent_limit_kVA'],dtype=float)
    nz=np.concatenate([np.abs(rr[rr!=0]),np.abs(xx[xx!=0])])
    min_rx=float(nz.min())
    actual={
      'node_count':int(len(z['node_axis'])),
      'edge_count':int(len(z['edge_child'])),
      'minimum_nonzero_r_or_x_ohm':min_rx,
      'baseline_min_voltage_flow_coefficient':0.002*min_rx,
      'b2_min_voltage_flow_coefficient':0.002*SCALE*min_rx,
      'coefficient_improvement_factor':SCALE,
      'finite_line_limit_kVA_min':float(np.nanmin(lim[np.isfinite(lim)])),
      'finite_line_limit_kVA_max':float(np.nanmax(lim[np.isfinite(lim)])),
      'finite_line_limit_MVA_min':float(np.nanmin(lim[np.isfinite(lim)])/SCALE),
      'finite_line_limit_MVA_max':float(np.nanmax(lim[np.isfinite(lim)])/SCALE),
    }
checks['actual_topology_168_nodes']=actual['node_count']==168
checks['known_2e9_source_matches']=abs(actual['baseline_min_voltage_flow_coefficient']-2e-9) <= 1e-18
checks['b2_grid_min_coefficient_2e6']=abs(actual['b2_min_voltage_flow_coefficient']-2e-6) <= 1e-15
checks['grid_tiny_coefficient_improved_1000x']=actual['coefficient_improvement_factor']==1000.0

# Prior R25F runtime evidence recorded [2e-09,7e+02].  If that lower edge was grid-driven,
# replacing only this source gives a static envelope 7e2/2e-6=3.5e8 (<1e9).  We label this
# as a predicted envelope; the full actual matrix statistics are intentionally deferred to B3.
prior_matrix_min=2e-9; prior_matrix_max=7e2
predicted_grid_driven_ratio=prior_matrix_max/actual['b2_min_voltage_flow_coefficient']
checks['predicted_grid_driven_ratio_under_1e9']=predicted_grid_driven_ratio < 1e9

result={
 'release':'R25I_B2_EXACT_NUMERICAL_RESCALING',
 'stage':'B2/7',
 'status':'PASS' if all(checks.values()) else 'FAIL',
 'checks':checks,
 'scale_kW_per_MW':SCALE,
 'randomized_trials':10000,
 'max_balance_equivalence_error':max_balance_err,
 'max_voltage_equivalence_error':max_voltage_err,
 'max_thermal_ratio_equivalence_error':max_thermal_err,
 'actual_BUILD7AR2_coefficients':actual,
 'prior_R25F_runtime_matrix_range':{'min':prior_matrix_min,'max':prior_matrix_max},
 'predicted_grid_driven_matrix_ratio_after_B2':predicted_grid_driven_ratio,
 'actual_full_model_matrix_range_measured':False,
 'actual_full_model_matrix_range_deferred_to':'B3 batch screening / first real model build',
 'scientific_feasible_set_changed':False,
 'objective_changed':False,
 'MIPGap_changed':False,
 'long_solver_run':False,
}
print(json.dumps(result,indent=2,sort_keys=True))
if result['status']!='PASS': raise SystemExit(2)
