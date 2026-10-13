"""Independent topology, inverse-alias, fixing and Hamming verification."""
from collections import defaultdict
from tools.global_local_multistart1800.adapter import *
from v42_common_mess.fixed_pattern import values_for

def inverse(case):
    direct={int(j):i for i,j in enumerate(case.selected_columns)};aliases={int(a['column']):a for a in case.aliases};cache={}
    def expand(j):
        if j in cache:return cache[j]
        if j in direct:answer=(F(0),{direct[j]:F(1)})
        else:
            a=aliases[j];constant=F(float(a['constant']));terms=defaultdict(F)
            for k,c in a['terms'].items():
                offset,parts=expand(int(k));weight=F(float(c));constant+=weight*offset
                for col,value in parts.items():terms[col]+=weight*value
            answer=constant,{j:c for j,c in terms.items() if c}
        cache[j]=answer;return answer
    return expand

def neighborhood(case,center,spec,low,high):
    d=case.d;assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(d)==v.DOMAIN_SHA
    assert np.count_nonzero(d['types']!='C')==9322
    receipt=read(spec['center_full_replay']['path'])
    assert v.file_sha(spec['center_full_replay']['path'])==spec['center_full_replay']['sha256']
    assert receipt['PASS'] and receipt['source_sha']==v.SOURCE_SHA and receipt['case_sha']==v.CASE_SHA and receipt['point_vector_sha256']==v.vector_sha(center)
    assert spec['center_vector_sha256']==v.vector_sha(center)
    arcs=case.graph[2];paths=spec['center_paths'];closures=spec['closures'];allow={u:set(c['allowed_arcs']) for u,c in closures.items()}
    for u,p in paths.items():
        assert u not in allow or set(p)<=allow[u]
    nodes={u:{arcs[k][:2] for k in c['inner_arcs']}|{arcs[k][2:4] for k in c['inner_arcs']} for u,c in closures.items()}
    # Independently rebuild the box from named coordinates; do not trust the
    # builder's fixed-column list or its claimed openness counts.
    el,eu=d['lower'].copy(),d['upper'].copy();expected_ham=[];fix=[];fixvals=[]
    for j,name in enumerate(map(str,d['names'])):
        family=name.split('[',1)[0]
        if family not in ('route_flow','node_activity'):continue
        axis=name.split('[',1)[1][:-1].split(',');u=axis[0];closure=closures.get(u);free=False
        if closure:
            if family=='route_flow':free=int(axis[1]) in closure['inner_arcs']
            else:free=(axis[1],int(axis[2])) in nodes[u] and closure['start']<=int(axis[2])<=closure['stop']
        if free and d['lower'][j]<d['upper'][j]:
            if family=='node_activity':expected_ham.append(j)
        else:
            assert center[j] in (0.,1.);el[j]=eu[j]=center[j];fix.append(j);fixvals.append(float(center[j]))
    assert np.array_equal(el,low) and np.array_equal(eu,high)
    assert fix==spec['fixed_route_columns'] and fixvals==spec['fixed_route_values']
    ham=np.asarray(spec['hamming_columns'],dtype=int);assert expected_ham==ham.tolist() and len(ham)>0
    modes=np.flatnonzero(np.char.startswith(d['names'],'charge_mode['));assert len(modes)==384 and not set(ham)&set(modes)
    assert np.array_equal(low[modes],d['lower'][modes]) and np.array_equal(high[modes],d['upper'][modes])
    fixed=np.asarray(fix,dtype=int);assert np.array_equal(center[fixed],low[fixed])
    box_excess=max(0.,float(np.max(low-center)),float(np.max(center-high)))
    # Keep unchanged Source numerical policy, rather than clipping the known
    # approximately5e-13 primal upper-bound residual in the inherited raw.
    from tools.u4_primal_alns.pilot import PARAMS
    assert box_excess<=PARAMS['FeasibilityTol']
    coefficients=np.where(center[ham]==1.,-1.,1.);rhs=float(spec['hamming_radius'])-float(np.count_nonzero(center[ham]))
    assert float(coefficients@center[ham])<=rhs
    expression=inverse(case);closed_arcs=0;closed_nodes=0
    original_center=case.lift(center)
    for j,name in enumerate(map(str,case.original_d['names'])):
        family=name.split('[',1)[0]
        if family not in ('arc','node_activity'):continue
        axis=name.split('[',1)[1][:-1].split(',');u=axis[0]
        if family=='arc':closed=u not in allow or int(axis[1]) not in allow[u];expected=original_center[j] if u not in allow else 0.
        else:
            vertex=(axis[1],int(axis[2]));c=closures.get(u)
            closed=c is None or vertex not in nodes[u] or not c['start']<=vertex[1]<=c['stop'];expected=original_center[j]
        if not closed:continue
        constant,terms=expression(j);lower=upper=constant
        for col,value in terms.items():
            lower+=min(value*F(float(low[col])),value*F(float(high[col])))
            upper+=max(value*F(float(low[col])),value*F(float(high[col])))
        assert lower==upper==F(float(expected)),'FREE_ORIGINAL_ROUTE_ALIAS_LEAK:'+name
        closed_arcs+=family=='arc';closed_nodes+=family=='node_activity'
    witnesses=[]
    for paths in spec['witness_paths']:
        assert paths!=spec['center_paths'];moves=0
        for u,path in paths.items():
            site,t=case.graph[1][u],0
            for k in path:
                a=arcs[k];assert a[:2]==(site,t) and t<a[3]<=96
                if u in allow:assert k in allow[u]
                else:assert path==spec['center_paths'][u]
                if a[-1] is not None:a[-1].validate(96);moves+=1
                site,t=a[2:4]
            assert t==96
        assert moves>0
        ids,vals=values_for(case,paths,lambda u,t:False);route=~np.char.startswith(d['names'][ids],'charge_mode[');ids,vals=ids[route],vals[route]
        trial=center.copy();trial[ids]=vals
        assert np.all(trial[ids]>=low[ids]) and np.all(trial[ids]<=high[ids])
        distance=int(np.count_nonzero(trial[ham]!=center[ham]));assert distance<=spec['hamming_radius']
        lifted=case.lift(trial);selected={u:set(p) for u,p in paths.items()}
        vertices={u:{arcs[k][:2] for k in p}|{(arcs[p[-1]][2],96)} for u,p in paths.items()}
        for j,name in enumerate(map(str,case.original_d['names'])):
            family=name.split('[',1)[0]
            if family not in ('arc','node_activity'):continue
            axis=name.split('[',1)[1][:-1].split(',');u=axis[0]
            expected=float(int(axis[1]) in selected[u]) if family=='arc' else float((axis[1],int(axis[2])) in vertices[u])
            assert lifted[j]==expected and case.original_d['lower'][j]<=expected<=case.original_d['upper'][j]
        witnesses.append(dict(Hamming_distance=distance,moves=moves,original_DAG_ETA_alias_bounds_terminal_PASS=True,SOC_PQ_Grid_feasibility_claimed=False))
    assert signature(low,high,ham,coefficients,rhs)==spec['mathematical_model_signature']
    return dict(PASS=True,Native_optimize_calls=0,original_rows_domains_objective_preserved=True,binary_count=9322,
        original_FULL_contains_restricted_model=True,center_original_FULL_PASS=True,center_fixings_and_Hamming_exact=True,
        center_box_residual=box_excess,unchanged_Source_FeasibilityTol=PARAMS['FeasibilityTol'],Raw_not_repaired=True,
        original_closed_Arc_aliases=closed_arcs,original_closed_Node_aliases=closed_nodes,alias_leak_absent=True,
        witnesses=witnesses,all384_modes_free=True,Modes_in_Hamming=0,Hamming_radius=spec['hamming_radius'],
        actual_free_binary=spec['actual_free_binary'],actual_fixed_binary=spec['actual_fixed_binary'],
        no_new_return_to_origin_rule=True,restricted_ObjBound_is_Global_LB=False)
