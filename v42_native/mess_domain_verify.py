"""Independent original-DAG and actual-row physical prescreen verification."""
from collections import defaultdict, deque
from fractions import Fraction as F
from time import perf_counter
from .contracts import digest, require

BATTERY_FIELDS=('minimum','maximum','initial','terminal','p_limit','pcs_kva','eta_charge','eta_discharge','dt_hours')

def verify_domain(domain):
    """Independent adjacency traversal, not the producer's time-sorted scan."""
    began=perf_counter();forward_adj=defaultdict(list);reverse_adj=defaultdict(list)
    require(domain.horizon>0,'MESS_PHYSICAL_VERIFY_HORIZON')
    b=dict(zip(BATTERY_FIELDS,domain.battery))
    require(b['dt_hours']==.25 and 0<b['eta_charge']<=1 and 0<b['eta_discharge']<=1,
        'MESS_PHYSICAL_VERIFY_ENERGY_UNITS')
    expected_arcs=tuple([(s,t,s,t+1,None) for s in domain.sites for t in range(domain.horizon)]+
        [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(domain.routes)])
    require(domain.arcs==expected_arcs,'MESS_PHYSICAL_VERIFY_RAW_GRAPH_DRIFT')
    for k,(s,t,d,end,r) in enumerate(domain.arcs):
        require(s in domain.sites and d in domain.sites and 0<=t<end<=domain.horizon,'MESS_PHYSICAL_VERIFY_NOT_DAG')
        forward_adj[s,t].append((d,end));reverse_adj[d,end].append((s,t))
    def reach(seeds,adj):
        found=set(seeds);queue=deque(found)
        while queue:
            for v in adj[queue.popleft()]:
                if v not in found:found.add(v);queue.append(v)
        return found
    backward=reach(((s,domain.horizon) for s in domain.sites),reverse_adj)
    require(tuple((u.mess,u.origin) for u in domain.units)==domain.initial,'MESS_PHYSICAL_VERIFY_UNIT_AXIS')
    for unit in domain.units:
        forward=reach(((unit.origin,0),),forward_adj)
        expected=tuple(k for k,a in enumerate(domain.arcs) if a[:2] in forward and a[2:4] in backward)
        expected_set=set(expected)
        require(unit.retained==expected and set(unit.forward)==forward and set(unit.backward)==backward,'MESS_PHYSICAL_VERIFY_MASK_DRIFT')
        removed=tuple((k,'FORWARD_UNREACHABLE' if a[:2] not in forward else 'BACKWARD_DEAD_END')
            for k,a in enumerate(domain.arcs) if k not in expected_set)
        require(unit.removals==removed,'MESS_PHYSICAL_VERIFY_ZERO_WITNESS_DRIFT')
        require(len(unit.slots)==domain.horizon and all(row[0]==t for t,row in enumerate(unit.slots)),
            'MESS_PHYSICAL_VERIFY_SLOT_AXIS')
        states={v for k in expected for v in (domain.arcs[k][:2],domain.arcs[k][2:4])}
        for t,row in enumerate(unit.slots):
            indices=[k for k in expected if domain.arcs[k][1]==t]
            stays=sum(domain.arcs[k][-1] is None for k in indices)
            require(row==(t,len(indices),stays,len(indices)-stays,sum(v[1]==t for v in states),
                stays,stays,stays,1,1,16*stays),'MESS_PHYSICAL_VERIFY_SLOT_COUNTS_DRIFT')
        require(unit.terminal_states==sum(v[1]==domain.horizon for v in states),
            'MESS_PHYSICAL_VERIFY_TERMINAL_COUNTS_DRIFT')
        b=dict(zip(BATTERY_FIELDS,domain.battery));limit=F(b['p_limit']);H=domain.horizon
        c=F(float(b['dt_hours']*b['eta_charge']))*limit
        p=F(float(b['dt_hours']/b['eta_discharge']))*limit
        lows=[F(b['minimum'])]*(H+1);highs=[F(b['maximum'])]*(H+1)
        lows[0]=highs[0]=F(b['initial']);lows[H]=highs[H]=F(b['terminal'])
        costs=defaultdict(lambda:F(0))
        for k in expected:
            a=domain.arcs[k]
            if a[-1] is not None:costs[a[1]]=max(costs[a[1]],F(float(a[-1].energy_kwh)))
        for t in range(H):
            lows[t+1]=max(lows[t+1],lows[t]-p-costs[t]);highs[t+1]=min(highs[t+1],highs[t]+c)
        for t in reversed(range(H)):
            lows[t]=max(lows[t],lows[t+1]-c);highs[t]=min(highs[t],highs[t+1]+p+costs[t])
        require(unit.global_soc==tuple((t,lows[t],highs[t]) for t in range(H+1)),
            'MESS_PHYSICAL_VERIFY_GLOBAL_SOC_DIAGNOSTIC_DRIFT')
    require(digest(domain.scientific_state())==domain.state_sha,'MESS_PHYSICAL_VERIFY_STATE_SHA_DRIFT')
    return dict(PASS=True,original_integer_and_fractional_LP_zero_masks_verified=True,
        original_nonnegative_unit_DAG_flow_required=True,structural_arcs_checked=len(domain.arcs)*len(domain.units),
        terminal_site_contract='ANY_SITE_AT_H',travel_energy_debit='departure -> SOC[departure+1]',
        actual_original_matrix_row_bridge_required=True,
        SOC_arc_deletions_applied=0,SOC_bound_changes_applied=0,Native_optimize_calls=0,
        independent_verifier_wall_seconds=perf_counter()-began)

def verify_original_rows(domain,A,d):
    """Bridge the input-only graph theorem to every actual flow/energy row.

    No producer/model is invoked. Coefficients are stored binary rationals.
    Applies equally to B2/B3 and M1/M2 before Native optimization.
    """
    proof=verify_domain(domain);began=perf_counter();names=list(map(str,d['names']))
    lookup={name:j for j,name in enumerate(names)};b=dict(zip(BATTERY_FIELDS,domain.battery));H=domain.horizon
    require(A.shape[1]==len(names) and len(lookup)==len(names),'MESS_PHYSICAL_ORIGINAL_COLUMN_AXIS')
    c=F(float(b['dt_hours']*b['eta_charge']));p=F(float(b['dt_hours']/b['eta_discharge']))
    outgoing=defaultdict(dict);incoming=defaultdict(dict);travel=defaultdict(dict);terminal=defaultdict(dict)
    expected_arcs=set();expected_power=set()
    for unit in domain.units:
        for k in unit.retained:
            name=f'arc[{unit.mess},{k}]';expected_arcs.add(name)
            require(name in lookup,'MESS_PHYSICAL_ORIGINAL_RETAINED_ARC_MISSING');j=lookup[name]
            require(d['types'][j]=='B' and d['lower'][j]==0 and d['upper'][j]==1,
                'MESS_PHYSICAL_ORIGINAL_NONNEGATIVE_ARC_BOX')
            s,t,dest,end,route=domain.arcs[k]
            outgoing[unit.mess,s,t][j]=F(1);incoming[unit.mess,dest,end][j]=F(1)
            if end==H:terminal[unit.mess][j]=F(1)
            if route is not None and route.energy_kwh:travel[unit.mess,t][j]=F(float(route.energy_kwh))
            if route is None:
                for fam in ('Pch','Pdis','Q'):expected_power.add(f'{fam}[{unit.mess},{s},{t}]')
        for t in range(H+1):
            name=f'SOC[{unit.mess},{t}]';require(name in lookup,'MESS_PHYSICAL_ORIGINAL_SOC_MISSING')
            j=lookup[name];require(d['types'][j]=='C' and d['lower'][j]==b['minimum'] and d['upper'][j]==b['maximum'],
                'MESS_PHYSICAL_ORIGINAL_SOC_BOX_DRIFT')
    require({name for name in names if name.startswith('arc[')}==expected_arcs,'MESS_PHYSICAL_ORIGINAL_ARC_COVER_DRIFT')
    require({name for name in names if name.split('[',1)[0] in ('Pch','Pdis','Q')}==expected_power,
        'MESS_PHYSICAL_ORIGINAL_CONNECTED_PQ_COVER_DRIFT')
    def row(i):
        a,z=A.indptr[i:i+2]
        return {int(j):F(float(w)) for j,w in zip(A.indices[a:z],A.data[a:z]) if w},F(float(d['rhs'][i]))
    families=defaultdict(list)
    for i,name in enumerate(d['row_names']):
        family=str(name).split('[',1)[0]
        if family in ('flow','terminal_location','initial_SOC','terminal_SOC','energy_balance'):families[family].append(i)
    cursor=0
    for unit in domain.units:
        for site in domain.sites:
            for t in range(H):
                require(cursor<len(families['flow']),'MESS_PHYSICAL_ORIGINAL_FLOW_COVER')
                i=families['flow'][cursor];cursor+=1;terms,rhs=row(i);expected=defaultdict(F,outgoing[unit.mess,site,t])
                for j,w in incoming[unit.mess,site,t].items():expected[j]-=w
                require(d['sense'][i]=='=' and terms=={j:w for j,w in expected.items() if w}
                    and rhs==int(t==0 and site==unit.origin),'MESS_PHYSICAL_ORIGINAL_UNIT_DAG_FLOW_DRIFT')
    require(cursor==len(families['flow']) and len(families['terminal_location'])==len(domain.units),
        'MESS_PHYSICAL_ORIGINAL_FLOW_OR_TERMINAL_COVER')
    for unit,i in zip(domain.units,families['terminal_location']):
        terms,rhs=row(i);require(d['sense'][i]=='=' and terms==terminal[unit.mess] and rhs==1,
            'MESS_PHYSICAL_ORIGINAL_ANY_TERMINAL_DRIFT')
    for family,t,value in (('initial_SOC',0,b['initial']),('terminal_SOC',H,b['terminal'])):
        require(len(families[family])==len(domain.units),'MESS_PHYSICAL_ORIGINAL_SOC_ENDPOINT_COVER')
        for unit,i in zip(domain.units,families[family]):
            terms,rhs=row(i);require(d['sense'][i]=='=' and terms=={lookup[f'SOC[{unit.mess},{t}]']:F(1)} and rhs==F(value),
                'MESS_PHYSICAL_ORIGINAL_SOC_ENDPOINT_DRIFT')
    require(len(families['energy_balance'])==len(domain.units)*H,'MESS_PHYSICAL_ORIGINAL_ENERGY_ROW_COVER')
    seen=set()
    for i in families['energy_balance']:
        terms,rhs=row(i);soc=[(names[j],w) for j,w in terms.items() if names[j].startswith('SOC[')]
        require(len(soc)==2,'MESS_PHYSICAL_ORIGINAL_ENERGY_SOC_AXIS')
        parsed=[(name[4:-1].split(',')[0],int(name[4:-1].split(',')[1]),w) for name,w in soc]
        parsed.sort(key=lambda v:v[1]);(u,t,w),(uu,end,ww)=parsed
        require(u==uu and end==t+1 and w==-1 and ww==1 and (u,t) not in seen,
            'MESS_PHYSICAL_ORIGINAL_ENERGY_TIME_DRIFT');seen.add((u,t))
        expected={lookup[f'SOC[{u},{t}]']:F(-1),lookup[f'SOC[{u},{t+1}]']:F(1)}
        for site in domain.sites:
            for family,weight in (('Pch',-c),('Pdis',p)):
                name=f'{family}[{u},{site},{t}]'
                if name in lookup:expected[lookup[name]]=weight
        expected.update(travel[u,t])
        require(d['sense'][i]=='=' and rhs==0 and terms==expected,
            'MESS_PHYSICAL_ORIGINAL_ENERGY_DEBIT_OR_COEFFICIENT_DRIFT')
    return dict(proof,actual_original_matrix_row_bridge_required=False,actual_original_flow_rows_checked=cursor,
        actual_original_energy_rows_checked=len(seen),actual_departure_energy_debit_verified=True,
        exact_stored_charge_coefficient=str(c),exact_stored_discharge_coefficient=str(p),
        original_matrix_row_verifier_wall_seconds=perf_counter()-began)
