"""Independent receipt verifier. Does not import or call the reducer."""
from fractions import Fraction as Q
import json
import numpy as np
import scipy.sparse as sp
from .common import *

def check_alias_edge(a,sense,rhs,edge):
    r,x,y=map(int,edge);p,q=map(int,a.indptr[r:r+2])
    if sense[r]!='=' or rhs[r]!=0 or q-p!=2:raise ValueError('ALIAS_ORIGINAL_ROW')
    if set(map(int,a.indices[p:q]))!={x,y}:raise ValueError('ALIAS_COLUMN_IDENTITY')
    c,d=a.data[p:q]
    if abs(c)!=1 or d!=-c:raise ValueError('ALIAS_COEFFICIENT')

def exact_interval(a,r,lb,ub,sense,rhs):
    p,q=map(int,a.indptr[r:r+2]);lo=Q(0);hi=Q(0);s=sense[r]
    for j,c in zip(a.indices[p:q],a.data[p:q]):
        l,u=(lb[j],ub[j]) if c>=0 else (ub[j],lb[j])
        if (s!='<' and not np.isfinite(l)) or (s!='>' and not np.isfinite(u)):raise ValueError('UNBOUNDED_INTERVAL_CERTIFICATE')
        if s!='<':lo+=Q(float(c))*Q(float(l))
        if s!='>':hi+=Q(float(c))*Q(float(u))
    b=Q(float(rhs[r]))
    if not ((s=='<' and hi<=b) or (s=='>' and lo>=b) or (s=='=' and lo==b and hi==b)):
        raise ValueError('ROW_NOT_LP_BOUND_REDUNDANT:'+str(r))

def check_duplicate(a,sense,rhs,pair):
    r,s=map(int,pair);p,q=map(int,a.indptr[r:r+2]);u,v=map(int,a.indptr[s:s+2])
    if sense[r]!=sense[s] or rhs[r]!=rhs[s] or not np.array_equal(a.indices[p:q],a.indices[u:v]) or not np.array_equal(a.data[p:q],a.data[u:v]):
        raise ValueError('FALSE_DUPLICATE')

def check_domination(a,sense,rhs,pair):
    r,s=map(int,pair);p,q=map(int,a.indptr[r:r+2]);u,v=map(int,a.indptr[s:s+2])
    if q==p or not np.array_equal(a.indices[p:q],a.indices[u:v]):raise ValueError('DOMINATION_AXIS')
    factor=Q(float(a.data[p]))/Q(float(a.data[u]))
    if any(Q(float(c))!=factor*Q(float(d)) for c,d in zip(a.data[p:q],a.data[u:v])):
        raise ValueError('NONEXACT_PROPORTION')
    # Rewrite row s in row r's coordinates. Check implication in rational
    # arithmetic, including negative-factor sense reversal and equality.
    source=sense[s] if factor>0 or sense[s]=='=' else ('>' if sense[s]=='<' else '<')
    b=Q(float(rhs[s]))*factor;target=sense[r];limit=Q(float(rhs[r]))
    valid=(target=='<' and source in ('<','=') and b<=limit or
           target=='>' and source in ('>','=') and b>=limit or
           target=='=' and source=='=' and b==limit)
    if not valid:raise ValueError('ROW_NOT_LP_DOMINATED')

def verify(name):
    a=sp.load_npz(LOCAL/'A0_MATRIX.npz');z=attributes()
    proof=proof_data(name); mapping=proof['mapping']; n=a.shape[1]
    adj=[None]*n
    for e in proof['alias_edges']:
        check_alias_edge(a,z['sense'],z['rhs'],e)
        _,x,y=map(int,e)
        if adj[x] is None:adj[x]=[]
        if adj[y] is None:adj[y]=[]
        adj[x].append(y);adj[y].append(x)
    # Independently derive connected components before accepting group-bound
    # implications. A forged group cannot transport a bound to another column.
    components=np.full(n,-1,dtype=np.int64);component_count=0
    for start in range(n):
        if components[start]>=0:continue
        stack=[start];components[start]=component_count
        while stack:
            x=stack.pop()
            for y in adj[x] or []:
                if components[y]<0:components[y]=component_count;stack.append(y)
        component_count+=1
    groups=proof['groups']
    if not np.array_equal(components,groups):raise ValueError('UNPROVED_BOUND_GROUPS')
    glb=np.full(component_count,-np.inf);gub=np.full(component_count,np.inf)
    np.maximum.at(glb,groups,z['lb']);np.minimum.at(gub,groups,z['ub'])
    oldlb=glb[groups];oldub=gub[groups]
    order=np.argsort(groups,kind='stable');offset=np.r_[0,np.cumsum(np.bincount(groups))]
    def members(g):return order[offset[g]:offset[g+1]]
    for r,g,value in zip(proof.get('resource_bound_rows',[]),proof.get('resource_bound_groups',[]),proof.get('resource_bound_values',[])):
        r=int(r);g=int(g);p,q=map(int,a.indptr[r:r+2]);terms={}
        for j,c in zip(a.indices[p:q],a.data[p:q]):
            group=int(groups[j]);terms[group]=terms.get(group,Q(0))+Q(float(c))
        terms={g:c for g,c in terms.items() if c}
        if z['sense'][r] not in ('<','=') or z['rhs'][r]!=value or value<0 or g not in terms or any(c!=1 for c in terms.values()) or np.any(oldlb[a.indices[p:q]]<0):raise ValueError('UNPROVED_RESOURCE_BOUND')
        oldub[members(g)]=np.minimum(oldub[members(g)],value)
    for iteration,r,group in proof['bound_receipts']:
        r=int(r);group=int(group);p,q=map(int,a.indptr[r:r+2]);terms={}
        for j,c in zip(a.indices[p:q],a.data[p:q]):
            if oldlb[j]==0 and oldub[j]==0:continue
            g=int(groups[j]);terms[g]=terms.get(g,Q(0))+Q(float(c))
        terms={g:c for g,c in terms.items() if c}
        if len(terms)!=1 or group not in terms or z['rhs'][r]!=0:raise ValueError('UNPROVED_ZERO_BOUND_ROW')
        c=terms[group];ids=members(group);lo=oldlb[ids[0]];hi=oldub[ids[0]];s=z['sense'][r]
        forces=s=='=' or s=='<' and c>0 and lo==0 or s=='<' and c<0 and hi==0 or s=='>' and c>0 and hi==0 or s=='>' and c<0 and lo==0
        if not forces or lo>0 or hi<0:raise ValueError('UNPROVED_ZERO_BOUND_SIGN')
        oldlb[ids]=oldub[ids]=0
    seen=np.zeros(n,dtype=bool);lb=[];ub=[];typ=[];zero_proofs=0
    for start in range(n):
        if seen[start]:continue
        stack=[start];component=[];seen[start]=True
        while stack:
            x=stack.pop();component.append(x)
            for y in adj[x] or []:
                if not seen[y]:seen[y]=True;stack.append(y)
        ids=np.array(component);values=np.unique(mapping[ids])
        if len(values)!=1:raise ValueError('UNPROVED_MAPPING_COMPONENT')
        lo=max(oldlb[ids]);hi=min(oldub[ids]);k=int(values[0])
        if k<0:
            if lo!=0 or hi!=0:raise ValueError('UNPROVED_ZERO_COLUMN')
            zero_proofs+=len(ids)
        else:
            while len(lb)<=k:lb.append(None);ub.append(None);typ.append(None)
            if lb[k] is not None:raise ValueError('MERGED_UNCONNECTED_COMPONENTS')
            lb[k]=lo;ub[k]=hi
            t=set(z['vtype'][ids]);typ[k]='B' if 'B' in t else 'I' if 'I' in t else 'C'
    lb=np.array(lb);ub=np.array(ub);typ=np.array(typ)
    if any(x is None for x in lb):raise ValueError('MAPPING_RANGE')
    co=a.tocoo(); valid=mapping[co.col]>=0
    projected=sp.coo_matrix((co.data[valid],(co.row[valid],mapping[co.col[valid]])),shape=(a.shape[0],len(lb))).tocsr()
    projected.eliminate_zeros();projected.sort_indices()
    # Confirm all merged coefficients exactly, as dyadic rationals. Most rows
    # have no collisions, so only collision rows require Fraction arithmetic.
    rowcounts=np.bincount(co.row[valid],minlength=a.shape[0]);lens=np.diff(projected.indptr)
    collisions=np.flatnonzero(rowcounts>lens)
    for r in collisions:
        exact={};p,q=map(int,a.indptr[r:r+2])
        for j,c in zip(a.indices[p:q],a.data[p:q]):
            k=int(mapping[j])
            if k>=0:exact[k]=exact.get(k,Q(0))+Q(float(c))
        u,v=map(int,projected.indptr[r:r+2]);native={int(j):Q(float(c)) for j,c in zip(projected.indices[u:v],projected.data[u:v])}
        exact={j:c for j,c in exact.items() if c}
        if exact!=native:raise ValueError('NONEXACT_DYADIC_SUBSTITUTION:'+str(r))
    for r in proof['interval_rows']:exact_interval(projected,int(r),lb,ub,z['sense'],z['rhs'])
    for r,s in proof['duplicate_pairs']:
        check_duplicate(projected,z['sense'],z['rhs'],(r,s))
    dominance=proof.get('domination_pairs',np.empty((0,2),dtype=np.int64))
    links={}
    for r,s in dominance:
        check_domination(projected,z['sense'],z['rhs'],(r,s));links[int(r)]=int(s)
    for start in links:
        visited=set();j=start
        while j in links:
            if j in visited:raise ValueError('CYCLIC_DOMINATION_PROOF')
            visited.add(j);j=links[j]
    removed=set(map(int,proof['interval_rows']))|set(map(int,proof['duplicate_pairs'][:,0]))|set(map(int,dominance[:,0]))
    retained=np.array([r for r in range(a.shape[0]) if r not in removed],dtype=np.int64)
    if not np.array_equal(retained,proof['retained_rows']):raise ValueError('UNCERTIFIED_ROW_REMOVAL')
    b=sp.load_npz(LOCAL/(name+'_MATRIX.npz')); zz=attributes(name)
    delta=projected[retained]-b;delta.eliminate_zeros()
    if delta.nnz or not np.array_equal(lb,zz['lb']) or not np.array_equal(ub,zz['ub']) or not np.array_equal(typ,zz['vtype']):raise ValueError('CANDIDATE_MATRIX_DOMAIN_DRIFT')
    if not np.array_equal(z['rhs'][retained],zz['rhs']) or not np.array_equal(z['sense'][retained],zz['sense']):raise ValueError('CANDIDATE_ROW_DRIFT')
    objective=read_artifact('CURRENT_OBJECTIVE_HIERARCHY.json')
    mapped=[]
    for ex in objective:
        d={}
        for j,c in zip(ex['indices'],ex['coefficients']):
            k=int(mapping[j])
            if k>=0:d[k]=d.get(k,Q(0))+Q(float(c))
        mapped.append(dict(name=ex['name'],constant=ex['constant'],indices=list(d),coefficients=[float(c) for c in d.values()]))
        if any(Q(float(c))!=c for c in d.values()):raise ValueError('OBJECTIVE_NONEXACT_SUM')
    write(name+'_OBJECTIVE_HIERARCHY.json',mapped)
    mutations=[]
    if len(proof['alias_edges']):
        bad=proof['alias_edges'][0].copy();bad[1]=n
        try:check_alias_edge(a,z['sense'],z['rhs'],bad)
        except (ValueError,IndexError):mutations.append('alias-column-ID rejected')
        else:raise ValueError('MUTATED_ALIAS_ACCEPTED')
        r,x,y=map(int,proof['alias_edges'][0]);tiny=a[r].copy();tiny.data[0]+=.25
        try:check_alias_edge(tiny,np.array(['=']),np.array([0.]),(0,x,y))
        except ValueError:mutations.append('alias-coefficient rejected')
        else:raise ValueError('MUTATED_ALIAS_COEFFICIENT_ACCEPTED')
    if len(proof['interval_rows']):
        r=int(proof['interval_rows'][0]); br=z['rhs'].copy();bs=z['sense'].copy();bs[r]='=';br[r]=1e100
        try:exact_interval(projected,r,lb,ub,bs,br)
        except ValueError:mutations.append('bound-row RHS/sign rejected')
        else:raise ValueError('MUTATED_BOUND_ACCEPTED')
    if len(proof['duplicate_pairs']):
        r,s=map(int,proof['duplicate_pairs'][0]);tiny=projected[[r,s]]
        rr=np.array([z['rhs'][r],z['rhs'][s]+1]);ss=np.array([z['sense'][r],z['sense'][s]])
        try:check_duplicate(tiny,ss,rr,(0,1))
        except ValueError:mutations.append('duplicate-RHS mismatch rejected')
        else:raise ValueError('MUTATED_DUPLICATE_ACCEPTED')
    result=dict(PASS=True,candidate=name,original_matrix_checks=True,alias_edges=len(proof['alias_edges']),
                zero_columns=zero_proofs,interval_rows=len(proof['interval_rows']),duplicate_rows=len(proof['duplicate_pairs']),
                zero_bound_tightenings=len(proof['bound_receipts']),
                resource_bound_tightenings=len(proof.get('resource_bound_rows',[])),
                exact_dyadic_collision_rows=len(collisions),all_objective_components=len(mapped),
                proportional_dominated_rows=len(dominance),removed_rows=len(removed),original_to_compressed=True,compressed_to_original=True,
                FULL_LP_equivalence=True,mutation_rejections=mutations,
                production_reducer_imported=False,files=[record(LOCAL/(name+s)) for s in ('_PROOF.npz','_MATRIX.npz','_ATTRIBUTES.npz')])
    write(name+'_INDEPENDENT_VERIFICATION.json',result); print(result,flush=True)
    return result

def run():
    results=[verify(x) for x in ('A1R','A2SC')]
    write('A_STAGE_INDEPENDENT_VERIFICATION.json',dict(PASS=all(x['PASS'] for x in results),candidates=results))

if __name__=='__main__':run()
