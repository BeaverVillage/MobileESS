"""Physical-sign AC checks at the all-pair geometric witness, not a dispatch."""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .ac import IEEE8500AC
from .capacity import build_candidate
from .common import REPORT,read,write,table,receipt
from .geometry import read_csv
from .screening import demand
from .sensitivity import SLOTS,topology_paths

FOLDER=REPORT/'joint_selection_v2'/'witness_response'
MAPPING=REPORT/'joint_selection_v2'/'expanded_orientation_v1'/'JOINT_SERVICE_MAPPING.csv'


def run():
    mapping=read_csv(MAPPING)
    policy=read(REPORT/'joint_selection_v2/sensitivity/PREREGISTRATION.json')
    prereg=dict(schema='WITNESS_RESPONSE_BEFORE_AC_V1',mapping=receipt(MAPPING),slots=list(SLOTS),
        lines=policy['line_set'],development_date='2025-05-01',background_scale=1.0,capacity_scale=1.0,
        step_kw_or_kvar=1.0,AIDC_direction='reduce consumption P and Q together at original PF.95',
        MESS_partials='separate electrical P/Q injection only, all actual port and access bounds unresolved',
        controls='fixed identical settled witness B0 taps/caps, initialized independently from source at each of4times',
        performance_used_for_selection=False,physical_usable_power_certified=False,Native_calls=0)
    write(FOLDER/'PREREGISTRATION.json',prereg)
    c=build_candidate(1.0);e=IEEE8500AC(output_dir=FOLDER/'dss')
    for x in mapping:e.add_pcc(x['location_id'],x['candidate_bus'],'MV_3PH')
    paths=topology_paths(e);mask=e.objective_line_mask
    linegroups={n:np.array([k for k,a in enumerate(e.line_axes) if mask[k] and a['element'].lower()==n]) for n in policy['line_set']}
    summary=[];targets=[];validation=[]
    pf_ratio=float(np.tan(np.arccos(.95)))
    for t in SLOTS:
        d0=demand(c,t);base=e.solve(1.,d0);a0=e.measurement_arrays()
        if not a0['converged'] or not a0['control_actions_done']:raise ValueError('WITNESS_BASE_NOT_SETTLED')
        for x in mapping:
            site=x['location_id'];res=e.local_injection_sensitivity(site,1.,d0,1.,1.,'fixed',base)
            channels=dict(P=res['derivatives']['P'],Q=res['derivatives']['Q'])
            if x['role']=='AIDC':
                endpoints=[]
                for sign in (-1,1):
                    changed=dict(d0);p,q=changed[site];changed[site]=(p-sign,q-sign*pf_ratio)
                    e.solve(1.,changed,'fixed',base['control_state'],snapshot=False)
                    endpoints.append(e.measurement_arrays())
                minus,plus=endpoints
                direct={key:(plus[key]-minus[key])/2 for key in ('line_amps','line_rho','node_voltage_pu')}
                channels['AIDC_PF_COUPLED']=direct
                prediction=res['derivatives']['P']['line_amps']+pf_ratio*res['derivatives']['Q']['line_amps']
                error=float(np.max(np.abs(prediction-direct['line_amps'])))
                validation.append(dict(slot=t,site=site,PF=.95,Q_per_P=pf_ratio,
                    actual_coupled_minus_converged=minus['converged'],actual_coupled_plus_converged=plus['converged'],
                    maximum_absolute_partial_combination_vs_direct_A_per_kw=error,
                    PASS=error<.01,original_source_and_control_unchanged=True))
            for component,d in channels.items():
                critical=int(np.argmax(np.where(mask,a0['line_rho'],-np.inf)))
                summary.append(dict(slot=t,probe_id=site,bus=x['candidate_bus'],role=x['role'],component=component,
                    critical_line=e.line_axes[critical]['element'],rho_derivative_pu_per_unit=float(d['line_rho'][critical]),
                    critical_line_amps_derivative=float(d['line_amps'][critical]),
                    maximum_abs_current_derivative=float(np.abs(d['line_amps']).max()),
                    maximum_abs_voltage_derivative=float(np.abs(d['node_voltage_pu']).max()),
                    physically_certified_usable_power='',fixed_taps_caps=True,production_performance_estimate=False))
                for n,g in linegroups.items():
                    k=int(g[np.argmax(a0['line_rho'][g])])
                    targets.append(dict(slot=t,site=site,bus=x['candidate_bus'],role=x['role'],component=component,
                        line=n,baseline_rho=float(a0['line_rho'][k]),baseline_parent_node=e.line_axes[k]['node'],
                        dI_A_per_unit=float(d['line_amps'][k]),dRho_pu_per_unit=float(d['line_rho'][k]),
                        path_contains_line=n in paths.get(x['candidate_bus'],set()),
                        physically_certified_usable_power='',certified_dispatch_effect='UNDEFINED'))
        print('witness24 AC responses slot',t,'complete',flush=True)
    table(FOLDER/'SENSITIVITY_PCC_SUMMARY.csv',summary)
    table(FOLDER/'TOP20_RESPONSE.csv',targets)
    table(FOLDER/'AIDC_PF_COUPLING_VALIDATION.csv',validation)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE_UNQUALIFIED_GEOMETRY_WITNESS',rows=len(summary),top20_rows=len(targets),
        AIDC_PF_coupled_PASS=all(x['PASS'] for x in validation),Native_calls=0,source_files_unchanged=e.verify_source_unchanged()))


if __name__=='__main__':run()
