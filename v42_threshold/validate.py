"""Independent numeric graph, battery and original full-grid validation."""
from collections import defaultdict
import math
from .common import *

@lru_cache(None)
def coefficients():
    from v42_bootstrap.grid import coefficients as inherited
    return inherited(inputs()[0])[1]

def physical(names,values):
    v=dict(zip(map(str,names),map(float,values)));_,_,_,sites,initial,_,battery=inputs();graph=arcs()
    flow_error=occupancy_error=energy_error=initial_error=terminal_error=pcs_violation=mode_violation=0.
    travel_total=0.;details=[]
    for u,origin in sorted(initial.items()):
        net=defaultdict(float);connected={};transit=np.zeros(97);debit=np.zeros(96)
        for k,a in enumerate(graph):
            mass=v.get(f'arc[{u},{k}]',0.)
            net[a[:2]]+=mass;net[a[2:4]]-=mass
            if a[-1] is None:connected[a[:2]]=mass
            else:
                transit[a[1]]+=mass;transit[a[3]]-=mass
                debit[a[1]]+=a[-1].energy_kwh*mass
        for t in range(96):
            for s in sites:flow_error=max(flow_error,abs(net[(s,t)]-int(t==0 and s==origin)))
        terminal_mass=-sum(net[(s,96)] for s in sites);flow_error=max(flow_error,abs(terminal_mass-1))
        transit=np.cumsum(transit);initial_error=max(initial_error,abs(v[f'SOC[{u},0]']-battery.initial))
        terminal_error=max(terminal_error,abs(v[f'SOC[{u},96]']-battery.terminal))
        for t in range(96):
            occupancy=sum(connected.get((s,t),0.) for s in sites)+transit[t]
            occupancy_error=max(occupancy_error,abs(occupancy-1))
            ch=dis=0.;mode=v[f'charge_mode[{u},{t}]']
            for s in sites:
                c=v.get(f'Pch[{u},{s},{t}]',0.);d=v.get(f'Pdis[{u},{s},{t}]',0.);q=v.get(f'Q[{u},{s},{t}]',0.);p=d-c
                weight=connected.get((s,t),0.)
                mode_violation=max(mode_violation,c-battery.p_limit*mode,d-battery.p_limit*(1-mode),
                    c-battery.p_limit*weight,d-battery.p_limit*weight,abs(q)-battery.pcs_kva*weight,-c,-d)
                for f in range(16):
                    pcs_violation=max(pcs_violation,math.cos(2*math.pi*f/16)*p+math.sin(2*math.pi*f/16)*q-battery.pcs_kva*math.cos(math.pi/16)*weight)
                ch+=c;dis+=d
            expected=v[f'SOC[{u},{t}]']+battery.dt_hours*(battery.eta_charge*ch-dis/battery.eta_discharge)-debit[t]
            energy_error=max(energy_error,abs(expected-v[f'SOC[{u},{t+1}]']))
        travel_total+=float(debit.sum())
        details.append(dict(unit=u,SOC0=v[f'SOC[{u},0]'],SOC58=v[f'SOC[{u},58]'],SOC66=v[f'SOC[{u},66]'],SOC96=v[f'SOC[{u},96]'],travel_energy_kwh=float(debit.sum())))
    maximum=max(flow_error,occupancy_error,energy_error,initial_error,terminal_error,pcs_violation,mode_violation)
    return dict(PASS=maximum<=MATRIX_TOL,max_violation=maximum,route_flow_residual=flow_error,occupancy_residual=occupancy_error,
        SOC_recurrence_residual=energy_error,initial_SOC_residual=initial_error,terminal_SOC_residual=terminal_error,
        PCS16_violation=max(0.,pcs_violation),mode_and_connection_violation=max(0.,mode_violation),travel_energy_kwh=travel_total,units=details,
        outside_mode_fractionality_is_authorized_relaxation=True,no_clipping_or_repair=True,full96=True)

def grid(names,values):
    from v42_forensic.forensic import control,faces
    from v42_bootstrap.grid import grid_report
    bundle,anchor,_,_,initial,_,_=inputs();v=dict(zip(map(str,names),map(float,values)));rho=v['rho_max'];controls=[];slots=[]
    for t,c in enumerate(coefficients()):
        x=control(c,v,anchor,sorted(initial),t);controls.append(x.tolist())
        loading=faces(c,x)[0];mask=np.asarray([not n.lower().startswith('transformer.') for n in c.branch_names])
        slots.append(dict(slot=t,recomputed_original_P1=float(loading[mask].max())))
    report=grid_report(bundle,controls,rho,tolerance=MATRIX_TOL)
    recomputed=max(r['recomputed_original_P1'] for r in slots)
    return dict(PASS=bool(report['PASS'] and recomputed<=rho+RHO_TOL),robust_grid=report,
        independently_recomputed_P1=recomputed,epigraph_slack=rho-recomputed,
        objective_recomputation_violation=max(0.,recomputed-rho),rho_epigraph_need_not_be_tight_with_zero_objective=True,
        full96=True,AIDC_anchor_unchanged=True,no_Actual_PQ_repair=True),slots

def validate_point(m,names,values):
    assert np.array_equal(names,axis()['names'])
    original=matrix_validation(m,values,include_threshold=False);threshold=matrix_validation(m,values)
    frac=float(np.max(abs(values[domains()]-np.rint(values[domains()]))))
    allfrac=float(np.max(abs(values[axis()['original_types']=='B']-np.rint(values[axis()['original_types']=='B']))))
    phys=physical(names,values);electrical,slots=grid(names,values);rho=float(values[list(names).index('rho_max')])
    b3valid=bool(original['PASS'] and frac<=INTEGER_TOL and phys['PASS'] and electrical['PASS'])
    certificate=threshold_guard(rho,electrical['independently_recomputed_P1'],threshold['max_residual'],frac,phys['PASS'],electrical['PASS'])
    return dict(B3_feasible_PASS=b3valid,threshold_certificate_PASS=certificate,threshold_matrix=threshold,original_B3_matrix=original,
        B3_binary_max_fractionality=frac,all_original_binary_max_fractionality=allfrac,physical=phys,grid=electrical,
        rho=rho,threshold=T,threshold_slack=T-rho,recomputed_threshold_slack=T-electrical['independently_recomputed_P1'],
        required_threshold_margin=THRESHOLD_MARGIN,threshold_not_relaxed=True,
        original_M1_UB_eligible=original_UB_eligible(dict(B3_feasible_PASS=b3valid),allfrac),
        partial_feasible_upper=rho if b3valid else None,original_feasible_UB=rho if original_UB_eligible(dict(B3_feasible_PASS=b3valid),allfrac) else None,
        actual_repair=False,clip=False),slots
