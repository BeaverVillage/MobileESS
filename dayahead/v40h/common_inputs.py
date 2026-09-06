"""Static 31-day common service materialization using the frozen V40F rule.

No candidate, optimization, electrical or Actual execution is performed.
Historical B0 placement is a reference-policy input, never a completed case.
"""
from pathlib import Path
import math
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, sha, digest
from dayahead.v40a.invariants import tail
from dayahead.v40d_actual.inputs import frozen_jobs
from .identity import REL, DAYS, require, file_record


def materialize(repo):
    repo = Path(repo).resolve(); output = repo / REL / 'common_inputs'
    bindings = read(repo / 'dayahead/artifacts/v40d_actual_realized_replay/V40D_ACTUAL_DECISION_BINDING_AUDIT.json')['cases']
    days = {}
    for day in DAYS:
        binding = next(b for b in bindings if b['day'] == day and b['case'] == 'B0')
        jobs = frozen_jobs(repo, binding)[0]
        source = repo / 'dayahead/artifacts/v37_r4a_per_day_aidc/days' / day
        lp = source / 'V37_R4A_JOB_LEDGER.parquet'; sp = source / 'V37_R4A_D1_SNAPSHOT.parquet'
        ledger = pd.read_parquet(lp); ledger['uid'] = ledger.job_id.astype(str); ledger = ledger.set_index('uid')
        snapshot = pd.read_parquet(sp); snapshot['uid'] = snapshot.id.astype(str); snapshot = snapshot.set_index('uid')
        require(set(ledger.index) == {r['job_uid'] for r in jobs} and not ledger.index.duplicated().any(), 'COMMON_JOB_UNIVERSE')
        issue = pd.Timestamp(day, tz='Australia/Brisbane') - pd.Timedelta(hours=6)
        require((pd.to_datetime(snapshot.loc[ledger.index].submit_time, utc=True) <= issue.tz_convert('UTC')).all(), 'COMMON_CAUSAL_SUBMISSION')
        rows = []; snapshot_sha = sha(sp)
        for job in jobs:
            row = ledger.loc[job['job_uid']]; slots = int(row.RSP_duration_slots); seconds = float(row.RSP_duration_seconds)
            require(slots == max(1, math.ceil(seconds / 900)) and seconds > 0, 'COMMON_DURATION')
            require(int(job['requested_GPU']) == int(row.requested_gpus) and job['state_at_issue'] == row.state_at_issue and job['qos'] == row.qos, 'COMMON_STATE_IDENTITY')
            require(row.duration_authority in ('SAFE_CAUSAL_RUNTIME_PENDING', 'REQUESTED_REMAINING', 'REQUESTED_WALLTIME_FAIL_CLOSED'), 'COMMON_CAUSAL_RUNTIME')
            job.update(safe_duration_slots=slots, safe_duration_seconds=seconds, duration_authority=str(row.duration_authority),
                end_slot=int(job['start_slot']) + slots, RSP_start_slot=int(row.RSP_scheduled_start), RW_completion_slot=int(row.RW_scheduled_completion),
                eligible_standby=bool(job['state_at_issue'] == 'PENDING' and job['qos'] == 'standby' and row.duration_authority == 'SAFE_CAUSAL_RUNTIME_PENDING'
                    and int(row.RSP_scheduled_start) <= int(row.RW_scheduled_completion) - slots), source_snapshot_sha256=snapshot_sha, operating_day=day)
            job['post_H_site'] = job['AIDC_site'] if job['end_slot'] > 120 else None
            job['terminal_class'] = 'IN_DAY_COMPLETE' if job['end_slot'] <= 120 else 'CROSS_BOUNDARY' if job['start_slot'] < 120 else 'POST_H_ONLY'
            obligation = {'must_complete_by_H': job['end_slot'] <= 120, 'postH_profile': tail(job)}
            job['common_terminal_obligation'] = obligation
            rows.append({'job_uid': job['job_uid'], 'requested_GPU': job['requested_GPU'], 'state_at_issue': job['state_at_issue'],
                'service_tier': job['qos'], 'T_DA_seconds': seconds, 'T_DA_slots': slots, 'duration_authority': str(row.duration_authority),
                'terminal_obligation': obligation, 'source_snapshot_sha': snapshot_sha})
        rows.sort(key=lambda r: r['job_uid']); authority_sha = digest(rows)
        path = output / day / 'COMMON_DA_SERVICE_AUTHORITY.json'; reference = output / day / 'COMMON_B0_REFERENCE_JOBS.json'
        write_json(path, {'day': day, 'COMMON_DA_DURATION_SHA': authority_sha, 'rows': rows,
            'source': file_record(lp), 'snapshot': file_record(sp), 'Realized_future_duration_read_count': 0,
            'reference_policy_origin': binding, 'completed_case_reuse': False})
        write_json(reference, jobs)
        days[day] = {'COMMON_DA_DURATION_SHA': authority_sha, 'authority': file_record(path), 'B0_reference_policy': file_record(reference),
                     'job_count': len(jobs), 'common_for_cases': ['B0', 'B1', 'B2', 'B3'], 'completed_case_reuse': False}
    frozen = read(repo / 'dayahead/artifacts/v40g_segment_integration/common_service/COMMON_DA_SERVICE_AUTHORITY.json')
    require(days['2025-05-01']['COMMON_DA_DURATION_SHA'] == frozen['COMMON_DA_DURATION_SHA'], 'FROZEN_MAY01_COMMON_T_DA_CHANGED')
    write_json(output / 'COMMON_INPUT_INDEX.json', days)
    print('31 common service inputs; May-01 frozen T_DA exact match; no solves', flush=True)
    return days
