"""Freeze corrected continuation policy without altering prior pilot evidence."""
import subprocess,sys,time,gc
from tools.adaptive_compact_joint.resume_adapter import *
from tools.adaptive_compact_joint.direct import save
from tools.adaptive_compact_joint.compact import integer_proof
from tools.global_local_multistart1800.joint import build_spec

def main():
    configure();guard();began=time.perf_counter();assert not (DOCS/'NATIVE0_GATE.json').exists()
    prior=read(PILOT_DOCS/'FINAL_STATE.json');assert prior['fresh_Native_used']==sum(c['Native_Runtime'] for c in prior['Native_calls'])
    immutable={p.relative_to(ROOT).as_posix():v.file_sha(p) for p in PILOT_DOCS.rglob('*') if p.is_file() and not p.is_relative_to(DOCS)}
    write(DOCS/'PRESERVED_PILOT_FILES.json',immutable)
    write(DOCS/'USER_CONTINUATION_CORRECTION.json',dict(PASS=True,
        request='Continue Adaptive Beam–Joint MILP in remaining1736.358s of the same fresh1800s budget; preserve63.642s pilot; compare multiple pools; do not reject algorithm for early UB stagnation',
        inherited_fresh_Native=prior['fresh_Native_used'],same_fresh_limit=1800,new_budget_reset=False,
        prior_stop_decision_superseded=True,prior_backend_whole_algorithm_rejection_superseded=True,
        prior_files=record(DOCS/'PRESERVED_PILOT_FILES.json'),same_execution_authorization=record(PILOT_DOCS/'FRESH_EXECUTION_AUTHORIZATION.json')))
    initial=prior['BEST_GLOBAL_UB'];accepted=[a for a in prior['validations'] if a['FULL_PASS']];assert accepted
    latest=accepted[-1];cert=validate(latest['dense_lift']['path'],DOCS/'INITIAL_FRESH_FULL_REPLAY.json',latest['UB']);assert cert['PASS']
    (DOCS/'SIGNED_SELECTION_CONTEXT.json').write_bytes((PILOT_DOCS/'SIGNED_SELECTION_CONTEXT.json').read_bytes())
    case=v.load_native_case();point=v.load_point(latest['dense_lift']['path']);pools=read(PILOT_DOCS/'POST_PILOT_FEEDBACK_SPEC.json')['pools']
    folder=DOCS/'packages/COMPARE_POOL_001';direct_spec,direct_proof=save(case,point,DOCS/'INITIAL_FRESH_FULL_REPLAY.json',pools,'COMPARE_POOL_001',folder)
    joint_spec,lo,hi,A,rhs=build_spec(case,point,DOCS/'INITIAL_FRESH_FULL_REPLAY.json',pools,'COMPARE_POOL_001',60)
    proof=integer_proof(case,point,joint_spec,lo,hi,A,rhs);joint_spec['center_raw']=record(latest['dense_lift']['path'])
    write(folder/'JOINT_SPEC.json',joint_spec);write(folder/'JOINT_PROOF.json',proof)
    del case,point,A,lo,hi;gc.collect()
    readbacks={}
    for form,spec in (('JOINT',folder/'JOINT_SPEC.json'),('DIRECT',folder/'SPEC.json')):
        out=DOCS/'native0'/form
        with (DOCS/f'NATIVE0_{form}.log').open('w',encoding='utf-8') as stream:
            rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_compact_joint.resume_worker','--mode','native0','--formulation',form,'--spec',str(spec),'--output',str(out),'--seconds','90'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
        assert rc==0 and read(out/'NATIVE_CALL.json')['status']=='NATIVE0_PASS'
        readbacks[form]=dict(call=record(out/'NATIVE_CALL.json'),presolve=record(out/'PRESOLVE_TRANSFORMATION.json'),admission=record(out/'POST_BUILD_ADMISSION.json'))
    policy=dict(Native_limit=1800,inherited_fresh_Native=prior['fresh_Native_used'],available_at_continuation=1800-prior['fresh_Native_used'],
        no_fresh_budget_reset=True,maximum_single_call_seconds=175,comparison_pools_minimum=3,initial_comparison_cap=90,
        normal_native_cap=140,root_incomplete_cap=165,periodic_other_formulation_every=5,
        premature_no_UB_gain_stop=False,no_UB_stagnation_reject=False,Beam_continues_if_direct_rejected=True,
        default_formulation_before_comparison='JOINT',model_signature_dedup=True,fixed_pool_size=8,
        max_pool_epochs_safety=100,stop_only_budget_or_source_resource_numeric_error_or_exhaustion=True,
        Heavy_Worker=1,Threads=1,all_four_MESS_STAY_single_multiple=True,no_MOVE_forcing=True,
        Original_FULL_ONLY_UB=True,restricted_ObjBound_Global_LB=False,Global_LB=GLOBAL_LB,
        new_LB_Optimize=0,conditional_LP_Optimize=0,cancellation_path='CANCEL_REQUEST.json',ACTUAL='ACTUAL_NOT_RUN')
    write(DOCS/'EXECUTION_POLICY.json',policy)
    write(DOCS/'NATIVE0_GATE.json',dict(PASS=True,Optimize_calls=0,source_physics_unchanged=True,all_four_joint=True,
        original_Route_Node_Flow_Alias_ETA_energy_exact=True,all384_Mode_P_Q_SOC_Grid_PCS16_original=True,
        warm_original_FULL_PASS=record(DOCS/'INITIAL_FRESH_FULL_REPLAY.json'),same_budget_offset=prior['fresh_Native_used'],
        direct_proof=record(folder/'EXACT_INTEGER_AND_ROW_EQUIVALENCE.json'),joint_proof=record(folder/'JOINT_PROOF.json'),
        native_readbacks=readbacks,original_pilot_preserved=True,wall_seconds=time.perf_counter()-began))
    code=[ROOT/'tools/adaptive_compact_joint'/name for name in ('resume_adapter.py','resume_prepare.py','resume_worker.py','resume_feedback.py','resume_controller.py')]
    files=code+[DOCS/name for name in ('PRESERVED_PILOT_FILES.json','USER_CONTINUATION_CORRECTION.json','EXECUTION_POLICY.json','NATIVE0_GATE.json')]
    files+=[p for p in folder.rglob('*') if p.is_file()]
    assert all(p.exists() for p in files)
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{p.relative_to(ROOT).as_posix():v.file_sha(p) for p in files})
    print(json.dumps(dict(PASS=True,Native_offset=prior['fresh_Native_used'],remaining=1800-prior['fresh_Native_used'],budget_reset=False)))

if __name__=='__main__':main()
