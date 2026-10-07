"""Static global integer cover lifting. No native model construction or solve."""
from support import *
from construct import ForwardRoutes, compatible, combine_state
import itertools, heapq, time

def main():
    start=time.perf_counter();assert not (OUT/'OPTIMIZE_ONCE.json').exists()
    A,d,_=hc.load();a=hc.Authority();rho=int(np.flatnonzero(d['names']=='rho_max')[0]);data=read(OUT/'CUT_PROOFS.json');original=[c for c in data['cuts'] if not c['family'].startswith('INTEGER_')];grids=read(OUT/'GRID_SUPPORT_PROOFS.json')['grids'];routes=ForwardRoutes(a)
    with np.load(hc.HISTORY/'PURE_LP_POINT.npz') as z:lp=z['x']
    with np.load(PREVIOUS/'BEST_VALID_POINT.npz') as z:inc=z['x']
    counts=defaultdict(int);viols=defaultdict(int);maxv=defaultdict(lambda:-float('inf'));tops=defaultdict(list);sequence=0
    units=sorted(a.initial);ranked={};caps={};mass={}
    for g in grids:
        for unit in units:
            candidates=[]
            for st in g['states']:
                if st['MESS']!=unit:continue
                expr,c=state(a,unit,st['site'],g['slot']);value=float(c)+sum(float(w)*lp[j] for j,w in expr.items());iv=float(c)+sum(float(w)*inc[j] for j,w in expr.items())
                candidates.append((-value,-iv,st['site']));caps[g['slot'],unit,st['site']]=F(st['kappa']);mass[g['slot'],unit,st['site']]=value
            ranked[g['slot'],unit]=[v[2] for v in sorted(candidates)]
    def candidate(selected,assignment):
        nonlocal sequence
        n=len(selected);total=F(0)
        for st in assignment:total+=caps[st['slot'],st['MESS'],st['site']]
        delta=(sum((F(g['B']) for g in selected),F(0))-total)/n
        if delta<=exact(T1):return
        family='INTEGER_CROSS_MESS_COVER' if n==1 else 'INTEGER_TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER';counts[family]+=1
        terms=defaultdict(F,{rho:F(-1)});constant=F(0)
        for st in assignment:constant=combine_state(a,terms,constant,st['MESS'],st['site'],st['slot'],delta)
        rhs=delta*(len(assignment)-1)-constant;native,nrhs=native_cut(terms,rhs,d);vio=sum(w*lp[j] for j,w in native.items())-nrhs;viols[family]+=int(vio>1e-8);maxv[family]=max(maxv[family],vio)
        sequence+=1;ident='ICOVER_'+'_'.join(str(g['slot']) for g in selected)+'_'+str(sequence)
        cut=encode_cut(ident,family,terms,rhs,d,grids=[g['id'] for g in selected],assignment=assignment,delta=str(delta));cut.update(stored_LP_violation=vio,incumbent_violation=sum(w*inc[j] for j,w in native.items())-nrhs)
        item=((vio,-cut['nnz'],ident),cut);limit=128 if n==1 else 224
        if len(tops[family])<limit:heapq.heappush(tops[family],item)
        elif item[0]>tops[family][0][0]:heapq.heapreplace(tops[family],item)
    for g in grids:
        t=g['slot']
        pools=[list(dict.fromkeys(ranked[t,unit][:4]+sorted(ranked[t,unit],key=lambda s:(caps[t,unit,s],s))[:4])) for unit in units]
        for combination in itertools.product(*pools):
            candidate([g],[dict(MESS=unit,site=s,slot=t) for unit,s in zip(units,combination)])
    for g,h in itertools.combinations(grids,2):
        t,u=g['slot'],h['slot']
        if not 1<=u-t<=8:continue
        choices=[]
        for unit in units:
            first=list(dict.fromkeys(ranked[t,unit][:2]+sorted(ranked[t,unit],key=lambda s:(caps[t,unit,s],s))[:2]));second=list(dict.fromkeys(ranked[u,unit][:2]+sorted(ranked[u,unit],key=lambda s:(caps[u,unit,s],s))[:2]))
            pairs=[(s,v) for s in first for v in second if compatible(a,routes,unit,s,t,v,u)[0]]
            bymass=sorted(pairs,key=lambda p:(-mass[t,unit,p[0]]-mass[u,unit,p[1]],p));bycap=sorted(pairs,key=lambda p:(caps[t,unit,p[0]]+caps[u,unit,p[1]],p));choices.append(list(dict.fromkeys(bymass[:4]+bycap[:4])))
        for combination in itertools.product(*choices):
            assignment=[dict(MESS=unit,site=s,slot=q) for unit,(s,v) in zip(units,combination) for s,q in [(s,t),(v,u)]]
            candidate([g,h],assignment)
    single=[x[1] for x in tops['INTEGER_CROSS_MESS_COVER']]
    paired=[c for c in original if c['family']=='TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER']+[x[1] for x in tops['INTEGER_TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER']]
    paired.sort(key=lambda c:(-c['stored_LP_violation'],c['nnz'],c['id']));paired=paired[:224]
    selected=[c for c in original if c['family'] in ('CROSS_MESS_COVER','MULTITIME_ROUTE_SOC_CONFLICT')]+single+paired
    selected.sort(key=lambda c:(-c['stored_LP_violation'],c['nnz'],c['id']));assert len(selected)<=512
    # Preserve first-stage receipt and record the pre-solve static refinement.
    data.update(cuts=selected,selected_budget=512,integer_cover_generated=counts,integer_cover_stored_LP_violated=viols,integer_cover_max_violation=maxv,static_revision_reason='Initial 362 valid support/conflict cuts have zero stored-LP violation; add globally valid integer assignment covers without restricting native domain.')
    write('CUT_PROOFS.json',data)
    old=[r for r in csv.DictReader((OUT/'CUT_CANDIDATE_CENSUS.csv').open(encoding='utf-8')) if not r['family'].startswith('INTEGER_')];census=[]
    for r in old:
        f=r['family'];r['selected']=sum(c['family']==f for c in selected);r['selected_nnz']=sum(c['nnz'] for c in selected if c['family']==f);census.append(r)
    for f in counts:census.append(dict(family=f,generated=counts[f],constructor_proven_valid=counts[f],stored_LP_violated=viols[f],selected=sum(c['family']==f for c in selected),selected_nnz=sum(c['nnz'] for c in selected if c['family']==f),maximum_violation=maxv[f]))
    table('CUT_CANDIDATE_CENSUS.csv',census);table('CUT_SELECTION.csv',[{k:c[k] for k in ('id','family','nnz','stored_LP_violation','incumbent_violation')} for c in selected])
    rows=[];cols=[];ws=[]
    for i,c in enumerate(selected):
        for j,w in c['native_terms'].items():rows.append(i);cols.append(int(j));ws.append(w)
    C=sparse.csr_matrix((ws,(rows,cols)),shape=(len(selected),A.shape[1]));sparse.save_npz(OUT/'SELECTED_CUT_MATRIX.npz',C);np.savez_compressed(OUT/'SELECTED_CUT_DATA.npz',rhs=np.array([c['native_rhs'] for c in selected]),names=np.array([c['id'] for c in selected]))
    write('INTEGER_COVER_BUILD_RECEIPT.json',dict(PASS=True,UTC=stamp(),seconds=time.perf_counter()-start,selected=len(selected),generated=counts,violated=viols,max_violation=maxv,optimize_calls_so_far=0,domain_restrictions=0,candidate_ranking_only=True))
    print('INTEGER_COVER_STATIC_COMPLETE',len(selected),dict(counts),dict(viols),dict(maxv),flush=True)
if __name__=='__main__':main()
