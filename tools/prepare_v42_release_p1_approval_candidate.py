"""Prepare concrete unapproved May01 P1 plans; no model/cache load or solve."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.a_engine import digest
from v42_integration.m_engine import file_record,_write
from v42_integration.release_p1_acceptance import saved_a1,read
from v42_integration.release_production_campaign import production_sources,preflight

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
OUT=BASE/'RC02/PRODUCTION/APPROVAL_CANDIDATE_V4'


def run():
    if OUT.exists():raise FileExistsError('APPROVAL_CANDIDATE_EXISTS_APPEND_NEW_VERSION')
    policy_path=BASE/'RC03/RELEASE_POLICY_CANDIDATE.json'
    policy=read(policy_path);policy_sha=digest(policy);policy_record=file_record(policy_path)
    saved=saved_a1();source=saved['manifest'];authority=dict(day='2025-05-01',source_sha=source['source_sha'],source_identity=source['identity'])
    m=read(BASE/'RC02/PRODUCTION/M1_CURRENT_FACTORY_NATIVE0.json');packet=m['runtime_packet']
    path=Path(packet['path'])
    if not path.is_file() or path.stat().st_size!=packet['bytes']:
        raise ValueError('LOCAL_NATIVE0_CURRENT_M1_PACKET_REQUIRED')
    # Reuse the independently measured receipt; do not scan/load the 2.13GB
    # packet again while preparing a human review. Runtime restore rehashes it.
    if (m['source_identity']!=source['identity'] or m['source_sha']!=source['source_sha']
            or m['parent_acceptance_sha']!=saved['acceptance']['acceptance_sha']):
        raise ValueError('CURRENT_M1_CACHED_SOURCE_PARENT_RECEIPT_DRIFT')
    root=BASE/'RC02/DATE_CASES/COMPILE01'
    compiled=read(root/'2025-05-01/CASE/D0_CASE_MANIFEST.json')
    if compiled!=source:raise ValueError('COMPILED_MAY01_MUST_EQUAL_SAVED_SUCCESSFUL_A1_CASE')
    r1=read(BASE/'RC03/CAMPAIGN_R1_CONTRACTS/MAY31_R1_CONTRACT_PREPARATION.json')
    policies=r1['actual_policy_by_day']
    if len(policies)!=31:raise ValueError('DATE_EXACT_R1_POLICY_PREPARATION_REQUIRED')
    plan=dict(schema='REAL_PRODUCTION_P1_CAMPAIGN_PLAN_V1',dates=['2025-05-01'],Worker=1,Threads=1,P2_calls=0,
        automatic_start=False,execution_scope='PLANNING_P1_ONLY',policy_sha=policy_sha,policy_record=policy_record,
        source_snapshot=production_sources(),compiled_case_root=str(root),prepared_M1_packet=packet,
        Actual_policy_by_day=policies,actual_policy_mapping_receipt=file_record(BASE/'RC03/CAMPAIGN_R1_CONTRACTS/MAY31_R1_CONTRACT_PREPARATION.json'),
        imported_May01_A1=saved['acceptance'],saved_A1_immutable_records=saved['immutable_records'])
    approval=dict(schema='RELEASE_PRODUCTION_P1_SEPARATE_AUTHORIZATION_V1',approved=False,
        scope='NEW_RELEASE_P1_ONLY_HEAVY',authorization_id='UNAPPROVED_MAY01_PLANNING_P1_CANDIDATE_V4_20261015',
        authorized_ledger_path=str(BASE/'RC02/BUDGET/MAY01_PLANNING_P1_V4_APPROVED_ONLY_LEDGER.json'),
        human_approval_reference=None,policy_sha=policy_sha,Worker=1,Threads=1,P2_calls=0,
        stage_cap_scope='PER_DATE_STAGE',stage_caps_seconds=dict(M1=180.,A2=120.,M2=180.),
        return_reserve_seconds=30.,overshoot_buffer_seconds=60.,limit_seconds=570.,
        authorized_date_cases=[authority],allowed_stage_bindings=[],policy_record=policy_record,
        proposal_is_approval=False,old_RC01_unused_runtime_is_downstream_authority=False)
    follow=dict(approval,authorization_id='UNAPPROVED_MAY01_K48_FOLLOWUP_CANDIDATE_V4_20261015',
        authorized_ledger_path=str(BASE/'RC02/BUDGET/MAY01_K48_FOLLOWUP_V4_APPROVED_ONLY_LEDGER.json'),
        stage_caps_seconds=dict(K48_M2=180.),limit_seconds=270.,
        requires_completed_planning_checkpoint_and_read_only_consumed_ledger=True,
        current_case_K48_inclusion_and_executor='NOT_CERTIFIED',
        submit_only_after_current_packet_independent_inclusion_proof=True)
    OUT.mkdir(parents=True)
    _write(OUT/'UNAPPROVED_MAY01_PLAN.json',plan)
    _write(OUT/'UNAPPROVED_PLANNING_570_APPROVAL.json',approval)
    _write(OUT/'UNAPPROVED_K48_LATER_270_PROPOSAL.json',follow)
    ready=preflight(plan,approval,{},planning_only=True)
    if ready['blockers']!=['NEW_EXPLICIT_STAGE_BUDGET_APPROVAL_REQUIRED_RC01_REMAINDER_FORBIDDEN']:
        raise ValueError('PLANNING_CANDIDATE_HAS_ADDITIONAL_SOURCE_OR_WIRING_BLOCKERS:'+str(ready['blockers']))
    _write(OUT/'EXACT_REVIEW_BINDING.json',dict(status='CONCRETE_UNAPPROVED_PLANNING_CANDIDATE',
        policy_sha=policy_sha,policy_record=policy_record,source_case=authority,
        plan=file_record(OUT/'UNAPPROVED_MAY01_PLAN.json'),approval=file_record(OUT/'UNAPPROVED_PLANNING_570_APPROVAL.json'),
        followup_proposal=file_record(OUT/'UNAPPROVED_K48_LATER_270_PROPOSAL.json'),readiness=ready,
        local_runtime_packet=packet,large_packet_rehashed_or_loaded_this_preparation=False,
        large_packet_hash_recheck_required_before_future_restore=True,
        Native_calls=0,native_model_builds=0,Actual_runs=0,AC_solves=0,P2_calls=0,
        no_New_Native_authorization_created=True,old_canonical_or_RC01_ledgers_modified=False,
        two_separate_requested_limits_sum=840,requested_limits_are_not_measured_runtime_predictions=True,
        preparation_tool=file_record(__file__)))
    q=lambda p:'"'+str(p)+'"'
    command='python -B -X utf8 '+q(ROOT/'tools/run_v42_production_campaign.py')+' --planning-only --plan '+q(OUT/'UNAPPROVED_MAY01_PLAN.json')+' --approval '+q(OUT/'UNAPPROVED_PLANNING_570_APPROVAL.json')
    (OUT/'REVIEW_AND_EXECUTION_KO.md').write_text(
        '이 후보는 현재 성공 A1·독립 May01 D0 manifest·측정된 현재 M1 캐시 receipt·실제 executor Source bytes·안정된 RC03 정책 hash에 직접 묶여 있다. approved=false이며 Native 권한은 없다. 기본 검토 CLI는 Source/Case/정책을 검사하고 실행하지 않는다.\n\n'
        '```powershell\n'+command+'\n```\n\n'
        '별도 명시 승인을 받은 뒤에만 같은 검토 파일의 승인 상태와 실제 human approval reference를 채워야 한다. 승인 파일은 하나의 새 원장 경로/authorization_id에 결합된다. 실행에는 --execute --output <새체크포인트폴더> --budget-ledger <승인에결합된원장경로>가 추가로 필요하다. 이번 준비에서 이 명령을 실행하지 않았다.\n\n'
        '첫 요청 상한은 Planning 570초(cap480+반환30+overshoot60)이며 A1을 반복하지 않고 M1→A2→M2까지만 수행한다. 각 단계 Original FULL이 없으면 다음 단계로 갈 수 없다. 이후 K48 현재 Case packet 포함성 인증 뒤 별도270초를 검토한다. 현재 K48 packet/executor가 미인증이므로 후속270초 제안도 승인 요청 전 단계다. 기존750초 문서는 역사 안으로 보존하고 현재 두 원장 흐름에 쓰지 않는다.\n\n'
        '2.13GB 캐시는 여기서 다시 읽거나 hash하지 않았다. 기존 Native0 측정 receipt를 재사용했으며 실제 복원 시 RAM admission, packet bytes 재hash, 원본 Source/Case/Domain proof 검증이 필수다. R1 31일 정책 mapping은 준비 자료이며 Actual96/Fresh96 또는 31일 실행 인증이 아니다.\n',encoding='utf-8')
    print(json.dumps(dict(status='PREPARED_UNAPPROVED_SOURCE_BOUND_PLANNING_CANDIDATE',
        policy_sha=policy_sha,Native_calls=0,P2_calls=0,folder=str(OUT)),indent=2))


if __name__=='__main__':run()
