"""Inherited choices with explicit service-preserving checkpoint/WAN states.

Slots use the common D-1 issue origin. The operating day starts at BEGIN.
The existing V39C binding chooses the first checkpoint and serializes selected
moves by UID, starting at operating slot 2. Those rules remain constraints.
"""
from copy import deepcopy
from dataclasses import dataclass
from collections import defaultdict
from dayahead.v40a.feedback import authorized_options
from dayahead.v40a.invariants import BEGIN, H, occupancy_deviation, tail, digest
from dayahead.v38.authority import checkpoint_slots
from dayahead.v38.wan import validate_fixed_path_transfers


@dataclass(frozen=True, order=True)
class Option:
    site: str
    start: int
    end: int
    checkpoint: int = -1
    transfer_start: int = -1
    transfer_end: int = -1

    @property
    def migrated(self): return self.checkpoint >= 0

    def segments(self, row):
        if not self.migrated: return ((self.site, self.start, self.end),)
        return ((row['AIDC_site'], self.start, self.checkpoint),
                (self.site, self.transfer_end + 1, self.end))


def options(row, capacity, wan, elapsed, temporal_only=False):
    if row.get('migration_selected'):
        raise ValueError('REFERENCE_WITH_PREEXISTING_MIGRATION_REQUIRES_BOUND_TRACE')
    if row['state_at_issue'] != 'RUNNING':
        return tuple(Option(s, t, t + row['safe_duration_slots'])
                     for s, t in authorized_options(row, capacity)
                     if not temporal_only or s == row['AIDC_site'])
    stay = Option(row['AIDC_site'], int(row['start_slot']), int(row['end_slot']))
    # A single migration cannot return to the immutable post-H site/profile.
    if temporal_only or row['end_slot'] > H or row['end_slot'] <= BEGIN:
        return (stay,)
    if wan is None or row['job_uid'] not in elapsed:
        raise ValueError('RUNNING_MIGRATION_CAUSAL_WAN_AUTHORITY_MISSING')
    cp = checkpoint_slots(elapsed[row['job_uid']] + BEGIN * 900, H - BEGIN)[0] + BEGIN
    if cp >= row['end_slot']: return (stay,)
    result = [stay]
    for site in capacity.aidc_ids:
        if site == row['AIDC_site'] or capacity.site_capacity[site] < row['requested_GPU'] or not capacity.eligible_racks(site, row['requested_GPU']):
            continue
        for start in range(max(BEGIN + 2, cp), H - 1):
            remaining = wan.payload_bytes(row['requested_GPU']); end = start
            while remaining > 0 and end < H - 1:
                remaining -= min(remaining, wan.path_capacity_bytes(row['AIDC_site'], site, end - BEGIN))
                end += 1
            finish = int(row['end_slot']) + end + 1 - cp
            if remaining == 0 and finish <= H:
                result.append(Option(site, stay.start, finish, cp, start, end))
    return tuple(sorted(result))


def deviation(row, option):
    # The canonical metric is the full UID/site occupancy symmetric difference.
    # This equals the existing function for every single-interval decision.
    if not option.migrated:
        return occupancy_deviation(row, {**row, 'AIDC_site': option.site,
                                         'start_slot': option.start, 'end_slot': option.end})
    overlap = sum(max(0, min(row['end_slot'], b) - max(row['start_slot'], a))
                  for s, a, b in option.segments(row) if s == row['AIDC_site'])
    return int(row['requested_GPU']) * (2 * row['safe_duration_slots'] - 2 * overlap)


def materialize(row, option, capacity, wan):
    value = deepcopy(row)
    value.update(AIDC_site=option.site, start_slot=option.start, end_slot=option.end)
    from dayahead.v41r1.terminal import active
    if active(row) and row['state_at_issue'] == 'PENDING':
        value['post_H_site'] = option.site if option.end > H else None
    if (option.site, option.start, option.end) == (row['AIDC_site'], row['start_slot'], row['end_slot']) and not option.migrated:
        return value
    if option.site != 'UNASSIGNED':
        value['Rack_label'] = sorted(p.rack_pool_id for p in capacity.eligible_racks(option.site, row['requested_GPU']))[0]
    if not option.migrated: return value
    sent = [0] * (H - BEGIN); remaining = wan.payload_bytes(row['requested_GPU'])
    for t in range(option.transfer_start, option.transfer_end):
        sent[t - BEGIN] = min(remaining, wan.path_capacity_bytes(row['AIDC_site'], option.site, t - BEGIN))
        remaining -= sent[t - BEGIN]
    assert remaining == 0
    transfer = {'job_uid': row['job_uid'], 'source_AIDC': row['AIDC_site'],
                'destination_AIDC': option.site, 'payload_bytes': sum(sent),
                'bytes_by_slot': sent, 'fixed_path_id': wan.path_id(row['AIDC_site'], option.site),
                'fixed_path_links': list(wan.path(row['AIDC_site'], option.site)), 'path_selection_decisions': 0}
    value.update(migration_selected=True, migration_destination=option.site,
                 initial_AIDC=row['AIDC_site'], frozen_execution_ready_slot=option.transfer_end + 1,
                 compute_segments=[{'site': s, 'start': a, 'end': b} for s, a, b in option.segments(row)],
                 migration_checkpoint_slot=option.checkpoint,
                 WAN_transfer_complete_slot=option.transfer_end - 1,
                 destination_READY_slot=option.transfer_end, restart_complete_slot=option.transfer_end + 1,
                 frozen_WAN_transfer=transfer,
                 accepted_A0_assignment_and_WAN={**transfer, 'migration_selected': True,
                    'migration_checkpoint_slot': option.checkpoint, 'restart_complete_slot': option.transfer_end + 1,
                    'slot_origin': 'D_MINUS_1_ISSUE', 'WAN_bytes_axis_origin': 'OPERATING_DAY'})
    return value


def segments(row):
    return tuple((s['site'], int(s['start']), int(s['end'])) for s in row['compute_segments']) if row.get('compute_segments') else ((row['AIDC_site'], int(row['start_slot']), int(row['end_slot'])),)


def audit(reference_jobs, selected, capacity, wan):
    refs = {r['job_uid']: r for r in reference_jobs}
    assert len(refs) == len(selected) and set(refs) == {r['job_uid'] for r in selected}
    transfers = []; changed_tail = 0
    for row in selected:
        before = refs[row['job_uid']]
        for field in ('requested_GPU','state_at_issue','qos','safe_duration_slots','safe_duration_seconds','duration_authority','common_terminal_obligation','source_snapshot_sha256'):
            assert before.get(field) == row.get(field), field
        parts = segments(row)
        assert sum(b-a for s,a,b in parts) == before['safe_duration_slots']
        assert all(a < b for s,a,b in parts)
        old_tail = [(s,max(H,a),b) for s,a,b in segments(before) if b>H]
        new_tail = [(s,max(H,a),b) for s,a,b in parts if b>H]
        from dayahead.v41r1.terminal import active, check
        if active(before) and before['state_at_issue'] == 'PENDING':
            check(before, row)
            changed_tail += old_tail != new_tail
        else:
            assert old_tail == new_tail
        if row.get('migration_selected'):
            assert before['state_at_issue']=='RUNNING' and row['start_slot']==before['start_slot']
            assert parts[0][0]==before['AIDC_site'] and parts[-1][0]==row['migration_destination']
            assert parts[0][2]==row['migration_checkpoint_slot']
            assert parts[-1][1]==row['restart_complete_slot'] and row['end_slot']<=H
            transfer=row['frozen_WAN_transfer']; assert sum(transfer['bytes_by_slot'])==wan.payload_bytes(row['requested_GPU'])
            transfers.append(transfer)
        elif before['state_at_issue']=='RUNNING':
            assert parts==segments(before)
    validation = validate_fixed_path_transfers(wan, transfers) if transfers else {'status':'PASS','path_selection_decisions':0,'violations':[]}
    assert validation['status']=='PASS'
    return {'status':'PASS','POST_H_RESERVATION_PROFILE_CHANGED_JOBS':changed_tail,'POST_H_SITE_STATE_CHANGED_JOBS':sum(
            bool(tail(refs[r['job_uid']]) or tail(r)) and refs[r['job_uid']]['AIDC_site'] != r['AIDC_site'] for r in selected),
            'REPAIR_INDUCED_INCREMENTAL_POST_MIDNIGHT_GPU_H':0.,'safe_runtime_GPU_state_qos_preserved':True,
            'common_service_compute_GPU_slots_preserved':True,'WAN':validation,'migration_count':len(transfers)}
