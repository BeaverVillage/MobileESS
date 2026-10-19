from pathlib import Path
import json,tomllib
config=tomllib.loads(Path('C:/Users/kjw39/.codex/automations/v44-may-campaign-autonomous-recovery/automation.toml').read_text(encoding='utf8'))
prefix="""최신 사용자 지시(2026-10-17): Phase I 오류를 해결하고 안정화·속도 개선 후 May02 B3 A2를 처음부터 다시 실행하라고 했다. Native 시간은 사용자가 추가로 \"M1 완료 시점 기준, 새 A2는 0초부터\"라고 명확히 지정했다. 이 지시가 과거 r019 A2 체크포인트/기존 A2 Native 승계 및 r020 May03 전환 대기보다 우선한다.

기존 r019 May02/B3/attempt003은 사용자 승인으로 Native inflight가 없는 경계에서 중단했다. 725회 호출/1214.5379996299744초는 원장과 USER_INTERRUPTION 및 R021_CURRENT_A2_STOPPED.json에 별도로 보존했다. 원장·실패/중단 이력을 덮어쓰지 않는다. 미실행 봉인 r020은 보존하되 Windows R020 task를 Disabled로 바꾸고 pending을 취소했다.

현재 봉인 v44_recovery_r021의 May02/B3/attempt004가 fresh_a2_parent=attempt001의 signed 완료 M1과 검증된 A1만 재사용하여 새 A2를 S0부터 재구성/실행한다. 이전 A2 해/풀/Native 시간은 가져오지 않는다. A2 Native는 새 원장 0초 시작/한도5400초이며 기존 시간은 이력으로만 표시한다. M1 plan SHA는 원본과 일치해야 한다. M2는 아직 이전에 실행되지 않았으므로 새 A2가 독립 FULL/Gap 조건을 통과한 뒤 최초 M2를 원래 K48 300/Joint900/호출300 정책으로 실행한다. M1/M2/Actual/Fresh의 제약·허용오차/독립 검증을 유지한다.

r021은 r020 exact class-block/projection-proof reuse, 단일 순회 class index, batch pool ledger와 기존 Actual/Fresh 개선을 유지한다. 두 B1/B3 A2 모두 안정화 경로를 쓰며 May02 B3 새 A2도 포함한다. LP는 원본 matrix/objective/허용오차를 보존하고 robust simplex Method1 NumericFocus3 ScaleFlag2 Aggregate0 Presolve1 LPWarmStart2를 적용한다. 현재 동일 A2 내 확장 뒤 독립 재검증된 이전 feasible point만 PStart로 넘긴다. 이전 원장/다른 날짜의 해는 넘기지 않는다. Raw primal/dual/sign과 이전 feasible Phi dominance를 검사하고 실패하면 동일 Native 예산에서 정해진 Method0 Quad1 MarkowitzTol0.5 복구 한 번만 허용한다. 모든 호출 시간을 원래 Native 원장에 합산한다. 여전히 검증 실패하면 중단하고 과학적 불가능이나 정상 수렴으로 포장하지 않는다. 이전 해로 Raw solver 결과를 대체하거나 작은 Phi를 표시만 하는 것은 금지한다. 원래 3회 정체 규칙과 1e-8 zero/1e-6 primal 및 기존 Gap 조건을 보존한다.

R021_CHANGE_AND_VALIDATION.json/R021_SEALED.json/RECOVERY_R021_EXECUTION_PERMIT.json/R021_HANDOVER_APPLIED.json/FRESH_A2_RESTART_ADMISSION.json과 실제 OS command/PID/생성시각/lease를 확인한다. 203개 회귀 검증과 별도 소형 leased Native smoke가 PASS이며 소형 smoke 시간은 새 production A2에 합산하지 않는다. 전체 실제 모델 안정화 성공은 아직 실행 결과로 검증해야 하며 미리 PASS로 주장하지 않는다. 각 solve의 R021_NUMERICAL_POLICY.json/R021_NUMERICAL_ACCEPTANCE.json 및 A2 OUTPUT/R021_PHASE_REBUILD_PROFILE.json을 확인한다.

현재 수집기는 collect_watchdog_r021.py, 감사는 audit_active_revision_r012.py이다. Windows R019/R020은 Disabled, R021 task와 단일 supervisor/coordinator/worker로 실행한다. 기존 Codex heartbeat의 PAUSED 상태·주기·대상 thread·알림 설정은 유지한다. 네이티브 supervisor는 독립적이다. 변화가 없으면 조용히 유지하고 의미 있는 변화/완료/실패/사용자 조치 필요 시에만 알린다. 아래 이력 중 충돌하는 리비전/복구/예산 시작점/수집기 설명보다 이 최신 r021 지시가 우선하며 나머지 과학/최종 검증 정책을 유지한다.

"""
args=dict(mode='update',id=config['id'],kind=config['kind'],name=config['name'],prompt=prefix+config['prompt'],status=config['status'],rrule=config['rrule'],targetThreadId=config['target_thread_id'])
if 'notification_policy' in config:args['notificationPolicy']=config['notification_policy']
print(json.dumps(args,ensure_ascii=False))
