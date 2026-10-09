"""Same development reference as V3 LV probes, all606 guarded MV candidates."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .ac import IEEE8500AC
from .capacity import build_candidate,FIXED_AIDC
from .common import REPORT,read,write,table,receipt
from .geometry import read_csv
from .screening import demand
from .sensitivity import SLOTS,topology_paths

FOLDER=REPORT/'joint_selection_v3/mv_sensitivity'


def run():
    policy=read(REPORT/'joint_selection_v2/sensitivity/PREREGISTRATION.json')
    candidates=read_csv(REPORT/'MV_AIDC_CANDIDATES.csv')
    prereg=dict(schema='V3_ALL_MV_AC_SENSITIVITY',slots=list(SLOTS),background_scale=.552,
        capacity_scale=1.0,sites_reference='historicalv3/currentV42B0, no MESS dispatch',development_date='2025-05-01',
        already_exposed_date=True,targets=policy['line_set'],candidates=receipt(REPORT/'MV_AIDC_CANDIDATES.csv'),
        perturbation_kw_or_kvar=1.0,controls='fixed common original-autocontrol settled base',
        hardware_spec='AIDC PF.95 coupled Q/P; known-only original UID power bound as uncertified relaxation, no idle/CC4',
        B1_B2_B3_results_used=False,physically_certified_dispatch=False,Native_calls=0)
    write(FOLDER/'PREREGISTRATION.json',prereg)
    c=build_candidate(1.);e=IEEE8500AC(output_dir=FOLDER/'dss')
    for site,bus in FIXED_AIDC.items():e.add_pcc(site,bus,'MV_3PH')
    for k,r in enumerate(candidates):e.add_pcc(f'MV3{k:04d}',r['dss_bus'],'MV_3PH')
    groups={n:np.array([k for k,a in enumerate(e.line_axes) if e.objective_line_mask[k] and a['element'].lower()==n]) for n in policy['line_set']}
    paths=topology_paths(e);rows=[];summaries=[];coupling=[]
    ratio=float(np.tan(np.arccos(.95)))
    for slot in SLOTS:
        base_demand=demand(c,slot);base=e.solve(.552,base_demand);a0=e.measurement_arrays()
        for k,r in enumerate(candidates):
            pid=f'MV3{k:04d}';bus=r['dss_bus']
            res=e.local_injection_sensitivity(pid,.552,base_demand,1.,1.,'fixed',base)
            dp,dq=res['derivatives']['P'],res['derivatives']['Q']
            for comp in ('P','Q'):
                d=res['derivatives'][comp];ep=res['endpoints'][comp]
                if any(not x['converged'] or x['control_queue_size'] for x in (ep['plus_injection'],ep['minus_injection'])):
                    raise ValueError('MV_PROBE_AC_FAILED')
                summaries.append(dict(slot=slot,bus=bus,probe_id=pid,component=comp,
                    maximum_abs_current_derivative=float(np.abs(d['line_amps']).max()),
                    maximum_abs_voltage_derivative=float(np.abs(d['node_voltage_pu']).max()),
                    plus_transformer_current_rho_max=float(ep['plus_injection']['transformer_current_rho'].max()),
                    minus_transformer_current_rho_max=float(ep['minus_injection']['transformer_current_rho'].max()),
                    plus_transformer_nameplate_rho_max=float(ep['plus_injection']['transformer_winding_nameplate_kva_rho'].max()),
                    minus_transformer_nameplate_rho_max=float(ep['minus_injection']['transformer_winding_nameplate_kva_rho'].max()),
                    plus_all_line_rho_max=float(ep['plus_injection']['line_rho'][e.objective_line_mask].max()),
                    minus_all_line_rho_max=float(ep['minus_injection']['line_rho'][e.objective_line_mask].max()),
                    plus_Vmin=float(ep['plus_injection']['node_voltage_pu'].min()),plus_Vmax=float(ep['plus_injection']['node_voltage_pu'].max()),
                    minus_Vmin=float(ep['minus_injection']['node_voltage_pu'].min()),minus_Vmax=float(ep['minus_injection']['node_voltage_pu'].max()),
                    dispatch_certified=False))
            for n,g in groups.items():
                axis=int(g[np.argmax(a0['line_rho'][g])])
                rows.append(dict(slot=slot,bus=bus,line=n,baseline_rho=float(a0['line_rho'][axis]),
                    baseline_node=e.line_axes[axis]['node'],dI_P_A_per_kw=float(dp['line_amps'][axis]),
                    dI_Q_A_per_kvar=float(dq['line_amps'][axis]),dRho_P_per_kw=float(dp['line_rho'][axis]),
                    dRho_Q_per_kvar=float(dq['line_rho'][axis]),
                    dRho_AIDC_PF95_per_kw=float(dp['line_rho'][axis]+ratio*dq['line_rho'][axis]),
                    dI_AIDC_PF95_A_per_kw=float(dp['line_amps'][axis]+ratio*dq['line_amps'][axis]),
                    path_contains_target=n in paths.get(bus,set()),
                    certified_available_flexible_kw='',performance_prediction=False))
            if k==0:
                pair=[]
                for sign in (-1,1):
                    dd=dict(base_demand);dd[pid]=(-sign,-sign*ratio)
                    e.solve(.552,dd,'fixed',base['control_state'],snapshot=False);pair.append(e.measurement_arrays())
                err=float(np.abs((pair[1]['line_amps']-pair[0]['line_amps'])/2-(dp['line_amps']+ratio*dq['line_amps'])).max())
                coupling.append(dict(slot=slot,bus=bus,maximum_absolute_PF_partial_vs_direct_A_per_kw=err,PASS=err<.01))
            if (k+1)%100==0:print('V3 MV',slot,k+1,'/',len(candidates),flush=True)
        table(FOLDER/f'TOP20_RESPONSE_SLOT_{slot:02d}.csv',[x for x in rows if x['slot']==slot])
    table(FOLDER/'TOP20_RESPONSE.csv',rows);table(FOLDER/'PCC_SUMMARY.csv',summaries)
    table(FOLDER/'PF_COUPLING_VALIDATION.csv',coupling)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE_ALL606_MV_DEVELOPMENT_DIAGNOSTICS',candidates=len(candidates),
        rows=len(rows),slots=list(SLOTS),known_workload_bound_is_relaxation=True,source_identity_unchanged=e.verify_source_unchanged(),
        PF_check_PASS=all(x['PASS'] for x in coupling),Native_calls=0))


if __name__=='__main__':run()
