"""Measured fractional structure, without proposing extra cut families."""
from .base import *
from .diagnostics import topology,mode_rows

def summarize(label):
    filename='BASE_ROOT_LP_SOLUTION.npz' if label=='S0' else label+'_ROOT_LP_SOLUTION.npz'
    with np.load(OUT/filename,allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
    _,_,_,sites,initial,routes,battery=inputs();arcs=topology(sites,routes)
    for unit in initial:
        for k in range(len(arcs)):v.setdefault(f'arc[{unit},{k}]',0.)
        for s in sites:
            for t in range(96):
                for prefix in ['Pch','Pdis','Q']:v.setdefault(f'{prefix}[{unit},{s},{t}]',0.)
    slots=[]
    for u in initial:
        for t in range(96):
            masses=[v[f'arc[{u},{sites.index(s)*96+t}]'] for s in sites]
            qs=[v[f'Q[{u},{s},{t}]'] for s in sites]
            ch=sum(v[f'Pch[{u},{s},{t}]'] for s in sites)
            dis=sum(v[f'Pdis[{u},{s},{t}]'] for s in sites)
            slots.append(dict(unit=u,time=t,positive_sites=sum(x>TOL for x in masses),
                reactive_sites=sum(abs(q)>TOL for q in qs),stay_mass=sum(masses),Pch=ch,Pdis=dis,
                sum_abs_Q=sum(abs(q) for q in qs),
                Q_perspective_utilization=sum(abs(q) for q in qs)/(battery.pcs_kva*sum(masses)) if sum(masses)>TOL else 0.))
    counts={family:sum(TOL<v[f'arc[{u},{k}]']<1-TOL for u in initial for k,a in enumerate(arcs) if (a[-1] is None)==(family=='stay')) for family in ['stay','travel']}
    countmode=sum(TOL<v[f'charge_mode[{u},{t}]']<1-TOL for u in initial for t in range(96))
    mode=mode_rows(v,sites,initial,battery)
    interior=label!='S0' and read(OUT/(label+'_ROOT_LP_OPTIMIZATION.json')).get('interior_fallback',False)
    return dict(candidate=label,solution_kind='optimal interior point' if interior else 'optimal basic point',
        point_specific_fractionality=True,rho=v['rho_max'],fractional_stay=counts['stay'],fractional_travel=counts['travel'],
        fractional_charge_mode=countmode,maximum_sites=max(r['positive_sites'] for r in slots),
        multiple_site_slot_fraction=sum(r['positive_sites']>1 for r in slots)/len(slots),
        multiple_reactive_site_slot_fraction=sum(r['reactive_sites']>1 for r in slots)/len(slots),
        maximum_reactive_sites=max(r['reactive_sites'] for r in slots),
        simultaneous_aggregate_charge_discharge_slots=sum(r['Pch']>TOL and r['Pdis']>TOL for r in slots),
        maximum_Pch=max(r['Pch'] for r in slots),maximum_Pdis=max(r['Pdis'] for r in slots),
        total_Pch_kWh=battery.dt_hours*sum(r['Pch'] for r in slots),
        total_Pdis_kWh=battery.dt_hours*sum(r['Pdis'] for r in slots),
        maximum_mode_hull_residual=max(max(r[h+'_residual'] for h in ['H1','H2','H3']) for r in mode),
        Q_diagnostic_only=True,no_Q_penalty=True)

def run():
    selected=read(OUT/'SELECTED_STRENGTHENING.json');base=summarize('S0');new=summarize(selected['selected'])
    rank=[dict(rank=1,mechanism='fractional route/location with distributed reactive support',
        measured=new,classification='measured remaining fractionality; causal bound contribution not isolated',
        next_question='Can physical integer trajectories realize the spatial and temporal reactive support of this LP point?'),
      dict(rank=2,mechanism='grid feasibility of averaged route/dispatch trajectories',
        classification='untested hypothesis',
        next_question='Even with path-consistent energy, which averaged voltage/thermal requirements cannot be met by individual integer trajectories?'),
      dict(rank=3,mechanism='mode disjunction and arc-energy pooling',
        classification='tested exactly in this task',root_gain=selected['delta_LB'],
        next_question='Evaluate measured root bound gain; a violated point alone does not measure its effect on the optimal face')]
    if not selected['material']:rank[-1]['conclusion']='Tested mode-disjunction and route-energy-pooling mechanisms do not materially explain the current root gap.'
    dump('RESIDUAL_RELAXATION_DIAGNOSIS.json',dict(baseline=base,selected_root=new,ranking=rank,
        material_root_gain=selected['material'],additional_strengthening_families_built=False,
        remaining_implied_gap=selected['implied_gap'],interpretation='LP diagnostics, not a MIP or physical-invalidity certificate',
        optimal_face_note='Fractionality describes the saved point. Interior and basic optima can differ on the same optimal face; counts do not measure causal bound contributions.'))
    text='# Next fractional-structure questions\n\n'
    if not selected['material']:
        text+='Tested mode-disjunction and route-energy-pooling mechanisms do not materially explain the current root gap. The baseline point exhibits both mechanisms, but eliminating that point did not materially raise the best LP bound.\n\n'
    text+='1. Inspect the selected optimum’s fractional location and distributed Q support. Measured maximum simultaneous sites: '+str(new['maximum_sites'])+'; slots with multiple reactive sites: '+str(new['multiple_reactive_site_slot_fraction'])+'.\n'
    text+='2. Determine whether average grid-feasible route/dispatch trajectories decompose into individually grid-feasible physical integer trajectories. This is an untested hypothesis.\n'
    text+='3. Review the tested mode/energy mechanisms on the entire optimal face, using the saved optimum and bound comparisons; do not infer bound gain merely from a cut violation.\n\n'
    text+='No additional strengthening family, solver parameter search, route pruning, Q reserve/penalty or downstream A2/M2/Actual/AC/IEEE8500 run is authorized by this ranking.\n'
    (OUT/'NEXT_MODIFICATIONS.md').write_text(text,encoding='utf8')

if __name__=='__main__':run()
