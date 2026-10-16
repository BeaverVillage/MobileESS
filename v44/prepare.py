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


def run(*,tests=None):
    from .inputs import manifest as inputs
    from .scheduler import manifest as scheduler
    from .science import manifest as science
    from .monitor import render
    source=science();data=inputs();schedule=scheduler()
    atomic(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json',source)
    atomic(DOC/'SEVEN_DAY_INPUT_MANIFEST.json',data)
    atomic(DOC/'CAMPAIGN_SCHEDULER_MANIFEST.json',schedule)
    blockers=[dict(day=r['day'],reasons=r['blockers']) for r in data['days'] if r['status']!='INPUT_READY']
    # Static/mock tests are evidence for adapters; they are not a current-source
    # real matrix/Actual/Fresh certification or a 7-day worker integration run.
    runtime=read(DOC/'RUNTIME_ADAPTER_COVERAGE.json') if (DOC/'RUNTIME_ADAPTER_COVERAGE.json').exists() else {}
    if runtime.get('all_stage_entrypoints_certified') is not True:
        blockers.append(dict(scope='RUNTIME',reasons=['DATED_A1_ACTUAL_DRIVER_AND_RESUME_INTEGRATION_NOT_CERTIFIED']))
    testdoc=read(tests) if tests else None
    if not testdoc or testdoc.get('failed')!=0 or testdoc.get('passed',0)==0:
        blockers.append(dict(scope='TESTS',reasons=['LIGHTWEIGHT_TEST_RECEIPT_MISSING_OR_FAILED']))
    if not source['source_PASS']:blockers.append(dict(scope='SOURCE',reasons=source['AST_drift']))
    certification=dict(schema='V44_PREEXECUTION_CERTIFICATION_V1',UTC=now(),
        status='V44_PRESTART_BLOCKED' if blockers else 'V44_PRESTART_READY',mode='PREPARE_ONLY',
        source_sha=source['source_sha'],source='PASS' if source['source_PASS'] else 'FAIL',
        inputs='PASS' if not any(r['status']!='INPUT_READY' for r in data['days']) else 'FAIL',
        date_axis='PASS',algorithm_source_identity='PASS' if source['source_PASS'] else 'FAIL',
        new_model_matrix_validation='NOT_RUN',new_physical_case_contract='NOT_CERTIFIED',
        Native_budgets='PASS_FIXTURES' if testdoc and testdoc.get('failed')==0 else 'NOT_CERTIFIED',
        Worker2_concurrency='PASS_OS_LOCK_FIXTURES' if testdoc and testdoc.get('failed')==0 else 'NOT_CERTIFIED',
        tests=testdoc,blockers=blockers,Native_optimize_calls=0,Actual_runs=0,Fresh_runs=0,
        model_builds=0,Golden003_reoptimization_calls=0,existing_results_modified=False,
        Known_policy_status='IMPLEMENTED_NOT_EXECUTED',Known_service_equivalence='NOT_CERTIFIED',
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
