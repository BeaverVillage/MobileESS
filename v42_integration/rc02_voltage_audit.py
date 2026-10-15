"""RC02 causal diagnostics, without changing RC01 controller or physical cores.

The ablations reuse *observed* episode intervals retrospectively. They are
neither new dispatches nor production/campaign performance claims.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import csv
import gzip
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np

from .unified_contract import digest
from .actual_validation import read, record

AEST = timezone(timedelta(hours=10))
SCOPE = 'RC02_FIXED_PR223_M2_CAUSAL_VOLTAGE_ABLATION_NOT_PRODUCTION'
LABELS = ('E0', 'E1', 'E2', 'E3')


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def _finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('RC02_FINITE_TIME_OR_QUANTITY_REQUIRED')
    return value


def time_fields(begin, native_seconds):
    """Native seconds are explicit physical time, never control iterations."""
    native_seconds = _finite(native_seconds)
    if native_seconds < 0:
        raise ValueError('RC02_NEGATIVE_NATIVE_TIME')
    absolute = _finite(begin) + native_seconds
    return dict(native_seconds=native_seconds, native_slot=int(native_seconds // 900),
                absolute_epoch_seconds=absolute,
                local_time_AEST=datetime.fromtimestamp(absolute, AEST).isoformat(),
                before_May01_begin=absolute < begin,
                physical_time_source='NATIVE_HOUR_TIMES_3600_PLUS_SECONDS',
                iteration_to_seconds_conversion=False)


def episode_roster(initial, queue_rows, start_rows, *, label, begin, end):
    """Join existing observed executions; never infer or reschedule a start."""
    if label not in LABELS:
        raise ValueError('RC02_EXPERIMENT_LABEL_REQUIRED')
    begin, end = _finite(begin), _finite(end)
    if end <= begin:
        raise ValueError('RC02_POSITIVE_WINDOW_REQUIRED')
    queues = {r['job_uid']: r for r in queue_rows}
    starts = {r['uid']: r for r in start_rows}
    if len(queues) != len(queue_rows) or len(starts) != len(start_rows):
        raise ValueError('RC02_DUPLICATE_UID')
    initial_uids = {r['uid'] for r in initial['running']}
    if len(initial_uids) != len(initial['running']) or initial_uids & starts.keys():
        raise ValueError('RC02_INITIAL_RUNNING_RESTARTED')
    chosen = set(initial_uids)
    if label != 'E0':
        chosen.update(uid for uid, row in starts.items()
                      if label in ('E2', 'E3') or row['origin_unknown'] is False)
    result = []
    for uid in sorted(chosen):
        q = queues[uid]
        start = _finite(q['admitted_time'])
        finish = end if q['completion_observed_time'] is None else _finite(q['completion_observed_time'])
        if finish < start or q.get('migration_count') != 0:
            raise ValueError('RC02_NONSTATIC_OR_INVALID_OBSERVED_EPISODE')
        gpu = _finite(q['GPU_gang'])
        if gpu <= 0 or not gpu.is_integer():
            raise ValueError('RC02_WHOLE_GPU_GANG_REQUIRED')
        if uid in initial_uids:
            original = next(r for r in initial['running'] if r['uid'] == uid)
            if (start, q['site'], gpu) != (original['observed_start_seconds'], original['site'], original['gpu']):
                raise ValueError('RC02_INITIAL_RUNNING_SOURCE_DRIFT')
            if not start <= begin or finish <= begin:
                raise ValueError('RC02_INITIAL_RUNNING_BOUNDARY_DRIFT')
            origin = 'INITIAL_RUNNING'
        else:
            row = starts[uid]
            if (start, q['site'], gpu, q['origin_unknown']) != (
                    row['time_seconds'], row['site'], row['GPU'], row['origin_unknown']):
                raise ValueError('RC02_ACTUAL_START_LEDGER_DRIFT')
            if not begin <= start < end:
                raise ValueError('RC02_START_OUTSIDE_EVALUATION')
            origin = 'NEW_UNKNOWN' if row['origin_unknown'] else 'NEW_KNOWN'
        result.append(dict(uid=uid, site=q['site'], GPU=gpu, start_seconds=start,
                           observed_completion_seconds=None if q['completion_observed_time'] is None else finish,
                           finish_for_integration_seconds=finish, origin=origin))
    executed = {r['job_uid'] for r in queue_rows if r['admitted_time'] is not None}
    if executed != initial_uids | starts.keys():
        raise ValueError('RC02_UNEXPLAINED_EXECUTED_EPISODE')
    return result


def integrated_gpu(episodes, sites, begin, slots=16):
    sites = tuple(sites)
    if len(sites) != len(set(sites)):
        raise ValueError('RC02_DUPLICATE_SITE')
    gpu = np.zeros((slots, len(sites)))
    for job in episodes:
        j = sites.index(job['site'])
        for t in range(slots):
            start, end = begin + t * 900, begin + (t + 1) * 900
            overlap = max(0., min(end, job['finish_for_integration_seconds']) - max(start, job['start_seconds']))
            gpu[t, j] += job['GPU'] * overlap / 900
    return gpu


def experiment_inputs(episodes, reference_prefix, sites, power_model):
    begin = reference_prefix[0]['start_seconds']
    gpu = integrated_gpu(episodes, sites, begin, len(reference_prefix))
    rows = []
    for t, original in enumerate(reference_prefix):
        if original['slot'] != t or original['start_seconds'] != begin + t * 900:
            raise ValueError('RC02_NONCONTIGUOUS_SOURCE_PREFIX')
        observations = deepcopy(original['observations'])
        power = power_model.recompute(gpu[t:t+1], sites, [observations['weather']['values']])
        rows.append(dict(slot=t, start_seconds=begin+t*900, end_seconds=begin+(t+1)*900,
                         GPU=gpu[t].tolist(), P=power['PCC_P_kw'][0].tolist(),
                         Q=power['PCC_Q_kvar'][0].tolist(), observations=observations,
                         authority='RETROSPECTIVE_OBSERVED_EPISODE_ABLATION_ORIGINAL_C1'))
    return rows


def violation_cells(row, following_time, begin, inputs, mess):
    """Every failing node/phase, linked to full native physical/control proof."""
    t = row['slot']
    fields = time_fields(begin, row['native_seconds'])
    hold = _finite(following_time) - row['native_seconds']
    if hold < 0:
        raise ValueError('RC02_PHYSICAL_TIME_BACKWARDS')
    result = []
    for node in row['physical']['nodes']:
        voltage = _finite(node['voltage_pu'])
        if .95 <= voltage <= 1.05:
            continue
        name = node['node_phase']
        bus, phase = name.rsplit('.', 1)
        result.append(dict(experiment=row['experiment'], slot=t, **fields,
            physical_hold_until_native_seconds=following_time, physical_hold_seconds=hold,
            node=name, bus=bus, phase=phase, voltage_pu=voltage,
            lower_pu=.95, upper_pu=1.05, event_kind=row['event']['kind'],
            control_iterations=row['event']['control_iterations'], electrical_iterations=row['event']['electrical_iterations'],
            physical_time_evaluation=True, internal_iteration_sample=False,
            solution_converged=row['event']['solution_converged'],
            AIDC_P_kw=inputs[t]['P'], AIDC_Q_kvar=inputs[t]['Q'], AIDC_GPU=inputs[t]['GPU'],
            MESS_P_kw={s: v[t] for s, v in mess['P_by_site'].items()},
            MESS_Q_kvar={s: v[t] for s, v in mess['Q_by_site'].items()},
            background=inputs[t]['observations'],
            control_context_sha=row['control_context_sha'], physical_sha=row['physical_sha'],
            SVR_sha=row['SVR_sha'], native_step=row['native_step'],
            load_change_event='SLOT_INPUT_CHANGE' if row['event']['kind']=='SLOT_INPUT_SAMPLE_AND_DUE_ACTIONS' else 'NO_INJECTION_CHANGE_NATIVE_QUEUED_CONTROL'))
    return result


def write_csv(path, rows):
    if not rows:
        fields = ['experiment','slot','native_seconds','node','voltage_pu']
    else:
        fields = list(rows[0])
    with Path(path).open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict,list,tuple)) else v
                             for k,v in row.items()})


def replay(inputs, mess, *, label, scenario, output, capture_prefix=True, current=None):
    """One fresh source engine, chronological queue carry, unchanged native AUTO.

    With current supplied the past prefix is replayed and exactly one current
    SolveSnap is measured. capture_prefix=False retains every original solve,
    convergence, due-queue and clock check. It is an equivalence experiment,
    never a substitute for the separately preserved full-prefix proof.
    """
    from v42_regcontrol import authority
    from v42_regcontrol.runner import background
    from v42_voltage_control.timecontrol import CommonClock, seconds, queue
    from v42_voltage_control.integration import _equipment, measure_full_network, assert_control_inventory
    from v42_voltage_control.svr import install
    from .actual_validation import mess_service_bindings

    began = perf_counter()
    begin = (inputs or [current])[0]['start_seconds']
    if current is not None:
        begin = current['start_seconds'] - current['slot'] * 900
    all_inputs = inputs + ([] if current is None else [current])
    source = authority.source()
    stamps = [datetime.fromtimestamp(begin+(t+1)*900, AEST).isoformat() for t in range(96)]
    demand = [all_inputs[min(t,len(all_inputs)-1)]['observations']['demand']['values']['demand_mw'] for t in range(96)]
    pv = [all_inputs[min(t,len(all_inputs)-1)]['observations']['pv']['values']['pv_mw'] for t in range(96)]
    bg = background(stamps, demand, pv)
    from dayahead.v28r2.opendss_mapping import _set_generator, _set_load, mess_injection_mapping
    from .partial_canary import resource_snapshot
    resource_before = resource_snapshot()
    if (resource_before['memory']['AvailableMBytes'] < 8192 or
            resource_before['memory']['PercentCommittedBytesInUse'] >= 75):
        raise RuntimeError('RC02_RAM_8GB_COMMIT_75_GATE')
    engine, adapter, _ = authority.compile_verified()
    rows, slots, contexts, boundaries, cells = [], [], {}, [], []
    compile_seconds = perf_counter()-began
    raw_path = Path(output) / f'{label}_ALL_SUBSTEPS.json.gz'
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists():
        raise FileExistsError('RC02_RAW_MUST_NOT_OVERWRITE')
    stream = gzip.open(raw_path, 'xt', encoding='utf-8')
    stream.write('[')
    node_voltages, phase_line_currents = [], []
    node_axis = current_axis = None
    summary = None
    try:
        equipment = _equipment(engine)
        nodes = {n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in {'1','2','3'}}
        native = source['NativeAllocation'].from_adapter(adapter)
        native.validate_native_engine(engine)
        svrs = install(engine, scenario['svr'])
        clock = CommonClock('ACTUAL', '2025-05-01')
        binding = clock.bind(engine)
        initial_inventory = source['inventory'](engine)
        assert_control_inventory(initial_inventory, scenario, initial=True)
        aliases, _ = mess_service_bindings(source, mess['P_by_site'])
        if len(aliases) != 24:
            raise ValueError('RC02_ALL_24_MESS_SERVICE_SITES_REQUIRED')

        def apply(point):
            t = point['slot']
            native.apply(engine, bg, t)
            for item in adapter['pv_generators']:
                loc = (str(item['bus']).lower(), 'ABC'[int(item['phase'])-1])
                _set_generator(engine, item['generator_name'], bg.pv_generation_kw_96[t].get(loc,0), 0)
            for j in range(12):
                _set_load(engine, f'IDC_IDC{j+1:02d}', point['P'][j], point['Q'][j])
            for site, names in aliases.items():
                inj = mess_injection_mapping(mess['P_by_site'][site][t], mess['Q_by_site'][site][t])
                _set_generator(engine, names['generator'], inj['generator_p_kw'], inj['generator_q_kvar'])
                _set_load(engine, names['load'], inj['charging_load_p_kw'], inj['charging_load_q_kvar'])

        active_slot = None
        def observe(event):
            nonlocal node_axis, current_axis
            physical = measure_full_network(engine, nodes, equipment)
            hardware = svrs.measure()
            inventory = source['inventory'](engine)
            assert_control_inventory(inventory, scenario)
            context = dict(inventory=inventory, SVR=hardware, event=event,
                           native_seconds=seconds(engine), slot=active_slot)
            context_sha = digest(context)
            contexts[context_sha] = context
            row = dict(experiment=label, slot=active_slot, native_step=len(rows),
                       **time_fields(begin, seconds(engine)), event=deepcopy(event),
                       physical=physical, SVR=hardware, control_context_sha=context_sha,
                       physical_sha=digest(physical), SVR_sha=digest(hardware),
                       PASS=bool(physical['PASS'] and hardware['hardware_PASS'] and hardware['added_nodes_voltage_PASS']))
            if rows:
                stream.write(',')
            json.dump(row, stream, ensure_ascii=False, allow_nan=False)
            now_nodes = [r['node_phase'] for r in physical['nodes']]
            now_currents = [f"{r['element']}:{r.get('terminal')}:{r.get('conductor')}:{i}" for i,r in enumerate(physical['currents'])]
            if node_axis is None:
                node_axis, current_axis = now_nodes, now_currents
            elif node_axis != now_nodes or current_axis != now_currents:
                raise ValueError('RC02_PHYSICAL_AXES_DRIFT')
            node_voltages.append([r['voltage_pu'] for r in physical['nodes']])
            phase_line_currents.append([r['loading_pu'] for r in physical['currents']])
            rows.append({k:v for k,v in row.items() if k not in ('physical','SVR')}
                        | dict(voltage_min_pu=physical['voltage_min_pu'], voltage_max_pu=physical['voltage_max_pu'],
                               voltage_violation_cells=physical['voltage_violation_cells'],
                               voltage_nodes=[r for r in physical['nodes'] if r['voltage_pu']<.95 or r['voltage_pu']>1.05]))
            # Store only the small voltage subset; full physical remains in gzip.
            rows[-1]['physical'] = {'nodes': rows[-1]['voltage_nodes']}

        previous_end = None
        for point in inputs:
            active_slot = int(point['slot'])
            before_queue = queue(engine)
            before_inventory = source['inventory'](engine)
            before_time = seconds(engine)
            if previous_end is not None:
                if (before_queue, before_inventory, before_time) != previous_end:
                    raise ValueError('RC02_QUEUE_OR_TAP_RESET_BETWEEN_SLOTS')
            apply(point)
            after_inventory = source['inventory'](engine)
            if before_inventory != after_inventory or before_queue != queue(engine):
                raise ValueError('RC02_INJECTION_MAPPING_MUTATED_CONTROL_STATE')
            boundaries.append(dict(slot=active_slot, native_seconds=before_time,
                queue_before_inputs=before_queue, queue_after_inputs=queue(engine),
                inventory_before_sha=digest(before_inventory), inventory_after_sha=digest(after_inventory),
                previous_boundary_exact_match=previous_end is not None,
                input_sha=digest(point), source_static_interval_end_label=stamps[active_slot],
                scalar_observation_asof_epoch=point['start_seconds']))
            slot_proof = clock.settle_slot(engine, active_slot, observer=observe if capture_prefix else None,
                                          capture_events=capture_prefix)
            slots.append(slot_proof)
            previous_end = (queue(engine), source['inventory'](engine), seconds(engine))
        if current is not None:
            active_slot = int(current['slot'])
            apply(current)
            if seconds(engine) != active_slot*900:
                raise ValueError('RC02_CURRENT_CLOCK_DRIFT')
            engine.Solution.SolveSnap()
            pending = queue(engine)
            if (not engine.Solution.Converged() or not engine.Solution.ControlActionsDone()
                    or any(r['absolute_seconds']<=seconds(engine) for r in pending)):
                raise ValueError('RC02_CURRENT_CONVERGENCE_OR_DUE_QUEUE')
            observe(dict(kind='CURRENT_CANDIDATE_ONLY_NO_FUTURE_TAP_EXECUTION', absolute_seconds=seconds(engine),
                solution_converged=True, control_actions_done_as_of_current_time=True,
                control_iterations=int(engine.Solution.ControlIterations()), electrical_iterations=int(engine.Solution.Iterations()),
                pending_queue=pending, native_event_log=list(engine.Solution.EventLog())))
        for i, row in enumerate(rows):
            following = rows[i+1]['native_seconds'] if i+1<len(rows) else (row['slot']+1)*900
            if current is not None and i+1==len(rows):
                following = row['native_seconds']  # admission point, no future hold claim
            cells.extend(violation_cells(row, following, begin, all_inputs, mess))
        failures = [r for r in rows if not r['PASS']]
        summary = dict(scope=SCOPE, experiment=label, status='PHYSICAL_FAIL' if failures else 'PASS_MEASURED_SCOPE',
            capture_prefix=capture_prefix, current_only_measurement=current is not None and not capture_prefix,
            measured_substeps=len(rows), full_original_physical_solve_count=clock.total_physical_solve_count+(current is not None),
            violating_substeps=len(failures), voltage_violation_cells=len(cells),
            voltage_min_pu=min(r['voltage_min_pu'] for r in rows), voltage_max_pu=max(r['voltage_max_pu'] for r in rows),
            all_measured_times_May01_or_later=all(not r['before_May01_begin'] for r in rows),
            physical_time_samples_not_internal_iterations=True, limits=[.95,1.05],
            initial_clock=binding, initial_inventory_sha=digest(initial_inventory),
            source_original_RegControl_count=7, added_SVR_units=11,
            all_24_fixed_MESS_service_sites=True, MESS_plan_sha=mess['plan_sha'],
            no_tap_or_queue_reset_between_slots=True, control_parameter_invariance_checked_every_substep=True,
            boundary_queue_carried=True, observed_inputs_sha=digest(inputs),
            compile_and_setup_seconds=compile_seconds, total_wall_seconds=perf_counter()-began,
            current_physical_sha=None if current is None else rows[-1]['physical_sha'],
            current_SVR_sha=None if current is None else rows[-1]['SVR_sha'],
            last_solve_per_slot=[next((r for r in reversed(rows) if r['slot']==p['slot']), None) for p in slots],
            original_common_clock=True, manual_control_actions=0, Native_calls=0,
            resource_before_engine=resource_before,
            future_controller_inputs=False, retrospective_ablation_not_new_controller_result=True)
    finally:
        stream.write(']')
        stream.close()
        engine.Basic.ClearAll()
    contexts_path = Path(output)/f'{label}_CONTROL_CONTEXTS.json.gz'
    with gzip.open(contexts_path, 'xt', encoding='utf-8') as context_stream:
        json.dump(contexts, context_stream, ensure_ascii=False, allow_nan=False)
    write_new(Path(output)/f'{label}_TIME_QUEUE_AUDIT.json', dict(boundaries=boundaries, slot_proofs=slots))
    write_new(Path(output)/f'{label}_STEP_INDEX.json', rows)
    write_csv(Path(output)/f'{label}_VOLTAGE_VIOLATION_CELLS.csv', cells)
    np.savez_compressed(Path(output)/f'{label}_PHYSICAL_ARRAYS.npz',
        native_seconds=np.array([r['native_seconds'] for r in rows]),
        nodes=np.array(node_axis), voltage_pu=np.array(node_voltages),
        current_axis=np.array(current_axis), loading_pu=np.array(phase_line_currents))
    summary.update(raw=record(raw_path), control_contexts=record(contexts_path),
                   cell_csv=record(Path(output)/f'{label}_VOLTAGE_VIOLATION_CELLS.csv'))
    write_new(Path(output)/f'{label}_SUMMARY.json', summary)
    return summary
