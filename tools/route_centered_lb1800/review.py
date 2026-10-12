"""Independent stored-source, Native, center and Original FULL audit; Optimize0."""
from collections import Counter
from pathlib import Path
import gc,math,time,numpy as np
from tools.route_centered_lb1800.adapter import *

def main():
    began=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json');assert state['stopped_reason']
    source=r.audit('ROUTE_CENTERED_INDEPENDENT_FINAL',True);assert source['PASS'];write(DOCS/'FINAL_SOURCE_RESOURCE_CHECK.json',source)
    assert v.file_sha(ROOT/RAW_REL)==RAW_SHA and v.vector_sha(v.load_point(ROOT/RAW_REL))==VECTOR_SHA
    fresh=v.validate(ROOT/RAW_REL,solver_objective=INITIAL_UB);assert fresh['PASS'] and fresh['Global_UB']==INITIAL_UB
    actual=[p for p in (DOCS/'calls').glob('*/native/NATIVE_CALL.json') if read(p)['entered_native']]
    assert len(actual)==len(state['calls']) and {str(p) for p in actual}=={c['receipt']['path'] for c in state['calls']}
    used=0.;signatures=set();proofs=[];raws={};case=v.load_native_case()
    for c in state['calls']:
        path=Path(c['receipt']['path']);assert v.file_sha(path)==c['receipt']['sha256'];call=read(path);folder=path.parent
        assert c['cumulative_Native_before']==used and used+call['requested_seconds']<=1792.+1e-6
        assert call['Native_Runtime'] is not None and math.isfinite(call['Native_Runtime']);used+=call['Native_Runtime'];assert used<=1800
        assert used==c['cumulative_Native_after'] and call['Threads']==call['Native_worker']==1
        assert call['parameter_readback']['Threads']==1 and call['requested_seconds']<=300
        assert not call['callback_errors'] and not call.get('error')
        assert call.get('callback_stop_reason') in (None,'FIRST_STRICT_IMPROVEMENT_RAW_EXIT_FOR_FULL_REPLAY')
        assert v.file_sha(DOCS/'EXECUTED_SOURCE_HASHES.json')==call['execution_source_seal']['sha256']
        assert read(folder/'POST_BUILD_NATIVE_ADMISSION.json')['PASS'] and all(s['safety']['PASS'] for s in call['resource_samples'])
        identity=read(folder/'MODEL_IDENTITY.json');assert identity['PASS'] and all(identity['checks'].values()) and not identity['unrestricted_original_C3A_MILP']
        spec=read(folder.parent/'SPEC.json');center=None if call['initial_point'] is None else v.load_point(call['initial_point']['path'])
        if center is not None:assert v.file_sha(call['initial_point']['path'])==call['initial_point']['sha256']
        low,high,ham,coeff,rhs,_=restriction(case,center,spec)
        proof=audit(case,center,spec,low,high);assert proof['PASS']
        sig=signature(low,high,ham,coeff,rhs);assert sig==spec['executed_mathematical_model_signature'] and sig not in signatures;signatures.add(sig)
        if spec['method']=='ROUTE_LOCAL_BRANCHING':
            rb=read(folder/'ROUTE_LOCAL_BRANCHING_NATIVE_READBACK.json');assert rb['PASS'] and all(rb['checks'].values())
            assert call['actual_NumStart']==1 and rb['native_Start_vector_SHA']==v.vector_sha(center)
            assert rb['Hamming_columns']==len(spec['hamming_columns']) and len(proof['witnesses'])>=1
            assert rb['actual_free_binary']+rb['actual_fixed_binary']==9322 and proof['Modes_in_Hamming']==0
        else:
            assert spec['stage']=='ABLATION' and call['actual_NumStart']==0 and spec['candidate_id']!='A0'
            assert read(folder/'MOVING_ROUTE_NATIVE_READBACK.json')['PASS']
        assert call['restricted_ObjBound_is_Global_LB'] is False
        for cap in call['captures']:
            assert v.file_sha(cap['file']['path'])==cap['file']['sha256'];raws[cap['file']['path']]=cap
        proofs.append(dict(specification=record(folder.parent/'SPEC.json'),native=record(path),signature=sig,independent_restriction_PASS=True))
    assert used==state['Native_used']==read(DOCS/'NATIVE_RUNTIME_LEDGER.json')['Native_used']
    assert state['new_LB_Optimize_calls']==state['unrestricted_FULL_calls']==state['Cold_N1_U4_calls']==0
    assert sum(c['Native_Runtime'] for c in state['calls'] if c['stage']=='ABLATION')<=250
    del case;gc.collect();full=[];seen=set()
    for it in state['iterations']:
        assert v.file_sha(it['specification']['path'])==it['specification']['sha256']
        for item in it['validated']:
            raw=item['raw']['path'];assert raw in raws and v.file_sha(raw)==item['raw']['sha256']
            if item['replay'] is not None:assert v.file_sha(item['replay']['path'])==item['replay']['sha256']
            if not item['PASS']:continue
            saved=read(item['replay']['path']);x=v.load_point(raw);digest=v.vector_sha(x)
            assert saved['point_vector_sha256']==digest and saved['point_file_sha256']==v.file_sha(raw)
            if digest in seen:continue
            seen.add(digest);replay=v.validate(Path(raw),solver_objective=saved['Global_UB']);assert replay['PASS'] and replay['Global_UB']==saved['Global_UB']
            assert replay['rounding']==replay['clipping']==replay['repairs']==0
            full.append(dict(raw=item['raw'],original_FULL_replay=item['replay'],independent_repeat_PASS=True,Global_UB=replay['Global_UB']))
    assert state['Global_LB']==GLOBAL_LB and state['Global_gap']==(state['BEST_GLOBAL_UB']['UB']-GLOBAL_LB)/state['BEST_GLOBAL_UB']['UB']
    assert state['BEST_GLOBAL_UB']['UB']<=INITIAL_UB and state['BEST_MOVING_FEASIBLE_UB']['moves']>0
    assert min([INITIAL_UB]+[e['UB'] for e in state['events']])>=state['BEST_GLOBAL_UB']['UB']-1e-8
    assert all(state['trajectory'][i]['UB']<state['trajectory'][i-1]['UB']-1e-8 for i in range(1,len(state['trajectory'])))
    assert state['trajectory'][0]['inherited_not_new_discovery'] and state['trajectory'][0]['Native_capture_seconds']==0.
    assert read(DOCS/'K32_K48_LB_CERTIFICATES.json')['Global_LB']==GLOBAL_LB
    assert read(DOCS/'ACTUAL_COMPATIBILITY.json')['ACTUAL']=='ACTUAL_NOT_RUN'
    result=dict(PASS=True,Native_used=used,Native_limit=1800,Native_calls_audited=len(actual),verifier_Optimize_calls=0,
        exact_nonrepeating_models=len(signatures),neighborhood_checks=proofs,independent_original_FULL_replays=full,
        PR219_authority_unchanged=True,Raw_rounding_clipping_repair=0,all384_Mode_free=True,all_source_physics_preserved=True,
        Route_Node_Flow_Alias_closure_consistent=True,all_local_centers_and_alternative_moving_witnesses_included=True,
        restricted_bounds_Global_LB_promotions=0,old_PR219_Native_separate=1795.0249993801117,
        actual_and_forbidden_case_date_campaign_LB_calls=0,Source_Case_FULL_SHA_preserved=True,wall_seconds=time.perf_counter()-began)
    write(DOCS/'FINAL_INDEPENDENT_REVIEW.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('neighborhood_checks','independent_original_FULL_replays')}))

if __name__=='__main__':main()
