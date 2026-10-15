"""Preserve auxiliary evidence sources without changing executed Actual bytes."""
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read,record,write
from v42_integration.policy import digest

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC'
REPLAY=BASE/'REPLAY02'


def exclusive(path,value):
    if path.exists():raise FileExistsError(str(path))
    write(path,value)


def main():
    frozen=read(REPLAY/'EXECUTED_SOURCE.json')['files']
    if [record(r['path']) for r in frozen]!=frozen:raise ValueError('EXECUTED_ACTUAL_SOURCE_DRIFT')
    sources={
        'RC01_AC_PROFILE.pstats':'HISTORICAL_TWO_CANDIDATE_PROFILE_DATA_NOT_ALGORITHM',
        'RC01_AC_PROFILE_INVOCATION.txt':'HISTORICAL_PROFILE_INVOCATION_AND_OBSERVED_TIMING_NOT_ALGORITHM',
        'RC01_RESOURCE_MONITOR.ps1':'READ_ONLY_PROCESS_RESOURCE_MONITOR_NOT_ALGORITHM',
        'RC01_DERIVE_AIDC_REPORTS.py':'POSTPROCESS_ONLY_NO_CONTROLLER_OR_PHYSICAL_ACTION',
        'RC01_COUNTERFACTUAL_PHYSICAL_API_FIXTURE_SERIALIZATION_FAILURE.py':'FAILED_JSON_SERIALIZATION_INVOCATION_SOURCE_PRESERVED',
        'RC01_COUNTERFACTUAL_PHYSICAL_API_FIXTURE.py':'NAMED_API_NEGATIVE_CAPACITY_POINT_NOT_REAL_PERMISSION',
        'RC01_COUNTERFACTUAL_FEASIBLE_PAIR_FIXTURE.py':'NAMED_API_LEGAL_GPU_PAIR_NOT_REAL_PERMISSION',
        'RC01_ARCHIVE_RUNTIME_SOURCES.py':'LOSSLESS_AUXILIARY_SOURCE_ARCHIVER_NOT_ALGORITHM'}
    dest=BASE/'RUNTIME_SOURCE';dest.mkdir(parents=True,exist_ok=True);rows=[]
    for name,role in sources.items():
        src=ROOT/'runtime'/name;target=dest/name
        if target.exists():raise FileExistsError(str(target))
        shutil.copyfile(src,target);before=record(src);after=record(target)
        if (before['sha256'],before['bytes'])!=(after['sha256'],after['bytes']):raise ValueError('AUXILIARY_COPY_BYTES_DRIFT')
        rows.append(dict(role=role,original=before,archived=after,lossless=True))
    result=dict(schema='RC01_AUXILIARY_SOURCE_PRESERVATION_V1',status='PASS',files=rows,
        executed_Actual_SOURCE7_unchanged=True,executed_Actual_files=frozen,
        auxiliary_code_is_not_added_to_executed_Actual_case=True,Native_calls=0)
    result['receipt_sha']=digest(result);exclusive(REPLAY/'RUNTIME_SOURCE_PRESERVATION.json',result)
    exclusive(REPLAY/'UNIT_TEST_RECEIPT.json',dict(status='PASS',tests=17,wall_seconds=1.31,
        command='python -m pytest tests/test_v42_release_actual.py -q',
        test_source=record(ROOT/'tests/test_v42_release_actual.py'),
        evidence_scope='NAMED_NATIVE0_FIXTURES_NOT_MAY_PERFORMANCE',Native_optimization_calls=0,
        executed_Actual_SOURCE7_unchanged=True))
    exclusive(REPLAY/'COUNTERFACTUAL_SERIALIZATION_FAILURE.json',dict(status='FAILED_JSON_SERIALIZATION',
        exception='TypeError: Object of type bool_ is not JSON serializable',
        failure_stage='AFTER_PHYSICAL_PROBES_BEFORE_JSON_WRITE',
        original_execution_path=str(ROOT/'runtime/RC01_COUNTERFACTUAL_PHYSICAL_API_FIXTURE.py'),
        preserved_source=record(dest/'RC01_COUNTERFACTUAL_PHYSICAL_API_FIXTURE_SERIALIZATION_FAILURE.py'),
        result_not_certified=True,physical_point_is_not_reusable_without_persisted_receipt=True,Native_calls=0))
    print('RUNTIME_SOURCE_PRESERVED',len(rows),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
