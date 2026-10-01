"""Independent connected PCS diagnostics and descriptive voltage decomposition."""
import math
import numpy as np
from v42_root.common import *
from v42_native.voltage import Stage,voltage_for
from .grid import coefficients

def supplemental_physical(best,sites,battery):
    v=best['values'];errors=[]
    for u in best['initial_sites']:
        chosen=set(best['chosen_arcs'][u])
        for t in range(96):
            mode=v[f'charge_mode[{u},{t}]']
            if abs(mode-round(mode))>1e-5:errors.append('NONBINARY_MODE')
            for k,s in enumerate(sites):
                c=v[f'Pch[{u},{s},{t}]'];d=v[f'Pdis[{u},{s},{t}]'];q=v[f'Q[{u},{s},{t}]']
                connected=k*96+t in chosen
                if c>battery.p_limit*mode+1e-5 or d>battery.p_limit*(1-mode)+1e-5:errors.append('MODE_DIRECTION')
                if not connected and max(abs(c),abs(d),abs(q))>1e-5:errors.append('DISCONNECTED_PCH_PDIS_Q')
    return dict(charge_mode_and_connection_PASS=not errors,charge_mode_and_connection_violations=errors)

def analyze(bundle,anchor,best,sites,routes,battery):
    if best is None:
        dump('M1_INTERVENTION_REPORT.json',dict(status='NO_INCUMBENT',movement_energy=None,movement_count=None,Q_statistics=None))
        dump('PR105_BLOCKER_M1_RESOLUTION.json',dict(resolved=False,M1_voltage=None,status='NO_INCUMBENT',causal_Q_alone_claim=False))
        (OUT/'M1_Q_UTILIZATION.csv').write_text('unit,slot,connected,site,P_kw,Q_kvar,Q_available_kvar,utilization\n',encoding='utf8')
        return
    v=best['values'];arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    selected={u:[arcs[k] for k in best['chosen_arcs'][u]] for u in best['initial_sites']}
    rows=[];active=[];at79=[];epsilon=1e-6
    for u,path in selected.items():
        for t in range(96):
            a=next(a for a in path if a[1]<=t<a[3]);connected=a[-1] is None;s=a[0]
            p=v[f'Pdis[{u},{s},{t}]']-v[f'Pch[{u},{s},{t}]'] if connected else 0.
            q=v[f'Q[{u},{s},{t}]'] if connected else 0.
            avail=math.sqrt(max(0.,battery.pcs_kva**2-p**2)) if connected else 0.
            ratio=abs(q)/avail if avail>epsilon else (0. if abs(q)<=epsilon else None)
            row=dict(unit=u,slot=t,connected=connected,site=s if connected else None,route_id=a[-1].route_id if not connected else None,
                     route_origin=a[0],route_destination=a[2],route_depart=a[1],route_connect=a[3],P_kw=p,Q_kvar=q,Q_available_kvar=avail,utilization=ratio)
            rows.append(row)
            if connected:active.append(row)
            if t==79:at79.append(row)
    table('M1_Q_UTILIZATION.csv',rows)
    ratios=[r['utilization'] for r in active if r['utilization'] is not None]
    stats=dict(connected_count=len(active),connected_fraction=len(active)/len(rows),Q_active_epsilon_kvar=epsilon,
               Q_active_fraction=sum(abs(r['Q_kvar'])>epsilon for r in active)/len(active) if active else None,
               median_utilization=float(np.median(ratios)) if ratios else None,P95_utilization=float(np.percentile(ratios,95)) if ratios else None,
               max_utilization=max(ratios) if ratios else None,near_cap_threshold=.95,near_cap_fraction=sum(r>=.95 for r in ratios)/len(ratios) if ratios else None,
               formula='abs(Q)/sqrt(max(S_nameplate^2-P_net^2,0)), connected unit/time only',diagnostic_only=True,production_PCS_faces=16,Q_penalty=False)
    movement=[a[-1] for path in selected.values() for a in path if a[-1] is not None]
    dump('M1_INTERVENTION_REPORT.json',dict(movement_energy=sum(r.energy_kwh for r in movement),movement_count=len(movement),Q_statistics=stats,
         selected_routes={u:[dict(route_id=a[-1].route_id,source=a[0],destination=a[2],depart=a[1],connect=a[3],energy_kwh=a[-1].energy_kwh) for a in path if a[-1] is not None] for u,path in selected.items()},
         Q_is_separate_objective=False,reserve_or_CC4_objective=False))
    cert,coeff=coefficients(bundle)
    with np.load(cert['outputs']['voltage']['path'],allow_pickle=False) as z:
        names=next(z[k].astype(str).tolist() for k in z.files if any(w in k.lower() for w in ('node','bus','name')) and z[k].ndim==1 and len(z[k])==len(coeff[0].voltage_constant))
    n=names.index('83.2');c=coeff[79];x=read(LOCAL/'M1/CONTROLS.json')[79];a=np.asarray(anchor['controls'][79]);w=c.voltage_matrix[:,n]
    parts={prefix:sum(float(w[i])*x[i] for i,name in enumerate(c.control_names) if name.startswith(prefix)) for prefix in ('aidc_load_kw','mess_p_kw','mess_q_kvar')}
    final=float(c.voltage_constant[n])+sum(parts.values());bootstrap=float(c.voltage_constant[n]+w@a);band=voltage_for(Stage.M1)
    dump('PR105_BLOCKER_M1_RESOLUTION.json',dict(slot=79,node_phase='83.2',A1_bootstrap_voltage_pu=math.sqrt(max(0,bootstrap)),
         M1_voltage_pu=math.sqrt(max(0,final)),M1_squared_voltage=final,robust_upper_pu=band.upper_pu,upper_margin_pu=band.upper_pu-math.sqrt(max(0,final)),
         resolved=band.lower_squared-1e-5<=final<=band.upper_squared+1e-5,voltage_constant_squared=float(c.voltage_constant[n]),
         fixed_AIDC_contribution_squared=parts['aidc_load_kw'],aggregate_MESS_P_contribution_squared=parts['mess_p_kw'],aggregate_MESS_Q_contribution_squared=parts['mess_q_kvar'],
         connected_units_and_route_state=at79,interpretation='Descriptive decomposition of the same jointly optimized route/P/Q/SOC solution. No isolated Q counterfactual or causal Q-alone claim.',causal_Q_alone_claim=False))
