"""Read-only reconciliation after the owned controller stops dispatching."""
import math,subprocess
from tools.adaptive_compact_joint.adapter import *

def main():
    owned=read(OLD_DOCS/'PHASE0_PROCESS_OWNERSHIP.json')
    # Source worker writes entered_native before optimize, and Runtime after return.
    receipts=sorted(OLD_DOCS.glob('calls/*/native/NATIVE_CALL.json'))+sorted((OLD_DOCS/'v2').glob('calls/*/native/NATIVE_CALL.json'))+list((OLD_DOCS/'v2/dual').glob('NATIVE_CALL.json'))
    calls=[];unknown=[]
    for p in receipts:
        q=read(p)
        if not q['entered_native']:continue
        if q.get('Native_Runtime') is None:unknown.append(str(p));continue
        assert q['Native_Runtime']>=0 and not q.get('error') and q.get('Status') in (2,9,11)
        calls.append(dict(receipt=record(p),Native_Runtime=q['Native_Runtime'],status=q.get('Status'),ObjVal=q.get('ObjVal'),ObjBound=q.get('ObjBound'),error=q.get('error')))
    assert not unknown,'UNKNOWN_RUNTIME_NO_REMAINING_BUDGET'
    total=sum(c['Native_Runtime'] for c in calls);assert total<=1800
    files={}
    for folder in ('tools/global_local_multistart1800','docs/v42_b2_global_local_multistart_dual1800'):
        for p in sorted((OLD_ROOT/folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:files[p.relative_to(OLD_ROOT).as_posix()]=v.file_sha(p)
    for seal in (OLD_DOCS/'EXECUTED_SOURCE_HASHES.json',OLD_DOCS/'v2/EXECUTED_SOURCE_HASHES.json'):
        for rel,h in read(seal).items():assert v.file_sha(OLD_ROOT/rel)==h
    write(DOCS/'PRESERVED_JOINT_FILES.json',files)
    q=read(receipts[-2]);last=OLD_DOCS/'v2/calls/024_JOINT_POOL_123/native/NATIVE_CALL.json';q=read(last)
    final_replay=read(OLD_DOCS/'v2/phase0/FINAL_REPLAY_EXACT_ARGUMENT.json');assert final_replay['PASS']
    write(DOCS/'PHASE0_SAFE_STOP.json',dict(PASS=True,Optimize_calls=0,owned_processes=owned,
        controller=dict(PID=125764,termination='Stop-Process after PID/parent/command ownership verification; dispatch blocked'),
        worker=dict(PID=142760,termination='Unmodified existing 120 second TimeLimit; normal return and model.dispose',Native_Runtime=q['Native_Runtime']),
        other_processes_stopped=[],original_worktree=str(OLD_ROOT),original_HEAD=BASE,execution_sources_uncommitted=True,
        original_source_and_policy_seals=[record(OLD_DOCS/'EXECUTED_SOURCE_HASHES.json'),record(OLD_DOCS/'v2/EXECUTED_SOURCE_HASHES.json')],
        original_ledgers=[record(OLD_DOCS/'NATIVE_RUNTIME_LEDGER.json'),record(OLD_DOCS/'v2/NATIVE_RUNTIME_LEDGER.json')],
        preserved_manifest=record(DOCS/'PRESERVED_JOINT_FILES.json'),actual_call_count=len(calls),calls=calls,
        Native_used=total,remaining_approved_seconds=1800-total,unknown_Runtime=unknown,budget_reset_count=0,
        last_call=record(last),final_raw=q['captures'][-1]['file'],last_original_FULL_replay=record(OLD_DOCS/'v2/phase0/FINAL_REPLAY_EXACT_ARGUMENT.json'),
        BEST_GLOBAL_UB=INITIAL_UB,BEST_MOVING_FEASIBLE_UB=INITIAL_UB,Global_LB=GLOBAL_LB,Global_Gap_percent=100*(INITIAL_UB-GLOBAL_LB)/INITIAL_UB,
        last_model=dict(paths_per_unit=24,binary=9418,continuous=344955,Status=q['Status'],NodeCount=q['NodeCount'],ObjBound=q['ObjBound'],restricted_gap=q['MIPGap'],root_completed=False),
        no_original_source_policy_ledger_raw_overwritten=True,ACTUAL='ACTUAL_NOT_RUN'))
    print(json.dumps(dict(PASS=True,Native_used=total,remaining=1800-total,files=len(files))))

if __name__=='__main__':main()
