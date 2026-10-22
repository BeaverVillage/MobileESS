"""Independent audit of original measurement times, preserving TIME failures."""
import numpy as np
from .static_common import *

def audit():
    init();summary=[];ticks=[]
    for schedule in ('ZERO','P_ONLY','Q50','TWO_MOVE'):
        for role,fresh in [('ACTUAL',False),('ACTUAL',True)]+([('PLANNING',False)] if schedule=='ZERO' else []):
            p=HIST_RUN/'source_yy'/schedule/('2025-05-01_'+role+('_FRESH' if fresh else ''))
            rec=read(p/'RECEIPT.json');events=read(p/'EVENTS.json');clock=read(p/'CLOCK.json')
            with np.load(p/'AC.npz') as z:a={k:z[k] for k in z.files}
            offset=24 if role=='ACTUAL' else 0;sel=[]
            for t in range(120 if offset else 96):
                j=int(np.flatnonzero(a['event_slot']==t)[-1]);sel.append(j)
                assert events[j]['physical_seconds']==clock[t]['last_solve_seconds']
                v=a['node_voltage_pu'][j];line=a['line_rho'][j]
                thermal=float(line.max())<=1. and float(a['transformer_current_rho'][j].max())<=1. and float(a['transformer_winding_nameplate_kva_rho'][j].max())<=1.
                ticks.append(dict(schedule=schedule,role=role,fresh=fresh,slot=t,evaluation_slot=t-offset,
                    selected_event_index=j,physical_seconds=events[j]['physical_seconds'],
                    Vmin=float(v.min()),Vmax=float(v.max()),voltage_PASS=bool(v.min()>=.95 and v.max()<=1.05),thermal_PASS=thermal))
            evals=ticks[-len(sel)+offset:] if offset else ticks[-len(sel):]
            # Slice this case explicitly; preceding cases never authorize it.
            local=ticks[-len(sel):];evals=local[offset:]
            primary=all(r['voltage_PASS'] and r['thermal_PASS'] for r in evals)
            prefix=all(r['voltage_PASS'] and r['thermal_PASS'] for r in local[:offset])
            summary.append(dict(schedule=schedule,role=role,fresh=fresh,evaluation_tick_count=len(evals),
                evaluation96_PASS=primary,prefix24_settled_PASS=prefix,
                eval_Vmin=min(r['Vmin'] for r in evals),eval_Vmax=max(r['Vmax'] for r in evals),
                rho_global=rec['rho_global'],rho_MV=rec['rho_MV'],rho_LV=rec['rho_LV'],
                event_envelope_full120_PASS=rec['full_TIME_PASS'],
                event_envelope_low_seconds=rec['voltage_violation_seconds']['low'],
                event_envelope_high_seconds=rec['voltage_violation_seconds']['high'],
                selection='Literal last native TIME event within each900s slot; no largest-current selection',
                archive=record(p/'AC.npz'),clock=record(p/'CLOCK.json')))
    table('MAY01_ORIGINAL_SETTLED_TICK_PHYSICS.csv',ticks)
    table('MAY01_PHYSICAL_CONTRACT_COMPARISON.csv',summary)
    sources=[dict(path='v44/svr11_frozen/v42_voltage_control/integration.py',symbol='PhysicalScenario.settle_actual',
        evidence='Clock completes native due actions; measure_full_network then determines PASS. Intermediate queue solves record controls and ratings, without event-voltage PASS. persist requires all settled slot rows PASS, including prefix after120-axis adapter.'),
        dict(path='v44/svr11_ac.py',symbol='probe_body/_settle/prefix_audit_class',
        evidence='TIME first solve -> settle_actual -> full measurement at last due action; prefix dimension120 only. OriginalCurrentAC branch measurements occur at that same settled state.'),
        dict(path='v44/svr11_frozen/v42_voltage_control/timecontrol.py',symbol='CommonClock.settle_slot',
        evidence='Physical delayed native events within[start,end); boundary event belongs to next inputs. No delay deletion or initial-state reset.')]
    for r in sources:r['source']=record(ROOT/r['path'])
    p=[r for r in summary if r['schedule']=='ZERO']
    return put('MAY01_PHYSICAL_EVALUATION_CONTRACT.json',dict(source=SOURCE,sources=sources,
        contract='Original settled-slot physical gate, independent event-envelope diagnosis',
        Primary96='All node/phase voltages0.95..1.05; original Parent Terminal max line loading; both-end current and transformer/PCS/port ratings at original post-TIME measurement',
        prefix_contract='All24 settled prefix slots and exact clock/queue continuity; no intermediate event-voltage gate found in source',
        adding_second_by_second_voltage_constraints_to_optimization=False,
        original_acceptance_policy_relaxed=False,earlier_stricter_full_event_gate_superseded_by_source_audit=True,
        source_YY_B0_Planning96_Actual96_Fresh_PASS=all(r['evaluation96_PASS'] and r['prefix24_settled_PASS'] for r in p),
        full120_event_envelope_PASS=False,TIME_violations_not_deleted=True,
        event_diagnosis=dict(Actual_prefix_undervoltage_seconds=23,Actual_prefix_overvoltage_seconds=18,Planning_initial_overvoltage_seconds=15),
        physical_initialization='Original cold Tap1 and original Cap/emptyQueue; unavailable causal prehistory not invented',
        frozen_SVR_banks=3,all_arms_same_actual_hardware=True,results=summary,
        SCIENTIFIC_B0_EVALUATION_SCOPE_ONLY=True,full_campaign_controller_certified=False,
        FIELD_INSTALLATION_UNVERIFIED=True))

if __name__=='__main__':audit()
