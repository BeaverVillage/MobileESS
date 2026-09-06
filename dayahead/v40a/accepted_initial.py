"""Import an accepted causal A0, retaining its terminal repair and WAN evidence.

This is an A0-only adapter. A historical B3 result is never accepted as a V40A
joint result. Campaign/date admission remains a separate, later operation.
"""
from copy import deepcopy
from pathlib import Path
import json
import numpy as np
from .context import file_sha
from .feedback import pcc_from_jobs
from .invariants import H, digest, terminal_audit


def materialize_accepted_a0(path, expected_file_sha, ledger, context):
    from dayahead.v38.authority import canonical_sha256
    path = Path(path)
    if file_sha(path) != expected_file_sha:
        raise ValueError('A0_ACCEPTED_AUTHORITY_FILE_SHA_MISMATCH')
    frozen = json.loads(path.read_text(encoding='utf-8'))
    decision = frozen['decision']
    if canonical_sha256(decision) != frozen['DA_decision_SHA256']:
        raise ValueError('A0_ACCEPTED_DECISION_SHA_MISMATCH')
    if decision['status'] != 'PASS' or decision['temporal_mode'] != 'RSP':
        raise ValueError('A0_REQUIRES_ACCEPTED_CAUSAL_RSP')
    if decision['operating_day'] != context.day:
        raise ValueError('A0_ACCEPTED_DAY_MISMATCH')
    temporal = {str(r['job_id']): r for r in decision['temporal_schedule']}
    assignments = {str(r['job_uid']): r for r in decision['AIDC_assignments']}
    if len(temporal) != len(decision['temporal_schedule']):
        raise ValueError('A0_DUPLICATE_TEMPORAL_JOB')
    jobs = []
    for row in ledger:
        uid = str(row['job_id'])
        selected = temporal[uid]
        placement = deepcopy(assignments.get(uid, {}))
        start, end = int(selected['scheduled_start_slot']), int(selected['scheduled_end_slot'])
        site = placement.get('destination_AIDC', 'UNASSIGNED')
        eligible = (row['state_at_issue'] == 'PENDING' and row['qos'] == 'standby'
                    and row['duration_authority'] == 'SAFE_CAUSAL_RUNTIME_PENDING'
                    and int(row['RSP_duration_slots']) > 0
                    and int(row['RSP_scheduled_start']) <= int(row['RW_scheduled_completion']) - int(row['RSP_duration_slots']))
        jobs.append({
            'job_uid': uid, 'state_at_issue': row['state_at_issue'], 'qos': row['qos'],
            'requested_GPU': int(row['requested_gpus']),
            'safe_duration_slots': int(row['RSP_duration_slots']),
            'safe_duration_seconds': float(row['RSP_duration_seconds']),
            'start_slot': start, 'end_slot': end, 'AIDC_site': site,
            'Rack_label': placement.get('logical_Rack_compatibility_label'),
            'migration_selected': bool(placement.get('migration_selected', False)),
            'migration_destination': site if placement.get('migration_selected') else None,
            'initial_AIDC': placement.get('initial_AIDC'),
            'terminal_class': 'IN_DAY_COMPLETE' if end <= H else 'CROSS_BOUNDARY' if start < H else 'POST_H_ONLY',
            'post_H_site': site if end > H else None, 'eligible_standby': eligible,
            'RSP_start_slot': int(row['RSP_scheduled_start']),
            'RW_completion_slot': int(row['RW_scheduled_completion']),
            'duration_authority': row['duration_authority'],
            'accepted_A0_assignment_and_WAN': placement,
            'accepted_A0_file_SHA': expected_file_sha,
        })
    if set(temporal) != {r['job_uid'] for r in jobs}:
        raise ValueError('A0_JOB_UNIVERSE_CHANGED')
    audit = terminal_audit(jobs, jobs)
    pcc, gpu = pcc_from_jobs(jobs, context)
    power = sorted(decision['site_PCC_power_trajectory'], key=lambda r: (r['slot'], r['AIDC']))
    accepted_pcc = np.asarray([r['PCC_P_kW'] for r in power]).reshape(96, 12)
    if not np.allclose(pcc, accepted_pcc, rtol=0, atol=1e-7):
        raise ValueError('A0_ACCEPTED_PCC_RECONSTRUCTION_MISMATCH')
    return {'jobs': jobs, 'PCC': pcc, 'GPU': gpu, 'A0_SHA': digest(jobs),
            'terminal_audit': audit, 'AIDC_solver_calls': 0,
            'accepted_A0_decision': decision,
            'source_SHAs': {str(path): expected_file_sha},
            'RUNNING_migrations_selected_in_A0': sum(r['migration_selected'] for r in jobs),
            'A0_policy': 'ACCEPTED_TERMINAL_SAFE_TEMPORAL_FIRST_AUTHORITY_WITH_INHERITED_WAN_STATE',
            'new_migration_optimization_calls': 0}
