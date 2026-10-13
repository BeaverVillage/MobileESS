"""Close preserved V1 and certify a point-only transport, with no budget reset."""
import gc,shutil,subprocess,time
from tools.global_local_multistart1800.adapter_v2 import *
from tools.global_local_multistart1800.joint import build_spec,independent,select_pools

def main():
    import psutil
    assert not psutil.pid_exists(126432),'V1_OWN_NATIVE_MUST_FINISH_FIRST'
    DOCS.mkdir(exist_ok=True);assert not (DOCS/'RUN_STARTED.json').exists()
    # Recheck the entire immutable V1 seal before copying any authority.
    seal=read(V1_DOCS/'EXECUTED_SOURCE_HASHES.json')
    assert all(v.file_sha(ROOT/p)==digest for p,digest in seal.items())
    records=[];used=0.
    for path in sorted((V1_DOCS/'calls').glob('*/native/NATIVE_CALL.json')):
        call=read(path)
        if not call['entered_native']:continue
        assert call['Native_Runtime'] is not None and math.isfinite(call['Native_Runtime']) and not call.get('error')
        before=used;used+=call['Native_Runtime']
        call.update(receipt=record(path),cumulative_Native_before=before,cumulative_Native_after=used,version='V1_PRESERVED',family='FOUR_MESS_JOINT' if call['method']=='FOUR_MESS_JOINT_ROUTE_POOL' else read(path.parent.parent/'SPEC.json')['family'])
        records.append(call)
    assert used<=1800 and len(records)==9
    write(DOCS/'INHERITED_V1_NATIVE_CALLS.json',dict(PASS=True,calls=records,actual_Native_used=used,
        old_ledger_preserved=record(V1_DOCS/'NATIVE_RUNTIME_LEDGER.json'),old_live_state_preserved=record(V1_DOCS/'LIVE_STATE.json'),
        orphan_finished_call_receipt_accounted=True,no_Native_reset=True,serialization_only_version=True))
    write(V1_DOCS/'CANARY_V1_STOP_RECEIPT.json',dict(PASS=True,all_actual_calls=len(records),actual_Native_used=used,
        old_sources_and_ledger_unchanged=True,no_other_process_stopped=True,own_inflight_child_finished=True,
        active_Final_state_not_fabricated=True,overall_budget_remaining=1800-used))
    for name in ('PR220_WARM_START_CERTIFICATE.json','PR220_FRESH_ORIGINAL_FULL_REPLAY.json','GLOBAL_CANDIDATE_POOL.json','GLOBAL_ROUTE_DIVERSITY_AUDIT.json','INITIAL_CRITICAL_PRIORITY.json','SOURCE_CASE_AUTHORITY.json','LB_CANDIDATE_COMPARISON.json','FAST_LB_NATIVE0.json','K32_K48_INHERITED_LB_CERTIFICATE.json','SIGNED_SELECTION_CONTEXT.json','SIGNED_SELECTION_SOURCE_RAW.json','SIGNED_SELECTION_INDEPENDENT_NATIVE0.json','U4_K32_SIGNED_DIAGNOSTICS.json'):
        shutil.copyfile(V1_DOCS/name,DOCS/name)
    certificates=[]
    for call in records:
        if call['method']!='FOUR_MESS_JOINT_ROUTE_POOL':continue
        for ordinal,cap in enumerate(call['captures']):
            raw=Path(cap['file']['path']);assert v.file_sha(raw)==cap['file']['sha256']
            with np.load(raw,allow_pickle=False) as z:point=z['point'].copy();lam=z['route_selection'].copy()
            assert v.vector_sha(point)==cap['vector_sha256'] and np.isin(lam,(0.,1.)).all()
            folder=DOCS/'inherited_v1'/raw.parent.parent.name/str(ordinal);folder.mkdir(parents=True,exist_ok=True)
            transported=folder/'POINT_ONLY_RAW.npz';np.savez_compressed(transported,point=point);np.savez_compressed(folder/'LAMBDA_RAW.npz',route_selection=lam)
            assert v.load_point(transported).tobytes()==point.tobytes()
            cert=v.validate(transported,solver_objective=cap['Solver_ObjVal'],output=folder/'ORIGINAL_FULL_REPLAY.json')
            certificates.append(dict(PASS=cert['PASS'],source_Native_packet=record(raw),point_only_packet=record(transported),lambda_packet=record(folder/'LAMBDA_RAW.npz'),
                point_vector_SHA=v.vector_sha(point),replay=record(folder/'ORIGINAL_FULL_REPLAY.json'),UB=cert.get('Global_UB'),
                source_array_bytes_unchanged=True,rounding=0,clipping=0,repair=0,reason='Lossless packet-field separation, not numerical repair'))
    assert all(c['PASS'] for c in certificates)
    write(DOCS/'V1_POINT_ONLY_TRANSPORT_CERTIFICATES.json',dict(PASS=True,certificates=certificates,Optimize_calls=0,Native_used_not_reset=used))
    # Actual Source/Case/Resource and point-only raw readback are repeated for V2.
    r.create_baseline();baseline=read(r.BASELINE);known={i['path'] for i in baseline['protected_files']}
    for p in V1_DOCS.rglob('*'):
        if p.is_file() and not p.is_relative_to(DOCS) and str(p) not in known:baseline['protected_files'].append(r.digest(p));known.add(str(p))
    write(r.BASELINE,baseline);r.baseline.cache_clear();resource=r.audit('JOINT_V2_PREPARE',True);assert resource['PASS'];write(DOCS/'PRE_RUN_RESOURCE_SOURCE_AUDIT.json',resource)
    case=v.load_native_case();x=v.load_point(ROOT/RAW_REL);pool=read(DOCS/'GLOBAL_CANDIDATE_POOL.json')['candidates']
    pools=select_pools(case,pool,x,8,variant=6)
    spec,lo,hi,A,rhs=build_spec(case,x,DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json',pools,'JOINT_V2_NATIVE0',120);spec['center_raw']=record(ROOT/RAW_REL)
    proof=independent(case,x,spec,lo,hi,A,rhs);assert proof['PASS']
    write(DOCS/'native0/SPEC.json',spec);write(DOCS/'native0/PROOF.json',proof)
    from tools.global_local_multistart1800.joint_native0 import verify_build
    verify_build(case,x,spec,lo,hi,A,rhs,DOCS/'native0/model')
    oldpolicy=read(V1_DOCS/'SEARCH_SWITCHING_POLICY.json');policy=dict(oldpolicy,version='V2_POINT_ONLY_TRANSPORT',
        budget_offset=used,total_budget_still1800=True,initial_pool_size=8,
        ablation_families=['PAIR_MESS01_MESS02','PAIR_MESS01_MESS04','PAIR_MESS02_MESS04'],
        root_incomplete_definition='Only TIME_LIMIT with no completed root: change small corridor. Presolve OPTIMAL is completed solve and permits expansion.',
        stagnation_expansion='Add2 original routes to all four vehicle pools after completed solves, retaining STAY/PR220/current center; no separate Cartesian combination MILPs.',
        Raw_transport='point-only NPZ compatible with unchanged original validator; lambda raw floats separately preserved in Native capture JSON.',
        V1_ledger=record(V1_DOCS/'NATIVE_RUNTIME_LEDGER.json'),V1_all_receipts=record(DOCS/'INHERITED_V1_NATIVE_CALLS.json'))
    write(DOCS/'SEARCH_SWITCHING_POLICY.json',policy)
    files=[ROOT/p for p in seal]
    files.extend((ROOT/'tools/global_local_multistart1800').glob('*_v2.py'))
    files.extend(DOCS/name for name in ('SEARCH_SWITCHING_POLICY.json','INHERITED_V1_NATIVE_CALLS.json','V1_POINT_ONLY_TRANSPORT_CERTIFICATES.json','native0/SPEC.json','native0/PROOF.json','native0/model/JOINT_NATIVE0_READBACK.json'))
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{str(p.relative_to(ROOT)):v.file_sha(p) for p in files})
    print(json.dumps(dict(PASS=True,Optimize_calls=0,prior_Native=used,new_remaining=1800-used,canonical_FULL_PASS=len(certificates))))

if __name__=='__main__':
    import math
    main()
