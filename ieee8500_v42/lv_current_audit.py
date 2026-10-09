"""Actual signed small split-phase charge/discharge AC current checks.

Original CT and Triplex ratings are preserved. A +/-0.1 kW electrical probe
does not constitute a licensed inverter or establish any nonzero port limit.
"""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .ac import IEEE8500AC
from .common import REPORT, read, write, table
from .capacity import build_candidate,FIXED_AIDC
from .geometry import read_csv
from .screening import demand
from .sensitivity import SLOTS


def run():
    policy=read(REPORT/'joint_selection_v2/sensitivity/PREREGISTRATION.json')
    probes=[p for p in policy['probes'] if p['mode']=='LV_SPLIT_240']
    inv={r['candidate_bus']:r for r in read_csv(REPORT/'LV_STA_CANDIDATES.csv')}
    folder=REPORT/'joint_selection_v2/lv_current_audit'
    e=IEEE8500AC(output_dir=folder/'dss');c=build_candidate(1.)
    for site,bus in FIXED_AIDC.items():e.add_pcc(site,bus,'MV_3PH')
    for p in probes:e.add_pcc(p['probe_id'],p['bus'],'LV_SPLIT_240')
    rows=[];ports=[]
    for t in SLOTS:
        d0=demand(c,t);base=e.solve(1.,d0);a0=e.measurement_arrays()
        for p in probes:
            meta=inv[p['bus']];lines=set(meta['direct_support_lines'].split('|'))
            li=[k for k,x in enumerate(e.line_axes) if x['element'].lower() in lines]
            xi=[k for k,x in enumerate(e.transformer_axes) if x['element'].lower()==meta['upstream_transformer']]
            for comp in ('P','Q'):
                for sign in (-1,1):
                    pq=(-sign*.1,0) if comp=='P' else (0,-sign*.1)
                    changed=dict(d0);changed[p['probe_id']]=pq
                    snap=e.solve(1.,changed,'fixed',base['control_state'])
                    a=e.measurement_arrays();pcc=snap['pcc_actual'][p['probe_id']]
                    # A 240V device injects equal opposite hot currents by KCL.
                    e.d.Circuit.SetActiveElement(e.pccs[p['probe_id']]['element'])
                    current=np.array(e.d.CktElement.Currents());coils=current.reshape(-1,2)
                    kcl=float(np.linalg.norm(coils.sum(0)))
                    ports.append(dict(slot=t,bus=p['bus'],probe_id=p['probe_id'],component=comp,
                        injection_sign=sign,actual_P_kw=pcc['p_kw'],actual_Q_kvar=pcc['q_kvar'],
                        equal_opposite_hot_KCL_A=kcl,KCL_PASS=kcl<1e-9,
                        engineering_kva_ceiling_NOT_port_permission=meta['engineering_upper_bound_kva_NOT_allowed_output'],
                        original_CT_primary_kva=meta['transformer_primary_kva'],original_Triplex_NormalAmps=meta['triplex_min_normal_amps'],
                        certified_allowed_port_kw='',certified_allowed_port_kvar='',vehicle_design_kw=450,
                        full_vehicle_rating_injected=False,physical_port_qualified=False,
                        original_CT_current_rho_max=float(a['transformer_current_rho'][xi].max()),
                        all_line_rho_max=float(a['line_rho'][e.objective_line_mask].max()),
                        all_node_Vmin=float(a['node_voltage_pu'].min()),all_node_Vmax=float(a['node_voltage_pu'].max())))
                    for k in li:
                        axis=e.line_axes[k]
                        rows.append(dict(slot=t,pcc_bus=p['bus'],probe_id=p['probe_id'],component=comp,
                            injection_sign=sign,**axis,base_current_A=float(a0['line_amps'][k]),actual_current_A=float(a['line_amps'][k]),
                            actual_rho=float(a['line_rho'][k]),change_current_A=float(a['line_amps'][k]-a0['line_amps'][k]),
                            charge_overload_audited=True,neutral_is_original_Kron_reduced_not_independently_rated=True))
    table(REPORT/'LV_SPLIT_PHASE_CURRENT_VALIDATION.csv',rows)
    table(folder/'PCC_KCL_AND_ELECTRICAL_CHECK.csv',ports)
    write(folder/'RECEIPT.json',dict(PASS=all(r['KCL_PASS'] for r in ports),
        status='REAL_SPLIT_PHASE_ELECTRICAL_PROBES_NOT_PORT_APPROVAL',PCC_cases=len(ports),conductor_cases=len(rows),
        source_original=e.verify_source_unchanged(),no_new_transformers=True,Native_calls=0))


if __name__=='__main__':run()
