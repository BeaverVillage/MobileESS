"""Saved-point affine counterfactuals. No optimizer, AC solve, or source edit."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import json
import numpy as np
import pandas as pd
from scipy import sparse

OUT = Path(__file__).resolve().parent
CASE = Path(r'D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01')
MODEL = CASE/'output'
INPUT = Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B2\2025-05-01')
REPO = Path(r'D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
REGULATORS = ('reg1a','reg2a','reg3a','reg3c','reg4a','reg4b','reg4c')
CAPACITORS = ('c83','c88a','c90b','c92c')

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def record(p, expected=None):
    p = Path(p).resolve()
    r = dict(path=str(p), sha256=sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)
    if expected is not None:
        assert r['sha256'] == expected['sha256'] and r['bytes'] == expected['bytes'], 'INPUT_RECEIPT_DRIFT:'+str(p)
    return r

def arrays(p):
    with np.load(p, allow_pickle=False) as data:
        return {k:data[k].copy() for k in data.files}

def table(name, rows):
    p = OUT/name
    with p.open('w', encoding='utf-8-sig', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    return record(p)

native = read(INPUT/'NATIVE_INPUT.json')
prior = read(OUT/'B2_MAY01_VOLTAGE_AUDIT.json')
factorial = read(OUT/'FACTORIAL_REPLAY_STATUS.json')
assert factorial['baseline_reproduced_bit_exact'] is True and factorial['PASS'] is True
sources = []
for r in prior['sources']:
    sources.append(record(r['path'],r))
for name in ('B2_MAY01_VOLTAGE_AUDIT.json','FACTORIAL_REPLAY_STATUS.json', 'B2_MAY01_19CELL_PQ_FACTORIAL.csv'):
    sources.append(record(OUT/name))
cp = Path(native['grid_outputs']['planning_coefficients']['path'].replace('C:','D:',1))
sp = Path(native['grid_outputs']['voltage']['path'].replace('C:','D:',1))
coeff = arrays(cp); anchor = arrays(sp)
certpath=Path(native['electrical_certificate']['path'])
sources.append(record(certpath,native['electrical_certificate']))
electrical_cert=read(certpath)
provenance=electrical_cert['input_identity']['identity']['inputs']
jointpath=cp.parents[2]/'april_joint_authority/V40E_CORRECTED_JOINT_VOLTAGE_AUTHORITY.json'
joint=read(jointpath);sources.append(record(jointpath))
generator_receipts=[]
for r in provenance['V41_generation_source']['files']:
    if r['relative_path'] in ('dayahead/v40i/electrical.py','dayahead/v40e/electrical.py'):
        generator_receipts.append(record(r['path'].replace('C:','D:',1),r))
r=provenance['voltage_generation']['dayahead/run_v16_3_voltage_candidate.py']
generator_receipts.append(record(REPO/'dayahead/run_v16_3_voltage_candidate.py',r))
sources.extend(generator_receipts)

pointpath=MODEL/'BEST_STRICT_UB_POINT.npz'
original_point_receipt=record(pointpath)
point=arrays(pointpath)['point']
identity=read(MODEL/'SCIENTIFIC_CASE_IDENTITY.json')
axes=arrays(MODEL/'CURRENT_C2_AXES.npz')
lifted=np.zeros(identity['transport']['compact_columns'])
lifted[axes['columns']]=point
for d in reversed(read(MODEL/'CURRENT_C2_ALIASES.json')):
    lifted[d['column']]=d['constant']+sum(weight*lifted[int(column)] for column,weight in d['terms'].items())
full=arrays(MODEL/'FULL_DATA.npz')
full_point=lifted[:len(full['names'])]
full_point_bytes=full_point.tobytes()
assert np.array_equal(full_point[full['types']!='C'],np.rint(full_point[full['types']!='C']))
fixed=read(MODEL/'FIXED_AIDC_ANCHOR.json')
controls=np.asarray(fixed['controls']).copy()
names=fixed['control_names']
assert names==anchor['control_names'].astype(str).tolist()
cols={str(name):i for i,name in enumerate(full['names'])}
P=np.array([n.startswith('mess_p_kw[') for n in names])
Q=np.array([n.startswith('mess_q_kvar[') for n in names])
for t in range(96):
    for j,name in enumerate(names):
        if P[j] or Q[j]:
            site=name.split('[',1)[1][:-1]
            controls[t,j]=full_point[cols[f"injection_{'P' if P[j] else 'Q'}[{site},{t}]"]]
zero_controls=controls.copy();zero_controls[:,P|Q]=0.
p_controls=controls.copy();p_controls[:,Q]=0.
q_controls=controls.copy();q_controls[:,P]=0.
variants={'FULL_PQ_REPLAY':controls, 'P_ONLY_Q_ZERO':p_controls,
          'Q_ONLY_P_ZERO':q_controls, 'ZERO_PQ':zero_controls}
plan2={k:coeff['voltage_constant']+np.einsum('tcn,tc->tn',coeff['voltage_matrix'],u) for k,u in variants.items()}
assert all((v>0).all() for v in plan2.values())
plan={k:np.sqrt(v) for k,v in plan2.items()}
actual={}
for v in factorial['variants']:
    rawpath=Path(v['diagnostic_raw_AC']['path'])
    sources.append(record(rawpath,v['diagnostic_raw_AC']))
    actual[v['variant']]=arrays(rawpath)
nodes=coeff['node_names'].astype(str)
assert np.array_equal(nodes,anchor['node_names'].astype(str))
for data in actual.values():
    assert np.array_equal(nodes,data['node_names'].astype(str)) and data['convergence'].all()
pv=arrays(OUT/'B2_MAY01_PLANNING_ACTUAL_VOLTAGES.npz')
sources.append(record(OUT/'B2_MAY01_PLANNING_ACTUAL_VOLTAGES.npz',prior['arrays']))
original_plan_error=float(np.max(abs(plan['FULL_PQ_REPLAY']-pv['Planning_V_pu'])))
assert original_plan_error<1e-12
assert np.array_equal(actual['FULL_PQ_REPLAY']['voltage_pu'],pv['Actual_V_pu'])
with (OUT/'B2_MAY01_19CELL_PQ_FACTORIAL.csv').open(encoding='utf-8-sig',newline='') as stream:
    rows=list(csv.DictReader(stream))
assert len(rows)==19
full_A=sparse.load_npz(MODEL/'FULL_A.npz').tocsr()
row_error=0.
for row in rows:
    t,n=int(row['slot_0based']),int(row['node_axis_0based'])
    assert nodes[n]==row['node_phase']
    i=int(row['FULL_voltage_upper_row'])
    row2=float((full_A.getrow(i)@full_point).item()+1.1025-full['rhs'][i])
    row_error=max(row_error,abs(row2-plan2['FULL_PQ_REPLAY'][t,n]))
    a={k:float(v['voltage_pu'][t,n]) for k,v in actual.items()}
    p={k:float(v[t,n]) for k,v in plan.items()}
    for key,col in (('FULL_PQ_REPLAY','VFull_PQ'),('P_ONLY_Q_ZERO','VPonly_Qzero'),
                    ('Q_ONLY_P_ZERO','VQonly_Pzero'),('ZERO_PQ','Vzero_PQ')):
        assert a[key]==float(row[col])
    pf,pp,pq,pz=(p[k] for k in ('FULL_PQ_REPLAY','P_ONLY_Q_ZERO','Q_ONLY_P_ZERO','ZERO_PQ'))
    af,ap,aq,az=(a[k] for k in ('FULL_PQ_REPLAY','P_ONLY_Q_ZERO','Q_ONLY_P_ZERO','ZERO_PQ'))
    row.update(Planning_Full_PQ_pu=pf,Planning_Ponly_Qzero_pu=pp,Planning_Qonly_Pzero_pu=pq,
        Planning_zero_PQ_pu=pz, Planning_minus_Actual_zero_PQ_pu=pz-az,
        baseline_Actual_minus_Planning_zero_PQ_pu=az-pz,
        Planning_MESS_P_effect_when_Qzero_pu=pp-pz,Planning_MESS_Q_effect_when_Pzero_pu=pq-pz,
        Planning_MESS_P_effect_when_Qoriginal_pu=pf-pq,Planning_MESS_Q_effect_when_Poriginal_pu=pf-pp,
        Planning_P_Q_interaction_pu=pf-pp-pq+pz,
        Planning_combined_MESS_effect_pu=pf-pz,
        P_contribution_error_when_Qzero_pu=(ap-az)-(pp-pz),
        Q_contribution_error_when_Pzero_pu=(aq-az)-(pq-pz),
        P_contribution_error_when_Qoriginal_pu=(af-aq)-(pf-pq),
        Q_contribution_error_when_Poriginal_pu=(af-ap)-(pf-pp),
        P_Q_interaction_error_pu=(af-ap-aq+az)-(pf-pp-pq+pz),
        combined_MESS_contribution_error_pu=(af-az)-(pf-pz),
        gap_decomposition_sum_pu=(az-pz)+((af-az)-(pf-pz)),
        gap_decomposition_identity_residual_pu=(af-pf)-((az-pz)+((af-az)-(pf-pz))),
        Planning_P_contribution_squared_pu=float(plan2['P_ONLY_Q_ZERO'][t,n]-plan2['ZERO_PQ'][t,n]),
        Planning_Q_contribution_squared_pu=float(plan2['Q_ONLY_P_ZERO'][t,n]-plan2['ZERO_PQ'][t,n]),
        Planning_anchor_AC_zeroMESS_pu=float(np.sqrt(anchor['anchor_v_squared'][t,n])),
        Planning_anchor_taps=json.dumps(anchor['regulator_taps'][t].tolist()),
        Planning_anchor_capacitor_states=json.dumps(anchor['capacitor_states'][t].tolist()),
        Actual_Full_capacitor_states=json.dumps(actual['FULL_PQ_REPLAY']['capacitor_states'][t].tolist()))
assert row_error<1e-12
assert full_point.tobytes()==full_point_bytes and record(pointpath)==original_point_receipt
cell_csv=table('B2_MAY01_PLANNING_ACTUAL_FACTORIAL_19CELLS.csv',rows)

taprows=[]
for variant,data in actual.items():
    for t in range(96):
        for j,regulator in enumerate(REGULATORS):
            delta=float(data['regulator_taps'][t,j]-anchor['regulator_taps'][t,j])
            taprows.append(dict(variant=variant,slot_0based=t,slot_1based=t+1,
                timestamp_interval_end_aest=str(pv['timestamps_interval_end_aest'][t]),regulator=regulator,
                Planning_anchor_tap=float(anchor['regulator_taps'][t,j]),
                Actual_autonomous_tap=float(data['regulator_taps'][t,j]),Actual_minus_Planning_anchor_tap=delta,
                physical_tap_step_difference=round(delta/.00625),diagnostic_forced_tap_changes=0))
tapcsv=table('B2_MAY01_PLANNING_ANCHOR_ACTUAL_TAPS.csv',taprows)
anchor_match=float(np.max(abs(coeff['voltage_constant']+
    np.einsum('tcn,tc->tn',coeff['voltage_matrix'],anchor['anchor_control'])-anchor['anchor_v_squared'])))
aidc_error=controls[:,~(P|Q)]-anchor['anchor_control'][:,~(P|Q)]
tap_summary={}
for variant,data in actual.items():
    difference=abs(data['regulator_taps']-anchor['regulator_taps'])>1e-12
    tap_summary[variant]=dict(different_regulator_slot_cells=int(difference.sum()),
        slots_with_any_regulator_difference=int(difference.any(axis=1).sum()),
        per_regulator_different_slot_count={r:int(difference[:,j].sum()) for j,r in enumerate(REGULATORS)},
        maximum_abs_tap_difference=float(np.max(abs(data['regulator_taps']-anchor['regulator_taps']))),
        capacitor_state_difference_count=int(np.count_nonzero(data['capacitor_states']!=anchor['capacitor_states'])))
forecastpath=Path(r'C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend\cache\v28r2_campaign_sources\may_2025\days\2025-05-01\aemo_forecast.json')
sources.append(record(forecastpath,provenance['demand']['source']))
forecast=read(forecastpath)
actualsource=read(MODEL/'OPERATIONS/ACTUAL_SOURCE/ACTUAL_SOURCE_RECEIPT.json')['source']
sources.append(record(actualsource['path'],actualsource))
observed=pd.read_parquet(actualsource['path'])
forecast_actual={}
for fkey,akey in (('demand_mw_96','demand_mw'),('pv_mw_96','rooftop_pv_mw')):
    delta=observed[akey].to_numpy()-np.asarray(forecast[fkey])
    forecast_actual[fkey]=dict(max_abs_Actual_minus_forecast_MW=float(np.max(abs(delta))),
        min_Actual_minus_forecast_MW=float(delta.min()),max_Actual_minus_forecast_MW=float(delta.max()),
        mean_Actual_minus_forecast_MW=float(delta.mean()))
for r in sources:
    assert record(r['path'])==r,'READ_ONLY_SOURCE_DRIFT:'+r['path']
interaction2=plan2['FULL_PQ_REPLAY']-plan2['P_ONLY_Q_ZERO']-plan2['Q_ONLY_P_ZERO']+plan2['ZERO_PQ']
worst=max(rows,key=lambda row:float(row['Actual_exceedance_pu']))
audit=dict(schema='V42_B2_MAY01_PLANNING_ACTUAL_FACTORIAL_GAP_AUDIT_V1',
    generated_UTC=datetime.now(timezone.utc).isoformat(),diagnostic_only=True,PASS=True,
    Native_optimizer_calls=0,OpenDSS_solve_calls=0,source_mutation_count=0,point_mutation_count=0,
    original_strict_point_and_original_Fresh_trajectory_preserved=True,
    original_case_SHA=identity['case_sha'],original_source_SHA=prior['source_SHA'],
    exact_coordinate_axis=True,original_FULL_point_counterfactual_controls=True,
    preserving_non_MESS_coordinates=True,original_FULL_voltage_row_max_v2_difference=row_error,
    original_Planning_reconstruction_max_pu_difference=original_plan_error,
    Planning_squared_voltage_PQ_interaction_max=float(np.max(abs(interaction2))),
    affine_evaluation='V_squared = original voltage_constant + original voltage_matrix * original controls. P-only zeros only MESS Q; Q-only zeros only MESS P; zero zeros only MESS P/Q. These hypothetical coordinate evaluations are not strict-feasible replacement points.',
    Planning_pu_interaction_semantics='The affine squared-voltage model has zero P/Q interaction; a nonzero pu interaction can arise solely from taking square roots.',
    decomposition_equation='ActualFull-PlanFull=(Actualzero-Planzero)+[(ActualFull-Actualzero)-(PlanFull-Planzero)]',
    contribution_error_equation='combined response error = P-only effect error + Q-only effect error + P/Q interaction error',
    baseline_residual_scope='The baseline residual combines forecast/Actual exogenous input differences, fixed AIDC operating-point differences, affine model error, and native control response. This comparison does not uniquely assign it to regulator controls or any single cause.',
    response_error_scope='Actual factorial effects include nonlinear network response and autonomous control actions along each trajectory. They are not fixed-tap local derivatives.',
    voltage_cell_count=len(rows),worst_original_voltage_cell=worst,
    maximum_abs_gap_decomposition_identity_residual_pu=max(abs(r['gap_decomposition_identity_residual_pu']) for r in rows),
    Planning_reference=dict(sensitivity_schema=str(anchor['schema_version']),day=str(anchor['operating_day']),
        native_master_SHA=str(anchor['native_master_sha']),reference_AIDC_plan_SHA=str(anchor['plan_sha256']),
        AC_anchor_input_role=provenance['AC_anchor_input']['role'],all_anchor_MESS_PQ_zero=bool((anchor['anchor_control'][:,P|Q]==0).all()),
        AIDC_control_change_max_abs_kw=float(np.max(abs(aidc_error))),
        AIDC_control_change_total_over_all_cells_kw=float(aidc_error.sum()),
        AIDC_control_different_slot_site_cells=int(np.count_nonzero(abs(aidc_error)>1e-9)),
        coefficient_anchor_reconstruction_max_v2_error=anchor_match,
        exported_H_vs_raw_D1_H_changed_entries=int(np.count_nonzero(coeff['voltage_matrix']!=anchor['sensitivity'])),
        exported_H_vs_raw_D1_H_max_abs_change=float(np.max(abs(coeff['voltage_matrix']-anchor['sensitivity']))),
        original_frozen_April_joint_gradient_pairs=len(joint['joint_gradients']),
        joint_calibration_days=joint['calibration_days'],May_outcomes_used_for_gradient_selection=joint['May_outcomes_used_for_selection'],
        reference_controls_method='Per slot enable native RegControls, apply forecast background/PV and V41R2 Q90 B0 PCC AIDC input with zero MESS, solve to settle taps/caps; then freeze those states and disable controls for central finite differences. Exported Planning H includes frozen April joint-gradient substitutions and is recentered to the same AC anchor.',
        regulator_order=list(REGULATORS),capacitor_order=list(CAPACITORS),
        tap_comparison=tap_summary,forecast_vs_Actual_profile_difference=forecast_actual),
    csv=cell_csv,reference_taps_csv=tapcsv,sources=sources)
path=OUT/'B2_MAY01_PLANNING_ACTUAL_FACTORIAL_AUDIT.json'
path.write_text(json.dumps(audit,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(audit_receipt=record(path),csv=cell_csv,worst=worst,
    tap_comparison=tap_summary,AIDC_change_max_abs_kw=audit['Planning_reference']['AIDC_control_change_max_abs_kw'],
    gap_identity_error=audit['maximum_abs_gap_decomposition_identity_residual_pu']),indent=2))
