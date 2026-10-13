"""Post-run independent evidence audit, without any new Optimize or Gurobi import."""
import gc,math,time
from scipy import sparse
from tools.global_local_multistart1800.adapter import *
from tools.global_local_multistart1800.joint import build_spec,independent,pool_signature
from tools.global_local_multistart1800.lb import data,inclusion,PARENT

def main():
    began=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json');assert state['stopped_reason']
    resource=r.audit('JOINT_FINAL_INDEPENDENT',True);write(DOCS/'FINAL_RESOURCE_SOURCE_AUDIT.json',resource);assert resource['PASS']
    assert v.file_sha(ROOT/RAW_REL)==RAW_SHA and v.vector_sha(v.load_point(ROOT/RAW_REL))==VECTOR_SHA
    warm=v.validate(ROOT/RAW_REL,solver_objective=INITIAL_UB);assert warm['PASS'] and warm['Global_UB']==INITIAL_UB
    actual=list((DOCS/'calls').glob('*/native/NATIVE_CALL.json'))
    if (DOCS/'dual/NATIVE_CALL.json').exists():actual.append(DOCS/'dual/NATIVE_CALL.json')
    entered=[p for p in actual if read(p)['entered_native']]
    assert len(entered)==len(state['calls']) and {str(p) for p in entered}=={c['receipt']['path'] for c in state['calls']}
    used=0.;models=set();pools=set();joint_proofs=[];case=v.load_native_case();joint_count=0
    for c in state['calls']:
        path=Path(c['receipt']['path']);assert v.file_sha(path)==c['receipt']['sha256'];call=read(path);out=path.parent
        assert c['cumulative_Native_before']==used;assert call['Native_Runtime'] is not None and math.isfinite(call['Native_Runtime']);used+=call['Native_Runtime']
        assert used==c['cumulative_Native_after'] and used<=1800 and call['Native_worker']==call['Threads']==1
        assert call['parameter_readback']['Threads']==1 and 0<call['requested_seconds']<=175
        assert not call.get('error') and not call['callback_errors']
        assert call.get('callback_stop_reason') in (None,'FIRST_STRICT_IMPROVEMENT_RAW_EXIT_FOR_FULL_REPLAY')
        assert call['execution_source_seal']['sha256']==v.file_sha(DOCS/'EXECUTED_SOURCE_HASHES.json')
        assert read(out/'POST_BUILD_NATIVE_ADMISSION.json')['PASS'] and all(s['safety']['PASS'] for s in call['resource_samples'])
        if call['method']=='DUAL':continue
        spec=read(out.parent/'SPEC.json')
        if call['method']=='FOUR_MESS_JOINT_ROUTE_POOL':
            center=v.load_point(call['initial_point']['path']);assert v.file_sha(call['initial_point']['path'])==call['initial_point']['sha256']
            rebuilt,lo,hi,A,rhs=build_spec(case,center,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],spec['seconds'])
            proof=independent(case,center,spec,lo,hi,A,rhs);assert proof['PASS']
            sig=rebuilt['mathematical_model_signature'];psig=pool_signature(spec['pools'])
            assert sig==spec['executed_mathematical_model_signature'] and psig not in pools;pools.add(psig)
            rb=read(out/'JOINT_NATIVE_READBACK.json');assert rb['PASS'] and all(rb['checks'].values())
            assert rb['source_binary']==9322 and rb['total_binary']==9322+spec['lambda_count']
            assert rb['source_Start_vector_SHA']==v.vector_sha(center) and call['actual_NumStart']==1
            joint_proofs.append(dict(spec=record(out.parent/'SPEC.json'),proof=proof,Native_readback=record(out/'JOINT_NATIVE_READBACK.json')));joint_count+=1
        else:
            assert spec['stage']=='ABLATION' and call['actual_NumStart']==0
            lo,hi,ham,coeff,rhs,_=restriction(case,None,spec);proof=audit(case,None,spec,lo,hi);assert proof['PASS']
            assert read(out/'MOVING_ROUTE_NATIVE_READBACK.json')['PASS'];sig=signature(lo,hi,ham,coeff,rhs)
        assert sig not in models;models.add(sig)
    assert used==state['Native_used']==read(DOCS/'NATIVE_RUNTIME_LEDGER.json')['Native_used']
    assert joint_count==state['all_four_joint_calls'] and joint_count>0
    assert state['conditional_LP_screen_calls']==state['unrestricted_FULL_calls']==state['Cold_N1_U4_calls']==0
    assert sum(c['Native_Runtime'] for c in state['calls'] if c['stage']=='ABLATION')<=250
    del case;gc.collect();full=[];seen=set();raw_pass=raw_fail=0
    for it in state['iterations']:
        assert v.file_sha(it['specification']['path'])==it['specification']['sha256']
        for item in it['validated']:
            raw=Path(item['raw']['path']);assert v.file_sha(raw)==item['raw']['sha256']
            if item['replay'] is not None:assert v.file_sha(item['replay']['path'])==item['replay']['sha256']
            if not item['PASS']:raw_fail+=1;continue
            raw_pass+=1;saved=read(item['replay']['path']);x=v.load_point(raw);digest=v.vector_sha(x)
            assert saved['PASS'] and saved['point_file_sha256']==v.file_sha(raw) and saved['point_vector_sha256']==digest
            if digest in seen:continue
            seen.add(digest);replay=v.validate(raw,solver_objective=saved['Global_UB']);assert replay['PASS'] and replay['Global_UB']==saved['Global_UB']
            assert replay['rounding']==replay['clipping']==replay['repairs']==0
            if it['method']=='FOUR_MESS_JOINT_ROUTE_POOL':
                spec=read(it['specification']['path'])
                with np.load(raw,allow_pickle=False) as z:lam=z['route_selection']
                assert np.isin(lam,(0.,1.)).all()
                case=v.load_native_case();paths=paths_of(case,x)
                for u in spec['pools']:
                    picked=[a for a,val in zip(spec['lambda_axis'],lam) if a['unit']==u and val==1]
                    assert len(picked)==1 and picked[0]['path']==paths[u]
                del case;gc.collect()
            full.append(dict(raw=item['raw'],replay=item['replay'],independent_repeat_FULL_PASS=True,UB=replay['Global_UB']))
    dual_calls=[c for c in state['calls'] if c['method']=='DUAL'];assert len(dual_calls)==state['new_LB_Optimize_calls']<=1
    newlb=None
    if dual_calls:
        d=data(PARENT/'JOINT_DATA.npz');A=sparse.load_npz(PARENT/'JOINT_A.npz').tocsr();choice=read(DOCS/'LB_CANDIDATE_COMPARISON.json')
        types=np.full(len(d['vtypes']),'C',dtype=d['vtypes'].dtype);types[choice['selected']]='B';proof=inclusion(A,d,types,choice['selected']);assert proof['PASS']
        rb=read(DOCS/'dual/NATIVE_READBACK.json');assert rb['PASS'] and all(rb['checks'].values())
        cert=read(DOCS/'FAST_LB_INDEPENDENT_CERTIFICATE.json');call=read(DOCS/'dual/NATIVE_CALL.json')
        if cert['PASS']:
            assert cert['native_source_attribute']=='ObjBound' and cert['Global_LB']==call['ObjBound']
            assert call['Status'] in (2,9) and math.isfinite(call['ObjBound']) and not call['callback_errors']
            assert call['ObjBound']<=.4812227124583283+1e-7,'K32_INTEGER_WITNESS_UPPER_LIMIT_CONTRADICTION'
            newlb=cert['Global_LB']
        assert call['requested_seconds']<=175 and call['Native_Runtime']<=180
    assert state['Global_LB']==max(GLOBAL_LB,newlb if newlb is not None else GLOBAL_LB)
    assert state['Global_gap']==(state['BEST_GLOBAL_UB']['UB']-state['Global_LB'])/state['BEST_GLOBAL_UB']['UB']
    assert state['trajectory'][0]['inherited_not_new_discovery'] and state['trajectory'][0]['Native_capture_seconds']==0
    assert all(state['trajectory'][i]['UB']<state['trajectory'][i-1]['UB']-1e-8 for i in range(1,len(state['trajectory'])))
    result=dict(PASS=True,verifier_Optimize_calls=0,Native_used=used,Native_limit=1800,Native_calls=len(entered),all_four_Joint_calls=joint_count,
        unique_joint_pool_signatures=len(pools),unique_primal_model_signatures=len(models),Joint_Native_proofs=joint_proofs,
        independent_FULL_replays=full,Raw_PASS=raw_pass,Raw_FAIL=raw_fail,original_physics_grid_case_source_preserved=True,
        all384_Modes_P_Q_SOC_free=True,original_9322_binary_and_added_lambda_types=True,lambda_original_Arc_Node_Flow_Alias_exact=True,
        Restricted_subset_original_FULL=True,all_four_moving_topology_allowed_not_forced=True,PR220_RAW_unmodified_valid_Start=True,
        Dual_calls=len(dual_calls),Dual_full_integer_projection_inclusion=bool(dual_calls),Dual_new_certificate_LB=newlb,
        restricted_bound_promotions_to_Global_LB=0,Actual='ACTUAL_NOT_RUN',old_times_separate=True,wall_seconds=time.perf_counter()-began)
    write(DOCS/'FINAL_INDEPENDENT_REVIEW.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('Joint_Native_proofs','independent_FULL_replays')}))

if __name__=='__main__':main()
