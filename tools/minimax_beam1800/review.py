"""Independent durable receipts and Original FULL replays, Native calls zero."""
from pathlib import Path
import gc,math,time,numpy as np
from tools.minimax_beam1800.adapter import *
from tools.minimax_beam1800 import native0

def main():
    began=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json');assert state['BEST_GLOBAL_UB']
    resource=r.audit('MINIMAX_INDEPENDENT_FINAL',True);assert resource['PASS'];write(DOCS/'FINAL_SOURCE_RESOURCE_CHECK.json',resource)
    actual=list((DOCS/'calls').glob('*/native/NATIVE_CALL.json'))+list((DOCS/'lp_calls').glob('*/native/NATIVE_CALL.json'))
    actual=[p for p in actual if read(p)['entered_native']]
    assert len(actual)==len(state['calls']) and {str(p) for p in actual}=={c['receipt']['path'] for c in state['calls']}
    used=0.;models=set();physical_routes=set();stationary=[];captures=set();calls=[]
    case=v.load_native_case()
    for call in state['calls']:
        path=Path(call['receipt']['path']);assert v.file_sha(path)==call['receipt']['sha256'];stored=read(path);folder=path.parent
        assert call['cumulative_Native_before']==used and used+stored['requested_seconds']<=1795.+1e-6
        assert math.isfinite(stored['Native_Runtime']) and stored['Native_Runtime']>=0;used+=stored['Native_Runtime'];assert used<=1800
        assert used==call['cumulative_Native_after']
        assert stored['Threads']==stored['Native_worker']==1 and stored['parameter_readback']['Threads']==1
        assert not stored['callback_errors'] and not stored.get('error') and stored['initial_point'] is None
        admission=read(folder/'POST_BUILD_NATIVE_ADMISSION.json');assert admission['PASS']
        assert admission['memory_admission']['RAM_reserve_bytes']==4*2**30 and admission['memory_admission']['commit_reserve_bytes']==6*2**30
        assert all(sample['safety']['PASS'] for sample in stored['resource_samples'])
        if stored['method']=='CONDITIONAL_LP':
            assert read(folder/'NATIVE_READBACK.json')['PASS'];offline=native0.certificate(folder)
            spec=read(folder.parent/'SPEC.json');assert spec['moves']>0
            assert offline['PASS'] and stored['route_bound_is_Global_LB'] is False
        else:
            identity=read(folder/'MODEL_IDENTITY.json');assert identity['PASS'] and all(identity['checks'].values())
            assert not identity['unrestricted_original_C3A_MILP']
            assert stored['actual_NumStart']==0 and read(folder/'INDEPENDENT_RESTRICTION_NATIVE0.json')['PASS']
            assert stored['restricted_ObjBound_is_Global_LB'] is False
            assert v.file_sha(DOCS/'EXECUTED_SOURCE_HASHES.json')==stored['execution_source_seal']['sha256']
            for cap in stored['captures']:
                assert v.file_sha(cap['file']['path'])==cap['file']['sha256'];captures.add(cap['file']['path'])
            if stored['method']=='ROUTE_FIXED':
                spec=read(folder.parent/'SPEC.json');signature=spec['mathematical_model_signature']
                assert signature not in models;models.add(signature)
                route_signature=hashlib.sha256(json.dumps(spec['paths'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
                assert route_signature not in physical_routes;physical_routes.add(route_signature)
                lo,hi,*_=restriction(case,None,spec);assert audit(case,None,spec,lo,hi)['PASS']
                checks=read(folder/'MOVING_ROUTE_NATIVE_READBACK.json');assert checks['PASS'] and all(checks['checks'].values())
                if spec['stationary_control']:
                    assert call['cumulative_Native_before']>=300 and spec['paths']==stationary_paths(case)
                    assert not any(e['moves']>0 and e['UB']<=HISTORICAL+1e-8 and e['cumulative_Native_at_FULL_validation']<=call['cumulative_Native_before'] for e in state['events'])
                    stationary.append(path)
                else:assert spec['moves']>0 and spec['paths']!=stationary_paths(case)
        calls.append(dict(method=stored['method'],Native=stored['Native_Runtime'],receipt=record(path),checks_PASS=True))
    assert used==state['Native_used']==read(DOCS/'NATIVE_RUNTIME_LEDGER.json')['Native_used'] and len(stationary)<=1
    assert state['new_Global_LB_Optimize_calls']==state['unrestricted_FULL_Optimize_calls']==state['N1_upfront_calls']==state['historical_solver_starts']==0
    del case;gc.collect();replays=[];seen=set()
    for iteration in state['iterations']:
        for item in iteration['validated']:
            assert item['raw']['path'] in captures and v.file_sha(item['raw']['path'])==item['raw']['sha256']
            assert v.file_sha(item['replay']['path'])==item['replay']['sha256']
            if not item['PASS']:continue
            key=item['raw']['sha256']
            if key in seen:continue
            seen.add(key);replay=v.validate(Path(item['raw']['path']),solver_objective=read(item['replay']['path'])['Global_UB'])
            assert replay['PASS'] and replay['Global_UB']==read(item['replay']['path'])['Global_UB']
            assert replay['repairs']==replay['rounding']==replay['clipping']==0
            replays.append(dict(raw=item['raw'],replay=item['replay'],independent_original_FULL_rerun_PASS=True,Global_UB=replay['Global_UB']))
    assert state['Global_LB']==GLOBAL_LB and read(DOCS/'K32_K48_LB_CERTIFICATES.json')['PASS']
    assert state['Global_gap']==(state['BEST_GLOBAL_UB']['UB']-GLOBAL_LB)/state['BEST_GLOBAL_UB']['UB']
    assert min(e['UB'] for e in state['events'])>=state['BEST_GLOBAL_UB']['UB']-1e-8
    moving=[e for e in state['events'] if e['moves']>0]
    if moving:assert min(e['UB'] for e in moving)>=state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8
    benchmarks=read(DOCS/'COLD_START_BENCHMARKS.json')
    for key,predicate in [('T1',lambda e:e['UB']<=HISTORICAL+1e-8),('T2',lambda e:e['moves']>0 and e['UB']<=HISTORICAL+1e-8),
        ('T3',lambda e:e['moves']>0 and e['UB']<HISTORICAL-1e-5)]:
        matches=[e for e in state['events'] if predicate(e)]
        if matches:assert benchmarks[key]['Native_capture_seconds']==min(e['Native_capture_seconds'] for e in matches)
        else:assert benchmarks[key]=='NOT_REACHED'
    for metric in state['LP_pilot']:
        if metric['pruned']:
            cert=read(Path(metric['folder'])/'OFFLINE_DUAL_CERTIFICATE.json');assert cert['PASS'] and cert['certified']
            # UB can only improve later, so a previously pruning conditional
            # bound remains at least the final UB within the frozen tolerance.
            assert cert['Certified_LP_LB']>=state['BEST_GLOBAL_UB']['UB']-1e-8
    for name in ('SIGNED_SELECTION_CONTEXT.json','SIGNED_SELECTION_SOURCE_RAW.json','SIGNED_SELECTION_INDEPENDENT_NATIVE0.json','U4_K32_SIGNED_DIAGNOSTICS.json'):
        assert v.file_sha(DOCS/name)==v.file_sha(OLD/name)
    assert read(DOCS/'ACTUAL_COMPATIBILITY.json')['ACTUAL']=='ACTUAL_NOT_RUN'
    result=dict(PASS=True,Native_used=used,Native_limit=1800,Native_calls_audited=len(calls),calls=calls,
        independent_FULL_replays=replays,original_source_and_predecessor_bytes_unchanged=True,unique_route_models=len(models),
        historical_starts=0,N1_upfront=0,stationary_controls=len(stationary),conditional_LP_Global_LB_promotions=0,
        all_primal_and_conditional_native_readbacks_PASS=True,original_validator_tolerance_unchanged=True,
        Raw_rounding_clipping_repair=0,Threads=1,Heavy_workers=1,verifier_Optimize_calls=0,
        B1_B3_8500_other_dates_campaign_runs=0,wall_seconds=time.perf_counter()-began,
        scientific_source=v.SOURCE_SHA,case_sha=v.CASE_SHA,FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA)
    write(DOCS/'FINAL_INDEPENDENT_REVIEW.json',result);print(json.dumps({k:value for k,value in result.items() if k not in ('calls','independent_FULL_replays')}))

if __name__=='__main__':main()
