"""No exclusion before a canonical counterfactual execution proof exists."""
from dayahead.v40g_segments.actual import replay_jobs as segment_replay
from dayahead.v40g_segments.actual import power_from_execution, write_runtime_audits
from .pre_day_complete import classify, require_safe_exclusion, SITE_BLOCKER
from .identity import require


def replay_jobs(jobs, observations, *, issue_time, site_capacity, racks):
    # Unknown-site pre-day jobs cannot be dispatched or capacity-delayed
    # authoritatively. Never let the old observed-end exclusion remove them.
    for job in jobs:
        if job['AIDC_site'] == 'UNASSIGNED' and job['start_slot'] < 120:
            witness = classify(job, observations[job['job_uid']], issue_time)
            raise ValueError(SITE_BLOCKER + ':' + job['job_uid'] + ':' + str(witness))
    result = segment_replay(jobs, observations, issue_time=issue_time, site_capacity=site_capacity, racks=racks)
    frozen = {r['job_uid']: r for r in jobs}; exclusions = []
    for row in result['job_ledger']:
        if row['status'] == 'EXECUTION_ACCOUNTED':
            proof = classify(frozen[row['job_uid']], observations[row['job_uid']], issue_time,
                             execution_segments=row['actual_compute_segments'])
            row['counterfactual_day_classification'] = proof
            if proof['status'] == 'PRE_DAY_COMPLETE':
                require_safe_exclusion(proof); exclusions.append(proof)
        else:
            require(row['status'] == 'UNASSIGNED_POST_H_BACKLOG', 'UNPROVEN_PRE_DAY_COMPLETE_EXCLUSION')
    result['counterfactual_pre_day_complete_proofs'] = exclusions
    return result
