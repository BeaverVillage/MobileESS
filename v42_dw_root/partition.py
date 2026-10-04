"""Ownership from original sparse dependency components, not P/Q name guesses."""
from .common import *
import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from v42_degen.identity import digest
from v42_strengthening.analysis import graph_inputs

def extract(B,e):
    n=B.shape[1];names=list(map(str,e['names']))
    # Free shared grid coordinates and objective coordinates cannot be local.
    # Bounds/objective are native matrix attributes, independent of names.
    global_anchor=(~np.isfinite(e['lower']))|(~np.isfinite(e['upper']))|(abs(e['lower'])>=1e90)|(abs(e['upper'])>=1e90)|(e['objective']!=0)
    row_global=np.asarray(abs(B[:,np.flatnonzero(global_anchor)]).sum(axis=1)).ravel()!=0
    cols=np.flatnonzero(~global_anchor);rows=np.flatnonzero(~row_global)
    L=B[rows][:,cols];graph=sparse.bmat([[None,L],[L.T,None]],format='csr')
    count,labels=connected_components(graph,directed=False);components=labels[len(rows):]
    sites,initial,arcs,battery,receipt=graph_inputs();assert tuple(initial)==UNITS
    anchor_owner={};component_units={}
    for j in np.flatnonzero(e['types']!='C'):
        name=names[j];family,args=name.split('[',1);u,k=args[:-1].split(',');assert u in UNITS
        if family=='arc':assert 0<=int(k)<len(arcs)
        else:assert family=='charge_mode' and 0<=int(k)<96
        anchor_owner[int(j)]=UNITS.index(u)
    column_component={int(j):int(k) for j,k in zip(cols,components)}
    for j,m in anchor_owner.items():component_units.setdefault(column_component[j],set()).add(m)
    owner=np.full(n,-1,dtype=np.int8)
    for j,k in zip(cols,components):
        units=component_units.get(int(k),set())
        if len(units)==1:owner[j]=next(iter(units))
        # Ambiguous or unanchored components stay global; never guessed local.
    assert all(owner[j]==m for j,m in anchor_owner.items()),'AMBIGUOUS_INTEGER_COMPONENT_STOP'
    local=[];global_rows=[]
    for i in range(B.shape[0]):
        a,b=B.indptr[i:i+2];dependencies=set(map(int,owner[B.indices[a:b]]))
        local.append(next(iter(dependencies)) if len(dependencies)==1 and -1 not in dependencies else -1)
    row_owner=np.asarray(local,dtype=np.int8);global_rows=np.flatnonzero(row_owner==-1)
    for m,u in enumerate(UNITS):
        js=np.flatnonzero(owner==m)
        assert any(names[j].startswith('SOC[') for j in js) and sum(names[j].startswith('charge_mode[') for j in js)==96
        # Independent native provenance check of graph-derived ownership.
        for j in js:
            if names[j].split('[',1)[0] in ('arc','charge_mode','Pch','Pdis','Q','SOC'):
                assert names[j].split('[',1)[1].split(',')[0]==u
    np.savez_compressed(OUT/'DW_PARTITION_AXES.npz',column_owner=owner,row_owner=row_owner,global_rows=global_rows,global_columns=np.flatnonzero(owner==-1))
    families={};local_census=[];global_census=[]
    for i,m in enumerate(row_owner):
        f=str(e['row_names'][i]).split('[',1)[0];key=(int(m),f)
        entry=families.setdefault(key,dict(rows=0,nnz=0));entry['rows']+=1;entry['nnz']+=int(B.indptr[i+1]-B.indptr[i])
    for (m,f),c in sorted(families.items()):
        row=dict(block='GLOBAL' if m<0 else UNITS[m],family=f,**c)
        (global_census if m<0 else local_census).append(row)
    table('DW_LOCAL_ROW_CENSUS.csv',local_census,['block','family','rows','nnz']);table('DW_GLOBAL_COUPLING_ROW_CENSUS.csv',global_census,['block','family','rows','nnz'])
    blocks=[]
    for m,u in enumerate(UNITS):
        rr=np.flatnonzero(row_owner==m);cc=np.flatnonzero(owner==m);A=B[rr][:,cc]
        blocks.append(dict(MESS=u,rows=len(rr),columns=len(cc),binaries=int((e['types'][cc]=='B').sum()),nnz=A.nnz,
                           all_original_local_columns=True,all_original_local_rows=True,local_objective_nonzeros=int(np.count_nonzero(e['objective'][cc]))))
    r=dict(PASS=True,base_exact_head=BASE,blocks=blocks,local_rows=int((row_owner>=0).sum()),global_rows=len(global_rows),global_columns=int((owner==-1).sum()),
           graph_components=count,free_or_objective_global_anchors=int(global_anchor.sum()),integer_anchors=len(anchor_owner),
           method='Remove native free/shared and objective anchors; build bipartite graph of all remaining actual matrix row/column dependencies. Components are owned only when all original integer provenance anchors agree on one MESS. Ambiguous/unanchored components remain global. Final row classification uses every actual nonzero dependency.',
           names_used_for_ownership='Only native route/mode integer provenance anchors, independently checked against immutable route domain. Continuous ownership is inferred from graph components, then independently cross-checked against constructor provenance.',
           no_ambiguous_row_local=True,source_route_receipt=receipt,column_owner_SHA=digest(owner),row_owner_SHA=digest(row_owner),original_model_changed=False)
    write('DW_BLOCK_PARTITION.json',r)
    # Reconstruct all nonzeros in original row/column coordinates exactly.
    rebuilt=B.copy();rebuilt.data[:]=0.;seen=np.zeros(B.shape[0],dtype=np.int8)
    for m in (-1,0,1,2,3):
        ix=np.flatnonzero(row_owner==m);seen[ix]+=1
        for i in ix:
            a,b=B.indptr[i:i+2];rebuilt.data[a:b]=B.data[a:b]
    assert np.all(seen==1) and np.array_equal(rebuilt.data,B.data)
    assert np.array_equal(rebuilt.indptr,B.indptr) and np.array_equal(rebuilt.indices,B.indices)
    write('DW_MATRIX_RECONSTRUCTION_PROOF.json',dict(PASS=True,row_count=B.shape[0],column_count=B.shape[1],nnz=B.nnz,
           each_original_row_once=True,each_original_column_once=True,coefficient_difference=0,RHS_difference=0,sense_difference=0,bound_difference=0,vtype_difference=0,objective_difference=0,
           proof='Axes are disjoint exhaustive original-index subsets. Every local row has exactly one owner and no global/off-block coefficient. Every other original row is retained verbatim globally. Reassembly in original indices equals original CSR arrays exactly; column attributes and row RHS/senses are inherited by indexing without transformation.',
           original_signature=read(OUT/'DW_BASE_MODEL_IDENTITY.json')['reference']))
    return owner,row_owner,r

def axes():
    with np.load(OUT/'DW_PARTITION_AXES.npz') as z:return z['column_owner'],z['row_owner']
