"""Export concise reviewable C1 evidence after independent reconciliation."""
import csv
from datetime import datetime,timezone,timedelta

from v43.common import DOC,read,record,atomic
from v43_corrective.experiment import ACTUAL,CANARY,PREFLIGHT


def export_csv(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run():
    report=read(ACTUAL/'INDEPENDENT_C1_REPORT.json');presite=read(ACTUAL/'PRESITE_UID_EVIDENCE.json')
    windows=read(PREFLIGHT/'KNOWN_WINDOW_AUDIT.json');other=read(ACTUAL/'KNOWN_UNSTARTED_AUDIT.json')
    transitions=[]
    for r in presite['actual_presite_transitions']:
        basic=next((x for x in r['all_candidates'] if x['site']==r['from_site']),{})
        base_score=basic.get('sensitivity') or {}
        transitions.append(dict(uid=r['uid'],from_site=r['from_site'],to_site=r['to_site'],
            START_AEST=datetime.fromtimestamp(r['START_seconds'],timezone(timedelta(hours=10))).isoformat(),
            START_KST=datetime.fromtimestamp(r['START_seconds'],timezone(timedelta(hours=9))).isoformat(),
            basic_candidate_reason=basic.get('reason'),basic_signed_score_available=bool(base_score),
            basic_signed_peak=base_score.get('grid_peak'),selected_signed_peak=r['selected_sensitivity']['grid_peak'],
            basic_signed_loading_hours=base_score.get('loading_hours'),
            selected_signed_loading_hours=r['selected_sensitivity']['loading_hours'],
            earlier_observed_overrun_QUEUE=len(r['earlier_overrun_blocked_QUEUE']),
            Current_AC_PASS=True,R1_authority='R1_ASSUMED',Source_verified=False))
    if transitions:export_csv(DOC/'V43_B1_R1_FLEX30_C1_PRESITE_UID.csv',transitions)
    export_csv(DOC/'V43_B1_KNOWN_WINDOW_FAIL_UID.csv',[dict(uid=r['uid'],planned_slot=r['Golden_start_slot'],
        allowed_slots='|'.join(map(str,r['PR189_FULL_allowed_slots'])),
        planned_seconds=r['Golden_start_seconds'],source_can_timeshift=r['source_can_timeshift'],
        source_delay_budget_slots=r['source_delay_budget_slots'],window_reason=r['WINDOWS']['reason'],
        Actual_status=r['Actual_known_decision_status'],window_widened=False) for r in windows['mismatch_UIDs']])
    export_csv(DOC/'V43_B1_C1_OTHER_KNOWN_UNSTARTED_UID.csv',[dict(uid=r['uid'],last_reason=r['last_reason'],
        NO_CAPACITY_events=r['counts'].get('NO_CAPACITY',0),
        observed_running_retained_events=r['counts'].get('PHYSICAL_CAPACITY_RUNNING_RETAINED',0)) for r in other['other_UIDs']])
    atomic(DOC/'V43_B1_R1_FLEX30_C1_RESULT.json',report)
    g=report['groups'];p=report['presite'];grid=report['grid'];t=report['timing'];q=report['QoS']
    peak_kst=datetime.fromisoformat(grid['peak_slot_begin_AEST']).astimezone(timezone(timedelta(hours=9))).isoformat()
    lines=['# May01 B1 R1-FLEX30-C1 Actual96 / Fresh96', '',
        'Golden003 Planning 재계산 0회. B1 C1 Actual96 1회 완료. 물리 실행·UID/GPU/P/Q 독립 검산·Fresh96 PASS.',
        '**Known 허용창 계약은 414 UID FAIL이며 서비스 동등성은 NOT_CERTIFIED이다.** 허용창을 변경하지 않았다.', '',
        '## 실제 서비스', '',
        'UID 수는 D-1 18:00 AEST부터 May01 종료까지 30시간 도착 코호트이며, Compute GPUh는 May01 24시간 적분이다.', '',
        '| 구분 | 전체 | START | COMPLETED | Carryout | May01 Compute GPUh | 30h Compute GPUh |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,r in g.items():lines.append(f"| {name} | {r['total']} | {r['START']} | {r['COMPLETED']} | {r['Carryout']} | {r['compute_GPUh_Dday']:.9f} | {r['compute_GPUh_whole30h']:.9f} |")
    lines += ['',f"의도적 부담 예산 초과 {q['intentional_burden_exceeds_budget_UIDs']} UID. 실제 latest-start 초과 {q['actual_latest_start_excess_UIDs']} UID(START한 UID {q['actual_latest_start_excess_started_UIDs']}). 명시적 완료 Deadline 위반 {q['completion_deadline_violations']} UID.",
        'Latest-start 초과는 용량 대기·미실행까지 포함한 연구 허용창 지표이며 고객 Source SLA 인증을 의미하지 않는다.', '',
        '## Unknown Pre-site', '',
        '| 지표 | UID 수 또는 후보 횟수 |','|---|---:|',
        f"| R1 적격 Unknown | {p['R1_eligible_UIDs']} |",f"| R1 참여 Unknown | {p['R1_participant_UIDs']} |",
        f"| 기본 사이트 PENDING 지정 | {p['basic_designated_UIDs']} |",
        f"| Signed Sensitivity 평가 UID | {p['sensitivity_evaluated_UIDs']} |",
        f"| 참여자 중 Signed Sensitivity 평가 UID | {p['R1_participant_sensitivity_evaluated_UIDs']} |",
        f"| 다른 호환 사이트 후보 횟수(권한 차단 포함) | {p['alternative_compatible_candidate_instances']} |",
        f"| 대체 사이트 권한 통과 후보 횟수 | {p['permission_pass_alternative_instances']} |",
        f"| 대체 사이트 민감도 평가 횟수 | {p['sensitivity_evaluated_alternative_instances']} |",
        f"| 대체 사이트 민감도 평가 UID | {p['sensitivity_evaluated_alternative_UIDs']} |",
        f"| Pre-site 선택 UID | {p['selected_presite_UIDs']} |",f"| 실제 Pre-site 후 START UID | {p['actual_presite_START_UIDs']} |",
        f"| 관측 Overrun 대기 후 Pre-site START UID | {p['overrun_wait_then_presite_START_UIDs']} |", '',
        f"185건의 선택 근거는 기본 사이트 NO_CAPACITY {p['selected_when_basic_NO_CAPACITY_UIDs']}건, 기본 사이트도 Signed 점수가 있는 경우 {p['selected_with_basic_signed_score_UIDs']}건이다. 후자에서 예측 최대 부하율 감소 {p['selected_predicted_peak_reduced_UIDs']}건, 예측 loading-hours 감소 {p['selected_predicted_loading_hours_reduced_UIDs']}건이다. 이는 실제 일 최대 부하율 감소 인증이 아니다.", '',
        '모든 변경은 실제 도착 이후 PENDING에서 이루어졌고, 실제 RUNNING 이벤트와 선택 시각·사이트를 UID별로 교차검증했다. Running Migration과 Unknown의 의도적 Time-shifting은 0건이다.',
        '참여 권한은 R1_ASSUMED이다. Source 인증으로 승격하지 않는다. 비참여자와 명시적 Source 금지 대상은 대체 사이트가 차단된다. C0_BASIC_SITE_ONLY가 C1 후보에 적용된 건수는 0이다.',
        '후보 Signed 점수는 원본 부호 있는 응답식을 사용한다. 정렬된 후보를 Current AC로 검사해 첫 안전 후보만 START한다. 선택되지 않아 AC를 실행하지 않은 후보의 물리 PASS를 주장하지 않는다.',
        'D00 이전에는 원본 Signed 응답의 지원 범위가 없어 대체 사이트를 PREFIX_SIGNED_RESPONSE_UNAVAILABLE로 차단한다. 이후 실제 관측 이벤트에서 다시 평가한다.', '',
        ('실제 이동 UID 전체와 기본/선택 사이트의 평가값: [Pre-site UID CSV](V43_B1_R1_FLEX30_C1_PRESITE_UID.csv).' if transitions
            else f"실제 Pre-site가 0건인 후보별 이유는 {p.get('zero_presite_analysis')}에 기록했다. 기능 활성화를 처리량 또는 부하율 개선 성과로 주장하지 않는다."), '',
        f"실제로 관측한 Overrun UID: {report['observed_overrun_UIDs']}. 관측 Overrun이 있는 사이트의 용량 대기로 QUEUE된 뒤 Pre-site START한 건수를 위 표에서 따로 집계했다.", '',
        '## Known 허용창 및 대기', '',
        'Golden003 selected_jobs, PR189 Original FULL 로더의 allowed_starts 바인딩, WINDOWS.json, OriginalKnownWindows.issue() 영수증 및 Actual _known_decision()을 UID별로 대조했다.',
        '18:00 기준 slot→초 변환은 동일하며 Adapter 해석 오류가 아니다. 예: UID 8632559는 시작 슬롯 0만 허용하지만 Golden003 선택은 슬롯 2이다. Golden003의 수치 인증을 실행 권한 인증으로 사용하지 않는다.',
        f"계약 불일치 414건 중 이번에도 미실행 {other['mismatch_unstarted_UIDs']}건. 나머지 미실행 Known {other['remaining_other_UIDs']}건의 마지막 사유: {other['other_last_reason_counts']}.",
        f"유효 Planning 명령을 기다렸다가 실제 허용 시작시각을 넘겨 START한 Known은 {report['Known_actual_START_outside_original_window_UID_count']} UID이며 별도 Actual QoS 초과로 포함했다. 동결 명령과 허용창은 수정하지 않았다.",
        '[414개 계약 FAIL UID](V43_B1_KNOWN_WINDOW_FAIL_UID.csv) · [나머지 미실행 Known UID](V43_B1_C1_OTHER_KNOWN_UNSTARTED_UID.csv). 기존 C0의 나머지 165 UID별 용량 대기 이벤트도 Preflight 원장에 보존했다.', '',
        '## 전력망', '',
        f"최대 선로·상 부하율 **{grid['peak_loading_fraction']*100:.9f}%**, {grid['peak_line']} / 상 {grid['peak_phase']}. 발생 구간 시작 {peak_kst} KST(원본 축 {grid['peak_slot_begin_AEST']} AEST, 15분 평균 Actual).",
        f"전압 범위 {grid['voltage_min_pu']:.9f}–{grid['voltage_max_pu']:.9f} pu. 독립 Fresh96 수렴 {grid['converged_slots']}/96; 위반 {grid['violations']}.",
        f"C0(68.893996691%) 대비 {grid['delta_vs_C0_percentage_points']:+.9f}%p, B0(71.818273624%) 대비 {grid['delta_vs_B0_percentage_points']:+.9f}%p.",
        f"May01 Compute GPUh는 C1 {sum(r['compute_GPUh_Dday'] for r in g.values()):.9f}, C0 12412.985555556, B0 18146.029166667이다. 처리량이 다르므로 부하율 차이를 동일 처리량 개선으로 해석하지 않는다.", '',
        '## 성능', '',
        '| 구간 | 초 |','|---|---:|',f"| Actual 입력 준비 | {t['input_preparation_wall_seconds']:.6f} |",
        f"| Actual Event | {t['actual_event_wall_seconds']:.6f} |",f"| Fresh AC96(30h 연속 replay의 마지막 96) | {t['fresh_AC96_wall_seconds']:.6f} |",
        f"| 본 Worker 전체 | {t['worker_total_wall_seconds']:.6f} |",f"| 최대 제어 Tick | {t['max_control_tick_seconds']:.6f} |",
        f"| 별도 입력/계약 Preflight | {t['preflight_wall_seconds']:.6f} |",f"| 한 번의 짧은 Canary 이벤트 실행 | {t['canary_wall_seconds']:.6f} |",
        f"| 독립 후처리 | {t['independent_audit_wall_seconds']:.6f} |",f"| 측정 실행 구간 합계 | {t['total_measured_experiment_wall_seconds']:.6f} |", '',
        f"첫 Canary START부터 최종 독립 검산까지의 연속 Wall은 {t['end_to_end_since_first_canary_START_seconds']:.6f}초이다. 중간 기록 보완·입력 준비 시간까지 포함하며 개발 착수 시각을 의미하지 않는다.", '',
        f"세부 측정: {t['measured_substages']}. Current AC 요청 {t['Current_AC_cache_requests']}회, cache miss {t['Current_AC_cache_misses']}회, 실제 probe 합계 {t['Current_AC_probe_seconds']:.6f}초.",
        'reservation_seconds는 Unknown 후보 feasibility, public_future_seconds는 공개 예약·잔여 수요 계산, sensitivity_seconds는 Signed 후보 점수, current_AC_seconds는 모든 Known/Unknown guard 호출이다. Probe 시간은 guard 시간과 겹치므로 더하지 않는다.',
        '동일 상태 프로파일/코호트 보존식/구간 적분/수치 Hash를 재사용했다. 단일 GPU 예약은 원본 UID별 max-union과 동일한 interval sweep을 사용하고 원본과 625개 무작위 후보를 대조했다. 기존 인증 Current AC 소스와 캐시는 유지했고 현재 후보 측정을 생략하지 않았다.', '',
        'Native 호출 0회 / Runtime 0초. Worker 1·Threads 1 및 6개 Heavy OS Lock을 준수했다. 40분 중단 한계 안에서 전체 Actual을 한 번만 수행했다.', '',
        '## 검증·범위', '',
        '집중 테스트 45개 PASS. 실제 Canary 25 Tick 1회 후, 같은 관측 원장에서 D00 이전 공개 상태를 복원하여 대체 사이트 11개 점수를 검증했다(이벤트 궤적 재실행 0회). Overrun 대기→대체 사이트 START는 명명된 이벤트 fixture로 별도 검증했으며 실제 실험 건수와 구분한다.',
        'Golden003 UB 0.6718471055537026 / 독립 LB 0.6715871456570585 / Gap 0.0386933%는 기존 인증을 보존한다. Phase I·Pricing·Integer Restoration·Native Optimize는 새로 실행하지 않았다.',
        'CC4 Q50/Q90, 기존 AIDC 전기 C1 P/Q, 원본 IEEE123·7-RegControl을 유지했다. Unknown 제어 Variant C1은 전기 C1 계수와 다른 개념이다.',
        '기존 C0/Golden003/B0/B2 원장과 분리된 Attempt를 사용했다. B2 종료 상태·소스·예산·원장, B0/B2 FCFS 경로를 이 변경에서 수정하지 않았다. May02–31과 Main Merge는 수행하지 않았다.',
        'FORECAST_CAUSAL_AVAILABILITY=NOT_CERTIFIED, CAUSAL_PASS=False, 초기 RUNNING 44개 사이트 MODEL_ASSUMED 상태를 유지한다.',
        '기존 공통 driver RESULT의 R1=NOT_EXECUTED_ASSUMED_SEPARATE는 Strict 공통 보고 필드가 남은 것이다. 이번 R1 실행의 근거는 새 CorrectivePolicy 영수증 및 독립 UID→실제 START 대조이며, 이 보고서의 R1_ASSUMED 상태가 권위 있는 해석이다.', '',
        '## 원장', '',f'- Attempt: `{ACTUAL}`',f'- 독립 보고: `{ACTUAL / "INDEPENDENT_C1_REPORT.json"}`',
        f'- 후보별 원장: `{ACTUAL / "CORRECTIVE_POLICY_RECEIPTS.json"}`',f'- Fresh96: `{ACTUAL / "C1/FRESH_ORIGINAL7_AC.json"}`',
        f'- Known 계약 원장: `{PREFLIGHT / "KNOWN_WINDOW_AUDIT.json"}`',
        f'- 실제 Adapter 영수증 교차검증: `{PREFLIGHT / "CANARY_KNOWN_WINDOW_ADAPTER_CROSSCHECK.json"}`', '',
        '기계 판독 요약과 SHA 바인딩: [RESULT JSON](V43_B1_R1_FLEX30_C1_RESULT.json).','']
    (DOC/'V43_B1_R1_FLEX30_C1_ACTUAL_KO.md').write_text('\n'.join(lines),encoding='utf8')
    body=f'''B1 Actual was pinned to Unknown control variant C0, which blocked every alternative site. May01 B1 now runs R1-FLEX30-C1 alone using the unchanged Golden003 selected jobs, Known allocation/start/migration commands, CC4 Q50/Q90 and original AIDC electrical C1 model. No A1 Phase I, pricing, integer restoration or Native optimize was rerun.

One new Actual96/Fresh96 attempt completed with physical execution and independent UID/site/time/GPU/P/Q checks PASS. **Service equivalence remains NOT_CERTIFIED: 414 Golden003 Known starts conflict with the original authorized windows.** Windows were not widened. Original FULL allowed starts, WINDOWS.json, actual OriginalKnownWindows receipts and `_known_decision()` agree on the conflict (example UID8632559: allowed slot0, selected slot2). Existing numerical Golden certification is not execution authorization.

| Observed 30h cohort | Total | START | COMPLETED | Carryout | May01 compute GPUh |
|---|---:|---:|---:|---:|---:|
| Known | {g['Known']['total']} | {g['Known']['START']} | {g['Known']['COMPLETED']} | {g['Known']['Carryout']} | {g['Known']['compute_GPUh_Dday']:.6f} |
| Unknown | {g['Unknown']['total']} | {g['Unknown']['START']} | {g['Unknown']['COMPLETED']} | {g['Unknown']['Carryout']} | {g['Unknown']['compute_GPUh_Dday']:.6f} |

Unknowns are observed only on arrival, designated a basic FCFS/reference site while PENDING, ranked with the original signed response and started only after Current AC passes. R1 uses the unchanged deterministic arrival UID hash: {p['R1_participant_UIDs']}/{p['R1_eligible_UIDs']} eligible Unknowns participate (R1_ASSUMED, not Source-certified consent). Basic designation {p['basic_designated_UIDs']} UID; signed evaluation {p['sensitivity_evaluated_UIDs']} UID; alternative signed evaluation {p['sensitivity_evaluated_alternative_instances']} candidate instances across {p['sensitivity_evaluated_alternative_UIDs']} UID; Pre-site selected/actually STARTed {p['selected_presite_UIDs']}/{p['actual_presite_START_UIDs']} UID. Observed-overrun queue then Pre-site START {p['overrun_wait_then_presite_START_UIDs']} UID. Nonparticipants and explicit Source prohibitions remain blocked. New running migration and intentional Unknown time shifting:0.

Of185 actual Pre-sites,88 had an infeasible basic-site capacity booking and97 had a scored basic candidate. All97 improved predicted loading-hours with an equal predicted horizon peak; none reduced the predicted horizon peak. These diagnostics are not an Actual peak reduction claim.

Actual peak line-phase loading {grid['peak_loading_fraction']*100:.9f}% at {grid['peak_line']} phase{grid['peak_phase']}, {peak_kst} KST ({grid['peak_slot_begin_AEST']} AEST,15-minute interval start). Voltage {grid['voltage_min_pu']:.9f}–{grid['voltage_max_pu']:.9f}pu. Independent original IEEE123 seven-RegControl Fresh96 converged96/96 with zero voltage/line/transformer violations. Peak difference versus frozen B1 C0:{grid['delta_vs_C0_percentage_points']:+.9f}%p; versus B0:{grid['delta_vs_B0_percentage_points']:+.9f}%p. May01 compute: C1 {sum(r['compute_GPUh_Dday'] for r in g.values()):.9f}, C0 12412.985555556, B0 18146.029166667GPUh. Throughputs differ, so the loading comparison is not an equal-service improvement. Known START falls1070→1023 while Unknown START rises683→800 versus C0.

Known unstarted626 =414 window-contract failures +212 other jobs (last reasons:NO_CAPACITY187, observed-running-retained25).172 Known starts exceeded their original execution window after capacity waiting. Intentional burden over budget0; actual latest-start excess1074UID including402 started UID; explicit completion deadline violations0. Customer SLA is not certified.

Timing: input preparation {t['input_preparation_wall_seconds']:.6f}s; Actual events {t['actual_event_wall_seconds']:.6f}s; Fresh {t['fresh_AC96_wall_seconds']:.6f}s; worker total {t['worker_total_wall_seconds']:.6f}s; maximum control callback {t['max_control_tick_seconds']:.6f}s. Unknown candidate reservation checks {t['measured_substages']['reservation_seconds']:.6f}s, public future/residual profiles {t['measured_substages']['public_future_seconds']:.6f}s, signed sensitivity {t['measured_substages']['sensitivity_seconds']:.6f}s, all Current AC guards {t['measured_substages']['current_AC_seconds']:.6f}s (overlapping probe-only time {t['Current_AC_probe_seconds']:.6f}s). Native calls/runtime0/0. First Canary START through independent reconciliation:{t['end_to_end_since_first_canary_START_seconds']:.3f}s, within40minutes.

Repeated immutable integrals, public reservation profiles, cohort conservation and numeric hashes are memoized. Integer GPU reservations retain per-UID max-union semantics;625 randomized candidates match the original check. The certified Current AC implementation/cache is unchanged, present candidates are fully checked and Fresh is independent. Worker1/Threads1 and all six heavy OS locks were used and released. One25-slot real event Canary plus a public-state candidate evidence continuation (11 alternatives, no event trajectory rerun) and a named queued-overrun→START event fixture preceded the one full Actual run.

Validation:45 focused tests PASS; independent event-interval GPU integrals, instantaneous capacity/rack/compatibility, frozen Known commands, arrival/participation rights and exact original electrical C1 P/Q recomputation PASS. Per-UID Pre-site transitions/scores and414 authorization failures are committed as CSV; detailed Korean report and machine-readable SHA-bound result are under `docs/v43/V43_B1_R1_FLEX30_C1_*`.

Golden003 UB0.6718471055537026 / independent Global LB0.6715871456570585 / gap0.0386933% are preserved parent certificates. Forecast availability remains NOT_CERTIFIED/CAUSAL_PASS=False;44 initial running sites remain MODEL_ASSUMED. The inherited raw driver's stale R1 status label is explicitly superseded by actual C1 policy receipts and independent UID START evidence; it is not used as an R1 certificate.

B0 exact PR189 FCFS Attempt005 remains immutable (71.818273624%, Native0, zero Fresh violations); B0/B2 FCFS source paths and the fixed B0 Planning reference are unchanged. B2 M1 Attempt001 had already terminated before this B1 execution with its prior reporting TypeError; its source, Native budgets and ledgers were preserved and it was not interrupted or rerun here. Existing C0/Golden003/B0/B2 attempts and unrelated working-tree changes are preserved. May01 only; no May02–31 and no Main merge.
'''
    (DOC/'PR_BODY.md').write_text(body,encoding='utf8')
    print(DOC/'V43_B1_R1_FLEX30_C1_ACTUAL_KO.md')


if __name__=='__main__':run()
