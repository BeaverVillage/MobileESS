"""Independent current-row/LP/algebra verifier; never calls Presolve decisions."""
from .common import *
import csv,time,collections
from fractions import Fraction as F
import numpy as np
from scipy import sparse
from v42_degen.identity import inputs,signature
from v42_redundancy import replay as r
from .build import load

def transport():
    t=time.perf_counter();_,_,A,d,_,_=inputs();sites,reach=r.fresh_reachability(A,d);sources,anchors=r.independent_sources(A,d,sites);vertices=r.independent_vertices(A,d)
    with (OLD/'M1_REMOVED_ROW_CERTIFICATES.csv').open(encoding='utf-8') as f:removed={int(c['original_row_id']):c for c in csv.DictReader(f)}
    assert not anchors.intersection(removed)
    methods=collections.Counter();minimum=float('inf');classification=[]
    C0,e=load('C0');assert (C0[:A.shape[0],:A.shape[1]]!=A).nnz==0
    assert C0[:A.shape[0],A.shape[1]:].nnz==0
    for k,(i,c) in enumerate(removed.items()):
        method,slack=r.verify_certificate(A,d,c,removed,sources,reach,vertices);methods[method]+=1
        if slack:minimum=min(minimum,slack)
        classification.append(dict(original_row=i,row_SHA256=c['row_SHA256'],classification='REDUNDANT_OVER_COMPACT_LP_RELAXATION',decision='DELETE',proof=method))
        if (k+1)%25000==0:print('CURRENT_PR160_LP_REPLAY',k+1,'wall',time.perf_counter()-t,flush=True)
    with np.load(OLD/'M1_REDUCTION_AXES.npz') as z:keep=z['keep'];gone=z['removed']
    assert set(gone)==set(removed)
    reduced=sparse.load_npz(OLD/'M1_EXACT_REDUCED_A.npz');assert (reduced!=A[keep]).nnz==0
    dependency=json.loads((OLD/'M1_REMOVAL_DEPENDENCY_GRAPH.json').read_text(encoding='utf-8'))
    # verify_certificate checks every representative against actual original rows;
    # removed representatives require a non-implication endpoint, prohibiting cycles.
    mutations=[]
    for kind in ['ROW_HASH','RHS','UPPER_BOUND','SELF_DEPENDENCY']:
        c=dict(next(c for c in removed.values() if bool(c['dominator'])==(kind=='SELF_DEPENDENCY')))
        if kind=='ROW_HASH':c['row_SHA256']='0'*64
        elif kind=='RHS':c['RHS']=str(float(c['RHS'])+1)
        elif kind=='UPPER_BOUND':c['certified_upper_bound']=str(float(c['RHS'])+1)
        else:c['dominator']=c['original_row_id']
        rejected=False
        try:r.verify_certificate(A,d,c,removed,sources,reach,vertices)
        except (AssertionError,ValueError):rejected=True
        assert rejected;mutations.append(dict(mutation=kind,rejected=True))
    result=dict(PASS=True,current_signature=signature(A,d),rows_checked=len(removed),methods=dict(methods),minimum_independent_slack=minimum,
        compact_LP_safe=len(removed),integer_only_LP_strengthening_retained=0,unknown_retained=0,affine_anchors_retained=len(anchors),
        row_identity_recomputed=True,representatives_current_checked=True,dependency_file_SHA256=sha(OLD/'M1_REMOVAL_DEPENDENCY_GRAPH.json'),dependency_closure_current_checked=True,
        proof='C0 compact LP projects identically onto original nonnegative unit-DAG arc relaxation. Added node links merely define outgoing/incoming unit-flow mass in [0,1]; all original physical rows are copied byte-exactly. Therefore independently replayed original LP interval/row implication proofs apply to every compact fractional point. No integer-only proof is transported.',
        mutation_rejections=mutations,decision_function_reused=False,wall=time.perf_counter()-t)
    write('PR160_CERTIFICATE_TRANSPORT_AUDIT.json',result);table('COMPACT_LP_REDUNDANCY_CLASSIFICATION.csv',classification,list(classification[0]))
    write('SUPERCOMPACT_FRACTIONAL_RELAXATION_AUDIT.json',dict(PASS=True,rows_proved=len(removed),all_deletions_cannot_cut_compact_LP=True,projection_proof=result['proof'],methods=result['methods'],integer_only_proofs_used=False))
    print('TRANSPORT_PASS',result,flush=True);return result

def inverse_map():
    A,d=load('C1');C,f=load('C2')
    with np.load(OUT/'C2_RETAINED_AXES.npz') as z:cols=z['columns'];rows=z['rows']
    steps=read('C2_ELIMINATION_CERTIFICATES.json');n=A.shape[1];target=np.full(n,-1,int);offset=np.zeros(n);target[cols]=np.arange(len(cols))
    seen=set(map(int,cols));definitions=[]
    for s in reversed(steps):
        j=s['column'];assert j not in seen;terms=s['terms'];assert len(terms)<=1
        if terms:
            k,w=next(iter(terms.items()));k=int(k);assert k in seen and w==1.;target[j]=target[k];offset[j]=s['constant']+offset[k]
        else:offset[j]=s['constant']
        seen.add(j);definitions.append(s)
    assert len(seen)==n
    nz=np.flatnonzero(target>=0);T=sparse.csr_matrix((np.ones(len(nz)),(nz,target[nz])),shape=(n,C.shape[1]))
    return A,d,C,f,T,offset,rows,cols,steps

def static():
    begin=time.perf_counter();A,d,C,f,T,offset,rows,cols,steps=inverse_map();D=(A@T).tocsr();D.eliminate_zeros();D.sort_indices();rhs=d['rhs']-A@offset
    assert np.array_equal(d['sense'][rows],f['sense'])
    assert np.array_equal(d['names'][cols],f['names']) and np.array_equal(d['types'][cols],f['types'])
    assert np.array_equal(np.asarray(d['objective']@T).ravel(),f['objective']) and F(float(d['constant']))+sum(F(float(w))*F(float(x)) for w,x in zip(d['objective'],offset) if w and x)==F(float(f['constant']))
    # Every changed coefficient and RHS is checked independently as binary rationals.
    changed=np.flatnonzero(np.diff(T.indptr)==0);aliases=np.flatnonzero((np.diff(T.indptr)==1)&(np.asarray(T@np.arange(C.shape[1])).ravel()!=np.arange(A.shape[1])))
    affected=np.unique(A[:,np.union1d(changed,aliases)].tocoo().row);checks=0
    for i in affected:
        exact=collections.defaultdict(F);rr=F(float(d['rhs'][i]));a,b=A.indptr[i:i+2]
        for j,w in zip(A.indices[a:b],A.data[a:b]):
            rr-=F(float(w))*F(float(offset[j]))
            for k in T.indices[T.indptr[j]:T.indptr[j+1]]:exact[int(k)]+=F(float(w))
        aa,bb=D.indptr[i:i+2];actual=dict(zip(D.indices[aa:bb],D.data[aa:bb]));exact={j:w for j,w in exact.items() if w}
        assert set(exact)==set(actual)
        for q in range(aa,bb):
            value=float(exact[int(D.indices[q])]);assert F(value)==exact[int(D.indices[q])];D.data[q]=value
        rhs[i]=float(rr);assert F(float(rhs[i]))==rr
        checks+=1
    assert (D[rows]!=C).nnz==0 and np.array_equal(rhs[rows],f['rhs'])
    # Build canonical primitive rational vectors from surviving constraints.
    def canonical(i):
        a,b=D.indptr[i:i+2];js=D.indices[a:b];ws=D.data[a:b];sg=-1 if d['sense'][i]=='>' else 1;ss='=' if d['sense'][i]=='=' else '<';r=F(sg*float(rhs[i]))
        if not len(js):return None,r,ss
        first=F(sg*float(ws[0]));scale=abs(first) if ss=='<' else first
        return (ss,tuple(map(int,js)),tuple(F(sg*float(w))/scale for w in ws)),r/scale,ss
    kept={};methods=collections.Counter()
    for i in rows:
        key,b,s=canonical(i)
        if key is not None:kept.setdefault(key,[]).append(b)
    keptset=set(map(int,rows));bound_map={int(r['column']):r for r in csv.DictReader((OUT/'COMPACT_BOUND_TIGHTENING.csv').open(encoding='utf-8'))}
    for i in range(A.shape[0]):
        if i in keptset:continue
        key,b,s=canonical(i)
        if key is None:
            assert b==0 if s=='=' else b>=0;methods['EXACT_ZERO_OR_SAFE_CONSTANT']+=1;continue
        if key in kept and ((b in kept[key]) if s=='=' else min(kept[key])<=b):methods['RETAINED_PROPORTIONAL_ROW']+=1;continue
        aa,bb=D.indptr[i:i+2];js=D.indices[aa:bb];ws=D.data[aa:bb];sg=-1 if d['sense'][i]=='>' else 1
        if s=='=':
            assert all(f['lower'][j]==f['upper'][j] for j in js)
            assert sum(F(float(w))*F(float(f['lower'][j])) for j,w in zip(js,ws))==F(float(rhs[i]));methods['EXACT_FIXED_BOUND_EQUALITY']+=1;continue
        upper=F(0)
        for j,w in zip(js,ws):
            v=float(f['upper'][j] if sg*w>0 else f['lower'][j]);assert abs(v)<1e90;upper+=F(sg*float(w))*F(v)
        assert upper<=F(sg*float(rhs[i]));methods['EXACT_RETAINED_VARIABLE_BOUNDS']+=1
    # Initial eliminated-column bounds must follow from definition and retained bounds.
    for j in range(A.shape[1]):
        if not np.isfinite(d['lower'][j]) and not np.isfinite(d['upper'][j]):continue
        a,b=T.indptr[j:j+2]
        lo=hi=F(float(offset[j]))
        if b>a:
            k=int(T.indices[a]);lo+=F(float(f['lower'][k]));hi+=F(float(f['upper'][k]))
        assert not np.isfinite(d['lower'][j]) or lo>=F(float(d['lower'][j]))
        assert not np.isfinite(d['upper'][j]) or hi<=F(float(d['upper'][j]))
        if d['types'][j]=='B' and b>a:assert f['types'][int(T.indices[a])]=='B'
    bounds=verify_bounds(A,d,T,offset)
    with np.load(OUT/'C2_RETAINED_AXES.npz') as axes:original_rows=axes['C1_original_rows']
    with (OUT/'COMPACT_LP_REDUNDANCY_CLASSIFICATION.csv').open(encoding='utf-8') as stream:classification=[v for v in csv.DictReader(stream) if v.get('stage','PR160_TRANSPORT')=='PR160_TRANSPORT']
    for v in classification:v['stage']='PR160_TRANSPORT'
    for i in range(A.shape[0]):
        original_id=int(original_rows[i]);compact_link=str(d['row_names'][i]).startswith('node_activity_link[')
        if i not in keptset or compact_link:
            classification.append(dict(original_row=original_id,row_SHA256=r.row_hash(A,d,i),classification='REDUNDANT_OVER_COMPACT_LP_RELAXATION' if i not in keptset else 'UNKNOWN',decision='DELETE' if i not in keptset else 'KEEP',proof='Independent exact C1 affine preimage row implication' if i not in keptset else 'No safe deletion of integral node activity link established; retained',stage='C2_STATIC'))
    table('COMPACT_LP_REDUNDANCY_CLASSIFICATION.csv',classification,['stage','original_row','row_SHA256','classification','decision','proof'])
    result=dict(PASS=True,all_C1_rows_checked=A.shape[0],retained_rows=len(rows),removed_rows=A.shape[0]-len(rows),deleted_row_proof_methods=dict(methods),eliminated_columns=len(steps),inverse_algebra_all_columns=True,exact_changed_rows_checked=checks,all_original_column_bounds_implied=True,bound_tightening=bounds,objective_exact=True,coefficient_rounding=False,production_deletion_decision_imported=False,wall=time.perf_counter()-begin)
    write('SUPERCOMPACT_INDEPENDENT_VERIFICATION.json',result);print('STATIC_INDEPENDENT_PASS',result,flush=True);return result

def verify_bounds(compactA=None,compactd=None,T=None,offset=None):
    from v42_strengthening.analysis import graph_inputs
    _,_,A,d,_,_=inputs();sites,initial,arcs,battery,_=graph_inputs();names=list(map(str,d['names']));index={n:j for j,n in enumerate(names)}
    proof=json.loads((OLD/'M1_PQ_ENVELOPE_CERTIFICATE.json').read_text(encoding='utf-8'));r.independent_vertices(A,d)
    points=[tuple(map(F,v)) for v in proof['PCS16_vertices']];qlo=min(v[1] for v in points);qhi=max(v[1] for v in points)
    envelope={}
    rf=np.asarray([str(n).split('[')[0] for n in d['row_names']]);energy=np.flatnonzero(rf=='energy_balance')
    for z,u in enumerate(sorted(initial)):
        lo=[F(battery.minimum)]*97;hi=[F(battery.maximum)]*97;lo[0]=hi[0]=F(battery.initial);lo[96]=hi[96]=F(battery.terminal)
        ch=dis=None;cost=[F(0)]*96
        for t in range(96):
            row=int(energy[z*96+t]);a,b=A.indptr[row:row+2]
            for j,w in zip(A.indices[a:b],A.data[a:b]):
                n=names[j]
                if n.startswith('Pch'):ch=-F(float(w))
                elif n.startswith('Pdis'):dis=F(float(w))
                elif n.startswith('arc['):
                    uu,kk=n[4:-1].split(',');k=int(kk);assert uu==u and arcs[k][1]==t and F(float(w))==F(arcs[k][-1].energy_kwh);cost[t]=max(cost[t],F(float(w)))
        assert ch and dis
        for t in range(96):lo[t+1]=max(lo[t+1],lo[t]-dis*F(battery.p_limit)-cost[t]);hi[t+1]=min(hi[t+1],hi[t]+ch*F(battery.p_limit))
        for t in reversed(range(96)):lo[t]=max(lo[t],lo[t+1]-ch*F(battery.p_limit));hi[t]=min(hi[t],hi[t+1]+dis*F(battery.p_limit)+cost[t])
        envelope[u]=(lo,hi)
    count=collections.Counter()
    with (OUT/'COMPACT_BOUND_TIGHTENING.csv').open(encoding='utf-8') as stream:
        for v in csv.DictReader(stream):
            n=v['name'];newlo=F(float(v['new_lower']));newhi=F(float(v['new_upper']))
            if v['proof'].startswith('SINGLETON_EQUALITY:'):
                i=int(v['proof'].split(':')[1]);j=int(v['column']);assert newlo==newhi
                # Exact original C1 equality after independently reconstructed aliases.
                row=compactA[i]@T;row.eliminate_zeros();rhs=F(float(compactd['rhs'][i]))
                aa,bb=compactA.indptr[i:i+2]
                for k,w in zip(compactA.indices[aa:bb],compactA.data[aa:bb]):rhs-=F(float(w))*F(float(offset[k]))
                rr=T[j].indices
                if len(rr):
                    assert len(row.indices)==1 and row.indices[0]==rr[0]
                    assert F(float(row.data[0]))*(newlo-F(float(offset[j])))==rhs
                else:assert not row.nnz and rhs==0 and newlo==F(float(offset[j]))
                count['SINGLETON_FIXED_EQUALITY']+=1
            elif n.startswith('Q['):assert newlo<=qlo and newhi>=qhi;count['PCS_GLOBAL_Q']+=1
            elif n.startswith('SOC['):
                u,t=n[4:-1].split(',');lo,hi=envelope[u];assert newlo<=lo[int(t)] and newhi>=hi[int(t)];count['SOC_ENVELOPE']+=1
            elif n.startswith('node_activity['):
                u,s,t=n[14:-1].split(',');assert int(t)==0 and newlo==newhi==int(s==initial[u]);count['SOURCE_UNIT_MASS']+=1
            else:raise AssertionError('UNKNOWN_BOUND_PROOF')
    return dict(PASS=True,checked=sum(count.values()),methods=dict(count),decision_code_reused=False)

if __name__=='__main__':
    import sys
    if 'transport' in sys.argv:transport()
    else:static()
