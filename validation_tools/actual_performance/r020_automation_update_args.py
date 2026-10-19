from pathlib import Path
import json,tomllib
config=tomllib.loads(Path('C:/Users/kjw39/.codex/automations/v44-may-campaign-autonomous-recovery/automation.toml').read_text(encoding='utf8'))
prefix='''최신 사용자 지시: "병목 개선해서 다음 날짜부터 적용해서 실행되게 해", "B1 B3 A2단계 모두에 적용해야 돼". 봉인 r020이 준비되었으며 현재 May02/B3/attempt003의 r019 전체 A2/M2/Actual/Fresh 및 원래 worker/coordinator가 자연 종료될 때까지 별도 r020 handover waiter가 대기한다. STOP_AUTONOMY의 R020_PHASE_I_REBUILD_PERFORMANCE_SAFE_HANDOVER_AFTER_MAY02_B3는 다음 작업 배정만 막는 승인된 전환 보류이며 현재 worker를 중단/재시작하지 않는다. 현재 r019 봉인과 원래 checkpoint 예산 승계는 유지한다. 완료 또는 기존 정책의 terminal 결과 뒤 자연 종료를 확인해야 새 coordinator가 lease를 잡는다. 알 수 없는 stop이나 사용자 stop을 덮어쓰지 않는다.

r020 적용 범위는 May03(2025-05-03) 이후 B0/B1/B3의 A stage이며 B1 A2와 B3 A2가 같은 stage-local 개선 경로를 타는 직접 검증을 포함했다. 변하지 않은 클래스 native block은 전체 정적 입력/graph bytes를 대조하고 재사용하고, 정확한 projection proof는 모든 행렬/축/계수/box/sense/RHS/descriptor/N 입력내용이 동일할 때만 재사용한다. Python 객체 공유 형태가 달라도 내용 hash가 같아야 한다. 변경된 클래스/조건은 원래 builder/검증을 재실행한다. 클래스별 변수와 descriptor의 반복 전체 탐색을 단일 순회 index로 바꾸고, 선택 후보 graph 갱신 순서는 유지하면서 전체 pool ledger만 최종 상태에서 한 번 계산한다. 각 A stage는 독립 cache이고 날짜/arm/A1-A2 사이 cache나 해/UB/LB/Native 시계가 공유되지 않는다. Solver 호출/Raw/전체 primal replay와 물리/FULL/Gap 허용오차를 생략하지 않는다. 새로운 Phase I도 처음 reference의 양의 dyadic artificial weight/sign을 유지하고 기존 inclusion guard를 보존해 과거 drift 재발을 방지한다.

R020_CHANGE_AND_VALIDATION.json, R020_SEALED.json, RECOVERY_R020_EXECUTION_PERMIT.json, R020_HANDOVER_GUARD/START/HEARTBEAT/APPLIED 및 CURRENT_HANDOFF를 확인한다. 193개 회귀 검증과 실제 A2 클래스 3개의 변경 전후 행렬/목적/descriptor/검증 일치 및 Native0 측정 PASS이다. 부분 fixture 반복 재구성 약1.75배, 변경 후보 재구성 약1.61배이며 전체 A2 속도 보장이나 전체 모델 benchmark 수치로 표현하지 않는다. 메모리 경합을 피하기 위해 전체 offline fixture 시험은 중단하고 축소 실제 클래스 검증으로 대체했다. 다음 실제 A2 OUTPUT/R020_PHASE_REBUILD_PROFILE.json과 R020_STAGE_COST_PROFILE.jsonl로 효과를 확인한다.

현재 수집기는 collect_watchdog_r020.py, source/OS 감사는 audit_active_revision_r011.py이며 활성/대기 리비전을 모두 검증한다. Windows R019 task는 Disabled, R020 task는 Ready이며 대기 프로세스가 직접 실행되어 있다. 기존 heartbeat의 PAUSED 상태/주기/대상/알림 설정은 유지하며 네이티브 supervisor는 독립적으로 실행한다. 상태가 바뀌지 않으면 조용히 유지하고 의미 있는 변화/완료/실패/사용자 조치 필요 시에만 알린다. 아래 이력과 충돌하는 리비전/수집기/후속 날짜 성능 적용 범위는 이 최신 r020 지시가 우선한다. 과거 실패 결과는 보존하고 기존 과학/예산/최종 인증 정책은 유지한다.

'''
args=dict(mode='update',id=config['id'],kind=config['kind'],name=config['name'],prompt=prefix+config['prompt'],status=config['status'],rrule=config['rrule'],targetThreadId=config['target_thread_id'])
if 'notification_policy' in config:args['notificationPolicy']=config['notification_policy']
print(json.dumps(args,ensure_ascii=False))
