from pathlib import Path
import json,tomllib
config=tomllib.loads(Path('C:/Users/kjw39/.codex/automations/v44-may-campaign-autonomous-recovery/automation.toml').read_text(encoding='utf8'))
prefix='''최신 복구 상태(2026-10-17): May02 B3는 봉인 v44_recovery_r019의 attempt003 A2에서 검증된 S14 체크포인트 다음 S15 Native 계산으로 실제 재개되었다. CURRENT_HANDOFF와 R019_CHECKPOINT_RESUME_DEPLOYED.json, R019_CHANGE_AND_VALIDATION.json, R019_SEALED.json, RECOVERY_R019_EXECUTION_PERMIT.json 및 실제 OS PID/생성시각/lease를 확인한다. 원래 attempt001의 artificial weight drift는 S14의 검증된 가중치를 유지하여 복구했다. r018 attempt002는 출력 경로 초기화 누락으로 Native 추가 소비 0초에서 중단되어 보존했으며, r019는 해당 한 줄을 수정하고 실제 S15 진입을 검증하는 직접 테스트를 포함한 180개 검증을 통과했다. r018을 다시 실행하지 않는다. 저장된 체크포인트 데이터는 checkpoint_03을 그대로 재사용하며 추가 재구성을 하지 않는다. 기존 545회 Native 호출 및 723.613000869751초를 승계해 A2 총 5400초 내에서만 계속한다. A1/M1은 검증된 원본 완료 산출물을 재사용하고 새 최적화 0회이다. 물리 제약/목적/허용오차 및 후속 M2와 Actual/Fresh의 독립 검증 정책은 유지한다.

현재 수집기는 collect_watchdog_r019.py, 감사는 audit_active_revision_r010.py이다. Windows Recovery_R017/R018 task는 Disabled이며 Recovery_R019 task와 단일 supervisor/coordinator/worker가 운용된다. Codex heartbeat의 기존 PAUSED 상태/주기/대상/알림 설정은 유지한다. 아래 이력의 리비전/attempt/수집기 선택은 이 최신 r019 상태가 우선한다.

'''
args=dict(mode='update',id=config['id'],kind=config['kind'],name=config['name'],prompt=prefix+config['prompt'],status=config['status'],rrule=config['rrule'],targetThreadId=config['target_thread_id'])
if 'notification_policy' in config:args['notificationPolicy']=config['notification_policy']
print(json.dumps(args,ensure_ascii=False))
