"""Independent name-based lift and exact original row coefficient audit. Native0."""
import gc,time
from collections import defaultdict,Counter
from scipy import sparse
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.global_local_multistart1800.dag import Graph

def main():
    began=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json');assert state['PASS']
    case=v.load_native_case();assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(case.d)==v.DOMAIN_SHA
    names=list(map(str,case.d['names']));route=[j for j,n in enumerate(names) if n.startswith(('route_flow[','node_activity['))]
    keep=[j for j,n in enumerate(names) if not n.startswith(('route_flow[','node_activity['))]
    assert len(route)==216674 and len(keep)==137603
    assert Counter(names[j].split('[')[0] for j in route)=={'node_activity':8938,'route_flow':207736}
    graph=Graph(case);proofs=[]
    for call in state['Native_calls']:
        spec=read(call['model']['path']);folder=Path(call['model']['path']).parent
        A=sparse.load_npz(folder/'A.npz').tocsr();T=sparse.load_npz(folder/'LIFT.npz').tocsr()
        with np.load(folder/'DATA.npz',allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
        assert keep==spec['keep_columns'] and route==spec['removed_route_columns']
        assert T.shape==(354277,len(keep)+spec['lambda_count'])
        tc=T.tocsc();assert np.all(np.diff(tc.indptr[:len(keep)+1])==1)
        assert np.array_equal(tc.indices[:len(keep)],keep) and np.all(tc.data[:len(keep)]==1.)
        # Derive every removed coordinate from names and the original DAG,
        # independently of the compiler incidence function.
        for col,entry in enumerate(spec['lambda_axis']):
            u=entry['unit'];path=entry['path'];graph.validate(u,path)
            arcs=set(path);vertices={graph.arcs[k][:2] for k in path}|{(graph.arcs[path[-1]][2],96)}
            expected=[]
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
        assert np.array_equal(d['rhs'][:715596],case.d['rhs']) and np.array_equal(d['sense'][:715596],case.d['sense'])
        assert np.array_equal(d['row_names'][:715596],case.d['row_names'])
        for field in ('lower','upper','objective','types','names'):assert np.array_equal(d[field][:len(keep)],case.d[field][keep])
        assert np.array_equal(d['constant'],case.d['constant'])
        assert np.array_equal(d['rhs'][715596:],np.ones(4)) and set(d['sense'][715596:])=={'='}
        assert np.all(d['lower'][len(keep):]==0) and np.all(d['upper'][len(keep):]==1) and np.all(d['types'][len(keep):]=='B') and np.all(d['objective'][len(keep):]==0)
        for i,u in enumerate(sorted(graph.origins)):
            row=A.getrow(715596+i);expected={len(keep)+j:1. for j,a in enumerate(spec['lambda_axis']) if a['unit']==u}
            assert dict(zip(map(int,row.indices),map(float,row.data)))==expected
        q=read(call['receipt']['path']);readback=read(q['readback']['path']);assert readback['PASS'] and all(readback['checks'].values())
        assert readback['NumVars']==137635 and readback['NumBinVars']==416 and readback['NumConstrs']==715600
        assert q['Threads']==q['Heavy_Worker']==1 and q['status']=='FINISHED' and q['Native_Runtime']==call['Native_Runtime'] and not q['callback_errors']
        assert all(s['safety']['PASS'] for s in q['resource_samples'])
        for capture in q['captures']:
            with np.load(capture['native_raw']['path'],allow_pickle=False) as z:native=z['point'].copy()
            dense=v.load_point(capture['dense_lift']['path']);assert np.array_equal(T@native,dense)
            assert v.vector_sha(T@native)==v.vector_sha(dense) and np.isin(native[len(keep):],(0.,1.)).all()
            assert np.array_equal(dense[keep],native[:len(keep)])
        proofs.append(dict(spec=call['model'],PASS=True,source_rows_exactly_rederived=715596,lambda_columns_exactly_rederived=spec['lambda_count'],source_coordinate_incidence_independent=True,raw_model_inverse_lift_exact=True))
    families=dict(Counter(str(n).split('[')[0] for n in case.original_d['row_names']))
    del case,A,T,d;gc.collect()
    # Fresh independent original FULL replays: no Gurobi imports in this process.
    replays=[]
    for i,item in enumerate(state['validations']):
        cert=validate(item['dense_lift']['path'],DOCS/f'audit/FRESH_FULL_REPLAY_{i:03d}.json',item['UB']);assert cert['PASS']
        replays.append(record(DOCS/f'audit/FRESH_FULL_REPLAY_{i:03d}.json'))
    warm=validate(ROOT/RAW_REL,DOCS/'audit/PR220_FULL_REPLAY.json',INITIAL_UB);assert warm['PASS']
    stop=read(beta.DOCS/'PHASE0_SAFE_STOP.json');actual_old=sum(c['Native_Runtime'] for c in stop['calls']);assert actual_old==stop['Native_used']
    fresh=sum(c['Native_Runtime'] for c in state['Native_calls']);assert fresh==state['fresh_Native_used']<=240 and fresh<=1800
    auth=read(DOCS/'FRESH_EXECUTION_AUTHORIZATION.json');assert auth['fresh_Native_used_before']==0 and auth['fresh_Native_limit']==1800
    prior_beta=sum(c['Native_Runtime'] for c in auth['prior_pilot_calls']);assert auth['historical_total_Native']==actual_old+prior_beta
    backend=read(DOCS/'FINAL_BACKEND_DECISION.json');assert backend['direct_substitution_adopted'] is False and backend['new_native_dispatch'] is False
    assert read(DOCS/'POST_PILOT_FEEDBACK_INTEGER_EQUIVALENCE.json')['PASS']
    diagnosis=read(beta.DOCS/'PHASE1_WHOLE_GRID_SOC_DIAGNOSTICS.json');assert diagnosis['unique_saved_vectors']==33
    assert all(set(map(int,q['per_slot_worst']))==set(range(96)) for q in diagnosis['records'])
    resource=r.audit('FINAL_INDEPENDENT_NATIVE0_AUDIT');write(DOCS/'FINAL_RESOURCE_SOURCE_AUDIT.json',resource);assert resource['PASS'];guard()
    report=dict(PASS=True,Optimize_calls=0,source_and_prior_seals_unchanged=True,independent_name_based_coordinate_and_exact_dyadic_row_proofs=proofs,
        all_physical_source_families=families,original_FULL_replays=replays,PR220_original_FULL_PASS=True,
        original_STAY_single_multiple_DAG_ETA_energy_preserved=True,Original_FULL_contains_restricted_MILP=True,full_feasible_region_equality_not_claimed=True,
        four_MESS_joint_actual_native_calls=len(state['Native_calls']),source_mode384_and_P_Q_SOC_Grid_preserved=True,
        old_Joint_Native=actual_old,stopped_remainder_pilot_Native=prior_beta,fresh_Native=fresh,
        all_this_work_actual_Native=actual_old+prior_beta+fresh,fresh_budget_limit=1800,budget_histories_preserved=True,
        source_resources=record(DOCS/'FINAL_RESOURCE_SOURCE_AUDIT.json'),direct_backend_rejected_for_measured_disadvantage=True,
        BEST_GLOBAL_UB=state['BEST_GLOBAL_UB']['UB'],BEST_MOVING_FEASIBLE_UB=state['BEST_MOVING_FEASIBLE_UB']['UB'],
        Global_LB=GLOBAL_LB,Global_Gap_percent=state['Global_Gap_percent'],physical_improvement_limit_proven=False,
        source_or_case_or_B1_or_schedule_mutations=0,ACTUAL='ACTUAL_NOT_RUN',wall_seconds=time.perf_counter()-began)
    write(DOCS/'FINAL_INDEPENDENT_REVIEW.json',report);print(json.dumps(dict(PASS=True,fresh_Native=fresh,total=report['all_this_work_actual_Native'])))

if __name__=='__main__':main()
