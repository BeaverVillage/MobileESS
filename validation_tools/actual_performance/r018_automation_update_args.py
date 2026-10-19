from pathlib import Path
import json,tomllib
config=tomllib.loads(Path('C:/Users/kjw39/.codex/automations/v44-may-campaign-autonomous-recovery/automation.toml').read_text(encoding='utf8'))
prefix='''최신 사용자 지시: "왜 5월 2일 B3 실패했어? 해결해서 체크포인트부터 재개해". 이 지시와 아래 r018 체크포인트 예외가 과거의 r017 전환 및 무조건 fresh A-stage 설명보다 우선한다. CURRENT_HANDOFF/실제 OS command·생성시각/COORDINATOR_LEASE/봉인 permit을 매번 확인한다. May02 B3 attempt001은 2026-10-17 20:38 KST A2 Phase I 후보 확장 뒤 PRIOR_WITNESS_FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT 구현 오류로 중단됐으며, 수학적 infeasibility나 Actual 물리 FAIL 증명이 아니다. 원래 실패 결과/Raw/545회 Native 기록은 보존한다.

복구는 별도 봉인 v44_recovery_r018의 May02 B3 attempt002에서만 a2_checkpoint_parent를 사용한다. 저장 초기 상태·완료 후보·S14 Raw를 Native0으로 재구성하고 저장된 S14 행렬/objective/축 fingerprint, primal/dual sign replay를 정확히 대조했다. S14 후 보조 REMAINING_PRICE에 저장된 마지막 후보를 포함해, 원래 inclusion_witness와 exact Phi 보존 검사를 통과한 상태에서 S15부터 이어간다. 기존 S14의 양의 dyadic artificial weights/signs를 새 후보에도 고정하며 원래 부호·이전 해 포함·원본 전 제약 검사와 3회 정체 규칙 및 zero tolerance를 우회하지 않는다. 이전 원본 P1 rho 목적/물리/정수성/독립 A2 Gap .005 조건은 동일하다. 이는 B&B 탐색 트리나 Actual native Tap/Queue 이어붙이기가 아니다.

A2 Native 예산은 기존 723.613000869751초를 승계하여 총5400초 중 잔여4676.386999130249초부터 시작한다. NATIVE_RUNTIME_LEDGER의 checkpoint_resume/inherited_Native_seconds/parent_ledger/Native_clock_reset=false/calls 합계를 확인한다. 새 시간으로 초기화하지 않는다. 동일 날짜 A1과 완료 M1은 signed completed-stage checkpoint 및 plan SHA 검증 후 재사용하며 새 A1/M1 최적화는 0회이다. A2가 독립 FULL/.5% Gap을 통과해야 새 M2, 이후 Actual/Fresh를 진행한다. M2는 아직 실행되지 않은 최초 단계이므로 원래 독립 K48 300/Joint900 및 단일호출300 예산을 적용한다. 일반 M 재시도 정책은 변경되지 않는다.

r018은 r017의 기존 B0/B1/B3 Current/Fresh 성능 개선을 모두 유지한다. 실행 중 봉인 코드 hotpatch, 제약/목적/허용오차/Native 예산 완화, 이전 M UB/LB를 새 독립 인증으로 승격하는 행위를 금지한다. 과거 실패는 삭제/덮어쓰지 않는다. 과학적 물리 FAIL이나 동일 실패를 근거 없이 반복하지 않는다. 새 기술 원인이 있으면 별도 수정·검증·불변 revision으로만 복구한다.

현재 수집기는 AUTONOMOUS_RECOVERY/collect_watchdog_r018.py, 소스/OS 감사는 audit_active_revision_r009.py이다. R018_CHANGE_AND_VALIDATION.json, R018_SEALED.json, RECOVERY_R018_EXECUTION_PERMIT.json, R018_HANDOVER_APPLIED.json과 CHECKPOINT_RESUME_ADMISSION.json/A2/OUTPUT/A2_CHECKPOINT_RESTORATION.json을 확인한다. Windows R017 task는 Disabled로 보존하고 R018 task/single supervisor·coordinator·worker가 복구 우선 처리 뒤 기존 순차 queue를 이어간다. Codex heartbeat의 기존 PAUSED 상태와 주기/대상 thread/알림 설정은 변경하지 않는다. 네이티브 supervisor는 이 예약과 독립적이다. 모니터는 새 A2 실행에서 이전 Native와 누적 경과를 명시적으로 표시하며 Source/원장은 수정하지 않는다. 상태가 그대로이면 조용히 유지하고 의미 있는 변화·완료·실패·사용자 조치 필요 시에만 알린다.

아래는 이전 운영 이력과 원래 과학 정책이다. 리비전/복구/예산 재개/수집기 선택에 관해서는 위 최신 r018 지시가 우선하며, 나머지 원래 과학·예산·fail-continue·최종 인증/PR 절차는 유지한다.

'''
args=dict(mode='update',id=config['id'],kind=config['kind'],name=config['name'],prompt=prefix+config['prompt'],
    status=config['status'],rrule=config['rrule'],targetThreadId=config['target_thread_id'])
if 'notification_policy' in config:args['notificationPolicy']=config['notification_policy']
print(json.dumps(args,ensure_ascii=False))
