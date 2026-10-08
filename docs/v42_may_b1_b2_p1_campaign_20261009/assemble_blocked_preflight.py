"""Assemble truthful Native=0 preflight evidence, without launching a campaign."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import json
import shutil
import subprocess
import hashlib

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RUNTIME = ROOT / 'runtime/v42_may_b1_b2_p1_campaign/scheduler_preflight_20261009'
BASE = 'dc15114d450c25394ff174cc0c65056aae40778f'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if ROOT.drive.upper() != 'D:':
        raise ValueError('D_DRIVE_REQUIRED')
    # This is an assembler for this observed snapshot, not a future campaign
    # preflight runner. Refuse to republish stale constant claims on new inputs.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    remote = subprocess.check_output(['git', 'rev-parse', 'origin/v42'], cwd=ROOT).decode().strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT).decode().strip()
    if head != BASE or remote != BASE or branch != 'v42':
        raise ValueError('THIS_ONE_OFF_EVIDENCE_ASSEMBLER_REQUIRES_THE_AUDITED_BASE_HEAD')
    regression = read(OUT / 'REGRESSION_SUMMARY.json')
    infrastructure = read(RUNTIME / 'INFRASTRUCTURE_REGRESSION.json')
    if not regression['PASS'] or not infrastructure['PASS']:
        raise ValueError('REGRESSION_FAILURE_MUST_REMAIN_VISIBLE')
    audits = ('A_STAGE_REUSE_AUDIT.json', 'M_STAGE_REUSE_AUDIT.json',
              'B2_INDEPENDENT_AIDC_GENERATION.json', 'MAY31_INPUT_IDENTITY.json',
              'ORCHESTRATION_REUSE_AUDIT.json', 'WINDOWS_EXISTING_TASK_PROCESS_SNAPSHOT.json')
    for name in audits:
        read(OUT / name)
    probes = [read(p) for p in sorted(RUNTIME.glob('*S4U*.json'))]
    if not probes or any(p['PASS'] or p['registered'] or p['started'] for p in probes):
        raise ValueError('THIS_REPORT_REQUIRES_OBSERVED_UNREGISTERED_S4U_BLOCK')
    if (len(probes) != 2 or any('0x80070005' not in p.get('fully_qualified_error_id', '') for p in probes)
            or (regression['passed'], regression['skipped'], regression['failed']) != (680, 12, 0)
            or infrastructure['tests'] != 12):
        raise ValueError('THIS_ONE_OFF_REPORT_MUST_MATCH_ITS_OBSERVED_PROBE_AND_REGRESSION_COUNTS')
    for p in sorted(RUNTIME.glob('*S4U*.json')):
        shutil.copyfile(p, OUT / p.name)
    shutil.copyfile(RUNTIME / 'INFRASTRUCTURE_REGRESSION.json', OUT / 'EXISTING_INFRASTRUCTURE_REGRESSION.json')
    now = datetime.now(timezone.utc).isoformat()
    common = dict(preflight_id='b1_b2_p1_preflight_20261009', campaign_run_id=None,
                  campaign_started=False, Native_optimize_calls=0, UTC=now)
    entries = [dict(ordinal=i + 1, arm=arm, day=f'2025-05-{day:02d}',
                    state='NOT_STARTED', input_generated=False, case_SHA=None)
               for i, (arm, day) in enumerate((arm, day) for arm in ('B1', 'B2') for day in range(1, 32))]
    policy = dict(**common, status='DRAFT_NOT_ACTIVATED', objectives=['min rho_max'],
        B1=dict(AIDC_optimization=True, MESS_optimization=False, MESS_P=0, MESS_Q=0, target_Global_Gap_percent=0.5),
        B2=dict(AIDC_optimization=False, MESS_optimization=True, vehicles=4, sites=24, slots=96,
                fixed_AIDC_rule='V42_COMMON_FCFS_Q50_NOMINAL_RELEASE_V2',
                AIDC_input_source='Own same-day raw input; independent common reference producer',
                B0_or_B1_schedule_reads_allowed=False, target_Global_Gap_percent=3.0),
        P2_calls_allowed=0, B3_runs_allowed=0, Threads=1,
        per_arm_date_wall_ceiling_seconds=5400, per_arm_date_Native_ceiling_seconds=5400,
        model_generation_certification_and_replay_in_wall=True,
        Fresh_AC_separately_measured=True, scientific_algorithms_changed=False,
        terminal_date_retries=0, failures_continue_to_next_date=True,
        B2_requires_all_B1_dates_terminal=True, simultaneous_Native_workers=1,
        Global_MILP_Actual=0, Local_P_repair=0, Local_Q_repair=0,
        execution_enforcement_status='NOT_IMPLEMENTED_NOT_TESTED',
        system_power_policy_changed=False)
    write('B1_B2_POLICY_DEFINITION.json', policy)
    write('CAMPAIGN_PREREGISTRATION.json', dict(**common, status='DRAFT_NOT_ACTIVATED',
        scientific_base_HEAD=BASE, branch='v42', repository='BeaverVillage/MobileESS',
        order='B1 2025-05-01..31 then B2 2025-05-01..31',
        planned_arm_dates=entries, planned_arm_date_count=62, activated_arm_date_count=0,
        preregistration_frozen=False, new_campaign_source_SHA=None, new_campaign_case_SHA=None,
        mandatory_preflight_PASS=False, runtime_root=str(RUNTIME), policy_file='B1_B2_POLICY_DEFINITION.json'))
    checks = [
        dict(check='LATEST_V42_HEAD', status='PASS', observed=BASE),
        dict(check='EXISTING_ALGORITHM_REUSE_PATHS', status='AUDITED', evidence=list(audits[:2])),
        dict(check='B1_A_STAGE_P1_DATE_CONNECTION', status='NOT_IMPLEMENTED'),
        dict(check='B2_M_STAGE_P1_DATE_CONNECTION', status='NOT_IMPLEMENTED'),
        dict(check='B2_INDEPENDENT_AIDC_GENERATION', status='NOT_EXECUTED'),
        dict(check='MAY31_HISTORICAL_INPUT_IDENTITY', status='PASS_EXISTING_INPUTS_ONLY',
             evidence='MAY31_INPUT_IDENTITY.json'),
        dict(check='NEW_DATE_ROUTE_GRID_PCC_JOB_AXIS', status='NOT_TESTED'),
        dict(check='NEW_DATE_ORIGINAL_P1_PHYSICAL_CONTRACT_EQUIVALENCE', status='NOT_TESTED'),
        dict(check='NEW_DATE_INDEPENDENT_GLOBAL_LB_UB_CERTIFIERS', status='NOT_TESTED'),
        dict(check='NEW_DATE_90_MINUTE_BUDGET', status='POLICY_ONLY_NOT_IMPLEMENTED'),
        dict(check='NEW_62_AXIS_CHECKPOINT_AND_ZERO_RETRY', status='NOT_IMPLEMENTED'),
        dict(check='NONINTERACTIVE_WINDOWS_TASK_INSTALL', status='FAIL', error='HRESULT 0x80070005'),
        dict(check='NEW_MONITOR_HTTP_AND_UI', status='NOT_STARTED'),
        dict(check='B1_COMPLETE_BEFORE_B2_ENFORCEMENT', status='POLICY_ONLY_NOT_IMPLEMENTED'),
        dict(check='EXISTING_COMMON_REGRESSION', status='PASS', passed=680, skipped=12, failed=0),
        dict(check='EXISTING_INFRASTRUCTURE_REGRESSION', status='PASS', tests=12,
             limitation='Historical 31-date/3600-second/two-infra-retry policy; does not validate requested new policy'),
    ]
    write('PREFLIGHT_ZERO_NATIVE.json', dict(**common, PASS=False,
        state='BLOCKED_OS_SCHEDULER_AND_UNIMPLEMENTED_DATE_CONNECTIONS', checks=checks,
        regression_PASS_does_not_imply_campaign_preflight_PASS=True))
    write('WINDOWS_TASK_STATUS.json', dict(**common, PASS=False,
        requested_roles=['Coordinator', 'Monitor', 'Watchdog'], campaign_tasks_registered=[],
        task_registration_error='HRESULT 0x80070005, Register-ScheduledTask: 액세스가 거부되었습니다.',
        attempts=probes, existing_tasks_changed=False, existing_processes_stopped=False,
        interactive_fallback_used=False, Codex_owned_solver_started=False,
        logoff_persistence_proven=False, OS_owned_new_process_ancestry_proven=False))
    write('MONITOR_STARTUP_CHECK.json', dict(**common, PASS=False, status='NOT_STARTED',
        URL=None, HTTP_tested=False, UI_tested=False, old_monitor_unchanged=True,
        old_monitor_is_not_new_campaign_monitor=True))
    write('CAMPAIGN_STATUS.json', dict(**common, status='NOT_STARTED_PREFLIGHT_BLOCKED',
        current_phase=None, current_day=None, Coordinator_PID=None, Worker_PID=None,
        Monitor_PID=None, Watchdog_PID=None, Monitor_URL=None,
        completed_arm_dates=0, B1_completed=0, B2_completed=0,
        PASS=0, TIMEOUT=0, FAIL=0, arm_date_observations=0, dates=entries,
        independent_continuation_available=False, resume_command=None,
        blocker='Noninteractive Scheduler installation failed 0x80070005; date adapters remain unimplemented'))
    write('EXISTING_ALGORITHM_REUSE_AUDIT.json', dict(**common,
        status='READ_ONLY_AUDIT_COMPLETED_IMPLEMENTATION_PENDING',
        algorithms_reimplemented=False, algorithms_modified=False, adapters_implemented=False,
        audits=[dict(path=name, sha256=sha(OUT / name)) for name in audits],
        existing_regression=regression, existing_infrastructure=infrastructure,
        new_date_equivalence_proof_available=False, new_B2_AIDC_optimizer_zero_proof_available=False))
    fields = {
        'DATE_ARM_RESULTS.csv': ['day', 'arm', 'status', 'incumbent_valid', 'P1_certified', 'case_SHA', 'result_SHA'],
        'DATE_ARM_RUNTIME.csv': ['day', 'arm', 'wall_seconds', 'Native_Runtime_seconds', 'Fresh_AC_seconds', 'Native_calls'],
        'DATE_ARM_GAP.csv': ['day', 'arm', 'UB', 'Native_BestBd', 'independent_Global_LB', 'Certified_Gap_percent', 'target_Gap_percent'],
        'DATE_ARM_DDAY_AC.csv': ['day', 'arm', 'Fresh_AC_status', 'Planning_max_line_loading', 'Fresh_AC_max_line_loading', 'voltage_violations', 'current_violations'],
        'FAILURE_LEDGER.csv': ['day', 'arm', 'classification', 'error', 'UTC', 'evidence_SHA'],
    }
    for name, headers in fields.items():
        with (OUT / name).open('w', encoding='utf-8', newline='') as stream:
            csv.writer(stream, lineterminator='\n').writerow(headers)
    write('PREFLIGHT_FAILURES.json', dict(**common, failures=[dict(
        classification='OS_TASK_SCHEDULER_ACCESS_DENIED', code='0x80070005',
        arm_date_failure=False, scientific_infeasibility=False, date_solver_timeout=False,
        evidence='WINDOWS_TASK_STATUS.json')]))
    report = '''# V42 B1→B2 5월 P1 캠페인 Preflight 검토

2026-10-09 KST 최종 상태: **미기동 / Preflight 실패**. 실행 캠페인 Run ID는 생성하지 않았다. 식별자는 감사용 `b1_b2_p1_preflight_20261009`다. Native optimize 0회, 완료 arm/date 0개다.

Windows에서 로그오프 지속 실행을 위한 S4U 예약 작업 등록을 실제로 2회 시도했으나 `Register-ScheduledTask`, **HRESULT 0x80070005 / 액세스가 거부되었습니다**로 실패했다. 현재 토큰은 관리자 역할이 아니다. Coordinator·Monitor·Watchdog 신규 작업은 등록되지 않았으며, 첫 May01 B1 Worker도 생성되지 않았다. InteractiveToken으로 대체해 전체 PASS를 주장하지 않았다.

## 검증된 내용

- `v42` 로컬·원격 최신 과학적 기준 HEAD: `dc15114d450c25394ff174cc0c65056aae40778f`.
- 기존 공통 Native=0 회귀: **680 PASS / 12 SKIP / 0 FAIL**. SKIP은 PASS가 아니다.
- 기존 infrastructure 회귀: **12 PASS**. 이 검사는 기존 31일/3600초/infra 2회 재시도 정책에 대한 것으로, 요청된 새 62개 축/5400초/실패 무반복 정책 검증은 아니다.
- 과거 May31 입력 31일 전체와 연결된 283개 파일의 SHA·크기를 실측 검증했으며 누락·불일치 0개다. 새 B1/B2 독립 입력이나 새 case 인증으로 간주하지 않는다.
- 기존 소스 1,117개 및 D runtime ledger 5개의 SHA를 회귀 전후 비교해 변경 0개를 확인했다. 추가 A/M·orchestration 감사에도 원본 SHA를 기록했다.
- 기존 알고리즘·과학적 결과·Native ledger를 변경하지 않았다. 기존 Task Scheduler 작업, 옛 read-only monitor PID 41292와 port 8791을 유지했다.

## 아직 완료되지 않은 실행 연결

A-stage는 기존 complete pricing, 원본 정수형 복구, original physical checker, exact LB를 재사용할 수 있다. 다만 May12/3~4일 전용 경로, class count, scientific permit과 날짜당 예산을 최소 adapter로 연결해야 한다. 과거 four-objective runner 및 P2를 호출하면 요청 범위를 벗어난다. 기존 launch 차단은 보존했다.

M-stage의 기존 adaptive primal–dual/role-exchange LNS와 exact LB 구현도 보존했다. 상위 loader·warm start·columns·case SHA·변수 개수·projection rows는 May01에 고정되어 있어 직접 월간 B2에 사용할 수 없다. 원본 FULL→compact→hybrid 조립의 하부 API를 날짜별 원본 입력에 연결하고 P1만 전달하는 adapter와 동치성 검증이 필요하다. 과거 May01 UB/LB/정수해를 다른 날짜 인증으로 사용하지 않았다.

B2는 `v42_capacity.reference.build_reference`의 기존 FCFS/Q50 nominal-release V2 규칙을 자기 원본 입력에서 독립 호출할 경로를 찾았다. 실제 입력 생성은 0일이다. 감사 중 AIDC optimizer 호출 0회를 실제 B2 Worker의 무최적화 실행 증거로 주장하지 않는다.

## 정책과 산출물 상태

사전 정책 초안은 B1 31일 후 B2 31일, Threads=1, P2=0, 날짜당 Wall/Native 각각 5400초, 실패 날짜 무반복 후 다음 날짜 진행, B1 gap 0.5%·B2 gap 3%를 기록한다. 이를 강제하는 신규 wrapper는 구현·검증하지 않았다. `CAMPAIGN_PREREGISTRATION.json`의 62개 항목은 계획 축이며 실행 등록이나 관측 결과가 아니다.

`DATE_ARM_*.csv`와 `FAILURE_LEDGER.csv`에는 열 머리글만 있다. arm/date 실행·실패·시간·gap·Fresh AC 관측 결과가 없기 때문이다. 예약 작업 실패는 `PREFLIGHT_FAILURES.json`에 별도로 기록했다. Monitor URL·Coordinator/Worker PID·heartbeat·OS 부모 관계 증거·checkpoint 재개 명령은 없다. 모니터·Publisher·무인 AI·반복 감시도 시작하지 않았다.

모든 새 파일은 `D:\\MobileESS_v42\\docs\\v42_may_b1_b2_p1_campaign_20261009\\`에, 임시 파일과 전체 회귀 로그는 `D:\\MobileESS_v42\\runtime\\v42_may_b1_b2_p1_campaign\\scheduler_preflight_20261009\\`에 저장했다. live runtime은 Git에 넣지 않는다.

## 다음 확인 명령

상태 확인:

```powershell
Get-Content -Raw 'D:\\MobileESS_v42\\docs\\v42_may_b1_b2_p1_campaign_20261009\\CAMPAIGN_STATUS.json'
```

권한을 갖춘 PowerShell에서 S4U **등록 가능성만** 다시 점검할 수 있다. 아래 명령은 solver·캠페인을 시작하거나 재개하지 않으며, 성공해도 나머지 Preflight를 대체하지 않는다.

```powershell
pwsh -NoProfile -File 'D:\\MobileESS_v42\\docs\\v42_may_b1_b2_p1_campaign_20261009\\Invoke-SchedulerPreflight.ps1'
```

캠페인 재개 명령은 없다. OS 등록 문제를 해소하고 날짜 adapter·독립 인증·새 wrapper·monitor를 구현한 뒤 전체 Native=0 Preflight를 통과해야 최초 실행이 가능하다. 시스템 절전·최대절전·종료 중 계산 지속을 주장하지 않았고 전원 정책을 변경하지 않았다.

기존 [PR189](https://github.com/BeaverVillage/MobileESS/pull/189)에 감사·차단 증거를 반영한다. 이 문서는 정상 독립 실행 인계 또는 성공한 캠페인 보고가 아니다.
'''
    (OUT / 'FINAL_REVIEW_KO.md').write_text(report, encoding='utf-8')
    manifest = {p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*'))
                if p.is_file() and p.name != 'SHA256_MANIFEST.json'}
    write('SHA256_MANIFEST.json', dict(scope='This new preflight evidence directory; self excluded',
        campaign_preflight_PASS=False, files=manifest, existing_science_preserved=True))
    print('BLOCKED_PREFLIGHT_EVIDENCE_WRITTEN', len(manifest), 'files; Native=0; campaign not started')


if __name__ == '__main__':
    main()
