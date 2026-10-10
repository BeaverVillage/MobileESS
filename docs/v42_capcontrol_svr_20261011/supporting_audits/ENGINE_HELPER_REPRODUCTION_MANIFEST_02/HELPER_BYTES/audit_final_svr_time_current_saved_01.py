"""Independently recompute saved SVR4/7 controls, native TIME and current bases.

Only file reads; never creates an OpenDSS engine or invokes a native optimizer.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import numpy as np

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def record(path):
    p = Path(path).resolve()
    data = p.read_bytes()
    return {'path': str(p), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def same(a, b):
    return Path(a['path']).resolve() == Path(b['path']).resolve() and all(a[k] == b[k] for k in ('sha256', 'bytes'))

def static_reg(row):
    return {k: v for k, v in row.items() if k != 'initial_tap' and k != 'resolved_properties'} | {
        'resolved_properties': {k: v for k, v in row['resolved_properties'].items() if k != 'TapNum'}}

def main(args):
    sys.path.insert(0, str(Path(args.source).resolve()))
    from v42_voltage_control.authority import source_files
    from v42_b3_joint.contracts import digest
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_before = source_files()
    dispatch = read(root/'DISPATCH_SOURCE_RECEIPT.json')
    checks, evidence, summaries, slots_csv, bases_csv = [], {}, [], [], []
    def require(value, name):
        checks.append({'check': name, 'PASS': bool(value)})
    def checked(item):
        actual = record(item['path'])
        require(same(item, actual), 'receipt_' + actual['path'])
        evidence[actual['path'].casefold()] = actual
        return Path(actual['path'])
    require(source_before == dispatch['source_map'], 'source_map_matches_dispatch')
    require(digest(source_before) == dispatch['source_SHA'], 'source_digest_matches_dispatch')
    for cfg in ('SVR4', 'SVR7'):
        infra_path = checked(dispatch['infrastructure'][cfg])
        infra = read(infra_path)
        scenario = read(checked(infra['scenario']))
        namespaces = {}
        for namespace_row in infra['independent_namespaces']:
            doc = read(checked(namespace_row['initial_state_receipt']))
            require(digest(doc['initial_state']) == doc['initial_state_SHA'] == namespace_row['initial_state_SHA'], cfg + '_initial_state_' + doc['namespace'])
            namespaces[doc['namespace']] = doc
        require(namespaces['ACTUAL']['initial_state'] == namespaces['DAYAHEAD']['initial_state'], cfg + '_independent_namespace_same_source_initial_state')
        initial = namespaces['ACTUAL']['initial_state']
        equipment = initial['installed_equipment_after']
        expected_regs = [static_reg(r) for r in initial['original_initial_inventory']['regulators']]
        expected_added = [static_reg(r) for r in initial['installed_inventory']['regulators'] if r['name'] not in {x['name'] for x in expected_regs}]
        expected_caps = initial['original_initial_inventory']['capacitors']
        require(len(expected_regs) == 7 and len(expected_added) == (12 if cfg == 'SVR4' else 21), cfg + '_native_reg_inventory_count')
        require(initial['native_clock']['Hour'] == 0 and initial['native_clock']['Seconds'] == 0 and initial['native_clock']['queue'] == [], cfg + '_initial_TIME0_empty_queue')
        require(all(r['initial_tap'] == 1 for r in initial['original_initial_inventory']['regulators']), cfg + '_original_seven_initial_taps_one')
        require(all(all(t == 1 for t in taps) for taps in initial['new_SVR_initial_winding_taps'].values()), cfg + '_new_windings_initial_taps_one')
        for arm, day in [('B2', '2025-05-01'), ('B1', '2025-05-28')]:
            folder = root/cfg/'days'/arm/day
            result_path = folder/'AC_ONLY_DAY_RESULT.json'
            if not result_path.exists():
                raise RuntimeError('KNOWN_DAY_NOT_TERMINAL: ' + str(result_path))
            result = read(result_path)
            checked(record(result_path))
            key = f'{cfg}/{arm}/{day}'
            require(result['source_SHA'] == dispatch['source_SHA'] and result['scenario_SHA'] == scenario['scenario_SHA'], key + '_source_scenario_exact')
            require(result['Native_optimizer_calls'] == 0 and result['Actual_PQ_repair'] == 0 and result['new_model_E2E_qualified'] is False, key + '_AC_only_no_optimizer_or_repair')
            audit = read(checked(result['physical_audit']))
            rows = read(checked(audit['slots_receipt']))
            global_events = read(checked(audit['physical_solve_events_receipt']))
            require([r['slot'] for r in rows] == list(range(96)), key + '_literal_96_chronological_slots')
            require(audit['source_initial_controls'] == initial['original_initial_inventory'], key + '_fresh_original_initial_controls')
            require(audit['namespace'] == 'ACTUAL' and audit['new_engine_from_original_Source_Initial_State'] and audit['independent_state_per_namespace'] and audit['Planning_Tap_or_Cap_state_transfer_to_Actual'] is False, key + '_independent_actual_context_no_copy')
            require(audit['Original_Source_SHA_before_after_equal'] and audit['original_input_setpoints_unchanged'] and audit['original_physical_ratings_changed'] is False, key + '_source_inputs_ratings_unchanged')
            control_ok = True
            for event in global_events:
                c = event['controls']
                control_ok &= (event['completed'] and c['solution_converged'] and c['ControlActionsDone'] and c['control_mode'] == 2
                    and c['configured_MaxControlIterations'] == 100 and c['configured_MaxIterations'] == 15
                    and [static_reg(r) for r in c['original_regulators']] == expected_regs
                    and [static_reg(r) for r in c['added_regulators']] == expected_added
                    and c['capacitors'] == expected_caps and c['capcontrols'] == [])
            require(control_ok, key + '_all_physical_solves_original7_and_caps_exact_static_parameters')
            initial_events = sum(e['kind'] == 'ORIGINAL_SLOT_INITIAL_SOLVE' for e in global_events)
            extra_events = sum(e['kind'] == 'NATIVE_TIME_QUEUE_SOLVE' for e in global_events)
            require(initial_events == 96 and extra_events + initial_events == audit['completed_physical_SolveSnap_count'] == audit['total_physical_SolveSnap_count'], key + '_native_call_count_independently_matched')
            total_extra = 0
            clock_ok = True
            current_ok, voltage_ok, kva_ok, raw_ok = True, True, True, True
            max_native_error = max_nameplate_error = max_kva_error = max_raw_error = 0.0
            max_nameplate = max_native = max_kva = 0.0
            raw = np.load(checked(result['raw_AC']), allow_pickle=False)
            axis = [str(x) for x in raw['node_names']]
            require(raw['voltage_pu'].shape == (96, 386) and len(axis) == 386, key + '_raw_original_96x386_axis')
            for row in rows:
                slot = row['slot']
                t = row['time_control']
                events = t['events']
                clock_ok &= (row['namespace'] == 'ACTUAL' and row['arm'] == arm and row['day'] == day
                    and row['original_input_setpoints_unchanged'] and t['namespace'] == 'ACTUAL'
                    and t['start_seconds'] == slot*900 and t['end_seconds'] == (slot+1)*900
                    and t['physical_elapsed_seconds'] == 900 and t['iteration_to_seconds_conversion'] is False
                    and t['manual_tap_or_cap_actions'] == 0 and t['converged'] and t['PASS']
                    and events[0]['absolute_seconds'] == slot*900 and events[0]['kind'] == 'INITIAL_ALREADY_COMPLETED'
                    and len(events) == 1+t['extra_SolveSnap_count'] == t['physical_solve_count'])
                for previous, event in zip(events, events[1:]):
                    pending = previous['pending_queue']
                    clock_ok &= (bool(pending) and event['kind'] == 'NATIVE_QUEUED_EVENT'
                        and event['absolute_seconds'] == min(q['absolute_seconds'] for q in pending)
                        and event['absolute_seconds'] < t['end_seconds'])
                for event in events:
                    clock_ok &= (event['solution_converged'] and event['control_actions_done_as_of_current_time']
                        and all(q['absolute_seconds'] > event['absolute_seconds'] for q in event['pending_queue']))
                clock_ok &= (t['queue_carried_to_next_slot'] == events[-1]['pending_queue']
                    and all(q['absolute_seconds'] >= t['end_seconds'] for q in t['queue_carried_to_next_slot'])
                    and t['last_solve_seconds'] == events[-1]['absolute_seconds']
                    and t['unsolved_hold_seconds'] == t['end_seconds'] - t['last_solve_seconds'])
                total_extra += t['extra_SolveSnap_count']
                physical = row['physical']
                voltages = {n['node_phase']: n['voltage_pu'] for n in physical['nodes']}
                raw_error = max(abs(voltages[n] - float(v)) for n, v in zip(axis, raw['voltage_pu'][slot]))
                max_raw_error = max(max_raw_error, raw_error)
                raw_ok &= raw_error == 0
                voltage_ok &= all(.95 <= v <= 1.05 for v in voltages.values())
                tx_phases = {}
                for c in physical['currents']:
                    if c['element'].startswith('transformer.'):
                        tx_phases.setdefault((c['element'], c['terminal']), set()).add(c['phase'])
                for c in physical['currents']:
                    e = c['element']
                    current, normal = c['current_A'], c['NormalAmps']
                    error = abs(c['loading_pu'] - current/normal)
                    max_native_error = max(max_native_error, error)
                    max_native = max(max_native, current/normal)
                    current_ok &= math.isfinite(current) and current >= 0 and normal > 0 and error <= 1e-12 and current/normal <= 1
                    if e.startswith('transformer.'):
                        spec = equipment[e]
                        winding = spec['windings'][c['terminal']-1]
                        phases = len(tx_phases[(e, c['terminal'])])
                        denominator = winding['kVA']/((math.sqrt(3) if phases >= 2 else 1)*winding['kV'])
                        nameplate_error = abs(c['nameplate_current_A'] - denominator)
                        loading_error = abs(c['nameplate_current_loading_pu'] - current/denominator)
                        max_nameplate_error = max(max_nameplate_error, nameplate_error, loading_error)
                        native_expected = float(spec['properties']['NormAmps'])*spec['windings'][0]['kV']/winding['kV']
                        current_ok &= abs(normal-native_expected) <= 1e-9*max(1, normal)
                        current_ok &= nameplate_error <= 1e-9*max(1, denominator) and loading_error <= 1e-12 and current/denominator <= 1
                        max_nameplate = max(max_nameplate, current/denominator)
                        if slot == 0:
                            bases_csv.append(dict(configuration=cfg, arm=arm, day=day, element=e, terminal=c['terminal'], phase=c['phase'],
                                original=c['original'], winding_kVA=winding['kVA'], winding_kV=winding['kV'], winding_phases=phases,
                                native_NormalAmps=normal, independently_recomputed_nameplate_A=denominator,
                                saved_nameplate_A=c['nameplate_current_A'], current_A=current,
                                native_loading=current/normal, nameplate_loading=current/denominator))
                for tx in physical['transformers']:
                    rating = equipment[tx['element']]['windings'][tx['terminal']-1]['kVA']
                    error = abs(tx['loading_pu'] - tx['kVA']/rating)
                    max_kva_error = max(max_kva_error, error)
                    kva_ok &= tx['rating_kVA'] == rating and error <= 1e-12 and tx['kVA']/rating <= 1
                    max_kva = max(max_kva, tx['kVA']/rating)
                slots_csv.append(dict(configuration=cfg, arm=arm, day=day, slot_0based=slot,
                    native_start_seconds=t['start_seconds'], native_end_seconds=t['end_seconds'],
                    last_electrical_solve_seconds=t['last_solve_seconds'], held_seconds=t['unsolved_hold_seconds'],
                    native_solve_count=t['physical_solve_count'], due_queue_events=t['extra_SolveSnap_count'],
                    queue_carried=len(t['queue_carried_to_next_slot']),
                    Vmin=physical['voltage_min_pu'], Vmax=physical['voltage_max_pu'],
                    original_reg_taps=json.dumps(row['settled_original_controls']['taps']), caps_fixed_ON=True))
            require(clock_ok and total_extra == extra_events == audit['additional_time_queue_solve_count'], key + '_every_earliest_due_timestamp_and_boundary_carry_verified')
            require(current_ok, key + '_all_both_terminal_native_and_nameplate_currents_recomputed')
            require(kva_ok, key + '_all_winding_nameplate_kVA_loadings_recomputed')
            require(voltage_ok and raw_ok, key + '_old_raw_and_all_added_voltages_exact_and_in_band')
            summaries.append(dict(configuration=cfg, arm=arm, day=day, status=result['status'], native_solve_count=len(global_events),
                initial_solves=initial_events, due_event_solves=extra_events, all_node_phases=len(rows[0]['physical']['nodes']),
                max_native_current_loading=max_native, max_nameplate_current_loading=max_nameplate, max_winding_kVA_loading=max_kva,
                max_native_current_arithmetic_error=max_native_error, max_nameplate_arithmetic_error=max_nameplate_error,
                max_kVA_arithmetic_error=max_kva_error, max_original_voltage_raw_error=max_raw_error,
                Vmin=result['metric']['Vmin'], Vmax=result['metric']['Vmax'],
                continuous_transient_certification=False, new_E2E_qualified=False))
            raw.close()
    require(source_files() == source_before, 'source_map_exact_after')
    for item in list(evidence.values()):
        require(same(item, record(item['path'])), 'evidence_unchanged_after_' + item['path'])
    for filename, rows in [('KNOWN_DATE_SUMMARY.csv', summaries), ('NATIVE_TIME_96SLOT_AUDIT.csv', slots_csv), ('BOTH_TERMINAL_CURRENT_BASE_AUDIT.csv', bases_csv)]:
        with (output/filename).open('x', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    shutil.copyfile(__file__, output/'AUDIT_SCRIPT_USED.py')
    result = dict(schema='V42_FINAL_SVR_TIME_CURRENT_SAVED_AUDIT_V1', created_UTC=datetime.now(timezone.utc).isoformat(),
        PASS=all(x['PASS'] for x in checks), scope='EXISTING_FROZEN_PLAN_ACTUAL_ONLY; NEW_E2E_NOT_RUN',
        source_SHA=dispatch['source_SHA'], evidence=list(evidence.values()), checks=checks, summaries=summaries,
        audit_script=record(output/'AUDIT_SCRIPT_USED.py'), source_or_tests_modified=False,
        Native_optimizer_calls=0, OpenDSS_calls=0, physical_jobs_launched=0,
        future_Actual_information_used_by_control_law=0,
        future_information_claim_basis='Native unchanged RegControl settings plus frozen SVR native law sample only current engine; chronology/due timestamps verified. Original full saved Actual inventory used for replay scheduling is not a new forecast or holdout claim.',
        current_basis='Transformer winding kVA/(sqrt(3)*kV) for three-phase; kVA/kV for single-phase. No extra factor1000. Native NormAmps retained and independently checked.',
        measurement_limit='96 slot-end full-network states; queue-driven electrical events are sampled, but inter-event continuous waveform/thermal transient certification and regenerated Planning E2E have not run.')
    (output/'FINAL_SVR_TIME_CURRENT_READONLY_AUDIT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'PASS': result['PASS'], 'cases': len(summaries), 'checks': len(checks), 'output': str(output)}))
    if not result['PASS']:
        print(json.dumps([c for c in checks if not c['PASS']]))
        return 1
    return 0

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', default='D:/v42voltage')
    p.add_argument('--root', required=True)
    p.add_argument('--output', required=True)
    raise SystemExit(main(p.parse_args()))
