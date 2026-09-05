"""Seal post-integration evidence. Never launch or optimize a day."""
from pathlib import Path
import json
import sys

WORK=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(WORK));sys.dont_write_bytecode=True
from dayahead.tools import integrate_v39k_fallback as k


def main():
    root=k.LIVE/k.REL
    before=k.read(k.ROOT/'V39K_PREINTEGRATION_LIVE_SNAPSHOT.json')
    receipt=k.read(root/'V39K_HOLD_RELEASE_RECEIPT.json')
    assert receipt['status']=='PASS'
    current=k.verify_live(before)
    gate=k.read(k.LIVE/k.GATE)
    assert all(gate['dates'][d]['release'] for d in k.DAYS)
    assert k.sha(k.LIVE/k.GATE)==receipt['after_gate_SHA256']
    ready=k.read(root/'V39K_31DAY_READINESS.json');assert ready['READY']==31 and ready['NOT_READY']==ready['MISSING']==0
    authority=k.read(root/'V39K_PRODUCTION_INTEGRATION_AUTHORITY.json')
    assert authority['GUROBI_THREADS_PER_MODEL']==authority['MAX_PARALLEL_DAY_WORKERS']==4
    ps=k.processes();workers=[r for r in ps if 'day' in r]
    parents=[r['ProcessId'] for r in ps if 'run_v39h_production_close.py' in r['CommandLine']]
    monitors=[r['ProcessId'] for r in ps if 'monitor_v39e_may_campaign.ps1' in r['CommandLine']]
    actual_before_monitors=[r['ProcessId'] for r in before['processes'] if k.is_monitor_process(r)]
    assert parents==before['orchestrator_PID'] and monitors==actual_before_monitors
    k.save(root/'V39K_PROCESS_INVENTORY_CORRECTION.json',dict(status='PASS',raw_preintegration_snapshot_preserved=True,
        raw_monitor_PID_field=before['monitor_PID'],verified_actual_monitor_PID=actual_before_monitors,
        excluded_query_helper_PIDs=[p for p in before['monitor_PID'] if p not in actual_before_monitors],
        reason='Initial substring query also matched its own PowerShell -Command helper. Actual monitor requires -File monitor_v39e_may_campaign.ps1. No monitor restart occurred.'))
    assert len({r['day'] for r in workers})==len(workers)
    statuses={p.stem:k.read(p) for p in (k.LIVE/k.FULL/'status').glob('*.json')}
    completed=sorted(d for d,v in statuses.items() if v.get('status')=='PASS')
    failed=sorted(d for d,v in statuses.items() if v.get('status')=='FAIL')
    history=k.read(root/'V39K_HISTORICAL_PROVENANCE_PRESERVATION.json')
    for raw,item in history['authorities'].items():
        p=Path(raw);assert k.sha(p)==item['manifest_SHA256']
        assert all(k.sha(p.parent/name)==s for name,s in item['files'].items())
    backup=k.read(root/'V39K_REPLACEMENT_BACKUP_MANIFEST.json')
    assert all(k.sha(root/'before_integration'/rel)==s for rel,s in backup.items())
    protected=k.protected_check(before)
    post=dict(LIVE_ROOT=str(k.LIVE),LIVE_HEAD=k.git('rev-parse','HEAD'),LIVE_BRANCH=k.git('branch','--show-current'),captured_at=k.now(),
        accepted_production_source_fingerprint=k.source_fingerprint(k.LIVE)[1],common_source_byte_identical=True,
        processes=ps,orchestrator_PID=parents,monitor_PID=monitors,active_workers=workers,completed_dates=completed,
        running_dates=[r['day'] for r in workers],HOLD_dates=[],failed_dates=failed,all_124_DA_freeze_SHA256=current,
        May23_26_authority_SHA256={k.fname(d,c):current[k.fname(d,c)] for d in k.DAYS for c in k.CASES},
        protected_result_SHA256=before['protected_result_SHA256'],protected_files_reverified=protected,
        launch_gate_SHA256=k.sha(k.LIVE/k.GATE),production_refreeze_authority_SHA256=k.sha(k.LIVE/k.CLOSE/'PRODUCTION_REFREEZE_AUTHORITY.json'),
        certified_production_fallback_migrations=105,MAX_PARALLEL_DAY_WORKERS=4,GUROBI_THREADS_PER_MODEL=4,
        V39K_process_stop_calls=0,V39K_process_start_calls=0,invalid_Actual_output_present_before_release=False)
    k.save(root/'V39K_POSTINTEGRATION_LIVE_SNAPSHOT.json',post)
    impact=k.read(root/'V39K_CHANGE_IMPACT_AUDIT.json')
    impact.update(verification_phase='LIVE_POST_RELEASE',protected_results_verified=protected,common_production_source_byte_identical=True,
        live_manifest_exact_changed_set=sorted(k.check_changed_cases(before['all_124_DA_freeze_SHA256'],current)),
        historical_sealed_artifacts_preserved=True,all_before_replacement_records_archived_byte_identical=True)
    k.save(root/'V39K_CHANGE_IMPACT_AUDIT.json',impact)
    tests=k.read(root/'V39K_TEST_REPORT.json')
    tests.update(live_loader_verification='124/124_PASS',native_resume_cheap_readiness='31/31_PASS',dynamic_live_gate='FOUR_HOLDS_BEFORE_FOUR_RELEASES_AFTER',
        duplicate_date_workers=0,protected_results_unchanged=protected,completed_date_rerun_calls=0,common_source_changes=0,
        historical_sealed_files_unchanged=True,monitor_PID_retained=monitors,orchestrator_PID_retained=parents)
    k.save(root/'V39K_TEST_REPORT.json',tests)
    status=dict(V39K_LIVE_INTEGRATION_COMPLETE='YES',MAY17_TEMPORAL_REPAIR_RETAINED='YES',
        CERTIFIED_PRODUCTION_FALLBACK_MIGRATIONS=105,MIGRATION_REDUCTION_FROM_BASELINE_105=0,
        EXPECTED_CHANGED_DAY_CASES=8,ACTUAL_CHANGED_DAY_CASES=8,UNEXPECTED_CHANGED_DAY_CASES=0,
        CHANGE_IMPACT_SOLVER_CALLS=0,PRIMARY_OPTIMIZATION_RERUN=0,MIGRATION_MILP_RERUN=0,FULL_13DAY_RERUN='NO',FULL_31DAY_OPTIMIZATION_RERUN='NO',
        READY='31/31',NOT_READY=0,MISSING=0,INVALID_ACTUAL_OUTPUT_PRESENT='NO',LIVE_ORCHESTRATOR_RESTARTED='NO',
        UNRELATED_RUNNING_WORKERS_STOPPED=0,UNRELATED_COMPLETED_DATES_RERUN=0,LIVE_COMMON_PRODUCTION_SOURCE_CHANGED='NO',
        MAY_CAMPAIGN_CONTINUES='YES',push='NO',PR='NO',GLOBAL_MINIMUM_UNDER_NEW_TERMINAL_FORMULATION_CLAIM='NO')
    for day in k.DAYS:
        prefix='MAY'+day[-2:]
        status.update({prefix+'_V39H_REPAIR_REJECTED':'YES',prefix+'_FALLBACK_MIGRATIONS':k.COUNTS[day],prefix+'_SELECTIVE_PREFLIGHT':'PASS',prefix+'_RELEASE':'YES'})
    k.save(root/'V39K_FINAL_STATUS.json',status)
    lines='\n'.join(f'{key} = {value}' for key,value in status.items())
    rows=[]
    for d in k.DAYS:
        cert=k.read(root/'days'/d/'V39K_FALLBACK_CERTIFICATE.json')
        rows.append(f"| {d} | {k.COUNTS[d]} | PASS | {cert['grid']['Vmax']:.12f} | {cert['grid']['Vmin']:.12f} | RELEASE |")
    review=f'''# V39K certified fallback live integration

May23–26 B1/B3의 기존 terminal-inconsistent V39H witness를 원본 base RSP와 기존 exact minimum migration witness로 복원했다. Live 통합, 네 날짜 선택 검증, 31일 readiness 및 동적 HOLD 해제를 완료했다.

| 날짜 | 기존 인증 migration | 선택 검증 | Vmax | Vmin | Gate |
|---|---:|---|---:|---:|---|
{chr(10).join(rows)}

현재 production fallback migration 합계는 **105회**다. 기존 8개 migration 날짜의 76회에 May23=4, May24=2, May25=8, May26=15를 더했다. 원래 105 대비 감소는 0이다. 이는 기존 solver-proven witness를 재사용한 fallback 구성의 합계이며, 새 terminal-consistent formulation에서 global minimum을 재최적화했다는 주장이 아니다. May23의 가능한 모든 대체 temporal repair가 infeasible하다는 주장도 하지 않는다.

## 변경 범위와 authority

실제 DA freeze 변경은 정확히 8개다. 다른 116개는 byte-identical이며 B0/B2와 May17 repair도 그대로다. 각 변경 decision에서 원본 pre-refreeze의 모든 기존 scientific field가 정확히 같음을 검사했다. 일정 일부를 고치거나 새로운 migration plan을 만든 적이 없다.

새 provenance는 기존 loader의 `temporal_repair_authority` 호환 key에 저장했다. 이 key는 `TEMPORAL_REPAIR_USED=false`와 V39K fallback certificate 및 원본 V37 RSP schedule을 가리킨다. 기존 V39H repair schedule/objective에 대한 실행 의존성은 없다. 따라서 scientific payload는 원본과 정확히 같지만, provenance가 추가된 전체 decision/file SHA는 원본과 다르다.

새 authoritative record는 `V39K_PRODUCTION_INTEGRATION_AUTHORITY.json`이다. 기존 production refreeze entrypoint는 동일한 새 내용을 제공하도록 갱신해 현재 loader와 향후 cheap resume/readiness 경로를 유지했다. 교체한 모든 기존 current record의 원래 bytes는 `before_integration/` 아래 보존했고 SHA를 재검증했다. V39H 76, V39J 101, May23 targeted audit의 sealed 역사 자료는 그대로이며 새 V39K authority가 현재 production을 supersede한다.

월간 GPU/IT/PCC trajectory 파일은 해당 8개 slice만 변경했고 나머지 116개 slice는 정확히 같음을 확인했다. Migration accounting, identity/fixed-replay audit, preflight 및 production authority를 일치시켰다. 이전 V39H per-day certificate와 historical migration-reuse report는 보존하며, 새 authority는 V39K per-day certificate를 참조한다.

## 검증

네 날짜 모두 원본 base RSP SHA, 전체 migration witness, 개수 4/2/8/15, site capacity, Rack compatibility, gang indivisibility, planning voltage/current/transformer/inner polygon, C1/PCC, WAN fixed path, payload, checkpoint/READY/restart를 solver 없이 검증했다. C1 P/Q는 같은 날짜의 frozen weather와 기존 C1 model로 별도 확인했다. 전체 runtime/GPU/일정 보존, common RW-anchored initial state, 새 RW completion violation 없음도 확인했다.

각 fallback은 원본 fallback 대비 repair-induced incremental post-H GPU-h, terminal reservation profile 변경, terminal site state 변경이 모두 0이다. 기존 baseline migration 자체를 0회라고 표현하지 않는다. 평가는 inter-day independent / intra-day stateful이고 물리 grid 검증 구간은 issue slots [24,120)이다. Post-H 물리 grid authority나 연속 multi-day carry를 만들지 않았다.

Staged loader 124개와 live loader 124개가 검증됐다. 기존 production `load_ready_refreeze` 경로도 실제로 호출하여 READY 31/31, NOT_READY=0, MISSING=0을 확인했다. 호출한 것은 authority/readiness assembly뿐이며 최적화 함수는 호출하지 않았다. 테스트 {tests['pytest_tests']}개와 별도 monitor regression checks가 통과했다. 의도적인 canonical tamper, 예상 밖 authority 변경 및 gate authority 누락은 fail-closed임을 확인했다.

Actual/Fresh 결과는 DA 구성에 사용하지 않았다. 사전/사후 보존 단계에서는 사용자가 요청한 완료 결과 SHA만 검증했다. May23–26의 invalid Actual 결과나 checkpoint가 release 전에 없었음을 확인했다. 따라서 새 fallback authority로 day-entry하며 이전 잘못된 Actual checkpoint에서 resume하지 않는다.

## Live 연속성

사전 완료 날짜 {len(before['completed_dates'])}개의 보호 파일 **{protected}개**가 SHA·크기·mtime까지 그대로다. 공통 production source와 admission source 모두 V39K 시작 시점 bytes와 같다. 공통 과학 소스 fingerprint는 `{before['accepted_production_source_fingerprint']}`이다. V39J formulation 소스의 공통 live 통합은 별도 source-refreeze 작업으로 남겨뒀다.

Orchestrator PID {parents}, monitor PID {monitors}가 유지된다. 현재 완료 날짜는 {len(completed)}/31, 실행 날짜는 {', '.join(r['day'] for r in workers)}, 실패 날짜 수는 {len(failed)}다. 같은 날짜의 중복 worker는 없다. Worker 한도 4, 활성 model당 Gurobi thread 4를 유지한다. V39K가 worker를 시작·중단·재시작하거나 완료 날짜를 rerun한 횟수는 0이다.

사전 raw process snapshot의 monitor PID 목록에는 조회 명령 자체의 PowerShell PID가 추가 집계돼 있었다. 원본 snapshot은 보존하고, 실제 `-File ...monitor_v39e_may_campaign.ps1` 실행만 분류한 정정 기록을 `V39K_PROCESS_INVENTORY_CORRECTION.json`에 남겼다. 실제 monitor는 시작/종료되지 않았다.

Gate는 네 선택 preflight PASS, live change-impact PASS, live readiness PASS 뒤 마지막에 해제했다. Release 당시 held worker 수는 {len(receipt['held_workers_before'])}개였다. 기존 worker entry는 runtime/Actual 전 gate를 10초마다 읽는다. 네 날짜는 기존 queue 순서와 빈 worker slot에 따라 자연스럽게 진입한다. Monitor를 재시작하지 않았고 PASS 완료 행 숨김, FAIL 유지 및 stage/substage/progress 표시를 확인했다.

기존 orchestrator의 시작 시점 progress 객체에는 과거 frozen-DA migration 합계 76이 캐시되어 있을 수 있다. 이를 외부에서 덮어쓰거나 process를 재시작하지 않았다. 현재 판단 authority와 월간 accounting은 105이며, 기존 final report writer는 갱신된 migration audit를 읽는다. 단순 live monitor는 그 캐시 합계를 표시하지 않는다.

## 최종 상태

```text
{lines}
```
'''
    (root/'V39K_FINAL_REVIEW.md').write_text(review,encoding='utf-8')
    required=['V39K_PREINTEGRATION_LIVE_SNAPSHOT.json','V39K_FALLBACK_AUTHORITY_MANIFEST.json','V39K_CHANGED_DAY_CASES.csv','V39K_SELECTIVE_PREFLIGHT_SUMMARY.json',
        'V39K_CHANGE_IMPACT_AUDIT.json','V39K_31DAY_READINESS.json','V39K_HOLD_RELEASE_RECEIPT.json','V39K_POSTINTEGRATION_LIVE_SNAPSHOT.json',
        'V39K_TEST_REPORT.json','V39K_FINAL_REVIEW.md','V39K_FINAL_STATUS.json','V39K_PRODUCTION_INTEGRATION_AUTHORITY.json','V39K_PROCESS_INVENTORY_CORRECTION.json']
    required += [f'days/{d}/V39K_FALLBACK_CERTIFICATE.json' for d in k.DAYS]
    k.save(root/'V39K_REQUIRED_ARTIFACT_SHA_MANIFEST.json',dict(status='PASS',SHA256={n:k.sha(root/n) for n in required},
        integration_script_SHA256=k.sha(WORK/'dayahead/tools/integrate_v39k_fallback.py'),finalizer_SHA256=k.sha(__file__)))
    for n in required+['V39K_REQUIRED_ARTIFACT_SHA_MANIFEST.json']:
        k.copy_atomic(root/n,k.ROOT/'final_live_evidence'/n)
    print(lines,flush=True)


if __name__=='__main__':main()
