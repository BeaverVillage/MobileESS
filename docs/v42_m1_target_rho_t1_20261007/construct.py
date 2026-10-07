"""Exact fleet support / route-coupled covers. No optimizer is imported."""
from support import *
import heapq, itertools, re, time

def binding_expand(A,d):
    families=[str(n).split('[')[0] for n in d['names']];defs={};cache={}
    for i,n in enumerate(d['row_names']):
        fam=str(n).split('[')[0]
        if fam.endswith('_binding'):
            own=[j for j in rowdict(A,i) if families[j]==fam[:-8]];assert len(own)==1;defs[own[0]]=i
    def expand(j):
        if j in cache:return cache[j]
        if families[j] in ('Pch','Pdis','Q'):r=({j:F(1)},F(0))
        elif d['lower'][j]==d['upper'][j]:r=({},exact(d['lower'][j]))
        else:
            i=defs[j];row=rowdict(A,i);own=row.pop(j);terms=defaultdict(F);c=exact(d['rhs'][i])/own
            for k,w in row.items():
                part,b=expand(k);c-=w*b/own
                for p,v in part.items():terms[p]-=w*v/own
            r=({p:v for p,v in terms.items() if v},c)
        cache[j]=r;return r
    return expand

def planes(a,u,s,t):
    energy=a.energy(u,t);full=a.full
    lo0=exact(full['lower'][a.names[f'SOC[{u},{t}]']]);hi0=exact(full['upper'][a.names[f'SOC[{u},{t}]']])
    lo1=exact(full['lower'][a.names[f'SOC[{u},{t+1}]']]);hi1=exact(full['upper'][a.names[f'SOC[{u},{t+1}]']])
    ch=min(exact(full['upper'][a.names[f'Pch[{u},{s},{t}]']]),(hi1-lo0)/energy['charge'])
    dis=min(exact(full['upper'][a.names[f'Pdis[{u},{s},{t}]']]),(hi0-lo1)/(-energy['discharge']))
    qlo=exact(full['lower'][a.names[f'Q[{u},{s},{t}]']]);qhi=exact(full['upper'][a.names[f'Q[{u},{s},{t}]']])
    assert ch>=0 and dis>=0
    return [(F(1),F(0),dis),(F(-1),F(0),ch),(F(0),F(1),qhi),(F(0),F(-1),-qlo)]+list(a.pcs(u,s,t))

def support_certificate(halfplanes,dp,dq):
    # Exact two-dimensional support dual by nonnegative active facet pairs.
    best=None;certificate=None
    for i,j in itertools.combinations(range(len(halfplanes)),2):
        ap,aq,b=halfplanes[i];cp,cq,e=halfplanes[j];det=ap*cq-aq*cp
        if not det:continue
        l1=(dp*cq-dq*cp)/det;l2=(ap*dq-aq*dp)/det
        if l1<0 or l2<0:continue
        v=l1*b+l2*e
        if best is None or v<best:best=v;certificate=dict(facets=[i,j],multipliers=[str(l1),str(l2)])
    assert best is not None and best>=0
    return best,certificate

class ForwardRoutes:
    def __init__(self,a):
        self.a=a;self.den=max(exact(arc[-1].energy_kwh).denominator for arc in a.arcs if arc[-1] is not None)
        self.edges=defaultdict(list);self.cache={}
        for k,(s,t,d,u,r) in enumerate(a.arcs):
            e=F(0) if r is None else exact(r.energy_kwh);assert self.den%e.denominator==0
            self.edges[t].append((a.sites.index(s),a.sites.index(d),u,int(e*self.den)))
    def distance(self,t,u):
        key=t,u
        if key in self.cache:return self.cache[key]
        n=len(self.a.sites);dist=[[None]*n for _ in range(u-t+1)]
        # Matrix labels: one independent origin per row.
        matrix=[[[None]*n for _ in range(n)] for _ in range(u-t+1)]
        for s in range(n):matrix[0][s][s]=0
        for q in range(t,u):
            for s,d,v,e in self.edges[q]:
                if v>u:continue
                for origin in range(n):
                    old=matrix[q-t][origin][s]
                    if old is None:continue
                    new=old+e;cur=matrix[v-t][origin][d]
                    if cur is None or new<cur:matrix[v-t][origin][d]=new
        result=matrix[-1];self.cache[key]=result;return result

def compatible(a,routes,unit,s,t,v,u):
    dist=routes.distance(t+1,u)[a.sites.index(s)][a.sites.index(v)]
    if dist is None:return False,'ROUTE',None
    energy=F(dist,routes.den)
    # Between the two connected slots: free SOC boundary bounds plus the
    # maximum charge in EVERY intervening slot, ignoring transit charge=0.
    # This is deliberately an overestimate; no route or schedule is pruned.
    cap=exact(a.battery.maximum)-exact(a.battery.minimum)
    for q in range(t+1,u):cap+=a.energy(unit,q)['charge']*exact(a.battery.p_limit)
    return (energy<=cap),'SOC' if energy>cap else 'COMPATIBLE',energy

def combine_state(a,terms,c,u,s,t,w):
    part,b=state(a,u,s,t);c+=w*b
    for j,v in part.items():terms[j]+=w*v
    return c

def main():
    began=time.perf_counter();assert git('merge-base',BASE,'HEAD')==BASE
    assert not (OUT/'OPTIMIZE_ONCE.json').exists();assert (OUT/'PREREGISTRATION.md').exists()
    A,d,_=hc.load();a=hc.Authority();full=a.load_matrix();rho=int(np.flatnonzero(d['names']=='rho_max')[0]);mapping=axes()
    with np.load(hc.HISTORY/'PURE_LP_POINT.npz') as z:lp=z['x'].copy()
    with np.load(PREVIOUS/'BEST_VALID_POINT.npz') as z:inc=z['x'].copy()
    assert sha(PREVIOUS/'BEST_VALID_POINT.npz')=='32fbc2036ef1fb874097d4dc38623818238510aaffd3b5b58f992e5ce519f2e3'
    assert float(d['objective']@inc)==UB
    before=protected();write('BASE_IDENTITY.json',dict(PASS=True,exact_base_HEAD=BASE,scientific_HEAD=SCIENTIFIC,UTC=stamp(),C3A_A_SHA256=sha(hc.PARENT/'C3A_A.npz'),C3A_DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),stored_LP_SHA256=sha(hc.HISTORY/'PURE_LP_POINT.npz'),incumbent_SHA256=sha(PREVIOUS/'BEST_VALID_POINT.npz'),protected_before=before,original_rows=A.shape[0],original_cols=A.shape[1],B=int((d['types']=='B').sum()),C=int((d['types']=='C').sum()),original_nnz=A.nnz))
    residual_lp=A@lp-d['rhs'];residual_inc=A@inc-d['rhs'];weights=A[:,rho].toarray().ravel();rank=defaultdict(list)
    for i in np.flatnonzero(d['row_names']=='line_thermal_face'):
        ii=int(i);orig=int(mapping[i]);names=[str(a.full['names'][j]) for j in full.indices[full.indptr[orig]:full.indptr[orig+1]]]
        ids=[re.fullmatch(r'response_line_(?:P|Q|correction)\[(\d+),(\d+)\]',n) for n in names];ids=[(int(m[1]),int(m[2])) for m in ids if m]
        assert len(set(ids))==1;slot,line=ids[0]
        if 66<=slot<=95:
            assert weights[i]<0
            lp_req=float(lp[rho]+residual_lp[i]/-weights[i]);inc_req=float(inc[rho]+residual_inc[i]/-weights[i])
            rank[slot].append((-(lp_req),-inc_req,ii,orig,line))
    expand=binding_expand(A,d);grids=[];caps={};proof_cache={};plane_cache={}
    for slot in sorted(rank):
        _,_,i,orig,line=min(rank[slot]);row=rowdict(A,i);D=-row.pop(rho);assert D>0 and str(d['sense'][i])=='<'
        pterms=defaultdict(F);constant=F(0)
        for j,w in row.items():
            part,b=expand(j);constant+=w*b
            for k,v in part.items():pterms[k]+=w*v
        grouped=defaultdict(lambda:defaultdict(F))
        for j,w in pterms.items():
            if not w:continue
            m=re.fullmatch(r'(Pch|Pdis|Q)\[([^,]+),([^,]+),(\d+)\]',str(d['names'][j]));assert m and int(m[4])==slot
            grouped[(m[2],m[3])][m[1]]+=w/D
        B=(constant-exact(d['rhs'][i]))/D;states=[];grid=dict(id=f'GRID_{slot}',slot=slot,C3A_row=i,FULL_row=orig,line=line,B=str(B),rho_weight=str(D),required_correction_at_T1=str(B-exact(T1)),physical_terms={str(j):str(w/D) for j,w in pterms.items() if w},constant=str(constant),states=states)
        for unit in sorted(a.initial):
            for site in a.sites:
                arc=a.sites.index(site)*96+slot
                if arc not in a.reachable[unit]:continue
                y,b=state(a,unit,site,slot);assert y or b
                v=grouped[(unit,site)];assert v['Pch']==-v['Pdis'];dp=-v['Pdis'];dq=-v['Q']
                key=(unit,site,slot)
                if key not in plane_cache:plane_cache[key]=planes(a,unit,site,slot)
                planes_key=tuple(plane_cache[key]);skey=(planes_key,dp,dq)
                if skey not in proof_cache:proof_cache[skey]=support_certificate(planes_key,dp,dq)
                k,cert=proof_cache[skey];caps[(slot,unit,site)]=k
                states.append(dict(MESS=unit,site=site,arc=arc,dp=str(dp),dq=str(dq),kappa=str(k),dual=cert,SOC_energy_row=a.energy(unit,slot)['row']))
        grids.append(grid);print('GRID_SUPPORT',slot,len(states),flush=True)
    write('GRID_SUPPORT_PROOFS.json',dict(grids=grids,original_grid_axes_SHA256=sha(PREVIOUS/'GRID_SOURCE_REDUCTION_AXES.npz'),exact_binary64_interpretation=True))
    routes=ForwardRoutes(a);cuts=[];counts=defaultdict(int);violated=defaultdict(int);maxv=defaultdict(lambda:-float('inf'));heap=[];route_stats=defaultdict(int)
    def annotate(c):
        n={int(j):float(w) for j,w in c['native_terms'].items()};vio=sum(w*lp[j] for j,w in n.items())-c['native_rhs'];ivio=sum(w*inc[j] for j,w in n.items())-c['native_rhs']
        c.update(stored_LP_violation=vio,incumbent_violation=ivio);fam=c['family'];counts[fam]+=1;violated[fam]+=int(vio>1e-8);maxv[fam]=max(maxv[fam],vio);return c
    for g in grids:
        terms=defaultdict(F,{rho:F(-1)});c=F(0)
        for st in g['states']:c=combine_state(a,terms,c,st['MESS'],st['site'],g['slot'],-F(st['kappa']))
        cuts.append(annotate(encode_cut('COVER_'+g['id'],'CROSS_MESS_COVER',terms,-F(g['B'])-c,d,grid=g['id'],slot=g['slot'])))
    for g,h in itertools.combinations(grids,2):
        t,u=g['slot'],h['slot']
        if not 1<=u-t<=8:continue
        terms=defaultdict(F,{rho:F(-1)});constant=F(0);Ms={};conditional=[]
        for unit in sorted(a.initial):
            first=[s for s in a.sites if (t,unit,s) in caps];second=[s for s in a.sites if (u,unit,s) in caps]
            M=max([F(0)]+[caps[(t,unit,s)] for s in first])+max([F(0)]+[caps[(u,unit,s)] for s in second]);Ms[unit]=M
            for s in first:
                possible=[]
                for v in second:
                    ok,why,e=compatible(a,routes,unit,s,t,v,u);route_stats[why]+=1
                    if ok:possible.append(caps[(u,unit,v)])
                    else:
                        rterms=defaultdict(F);rc=F(0);rc=combine_state(a,rterms,rc,unit,s,t,F(1));rc=combine_state(a,rterms,rc,unit,v,u,F(1))
                        rn={j:down(w) for j,w in rterms.items() if w};rr=up(F(1)-rc);vio=sum(w*lp[j] for j,w in rn.items())-rr
                        fam='MULTITIME_ROUTE_SOC_CONFLICT';counts[fam]+=1;violated[fam]+=int(vio>1e-8);maxv[fam]=max(maxv[fam],vio)
                        ident=f'CONFLICT_{unit}_{t}_{s}_{u}_{v}';score=(vio,-len(rn),ident)
                        metadata=(unit,s,t,v,u,why,None if e is None else str(e))
                        if len(heap)<128:heapq.heappush(heap,(score,metadata))
                        elif score>heap[0][0]:heapq.heapreplace(heap,(score,metadata))
                bound=caps[(t,unit,s)]+max([F(0)]+possible);reduction=(M-bound)/2;assert reduction>=0
                constant=combine_state(a,terms,constant,unit,s,t,reduction)
                conditional.append(dict(MESS=unit,site=s,capacity=str(bound),reduction=str(reduction)))
        rhs=(sum(Ms.values(),F(0))-F(g['B'])-F(h['B']))/2-constant
        cuts.append(annotate(encode_cut(f'TWO_TIME_{t}_{u}','TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER',terms,rhs,d,grids=[g['id'],h['id']],slots=[t,u],unit_baselines=Ms,conditional_capacities=conditional)))
        print('TWO_TIME_SUPPORT',t,u,flush=True)
    for _,(unit,s,t,v,u,why,e) in sorted(heap,reverse=True):
        terms=defaultdict(F);c=F(0);c=combine_state(a,terms,c,unit,s,t,F(1));c=combine_state(a,terms,c,unit,v,u,F(1))
        cut=encode_cut(f'CONFLICT_{unit}_{t}_{s}_{u}_{v}','MULTITIME_ROUTE_SOC_CONFLICT',terms,F(1)-c,d,MESS=unit,sites=[s,v],slots=[t,u],reason=why,min_movement_energy=e)
        n={int(j):float(w) for j,w in cut['native_terms'].items()};cut.update(stored_LP_violation=sum(w*lp[j] for j,w in n.items())-cut['native_rhs'],incumbent_violation=sum(w*inc[j] for j,w in n.items())-cut['native_rhs']);cuts.append(cut)
    assert len(cuts)<=384
    cuts.sort(key=lambda c:(-c['stored_LP_violation'],c['nnz'],c['id']))
    write('CUT_PROOFS.json',dict(cuts=cuts,route_stats=route_stats,selected_budget=384,rational_energy_denominator=str(routes.den),SOC_only_conflicts=route_stats.get('SOC',0),SOC_projection_is_conservative=True))
    table('CUT_SELECTION.csv',[{k:c[k] for k in ('id','family','nnz','stored_LP_violation','incumbent_violation')} for c in cuts])
    table('CUT_CANDIDATE_CENSUS.csv',[dict(family=fam,generated=counts[fam],constructor_proven_valid=counts[fam],stored_LP_violated=violated[fam],selected=sum(c['family']==fam for c in cuts),selected_nnz=sum(c['nnz'] for c in cuts if c['family']==fam),maximum_violation=maxv[fam]) for fam in counts])
    rows=[];cols=[];data=[];rhs=[]
    for i,c in enumerate(cuts):
        for j,w in c['native_terms'].items():rows.append(i);cols.append(int(j));data.append(w)
        rhs.append(c['native_rhs'])
    C=sparse.csr_matrix((data,(rows,cols)),shape=(len(cuts),A.shape[1]));sparse.save_npz(OUT/'SELECTED_CUT_MATRIX.npz',C);np.savez_compressed(OUT/'SELECTED_CUT_DATA.npz',rhs=np.array(rhs),names=np.array([c['id'] for c in cuts]))
    write('THRESHOLD_AUTHORITY.json',dict(T1=T1,T1_exact=str(exact(T1)),rho_column=rho,name='TARGET_RHO_T1',sense='<',coefficient=1.,RHS=T1,scientific_decision_rows_added=1,original_objective_stored_for_replay=True,native_objective='ZERO_FEASIBILITY',start_supplied=False,current_incumbent_rho=UB,current_incumbent_target_violation=UB-T1,full_domain_preserved=True,cut_rho_symbolic=True,old_LB=LB,old_UB=UB))
    write('STATIC_BUILD_RECEIPT.json',dict(UTC=stamp(),seconds=time.perf_counter()-began,selected_cuts=len(cuts),no_optimize=True,protected_unchanged=before==protected(),route_compatibility_stats=route_stats))
    assert before==protected();print('STATIC_CONSTRUCT_COMPLETE',len(cuts),dict(counts),flush=True)
if __name__=='__main__':main()
