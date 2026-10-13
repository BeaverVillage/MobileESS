"""Suspend only the verified dispatcher at an idle, fully-accounted boundary."""
import subprocess,psutil
from tools.adaptive_perf_v3.bootstrap import *

def main():
    configure();full_guard();assert read(DOCS/'NATIVE0_STATIC_GATE.json')['PASS'] and read(DOCS/'SCORE_VECTORIZE_EQUIVALENCE.json')['PASS']
    assert read(DOCS/'INDEPENDENT_NATIVE0_REVIEW.json')['PASS']
    assert read(DOCS/'SCORE_VECTORIZE_EQUIVALENCE.json')['source_code']['sha256']==v.file_sha(DEVELOPMENT_ROOT/'tools/adaptive_perf_v3/scoring.py')
    assert not (DOCS/'MIGRATION_STATE.json').exists()
    process=psutil.Process(147752);ownership=dict(PID=process.pid,parent_PID=process.ppid(),create_time=process.create_time(),cwd=process.cwd(),command=process.cmdline())
    assert process.ppid()==109732 and process.cwd()==str(PREVIOUS_ROOT) and 'tools.adaptive_compact_joint.resume_controller' in process.cmdline()
    write(DOCS/'PRE_HANDOFF_OWNERSHIP.json',ownership)
    paused=False
    try:
        while True:
            assert process.create_time()==ownership['create_time'] and process.cmdline()==ownership['command']
            if process.children(recursive=True):time.sleep(1);continue
            process.suspend();paused=True
            if process.children(recursive=True):process.resume();paused=False;time.sleep(1);continue
            try:
                state=read(PREVIOUS_DOCS/'LIVE_STATE.json')
                actual=state['prior_Native']+sum(read(p)['Native_Runtime'] for p in sorted(PREVIOUS_DOCS.glob('calls/*/NATIVE_CALL.json')))
                ready=(actual==state['Native_used'] and len(state['iterations'])==len(state['new_calls']) and all(a['PASS'] for a in state['validations']))
            except Exception:ready=False
            if not ready:process.resume();paused=False;time.sleep(1);continue
            assert state['stopped_reason'] is None and 1800-state['Native_used']>=60
            break
        write(DOCS/'MIGRATION_STATE.json',state)
        write(DOCS/'FROZEN_PREVIOUS_FILES.json',{str(p):v.file_sha(p) for p in PREVIOUS_DOCS.rglob('*') if p.is_file()})
        policy=dict(Native_limit=1800,inherited_Native=state['Native_used'],budget_reset=False,maximum_single_call_seconds=175,
            Heavy_Worker=1,Threads=1,normal_cap=140,matched_formulation_comparisons_first2_pools=True,
            backend_default='DIRECT',comparison_EF_original_helpers_retained=True,Original_FULL_ONLY_UB=True,Global_LB=GLOBAL_LB,
            restricted_ObjBound_Global_LB=False,no_MOVE_forcing=True,all_four_STAY_single_multiple=True,
            no_UB_stagnation_stop=True,new_LB_Optimize=0,ACTUAL='ACTUAL_NOT_RUN',
            callback_guard='Current executed source/policy SHA + original physical source/resource/B1 gate every10Native seconds. Full predecessor history SHA before/after each call and before FULL acceptance.',
            cache='Static exact alias operator SHA-verified readonly; new DAG/links/Start/raw checked each pool/call')
        write(DOCS/'EXECUTION_POLICY.json',policy)
        files=list((DEVELOPMENT_ROOT/'tools/adaptive_perf_v3').glob('*.py'))+[DOCS/name for name in ('EXECUTION_POLICY.json','NATIVE0_STATIC_GATE.json','INDEPENDENT_NATIVE0_REVIEW.json','SCORE_VECTORIZE_EQUIVALENCE.json','PROTECTED_BASELINE.json','SIGNED_SELECTION_CONTEXT.json')]
        files.extend(p for p in (DOCS/'packages/INITIAL_1001').rglob('*') if p.is_file())
        write(DOCS/'EXECUTED_SOURCE_HASHES.json',{str(p):v.file_sha(p) for p in files})
        readbacks={}
        for form in ('DIRECT','EF'):
            output=DOCS/'native0'/form;log=DOCS/f'NATIVE0_READBACK_{form}.log'
            with log.open('w',encoding='utf-8') as stream:
                rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_perf_v3.worker','--mode','native0','--spec',str(DOCS/f'packages/INITIAL_1001/{form}/SPEC.json'),'--output',str(output),'--seconds','140'],cwd=DEVELOPMENT_ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
            q=read(output/'NATIVE_CALL.json');assert rc==0 and q['Native_Runtime']==0. and not q['entered_native'] and q['model_disposed']
            readbacks[form]=dict(call=record(output/'NATIVE_CALL.json'),readback=q['readback'])
        full_guard()
        write(DOCS/'NATIVE0_GATE.json',dict(PASS=True,Optimize_calls=0,Source_Policy_frozen_before_native_readback=True,
            independent_static_and_dynamic_proof=record(DOCS/'NATIVE0_STATIC_GATE.json'),cache_regression=record(DOCS/'CACHE_NATIVE0_EQUIVALENCE.json'),
            score_equivalence=record(DOCS/'SCORE_VECTORIZE_EQUIVALENCE.json'),readbacks=readbacks,
            inherited_Native=state['Native_used'],same_limit=1800,budget_reset=False,Worker1_Threads1=True,Global_LB=GLOBAL_LB))
        for path,digest in read(DOCS/'FROZEN_PREVIOUS_FILES.json').items():assert v.file_sha(path)==digest
        assert not process.children(recursive=True)
        write(DOCS/'HANDOFF_PASS.json',dict(PASS=True,previous_controller=ownership,previous_dispatch_temporarily_suspended=True,
            actual_worker_count_at_handoff=0,previous_Native=state['Native_used'],remaining=1800-state['Native_used'],budget_reset=False,
            Source_and_Native_ledger_not_modified=True,new_Native0_gate=record(DOCS/'NATIVE0_GATE.json')))
        print(json.dumps(dict(PASS=True,Native_offset=state['Native_used'],remaining=1800-state['Native_used'],paused_dispatcher=147752)),flush=True)
    except Exception:
        if paused and process.is_running():process.resume()
        raise
if __name__=='__main__':main()
