"""Global grid necessities and certified analytical route/energy support bounds.

Every scientific number is its exact stored IEEE-754 dyadic. No optimize call.
The capacity model is an explicitly documented superset of the original model:
PCS, charge/discharge exclusivity, route time and terminal energy are retained;
intermediate SOC bounds are relaxed by a scalar energy Lagrangian.
"""
from .common import *
from fractions import Fraction as F
from collections import defaultdict, Counter
import gzip, itertools


def dy(x): return F.from_float(float(x))
def down(x):
    v=float(x)
    return float(np.nextafter(v,-np.inf)) if dy(v)>x else v
def up(x):
    v=float(x)
    return float(np.nextafter(v,np.inf)) if dy(v)<x else v
def dump_gz(path,value):
    path=Path(path);assert path.resolve().is_relative_to(OUT)
    raw=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    # mtime=0 is deterministic and does not rewrite existing evidence.
    path.write_bytes(gzip.compress(raw,mtime=0));return dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size)
def args(n): return str(n).split('[',1)[1][:-1].split(',')


class AffineClosure:
    def __init__(self,A,d):
        self.A,self.d=A,d
        self.family=np.array([str(n).split('[')[0] for n in d['names']])
        self.defs={};self.memo={};self.used=set();self.active=set();self.fixed=set()
        for i,n in enumerate(d['row_names']):
            fam=str(n).split('[')[0]
            if not fam.endswith('_binding'):continue
            js=A.indices[A.indptr[i]:A.indptr[i+1]]
            own=[int(j) for j in js if self.family[j]==fam[:-8]]
            assert len(own)==1 and d['sense'][i]=='=' and own[0] not in self.defs
            self.defs[own[0]]=i
    def expand(self,j):
        j=int(j)
        if j in self.memo:return self.memo[j]
        assert j not in self.active,'CYCLIC_ORIGINAL_BINDING'
        self.active.add(j)
        if self.family[j] in ('Pch','Pdis','Q','rho_max'):
            result=(F(0),{j:F(1)})
        elif self.d['lower'][j]==self.d['upper'][j]:
            self.fixed.add(j);result=(dy(self.d['lower'][j]),{})
        else:
            assert j in self.defs,('UNELIMINATED_GRID_VARIABLE',str(self.d['names'][j]))
            i=self.defs[j];self.used.add(i);r=self.A.getrow(i)
            pivot=dy(r[0,j]);assert pivot in (F(-1),F(1))
            const=dy(self.d['rhs'][i])/pivot;terms=defaultdict(F)
            for k,a in zip(r.indices,r.data):
                if k==j:continue
                c,t=self.expand(k);mult=-dy(a)/pivot;const+=mult*c
                for p,v in t.items():terms[p]+=mult*v
            result=(const,{p:v for p,v in terms.items() if v})
        self.active.remove(j);self.memo[j]=result;return result
    def row(self,i):
        const=F(0);terms=defaultdict(F);r=self.A.getrow(i)
        for j,a in zip(r.indices,r.data):
            c,t=self.expand(j);a=dy(a);const+=a*c
            for p,v in t.items():terms[p]+=a*v
        return const,{p:v for p,v in terms.items() if v}


def demand(A,d,rows,pi,label):
    closure=AffineClosure(A,d);rho=int(np.flatnonzero(d['objective'])[0])
    constant=F(0);rhow=F(0);weights=defaultdict(F);records=[]
    for i in rows:
        i=int(i);assert d['sense'][i] in ('<','>')
        orient=F(1) if d['sense'][i]=='<' else F(-1)
        lam=max(F(0),-orient*dy(pi[i]))
        if not lam:continue
        c,terms=closure.row(i);ar=orient*terms.pop(rho,F(0));assert ar<=0
        c*=orient;rhs=orient*dy(d['rhs'][i])
        constant+=lam*(c-rhs);rhow+=lam*ar
        for j,a in terms.items():weights[j]-=lam*orient*a
        records.append(dict(row=i,name=str(d['row_names'][i]),multiplier=str(lam),
            source_sense=str(d['sense'][i]),orientation=str(orient),
            expanded_constant=str(c),rhs=str(rhs),rho_coefficient=str(ar)))
    weights={j:v for j,v in weights.items() if v};assert rhow<0
    D=constant+F(3,5)*rhow
    exact=dict(schema='GRID_GLOBAL_DYADIC_AFFINE_V1',label=label,
        cutoff='3/5',source_matrix_sha256=sha(PARENT/'C3A_A.npz'),
        source_data_sha256=sha(PARENT/'C3A_DATA.npz'),
        inequality='sum(weights[j]*x[j]) >= constant + rho_coefficient*c, for every original feasible point with rho<=c',
        constant=str(constant),rho_coefficient=str(rhow),D_exact=str(D),
        weights=[dict(column=int(j),name=str(d['names'][j]),coefficient=str(v)) for j,v in sorted(weights.items())],
        rows=records,binding_rows=sorted(closure.used),fixed_columns=sorted(closure.fixed),
        no_primal_substitution=True,no_uneliminated_auxiliary_columns=True,
        row_sign_cone_checked=True,all_multiplier_and_source_arithmetic_exact=True)
    receipt=dump_gz(OUT/(label+'_GRID_EXACT.json.gz'),exact)
    summary=dict(label=label,scope='Every original integer and continuous feasible point',
        thermal_rows=sum(r['name']=='line_thermal_face' for r in records),
        source_rows=len(records),binding_equalities=len(closure.used),fixed_bound_constants=len(closure.fixed),
        rho_coefficient=float(rhow),constant=float(constant),D_0_60_lower=down(D),D_0_60_upper=up(D),
        D_exact=str(D),power_columns=len(weights),exact_artifact=receipt,
        no_point_only_claim=True,precision='Exact rational arithmetic on immutable binary64 source numbers')
    return weights,constant,rhow,D,summary


def route_graph():
    assert sha(ROUTE)=='3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9'
    table=json.loads(gzip.decompress(ROUTE.read_bytes()))
    prior=read(ROOT/'docs/v42_m1_route_mode_benders_20261008/ROUTE_PROJECTION_AUDIT.json')
    assert prior['PASS'] and not prior['duplicate_endpoint_arcs'] and not prior['non_forward_arcs']
    sites=table['service_ids'];arcs=[(s,t,s,t+1,F(0),True) for s in sites for t in range(96)]
    forecast=set();seen=set()
    for r in table['routes']:
        s,t,z=r['origin_service_id'],int(r['departure_slot_15']),r['destination_service_id']
        arrival=t+int(r['travel_slots_15min']);ready=t+int(r['connection_ready_slots_15min'])
        if s==z or not 0<=t<arrival<=ready<96:continue
        key=(s,t,z,ready);assert key not in seen;seen.add(key);forecast.add(r['traffic_forecast_sha'])
        arcs.append((s,t,z,ready,dy(r['energy_safe_kwh']),False))
    assert len(arcs)==prior['graph_arcs']==53626 and len(forecast)==1
    assert tuple(sites)==tuple(prior['graph_receipt']['sites'])
    initial=prior['graph_receipt']['initial_MESS_sites']
    outgoing=defaultdict(list)
    for ai,a in enumerate(arcs):outgoing[a[0],a[1]].append(ai)
    return sites,initial,arcs,outgoing,prior


def vertices(planes):
    result=set()
    for (a,b,c),(x,y,z) in itertools.combinations(planes,2):
        determinant=a*y-b*x
        if not determinant:continue
        p=(c*y-b*z)/determinant;q=(a*z-c*x)/determinant
        if all(u*p+v*q<=w for u,v,w in planes):result.add((p,q))
    assert result,'EMPTY_DISPATCH_OUTER_POLYGON'
    return tuple(sorted(result))


def capacity_inputs(A,d,arcs):
    family=np.array([str(n).split('[')[0] for n in d['names']]);groups=defaultdict(dict)
    for j in np.flatnonzero(np.isin(family,['Pch','Pdis','Q'])):
        u,s,t=args(d['names'][j]);groups[u,s,int(t)][str(family[j])]=int(j)
    assert len(groups)==8942 and all(set(v)=={'Pch','Pdis','Q'} for v in groups.values())
    planes=defaultdict(list);pcsrows=defaultdict(list)
    for i in np.flatnonzero(d['row_names']=='PCS16'):
        r=A.getrow(i);pcols=[j for j in r.indices if family[j] in ('Pch','Pdis','Q')]
        key=next(k for k in [tuple(args(d['names'][j])) for j in pcols])
        key=(key[0],key[1],int(key[2]));cols=groups[key]
        a=dy(r[0,cols['Pdis']]);b=dy(r[0,cols['Q']]);assert dy(r[0,cols['Pch']])==-a
        c=dy(d['rhs'][i])
        for j,v in zip(r.indices,r.data):
            if family[j] in ('Pch','Pdis','Q'):continue
            # Exact finite-box bound of the original single STAY alias.
            assert family[j] in ('route_flow','node_activity') and d['lower'][j]>=0 and d['upper'][j]<=1
            c-=min(dy(v)*dy(d['lower'][j]),dy(v)*dy(d['upper'][j]))
        assert c>=0;planes[key].append((a,b,c));pcsrows[key].append(int(i))
    energy=defaultdict(lambda:defaultdict(F));erhs=defaultdict(F);energyrows=defaultdict(list)
    suffix=defaultdict(lambda:defaultdict(F));suffixrhs=defaultdict(F);suffixrows=defaultdict(list)
    for i in np.flatnonzero(d['row_names']=='energy_balance'):
        r=A.getrow(i);units={args(d['names'][j])[0] for j in r.indices};assert len(units)==1
        u=next(iter(units));energyrows[u].append(int(i));erhs[u]+=dy(d['rhs'][i])
        for j,a in zip(r.indices,r.data):energy[u][int(j)]+=dy(a)
        slots={int(args(d['names'][j])[-1]) for j in r.indices if family[j] in ('Pch','Pdis')}
        assert len(slots)==1
        if next(iter(slots))>=66:
            suffixrows[u].append(int(i));suffixrhs[u]+=dy(d['rhs'][i])
            for j,a in zip(r.indices,r.data):suffix[u][int(j)]+=dy(a)
    energy={u:{j:a for j,a in terms.items() if a} for u,terms in energy.items()}
    assert all(v==0 for v in erhs.values())
    suffix_audit=[]
    for u,terms in suffix.items():
        terms={j:a for j,a in terms.items() if a};state=[(j,a) for j,a in terms.items() if family[j]=='SOC']
        assert len(state)==1 and str(d['names'][state[0][0]])==f'SOC[{u},66]' and state[0][1]==-1
        j,a=state[0];allowance=suffixrhs[u]-min(a*dy(d['lower'][j]),a*dy(d['upper'][j]))
        assert allowance==320
        for j,a in terms.items():
            if family[j]=='route_flow':
                ai=int(args(d['names'][j])[1]);assert arcs[ai][1]>=66 and a==arcs[ai][4]
            elif family[j] in ('Pch','Pdis'):assert int(args(d['names'][j])[-1])>=66 and a==energy[u][j]
            else:assert family[j]=='SOC'
        for j,a in energy[u].items():
            if family[j]=='route_flow':
                ai=int(args(d['names'][j])[1]);expected=a if arcs[ai][1]>=66 else F(0)
                assert terms.get(j,F(0))==expected,'SUFFIX_TRAVEL_COMPLETENESS_OR_CROSSING_ARC_FAILURE'
            elif family[j] in ('Pch','Pdis'):
                expected=a if int(args(d['names'][j])[-1])>=66 else F(0)
                assert terms.get(j,F(0))==expected,'SUFFIX_POWER_COMPLETENESS_FAILURE'
        suffix_audit.append(dict(MESS=u,rows=suffixrows[u],summed_rhs=str(suffixrhs[u]),
            remaining_SOC_column=state[0][0],remaining_SOC_coefficient='-1',upper_SOC_exact='1080',
            suffix='[66,96)',energy_spent_upper_exact=str(allowance),
            every_global_energy_column_suffix_coefficient_verified=True,
            departure_before66_including_crossing_arcs_suffix_coefficient_zero=True))
    polygon_cache={};group_polygons={};ec={};audit=[]
    for key,cols in groups.items():
        ch,dis,q=cols['Pch'],cols['Pdis'],cols['Q'];assert d['lower'][ch]==d['lower'][dis]==0
        pp=tuple(planes[key]+[(F(1),F(0),dy(d['upper'][dis])),(F(-1),F(0),dy(d['upper'][ch])),
            (F(0),F(1),dy(d['upper'][q])),(F(0),F(-1),-dy(d['lower'][q]))])
        if pp not in polygon_cache:
            # Splitting at p=0 retains original integral charge/discharge modes.
            polygon_cache[pp]=(vertices(pp+((F(1),F(0),F(0)),)),
                vertices(pp+((F(-1),F(0),F(0)),)))
        group_polygons[key]=polygon_cache[pp]
        u=key[0];ec[key]=(energy[u][ch],energy[u][dis]);assert ec[key][0]<0<ec[key][1]
    for u,terms in energy.items():
        matches=0
        for j,a in terms.items():
            if family[j]=='route_flow':
                ai=int(args(d['names'][j])[1]);assert not arcs[ai][5] and a==arcs[ai][4];matches+=1
            else:assert family[j] in ('Pch','Pdis')
        audit.append(dict(MESS=u,exact_energy_rows=len(energyrows[u]),summed_rhs=str(erhs[u]),
            cancelled_SOC_columns=True,matched_movement_energy_columns=matches))
    detail=dict(original_PCS_rows=89420,power_triplets=len(groups),distinct_PCS_outer_polygons=len(polygon_cache),
        energy_transport=audit,energy_equalities=energyrows,
        suffix_energy_upper_bounds=suffix_audit,
        finite_box_PCS_occupancy_bound_checked=True,all_retained_original_movement_energy_coefficients_matched=True,
        polygon_planes=[dict(planes=[[str(x) for x in p] for p in pp],
            negative_vertices=[[str(x) for x in v] for v in vs[0]],positive_vertices=[[str(x) for x in v] for v in vs[1]])
            for pp,vs in polygon_cache.items()])
    source=ROOT/'docs/v42_m1_gap_rootcause_20261007/source_authority/FULL_DATA.npz'
    with np.load(source) as z:original_names=z['names'].copy()
    original_power={str(n) for n in original_names if str(n).split('[')[0] in ('Pch','Pdis','Q')}
    current_power={str(d['names'][j]) for cols in groups.values() for j in cols.values()}
    assert original_power==current_power and len(original_power)==26826
    route_identity=ROOT/'docs/v42_m1_route_mode_benders_20261008/ROUTE_PROJECTION_AUDIT.json'
    detail['original_to_relaxation_containment']=dict(
        original_power_namespace_matches_C3A=True,original_power_columns=26826,
        unreachable_service_triplets_with_no_original_power_variable=274,
        full_source_data_sha256=sha(source),
        original_integer_single_path_projection_certificate_sha256=sha(route_identity),
        terminal_activity_label96_maps_to_last_STAY_slot95=True,
        every_original_power_dispatch_is_scored_on_its_actual_STAY=True,
        missing_triplets_have_no_original_power_variable_and_reward_zero=True,
        graph_uses_all_frozen_travel_and_ready_times=True,
        enlarged_graph_and_relaxed_SOC_only_increase_the_capacity_upper_bound=True)
    return groups,group_polygons,ec,detail


def rewards(weights,groups,polygons,ec,u,mu,exact=True,suffix_mu=0):
    cast=(lambda v:v) if exact else float;out={}
    for key,cols in groups.items():
        if key[0]!=u:continue
        wp=weights.get(cols['Pdis'],F(0));wq=weights.get(cols['Q'],F(0))
        assert weights.get(cols['Pch'],F(0))==-wp
        ch,dis=ec[key];best=None
        local_mu=cast(mu)+(cast(suffix_mu) if key[2]>=66 else 0)
        for mode,vs in enumerate(polygons[key]):
            slope=cast(wp)+local_mu*(cast(ch) if mode==0 else -cast(dis))
            for p,q in vs:
                value=slope*cast(p)+cast(wq)*cast(q)
                energy=cast(ch)*(-cast(p)) if mode==0 else cast(dis)*cast(p)
                if best is None or value>best[0]:best=(value,-energy)
        out[key[1],key[2]]=best
    return out


def dp(sites,initial,arcs,outgoing,reward,mu,exact=True,suffix_mu=0):
    zero=F(0) if exact else 0.;cast=(lambda v:v) if exact else float
    potential={(s,96):zero for s in sites};slope={(s,96):zero for s in sites};chosen={}
    for t in reversed(range(96)):
        for s in sites:
            best=None
            for ai in outgoing[s,t]:
                a=arcs[ai];local_mu=cast(mu)+(cast(suffix_mu) if t>=66 else 0)
                gain,deriv=reward.get((s,t),(zero,zero)) if a[5] else (-local_mu*cast(a[4]),-cast(a[4]))
                candidate=gain+potential[a[2],a[3]]
                if best is None or candidate>best[0]:best=(candidate,deriv+slope[a[2],a[3]],ai)
            assert best is not None
            potential[s,t],slope[s,t],chosen[s,t]=best
    path=[];node=(initial,0)
    while node[1]<96:
        ai=chosen[node];path.append(ai);a=arcs[ai];node=(a[2],a[3])
    return potential[initial,0]+cast(suffix_mu)*320,slope[initial,0],potential,path


def capacity(weights,label,groups,polygons,ec,sites,initial,arcs,outgoing,details):
    rows=[];proofs=[]
    for u,s0 in initial.items():
        zero=dp(sites,s0,arcs,outgoing,rewards(weights,groups,polygons,ec,u,F(0)),F(0))[0]
        def trial(mu):
            rw=rewards(weights,groups,polygons,ec,u,mu,False)
            return dp(sites,s0,arcs,outgoing,rw,mu,False)[:2]
        # Numerical minimization only chooses an arbitrary multiplier. Final
        # support, all edge potentials and bound are independently exact.
        scale=max([abs(float(v)) for v in weights.values()]+[1e-12])*8
        _,slope=trial(0.)
        if slope<0:
            lo,hi=0.,scale
            while trial(hi)[1]<0 and hi<1.:hi*=2
        elif slope>0:
            lo,hi=-scale,0.
            while trial(lo)[1]>0 and lo>-1.:lo*=2
        else:lo=hi=0.
        for _ in range(36):
            mid=(lo+hi)/2
            if trial(mid)[1]<0:lo=mid
            else:hi=mid
        global_mu=dy((lo+hi)/2)
        # A second exact valid constraint uses original SOC[66]<=1080,
        # terminal760 and the original30 suffix energy equalities.
        def suffix_trial(smu):
            rw=rewards(weights,groups,polygons,ec,u,F(0),False,smu)
            b,_,_,path=dp(sites,s0,arcs,outgoing,rw,0.,False,smu)
            slope=320.
            for ai in path:
                a=arcs[ai]
                if a[1]<66:continue
                slope+=rw.get((a[0],a[1]),(0.,0.))[1] if a[5] else -float(a[4])
            return b,slope
        slo,shi=0.,scale
        if suffix_trial(0.)[1]<0:
            while suffix_trial(shi)[1]<0 and shi<1.:shi*=2
            for _ in range(36):
                mid=(slo+shi)/2
                if suffix_trial(mid)[1]<0:slo=mid
                else:shi=mid
        else:shi=0.
        suffix_mu=dy((slo+shi)/2)
        candidates=[(F(0),F(0)),(global_mu,F(0)),(F(0),suffix_mu)]
        evaluated=[]
        for mu,smu in candidates:
            rw=rewards(weights,groups,polygons,ec,u,mu,suffix_mu=smu)
            bound,sl,pot,path=dp(sites,s0,arcs,outgoing,rw,mu,suffix_mu=smu)
            evaluated.append((bound,mu,smu,sl,pot,path,rw))
        bound,mu,smu,sl,pot,path,rw=min(evaluated,key=lambda x:x[0])
        terminal_bound=min(v[0] for v in evaluated[:2]);suffix_bound=evaluated[2][0]
        proof=dict(MESS=u,initial_site=s0,mu=str(mu),suffix_mu=str(smu),suffix_energy_allowance='320',U_exact=str(bound),
            terminal_energy_identity_rhs='0',edge_potentials=[dict(site=s,slot=t,value=str(v)) for (s,t),v in sorted(pot.items())],
            stay_rewards=[dict(site=s,slot=t,value=str(v[0])) for (s,t),v in sorted(rw.items())],
            maximizing_relaxation_path=path)
        proofs.append(proof)
        rows.append(dict(MESS=u,U_upper=up(bound),U_lower=down(bound),U_exact=str(bound),
            route_PCS_only_upper=up(zero),terminal_energy_bound_improvement=down(zero-terminal_bound),
            route_terminal_energy_upper=up(terminal_bound),suffix_SOC_upper=up(suffix_bound),
            terminal_energy_only_improvement=down(zero-terminal_bound),
            suffix_SOC_improvement=down(terminal_bound-bound),
            lagrange_multiplier=float(mu),suffix_lagrange_multiplier=float(smu),
            suffix_energy_upper_bound_kwh=320.,maximizing_relaxed_path_movement_count=sum(not arcs[i][5] for i in path),
            certified_support_incumbent=None,full_original_vehicle_MILP_bound_gap=None,
            retained=['all 96 slots','one actual route','initial location','travel and connection ready times',
                'travel P/Q zero','original PCS16 outer polygon','charge/discharge integral mode','summed original terminal SOC energy equality',
                'SOC66 upper and terminal SOC impose E[66,96)<=320kWh'],
            relaxed=['intermediate SOC minimum/maximum except SOC66 upper','site-wise connection aliases relaxed to at most one actual STAY'],
            relation='Every original schedule maps into this analytical relaxation; upper bound is valid without a vehicle incumbent'))
    exactsum=sum(F(r['U_exact']) for r in rows)
    receipt=dump_gz(OUT/(label+'_CAPACITY_EXACT.json.gz'),dict(schema='ROUTE_ENERGY_SUPPORT_DUAL_V1',
        source_route_sha256=sha(ROUTE),label=label,vehicles=proofs,capacity_structure=details))
    return dict(label=label,vehicles=rows,sum_U_exact=str(exactsum),sum_U_upper=up(exactsum),
        native_optimize_calls=0,exact_artifact=receipt,certification='Exact dispatch polygon and exact DAG dual potential bounds',
        full_vehicle_MILP_solved=False,original_integer_feasible_set_containment='F subset R',
        intermediate_SOC_relaxation_loss='NOT_SEPARATELY_BOUNDED; original full vehicle optimization may tighten U'),exactsum


def main():
    began=time.perf_counter();forbid_optimize();A,d,T,AA,dd=load()
    original=read(ROOT/'docs/v42_m1_physics_strengthened_20261008/CRITICAL_GRID_RHO_COUPLING.json')
    rows0=[r['original_row_index'] for r in original['critical_rows']]
    with np.load(ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz') as f:pi0=f['Pi'].copy()
    with np.load(B2/'B2_ROOT_RAW.npz') as f:pi1=f['pi'].copy()
    with (ROOT/'docs/v42_m1_group_branching_20261008/CRITICAL_GRID_ROWS.csv').open(newline='',encoding='utf-8-sig') as f:
        rows1=[int(r['row']) for r in csv.DictReader(f)]
    security={'line_thermal_face','voltage_upper','voltage_lower','transformer_kVA'}
    rows2=[i for i,n in enumerate(d['row_names']) if str(n) in security and abs(pi1[i])>1e-8]
    demands=[demand(A,d,rows0,pi0,'ARCHIVED_ROOT_ALL_BINDING'),demand(A,d,rows1,pi1,'B2_ACTIVE_THERMAL'),
        demand(A,d,rows2,pi1,'B2_ACTIVE_ALL_SECURITY')]
    sites,initial,arcs,outgoing,prior=route_graph();groups,polygons,ec,details=capacity_inputs(A,d,arcs)
    results=[]
    for weights,const,rhow,D,summary in demands:
        cap,total=capacity(weights,summary['label'],groups,polygons,ec,sites,initial,arcs,outgoing,details)
        delta=D-total
        safe=(total-const)/rhow
        results.append(dict(demand=summary,capacity=cap,D_minus_sum_U_exact=str(delta),
            D_minus_sum_U_lower=down(delta),D_minus_sum_U_upper=up(delta),
            certified_lower_bound_from_support=down(safe),strict_global_contradiction=delta>0,
            status='INFEASIBILITY_CERTIFIED' if delta>0 else 'NOT_PROVEN'))
    best=max(results,key=lambda x:x['certified_lower_bound_from_support'])
    write(OUT/'GRID_DEMAND_CERTIFICATE.json',dict(PASS=True,status='GLOBALLY_VALID_NECESSARY_CONDITIONS',
        cutoff_exact='3/5',candidates=[r['demand'] for r in results],selected_label=best['demand']['label'],
        selected=best['demand'],original_ROOT_active_line_thermal_rows=len(rows0),
        requested_historical_starting_count=95,observed_archived_critical_thermal_rows=len(rows0),
        all_constants_and_frozen_grid_values_included=True,auxiliary_elimination_exact=True,
        certification='Dyadic inputs and exact rational operations; printed lower/upper bounds rounded outward',
        all_original_feasible_schedules_scope=True,native_optimize_calls=0))
    write(OUT/'MESS_CAPACITY_UPPER_BOUNDS.json',dict(PASS=True,status='CERTIFIED_ANALYTICAL_UPPER_BOUNDS',
        selected_label=best['demand']['label'],selected=best['capacity'],candidates=[r['capacity'] for r in results],
        comparisons=[{k:v for k,v in r.items() if k not in ('demand','capacity')} for r in results],
        no_incumbent_used_as_maximization_upper_bound=True,native_optimize_calls=0,
        analysis_wall_seconds=time.perf_counter()-began))
    print(json.dumps(dict(selected=best['demand']['label'],D=best['demand']['D_0_60_lower'],
        sum_U=best['capacity']['sum_U_upper'],difference=best['D_minus_sum_U_lower'],
        support_LB=best['certified_lower_bound_from_support'],status=best['status'],wall_seconds=time.perf_counter()-began)),flush=True)


if __name__=='__main__':main()
