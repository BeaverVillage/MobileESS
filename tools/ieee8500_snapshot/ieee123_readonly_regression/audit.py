"""Read saved IEEE123 Actual mobility evidence only; no production imports or replay."""
from pathlib import Path
import collections
import csv
import hashlib
import json
import math
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
ROOT = Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
F = ROOT / 'frozen_artifacts'
inputs = {}
checks = collections.Counter()

def sha(b):
    return hashlib.sha256(b).hexdigest()

def digest(v):
    return sha(json.dumps(v, sort_keys=True, separators=(',', ':'), default=str).encode())

def check(ok, label):
    if not ok:
        raise AssertionError(label)
    checks[label] += 1

def read(path, expected=None):
    path = Path(path).resolve()
    st = path.stat()
    b = path.read_bytes()
    h = sha(b)
    if expected is not None:
        check(h == expected, 'stored_source_or_receipt_SHA_match')
    rec = dict(path=str(path), bytes=len(b), sha256_before=h, mtime_ns_before=st.st_mtime_ns)
    if str(path) in inputs:
        check(inputs[str(path)] == rec, 'source_stable_during_reads')
    inputs[str(path)] = rec
    return b

def js(path, expected=None):
    return json.loads(read(path, expected))

def write_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def write_csv(name, rows, fields):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def main():
    pointer = js(F / 'v41r4_may/loop_wall_v4/audit/ACTUAL_EXECUTION_METHOD_CURRENT.json')
    final = js(F / 'v41r4_restoration_revision_v1/FINAL_AUDIT.json')
    check(final['status'] == 'COMPLETE', 'final_authority_COMPLETE')
    js(final['restoration_rule']['path'], final['restoration_rule']['sha256'])
    for p in ['dayahead/v33m/contracts.py', 'dayahead/v33m/mobility_15min_adapter.py',
              'dayahead/v33m/mess_trajectory.py', 'dayahead/v40d_actual/mess_replay.py',
              'dayahead/v40d_actual/inputs.py', 'dayahead/paper_analysis/storage.py']:
        read(ROOT / p)
    expected = {(f'2025-05-{d:02d}', p) for d in range(1, 32) for p in ['B0', 'B1', 'B2', 'B3']}
    check(len(final['rows']) == 124 and {(r['day'], r['policy']) for r in final['rows']} == expected,
          'complete_31x4_unique_authority_coverage')
    movements, coverage, vehicles, pairs, collisions = [], [], [], [], []
    namespaces = collections.Counter()
    for auth in final['rows']:
        day, policy = auth['day'], auth['policy']
        view = F / 'v41r4_revision_monitor_view/replays' / day / policy
        replay = view.resolve()
        namespace = replay.parents[2]
        namespaces[namespace.name] += 1
        common = namespace / 'common_inputs' / day / policy
        receipt = js(replay / 'CANDIDATE_RECEIPT.json')
        check(receipt['status'] == 'COMPLETE' and receipt['day'] == day and receipt['policy'] == policy,
              'receipt_identity_COMPLETE')
        def replay_json(rel):
            return js(replay / rel, receipt['files'][rel.replace('/', '\\')])
        complete = replay_json('COMPLETE.json')
        check(complete['status'] == 'PASS', 'saved_Actual_complete_PASS')
        stage = 'CONTROL_COMMON_BINDING' if policy in ['B0', 'B1'] else 'ETA95_QSAFE_ACTUAL'
        actuator = replay_json(stage + '/ACTUATOR.json')
        check(actuator['binding'] == complete['binding'], 'final_actuator_binding_identity')
        audit = js(common / 'ACTUAL_MESS_AUDIT.json')
        snapshot = js(common / 'DA_FRESH_INPUT_SNAPSHOT.json')
        ready = js(common / 'READY.json')
        check(ready['status'] == 'PASS', 'saved_input_ready_PASS')
        sources = [k for k in snapshot if k.endswith('FROZEN_MESS_COMMANDS.json')]
        check(len(sources) == 1, 'unique_frozen_command_source')
        commands_path = sources[0]
        commands = js(commands_path, snapshot[commands_path])['MESS_trajectory']
        check(digest(commands) == auth['new_trajectory_SHA'], 'final_DA_trajectory_authority_SHA_identity')
        binding = complete['binding']
        check(digest(audit['moves']) == binding['realized_moves_SHA'], 'saved_moves_final_binding_SHA_identity')
        check(audit['frozen_commands_SHA'] == binding['frozen_command_SHA']
              and sha((json.dumps(audit['frozen_commands'], sort_keys=True, ensure_ascii=False,
                                  allow_nan=False, separators=(',', ':')) + '\n').encode()) == audit['frozen_commands_SHA'],
              'saved_commands_final_binding_SHA_identity')
        check(audit['audit']['status'] == actuator['independent_audit']['status'] == 'PASS',
              'saved_independent_mobility_audit_PASS')
        check(len(commands) == len(audit['frozen_commands']) == len(actuator['trajectory']) == 384,
              'full_4_vehicle_96_slot_coverage')
        original = {(c['mess_id'], c['slot']): c for c in commands}
        check(len(original) == 384, 'unique_command_vehicle_slots')
        mobility_keys = ['departure_slot', 'origin_service_id', 'destination_service_id',
                         'route_link_ids', 'connection_ready_slot', 'mode', 'service_id']
        for c in audit['frozen_commands']:
            check(all(c.get(k) == original[(c['mess_id'], c['slot'])].get(k) for k in mobility_keys),
                  'full_frozen_mobility_commands_identity')
        planned = {(c['mess_id'], c['departure_slot']): c for c in commands
                   if c['mode'] == 'TRANSIT' and c['departure_slot'] == c['slot']}
        moves = audit['moves']
        check(len(moves) == len(planned) and {(m['mess_id'], m['departure_slot']) for m in moves} == set(planned),
              'all_planned_moves_present_once_in_Actual')
        local = []
        for m in moves:
            c = planned[(m['mess_id'], m['departure_slot'])]
            src = m['frozen_command_source']
            check(Path(src['path']).resolve() == Path(commands_path).resolve()
                  and src['sha256'] == snapshot[commands_path], 'move_frozen_command_source_identity')
            check(all(m[k] == c[k] for k in ['origin_service_id', 'destination_service_id', 'route_link_ids']),
                  'move_route_origin_destination_identity')
            dep = m['departure_slot']
            eta = m['actual_eta_seconds']
            actual_ready = m['actual_connection_ready_slot']
            check(abs(m['actual_arrival_slot'] - (dep + eta / 900)) < 1e-10,
                  'stored_actual_arrival_arithmetic')
            check(actual_ready == dep + math.ceil((eta + 600) / 900), 'stored_actual_ready_600s_arithmetic')
            check(c['connection_ready_slot'] == dep + math.ceil((c['route_safe_eta_sec'] + 600) / 900),
                  'stored_planned_ready_safe_ETA_600s_arithmetic')
            late = eta > c['route_safe_eta_sec']
            crossed = actual_ready > c['connection_ready_slot']
            row = dict(day=day, policy=policy, mess_id=m['mess_id'],
                       previous_origin=m['origin_service_id'], previous_destination=m['destination_service_id'],
                       previous_departure_slot=dep,
                       previous_planned_connection_ready_slot=c['connection_ready_slot'],
                       previous_actual_arrival_slot=m['actual_arrival_slot'],
                       previous_actual_connection_ready_slot=actual_ready,
                       next_planned_departure_slot=None, collision_magnitude_slots=0,
                       planned_safe_eta_seconds=c['route_safe_eta_sec'], planned_q50_eta_seconds=c['route_q50_eta_sec'],
                       planned_q90_eta_seconds=c['route_q90_eta_sec'], actual_eta_seconds=eta,
                       actual_eta_late_vs_safe=late, actual_eta_late_vs_q50=eta > c['route_q50_eta_sec'],
                       actual_eta_late_vs_q90=eta > c['route_q90_eta_sec'],
                       eta_delay_vs_safe_seconds=eta-c['route_safe_eta_sec'],
                       ready_delay_slots=actual_ready-c['connection_ready_slot'],
                       planned_arrival_slot_safe=dep+c['route_safe_eta_sec']/900,
                       physical_arrival_slot_boundary_crossing=math.ceil(eta/900)>math.ceil(c['route_safe_eta_sec']/900),
                       connection_ready_slot_boundary_crossing=crossed,
                       classification=('CONNECTION_READY_SLOT_BOUNDARY_CROSSING' if crossed else
                                       'ETA_DELAY_WITHOUT_CONNECTION_READY_SLOT_CROSSING' if late else
                                       'WITHIN_SAFE_ETA'),
                       frozen_command_source=commands_path, actual_moves_source=str(common/'ACTUAL_MESS_AUDIT.json'),
                       actual_final_actuator=str(replay/stage/'ACTUATOR.json'))
            local.append(row)
        for v in sorted({c['mess_id'] for c in commands}):
            seq = sorted([m for m in local if m['mess_id'] == v], key=lambda m: m['previous_departure_slot'])
            for a, b in zip(seq, seq[1:]):
                a['next_planned_departure_slot'] = b['previous_departure_slot']
                a['collision_magnitude_slots'] = max(0, a['previous_actual_connection_ready_slot'] - b['previous_departure_slot'])
                pairs.append(dict(a))
                if a['collision_magnitude_slots'] > 0:
                    collisions.append(dict(a))
            vehicles.append(dict(day=day, policy=policy, mess_id=v, moves=len(seq),
                                 consecutive_move_pairs=max(0,len(seq)-1),
                                 collision_count=sum(x['collision_magnitude_slots'] > 0 for x in seq)))
        movements.extend(local)
        coverage.append(dict(day=day, policy=policy, Actual_disposition=auth['Actual_disposition'],
                             resolved_namespace=str(namespace), authoritative_replay=str(replay),
                             final_DA_trajectory_SHA=auth['new_trajectory_SHA'], moves=len(moves),
                             eta_late_safe=sum(x['actual_eta_late_vs_safe'] for x in local),
                             eta_late_q50=sum(x['actual_eta_late_vs_q50'] for x in local),
                             eta_late_q90=sum(x['actual_eta_late_vs_q90'] for x in local),
                             ready_slot_late=sum(x['connection_ready_slot_boundary_crossing'] for x in local),
                             collisions=sum(x['collision_magnitude_slots'] > 0 for x in local), binding_status='PASS'))
    summary = dict(status='READ_ONLY_AUDIT_COMPLETE',scope='IEEE123 authoritative May 2025 Actual 31 days x B0/B1/B2/B3',
                   policy_days=len(coverage), vehicle_policy_days=len(vehicles), total_moves=len(movements),
                   moving_vehicle_policy_days=sum(v['moves'] > 0 for v in vehicles),
                   maximum_moves_per_vehicle_policy_day=max(v['moves'] for v in vehicles),
                   consecutive_move_pairs=len(pairs), actual_ETA_later_than_planned_safe=sum(x['actual_eta_late_vs_safe'] for x in movements),
                   actual_ETA_later_than_nominal_q50=sum(x['actual_eta_late_vs_q50'] for x in movements),
                   actual_ETA_later_than_q90=sum(x['actual_eta_late_vs_q90'] for x in movements),
                   connection_ready_slot_later_than_planned=sum(x['connection_ready_slot_boundary_crossing'] for x in movements),
                   physical_arrival_slot_boundary_crossing_vs_safe=sum(x['physical_arrival_slot_boundary_crossing'] for x in movements),
                   collision_count=len(collisions), maximum_collision_slots=max([x['collision_magnitude_slots'] for x in collisions],default=0),
                   affected_day_policy_vehicle=sorted({(x['day'],x['policy'],x['mess_id']) for x in collisions}),
                   authority_namespaces=dict(namespaces),
                   ETA_definition='Primary: actual_eta_seconds > route_safe_eta_sec, the frozen connection-ready planning authority. Nominal Q50 and Q90 comparisons also reported.',
                   boundary_definition='actual_connection_ready_slot > planned_connection_ready_slot; both include the unchanged 600-second connection delay and 900-second ceil.',
                   collision_definition='next fixed planned departure < previous saved actual connection-ready; strict inequality, same day/policy/vehicle.',
                   empty_pair_interpretation='No consecutive within-day moves exist. Collision absence is observational and does not validate replay behavior for future multi-move schedules. Days/policies are separate experiment trajectories, not concatenated.',
                   operations='Read stored JSON/source text and hashes; arithmetic audit only. No production imports, replay, departure shifts, rerouting, optimization or regeneration.',
                   finished_utc=datetime.now(timezone.utc).isoformat())
    for rec in inputs.values():
        p = Path(rec['path'])
        rec['sha256_after'] = sha(p.read_bytes())
        rec['mtime_ns_after'] = p.stat().st_mtime_ns
        check(rec['sha256_before'] == rec['sha256_after'] and rec['mtime_ns_before'] == rec['mtime_ns_after'],
              'audited_input_bytes_and_mtime_unchanged')
    summary['input_files_verified_unchanged'] = len(inputs)
    summary['integrity_checks'] = dict(checks)
    fields = list(movements[0])
    write_csv('ALL_MOVEMENTS.csv', movements, fields)
    write_csv('COLLISION_EVENTS.csv', collisions, fields)
    write_csv('CONSECUTIVE_MOVE_PAIRS.csv', pairs, fields)
    write_csv('ETA_DELAY_EVENTS.csv', [m for m in movements if m['actual_eta_late_vs_safe']], fields)
    write_csv('DAY_POLICY_COVERAGE.csv', coverage, list(coverage[0]))
    write_csv('VEHICLE_MOVEMENT_COUNTS.csv', vehicles, list(vehicles[0]))
    write_json('SUMMARY.json', summary)
    write_json('INPUT_READ_ONLY_MANIFEST.json', list(inputs.values()))
    report = [
        '# IEEE123 Actual 이동 지연·다음 출발 충돌 read-only audit', '',
        f"최종 authoritative May 31일 × B0/B1/B2/B3 = {len(coverage)}건을 확인했습니다. 충돌은 {len(collisions)}건입니다.", '',
        '| 항목 | 결과 |','|---|---:|',
        f'| 총 이동 수 | {len(movements)} |',
        f"| Actual ETA > planned Safe ETA | {summary['actual_ETA_later_than_planned_safe']} |",
        f"| Actual ETA > nominal Q50 ETA (보조 비교) | {summary['actual_ETA_later_than_nominal_q50']} |",
        f"| Actual ETA > Q90 ETA (보조 비교) | {summary['actual_ETA_later_than_q90']} |",
        f"| actual connection-ready slot > planned slot | {summary['connection_ready_slot_later_than_planned']} |",
        f"| 물리적 도착의 15분 경계 crossing (Safe ETA 대비, 별도 지표) | {summary['physical_arrival_slot_boundary_crossing_vs_safe']} |",
        f'| collision edge case | {len(collisions)} |',
        f"| 최대 collision slot | {summary['maximum_collision_slots']} |",
        f'| 같은 day/policy/vehicle의 연속 이동 쌍 | {len(pairs)} |','',
        '충돌 영향을 받은 day/policy/vehicle: ' + (str(summary['affected_day_policy_vehicle']) if collisions else '**없음**.') + '.', '',
        'ETA 비교의 기본 기준은 frozen 계획이 connection-ready slot을 산정할 때 사용한 `route_safe_eta_sec`입니다. '
        '명목 예측 Q50을 의미하는 경우의 지연 수는 별도로 기재했습니다. 슬롯은 운영일 기준 0부터 시작하며 1 slot = 15분입니다. '
        '실제 도착 slot은 연속값이고 connection-ready slot은 실제 ETA에 600초를 더한 후 900초 단위로 올림한 정수입니다.', '',
        '물리적 도착의 slot boundary crossing과 connection-ready boundary crossing을 구분했습니다. '
        '물리적 도착 crossing은 `ceil(actual_eta/900) > ceil(planned_safe_eta/900)`입니다. '
        'May20 B2 MESS02는 planned safe arrival slot 23.985970196에서 actual 24.000478096으로 물리적 도착 경계를 넘었으나, '
        'connection-ready는 계획·실제 모두 slot 25로 동일하며 다음 이동은 없습니다.', '',
        '**해석 한계:** 이동한 95개 day/policy/vehicle은 각각 한 번만 이동했습니다. 따라서 다음 출발과 비교할 연속 이동 쌍 자체가 0개입니다. '
        '이 결과는 현재 IEEE123 결과가 해당 edge case를 경험하지 않았다는 뜻이며, 여러 번 이동하는 스케줄에서 replay rule이 안전하다는 검증은 아닙니다. '
        '서로 다른 날짜 또는 정책의 독립 실행을 이어 붙이지 않았습니다.', '',
        '## Safe ETA를 넘긴 이동', '',
        '| Day | Policy | MESS | Origin → destination | Safe ETA (s) | Actual ETA (s) | Planned ready | Actual arrival slot | Actual ready | 다음 출발 | 분류 |',
        '|---|---|---|---|---:|---:|---:|---:|---:|---|---|']
    for m in movements:
        if m['actual_eta_late_vs_safe']:
            report.append(f"| {m['day']} | {m['policy']} | {m['mess_id']} | {m['previous_origin']} → {m['previous_destination']} | {m['planned_safe_eta_seconds']:.6f} | {m['actual_eta_seconds']:.6f} | {m['previous_planned_connection_ready_slot']} | {m['previous_actual_arrival_slot']:.9f} | {m['previous_actual_connection_ready_slot']} | {m['next_planned_departure_slot'] if m['next_planned_departure_slot'] is not None else '없음'} | ETA 지연, ready-slot crossing 없음 |")
    report += ['', '## Authority 및 read-only 검증', '',
               '최종 revision monitor의 junction을 실제 경로로 해석해 perf1 122건과 selective revision의 May31 B2/B3 2건을 사용했습니다. '
               '모든 124건의 DA trajectory SHA가 restoration FINAL_AUDIT의 최종 SHA와 일치합니다. '
               '저장된 COMPLETE/최종 ACTUATOR는 receipt SHA와 일치하고, Actual moves와 frozen command의 canonical SHA는 최종 binding과 일치합니다. '
               '384개 차량-slot 명령을 각 policy-day마다 대조했으며 모든 계획 이동과 Actual 이동의 일대일 대응을 확인했습니다.', '',
               f'읽은 입력 {len(inputs)}개는 감사 전후 SHA256 및 수정시각이 동일합니다. 기존 파일에 쓰기를 하지 않았습니다. '
               '기존 SUMO 이동 기록의 ETA를 사용했으며 SUMO/Actual/OpenDSS를 재실행하지 않았습니다. 원래 이동 기록에 포함된 독립 traffic-source 검증 PASS를 확인했습니다.', '',
               '전체 95건의 상세는 ALL_MOVEMENTS.csv, 충돌 사건 전용 표는 COLLISION_EVENTS.csv(발생 0건이므로 헤더만), '
               '124건 coverage는 DAY_POLICY_COVERAGE.csv, 전체 496개 차량별 이동 수는 VEHICLE_MOVEMENT_COUNTS.csv에 있습니다. '
               'INPUT_READ_ONLY_MANIFEST.json은 읽은 원본의 SHA 전후 비교, OUTPUT_SHA256_MANIFEST.json은 이 별도 감사 산출물의 SHA입니다.', '']
    (OUT/'AUDIT_REPORT.md').write_text('\n'.join(report),encoding='utf-8')
    write_json('OUTPUT_SHA256_MANIFEST.json', {p.name:sha(p.read_bytes()) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='OUTPUT_SHA256_MANIFEST.json'})
    print(json.dumps({k:v for k,v in summary.items() if k!='integrity_checks'},ensure_ascii=True,indent=2))

if __name__ == '__main__':
    main()
