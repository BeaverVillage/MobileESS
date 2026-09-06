"""Canonical compute intervals and non-compute migration events.

All times are boundaries relative to D-1 issue, in 900-second slots.
Only ``import_frozen`` may translate the legacy nonmigrated interval. A
migrated interval is never inferred from its final site and elapsed span.
"""
from copy import deepcopy
import math
import numpy as np
from dayahead.v40a.invariants import BEGIN, H, digest

SCHEMA = 'V40G_CANONICAL_COMPUTE_SEGMENTS_V1'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def import_frozen(jobs):
    result = deepcopy(jobs)
    for row in result:
        if row.get('segment_schema') == SCHEMA:
            validate(row)
            continue
        migrated = bool(row.get('migration_selected'))
        require(not migrated or bool(row.get('compute_segments')), 'MIGRATED_SEGMENTS_REQUIRED')
        row['compute_segments'] = deepcopy(row.get('compute_segments') or [
            {'site': row['AIDC_site'], 'start': row['start_slot'], 'end': row['end_slot']}])
        row['migration_events'] = []
        if migrated:
            transfer = deepcopy(row['frozen_WAN_transfer'])
            active = [i + BEGIN for i, b in enumerate(transfer['bytes_by_slot']) if b > 0]
            require(bool(active), 'MIGRATION_WITHOUT_BYTES')
            row['migration_events'] = [{
                **transfer, 'checkpoint': row['migration_checkpoint_slot'],
                'transfer_start': min(active), 'transfer_end': max(active) + 1,
                'ready': row['destination_READY_slot'], 'restart_end': row['restart_complete_slot'],
                'interruption_start': row['compute_segments'][0]['end'],
                'interruption_end': row['compute_segments'][1]['start'],
                'slot_origin': 'D_MINUS_1_ISSUE', 'bytes_axis_origin': 'OPERATING_DAY',
            }]
        row['segment_schema'] = SCHEMA
        validate(row)
    require(len({r['job_uid'] for r in result}) == len(result), 'DUPLICATE_CANONICAL_UID')
    return result


def validate(row):
    require(row.get('segment_schema') == SCHEMA, 'CANONICAL_SEGMENT_SCHEMA_REQUIRED')
    parts = row['compute_segments']; events = row['migration_events']
    require(len(parts) == (2 if row.get('migration_selected') else 1), 'SEGMENT_COUNT')
    require(len(events) == int(bool(row.get('migration_selected'))), 'EVENT_COUNT')
    require(all(isinstance(s[k], (int, float)) and math.isfinite(s[k]) for s in parts for k in ('start', 'end')), 'SEGMENT_TIME')
    require(all(s['start'] < s['end'] for s in parts), 'EMPTY_COMPUTE_SEGMENT')
    require(all(a['end'] <= b['start'] for a, b in zip(parts, parts[1:])), 'COMPUTE_OVERLAP')
    require(sum(s['end'] - s['start'] for s in parts) == row['safe_duration_slots'], 'COMMON_COMPUTE_SERVICE_CHANGED')
    require(parts[0]['start'] == row['start_slot'] and parts[-1]['end'] == row['end_slot'], 'LEGACY_BOUNDARY_DRIFT')
    require(parts[-1]['site'] == row['AIDC_site'], 'FINAL_SITE_DRIFT')
    if events:
        a, b = parts; e = events[0]
        require(row['state_at_issue'] == 'RUNNING' and a['site'] != b['site'], 'FIRST_PLACEMENT_IS_NOT_MIGRATION')
        require(a['site'] == row['initial_AIDC'] == e['source_AIDC'], 'MIGRATION_SOURCE')
        require(b['site'] == row['migration_destination'] == e['destination_AIDC'], 'MIGRATION_DESTINATION')
        require(a['end'] == e['checkpoint'] == e['interruption_start'] == row['migration_checkpoint_slot'], 'CHECKPOINT_DRIFT')
        require(b['start'] == e['restart_end'] == e['interruption_end'] == row['frozen_execution_ready_slot'] == row['restart_complete_slot'], 'RESTART_DRIFT')
        require(e['checkpoint'] <= e['transfer_start'] < e['transfer_end'] == e['ready'] < e['restart_end'], 'EVENT_CAUSALITY')
        require(e['restart_end'] - e['ready'] == 1 and e['ready'] == row['destination_READY_slot'], 'RESTART_AUTHORITY_CHANGED')
        require(e['transfer_end'] - 1 == row['WAN_transfer_complete_slot'], 'TRANSFER_COMPLETE_DRIFT')
        amounts = e['bytes_by_slot']
        require(len(amounts) == H - BEGIN and all(isinstance(x, int) and x >= 0 for x in amounts), 'WAN_BYTE_AXIS')
        require(sum(amounts) == e['payload_bytes'] > 0, 'WAN_PAYLOAD_CONSERVATION')
        active = [i + BEGIN for i, amount in enumerate(amounts) if amount]
        require(active == list(range(e['transfer_start'], e['transfer_end'])), 'FROZEN_WAN_INTERVAL_DRIFT')
        for k, value in row['frozen_WAN_transfer'].items():
            require(e[k] == value, 'FROZEN_WAN_EVENT_DRIFT:' + k)
        for k in ('job_uid', 'source_AIDC', 'destination_AIDC', 'payload_bytes', 'bytes_by_slot', 'fixed_path_id', 'fixed_path_links'):
            require(row['accepted_A0_assignment_and_WAN'][k] == e[k], 'ACCEPTED_WAN_DRIFT:' + k)
    return row


def identities(jobs):
    for row in jobs: validate(row)
    ordered = sorted(jobs, key=lambda r: r['job_uid'])
    base = [{'job_uid': r['job_uid'], 'requested_GPU': r['requested_GPU'],
             'safe_duration_slots': r['safe_duration_slots'], 'safe_duration_seconds': r['safe_duration_seconds'],
             'compute_segments': r['compute_segments']} for r in ordered]
    events = [{'job_uid': r['job_uid'], 'migration_events': r['migration_events']} for r in ordered]
    return {'compute_segment_SHA': digest(base), 'migration_event_SHA': digest(events),
            'segment_and_event_SHA': digest({'compute': base, 'events': events}),
            'canonical_decision_SHA': digest(ordered)}


def parts(row, actual=False):
    require(row.get('segment_schema') == SCHEMA, 'CANONICAL_SEGMENT_SCHEMA_REQUIRED')
    if actual:
        require('actual_compute_segments' in row, 'ACTUAL_SEGMENTS_REQUIRED')
        return row['actual_compute_segments']
    return row['compute_segments']


def occupancy(jobs, sites, *, actual=False):
    sites = tuple(sites); index = {s: i for i, s in enumerate(sites)}
    occ = np.zeros((H - BEGIN, len(sites)), dtype=int); contributions = []; seen = set()
    for row in jobs:
        for seg in parts(row, actual):
            start, end = seg['start'], seg['end']
            for slot in range(max(BEGIN, math.ceil(start)), min(H, math.ceil(end))):
                require(seg['site'] in index, 'UNASSIGNED_OPERATING_COMPUTE')
                key = (row['job_uid'], slot)
                require(key not in seen, 'ROOT_UID_GANG_DOUBLE_COMPUTE')
                seen.add(key); g = int(row['requested_GPU'])
                occ[slot - BEGIN, index[seg['site']]] += g
                contributions.append({'job_uid': row['job_uid'], 'site_id': seg['site'],
                    'slot': slot - BEGIN, 'GPU': g})
    return occ, contributions


def planning_power(jobs, context):
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v36.contracts import PF_TAN
    for row in jobs: validate(row)
    sites = tuple(context.capacity.aidc_ids)
    gpu, _ = occupancy(jobs, sites)
    require(all(np.all(gpu[:, i] <= context.capacity.site_capacity[s]) for i, s in enumerate(sites)), 'SITE_CAPACITY_VIOLATION')
    pcc = np.column_stack([context.tables[s][np.arange(H - BEGIN), gpu[:, i]] for i, s in enumerate(sites)])
    it = np.asarray([[float(site_it_power_kw(context.capacity.site_capacity[s], int(gpu[t, i]))) for i, s in enumerate(sites)] for t in range(H - BEGIN)])
    return {'gpu': gpu, 'it': it, 'pcc': pcc, 'qcc': pcc * PF_TAN}


def pcc_from_jobs(jobs, context):
    result = planning_power(jobs, context)
    return result['pcc'], result['gpu']


def deviation(before, after):
    a = parts(before); b = parts(after)
    overlap = sum(max(0, min(x['end'], y['end']) - max(x['start'], y['start']))
                  for x in a for y in b if x['site'] == y['site'])
    return before['requested_GPU'] * (sum(s['end'] - s['start'] for s in a + b) - 2 * overlap)


def terminal(row, *, actual=False, horizon=H):
    segs = parts(row, actual); events = row['migration_events']
    tail = [{**s, 'start': max(horizon, s['start'])} for s in segs if s['end'] > horizon]
    remaining = sum(s['end'] - s['start'] for s in tail)
    backlog = actual and row.get('status') == 'UNASSIGNED_POST_H_BACKLOG'
    if backlog: remaining = row['actual_service_seconds'] / 900
    active = next((s for s in segs if s['start'] <= horizon < s['end']), None)
    e = events[0] if events else None
    executed = bool(e) and (not actual or row.get('migration_executed', False))
    sent = sum(e['bytes_by_slot'][:max(0, min(96, math.floor(horizon - BEGIN)))]) if executed else 0
    if not executed: migration = 'CANCELLED_COMPLETED_BEFORE_CHECKPOINT' if e else 'NONE'
    elif horizon < e['checkpoint']: migration = 'BEFORE_CHECKPOINT'
    elif horizon < e['transfer_start']: migration = 'CHECKPOINT_WAIT'
    elif horizon < e['transfer_end']: migration = 'TRANSFERRING'
    elif horizon < e['restart_end']: migration = 'RESTARTING'
    else: migration = 'DESTINATION_READY'
    if active: site = active['site']; state = 'RUNNING'
    elif remaining:
        site = ('UNASSIGNED' if backlog else e['source_AIDC'] if executed and horizon < e['ready'] else tail[0]['site'])
        state = 'MIGRATING' if migration in ('CHECKPOINT_WAIT', 'TRANSFERRING', 'RESTARTING') else 'PENDING'
    else: site = segs[-1]['site'] if segs else None; state = 'COMPLETE'
    return {'job_uid': row['job_uid'], 'H': horizon, 'site_at_H': site, 'state_at_H': state,
        'RUNNING_at_H': state == 'RUNNING', 'PENDING_at_H': state == 'PENDING',
        'remaining_compute_slots': remaining, 'remaining_compute_GPU_slots': remaining * row['requested_GPU'],
        'post_H_segments': tail, 'post_H_site': tail[0]['site'] if tail else 'UNASSIGNED' if backlog else None,
        'migration_state': migration, 'WAN_bytes_sent': sent,
        'WAN_bytes_remaining': e['payload_bytes'] - sent if executed else 0,
        'WAN_bytes_arrived': sent, 'WAN_bytes_in_pipeline': 0,
        'common_terminal_obligation': row.get('common_terminal_obligation')}


def terminal_audit(before, after):
    old = {r['job_uid']: r for r in before}
    require(len(old) == len(after) and set(old) == {r['job_uid'] for r in after}, 'TERMINAL_UID_DRIFT')
    for row in after:
        validate(row); prev = old[row['job_uid']]; validate(prev)
        for k in ('requested_GPU', 'safe_duration_seconds', 'safe_duration_slots', 'duration_authority', 'state_at_issue', 'qos', 'common_terminal_obligation', 'source_snapshot_sha256'):
            require(row.get(k) == prev.get(k), 'COMMON_AUTHORITY_DRIFT:' + k)
        a, b = terminal(prev), terminal(row)
        from dayahead.v41r1.terminal import active, check
        if active(prev) and prev['state_at_issue'] == 'PENDING':
            check(prev, row)
        else:
            for k in ('post_H_segments', 'post_H_site', 'remaining_compute_GPU_slots'):
                require(a[k] == b[k], 'COMMON_TERMINAL_DRIFT:' + k)
        obligation = row.get('common_terminal_obligation', {})
        if obligation.get('must_complete_by_H'): require(b['remaining_compute_slots'] == 0, 'COMMON_IN_DAY_SERVICE_LOST')
    return {'status': 'PASS', 'POST_H_RESERVATION_PROFILE_CHANGED_JOBS': sum(
        terminal(old[r['job_uid']])['post_H_segments'] != terminal(r)['post_H_segments'] for r in after),
        'POST_H_SITE_STATE_CHANGED_JOBS': sum(terminal(old[r['job_uid']])['post_H_site'] != terminal(r)['post_H_site'] for r in after),
        'REPAIR_INDUCED_INCREMENTAL_POST_MIDNIGHT_GPU_H': 0.0}


def wan_audit(jobs, authority, *, actual=False):
    from dayahead.v38.wan import validate_fixed_path_transfers
    events = []
    for row in jobs:
        validate(row)
        for e in row['migration_events']:
            source, dest = e['source_AIDC'], e['destination_AIDC']
            require(e['payload_bytes'] == authority.payload_bytes(row['requested_GPU']), 'WAN_GPU_PAYLOAD_DRIFT')
            require(e['fixed_path_id'] == authority.path_id(source, dest) and e['fixed_path_links'] == list(authority.path(source, dest)), 'WAN_PATH_DRIFT')
            require(e['path_selection_decisions'] == 0, 'WAN_PATH_OPTIMIZATION_FORBIDDEN')
            for t, amount in enumerate(e['bytes_by_slot']):
                require(amount <= authority.path_capacity_bytes(source, dest, t), 'WAN_PATH_CAPACITY')
            if not actual or row.get('migration_executed'): events.append(e)
    result = validate_fixed_path_transfers(authority, events)
    require(result['status'] == 'PASS', 'WAN_CAPACITY_ACCOUNTING')
    result.update(migration_count=len(events), total_payload_bytes=sum(e['payload_bytes'] for e in events))
    return result
