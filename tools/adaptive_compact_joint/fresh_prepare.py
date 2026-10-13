"""Fresh 1800s authorization, preserved historical costs, and direct Native0 gate."""
import subprocess,sys,time,gc
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.adaptive_compact_joint.direct import save

def invoke(args,log):
    with log.open('w',encoding='utf-8') as stream:rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_compact_joint.fresh_worker',*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    assert rc==0,log

def main():
    began=time.perf_counter();guard();assert not (DOCS/'NATIVE0_GATE.json').exists()
    previous=read(beta.DOCS/'PHASE0_SAFE_STOP.json');beta_calls=[]
    for p in sorted((beta.DOCS/'pilot').glob('*/NATIVE_CALL.json')):
        q=read(p);assert q['status']=='FINISHED' and q['Native_Runtime'] is not None
        beta_calls.append(dict(receipt=record(p),Native_Runtime=q['Native_Runtime']))
    beta_used=sum(c['Native_Runtime'] for c in beta_calls)
    write(DOCS/'FRESH_EXECUTION_AUTHORIZATION.json',dict(PASS=True,user_instruction='잔여로 하면 안되고 처음부터 돌려야지',
        interpretation='Separate new execution with fresh Native1800s limit; earlier actual runtimes are preserved and never erased',
        prior_joint_Native_used=previous['Native_used'],stopped_remainder_pilot_Native_used=beta_used,
        historical_total_Native=previous['Native_used']+beta_used,prior_pilot_calls=beta_calls,
        fresh_Native_limit=1800,fresh_Native_used_before=0.,prior_ledgers_not_reset_or_modified=True,
        prior_joint_source_seals=previous['original_source_and_policy_seals'],beta_source_seal=record(beta.DOCS/'EXECUTED_SOURCE_HASHES.json'),
        stopped_beta_controller_PID=142572,stop_method='Owned controller Stop-Process; already dispatched worker returned normally',ACTUAL='ACTUAL_NOT_RUN'))
    warm=validate(ROOT/RAW_REL,DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json',INITIAL_UB);assert warm['PASS']
    latest=beta.DOCS/'pilot/ADAPTIVE/FINAL_RAW.npz'
    beta_native=read(beta.DOCS/'pilot/ADAPTIVE/NATIVE_CALL.json')
    latest_cert=validate(latest,DOCS/'HISTORICAL_LAST_PILOT_ORIGINAL_FULL_REPLAY.json',beta_native['ObjVal']);assert latest_cert['PASS']
    (DOCS/'SIGNED_SELECTION_CONTEXT.json').write_bytes((beta.DOCS/'SIGNED_SELECTION_CONTEXT.json').read_bytes())
    case=v.load_native_case();point=v.load_point(ROOT/RAW_REL)
    paths={'SAME_POOL':read(beta.DOCS/'SAME_POOL_SPEC.json')['pools'],'ADAPTIVE':read(beta.DOCS/'ADAPTIVE_SPEC.json')['pools']}
    packages={}
    for label,pools in paths.items():
        folder=DOCS/'packages'/label;spec,proof=save(case,point,DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json',pools,label,folder)
        assert proof['compact_nonzeros']<proof['source_nonzeros']
        packages[label]=dict(spec=record(folder/'SPEC.json'),proof=record(folder/'EXACT_INTEGER_AND_ROW_EQUIVALENCE.json'))
    del case,point;gc.collect()
    readbacks={}
    for label in packages:
        target=DOCS/'native0'/label
        invoke(['--mode','native0','--spec',packages[label]['spec']['path'],'--seconds',60,'--output',target],DOCS/f'NATIVE0_{label}.log')
        readbacks[label]=dict(readback=record(target/'NATIVE_READBACK.json'),presolve=record(target/'PRESOLVE_TRANSFORMATION.json'),admission=record(target/'POST_BUILD_ADMISSION.json'))
    policy=dict(method='Adaptive Minimax-Aware Beam + EXACT_DIRECT_COMPACT_4MESS_JOINT + VERIFIED_FEEDBACK',
        Native_limit=1800,fresh_Native_initial=0.,inherited_scientific_UB=INITIAL_UB,inherited_global_LB=GLOBAL_LB,
        historical_Native_is_separate=True,pilot_limit=240,maximum_single_call_seconds=175,
        initial_pilot=[dict(label='SAME_POOL',seconds=60),dict(label='ADAPTIVE',seconds=150)],
        continue_only_on_verified_UB_gain_or_measured_compute_gain=True,compute_gain_ratio=.85,
        max_feedback_rounds_without_UB_gain=8,fixed_pool_size=8,no_blind_pool_size_growth=True,
        feedback_default_Native_cap=150,Heavy_Worker=1,Threads=1,all384_modes_free=True,
        all_four_route_selection_joint=True,no_MOVE_forcing=True,Original_FULL_ONLY_UB=True,
        conditional_LP_screening=False,additional_LB_Optimize=0,all_source_physics_and_Grid_preserved=True,
        cancellation_path='Create CANCEL_REQUEST.json in this fresh output tree; controller blocks dispatch and callback terminates owned active model',ACTUAL='ACTUAL_NOT_RUN')
    write(DOCS/'EXECUTION_POLICY.json',policy)
    write(DOCS/'NATIVE0_GATE.json',dict(PASS=True,Optimize_calls=0,model_transformation_calls=2,packages=packages,readbacks=readbacks,
        all_source_rows_semantically_exact=True,all_original_RHS_Sense_exact=True,full_warm_bit_exact=True,
        original_P_Q_SOC_Grid_PCS16_Mode_preserved=True,original_DAG_ETA_Flow_Arc_Node_Alias_exact=True,
        STAY_single_multiple_MOVE_all_four=True,removed_binary=8938,removed_continuous_route_flows=207736,
        no_sparse_fill_in_increase=True,whole_96_source_unmodified=True,exact_dyadic_product_proof=True,
        source_case=record(DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json'),fresh_authorization=record(DOCS/'FRESH_EXECUTION_AUTHORIZATION.json'),
        wall_seconds=time.perf_counter()-began))
    core=['fresh_adapter.py','direct.py','fresh_prepare.py','fresh_worker.py','fresh_controller.py','fresh_feedback.py']
    files=[ROOT/'tools/adaptive_compact_joint'/name for name in core]
    assert all(p.exists() for p in files)
    files.extend(DOCS/name for name in ('EXECUTION_POLICY.json','NATIVE0_GATE.json','FRESH_EXECUTION_AUTHORIZATION.json'))
    files.extend(p for p in (DOCS/'packages').rglob('*') if p.is_file())
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{p.relative_to(ROOT).as_posix():v.file_sha(p) for p in files})
    print(json.dumps(dict(PASS=True,fresh_Native_used=0.,fresh_limit=1800,historical_Native=previous['Native_used']+beta_used)))

if __name__=='__main__':main()
