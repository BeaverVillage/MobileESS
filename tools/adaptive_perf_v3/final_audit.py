"""Final independent source-row, literal selection, FULL, ledger and resource audit."""
from scipy import sparse
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_compact_joint.continuation_audit import alias_operator,independent_links,direct_check
from tools.global_local_multistart1800.joint import pool_signature
from tools.global_local_multistart1800.dag import Graph
from tools.adaptive_perf_v3.cache import verify,identity

def main():
    configure();full_guard();state=read(DOCS/'FINAL_STATE.json');assert state['PASS'];timer=Timing()
    for path,digest in read(DOCS/'FROZEN_PREVIOUS_FILES.json').items():assert v.file_sha(path)==digest
    case=v.load_native_case();names=list(map(str,case.d['names']));route=[j for j,n in enumerate(names) if n.startswith(('route_flow[','node_activity['))]
    keep=[j for j,n in enumerate(names) if not n.startswith(('route_flow[','node_activity['))];operator=alias_operator(case,route);graph=Graph(case)
    records=[];seen=set();vectors={};union={u:set() for u in graph.origins}
    for i,call in enumerate(state['calls']):
        for field in ('model','receipt'):assert v.file_sha(call[field]['path'])==call[field]['sha256']
        spec=read(call['model']['path']);folder=Path(call['model']['path']).parent;form=call.get('formulation','DIRECT');sig=form+'|'+spec['pool_signature'];assert sig not in seen;seen.add(sig)
        assert spec['pool_signature']==pool_signature(spec['pools']);center=v.load_point(spec['center_raw']['path'])
        links,signature=independent_links(case,spec,route,operator)
        for u,paths in spec['pools'].items():
            depths=[len(graph.move_indices(p)) for p in paths];assert len(paths)==8 and 0 in depths and 1 in depths and max(depths)>=2
            for path in paths:graph.validate(u,path);union[u].add(tuple(path))
        if form=='DIRECT':T=direct_check(case,spec,folder,keep,route)
        elif form=='EF':
            A=sparse.load_npz(folder/'A.npz').tocsr();assert v.matrix_sha(A[:715596,:354277].tocsr())==v.MATRIX_SHA and A[:715596,354277:].nnz==0
            assert v.matrix_sha(A[715596:].tocsr())==v.matrix_sha(links)
            with np.load(folder/'DATA.npz',allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
            for field in ('rhs','sense','row_names'):assert np.array_equal(d[field][:715596],case.d[field])
            for field in ('lower','upper','types','objective','names'):assert np.array_equal(d[field][keep],case.d[field][keep])
            assert np.count_nonzero(d['types']=='B')==416
            T=sparse.load_npz(folder/'LIFT.npz').tocsr();assert (T[:,:354277]!=sparse.eye(354277,format='csr')).nnz==0 and T[:,354277:].nnz==0
            del A,d
        else:assert form=='JOINT' and signature==spec['mathematical_model_signature'];T=None
        q=read(call['receipt']['path']);rb=read(q['readback']['path']);assert rb['PASS'] and all(rb['checks'].values())
        assert q['Threads']==q['Heavy_Worker']==q['Optimize_calls']==1 and q['model_disposed'] and q['status']=='FINISHED' and not q['callback_errors']
        assert q['Global_LB_admissible'] is False and q['Native_Runtime']==call['Native_Runtime']
        assert rb['NumBinVars']==(9354 if form=='JOINT' else 416)
        assert rb['NumVars']==(137635 if form=='DIRECT' else 354309)
        assert all(sample['safety']['PASS'] for sample in q['resource_samples'])
        if form=='JOINT':
            full=sparse.vstack([sparse.hstack([case.A,sparse.csr_matrix((715596,32))],format='csr'),links],format='csr')
            assert v.matrix_sha(full)==rb['new_joint_matrix_SHA'];del full
        for capture in q['captures']:
            dense=v.load_point(capture['dense_lift']['path']);selection=np.asarray(capture['lambda_values']);assert np.isin(selection,(0.,1.)).all() and capture['strict_literal_lambda']
            if T is not None:
                with np.load(capture['native_raw']['path'],allow_pickle=False) as z:native=z['point'].copy()
                assert np.array_equal(T@native,dense)
            chosen=paths_of(case,dense)
            for u in chosen:assert [a['path'] for a,value in zip(spec['lambda_axis'],selection) if a['unit']==u and value==1.]==[chosen[u]]
            vectors[v.vector_sha(dense)]=(capture['dense_lift']['path'],capture['Solver_ObjVal'])
        records.append(dict(PASS=True,call=call,source_rows_exactly_checked=715596,four_route_Node_Flow_Arc_Alias_ETA_energy=True,raw_inverse_lift_exact=True))
        del T,links,center;gc.collect();print(json.dumps(dict(audit_model=i+1,total=len(state['calls']),PASS=True)),flush=True)
    del case,operator;gc.collect();replays=[]
    for i,(raw,obj) in enumerate(vectors.values()):
        path=DOCS/f'audit/INDEPENDENT_FULL_{i:03d}.json';assert validate(raw,path,obj)['PASS'];replays.append(record(path))
    best=state['BEST_GLOBAL_UB'];best_replay=DOCS/'audit/BEST_ORIGINAL_FULL.json';assert validate(best['point']['path'],best_replay,best['UB'])['PASS']
    warm=DOCS/'audit/PR220_ORIGINAL_FULL.json';assert validate(ROOT/RAW_REL,warm,INITIAL_UB)['PASS']
    fresh=sum(c['Native_Runtime'] for c in state['calls']);assert fresh==state['Native_used']<=1800 and all(a['PASS'] for a in state['validations'])
    migration=read(DOCS/'MIGRATION_STATE.json');assert state['calls'][:len(migration['calls'])]==migration['calls']
    assert state['calls'][len(migration['calls']):]==state['new_calls'] and state['Global_LB']==GLOBAL_LB
    assert not read(DOCS/'NATIVE_RUNTIME_LEDGER.json')['budget_reset'] and read(DOCS/'HANDOFF_PASS.json')['actual_worker_count_at_handoff']==0
    resource=r.audit('V3_FINAL_INDEPENDENT_NATIVE0');write(DOCS/'FINAL_RESOURCE_SOURCE_AUDIT.json',resource);assert resource['PASS'];full_guard()
    report=dict(PASS=True,Optimize_calls=0,models=records,Original_FULL_independent_replays=replays,best_FULL=record(best_replay),PR220_FULL=record(warm),
        original_Row_Grid_PCS16_SOC_Mode384_DAG_physics_preserved=True,restricted_subset_of_Original_FULL=True,
        Native_used=fresh,Native_limit=1800,pilot_Native=63.64199995994568,v2_Native=migration['Native_used']-63.64199995994568,
        v3_Native=fresh-migration['Native_used'],budget_reset=False,prior_sources_Raw_and_ledger_SHA_preserved=True,
        unique_formulation_pool_signatures=len(seen),evaluated_unique_paths={u:len(p) for u,p in union.items()},
        BEST_GLOBAL_UB=best['UB'],BEST_MOVING_FEASIBLE_UB=state['BEST_MOVING_FEASIBLE_UB']['UB'],Global_LB=GLOBAL_LB,Global_Gap_percent=state['Global_Gap_percent'],
        restricted_ObjBound_never_Global_LB=True,physical_improvement_limit_proven=False,source_Case_B1_mutations=0,ACTUAL='ACTUAL_NOT_RUN',wall_seconds=timer.receipt()['total_wall'])
    write(DOCS/'FINAL_INDEPENDENT_REVIEW.json',report);print(json.dumps(dict(PASS=True,Native=fresh,models=len(records),unique_raws=len(replays))),flush=True)
if __name__=='__main__':main()
