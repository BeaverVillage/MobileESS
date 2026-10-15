"""Read-only source authority taxonomy; does not activate any permission."""
from pathlib import Path
import ast
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.actual_validation import read, record
from v42_integration.rc02_voltage_audit import write_new
from v42_integration.isolated_unknown import RAW, INITIAL


def source(path, names):
    path=ROOT/path
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    return dict(record=record(path),functions=[dict(name=n.name,start_line=n.lineno,end_line=n.end_lineno)
        for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names])


def main():
    out=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/VOLTAGE'
    old=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/AIDC/REPLAY02'
    frozen=read(old/'EXECUTED_SOURCE.json')['files']
    for r in frozen:
        if record(r['path'])!=r:raise ValueError('RC02_SOURCE7_DRIFT')
    initial=read(INITIAL);actual=read(RAW/'ACTUAL_INPUT_BUNDLE.json');native=read(RAW/'NATIVE_INPUT_TEMPLATE_B1.json')
    begin=initial['begin_epoch_seconds'];end=begin+16*900
    from v42_integration.current_ac_admission import epoch
    future=[r for r in actual['post_issue_arrivals'] if epoch(r['submit_time'])>=begin]
    submitted=[r for r in future if epoch(r['submit_time'])<end]
    initial_placements=read(old/'C0/INITIAL_PLACEMENT_LEDGER.json')
    result=dict(schema='RC02_PLACEMENT_AUTHORITY_READ_ONLY_V1',status='PASS_AUTHORITY_SEPARATION_NO_NEW_RIGHTS',
        evidence_scope='READ_ONLY_SOURCE_AND_EXECUTED_RC01_NOT_NEW_DISPATCH',
        raw_actual=record(RAW/'ACTUAL_INPUT_BUNDLE.json'),raw_native=record(RAW/'NATIVE_INPUT_TEMPLATE_B1.json'),
        original_initial=record(INITIAL),initial_semantic_sha=initial['common_initial_state_sha'],
        future_Unknown_UIDs=len(future),first16_Unknown_UIDs=len(submitted),
        raw_future_rows_with_explicit_preplace_field=sum('can_prestart_place' in r for r in future),
        raw_future_rows_with_data_or_WAN_preparation=sum(bool(r.get('preplacement_data')) for r in future),
        raw_future_rows_source_site_missing=sum(r.get('source_site') is None for r in future),
        native_unknown_arrival_actions=native['unknown_arrival_actions'],
        Initial=dict(authority='USER_APPROVED_EXISTING_UNKNOWN_INITIAL_COMPATIBLE_SITE_RESEARCH_MODEL',
            runtime_schema='PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1',
            basic_reference_site_only=True,sensitivity_used=False,preplace_permission_required=False,
            Strict_Source_customer_site_permission_claim=False,
            real_initial_designations=len(initial_placements),real_research_initial_designations=sum(
                r['authority']=='RESEARCH_INITIAL_PLACEMENT' for r in initial_placements)),
        Pending_PreSite=dict(status='NOT_AUTHORIZED_NO_READY_SOURCE_PROOF',
            metadata_can_prestart_place=False,
            false_is='CONSERVATIVE_ORIGINAL_ADAPTER_DEFAULT_FOR_MISSING_SOURCE_ACTION_AUTHORITY_NOT_CUSTOMER_EXPLICIT_DENIAL',
            basic_study_authority_is_not_pre_site_data_residency_or_WAN_authority=True,
            missing=['EXPLICIT_PENDING_ALTERNATE_SITE_ACTION_AUTHORITY','DESTINATION_DATA_RESIDENCY_PERMISSION',
                'OBSERVED_READY_DATA_OR_SOURCE_PAYLOAD_BANDWIDTH_WAN_PREPARATION_RECEIPT'],
            real_first16_changed_UIDs=0,
            no_source_supported_existing_permission_found_to_unblock=True,
            additional_research_assumption_activation=False,
            minimum_separate_research_contract_if_later_approved=['AUTHORIZED_DESTINATIONS_PER_SOURCE_OR_COHORT',
                'PUBLIC_DATA_LOCATION_READY_ASOF_OR_EXACT_PAYLOAD_BYTES_AND_BANDWIDTH_BYTES_PER_SECOND',
                'WAN_PATH_CAPACITY_AND_PREPARATION_TIME','ORIGINAL_QOS_HARD_WINDOWS_UNCHANGED',
                'CURRENT_GPU_RACK_ALL_PHASE_LINE_CANDIDATE_AC_AND_VALID_PUBLIC_Q50_OBJECTIVE']),
        Running_Migration=dict(status='HOLD',initial_migration_capability=None,
            no_checkpoint_or_resume_or_transfer_authority_inferred=True),
        sources=[source(Path('v42_integration/release_actual.py'),{'initial_authority','designate','_candidate','select'}),
            source(Path('v42_integration/aidc_sensitivity_runtime.py'),{'_study_site_authorized','corrective_allowed','_preparation'}),
            source(Path('v42_integration/actual_validation.py'),{'prepare_actual','_build_dday_actual_inputs'}),
            source(Path('v42_integration/dday_initialization.py'),{'_metadata'})],
        frozen_source7=frozen,Native_calls=0,AC_calls=0,code=record(__file__))
    write_new(out/'AUTHORITY_AUDIT.json',result)
    text='''# RC02 최초 배치·Pre-site·Migration 권한 감사

현재 16슬롯 Unknown 217개는 원본 입력에 고객 사이트 지정이나 Pre-site 필드가 없다. 원본 Actual 어댑터가 `can_prestart_place=False`를 부여한다. 이는 확인되지 않은 행동 권한을 보수적으로 닫은 것이며, 고객이 명시적으로 금지했다고 해석하지 않는다.

최초 배치는 이미 승인된 연구용 기본 사이트 계약이다. 같은 Reference site를 사용하며 계통 민감도로 다시 선택하지 않고, Pre-site 권한을 요구하지 않는다. RC01의 217개 기본 사이트 지정과 25개 실제 STAY 시작은 이 계약 범위이다. SourceStrict 고객 동의 인증은 아니다.

PENDING 대체 사이트 이동에는 별도의 행동 권한과 데이터 위치·목적지·관측 시각, 이미 준비된 데이터 또는 실제 payload/WAN 경로·대역폭·준비시간이 필요하다. 현재 미래 Unknown 696개에는 해당 근거가 없다. `compatible_sites`는 GPU/사이트 호환성으로, 데이터가 모든 사이트에 준비되어 있다는 뜻이 아니다. 기존 최초 배치 연구 계약에서 이를 잘못 차단한 연결부 오류는 확인되지 않았다. Pre-site 변경 0건을 유지하며 기본 사이트 실행은 계속한다.

RUNNING Migration은 체크포인트·전송·재개 근거가 없어 HOLD이다. 추가 연구용 Pre-site 가정이 필요하면 별도 Science/Policy로 승인받아야 하며 현재 활성화하지 않았다. 원본 QoS와 hard window를 연장하지 않는다.

세부 수치, 원본 파일 SHA, 함수별 근거 줄과 최소 추가 계약 항목은 `AUTHORITY_AUDIT.json`에 있다. 이 감사는 신규 실행 또는 생산 권한을 발급하지 않는다.
'''
    with (out/'AUTHORITY_AUDIT_KO.md').open('x',encoding='utf-8') as stream:stream.write(text)
    for r in frozen:
        if record(r['path'])!=r:raise ValueError('RC02_SOURCE7_DRIFT_AFTER_AUTHORITY_AUDIT')
    print(result['status'],len(future),len(submitted),len(initial_placements))


if __name__=='__main__':main()
