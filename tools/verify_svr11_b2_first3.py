"""Independent user handoff: new B2 May01/02/03 FULL + Actual96, not all124."""
from pathlib import Path
import sys,math
from fractions import Fraction
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.processes import live
from verify_svr11_handoff37 import audit_date,require


def run(root):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json')
    require(m['algorithm_version']=='V42_COMMON_MESS_U4_THEN_FULL_MILP_V2','HANDOFF_NEW_FULL_MILP_REQUIRED')
    ledger=read(root/'CAMPAIGN_LEDGER.json');outcomes=[]
    for day in ('2025-05-01','2025-05-02','2025-05-03'):
        row=ledger['dates']['B2/'+day]
        if row['status']!='PASS' or live(row.get('worker',{})):
            outcomes.append(dict(day=day,PASS=False,status=row['status'],reason=row.get('reason')));continue
        try:
            require(row.get('reused') is not True,'HANDOFF_OLD_B2_OPTIMIZATION_FORBIDDEN')
            r=read(row['result']);request=read(r['request']['path'])
            require(r['source_SHA']==m['execution_SHA'] and request['retry_starts_from_native_zero'] is True,
                'HANDOFF_FRESH_B2_SOURCE_OR_NATIVE_START')
            proof=audit_date(root,m,row);science=r['scientific'];native=0.;calls=0
            for receipt in r['native_ledgers']:
                value=read(receipt['receipt']['path'])
                require(value['inflight'] is None,'HANDOFF_UNKNOWN_INFLIGHT_NATIVE')
                for call in value['calls']:
                    require(call.get('entered_native') is True and call.get('runtime_unavailable') is False
                        and call['Native_Runtime'] is not None and math.isfinite(call['Native_Runtime']),
                        'HANDOFF_UNKNOWN_NATIVE_RUNTIME')
                    require(call['effective_TimeLimit']<=max(0,1800-native),
                        'HANDOFF_NATIVE_TIME_LIMIT_RESET')
                    native+=call['Native_Runtime'];calls+=1
            require(abs(native-r['Native_Runtime'])<1e-8,'HANDOFF_NATIVE_DOUBLECOUNT')
            require(science['native_runtime_limit_seconds']==1800,'HANDOFF_M_NATIVE_CAP_CHANGED')
            require(science['error'] is None,'HANDOFF_M_SCIENTIFIC_ERROR')
            if not science['global_gap_certified']:
                require(native>=1800,'HANDOFF_U4_EARLY_EXHAUSTION_STILL_TERMINATES')
                require(science['certified_Global_LB'] is science['certified_gap'] is None,
                    'HANDOFF_DIAGNOSTIC_BOUND_USED_AS_GLOBAL')
            if science.get('initial_exact_verified_UB') is not None:
                require(Fraction(science['exact_Global_UB'])<=Fraction(science['initial_exact_verified_UB']),
                    'HANDOFF_FULL_UB_REGRESSION')
            outcomes.append(dict(day=day,PASS=True,validation=proof,Native_Runtime=native,
                Native_calls=calls,UB=science['verified_UB'],initial_UB=science.get('initial_verified_UB'),
                certified_LB=science['certified_Global_LB'],certified_Gap=science['certified_gap'],
                termination=science['termination_reason'],Phase2_started=science['Phase2_started'],
                Phase2_calls=science['Phase2_calls'],actual_optimizer_calls=0,Actual_repair_calls=0,
                result=record(row['result']),evidence=proof['evidence']))
        except Exception as error:
            outcomes.append(dict(day=day,PASS=False,status='INDEPENDENT_VERIFICATION_FAILED',error=repr(error)))
    value=dict(PASS=all(v['PASS'] for v in outcomes),schema='SVR11_B2_FIRST3_USER_HANDOFF_V1',
        root=str(root),source_SHA=m['execution_SHA'],dates=outcomes,
        all124_campaign_complete=ledger.get('status')=='COMPLETE',campaign_processes_terminated=0,
        Native_optimizer_calls=0,original_results_modified=0,verifier=record(__file__),UTC=now())
    atomic(root/'B2_FIRST3_USER_HANDOFF.json',value)
    print({k:v for k,v in value.items() if k!='dates'})
    print([{k:v for k,v in row.items() if k not in ('validation','evidence')} for row in outcomes])
    return value


if __name__=='__main__':run(sys.argv[1])
