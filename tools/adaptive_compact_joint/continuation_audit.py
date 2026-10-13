"""Post-run independent original-coordinate, runtime, and FULL audit; Native0."""
import gc,time
from collections import Counter,defaultdict
from scipy import sparse
from tools.adaptive_compact_joint.resume_adapter import *
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import pool_signature,path_signature
from tools.global_local_multistart1800.proof import inverse

def alias_operator(case,route):
    expand=inverse(case);position={j:i for i,j in enumerate(route)};position_set=set(position);rows=[];cols=[];coeff=[];constant=[];axes=[]
    for j,name in enumerate(map(str,case.original_d['names'])):
        family=name.split('[',1)[0]
        if family not in ('arc','node_activity'):continue
        fields=name.split('[',1)[1][:-1].split(',');offset,terms=expand(j)
        assert offset.denominator==1 and set(terms)<=position_set
        assert all(value.denominator==1 for value in terms.values())
        row=len(axes);axes.append((j,family,fields));constant.append(int(offset))
        for col,value in terms.items():rows.append(row);cols.append(position[col]);coeff.append(int(value))
        assert abs(int(offset))+sum(abs(int(value)) for value in terms.values())<2**62
    M=sparse.csr_matrix((np.asarray(coeff,dtype=np.int64),(rows,cols)),shape=(len(axes),len(route)))
    return M,np.asarray(constant,dtype=np.int64),axes

def independent_links(case,spec,route,operator):
    graph=Graph(case);names=list(map(str,case.d['names']));M,constant,axes=operator;L=spec['lambda_count']
    values=np.zeros((len(route),L),dtype=np.int64);routeunits=[]
    for j in route:routeunits.append(names[j].split('[',1)[1].split(',')[0])
    for col,entry in enumerate(spec['lambda_axis']):
        u=entry['unit'];path=entry['path'];arcs=set(path);vertices={graph.arcs[k][:2] for k in path}|{(graph.arcs[path[-1]][2],96)}
        graph.validate(u,path)
        for k,j in enumerate(route):
            if routeunits[k]!=u:continue
            family,fields=names[j].split('[',1);axis=fields[:-1].split(',')
            values[k,col]=int(int(axis[1]) in arcs) if family=='route_flow' else int((axis[1],int(axis[2])) in vertices)
        selected=[i for i,(j,family,fields) in enumerate(axes) if fields[0]==u]
        actual=np.asarray(M[selected]@values[:,col]).ravel()+constant[selected]
        expected=np.asarray([int(int(axes[i][2][1]) in arcs) if axes[i][1]=='arc' else int((axes[i][2][1],int(axes[i][2][2])) in vertices) for i in selected])
        assert np.array_equal(actual,expected)
        original=np.asarray([axes[i][0] for i in selected]);assert np.all(expected>=case.original_d['lower'][original]) and np.all(expected<=case.original_d['upper'][original])
    lower=case.d['lower'].copy();upper=case.d['upper'].copy();rr=[];cc=[];vv=[];vary=[]
    for row,u in enumerate(sorted(spec['pools'])):
        for col,a in enumerate(spec['lambda_axis']):
            if a['unit']==u:rr.append(row);cc.append(354277+col);vv.append(1.)
    for k,j in enumerate(route):
        columns=[col for col,a in enumerate(spec['lambda_axis']) if a['unit']==routeunits[k]];vrow=values[k,columns]
        lower[j]=vrow.min();upper[j]=vrow.max()
        if lower[j]==upper[j]:continue
        row=4+len(vary);vary.append(j);rr.append(row);cc.append(j);vv.append(1.)
        for col in columns:
            if values[k,col]:rr.append(row);cc.append(354277+col);vv.append(-1.)
    A=sparse.csr_matrix((vv,(rr,cc)),shape=(4+len(vary),354277+L));rhs=np.r_[np.ones(4),np.zeros(len(vary))]
    # Builder's row order follows grouped unit coordinates; derive that order explicitly.
    unit_for={j:u for j,u in zip(route,routeunits)}
    expected_order=sorted(vary,key=lambda j:(unit_for[j],j));positions={j:i for i,j in enumerate(vary)}
    A=A[[0,1,2,3]+[4+positions[j] for j in expected_order]]
    assert expected_order==spec['varying_route_columns']
    signature=hashlib.sha256()
    for value in (lower,upper):signature.update(value.tobytes())
    signature.update(v.matrix_sha(A).encode());signature.update(rhs.tobytes())
    center=v.load_point(spec['center_raw']['path']);assert v.vector_sha(center)==spec['center_vector_SHA']
    assert np.array_equal(A@np.r_[center,spec['lambda_Start']],rhs)
    return A,signature.hexdigest()

def direct_check(case,spec,folder,keep,route):
    A=sparse.load_npz(folder/'A.npz').tocsr();T=sparse.load_npz(folder/'LIFT.npz').tocsr()
    with np.load(folder/'DATA.npz',allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    names=list(map(str,case.d['names']));graph=Graph(case)
    assert keep==spec['keep_columns'] and route==spec['removed_route_columns']
    assert T.shape==(354277,len(keep)+spec['lambda_count'])
    tc=T.tocsc();assert np.all(np.diff(tc.indptr[:len(keep)+1])==1)
    assert np.array_equal(tc.indices[:len(keep)],keep) and np.all(tc.data[:len(keep)]==1.)
    for col,entry in enumerate(spec['lambda_axis']):
        u=entry['unit'];path=entry['path'];graph.validate(u,path)
        arcs=set(path);vertices={graph.arcs[k][:2] for k in path}|{(graph.arcs[path[-1]][2],96)};expected=[]
        for j in route:
            family,fields=names[j].split('[',1);axis=fields[:-1].split(',')
            if axis[0]!=u:continue
            value=float(int(axis[1]) in arcs) if family=='route_flow' else float((axis[1],int(axis[2])) in vertices)
            assert case.d['lower'][j]<=value<=case.d['upper'][j]
            if value:expected.append(j)
        actual=T.getcol(len(keep)+col).tocoo()
        assert np.array_equal(np.sort(actual.row),expected) and np.all(actual.data==1)
        selected=case.A[:,expected].tocoo();sums=defaultdict(F)
        for row,co in zip(selected.row,selected.data):sums[int(row)]+=F(float(co))
        got=A[:715596,len(keep)+col].tocoo();observed=dict(zip(map(int,got.row),map(lambda co:F(float(co)),got.data)))
        assert {r:co for r,co in sums.items() if co}==observed
    assert (A[:715596,:len(keep)]!=case.A[:,keep]).nnz==0
    for field in ('rhs','sense','row_names'):assert np.array_equal(d[field][:715596],case.d[field])
    for field in ('lower','upper','objective','types','names'):assert np.array_equal(d[field][:len(keep)],case.d[field][keep])
    assert np.array_equal(d['constant'],case.d['constant'])
    assert np.array_equal(d['rhs'][715596:],np.ones(4)) and set(d['sense'][715596:])=={'='}
    assert np.all(d['lower'][len(keep):]==0) and np.all(d['upper'][len(keep):]==1) and np.all(d['types'][len(keep):]=='B') and np.all(d['objective'][len(keep):]==0)
    for i,u in enumerate(sorted(graph.origins)):
        row=A.getrow(715596+i);expected={len(keep)+j:1. for j,a in enumerate(spec['lambda_axis']) if a['unit']==u}
        assert dict(zip(map(int,row.indices),map(float,row.data)))==expected
    del A,tc,d;gc.collect();return T

def main():
    began=time.perf_counter();configure();guard();state=read(DOCS/'FINAL_STATE.json');assert state['PASS']
    assert state['stopped_reason'] in ('NATIVE_BUDGET_WITH_RETURN_RESERVE','VALID_ADAPTIVE_CANDIDATE_SIGNATURES_EXHAUSTED','CONFIGURED_POOL_EPOCH_SAFETY_LIMIT','USER_CANCEL')
    assert len(state['comparisons'])>=3
    case=v.load_native_case();assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(case.d)==v.DOMAIN_SHA
    names=list(map(str,case.d['names']));route=[j for j,n in enumerate(names) if n.startswith(('route_flow[','node_activity['))]
    keep=[j for j,n in enumerate(names) if not n.startswith(('route_flow[','node_activity['))]
    assert len(route)==216674 and len(keep)==137603
    graph=Graph(case);operator=alias_operator(case,route);proofs=[];seen=set();replay_inputs={};path_union={u:set() for u in graph.origins}
    for index,call in enumerate(state['calls']):
        for key in ('receipt','model'):assert v.file_sha(call[key]['path'])==call[key]['sha256']
        spec=read(call['model']['path']);folder=Path(call['model']['path']).parent
        form=call.get('formulation','DIRECT');signature=form+'|'+spec['pool_signature'];assert signature not in seen;seen.add(signature)
        assert spec['pool_signature']==pool_signature(spec['pools'])
        for u,paths in spec['pools'].items():
            counts=[len(graph.move_indices(p)) for p in paths]
            assert len(paths)==8 and 0 in counts and 1 in counts and max(counts)>=2
            for p in paths:graph.validate(u,p);path_union[u].add(path_signature(p))
        center=v.load_point(spec['center_raw']['path'])
        links,signature=independent_links(case,spec,route,operator)
        if form=='JOINT':assert signature==spec['mathematical_model_signature']
        T=direct_check(case,spec,folder,keep,route) if form=='DIRECT' else None
        q=read(call['receipt']['path']);rb=read(q['readback']['path'])
        assert rb['PASS'] and all(rb['checks'].values())
        assert rb['NumBinVars']==(416 if form=='DIRECT' else 9354)
        assert rb['NumVars']==(137635 if form=='DIRECT' else 354309)
        if form=='JOINT':
            combined=sparse.vstack([sparse.hstack([case.A,sparse.csr_matrix((715596,spec['lambda_count']))],format='csr'),links],format='csr')
            assert v.matrix_sha(combined)==rb['new_joint_matrix_SHA'];del combined
        assert q['Threads']==q['Heavy_Worker']==q['Optimize_calls']==1 and q['status']=='FINISHED'
        assert q['Native_Runtime']==call['Native_Runtime'] and not q['callback_errors'] and q['model_disposed']
        assert all(s['safety']['PASS'] for s in q['resource_samples'])
        assert call['Native_before']+q['Native_Runtime']==call['Native_after']
        for capture in q['captures']:
            dense=v.load_point(capture['dense_lift']['path']);lam=np.asarray(capture['lambda_values'])
            assert np.isin(lam,(0.,1.)).all() and capture['strict_literal_lambda']
            if T is not None:
                with np.load(capture['native_raw']['path'],allow_pickle=False) as z:native=z['point'].copy()
                assert np.array_equal(T@native,dense) and np.array_equal(native[len(keep):],lam)
                assert np.array_equal(dense[keep],native[:len(keep)])
            else:assert capture['native_raw']==capture['dense_lift']
            chosen_paths=paths_of(case,dense)
            for u in spec['pools']:
                chosen=[a['path'] for a,value in zip(spec['lambda_axis'],lam) if a['unit']==u and value==1.]
                assert chosen==[chosen_paths[u]]
            replay_inputs[v.vector_sha(dense)]=(capture['dense_lift']['path'],capture['Solver_ObjVal'])
        proofs.append(dict(PASS=True,formulation=form,spec=call['model'],native_readback=q['readback'],source_rows_exact=715596,
            four_MESS_route_simplex_Node_Flow_Arc_Alias_DAG_ETA_energy_exact=True,source_mode384_P_Q_SOC_PCS16_Grid_preserved=True,
            Direct_exact_dyadic_coefficients_rederived=T is not None,raw_inverse_mapping_exact=True))
        del center,T,links;gc.collect();print(json.dumps(dict(audit_model=index+1,total=len(state['calls']),PASS=True)),flush=True)
    families=dict(Counter(str(n).split('[')[0] for n in case.original_d['row_names']));del case;gc.collect()
    replays=[]
    for i,(raw,obj) in enumerate(replay_inputs.values()):
        path=DOCS/f'audit/INDEPENDENT_FULL_{i:03d}.json';assert validate(raw,path,obj)['PASS'];replays.append(record(path))
    best=state['BEST_GLOBAL_UB'];best_path=DOCS/'audit/BEST_ORIGINAL_FULL.json';assert validate(best['point']['path'],best_path,best['UB'])['PASS']
    warm_path=DOCS/'audit/PR220_ORIGINAL_FULL.json';assert validate(ROOT/RAW_REL,warm_path,INITIAL_UB)['PASS']
    pilot=read(PILOT_DOCS/'FINAL_STATE.json');prior=sum(c['Native_Runtime'] for c in pilot['Native_calls']);fresh=sum(c['Native_Runtime'] for c in state['calls'])
    assert prior==state['prior_Native']==63.64199995994568 and fresh==state['Native_used']<=1800
    assert state['calls'][:2]==pilot['Native_calls'] and state['calls'][2:]==state['new_calls']
    assert state['Global_LB']==GLOBAL_LB==.46498486997548166
    assert all(item['Global_LB_admissible'] is False for item in (read(c['receipt']['path']) for c in state['calls']))
    auth=read(PILOT_DOCS/'FRESH_EXECUTION_AUTHORIZATION.json');historical=auth['historical_total_Native']
    assert not read(DOCS/'NATIVE_RUNTIME_LEDGER.json')['budget_reset']
    resource=r.audit('CONTINUATION_FINAL_INDEPENDENT_NATIVE0');write(DOCS/'FINAL_RESOURCE_SOURCE_AUDIT.json',resource);assert resource['PASS'];guard()
    report=dict(PASS=True,Optimize_calls=0,models=proofs,source_physical_families=families,independent_original_FULL_replays=replays,
        best_original_FULL=record(best_path),PR220_original_FULL=record(warm_path),four_MESS_joint_calls=len(state['calls']),
        prior_pilot_Native=prior,continuation_Native=fresh-prior,fresh_Native=fresh,fresh_limit=1800,budget_reset=False,
        historical_Native=historical,all_this_work_Native=historical+fresh,unique_formulation_pool_signatures=len(seen),
        evaluated_unique_paths={u:len(s) for u,s in path_union.items()},all_validations_PASS=all(a['PASS'] for a in state['validations']),
        source_and_prior_pilot_SHA_preserved=True,restricted_MILP_subset_of_original_FULL=True,restricted_ObjBound_not_Global_LB=True,
        Global_LB=GLOBAL_LB,Global_Gap_percent=state['Global_Gap_percent'],BEST_GLOBAL_UB=best['UB'],BEST_MOVING_FEASIBLE_UB=state['BEST_MOVING_FEASIBLE_UB']['UB'],
        physical_improvement_limit_proven=False,source_or_case_or_B1_mutations=0,ACTUAL='ACTUAL_NOT_RUN',wall_seconds=time.perf_counter()-began)
    assert report['all_validations_PASS'];write(DOCS/'FINAL_INDEPENDENT_REVIEW.json',report)
    print(json.dumps(dict(PASS=True,fresh_Native=fresh,unique_vectors=len(replays),models=len(proofs))))

if __name__=='__main__':main()
