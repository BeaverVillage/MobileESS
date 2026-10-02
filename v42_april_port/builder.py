"""Port construction interfaces, never historical eligibility or May values.

Known request/state inputs and Actual observations are separate arguments.
Unknown arrivals become observable at submission, never enter Planning.
Incomplete rows remain in both the population and a failing input gate.
"""
from datetime import datetime, timedelta, timezone
import math
import re
from v42_final.common import MODEL
from v42_final.native_inputs import memory_mib
from v42_final.state import planning_remaining
from v42_april_b0_v2.recovery import positive_integer, recover_gpu
from v42_april_b0_v2.contracts import digest, ZERO_ACTIONS
from v42_april_b0_v2.reference import build_reference

SCHEMA = 'V42_DAY_INPUT_BUNDLE_V1'
BASE = 'c0783fadbbca282f2ce580c45fe82feaed71584c'
B0_FLAGS = dict(AIDC_PRESENT=True, AIDC_WORKLOAD_PRESENT=True, ML_RUNTIME_USED=True,
                AIDC_FLEX_OPTIMIZATION=False, MESS_ACTIVE=False,
                timeshift_optimization=False, migration_optimization=False,
                prestart_relocation_optimization=False, grid_aware_site_allocation=False,
                P_MESS=0, Q_MESS=0, movement=0, MESS_optimization_calls=0,
                B1_RUN=False, B2_RUN=False, B3_RUN=False, MAY_RUN=False,
                M1_BENDERS_RUN=False, M1_PRODUCTION_RUN=False, A2_M2_PRODUCTION_RUN=False,
                OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True, DA_AC_OPERATIONAL_GATE=False,
                FINAL_MARGIN_ACCEPTED=False, historical_requested_walltime_fallback=False,
                **dict.fromkeys(ZERO_ACTIONS, 0))


def timestamp(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)


def axis(day):
    start = datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=10)))
    if start.strftime('%Y-%m-%d') != day:
        raise ValueError('CANONICAL_DAY_REQUIRED')
    return start - timedelta(hours=6), start, start + timedelta(days=1)


def value_or_none(value):
    try:
        return None if not math.isfinite(float(value)) else value
    except (TypeError, ValueError):
        return value


def immutable_request(target, requests, *, event_time, target_day):
    """Exact UID+submission join, normalized instants, no resource inference.

    Archive uniqueness is not proof of original submission-version history.
    That separate limitation is retained in every gate/provenance record.
    """
    uid = str(target['job_uid'])
    submit = timestamp(target['submit_time'])
    event = timestamp(event_time)
    if submit > event:
        raise ValueError('REQUEST_NOT_YET_SUBMITTED')
    candidates = []
    for raw in requests.get(uid, ()):
        if timestamp(raw['submit_time']) != submit:
            continue
        # Future-month raw payloads may not supply earlier-day workload values.
        member = raw.get('source_member', '')
        date_part = re.search(r'year=(\d{4})/month=(\d{1,2})/', member)
        if date_part:
            source_year, source_month = map(int, date_part.groups())
            if (source_year, source_month) > (int(target_day[:4]), int(target_day[5:7])):
                raise ValueError('FUTURE_MONTH_VALUE_DONOR')
        candidates.append(dict(raw, job_uid=uid, submit_time=submit.isoformat(),
                               gpus_requested=value_or_none(raw.get('gpus_requested'))))
    result = recover_gpu(dict(job_uid=uid, submit_time=submit.isoformat()), candidates,
                         event_time=event.isoformat())
    if len(candidates) != 1:
        # Descriptors used by Runtime must also have one exact source identity.
        if len(candidates) > 1:
            result = dict(result, GPU_gang=None, status='AMBIGUOUS_SOURCE_MATCH', ambiguity_count=len(candidates))
        return result, None
    raw = candidates[0]
    # Only the explicit raw GPU field is ported. A historical filter or an
    # undocumented nodes->GPU fallback cannot become physical authority here.
    gpu = int(raw['gpus_requested']) if positive_integer(raw['gpus_requested']) else None
    if result['GPU_gang'] != gpu:
        raise ValueError('UNAUTHORIZED_GPU_DERIVATION')
    return result, raw


def request_features(raw):
    return dict(num_gpus_req=value_or_none(raw.get('gpus_requested')),
                num_nodes_req=value_or_none(raw.get('nodes_req')),
                num_cores_req=value_or_none(raw.get('processors_req')),
                requested_memory_mib=memory_mib(raw.get('memory_req')),
                requested_seconds=raw['requested_seconds'],
                array_index=value_or_none(raw.get('array_pos')),
                account=raw.get('account_hash'), qos=raw.get('qos'), partition=raw.get('partition'))


def predict_causal_batch(provider, raws, submissions, events):
    if not raws:
        return []
    if len(raws) != len(events) or len(events) != len(submissions):
        raise ValueError('PREDICTION_AXIS')
    if any(timestamp(s) > timestamp(e) for s, e in zip(submissions, events)):
        raise ValueError('PREDICTION_BEFORE_SUBMISSION')
    available = provider.available
    if isinstance(available, (int, float)):
        available = datetime.fromtimestamp(available, timezone.utc)
    if any(timestamp(e) < timestamp(available) for e in events):
        raise ValueError('FROZEN_MODEL_NOT_AVAILABLE_AT_ROW_EVENT')
    # The provider is immutable across the batch; only request descriptors are
    # features. Batching at max(event) is equivalent to row-event inference:
    # no model update, state feature, event-time feature or future label exists.
    predictions = provider.predict_batch([request_features(r) for r in raws],
                                         submit_times=submissions, event_time=max(map(timestamp, events)))
    if len(predictions) != len(raws):
        raise ValueError('RUNTIME_PREDICTION_CARDINALITY')
    return predictions


def build_v42_day_input_bundle(day, *, known_snapshot, raw_requests, actual_observations,
                              runtime_provider, physical_authority, forecast_inputs,
                              actual_inputs):
    issue, start, end = axis(day)
    capacities = physical_authority['capacities']
    racks = physical_authority['rack_compatibility']
    if any(not positive_integer(c) for c in capacities.values()) or set(racks) != set(capacities):
        raise ValueError('CAPACITY_RACK_AUTHORITY')
    if not capacities or any(not rs or any(not positive_integer(x) for x in rs) for rs in racks.values()):
        raise ValueError('CAPACITY_RACK_AUTHORITY')
    prohibited = {'start_time', 'end_time', 'actual_remaining', 'voltage', 'line_loading', 'May_GPU'}
    if any(prohibited.intersection(j) for j in known_snapshot):
        raise ValueError('PLANNING_FUTURE_OR_GRID_FEATURE')
    known_targets = [dict(j, job_uid=str(j['job_uid'])) for j in known_snapshot]
    if len({j['job_uid'] for j in known_targets}) != len(known_targets):
        raise ValueError('DUPLICATE_KNOWN_UID')
    if any(timestamp(j['submit_time']) > timestamp(issue) for j in known_targets):
        raise ValueError('PLANNING_FUTURE_ARRIVAL')
    known_ids = {j['job_uid'] for j in known_targets}
    actual_targets = []
    for uid, records in sorted(raw_requests.items()):
        arrivals = [r for r in records if timestamp(issue) < timestamp(r['submit_time']) < timestamp(end)]
        if arrivals:
            submits = {timestamp(r['submit_time']) for r in arrivals}
            if len(submits) != 1:
                raise ValueError('AMBIGUOUS_SUBMISSION_IDENTITY')
            actual_targets.append(dict(job_uid=str(uid), submit_time=arrivals[0]['submit_time']))
    if known_ids & {j['job_uid'] for j in actual_targets}:
        raise ValueError('KNOWN_ACTUAL_IDENTITY_OVERLAP')
    recoveries = []
    version_authority = []

    def construct(targets, role):
        rows, ready_raw, submissions, events, positions = [], [], [], [], []
        for target in targets:
            event = issue if role == 'KNOWN_D1' else timestamp(target['submit_time'])
            result, raw = immutable_request(target, raw_requests, event_time=event, target_day=day)
            gpu = result['GPU_gang'] if raw is not None else None
            existing = target.get('GPU_gang', target.get('gpus_requested'))
            if positive_integer(existing) and gpu != existing:
                raise ValueError('IMMUTABLE_GPU_CONFLICT')
            version_authority.append(raw is not None and raw.get('request_version_verified') is True)
            state = target.get('state_at_D1_cutoff', 'PENDING')
            if state not in ('RUNNING', 'PENDING'):
                raise ValueError('OBSERVED_STATE')
            elapsed = float(target.get('elapsed_seconds', 0))
            site = target.get('source_site')
            compatible = [s for s in sorted(capacities) if gpu is not None and
                          gpu <= capacities[s] and any(gpu <= r for r in racks[s])]
            row = dict(job_uid=target['job_uid'], submit_time=timestamp(target['submit_time']).isoformat(),
                       state_at_D1_cutoff=state if role == 'KNOWN_D1' else None,
                       state=state, source_site=site, source_site_authority=target.get('source_site_authority'), GPU_gang=gpu,
                       gpu_authority='EXACT_IMMUTABLE_RAW_REQUEST' if gpu is not None else 'UNRESOLVED',
                       gpu_source_field='gpus_requested', request_version_history='UNVERIFIED_SOURCE_PROXY',
                       runtime_authority=MODEL, Q50_total_seconds=None, service_slots=None,
                       nominal_remaining_seconds=None, elapsed_seconds=elapsed,
                       compatible_sites=compatible, reference_site=None, reference_start=None,
                       source_member=raw.get('source_member') if raw else None,
                       source_row=raw.get('source_row') if raw else None,
                       runtime_inference_event_time=timestamp(event).isoformat())
            if raw is not None:
                ready_raw.append(raw); submissions.append(row['submit_time']); events.append(event); positions.append(len(rows))
            recoveries.append(dict(day=day, role=role, job_uid=row['job_uid'], submission_time=row['submit_time'],
                                   status=result['status'], GPU_gang=gpu,
                                   candidate_count=result['candidate_count'], source_member=row['source_member'],
                                   source_row=row['source_row'], source_field='gpus_requested',
                                   parser_rule='POSITIVE_INTEGER_RAW_REQUEST_NO_NODE_DERIVATION',
                                   raw_value=None if raw is None else value_or_none(raw.get('gpus_requested'))))
            rows.append(row)
        predictions = predict_causal_batch(runtime_provider, ready_raw, submissions, events)
        for pos, total in zip(positions, predictions):
            row = rows[pos]
            remaining = planning_remaining(float(total), row['elapsed_seconds'], state=row['state'])
            row.update(Q50_total_seconds=float(total), service_slots=remaining['nominal_slots'],
                       nominal_remaining_seconds=remaining['nominal_remaining_seconds'],
                       observed_running_hard=remaining['observed_running_hard'],
                       overrun_uncertainty=remaining['overrun_uncertainty'])
        if role == 'ACTUAL_POST_ISSUE':
            for row in rows:
                observed = actual_observations.get(row['job_uid'], {})
                for field in ('start_time', 'end_time'):
                    t = observed.get(field)
                    row[field.replace('_time', '_observed_by_day_end')] = (
                        timestamp(t).isoformat() if t is not None and timestamp(t) <= timestamp(end) else None)
                row['arrival_period'] = 'POST_ISSUE_PRE_DAY_CARRYIN' if timestamp(row['submit_time']) < timestamp(start) else 'DDAY_ARRIVAL'
        return rows

    known = construct(known_targets, 'KNOWN_D1')
    arrivals = construct(actual_targets, 'ACTUAL_POST_ISSUE')
    known_complete = all(positive_integer(j['GPU_gang']) for j in known)
    actual_complete = known_complete and all(positive_integer(j['GPU_gang']) for j in arrivals)
    gate = dict(day=day, KNOWN_GPU_AUTHORITY_COMPLETE=known_complete,
                ACTUAL_GPU_AUTHORITY_COMPLETE=actual_complete,
                ARRIVAL_GPU_AUTHORITY_COMPLETE=all(positive_integer(j['GPU_gang']) for j in arrivals),
                runtime_authority_complete=all(j['service_slots'] is not None for j in known + arrivals),
                compatibility_complete=all(j['compatible_sites'] and
                    (j['source_site'] is None or j['source_site'] in j['compatible_sites']) for j in known + arrivals),
                capacity_authority_complete=True,
                forecast_complete=forecast_inputs['complete'], actual_grid_complete=actual_inputs['complete'],
                network_static_authority_complete=physical_authority.get('network_static_complete', False),
                april_electrical_adapter_bound=physical_authority.get('electrical_adapter_bound', False),
                CC4_forecast_bound=forecast_inputs.get('CC4_bound', False),
                submission_cutoff_PASS=True, D1_request_version_causality_PASS=None,
                request_version_history='UNVERIFIED_SOURCE_PROXY', no_synthetic_fill=True,
                request_version_authority_verified=bool(version_authority) and all(version_authority),
                workload_population_present=bool(known or arrivals),
                rows_dropped=0, known_jobs=len(known), actual_post_issue_jobs=len(arrivals),
                missing_known_GPU=sum(j['GPU_gang'] is None for j in known),
                missing_actual_GPU=sum(j['GPU_gang'] is None for j in arrivals),
                runtime_authority=MODEL, scientific_execution='NOT_RUN')
    gate['PASS'] = all(gate[k] for k in ('KNOWN_GPU_AUTHORITY_COMPLETE', 'ACTUAL_GPU_AUTHORITY_COMPLETE',
        'runtime_authority_complete', 'compatibility_complete', 'capacity_authority_complete',
        'forecast_complete', 'actual_grid_complete', 'network_static_authority_complete',
        'april_electrical_adapter_bound', 'CC4_forecast_bound', 'request_version_authority_verified',
        'workload_population_present'))
    if gate['request_version_authority_verified']:
        gate['D1_request_version_causality_PASS'] = True
        gate['request_version_history'] = 'SOURCE_VERIFIED_IMMUTABLE_SUBMISSION_REQUEST'
    common = dict(schema=SCHEMA, day=day, timezone='fixed UTC+10', slots=96, slot_seconds=900,
                  issue_time=issue.isoformat(), runtime_authority=MODEL,
                  capacities=capacities, rack_compatibility=racks, flags=dict(B0_FLAGS),
                  input_gate_PASS=gate['PASS'], status='READY' if gate['PASS'] else 'INCOMPLETE_NONEXECUTABLE')
    planning = dict(common, stage='PLANNING', known_population=known,
                    forecast_inputs=forecast_inputs, network_authority=physical_authority,
                    future_actual_arrival_IDs_present=False, primary_voltage_band_pu=[.95, 1.05])
    known_observations = []
    for row in known:
        event = actual_observations.get(row['job_uid'], {})
        known_observations.append(dict(job_uid=row['job_uid'], GPU_gang=row['GPU_gang'],
            **{f.replace('_time', '_observed_by_day_end'): timestamp(event[f]).isoformat()
               if event.get(f) is not None and timestamp(event[f]) <= timestamp(end) else None
               for f in ('start_time', 'end_time')}))
    actual = dict(common, stage='ACTUAL', actual_as_of=end.isoformat(), post_issue_arrivals=arrivals,
                  observed_known_episodes=known_observations, realized_inputs=actual_inputs,
                  known_immutable_GPU_map={j['job_uid']:j['GPU_gang'] for j in known},
                  physical_arrays_generated=False, actual_occupancy_reconstructed=False,
                  IT_recomputed_from_actual_occupancy=None, DayAhead_power_arrays_copied=None)
    return planning, actual, gate, recoveries


def freeze_common_reference(planning, gate):
    if not gate['PASS'] or planning['input_gate_PASS'] is not True:
        raise ValueError('INPUT_GATE_REQUIRED_BEFORE_REFERENCE')
    rows, audit = build_reference(planning['known_population'], planning['capacities'], planning['rack_compatibility'],
                                  issue_time=planning['issue_time'])
    if not audit['full_reference_ready']:
        raise ValueError('COMMON_REFERENCE_MAPPING_INCOMPLETE')
    return rows, digest(rows)


def require_b0_physical_presence(metrics):
    keys = ('served_jobs', 'served_GPUh', 'AIDC_IT_energy_kWh', 'AIDC_PCC_energy_kWh', 'active_AIDC_slots')
    if any(k not in metrics or isinstance(metrics[k], bool) or not isinstance(metrics[k], (int, float)) or
           not math.isfinite(metrics[k]) or metrics[k] <= 0 for k in keys):
        raise ValueError('B0_AIDC_PHYSICAL_PRESENCE_REQUIRED')
    return True
