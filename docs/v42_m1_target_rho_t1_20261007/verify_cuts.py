"""Independent rational verifier. Does NOT import construct.py.

Uses iterative equation substitution, original sparse flow/energy incidence,
support dual certificates and backward integer-cost time-DAG dynamic programming.
"""
from support import *
import copy, itertools, re, time

class Checker:
    def __init__(self):
        self.A,self.d,_=hc.load();self.a=hc.Authority();self.full=self.a.load_matrix()
        self.rho=int(np.flatnonzero(self.d['names']=='rho_max')[0]);self.defs={};self.cached={};self.plane_cache={};self.distance_cache={}
        for i,n in enumerate(self.d['row_names']):
            family=str(n).split('[')[0]
            if family.endswith('_binding'):
                row=rowdict(self.A,i);own=[j for j in row if str(self.d['names'][j]).split('[')[0]==family[:-8]];assert len(own)==1
                self.defs[own[0]]=(row,exact(self.d['rhs'][i]))
        self.edges=defaultdict(list)
        self.den=max(exact(r.energy_kwh).denominator for *_,r in self.a.arcs if r is not None)
        for s,t,v,u,r in self.a.arcs:
            e=F(0) if r is None else exact(r.energy_kwh)
            self.edges[t].append((self.a.sites.index(s),self.a.sites.index(v),u,int(e*self.den)))

    def substitute(self,terms,constant=F(0)):
        # Expand a whole row iteratively, rather than production recursive closure.
        terms=defaultdict(F,terms)
        while True:
            pending=[j for j,v in terms.items() if v and not str(self.d['names'][j]).startswith(('Pch[','Pdis[','Q[','rho_max'))]
            if not pending:break
            j=pending[0];w=terms.pop(j)
            if self.d['lower'][j]==self.d['upper'][j]:constant+=w*exact(self.d['lower'][j])
            else:
                row,b=self.defs[j];scale=w/row[j];constant+=scale*b
                for k,v in row.items():
                    if k!=j:terms[k]-=scale*v
        return {j:v for j,v in terms.items() if v},constant

    def audit_network(self):
        a=self.a;A=self.full;flow_count=0;incidence=defaultdict(list);rows=0;energy_columns=0;power_connections=0
        for i in np.flatnonzero(a.full['row_names']=='flow'):
            js=A.indices[A.indptr[i]:A.indptr[i+1]];ws=A.data[A.indptr[i]:A.indptr[i+1]]
            assert str(a.full['sense'][i])=='='
            if not len(js):assert a.full['rhs'][i]==0;continue
            node=None;unit=None
            for j,w in zip(js,ws):
                match=re.fullmatch(r'arc\[([^,]+),(\d+)\]',str(a.full['names'][j]));assert match and w in (-1.,1.)
                u,k=match[1],int(match[2]);s,t,v,q,r=a.arcs[k];here=(s,t) if w==1 else (v,q)
                if node is None:node=here;unit=u
                assert node==here and unit==u
                incidence[int(j)].append((here,int(w)));flow_count+=1
            expected=1. if node==(a.initial[unit],0) else 0.;assert float(a.full['rhs'][i])==expected;rows+=1
        for unit in a.initial:
            for k,(s,t,v,q,r) in enumerate(a.arcs):
                j=a.names.get(f'arc[{unit},{k}]')
                if j is None:continue
                assert a.full['lower'][j]==0 and a.full['upper'][j]==1 and str(a.full['types'][j])=='B'
                expected=[((s,t),1)]+([] if q==96 else [((v,q),-1)])
                assert sorted(incidence[j])==sorted(expected)
            for t in range(96):
                energy=a.energy(unit,t);raw=energy['raw'];normal=energy['normalizer'];assert normal==1 and a.full['rhs'][energy['row']]==0 and a.full['sense'][energy['row']]=='='
                for j,w in raw.items():
                    n=str(a.full['names'][j]);m=re.fullmatch(r'arc\[([^,]+),(\d+)\]',n)
                    if m:
                        assert m[1]==unit;k=int(m[2]);arc=a.arcs[k];assert arc[1]==t and arc[-1] is not None
                        assert w==exact(arc[-1].energy_kwh) and w>=0;energy_columns+=1
                for k in a.reachable[unit]:
                    arc=a.arcs[k]
                    if arc[1]==t and arc[-1] is not None:
                        assert raw.get(a.names[f'arc[{unit},{k}]'],F(0))==exact(arc[-1].energy_kwh)
        # Original connection rows prove all P/Q vanish in unconnected states;
        # the PCS +/-Q facets imply Q=0 when y=0.
        for fam,power in [('connected_Pch','Pch'),('connected_Pdis','Pdis')]:
            for i in np.flatnonzero(a.full['row_names']==fam):
                row=a.row(int(i));pj=[j for j in row if str(a.full['names'][j]).startswith(power+'[')];assert len(pj)==1
                name=str(a.full['names'][pj[0]]);m=re.fullmatch(r'\w+\[([^,]+),([^,]+),(\d+)\]',name);u,s,t=m[1],m[2],int(m[3]);aj=a.names[f'arc[{u},{a.sites.index(s)*96+t}]']
                assert row=={pj[0]:F(1),aj:-exact(a.battery.p_limit)} and a.full['sense'][i]=='<' and a.full['rhs'][i]==0;power_connections+=1
        # Verify the actual C3 continuous-route integrality authority. Through
        # masses at every node are binary; parallel same-endpoint arcs remain
        # binary. Nonnegative acyclic unit flow then has one integral path.
        selected_flow=set();selected_links=set()
        def signature(row,b):return tuple(sorted((j,str(w)) for j,w in row.items() if w)),str(b)
        for i,n in enumerate(self.d['row_names']):
            if str(n).split('[')[0] in ('flow','node_activity_link'):
                assert self.d['sense'][i]=='='
                (selected_flow if str(n).split('[')[0]=='flow' else selected_links).add(signature(rowdict(self.A,i),exact(self.d['rhs'][i])))
        def equal_retained(row,b):
            known=selected_flow|selected_links
            return signature(row,b) in known or signature({j:-w for j,w in row.items()},-b) in known
        nodes=set();outgoing=defaultdict(list);incoming=defaultdict(list);parallel=defaultdict(list)
        for unit in a.initial:
            for k,arc in enumerate(a.arcs):
                if f'arc[{unit},{k}]' not in a.names:continue
                s,t,v,u,r=arc;nodes.update([(unit,s,t),(unit,v,u)]);outgoing[unit,s,t].append(k);incoming[unit,v,u].append(k);parallel[unit,s,t,v,u].append(k)
        ordered=sorted(nodes,key=lambda n:(n[0],n[2],n[1]));assert len(a.target)==len(a.full['names'])+len(ordered)
        for no,(unit,s,t) in enumerate(ordered):
            original=len(a.full['names'])+no;j=int(a.target[original]);offset=a.offset[original]
            expected=defaultdict(F);constant=offset
            if j>=0:
                assert self.d['types'][j]=='B';expected[j]+=1
            else:assert offset in (0,1)
            for k in (incoming[unit,s,t] if t==96 else outgoing[unit,s,t]):
                expr,c=a.expression(f'arc[{unit},{k}]');constant-=c
                for q,w in expr.items():expected[q]-=w
            row={q:w for q,w in expected.items() if w}
            assert (not row and constant==0) or equal_retained(row,-constant),dict(node=[unit,s,t],native=None if j<0 else str(self.d['names'][j]),rhs=str(-constant),terms=[(str(self.d['names'][q]),str(w)) for q,w in list(row.items())[:8]])
        for (unit,*_),keys in parallel.items():
            if len(keys)>1:
                for k in keys:
                    expr,c=a.expression(f'arc[{unit},{k}]');assert all(self.d['types'][j]=='B' for j in expr)
        for i in np.flatnonzero(a.full['row_names']=='flow'):
            expected=defaultdict(F);constant=F(0)
            for j,w in a.row(int(i)).items():
                expr,c=a.expression(str(a.full['names'][j]));constant+=w*c
                for q,v in expr.items():expected[q]+=w*v
            row={q:w for q,w in expected.items() if w};b=exact(a.full['rhs'][i])-constant
            assert (not row and b==0) or equal_retained(row,b)
        return dict(PASS=True,nonempty_flow_rows=rows,flow_arc_incidences=flow_count,energy_arc_coefficients=energy_columns,connection_rows=power_connections,compact_binary_node_masses_verified=len(ordered),original_flow_exact_preimages_verified=True,integral_unit_flow_is_one_acyclic_path=True,complete_time_DAG_is_safe_supergraph=True,all_original_bounds_preserved=True)

    def halfplanes(self,unit,site,t):
        key=unit,site,t
        if key in self.plane_cache:return self.plane_cache[key]
        a=self.a;full=a.full
        energy=a.energy(unit,t);i0=a.names[f'SOC[{unit},{t}]'];i1=a.names[f'SOC[{unit},{t+1}]']
        alpha=energy['charge'];beta=-energy['discharge'];assert alpha>0 and beta>0
        pch=a.names[f'Pch[{unit},{site},{t}]'];pd=a.names[f'Pdis[{unit},{site},{t}]'];q=a.names[f'Q[{unit},{site},{t}]']
        charge=min(exact(full['upper'][pch]),(exact(full['upper'][i1])-exact(full['lower'][i0]))/alpha)
        discharge=min(exact(full['upper'][pd]),(exact(full['upper'][i0])-exact(full['lower'][i1]))/beta)
        result=[(F(1),F(0),discharge),(F(-1),F(0),charge),(F(0),F(1),exact(full['upper'][q])),(F(0),F(-1),-exact(full['lower'][q]))]+list(a.pcs(unit,site,t))
        self.plane_cache[key]=result;return result

    def support_valid(self,st,t):
        planes=self.halfplanes(st['MESS'],st['site'],t);ids=st['dual']['facets'];multipliers=list(map(F,st['dual']['multipliers']))
        if len(ids)!=2 or len(multipliers)!=2 or any(v<0 for v in multipliers):return False
        if any(not 0<=i<len(planes) for i in ids):return False
        dp=sum((w*planes[i][0] for i,w in zip(ids,multipliers)),F(0));dq=sum((w*planes[i][1] for i,w in zip(ids,multipliers)),F(0));bound=sum((w*planes[i][2] for i,w in zip(ids,multipliers)),F(0))
        return dp==F(st['dp']) and dq==F(st['dq']) and bound<=F(st['kappa']) and F(st['kappa'])>=0

    def grid_valid(self,g):
        i=g['C3A_row'];raw=rowdict(self.A,i);D=-raw[self.rho];assert D>0
        expanded,c=self.substitute(raw)
        assert expanded.pop(self.rho)==-D
        assert {str(j):str(w/D) for j,w in expanded.items()}==g['physical_terms']
        assert c==F(g['constant']) and (c-exact(self.d['rhs'][i]))/D==F(g['B'])
        # Independently map original FULL grid row through exact saved inverse.
        fraw=self.a.row(g['FULL_row']);terms=defaultdict(F);offset=F(0)
        for j,w in fraw.items():
            part,b=self.a.expression(str(self.a.full['names'][j]));offset+=w*b
            for k,v in part.items():terms[k]+=w*v
        assert {j:v for j,v in terms.items() if v}==raw
        assert exact(self.a.full['rhs'][g['FULL_row']])-offset==exact(self.d['rhs'][i])
        assert F(g['required_correction_at_T1'])==F(g['B'])-exact(T1)
        states={(st['MESS'],st['site']):st for st in g['states']};assert len(states)==len(g['states'])
        for unit in self.a.initial:
            for site in self.a.sites:
                k=self.a.sites.index(site)*96+g['slot'];legal=k in self.a.reachable[unit]
                assert ((unit,site) in states)==legal
                if not legal:continue
                st=states[(unit,site)];assert st['arc']==k and self.support_valid(st,g['slot'])
                byfam={}
                for family in ('Pch','Pdis','Q'):
                    terms,b=self.a.expression(f'{family}[{unit},{site},{g["slot"]}]');assert b==0
                    byfam[family]=sum((expanded.get(j,F(0))*w/D for j,w in terms.items()),F(0))
                assert byfam['Pch']==-byfam['Pdis'] and F(st['dp'])==-byfam['Pdis'] and F(st['dq'])==-byfam['Q']
        return True

    def backward(self,start,end):
        key=start,end
        if key in self.distance_cache:return self.distance_cache[key]
        n=len(self.a.sites);mat=[[[None]*n for _ in range(n)] for _ in range(end-start+1)]
        for dest in range(n):mat[-1][dest][dest]=0
        for t in range(end-1,start-1,-1):
            for s,v,u,cost in self.edges[t]:
                if u>end:continue
                for dest in range(n):
                    tail=mat[u-start][v][dest]
                    if tail is None:continue
                    val=cost+tail;old=mat[t-start][s][dest]
                    if old is None or val<old:mat[t-start][s][dest]=val
        self.distance_cache[key]=mat[0];return mat[0]

    def possible(self,unit,s,t,v,u):
        cost=self.backward(t+1,u)[self.a.sites.index(s)][self.a.sites.index(v)]
        if cost is None:return False,'ROUTE',None
        e=F(cost,self.den)
        # Reconstruct cap directly from original SOC bound columns and raw
        # energy equations, independent of battery constants in constructor.
        after=self.a.names[f'SOC[{unit},{t+1}]'];before=self.a.names[f'SOC[{unit},{u}]']
        cap=exact(self.a.full['upper'][after])-exact(self.a.full['lower'][before])
        for k in range(t+1,u):
            alpha=self.a.energy(unit,k)['charge'];cap+=alpha*exact(self.a.battery.p_limit)
        return e<=cap,'SOC' if e>cap else 'COMPATIBLE',e

    def accumulate(self,terms,constant,unit,site,t,w):
        expr,offset=self.a.expression(f'arc[{unit},{self.a.sites.index(site)*96+t}]');constant+=w*offset
        for j,v in expr.items():assert self.d['lower'][j]==0 and self.d['upper'][j]==1;terms[j]+=w*v
        return constant

    def expected(self,cut,grids):
        terms=defaultdict(F);c=F(0);family=cut['family']
        if family=='CROSS_MESS_COVER':
            g=grids[cut['grid']];terms[self.rho]=F(-1)
            for st in g['states']:c=self.accumulate(terms,c,st['MESS'],st['site'],g['slot'],-F(st['kappa']))
            rhs=-F(g['B'])-c
        elif family=='MULTITIME_ROUTE_SOC_CONFLICT':
            unit=cut['MESS'];s,v=cut['sites'];t,u=cut['slots'];ok,why,e=self.possible(unit,s,t,v,u)
            assert not ok and why==cut['reason'] and (None if e is None else str(e))==cut['min_movement_energy']
            c=self.accumulate(terms,c,unit,s,t,F(1));c=self.accumulate(terms,c,unit,v,u,F(1));rhs=F(1)-c
        elif family in ('INTEGER_CROSS_MESS_COVER','INTEGER_TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER'):
            selected=[grids[x] for x in cut['grids']];times=[g['slot'] for g in selected];total=F(0);states=cut['assignment'];byunit=defaultdict(list)
            for st in states:byunit[st['MESS']].append(st)
            for unit in self.a.initial:
                cap=F(0)
                for g in selected:
                    matched=[st for st in byunit[unit] if st['slot']==g['slot']];assert len(matched)<=1
                    values={st['site']:F(st['kappa']) for st in g['states'] if st['MESS']==unit}
                    cap+=values[matched[0]['site']] if matched else max([F(0)]+list(values.values()))
                if len(selected)==2 and len(byunit[unit])==2:
                    st=sorted(byunit[unit],key=lambda r:r['slot']);assert self.possible(unit,st[0]['site'],times[0],st[1]['site'],times[1])[0]
                total+=cap
            delta=(sum((F(g['B']) for g in selected),F(0))-total)/len(selected);assert delta==F(cut['delta']) and delta>exact(T1)
            terms[self.rho]=F(-1)
            for st in states:c=self.accumulate(terms,c,st['MESS'],st['site'],st['slot'],delta)
            rhs=delta*(len(states)-1)-c
        else:
            assert family=='TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER';g,h=[grids[k] for k in cut['grids']];t,u=g['slot'],h['slot'];terms[self.rho]=F(-1);total=F(0);conditional=[]
            for unit in self.a.initial:
                first={s['site']:F(s['kappa']) for s in g['states'] if s['MESS']==unit};second={s['site']:F(s['kappa']) for s in h['states'] if s['MESS']==unit}
                M=max([F(0)]+list(first.values()))+max([F(0)]+list(second.values()));assert M==F(cut['unit_baselines'][unit]);total+=M
                for site,k in first.items():
                    future=[value for dest,value in second.items() if self.possible(unit,site,t,dest,u)[0]]
                    cap=k+max([F(0)]+future);w=(M-cap)/2;assert w>=0
                    c=self.accumulate(terms,c,unit,site,t,w);conditional.append(dict(MESS=unit,site=site,capacity=str(cap),reduction=str(w)))
            assert conditional==cut['conditional_capacities'];rhs=(total-F(g['B'])-F(h['B']))/2-c
        return {j:v for j,v in terms.items() if v},rhs

    def cut_valid(self,cut,grids):
        terms,rhs=self.expected(cut,grids)
        if terms!={int(j):F(w) for j,w in cut['terms'].items()} or rhs!=F(cut['rhs']):return False
        if len(terms)!=cut['nnz']:return False
        native={int(j):exact(w) for j,w in cut['native_terms'].items()}
        return set(native)==set(terms) and all(native[j]<=w and self.d['lower'][j]>=0 for j,w in terms.items()) and exact(cut['native_rhs'])>=rhs

def main():
    start=time.perf_counter();v=Checker();network=v.audit_network();print('INDEPENDENT_NETWORK_PASS',flush=True)
    proof=read(OUT/'GRID_SUPPORT_PROOFS.json');grids={g['id']:g for g in proof['grids']};data=read(OUT/'CUT_PROOFS.json');cuts=data['cuts'];mutations=[]
    for g in grids.values():assert v.grid_valid(g);print('INDEPENDENT_GRID_PASS',g['slot'],flush=True)
    for g in grids.values():
        for st in g['states']:
            altered=copy.deepcopy(st);altered['kappa']=str(F(st['kappa'])-F(1,1000000));assert not v.support_valid(altered,g['slot'])
            altered=copy.deepcopy(st);altered['dp']=str(F(st['dp'])+1);assert not v.support_valid(altered,g['slot'])
    mutations.append(dict(test='Every support capacity decreased / direction changed',cases=2*sum(len(g['states']) for g in grids.values()),PASS=True))
    C=sparse.load_npz(OUT/'SELECTED_CUT_MATRIX.npz').tocsr()
    with np.load(OUT/'SELECTED_CUT_DATA.npz') as z:rhs=z['rhs'];names=z['names']
    for i,cut in enumerate(cuts):
        assert v.cut_valid(cut,grids);assert names[i]==cut['id'] and rhs[i]==cut['native_rhs']
        native={int(j):float(w) for j,w in cut['native_terms'].items()};assert {j:float(w) for j,w in rowdict(C,i).items()}==native
        bad=copy.deepcopy(cut);bad['rhs']=str(F(cut['rhs'])-1);assert not v.cut_valid(bad,grids)
        bad=copy.deepcopy(cut);j=next(iter(bad['terms']));bad['terms'][j]=str(F(bad['terms'][j])+1);assert not v.cut_valid(bad,grids)
        bad=copy.deepcopy(cut);j=next(iter(bad['native_terms']));bad['native_terms'][j]=float(F(cut['terms'][j])+1);assert not v.cut_valid(bad,grids)
    mutations.append(dict(test='Every exact RHS / coefficient and native outward coefficient altered',cases=3*len(cuts),PASS=True))
    # Adversarial route tests: identity (adjacent STAY), impossible site change
    # within one time boundary, and every original single MOVE edge. Backward
    # distance must include each physical witness, rather than prune it.
    adversarial=0
    for t in range(67,96):
        matrix=v.backward(t,t)
        for s in range(len(v.a.sites)):
            for d in range(len(v.a.sites)):assert matrix[s][d]==(0 if s==d else None);adversarial+=1
    for s,t,d,u,r in v.a.arcs:
        if 67<=t<u<=95 and u-t<=7:
            cost=v.backward(t,u)[v.a.sites.index(s)][v.a.sites.index(d)]
            bound=0 if r is None else int(exact(r.energy_kwh)*v.den);assert cost is not None and cost<=bound;adversarial+=1
    with np.load(PREVIOUS/'BEST_VALID_POINT.npz') as z:inc=z['x'].copy()
    with np.load(hc.PARENT/'C3A_VALID_START.npz') as z:old=z['point'].copy()
    with np.load(hc.HISTORY/'PURE_LP_POINT.npz') as z:lp=z['x'].copy()
    references=[]
    for name,point in [('PR171',inc),('original_C3A_start',old)]:
        raw=hc.replay(v.A,v.d,point,True);maxvio=float(np.max(C@point-rhs));assert raw['PASS'] and maxvio<=1e-8
        references.append(dict(name=name,original_C3A=raw,all_new_cut_max_violation=maxvio,PASS=True))
    # Numeric rounding is proven globally, including unit binary extremes and
    # rho=0/1; it is not just a test on reference points.
    for cut in cuts:
        exactterms={int(j):F(w) for j,w in cut['terms'].items()};native={int(j):exact(w) for j,w in cut['native_terms'].items()}
        for bit in (F(0),F(1)):
            assert sum(((native[j]-w)*bit for j,w in exactterms.items()),F(0))<=0
    result=dict(PASS=True,independent_constructor_imported=False,network=network,grid_rows_verified=len(grids),exact_support_duals_verified=sum(len(g['states']) for g in grids.values()),selected_cuts_independently_verified=len(cuts),outward_rounding_all_original_domain_PASS=True,mutation_tests=mutations,adversarial_route_cases=adversarial,reference_integer_points=references,stored_LP_max_violation=float(np.max(C@lp-rhs)),selected_budget=512,no_optimize_calls=True,seconds=time.perf_counter()-start,SOC_only_conflicts=data['SOC_only_conflicts'],SOC_effect='Two-slot SOC span/power and intervening maximum-charge envelopes are conservative; SOC-only pruning is absent when these bounds do not exclude any route-compatible pair.',all_original_integer_schedules_preserved=True)
    result['verified_inputs_SHA256']={n:sha(OUT/n) for n in ('PREREGISTRATION.md','GRID_SUPPORT_PROOFS.json','CUT_PROOFS.json','SELECTED_CUT_MATRIX.npz','SELECTED_CUT_DATA.npz','construct.py','integer_covers.py','verify_cuts.py','support.py')}
    write('CUT_VALIDATION.json',result);print('INDEPENDENT_CUT_VERIFIER_PASS',len(cuts),result['stored_LP_max_violation'],flush=True)
if __name__=='__main__':main()
