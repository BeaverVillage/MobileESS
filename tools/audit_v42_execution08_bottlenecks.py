"""Read-only failure audit; no case rebuild, optimizer or ledger mutation."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main(execution, output):
    read=lambda path:json.loads(path.read_text(encoding='utf8'))
    output.mkdir(parents=True,exist_ok=True)
    ledger=read(execution/'PLANNING_NATIVE_LEDGER.json')
    if ledger.get('inflight') or ledger.get('active_stage_context'):
        raise RuntimeError('STOPPED_RECONCILED_EXECUTION_REQUIRED')
    calls=[row for row in ledger['calls'] if row.get('solver')=='GUROBI']
    b1=[r for r in calls if r.get('stage_context',{}).get('arm')=='B1']
    a=execution/'B1/A1';dw=read(a/'DW/DW_RESULT.json')
    integer=read(a/'ORIGINAL_INTEGER_BOUND_ATTRIBUTES.json')
    native=read(a/'P1_ONLY_RESULT.json')
    phases=[]
    for attempt in sorted((a/'DW/PHASE_I').glob('S*/*/NATIVE_RESULT.json')):
        r=read(attempt)
        phases.append(dict(profile=r['adaptive_policy'],status=r['status'],Native_seconds=r['native_seconds'],
                           Work=r['Work'],SolCount=r['SolCount'],snapshot_sha=r['snapshot_sha'],
                           raw_attributes=str(attempt.with_name('RAW_ATTRIBUTES.npz'))))
    log=(a/'NATIVE_GUROBI.log').read_text(errors='replace')
    b2=read(execution/'B2/ARM_OUTCOME.json')
    b2_calls=[r for r in calls if r.get('stage_context',{}).get('arm')=='B2']
    f2=read(execution/'B2/M1/INITIALIZATION/F2_STATIONARY_FREE_MODES/RESULT.json')
    f3=read(execution/'B2/M1/INITIALIZATION/F3_CURRENT_DAY_ROUTE/RESULT.json')
    archive=read(execution/'SOURCE_ARCHIVE_RECEIPT.json')
    source=Path(archive['archive'])/'v42_integration/table_v_a_control.py'
    source_lines=source.read_text().splitlines()
    audit=dict(
        execution=str(execution),Native_optimize_calls_by_audit=0,
        B1=dict(phase_I_status=dw['status'],completed_outer_Phase_I_iterations=0,
                last_Phase_I_iteration='S0',S1_started=False,P1_full_pricing_started=False,
                Phase_I_policies=phases,Phase_I_Native_seconds=dw['Native_Runtime'],
                Phase_I_wall_seconds=dw['wall_seconds'],Integer_MILP_Optimize_entered=True,
                Integer_Native_status=integer['status'],Integer_Native_seconds=integer['native_call']['Native_Runtime'],
                Integer_SolCount=integer['native_call']['native_numeric_attributes']['SolCount'],
                callback_exception=False,callback_message_forced_terminate=True,
                callback_source=str(source),callback_source_function='solve_original.callback',
                callback_source_line=next(i for i,s in enumerate(source_lines,1) if 'errors.append(message.strip());m.terminate()' in s),
                native_terminal_NUMERIC=False,native_terminal_INTERRUPTED='Solve interrupted' in log,
                root_barrier_numerical_warning=True,warning_recovery_success_unestablished=True,
                FULL_replay_failure=False,FULL_replay_status='NOT_ENTERED_NO_INCUMBENT',
                last_valid_E08_X_Pi_RC_Basis=None,
                cumulative_stage_Native_seconds=sum(r['Native_Runtime'] for r in b1),
                Native_remaining_seconds=5400-sum(r['Native_Runtime'] for r in b1),
                original_binding=integer['native_binding'],source_case_binding=integer['binding']),
        B2=dict(outcome=b2,first_gate_error=f2['native_error'],last_gate_error=f3['native_error'],
                F2_Optimize_entered=f2['Native_Runtime']>0,F3_Optimize_entered=f3['Native_Runtime']>0,
                F2_available_RAM_bytes=f2['memory_after_native']['RAM_available'],threshold_removed_bytes=8*1024**3,
                C3A_independent_proof=read(execution/'B2/M1/CURRENT_EXACT_C3A_PROOF.json'),
                cumulative_stage_Native_seconds=sum(r['Native_Runtime'] for r in b2_calls),
                full_domain_infeasibility_certified=False,
                concurrent_agent_audit_RSS_observed_bytes=6261542912,
                agent_audit_contributed_memory_pressure=True,agent_audit_stopped=True),
        Native_ledger_total_seconds=ledger['Gurobi_Native_seconds'],ledger_reset=False,
        stopped=True,automatic_resume=False,P2_calls=0,R2='HOLD',IEEE8500_executed=False,
        limitations=['No additional Native Optimize authorized or executed by this audit',
                     'Dual-simplex comparison, S1 warm-start performance and repaired MILP success need bounded Native approval'])
    (output/'EXECUTION08_FAILURE_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf8')
    with (output/'NATIVE_CALLS.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        fields=['arm','stage','label','status','Native_Runtime','wall_seconds']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in calls:
            writer.writerow(dict(arm=r.get('stage_context',{}).get('arm'),stage=r.get('stage_context',{}).get('stage'),
                                 **{k:r.get(k) for k in fields[2:]}))
    print(json.dumps(dict(B1_Native=audit['B1']['cumulative_stage_Native_seconds'],
                         B2_Native=audit['B2']['cumulative_stage_Native_seconds'],audit=str(output))))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--execution',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();main(a.execution,a.output)
