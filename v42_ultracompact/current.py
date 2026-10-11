"""Selected C3A reductions regenerated from the current C2 matrix.

No historical row ID, matrix, point or PASS packet enters this implementation.
The selected PR162 local Farkas and unit-flow affine-support techniques are
reused. Security rows (including new SVR/current rows) are conservatively kept.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction as F
from time import perf_counter
import numpy as np

from .polytope import minimal, farkas, vertices, down, up
from .support import domains, exact_sources, union_upper
from v42_m1_hybrid.blocks import matrix_sha

POLICY='SELECTED_EXACT_CURRENT_MATRIX_PROOFS'
SOURCES=('v42_ultracompact/current.py','v42_ultracompact/current_verify.py',
         'v42_ultracompact/polytope.py','v42_ultracompact/support.py')

def family(name):return str(name).split('[',1)[0]

def row(A,d,i):
    a,b=A.indptr[i:i+2];sign=-1 if d['sense'][i]=='>' else 1
    return {int(j):F(sign*float(w)) for j,w in zip(A.indices[a:b],A.data[a:b])},F(sign*float(d['rhs'][i]))

def size(A,d):
    return dict(rows=A.shape[0],columns=A.shape[1],binaries=int(np.count_nonzero(d['types']=='B')),nnz=A.nnz)

@dataclass
class CurrentC3A:
    original:object
    original_data:dict
    A:object
    d:dict
    row_ids:object
    certificates:list
    bounds:list
    proof:dict
    physical_original:object=None
    physical_original_data:object=None

def reduce_current_c3a(A,d,graph,progress=None,physical_original=None):
    began=perf_counter();vf=[family(n) for n in d['names']]
    rf=[family(n) for n in d['row_names']];byname={str(n):j for j,n in enumerate(d['names'])}
    physical=defaultdict(dict);pcs=defaultdict(list);links=defaultdict(dict)
    for j,n in enumerate(d['names']):
        if vf[j] in ('Pch','Pdis','Q'):
            physical[str(n).split('[',1)[1][:-1]][vf[j]]=j
    for i,fam in enumerate(rf):
        if fam not in ('PCS16','connected_Pch','connected_Pdis','connected_Qmax','connected_Qmin'):continue
        v,r=row(A,d,i);axes={str(d['names'][j]).split('[',1)[1][:-1] for j in v if vf[j] in ('Pch','Pdis','Q')}
        if len(axes)!=1:raise ValueError('CURRENT_C3A_LOCAL_PHYSICAL_AXIS_DRIFT')
        key=axes.pop()
        if fam=='PCS16':pcs[key].append(i)
        else:links[key][fam]=i
    certs=[];local_cache={};polygons={};p_limit=F(float(graph[3].p_limit))
    for key,ids in pcs.items():
        # C2 fixed-source singleton removals can leave a partial block. Such
        # blocks are kept; they are still safely enclosed by the common PCS.
        if len(ids)!=16 or set(physical[key])!={'Pch','Pdis','Q'}:continue
        ch,pd,q=(physical[key][f] for f in ('Pch','Pdis','Q'))
        stay_ids={j for i in ids for j in row(A,d,i)[0] if vf[j] in ('route_flow','node_activity')}
        if len(stay_ids)>1:raise ValueError('CURRENT_C3A_LOCAL_CONNECTION_AXIS_DRIFT')
        stay=next(iter(stay_ids)) if stay_ids else None
        planes=[];sources=[]
        for i in ids:
            v,r=row(A,d,i);p=v.get(pd,F(0));qq=v.get(q,F(0))
            if d['sense'][i]!='<' or v.get(ch,F(0))!=-p or set(v)-{ch,pd,q,stay}:
                raise ValueError('CURRENT_C3A_PCS_STRUCTURE_DRIFT')
            if stay is not None and r:raise ValueError('CURRENT_C3A_NONHOMOGENEOUS_PCS')
            planes.append((p,qq,-v.get(stay,F(0)) if stay is not None else r))
            sources.append([dict(row=i,weight='1')])
        for sign,col,other,fam in ((1,pd,ch,'connected_Pdis'),(-1,ch,pd,'connected_Pch')):
            support=[]
            if fam in links[key]:
                i=links[key][fam];v,r=row(A,d,i)
                expected={col:F(1)}
                if stay is not None:expected[stay]=-p_limit
                if v!=expected or r!=(0 if stay is not None else p_limit):
                    raise ValueError('CURRENT_C3A_CONNECTED_P_STRUCTURE_DRIFT')
                support.append(dict(row=i,weight='1'))
            elif stay is None and F(float(d['upper'][col]))<=p_limit:
                support.append(dict(bound=col,endpoint='upper',weight='1'))
            else:break
            if d['lower'][other]!=0:raise ValueError('CURRENT_C3A_POWER_NONNEGATIVITY_DRIFT')
            support.append(dict(bound=other,endpoint='lower',weight='1'))
            planes.append((F(sign),F(0),p_limit));sources.append(support)
        if len(planes)!=18:continue
        signature=tuple(planes)
        if signature not in local_cache:local_cache[signature]=minimal(planes)
        keep,removed=local_cache[signature];polygons[signature]=vertices(planes)
        for face,certificate in removed.items():
            if face>=16:continue
            certs.append(_certificate(ids[face],'PCS_FARKAS',certificate,sources,stay))
        for fam,target in (('connected_Qmax',(F(0),F(1),F(float(graph[3].pcs_kva)))),
                           ('connected_Qmin',(F(0),F(-1),F(float(graph[3].pcs_kva))))):
            if fam not in links[key]:continue
            i=links[key][fam];v,r=row(A,d,i);expected={q:target[1]}
            if stay is not None:expected[stay]=-target[2]
            if v!=expected or r!=(0 if stay is not None else target[2]):
                raise ValueError('CURRENT_C3A_CONNECTED_Q_STRUCTURE_DRIFT')
            proof=farkas(target,[planes[j] for j in keep])
            if proof:
                bound,a,b,l,m=proof
                c=dict(support=[keep[a],keep[b]],multipliers=[str(l),str(m)],slack=str(target[2]-bound))
                certs.append(_certificate(i,'Q_LINK_FARKAS',c,sources,stay))
    gone={p['row'] for p in certs}
    # Every terminal equality is checked against an exact sparse sum of actual
    # retained C2 flow rows. No textbook/index assumption is substituted.
    flow=defaultdict(list)
    for i,fam in enumerate(rf):
        if fam!='flow':continue
        owners={str(d['names'][j]).split('[',1)[1].split(',',1)[0] for j in row(A,d,i)[0] if vf[j] in ('route_flow','node_activity')}
        if len(owners)==1:flow[owners.pop()].append(i)
    for i,fam in enumerate(rf):
        if fam!='terminal_location':continue
        target,r=row(A,d,i);owners={str(d['names'][j]).split('[',1)[1].split(',',1)[0] for j in target if vf[j] in ('route_flow','node_activity')}
        if len(owners)!=1:continue
        ids=flow[owners.pop()];total=defaultdict(F);rhs=F(0)
        for j in ids:
            v,b=row(A,d,j);rhs+=b
            for k,w in v.items():total[k]+=w
        if {k:w for k,w in total.items() if w}==target and rhs==r:
            certs.append(dict(row=i,kind='FLOW_EQUALITY_SUM',support=ids));gone.add(i)
    if progress:progress(dict(phase='M_CURRENT_EXACT_C3A_AFFINE_BOUNDS',rows_removed=len(gone)))
    dom=domains(A,d,graph);src=exact_sources(A,d,dom);keys,vectors,constants,times,defs,_=src
    # Reuse a conservative enclosing PCS polygon. Reject unequal local PCS
    # authorities instead of transporting one state proof to another domain.
    if len(polygons)!=1:raise ValueError('CURRENT_C3A_PCS_BOUND_AUTHORITY_UNAVAILABLE_OR_UNEQUAL')
    verts=next(iter(polygons.values()));width=3*len(dom['units'])*len(dom['sites'])
    eligible=[j for j in sorted(keys) if vf[j].startswith(('injection_','response_')) and d['lower'][j]!=d['upper'][j]]
    pairs=list(dict.fromkeys((keys[j],times[j]) for j in eligible));cache={}
    for start in range(0,len(pairs),256):
        chunk=pairs[start:start+256];mid=np.zeros((len(chunk),width));err=mid.copy();tt=[]
        for k,(h,t) in enumerate(chunk):
            for q,x in vectors[h].items():
                lo,hi=down(x),up(x);m=(lo+hi)/2
                mid[k,q]=m;err[k,q]=max(m-lo,hi-m)
            tt.append(t)
        uu=union_upper(mid,err,np.asarray(tt),dom,verts)
        ll=union_upper(-mid,err,np.asarray(tt),dom,verts)
        for pair,l,u in zip(chunk,ll,uu):cache[pair]=(-float(l),float(u))
    bounds=[];e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
    for j in eligible:
        lo,hi=cache[keys[j],times[j]]
        newlo=max(float(d['lower'][j]),float(np.nextafter(down(constants[j])+lo,-np.inf)))
        newhi=min(float(d['upper'][j]),float(np.nextafter(up(constants[j])+hi,np.inf)))
        if newlo>newhi:raise ValueError('CURRENT_C3A_AFFINE_BOUND_CONTRADICTION')
        if newlo>d['lower'][j] or newhi<d['upper'][j]:
            bounds.append(dict(column=j,name=str(d['names'][j]),old_lower=float(d['lower'][j]),old_upper=float(d['upper'][j]),
                new_lower=newlo,new_upper=newhi,definition=defs.get(j),kind='UNIT_DAG_PCS_AFFINE_SUPPORT'))
            e['lower'][j]=newlo;e['upper'][j]=newhi
    rows=np.asarray([i for i in range(A.shape[0]) if i not in gone],dtype=np.int64)
    B=A[rows]  # Exactly one retained-row allocation; no second CSR copy.
    e.update({k:d[k][rows] for k in ('rhs','sense','row_names')})
    full,fd=physical_original if physical_original is not None else (None,None)
    ultra=CurrentC3A(A,d,B,e,rows,certs,bounds,{},full,fd)
    del src, keys, vectors, constants, times, defs, _, cache, dom, pairs, eligible
    from .current_verify import verify_current_c3a
    proof=verify_current_c3a(ultra,graph)
    proof.update(schema='V42_CURRENT_EXACT_C3A_PROOF_V1',C3A_policy=POLICY,
        baseline=size(A,d),selected=size(B,e),baseline_matrix_SHA256=matrix_sha(A),selected_matrix_SHA256=matrix_sha(B),
        removed_families=dict(Counter(rf[p['row']] for p in certs)),bound_families=dict(Counter(vf[p['column']] for p in bounds)),
        fresh_current_matrix_certificates=True,historical_row_indices_read=0,Native_optimize_calls=0,
        selected_PR162_techniques_reused=True,security_rows_kept=True,wall_seconds=perf_counter()-began)
    ultra.proof=proof
    return ultra

def _certificate(target,kind,certificate,sources,stay):
    support=[]
    for face,multiplier in zip(certificate['support'],certificate['multipliers']):
        for item in sources[face]:support.append(dict(item,weight=str(F(item['weight'])*F(multiplier))))
    slack=F(certificate['slack'])
    if slack and stay is not None:support.append(dict(bound=stay,endpoint='lower',weight=str(slack)))
    return dict(row=target,kind=kind,support=support)
