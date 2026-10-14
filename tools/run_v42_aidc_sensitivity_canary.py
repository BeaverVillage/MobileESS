"""May01 observed boundary probes; no native solver, private runtime or replay."""
from pathlib import Path
from copy import deepcopy
from time import perf_counter
import csv
import heapq
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v42_integration.unified_contract import load_contracts, REPORT, file_sha
from v42_integration.policy import digest
from v42_integration.production_case import read, KERNEL, TIMING
from v42_integration.tracking_canary import prepare, reference_from_anchor, HISTORICAL_A1
from v42_integration.partial_canary import SOURCE_DIR
from v42_integration.experimental_actual import prepare_conditional_arguments
from v42_integration.trajectory_tracking import TrackingReference, TrajectoryTrackingPolicy, TrackingJobEventController
from v42_integration.aidc_sensitivity_runtime import (Research60QoSProvider,
    SignedSensitivityPolicy, SensitivityRuntimeController, known_initial_reconciliation,
    known_planning_bridge, conditional_remaining_runtime)


def write(name, value):
    (REPORT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def csv_write(name, rows, fields):
    with (REPORT/name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def observed_controller(args, policy, controller_class, commands):
    """Only public initial RUNNING/issued PENDING; Environment is unread."""
    begin = args['begin']
    c = controller_class(args['capacities'], arm='B1', qos_window_provider=args['qos_window_provider'],
        frozen_policy=policy, known_schedule=commands, reference=deepcopy(args.get('reference')),
        forecast=deepcopy(args.get('forecast')), wan_capacities=args.get('wan_capacities'))
    for request, site, start in sorted(args['running'], key=lambda r:(r[0].submit, r[0].uid)):
        if request.uid not in c.reference.assigned:
            c.reference.observe_running(request, site=site, start_seconds=start,
                event_seconds=begin, elapsed_compute_seconds=request.metadata.get('elapsed_compute_seconds', begin-start))
    for request, site, start in sorted(args['running'], key=lambda r:(r[0].submit, r[0].uid)):
        c.submit(request, begin)
        c.pending.remove((request.submit, request.uid))
        heapq.heapify(c.pending)
        c.ledger.start(request.uid, site, begin, request.metadata.get('episode_id', 'OBSERVED:'+request.uid))
        c.ledger.jobs[request.uid]['start_time'] = start
        c.metadata[request.uid].update(state='RUNNING', current_site=site,
            accumulated_compute_seconds=request.metadata.get('elapsed_compute_seconds', begin-start))
        c.reservations.retain_running(request.uid, site, begin, begin+900, request.gpu)
    for request in sorted(args['requests'], key=lambda r:(r.submit, r.uid)):
        if request.submit <= begin and request.uid not in c.requests:
            c.submit(request, begin)
    return c


def run():
    began = perf_counter()
    shared = load_contracts()
    bindings = shared['bindings']
    setup = REPORT/'AIDC_SOURCE_DIAGNOSTIC'
    setup.mkdir(exist_ok=True)
    case, a_case, records, strict = prepare(setup)
    historical_ref, packet, cc4 = reference_from_anchor(case, a_case, records, read(HISTORICAL_A1), setup)
    spec = read(REPORT/'TIME_SHIFT_60MIN_QOS_CONTRACT.json')
    initial_path = SOURCE_DIR/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json'
    initial = read(initial_path)
    known = known_initial_reconciliation(historical_ref.commands, initial,
        issue_seconds=case.planning_slot_zero_seconds, begin_seconds=packet.begin_seconds)
    known.update(bindings=bindings, evidence_scope='HISTORICAL_PLAN_VERSUS_SOURCE_BOUNDARY_AUDIT',
        initial_source_sha=file_sha(initial_path), known_issue_UIDs=len(records),
        native_command_UIDs=len(historical_ref.commands), active_known_UIDs=sum(
            not r['origin_unknown'] for r in initial['running']+initial['pending']),
        planning_domain_recipe=known_planning_bridge(records, issue_seconds=case.planning_slot_zero_seconds,
            begin_seconds=packet.begin_seconds), new_60min_A1='NOT_RUN',
        Known_replay_gate='BLOCKED_BEFORE_ACTUAL', source_reference_fallback_is_observed_site=False)
    write('KNOWN_INITIAL_STATE_RECONCILIATION.json', known)
    # The new case uses the same numeric historical anchor as a diagnostic
    # reference; its historical optimum/certificate is never transferred.
    packet.bindings = dict(bindings)
    identity = dict(historical_ref.identity, bindings=bindings,
        CC4_source_authority=dict(model_id='LGBM_weighted_c1_s20260924',
            prediction_sha=cc4['prediction_sha'], kernel_sha=file_sha(KERNEL),
            timing_envelope_sha=file_sha(TIMING), aidc_anchor=historical_ref.identity['A1_Anchor_SHA'],
            future_Actual_or_UID_inputs_used=False, forecast_modifications=0),
        lineage='HISTORICAL_NUMERIC_ANCHOR_ONLY_NEW60_NOT_CERTIFIED')
    reference = TrackingReference(*(historical_ref.arrays[k] for k in (
        'G_Known_Plan', 'G_Unknown_Q50_Plan', 'IT_Plan', 'PCC_P_Plan', 'PCC_Q_Plan')),
        sites=historical_ref.sites, begin=historical_ref.begin,
        commands=historical_ref.commands, identity=identity)
    manifest = digest(dict(known_commands=digest(reference.commands), initial_state=bindings['initial_state_sha'],
        cc4=bindings['cc4_sha'], qos=bindings['qos_sha'], runtime=bindings['runtime_sha'],
        selection='FIRST_5_FCFS_OBSERVED_UNKNOWN_PENDING_AT_DDAY_00'))
    decisions, comparisons, migration, overruns, backfill = [], [], [], [], []
    current_witnesses, grid_funnel, cohort_audits = [], [], []
    chosen = None
    for label in ('C0', 'C1', 'C2', 'C3'):
        provider = Research60QoSProvider(strict, case_sha=bindings['case_sha'], frozen_spec=spec)
        if provider.stats.sha != bindings['qos_sha']:
            raise ValueError('SHARED_QOS_POLICY_SHA_DRIFT')
        base = dict(case.actual_arguments, qos_window_provider=strict)
        # Clip to observed boundary before projection: future Unknown UID
        # metadata and all simulator-private completion values are unread.
        base['requests'] = [r for r in base['requests'] if r.submit <= base['begin']]
        projection = prepare_conditional_arguments(base, records, scenario='U60', participation='FLEX30',
            case_sha=bindings['case_sha'], existing_provider=provider)
        args = projection['arguments']
        if label == 'C0':
            from v42_integration.qos import receipt_slot_domain
            native_jobs = a_case.data[1]
            empty = [uid for uid, j in native_jobs.items() if j.state == 'PENDING' and not any(
                case.planning_slot_zero_seconds+slot*900 >= packet.begin_seconds for slot in
                receipt_slot_domain(provider.receipts[uid], axis_origin_seconds=case.planning_slot_zero_seconds))]
            known['native_new60_boundary_domain'] = dict(native_UIDs=len(native_jobs),
                issue_Running_UIDs=sum(j.state == 'RUNNING' for j in native_jobs.values()),
                issue_Pending_UIDs=sum(j.state == 'PENDING' for j in native_jobs.values()),
                empty_post_Dday_authorized_UIDs=empty, empty_post_Dday_authorized_count=len(empty),
                original_issue_reference_and_budget_unchanged=True, future_Dday_snapshot_used=False,
                status='EMPTY_AUTHORIZED_DOMAIN_PREFIX_EXECUTION_NEEDED' if empty else 'READY_NATIVE_NOT_RUN')
            write('KNOWN_INITIAL_STATE_RECONCILIATION.json', known)
        if label == 'C1':
            policy = TrajectoryTrackingPolicy(reference, packet, bindings=bindings,
                migration_authority=case.experimental_migration_authority)
            cls = TrackingJobEventController
        else:
            policy = SignedSensitivityPolicy(reference, packet, bindings=bindings, expected_bindings=bindings,
                migration_authority=case.experimental_migration_authority,
                runtime_repair=label == 'C3', basic=label == 'C0', evidence_scope='REAL_OBSERVED_BOUNDARY_PROBE_ONLY')
            cls = SensitivityRuntimeController
        c = observed_controller(args, policy, cls, reference.commands)
        if label != 'C1':
            current_tick = args['begin']
            current_weather = deepcopy(args['weather'][0])
            def weather_provider(now):
                if now != current_tick:
                    raise ValueError('FUTURE_ACTUAL_WEATHER_QUERY_FORBIDDEN')
                return deepcopy(current_weather)
            policy.bind_observed_c1(args['power_model'], current_weather_provider=weather_provider)
        pending = [uid for _, uid in sorted(c.pending) if c.metadata[uid]['origin_unknown']]
        targets = pending[:5]
        if chosen is None:
            chosen = targets
        elif chosen != targets:
            raise ValueError('FAIR_BOUNDARY_TARGET_SELECTION_DRIFT')
        now = args['begin']
        use = c.ledger.physical(now)
        at = perf_counter()
        policy.observe(now, use, c.metadata)
        if label == 'C2':
            base_gpu = np.asarray([use[s] for s in packet.sites], float)
            model = args['power_model']
            base_power = model.recompute(base_gpu[None,:], packet.sites, [current_weather])
            for uid in targets:
                m, receipt = c.metadata[uid], c.budgets[uid]
                source = m.get('reference_site', m.get('source_site'))
                for site in sorted(m['compatible_sites']):
                    non_grid = []
                    if site != source and m.get('can_prestart_place') is not True:
                        non_grid.append('PREPLACE_SOURCE_AUTHORITY')
                    if m['gpu'] > max(packet.rack_compatibility[site]):
                        non_grid.append('RACK_GANG_INCOMPATIBLE')
                    end = now+max(m['t50_seconds'], 1e-9)
                    if (m.get('hard_latest_start_seconds') is not None and now > m['hard_latest_start_seconds']) or (
                            m.get('completion_deadline_seconds') is not None and end > m['completion_deadline_seconds']):
                        non_grid.append('HARD_WINDOW')
                    segments = [dict(resource='gpu:'+site, begin=now, end=end, quantity=m['gpu'])]
                    cap = c.reservations.feasible(segments, exclude=uid)
                    if cap:
                        non_grid.append(cap)
                    placement_capacity_eligible = not non_grid
                    if now < max(receipt.reference_start_seconds, m.get('release_seconds') or now,
                            m.get('hard_earliest_start_seconds') or now):
                        non_grid.append('SOURCE_START_BEFORE_FCFS_REFERENCE_OR_RELEASE')
                    elif now not in receipt.allowed_starts_seconds and site != source:
                        non_grid.append('SOURCE_START_WINDOW')
                    candidate = base_gpu.copy(); candidate[packet.sites.index(site)] += m['gpu']
                    power = model.recompute(candidate[None,:], packet.sites, [current_weather])
                    peak, bad = packet._at_slot(0, policy._grid_delta(0, candidate, now))
                    current_witnesses.append(dict(uid=uid, site=site, gpu=m['gpu'], q50_seconds=m['t50_seconds'],
                        observed_at_seconds=now, original_reference_seconds=receipt.reference_start_seconds,
                        candidate_start_seconds=now, non_grid_guard_reasons=non_grid,
                        placement_capacity_eligible=placement_capacity_eligible,
                        current_non_grid_eligible=not non_grid, observed_GPU_by_site=dict(use),
                        candidate_GPU_by_site=dict(zip(packet.sites, candidate.tolist())),
                        baseline_PCC_P_kw=base_power['PCC_P_kw'][0].tolist(),
                        baseline_PCC_Q_kvar=base_power['PCC_Q_kvar'][0].tolist(),
                        candidate_PCC_P_kw=power['PCC_P_kw'][0].tolist(),
                        candidate_PCC_Q_kvar=power['PCC_Q_kvar'][0].tolist(),
                        delta_PCC_P_kw=(power['PCC_P_kw'][0]-base_power['PCC_P_kw'][0]).tolist(),
                        delta_PCC_Q_kvar=(power['PCC_Q_kvar'][0]-base_power['PCC_Q_kvar'][0]).tolist(),
                        current_signed_affine_peak=peak, current_signed_affine_violations=bad,
                        current_weather=current_weather, C1_source_sha=model.authority_sha,
                        coefficient_sha=packet.coefficients[0].coefficient_sha256,
                        Actual_executed=False, Fresh_AC='SUPERVISOR_ONLY_NOT_RUN'))
        for uid in targets:
            d = policy.select(c.metadata[uid], c.budgets[uid], now, c.reservations, reserve=False)
            scores = d.get('tracking', {})
            decisions.append(dict(variant=label, uid=uid, observed_at_seconds=now, action=d['action'],
                site=d.get('site'), start_seconds=d.get('start_seconds'),
                predicted_max_loading=scores.get('grid_peak'),
                hard_guard=d.get('reason', d['status']), candidate_count=d['candidate_count'],
                decision_seconds=d['decision_seconds'], executed=False,
                evidence_scope='OBSERVED_EVENT_CANDIDATE_DIAGNOSTIC_ONLY'))
        if label != 'C1':
            grid_funnel.extend(dict(variant=label, **r,
                current_violation_slots=sorted({v['slot'] for v in r['violations'] if v['slot'] == 0}),
                future_violation_slots=sorted({v['slot'] for v in r['violations'] if v['slot'] > 0}))
                for r in policy.diagnostics)
            cohort_audits.append(dict(variant=label, **policy.anonymous_residual_audit))
        # Overruns are public observations. They are not repaired by evicting
        # Running jobs, and no residual completion time is exposed here.
        for uid, m in sorted(c.metadata.items()):
            if m['state'] == 'RUNNING' and m['accumulated_compute_seconds'] > m['t50_seconds']:
                r = conditional_remaining_runtime(m)
                overruns.append(dict(variant=label, uid=uid, observed_at_seconds=now,
                    action='RUNNING_HOLD_UNTIL_OBSERVED_COMPLETION', gpu=m['gpu'],
                    site=m['current_site'], elapsed_seconds=r['elapsed_seconds'],
                    Q50_seconds=r['total_Q50_seconds'], conditional_remaining_Q90=None,
                    running_gpu_protected=True, reservation_repair_executed=False,
                    evidence_scope='OBSERVED_BOUNDARY_NO_REPLAY'))
        comparisons.append(dict(variant=label, same_input_sha=manifest, observed_unknown_pending_probes=len(targets),
            selected_candidate_UIDs=sum(d['variant'] == label and d['action'] != 'QUEUE' for d in decisions),
            executed_changed_UIDs='NOT_RUN', actual_max_line_loading='NOT_RUN',
            actual_completed_carry='NOT_RUN', actual_queue_deadline='NOT_RUN',
            controller_P50_seconds=float(np.percentile(policy.times, 50)),
            controller_P95_seconds=float(np.percentile(policy.times, 95)),
            controller_max_seconds=max(policy.times), wall_seconds=perf_counter()-at,
            Native_Optimize_calls=0, status='BOUNDARY_PROBE_ONLY_KNOWN_REPLAY_BLOCKED'))
        if label != 'C1':
            comparisons[-1].update(exact_baseline_cache_hits=policy.baseline_cache_hits,
                exact_baseline_cache_misses=policy.baseline_cache_misses)
        if label != 'C1':
            # Source-compatible checkpoint opportunities are inspected with
            # no reservation/physical mutation and retained by UID.
            initial_unknown_running = [u for u, m in sorted(c.metadata.items())
                if m['origin_unknown'] and m['state'] == 'RUNNING']
            for uid in initial_unknown_running:
                m = c.metadata[uid]
                policy.select_migration(m, c.budgets[uid], now, c.reservations,
                    checkpoint_at=None, reserve=False)
            migration.extend(dict(variant=label, **row, executed=False,
                evidence_scope='OBSERVED_BOUNDARY_NO_CHECKPOINT_EVENT') for row in policy.funnel)
        # Actual completion is intentionally not queried; a no-event report
        # cannot claim successful short-runtime backfilling.
        backfill.append(dict(variant=label, uid='', status='NOT_RUN', selected=False,
            reason='NO_ACTUAL_COMPLETION_EVENT_REPLAY_BEFORE_KNOWN_RECONCILIATION',
            next_reservation_protected=True, budget_reissued=False))
    csv_write('UNKNOWN_JOB_SENSITIVITY_DECISIONS.csv', decisions, list(decisions[0]))
    csv_write('AIDC_CANARY_COMPARISON.csv', comparisons, list(comparisons[0]))
    csv_write('RUNTIME_OVERRUN_RESERVATION_REPAIR.csv', overruns, list(overruns[0]) if overruns else [
        'uid', 'status', 'reason'])
    csv_write('RUNTIME_SHORT_BACKFILLING.csv', backfill, list(backfill[0]))
    csv_write('CHECKPOINT_MIGRATION_FUNNEL.csv', migration, list(migration[0]) if migration else ['uid', 'status'])
    write('CURRENT_C1_CANDIDATE_WITNESSES.json', dict(bindings=bindings,
        evidence_scope='MAY01_IEEE123_B1_HISTORICAL_ANCHOR_CURRENT_OBSERVED_DIAGNOSTIC',
        source_response='AUTO_CAUSAL_PREFIX_SIGNED_SECANTS_PLUS_LDC_INTERVAL',
        site_axis=list(packet.sites), s0_MESS=dict(case.initial_mess),
        source_initial_state_sha=bindings['initial_state_sha'], witnesses=current_witnesses,
        historical_known_commands_sha=digest(reference.commands),
        current_exact_C1=True, future_actual_weather_used=False, Native_calls=0, AC_calls=0))
    write('SENSITIVITY_CURRENT_FUTURE_REJECT_FUNNEL.json', dict(bindings=bindings, rows=grid_funnel))
    write('ANONYMOUS_CC4_COHORT_CONSERVATION.json', dict(bindings=bindings, audits=cohort_audits))
    (REPORT/'SENSITIVITY_ALLOCATION_ALGORITHM_KO.md').write_text(
        '# Signed Sensitivity 기반 AIDC 알고리즘\n\n'
        '신규 정책은 후보 추가 후 모든 선로·상·잔여 96슬롯의 최대 부하율을 최소화한다. '
        '민감도 절댓값 또는 기존 혼잡 선로 하나만 비교하지 않는다. C1 PCC P/Q 변화와 원래 '
        'Voltage/NormalAmps/Transformer 선형 행을 유지하며 Fresh AC 인증을 대신하지 않는다.\n\n'
        '관측 Running, Known 동결 명령, Unknown 확정 예약은 Hard이다. 익명 CC4 Q50/Q90 및 '
        'Running Q50 잔여예측은 Forecast이며 GPU 용량 확정 예약으로 승격하지 않는다. '
        '동일 UID의 겹친 물리 점유는 구간별 최대값으로 합친다.\n\n'
        'FLEX30은 공개 UID 해시로 결정하는 30% 참여 비율이다. U60은 참여 Batch에 최대 3600초 '
        '추가 시작 지연을 가정한 별도 연구 계약이며 고객 SLA가 아니다. 보호·긴급·Interactive '
        '추가 지연은 0이다. 원래 Deadline은 별도이고 재시도로 예산을 다시 발급하지 않는다.\n\n'
        'Overrun은 실제 완료 관측까지 Running GPU를 보존하고 아직 시작하지 않은 Unknown '
        '예약을 재검사한다. Known 명령은 변경 권한 없이 재배치하거나 현재 시각으로 이동하지 않는다. '
        'Short Runtime은 기존 15분 제어 Release 계약을 유지하며 다음 확정 예약 앞의 Backfill은 '
        '출처가 인증된 Runtime 상한이 있을 때만 허용한다. Q50/Q90는 완료 보장이 아니다. '
        '조건부 잔여 Runtime Q90 Provider는 NOT_CERTIFIED이다.\n\n'
        'Checkpoint Migration은 실제 RUNNING, 관측 Checkpoint, 1회 한도, Source/Destination '
        'Capability, WAN·Residency·Transfer·Restart, 공유 QoS, 잔여 서비스 및 GPU/Rack 행을 '
        '통과할 때만 후보가 된다. 0건 결과도 UID Funnel로 보존한다.\n\n'
        'May01 Known 1649 UID 중 Dday Running 301, Pending 1245, Completed 103이다. '
        'Pending 886 UID는 계획 시작시각이 이미 지났으나 실행 관측이 없다. 과거 명령을 이동하지 '
        '않으며 새 Native A1/Prefix 연결이 인증되기 전 Actual 비교는 차단한다. 이번 Canary는 '
        '동일 초기 상태·Known 명령·Forecast·QoS에서 최초 FCFS Unknown Pending 5 UID에 대한 '
        '현재 관측 후보 진단이다. 실제 실행 변경 수, 전력망 개선, Full96 및 새 A1 최적성은 '
        'NOT_RUN/NOT_CERTIFIED이며 기존 인증을 이전하지 않는다.\n', encoding='utf-8')
    write('AIDC_NATIVE0_CANARY_RECEIPT.json', dict(bindings=bindings, target_UIDs=chosen,
        selection_rule='FIRST_5_FCFS_OBSERVED_UNKNOWN_PENDING_AT_DDAY_00',
        same_input_sha=manifest, same_inputs_PASS=True, wall_seconds=perf_counter()-began,
        private_Environment_read=False, future_Unknown_UIDs_in_policy_input=0,
        Native_Optimize_calls=0, Actual_replay_calls=0, Fresh_AC_calls=0,
        status='OBSERVED_CANDIDATE_DIAGNOSTIC_KNOWN_BLOCKED',
        Full96='NOT_RUN', new_A1='NOT_CERTIFIED', performance_improvement='NOT_CERTIFIED'))
    print(json.dumps(dict(status='AIDC_OBSERVED_BOUNDARY_PROBE_COMPLETE', probes=len(decisions),
        blocked_known=known['counts'].get('PAST_START_NOT_OBSERVED_EXECUTED_BLOCKED', 0),
        Native_Optimize_calls=0, wall_seconds=perf_counter()-began)))


if __name__ == '__main__':
    run()
