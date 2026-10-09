"""Focused automatic384endpoint audit with actual PCC/local-grid readbacks.

Original automatic full-rating archive had global/control summaries only.
This adds the missing local evidence without rerunning fixed9216 endpoints.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .common import REPORT,write,table,receipt
from .geometry import read_csv
from .capacity import build_candidate
from .screening import demand
from .selected_case_v3 import engine,MAPPING,array_summary
from .selected_port_ac import COMMANDS
from .lv_sensitivity import axes_for_candidate
from .lv_port_design import command_check
from .integration import digest

FOLDER=REPORT/'joint_selection_v3/selected_port_ac/automatic_local_audit'


def run():
    write(FOLDER/'PREREGISTRATION.json',dict(mapping=receipt(MAPPING),slots=[0,9,48,75],
        commands=COMMANDS,reason='original384automatic archive lacked local PCC readbacks; focusedaudit',
        controls='each endpoint restores original source initial taps/caps and independently settles automatic controls',
        archived_Planning_states_imported=False,Native_calls=0,continuous_control_domain_certificate=False))
    e=engine('automatic_port_local');c=build_candidate(1.)
    candidates={r['candidate_bus']:r for r in read_csv(REPORT/'LV_STA_CANDIDATES.csv')}
    mapping=[r for r in read_csv(MAPPING) if r['role']=='STA']
    local={r['location_id']:axes_for_candidate(e,candidates[r['candidate_bus']]) for r in mapping}
    rows=[];states=[]
    for t in (0,9,48,75):
        dd=demand(c,t)
        for r in mapping:
            site=r['location_id'];bus=r['candidate_bus'];li=local[site]
            for p,q in COMMANDS:
                d=dict(dd);d[site]=(-p,-q)
                e.solve(.552,d,reset_controls=True,snapshot=False);a=e.measurement_arrays()
                e.d.Circuit.SetActiveElement(e.pccs[site]['element'])
                powers=np.array(e.d.CktElement.Powers()).reshape(-1,2).sum(0)
                currents=np.array(e.d.CktElement.Currents()).reshape(-1,2)
                e.d.Circuit.SetActiveBus(bus)
                vv=np.array(e.d.Bus.Voltages()).reshape(-1,2)
                vv={n:complex(*v) for n,v in zip(e.d.Bus.Nodes(),vv)}
                state=e.control_state();hw=command_check(p,q,vv[1],vv[2])
                ok=bool(a['line_rho'][li['line']].max()<=1
                    and a['transformer_current_rho'][li['tx_current']].max()<=1
                    and a['transformer_winding_nameplate_kva_rho'][li['tx_kva']].max()<=1
                    and a['node_voltage_pu'][li['nodes']].min()>=.95
                    and a['node_voltage_pu'][li['nodes']].max()<=1.05)
                row=dict(slot=t,site=site,bus=bus,P_injection_kw=p,Q_injection_kvar=q,
                    actual_P_kw=float(powers[0]),actual_Q_kvar=float(powers[1]),
                    PQ_readback_error=float(np.abs(powers+np.array([p,q])).max()),
                    hot1_A=float(np.linalg.norm(currents[0])),hot2_A=float(np.linalg.norm(currents[1])),
                    hot_KCL_A=float(np.linalg.norm(currents.sum(0))),actual_VLL_V=abs(vv[1]-vv[2]),
                    local_voltage_min_pu=float(a['node_voltage_pu'][li['nodes']].min()),
                    local_voltage_max_pu=float(a['node_voltage_pu'][li['nodes']].max()),
                    local_line_rho_max=float(a['line_rho'][li['line']].max()),
                    CT_current_rho_max=float(a['transformer_current_rho'][li['tx_current']].max()),
                    CT_nameplate_rho_max=float(a['transformer_winding_nameplate_kva_rho'][li['tx_kva']].max()),
                    interface_envelope_PASS=hw['interface_envelope_PASS'],local_original_grid_PASS=ok,
                    settled_state_sha256=digest(state),source_initial_reset=True,**array_summary(e,a))
                if row['PQ_readback_error']>1e-6 or row['hot_KCL_A']>1e-9 or not a['converged'] or not a['control_actions_done'] or a['control_queue_size']:
                    raise ValueError('AUTOMATIC_PCC_OR_CONTROL_READBACK_FAILED')
                rows.append(row);states.append(dict(slot=t,site=site,P=p,Q=q,state=state,sha256=digest(state)))
    table(FOLDER/'AUTOMATIC_PCC_LOCAL_FULL_RATING.csv',rows)
    write(FOLDER/'ORIGINAL_AUTOMATIC_CONTROL_STATES.json',states)
    write(FOLDER/'RECEIPT.json',dict(status='COMPLETE384_AUTOMATIC_LOCAL_PCC_READBACKS',cases=len(rows),
        all_sampled_local_PASS=all(r['local_original_grid_PASS'] for r in rows),
        all_sampled_hardware_PASS=all(r['interface_envelope_PASS'] for r in rows),
        maximum_PQ_error=max(r['PQ_readback_error'] for r in rows),maximum_KCL_A=max(r['hot_KCL_A'] for r in rows),
        original_source_identity=e.verify_source_unchanged(),continuous_domain_certificate=False,
        baseline_global_voltage_PASS=False,Native_calls=0))
    print('automatic384local PCC audit complete',flush=True)


if __name__=='__main__':run()
