"""Offline manifests and explicit prepare-only entry point."""
import argparse
from pathlib import Path
from .common import DOC,atomic,read,record,verify,NotReady,digest,now


def require_execution_permit(path,certification):
    if path is None:raise PermissionError('SEPARATE_EXPLICIT_USER_EXECUTION_PERMIT_REQUIRED')
    permit=read(path)
    if certification['status']!='V44_PRESTART_READY':raise NotReady('V44_PRESTART_BLOCKED')
    if (permit.get('explicit_user_approved') is not True or permit.get('mode')!='EXECUTE'
            or permit.get('source_sha')!=certification['source_sha']
            or permit.get('days')!=list(__import__('v44.config',fromlist=['DAYS']).DAYS)
            or permit.get('certification_sha')!=digest(certification)):
        raise PermissionError('V44_PERMIT_SOURCE_DATE_CERTIFICATION_MISMATCH')
    return permit


def prestart_evidence():
    """Check required evidence once before dispatch, outside the campaign."""
    from .svr12 import DIRECTORY,HARDWARE,certificate
    receipts=[]
    for name in ('PLANNING_MATRIX_EQUIVALENCE.json','REFERENCE_C_RAW_REPLAY.json',
            'ACTUAL_ENTRYPOINT_CERTIFICATION.json'):
        row=record(DIRECTORY/name);value=read(row['path'])
        if value.get('PASS') is not True:raise NotReady('PRESTART_EVIDENCE_FAILED:'+name)
        verify(value.get('sources',[]));receipts.append(row)
    matrix=read(receipts[0]['path']);canary=read(receipts[2]['path'])
    if (matrix['Native_calls']!=0 or matrix['RegControl_count']!=7 or matrix['added_SVR']!=0
            or len(matrix['comparisons'])!=2 or not all(r['PASS'] for r in matrix['comparisons'])
            or canary['Native_calls']!=0 or canary['control_slots']!=1
            or canary['independent_Current_Fresh_prefix_slots']!=25):
        raise NotReady('PRESTART_PLANNING_OR_SHORT_CANARY_SCOPE_DRIFT')
    certificate(DIRECTORY/'CURRENT_AC_CERTIFICATION.json')
    h=read(HARDWARE/'HARDWARE.json');verify([h['scenario'],h['thermal']]+list(h['sources'].values()))
    if (h['SVR_count'],h['RegControl_count'])!=(12,43):raise NotReady('PRESTART_SVR12_INVENTORY_DRIFT')
    verify([canary['pair'],canary['B1_canary']])
    pair=read(canary['pair']['path'])
    if not pair['PASS'] or not pair['midnight_continuity']['PASS'] or pair['Fresh_native_state_reused']:
        raise NotReady('PRESTART_CURRENT_FRESH_STATE_ISOLATION_FAILED')
    return receipts


def run(*,tests=None):
    from .inputs import manifest as inputs
    from .scheduler import manifest as scheduler
    from .science import manifest as science
    from .monitor import render
    source=science();data=inputs();schedule=scheduler()
    atomic(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json',source)
    atomic(DOC/'SEVEN_DAY_INPUT_MANIFEST.json',data)
    atomic(DOC/'CAMPAIGN_SCHEDULER_MANIFEST.json',schedule)
    from .initial_states import READY_INPUT_STATES
    blockers=[dict(day=r['day'],reasons=r['blockers']) for r in data['days'] if r['status'] not in READY_INPUT_STATES]
    evidence=prestart_evidence()
    testdoc=read(tests) if tests else None
    if not testdoc or testdoc.get('failed')!=0 or testdoc.get('passed',0)==0:
        blockers.append(dict(scope='TESTS',reasons=['LIGHTWEIGHT_TEST_RECEIPT_MISSING_OR_FAILED']))
    if not source['source_PASS']:blockers.append(dict(scope='SOURCE',reasons=source['AST_drift']))
    certification=dict(schema='V44_PREEXECUTION_CERTIFICATION_V1',UTC=now(),
        status='V44_PRESTART_BLOCKED' if blockers else 'V44_PRESTART_READY',mode='PREPARE_ONLY',
        source_sha=source['source_sha'],source='PASS' if source['source_PASS'] else 'FAIL',
        inputs='PASS' if not any(r['status'] not in READY_INPUT_STATES for r in data['days']) else 'FAIL',
        date_axis='PASS',algorithm_source_identity='PASS' if source['source_PASS'] else 'FAIL',
        revision=source['revision'],prestart_evidence=evidence,
        new_model_matrix_validation='MAY01_V43_FULL_C3A_EXACT_PASS',
        new_physical_case_contract='SVR12_EXACT_EQUIPMENT_AND_SHORT_CURRENT_FRESH_ENTRY_PASS',
        Native_budgets='PASS_FIXTURES' if testdoc and testdoc.get('failed')==0 else 'NOT_CERTIFIED',
        Worker2_concurrency='PASS_OS_LOCK_FIXTURES' if testdoc and testdoc.get('failed')==0 else 'NOT_CERTIFIED',
        tests=testdoc,blockers=blockers,Native_optimize_calls=0,Actual96_runs=0,Fresh96_runs=0,
        real_B1_entry_canary_slots=1,independent_Current_Fresh_prefix_slots=25,
        model_builds=1,Golden003_reoptimization_calls=0,existing_results_modified=False,
        Known_policy_status='SHORT_PREFIX_ONLY_FULL_ACTUAL_NOT_CERTIFIED',Known_service_equivalence='NOT_CERTIFIED',
        full_28_case_runtime_PASS_claimed=False,
        FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',execution_permit_created=False)
    atomic(DOC/'PREEXECUTION_CERTIFICATION.json',certification)
    (DOC/'MONITOR.html').write_text(render(data),encoding='utf8')
    return certification


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--permit',type=Path)
    parser.add_argument('--resume',type=Path);parser.add_argument('--tests',type=Path)
    args=parser.parse_args()
    if not args.execute:
        cert=run(tests=args.tests)
        print(dict(status=cert['status'],mode='PREPARE_ONLY',Native_calls=0,Actual_runs=0,Fresh_runs=0));return
    cert=read(DOC/'PREEXECUTION_CERTIFICATION.json');require_execution_permit(args.permit,cert)
    from .campaign import run as campaign
    campaign(args.resume or __import__('v44.common',fromlist=['RUNTIME']).RUNTIME/'campaign001',args.permit,resume=bool(args.resume))


if __name__=='__main__':main()
