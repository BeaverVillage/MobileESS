"""Four-MESS route-pool restriction: exact simplex selection and source links."""
from collections import defaultdict
from scipy import sparse
from tools.global_local_multistart1800.adapter import *
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.proof import inverse

def path_signature(path):return hashlib.sha256(np.asarray(path,dtype='<i8').tobytes()).hexdigest()
def pool_signature(pools):
    return hashlib.sha256(json.dumps({u:sorted(path_signature(p) for p in paths) for u,paths in sorted(pools.items())},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def unit_vector(case,unit,indices,path):
    selected=set(path);vertices={case.graph[2][k][:2] for k in path}|{(case.graph[2][path[-1]][2],96)}
    values=[]
    for j in indices:
        family,text=str(case.d['names'][j]).split('[',1);axis=text[:-1].split(',');assert axis[0]==unit
        values.append(float(int(axis[1]) in selected) if family=='route_flow' else float((axis[1],int(axis[2])) in vertices))
    return np.asarray(values)

def select_pools(case,candidates,point,size,previous=None,variant=0):
    graph=Graph(case);center=paths_of(case,point);pools={u:[] for u in sorted(graph.origins)}
    authority=paths_of(case,v.load_point(ROOT/RAW_REL))
    for u in pools:
        seen=set()
        def add(path):
            sig=path_signature(path)
            if sig not in seen:graph.validate(u,path);pools[u].append(list(path));seen.add(sig)
        add(center[u]);add(graph.complete(u,[]));add(authority[u])
        if previous:
            for path in previous[u]:add(path)
        choices=[c for c in candidates if c['units']==[u]]
        choices.sort(key=lambda c:(c['estimated_peak_loading'],-c['distance_slots_from_center'],c['signature']))
        buckets=defaultdict(list)
        for c in choices:buckets[str(c['diversity_key'][1:])].append(c)
        # New location/time groups receive admission before a second member of a group.
        ranked=sorted((b[0] for b in buckets.values()),key=lambda c:(c['estimated_peak_loading'],-c['distance_slots_from_center'],c['signature']))
        if variant and ranked:
            shift=(variant*max(1,size-2))%len(ranked);ranked=ranked[shift:]+ranked[:shift]
        for c in ranked+choices:
            if len(pools[u])>=size:break
            add(c['paths'][u])
        assert len(pools[u])>=4 and any(graph.move_indices(p) for p in pools[u]) and graph.complete(u,[]) in pools[u]
        assert center[u] in pools[u]
    return pools

def build_spec(case,point,replay,pools,label,seconds):
    graph=Graph(case);baseline=paths_of(case,point);ids,values=route_values(case,baseline)
    grouped=defaultdict(list)
    for j in ids:grouped[str(case.d['names'][j]).split('[',1)[1].split(',')[0]].append(int(j))
    lambdas=[];rows=[];cols=[];vals=[];lower=case.d['lower'].copy();upper=case.d['upper'].copy();vary=[];unit_values={}
    for u,paths in sorted(pools.items()):
        indices=np.asarray(grouped[u],dtype=int);unit_values[u]=[]
        for ordinal,path in enumerate(paths):
            graph.validate(u,path);vector=unit_vector(case,u,indices,path)
            assert len(vector)==len(indices) and np.isin(vector,(0.,1.)).all()
            unit_values[u].append(vector)
            lambdas.append(dict(unit=u,ordinal=ordinal,name=f'lambda[{u},{ordinal}]',path=path,path_signature=path_signature(path)))
        V=np.vstack(unit_values[u]);lo=V.min(axis=0);hi=V.max(axis=0);lower[indices]=lo;upper[indices]=hi
        varying=np.flatnonzero(lo!=hi)
        for k in varying:
            row=len(vary);vary.append(int(indices[k]));rows.append(row);cols.append(int(indices[k]));vals.append(1.)
            for r,route in enumerate(paths):
                value=V[r,k]
                if value:
                    offset=next(i for i,a in enumerate(lambdas) if a['unit']==u and a['ordinal']==r)
                    rows.append(row);cols.append(len(lower)+offset);vals.append(-float(value))
    L=len(lambdas);link=sparse.csr_matrix((vals,(rows,cols)),shape=(len(vary),len(lower)+L))
    one=sparse.csr_matrix(([1.]*L,([sorted(pools).index(a['unit']) for a in lambdas],[len(lower)+i for i in range(L)])),shape=(4,len(lower)+L))
    A=sparse.vstack([one,link],format='csr');rhs=np.r_[np.ones(4),np.zeros(len(vary))]
    start=np.zeros(L)
    for u in pools:
        chosen=next(i for i,a in enumerate(lambdas) if a['unit']==u and a['path']==baseline[u]);start[chosen]=1
    sig=hashlib.sha256()
    for value in (lower,upper):sig.update(value.tobytes())
    sig.update(v.matrix_sha(A).encode());sig.update(rhs.tobytes())
    spec=dict(method='FOUR_MESS_JOINT_ROUTE_POOL',stage='JOINT',candidate_id=label,family='FOUR_MESS_JOINT',
        pools=pools,pool_signature=pool_signature(pools),lambda_axis=lambdas,center_paths=baseline,center_vector_SHA=v.vector_sha(point),
        center_replay=record(replay),seconds=seconds,source_columns=len(lower),lambda_count=L,source_binary=9322,
        added_binary=L,added_rows=A.shape[0],varying_route_columns=vary,mathematical_model_signature=sig.hexdigest(),
        lambda_Start=start.tolist(),all_four_route_decision_free=True,all384_Mode_free=True,
        original_FULL_contains_restricted_joint=True,restricted_ObjBound_is_Global_LB=False,
        all_four_MOVE_combinations_topologically_selectable=True,no_MOVE_forcing=True)
    return spec,lower,upper,A,rhs

def independent(case,point,spec,lower,upper,A,rhs):
    assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(case.d)==v.DOMAIN_SHA
    assert spec['source_columns']==case.A.shape[1] and np.count_nonzero(case.d['types']!='C')==9322
    cert=read(spec['center_replay']['path']);assert cert['PASS'] and cert['source_sha']==v.SOURCE_SHA and cert['case_sha']==v.CASE_SHA
    assert cert['point_vector_sha256']==v.vector_sha(point)==spec['center_vector_SHA']
    assert v.file_sha(spec['center_replay']['path'])==spec['center_replay']['sha256']
    graph=Graph(case);center=paths_of(case,point);assert spec['center_paths']==center
    axis=spec['lambda_axis'];assert len(axis)==spec['lambda_count'] and set(spec['pools'])==set(graph.origins)
    assert all(len(paths)>=4 and graph.complete(u,[]) in paths and center[u] in paths and any(graph.move_indices(p) for p in paths) for u,paths in spec['pools'].items())
    authority=paths_of(case,v.load_point(ROOT/RAW_REL))
    assert all(authority[u] in spec['pools'][u] for u in authority),'PR220_AUTHORITY_PATH_MISSING'
    assert pool_signature(spec['pools'])==spec['pool_signature']
    byunit={u:[(i,a) for i,a in enumerate(axis) if a['unit']==u] for u in graph.origins}
    assert all([a['path'] for i,a in byunit[u]]==spec['pools'][u] for u in byunit)
    ids,basevalues=route_values(case,center);lookup={int(j):k for k,j in enumerate(ids)}
    source_route=set(map(int,ids));expected_lower=case.d['lower'].copy();expected_upper=case.d['upper'].copy()
    routevectors={};expected_rows={};original_aliases=inverse(case);alias_checked=0
    for u in sorted(byunit):
        unit_ids=[j for j in ids if str(case.d['names'][j]).split('[',1)[1].split(',')[0]==u]
        vectors=[]
        for offset,entry in byunit[u]:
            assert entry['name']==f"lambda[{u},{entry['ordinal']}]" and path_signature(entry['path'])==entry['path_signature']
            graph.validate(u,entry['path'])
            # Independent indicators from original selected arcs and departure/terminal
            # vertices, checked below against every original affine inverse alias.
            chosen=set(entry['path']);vertices={graph.arcs[k][:2] for k in chosen}|{(graph.arcs[entry['path'][-1]][2],96)}
            vector=[]
            for j in unit_ids:
                name=str(case.d['names'][j]);fields=name.split('[',1)[1][:-1].split(',')
                if name.startswith('route_flow['):value=int(fields[1]) in chosen
                else:value=(fields[1],int(fields[2])) in vertices
                vector.append(float(value))
            vectors.append(vector)
        V=np.vstack(vectors);routevectors[u]=(unit_ids,V)
        path_sets=[set(entry['path']) for offset,entry in byunit[u]]
        vertex_sets=[{graph.arcs[k][:2] for k in entry['path']}|{(graph.arcs[entry['path'][-1]][2],96)} for offset,entry in byunit[u]]
        for k,j in enumerate(unit_ids):
            expected_lower[j]=V[:,k].min();expected_upper[j]=V[:,k].max()
            if expected_lower[j]!=expected_upper[j]:expected_rows[int(j)]={int(j):F(1),**{len(lower)+offset:-F(float(V[r,k])) for r,(offset,a) in enumerate(byunit[u]) if V[r,k]}}
        # Independent affine inverse-alias proof for every original Arc/Node.
        positions={int(j):k for k,j in enumerate(unit_ids)}
        position_set=set(positions)
        for j,name in enumerate(map(str,case.original_d['names'])):
            family=name.split('[',1)[0]
            if family not in ('arc','node_activity') or not name.startswith(family+'['+u+','):continue
            constant,terms=original_aliases(j);assert set(terms)<=position_set,'CROSS_UNIT_OR_NONROUTE_ALIAS'
            axis_fields=name.split('[',1)[1][:-1].split(',')
            for r,(offset,entry) in enumerate(byunit[u]):
                expected=float(int(axis_fields[1]) in path_sets[r]) if family=='arc' else float((axis_fields[1],int(axis_fields[2])) in vertex_sets[r])
                actual=constant+sum(co*F(float(V[r,positions[col]])) for col,co in terms.items())
                assert actual==F(expected) and case.original_d['lower'][j]<=expected<=case.original_d['upper'][j]
            alias_checked+=1
    assert np.array_equal(lower,expected_lower) and np.array_equal(upper,expected_upper)
    nonroute=[j for j in range(len(lower)) if j not in source_route]
    assert np.array_equal(lower[nonroute],case.d['lower'][nonroute]) and np.array_equal(upper[nonroute],case.d['upper'][nonroute])
    assert sorted(expected_rows)==sorted(spec['varying_route_columns']) and A.shape==(4+len(expected_rows),len(lower)+len(axis))
    for i,u in enumerate(sorted(byunit)):
        row=A.getrow(i);assert dict(zip(row.indices,map(F,map(float,row.data))))=={len(lower)+offset:F(1) for offset,entry in byunit[u]} and rhs[i]==1
    for i,j in enumerate(spec['varying_route_columns'],4):
        row=A.getrow(i);assert dict(zip(row.indices,map(F,map(float,row.data))))==expected_rows[j] and rhs[i]==0
    start=np.asarray(spec['lambda_Start']);assert np.isin(start,(0.,1.)).all() and np.array_equal(A@np.r_[point,start],rhs)
    for u in byunit:assert sum(start[offset] for offset,a in byunit[u])==1 and all(not start[offset] or a['path']==center[u] for offset,a in byunit[u])
    from tools.u4_primal_alns.pilot import PARAMS
    excess=max(0.,float((lower-point).max()),float((point-upper).max()));assert excess<=PARAMS['FeasibilityTol']
    return dict(PASS=True,Optimize_calls=0,source_matrix_domain_objective_unchanged=True,Original_FULL_contains_joint=True,
        exact_lambda_simplex_and_route_links=True,original_Arc_Node_Flow_Alias_exact=alias_checked,
        proof='Binary lambda plus one-route simplex selects exactly one original complete DAG for each of four units. Exact route links and inverse aliases give its original Arc/Node/Flow. Remaining original source rows/bounds/types/objective are unchanged, so every restricted feasible point projects into original FULL.',
        all_four_route_decisions=True,all_four_MOVE_joint_combination_topology=True,alternative_joint_SOC_Grid_feasibility_not_assumed=True,
        current_FULL_center_included=True,unchanged_raw_Start_valid=True,center_box_residual=excess,
        all384_Mode_P_Q_SOC_original_free=True,pool_counts={u:len(p) for u,p in spec['pools'].items()},no_MOVE_forcing=True)
