"""Preserve the existing paused automation and its schedule; update revision context."""
from pathlib import Path
import json,tomllib
path=Path('C:/Users/kjw39/.codex/automations/v44-may-campaign-autonomous-recovery/automation.toml')
value=tomllib.loads(path.read_text(encoding='utf8'))
prefix='''2026-10-17 최신 사용자 지시: "응 반영해서 r017로 B3끝나면 r017로 돌아가게 해." 이 지시와 아래 r017 상태가 과거 r016 대기/적용 지시보다 우선한다. 현재 May01 B3 attempt003 Actual96와 독립 Fresh96 모두 PASS 및 정상 Worker/Coordinator 자연종료를 확인했고, 봉인한 v44_recovery_r017로 실제 전환했다. CURRENT_HANDOFF의 active_revision, 실제 OS command/생성시각, COORDINATOR_LEASE, R017_HANDOVER_APPLIED.json을 매번 먼저 읽어 최신 상태를 확인한다. 이전 r016 waiter는 전환용 STOP reason을 보고 자연종료했고 Windows R016 task는 Disabled로 보존했다. R017 task MobileESS_V44_Campaign004_Recovery_R017은 Ready이며 pythonw -X utf8 -u -m v44_recovery_r017.operations --handover, 동일한 단일 Supervisor/Coordinator/Worker 정책이다. 이미 활성화된 r017을 중복 실행하거나 완료된 B3를 재시작하지 않는다.

현재 수집기는 AUTONOMOUS_RECOVERY/collect_watchdog_r017.py, 추가 소스/OS 감사는 audit_active_revision_r008.py를 사용한다. 이전 수집기와 감사 스크립트는 역사 증거로 보존한다. 수집기는 실제 active r015/r016/r017를 따라 읽고, 일시중지 예약의 next_run_at=null을 허용한다. 기존 Codex heartbeat 예약 PAUSED 상태와 주기/대상 thread/알림 설정을 임의로 변경하지 않는다. Native Windows supervisor는 이 예약과 독립적으로 계속 실행된다. 정상 상태가 바뀌지 않으면 조용히 유지하고, 완료·실패·의미 있는 변화·사용자 조치 필요 시에만 알린다.

r017은 r016의 모든 검증된 개선을 포함하고 B0/B1/B3에 구조 개선을 추가한다. 역사 입력 전체 prefix, Arm/Day/Issue/하드웨어/Source/Scenario/MESS/Sites와 정확한 Native Tap/Cap/Queue/Time/모든 복소 버스전압/Solution counters가 일치할 때에만 역사 중간 제어 감사 증거를 재사용한다. 각 역사 슬롯 첫/마지막 전체 실시간 Controls/Ratings, 기존 외부 inventory, 모든 순차 Native SolveSnap/TIME, 현재 후보 전체 검사, 입력 변경 검사는 유지한다. 저비용 역사 슬롯은 기존 settle 경로를 사용한다. 불변 물리 결과 그래프 공유로 중복 deepcopy를 줄인다. 중간 역사 속성값을 매번 읽는 pure no-value-cache 계약과는 다르며 R017_EXECUTION_PERMIT의 명시적 Historical_audit_guard 정책을 적용한다. 불완전 native checkpoint/JSON/tap-only 상태 복원은 사용하지 않는다. 독립 Fresh는 별도 순수 live scope이며 전 노드/단자 측정과 모든 solve를 수행하고 역사·bank·이전 Current 상태 재사용은 0이다. 모델 제약/목적/허용오차/Native 예산/물리 파라미터/Raw bytes를 변경하지 않는다. B2 완료 7PASS를 보존한다.

봉인 증거: R017_CHANGE_AND_VALIDATION.json, RECOVERY_R017_EXECUTION_PERMIT.json, R017_SEALED.json, source_snapshots/r017. 회귀173 PASS, r017 패키지120슬롯 Current cold/repeat 및 독립 Fresh를 B0/B1/B3 전부 대조한9쌍 exact physics/Raw/solve counts PASS, 앞선 구조 검사23쌍 PASS. 성능은 진단120슬롯 반복 후보 검사에서 B0 약9%, B1 약5%, B3 약28% 감소였고 전체 캠페인 완주 시간 개선율로 과장하지 않는다. 최초 증거 생성 비용으로 첫 검사는 느려질 수 있다. 실제 운영 telemetry CURRENT_AC_R017_PERFORMANCE.json과 R017_STAGE_COST_PROFILE.jsonl을 확인한다. 봉인 소스/permit은 hotpatch하지 않고 새 기술 원인이 있으면 새 immutable revision으로 고친다.

아래는 이전 운영 이력과 과학 정책이며, revision/전환/도구/속성 재사용에 관해서는 위 r017 지시가 우선한다.

'''
arguments=dict(mode='update',id=value['id'],kind=value['kind'],name=value['name'],
    prompt=prefix+value['prompt'],status=value['status'],rrule=value['rrule'],targetThreadId=value['target_thread_id'])
if 'notification_policy' in value:arguments['notificationPolicy']=value['notification_policy']
print(json.dumps(arguments,ensure_ascii=False))
