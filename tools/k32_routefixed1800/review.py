"""Independent stored-evidence audit; no Native model or Optimize calls."""
from pathlib import Path
from collections import Counter
from fractions import Fraction
import json,math,time,numpy as np
from scipy import sparse
from tools.k32_routefixed1800.adapter import ROOT,DOCS,v,r,read,write,record,guard

def main():
    started=time.perf_counter();guard();state=read(DOCS/'FINAL_STATE.json')
    assert state['stopped_reason'] and state['BEST_GLOBAL_UB']
    frozen=r.audit('FINAL_INDEPENDENT_READONLY',True);assert frozen['PASS']
    write(DOCS/'FINAL_SOURCE_RESOURCE_CHECK.json',frozen)
    calls=[];used=0.;signatures=set();known_raw=set();all_start_points=set()
    actual=[]
    for path in list((DOCS/'calls').glob('*/native/NATIVE_CALL.json'))+[DOCS/'dual/NATIVE_CALL.json']:
        if path.exists() and read(path).get('entered_native'):actual.append(path)
    assert len(actual)==len(state['calls'])
    assert {str(p) for p in actual}=={c['receipt']['path'] for c in state['calls']}
    case=v.load_case()
    for call in state['calls']:
        path=Path(call['receipt']['path']);assert v.file_sha(path)==call['receipt']['sha256']
        stored=read(path);runtime=stored['Native_Runtime'];assert runtime is not None and math.isfinite(runtime) and runtime>=0
        assert used+stored['requested_seconds']<=1795.+1e-6
        used+=runtime;assert used<=1800
        assert stored['Threads']==stored['Native_worker']==1 and stored['entered_native']
        assert stored['parameter_readback']['Threads']==1
        assert not stored['callback_errors']
        folder=path.parent
        admission=read(folder/'POST_BUILD_NATIVE_ADMISSION.json');assert admission['PASS']
        assert admission['memory_admission']['RAM_reserve_bytes']==4*2**30
        assert admission['memory_admission']['commit_reserve_bytes']==6*2**30
        assert all(s['safety']['PASS'] for s in stored['resource_samples'])
        if stored['method']=='DUAL':
            cert=read(folder/'INDEPENDENT_CERTIFICATE.json')
            if cert['PASS']:
                assert cert['Global_LB']==stored['ObjBound'] and cert['native_source_attribute']=='ObjBound'
                assert cert['FULL_projection_subset_strengthened_K48']
                from tools.b2_root_lp_tightening.verify import cut_validity
                recheck=cut_validity('GRID',ROOT/'docs/v42_b2_root_lp_tightening/base',ROOT/'docs/v42_b2_root_lp_tightening/grid')
                assert recheck['PASS'] and recheck['CUTS_EXACT_sha256']==v.file_sha(folder/'CUTS_EXACT.json')
                parent=ROOT/'docs/v42_critical_grid_cg/iteration02'
                native_A=sparse.load_npz(folder/'JOINT_A.npz').tocsr();parent_A=sparse.load_npz(parent/'JOINT_A.npz').tocsr()
                assert v.matrix_sha(native_A[:parent_A.shape[0]])==v.matrix_sha(parent_A)
                with np.load(folder/'JOINT_DATA.npz') as new,np.load(parent/'JOINT_DATA.npz') as old:
                    for key in ('c','lb','ub','vtypes','names','constant'):assert np.array_equal(new[key],old[key])
                    for key in ('rhs','senses','row_names'):assert np.array_equal(new[key][:parent_A.shape[0]],old[key])
                assert read(folder/'NATIVE_READBACK.json')['PASS']
                assert v.matrix_sha(native_A)==read(folder/'NATIVE_READBACK.json')['matrix_SHA']
                del native_A,parent_A
        else:
            identity=read(folder/'MODEL_IDENTITY.json');assert identity['PASS'] and all(identity['checks'].values())
            assert not identity['unrestricted_original_C3A_MILP']
            assert read(folder/'INDEPENDENT_RESTRICTION_NATIVE0.json')['PASS']
            assert stored['restricted_ObjBound_is_Global_LB'] is False
            seal=stored['execution_source_seal'];seal_path=Path(seal['path'])
            if v.file_sha(seal_path)!=seal['sha256']:
                matches=[p for p in (DOCS/'epochs').glob('*/EXECUTED_SOURCE_HASHES.json') if v.file_sha(p)==seal['sha256']]
                assert len(matches)==1;seal_path=matches[0]
                for name,digest in read(seal_path).items():assert v.file_sha(seal_path.parent/name)==digest
            else:assert v.file_sha(seal_path)==seal['sha256']
            if stored['initial_point']:
                assert stored['initial_point']['sha256'] in known_raw,'MIP_START_NOT_PREVIOUS_FRESH_FULL'
                all_start_points.add(stored['initial_point']['sha256'])
            if stored['method']=='INITIALIZE':assert stored['initial_point'] is None and stored['actual_NumStart']==0
            if stored['method']=='ROUTE_FIXED':
                assert stored['initial_point'] is None and stored['actual_NumStart']==0
                spec=read(folder/'NEIGHBORHOOD.json');assert spec['moves']>=1
                assert read(folder/'MOVING_ROUTE_NATIVE_READBACK.json')['PASS']
                assert all(read(folder/'MOVING_ROUTE_NATIVE_READBACK.json')['checks'].values())
                proof=read(folder/'INDEPENDENT_RESTRICTION_NATIVE0.json')
                assert proof['original_alias_route_coordinates_checked']==207928
                canonical=json.dumps(spec['paths'],sort_keys=True,separators=(',',':'))
                assert canonical not in signatures;signatures.add(canonical)
                selected=0;energy=0.
                for u,path_indices in spec['paths'].items():
                    site=case.graph[1][u];t=0
                    for k in path_indices:
                        a=case.graph[2][k];assert a[:2]==(site,t) and t<a[3]<=96
                        if a[-1] is not None:
                            a[-1].validate(96);assert a[:4]==(a[-1].source,a[-1].depart,a[-1].destination,a[-1].connect)
                            selected+=1;energy+=float(a[-1].energy_kwh)
                        site,t=a[2:4]
                    assert t==96
                assert selected==spec['moves'] and abs(energy-spec['travel_energy_kWh'])<=1e-10
            iteration=next(it for it in state['iterations'] if it['call']['path']==str(path))
            assert len(stored['captures'])==len(iteration['validated'])
            for capture,item in zip(stored['captures'],iteration['validated']):
                assert capture['file']==item['raw'] and v.file_sha(item['raw']['path'])==item['raw']['sha256']
                if item['replay']:
                    assert v.file_sha(item['replay']['path'])==item['replay']['sha256']
                    replay=read(item['replay']['path'])
                    if item['PASS']:
                        assert replay['PASS'] and replay['source_sha']==v.SOURCE_SHA and replay['case_sha']==v.CASE_SHA
                        assert replay['point_file_sha256']==item['raw']['sha256']
                        assert replay['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact']
                        assert replay['solver_and_original_objective_bit_equal']
                        known_raw.add(item['raw']['sha256'])
        calls.append(dict(method=stored['method'],Native_Runtime=runtime,status=stored['Status'],receipt=record(path),PASS=True))
    assert used==state['Native_used']
    ub=state['BEST_GLOBAL_UB']['UB'];lb=.46498486997548166
    for key,value in [('K32',.46497617639758426),('K48',lb)]:
        cert=read(DOCS/'K32_K48_LB_CERTIFICATES.json')['certificates'][key]
        assert cert['LB']==value and cert['proof']['PASS']
        assert cert['proof']['source18r']==v.SOURCE_SHA and cert['proof']['case_sha']==v.CASE_SHA
    dual=DOCS/'dual/INDEPENDENT_CERTIFICATE.json'
    if dual.exists() and read(dual)['PASS']:lb=max(lb,read(dual)['Global_LB'])
    assert lb==state['Global_LB'] and state['Global_gap']==(ub-lb)/ub
    trajectory=state['trajectory'];prev_ub=math.inf;prev_lb=-math.inf
    for point in trajectory:
        assert point['UB']<=prev_ub and point['LB']>=prev_lb
        if point['method']!='DUAL':assert prev_ub-point['UB']>1e-8
        assert point['gap']==(point['UB']-point['LB'])/point['UB']
        prev_ub,prev_lb=point['UB'],point['LB']
    final_replays={}
    for name in ('BEST_GLOBAL_UB','BEST_MOVING_FEASIBLE_UB'):
        best=state[name]
        if best is None:continue
        out=DOCS/(name+'_FINAL_INDEPENDENT_REPLAY.json')
        packet=v.validate(best['point']['path'],solver_objective=best['UB'],output=out)
        assert packet['PASS'] and packet['Global_UB']==best['UB']
        final_replays[name]=record(out)
    required=['SOURCE_AND_CASE_AUTHORITY.json','ALGORITHM_CONTRACT_KO.md','EXACT_ROUTE_DAG_AUDIT.json','ROUTE_CANDIDATES.json',
        'ROUTE_FIXED_MILP_RESULTS.json','MOVING_FEASIBILITY_DIAGNOSTICS.json','FULL_REPLAY_CERTIFICATES.json','BEST_UB_TRAJECTORY.json',
        'K32_K48_LB_CERTIFICATES.json','VALID_GRID_STRENGTHENING_AUDIT.json','GLOBAL_GAP_TRAJECTORY.json','NATIVE_RUNTIME_LEDGER.json',
        'MEMORY_NUMERIC_AUDIT.json','ACTUAL_COMPATIBILITY.json','BEST_GLOBAL_96_SLOT_MESS_PLAN.csv','UB_LB_GAP_VS_NATIVE_RUNTIME.png',
        'K32_ROUTE_FIXED_1800_CANARY_FINAL_KO.md']
    assert all((DOCS/f).exists() for f in required)
    classification=read(DOCS/'SCIENTIFIC_RESULT_CLASSIFICATION.json')
    assert classification['GLOBAL_GAP_3PCT_CERTIFIED']==(state['Global_gap']<=.03)
    assert read(DOCS/'ACTUAL_COMPATIBILITY.json')['ACTUAL']=='ACTUAL_NOT_RUN'
    answer=dict(PASS=True,scope='Independent stored Native readback/cut/ledger/Raw certificates plus fresh Original FULL replay of both best plans',
        Native_optimize_calls=0,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,base_PR217='114f44330fbd995221c55385c6fde5b5b9e40d95',
        original_matrix_SHA=v.FULL_MATRIX_SHA,original_domain_SHA=v.FULL_DOMAIN_SHA,
        BEST_GLOBAL_UB=ub,BEST_MOVING_FEASIBLE_UB=None if state['BEST_MOVING_FEASIBLE_UB'] is None else state['BEST_MOVING_FEASIBLE_UB']['UB'],
        certified_Global_LB=lb,Global_gap=state['Global_gap'],GLOBAL_GAP_3PCT_CERTIFIED=state['Global_gap']<=.03,
        Native_used=used,Native_limit=1800,budget_reset_count=0,calls=calls,
        moving_models_independently_checked=len(signatures),stationary_ROUTE_FIXED_models=0,
        incompatible_N1_new_route_starts=0,start_points_all_previous_fresh_FULL=True,
        callback_errors=0,raw_repaired=False,FULL_replays=final_replays,
        restricted_bounds_never_Global_LB=True,compact_incumbents_never_FULL_UB=True,
        Actual='ACTUAL_NOT_RUN',scientific_classification=classification,
        evidence={f:record(DOCS/f) for f in required},review_source=record(Path(__file__)),wall_seconds=time.perf_counter()-started,
        independent_audit_is_solver_free_not_separate_person=True)
    write(DOCS/'FINAL_INDEPENDENT_REVIEW.json',answer)
    print(json.dumps({k:answer[k] for k in ('PASS','Native_used','BEST_GLOBAL_UB','BEST_MOVING_FEASIBLE_UB','certified_Global_LB','Global_gap')}))

if __name__=='__main__':main()
