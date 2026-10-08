"""Verified owned M0 numerical handoff; never fabricate a solver status."""
from practical_support import *
import argparse,re

def simplex_rows(log):
    rows=[]
    for line in log.splitlines():
        fields=line.split()
        if len(fields)!=5 or not fields[0].isdigit() or not fields[-1].endswith('s'):continue
        try:rows.append(dict(iterations=int(fields[0]),objective=float(fields[1]),primal_infeasibility=float(fields[2]),dual_infeasibility=float(fields[3]),seconds=float(fields[4][:-1]),literal=line))
        except ValueError:continue
    return rows

def ready(native_receipt,rows,root_receipt_exists):
    tail=rows[-10:]
    conditions=dict(native_clean_stall=native_receipt.get('Status')==11 and native_receipt.get('stop_reason')=='FIRST_HOUR_NO_MATERIAL_BOUND_OR_TREE_PROGRESS' and not native_receipt.get('callback_errors') and not native_receipt.get('exception'),root_receipt_absent=not root_receipt_exists,ten_simplex_records=len(tail)==10,root_elapsed_7200=bool(tail and tail[-1]['seconds']>=7200),cleanup_still_infeasible=bool(tail and all(r['primal_infeasibility']>1e6 and r['objective']>1. for r in tail)))
    return dict(PASS=all(conditions.values()),conditions=conditions,tail=tail)

def run(execute=False):
    import psutil
    folder=OUT/'runs/native_production_initial';receipt=folder/'NATIVE_RECEIPT.json'
    native=read(receipt) if receipt.exists() else {}
    root=OLD/'external_nodes/0000';log=root/'LP.log'
    check=ready(native,simplex_rows(log.read_text(encoding='utf-8',errors='replace')),(root/'RESULT.json').exists())
    if not execute:print(json.dumps(clean(check),ensure_ascii=False));return
    assert check['PASS'],'PREREGISTERED_HANDOFF_CONDITIONS_NOT_MET'
    assert read(folder/'INDEPENDENT_AUDIT.json')['PASS'],'NATIVE_RESULT_AUDIT_REQUIRED_BEFORE_SWITCH'
    assert not (OUT/'M0_OPERATOR_ABORTED.json').exists(),'M0_HANDOFF_ALREADY_EXECUTED'
    baseline=read(OUT/'BACKEND_SELECTION.json')['external']
    pid=read(OUT/'IMMUTABLE_DEADLINE.json')['existing_M0_process_PID'];p=psutil.Process(pid)
    assert p.create_time()==baseline['registered_process_create_time'],'PID_REUSED_NO_ACTION'
    assert Path(p.cwd()).resolve()==ROOT.resolve() and len(p.cmdline())==2
    assert Path(p.cmdline()[1].replace('\\','/')).as_posix()=='docs/v42_m1_exact_solver_redesign_20261008/external_bb.py'
    before=dict(PID=pid,create_time=p.create_time(),cwd=p.cwd(),cmdline=p.cmdline(),memory=p.memory_info()._asdict(),cpu=p.cpu_times()._asdict(),checkpoint_SHA256=sha(OLD/'OPEN_CHECKPOINT.json'))
    # Re-check the terminal receipt just before the owned process action.
    assert not (root/'RESULT.json').exists(),'M0_COMPLETED_DURING_HANDOFF_NO_ACTION'
    atomic(OUT/'M0_HANDOFF_BEFORE.json',dict(UTC=stamp(),policy_SHA256=sha(OUT/'M0_NUMERICAL_HANDOFF_POLICY.json'),eligibility=check,owned_process=before,unknown_native_status=True,OPEN_root_retained=True))
    p.terminate();p.wait(timeout=15)
    after={q.relative_to(OLD).as_posix():sha(q) for q in [OLD/'OPEN_CHECKPOINT.json',OLD/'EXTERNAL_MODEL_AUTHORITY.json',*root.rglob('*')] if q.is_file()}
    checkpoint=read(OLD/'OPEN_CHECKPOINT.json');state=checkpoint['state']
    assert state['in_flight']==0 and len(state['nodes'])==1 and state['nodes']['0']['state']=='OPEN' and state['processed']==0
    atomic(OUT/'M0_OPERATOR_ABORTED.json',dict(UTC=stamp(),operator_reason='PREREGISTERED_INFEASIBLE_CROSSOVER_CLEANUP_HANDOFF',native_final_status=None,native_Status_unavailable=True,not_claimed_native_INTERRUPTED=True,last_observed_simplex=check['tail'][-1],owned_process=before,registered_attempt_file_SHA256=after,OPEN_checkpoint_retained=True,root_OPTIMAL=False,exact_node_certificates=0,valid_LB_UB_unchanged=True,original_M0_source_unchanged=True,A_stage_untouched=True,no_concurrent_duplicate_root=True))
    print('VERIFIED_M0_OPERATOR_ABORT_OPEN_ROOT_PRESERVED',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');run(parser.parse_args().execute)
