"""Read-only membership bridge; never changes the registered study population."""
from experiment import *


def main():
    jobs, _ = data()
    rows = []
    for reference in read('MODERN_BASELINE_REPRODUCTION.json')['days']:
        issue = pd.Timestamp(reference['day'], tz='Etc/GMT-10') - pd.Timedelta(hours=6)
        issue = issue.tz_convert('UTC')
        study = member('expanding', issue)
        production_eligible = jobs[
            jobs.submit_time.le(issue) & jobs.end_time.lt(issue)
            & jobs.runtime_seconds.gt(0) & np.isfinite(jobs.runtime_seconds)
            & jobs[CLOCK].notna().all(axis=1)
        ]
        reference_match = (len(production_eligible) == reference['training_N']
                           and ids(production_eligible.job_id) == reference['training_membership_hash'])
        require(reference_match, 'PRODUCTION_TRAINING_MEMBERSHIP_NOT_RECONSTRUCTED')
        rows.append(dict(day=reference['day'], issue_time=issue,
                         production_N=reference['training_N'], study_expanding_N=len(study),
                         production_membership_hash=reference['training_membership_hash'],
                         study_membership_hash=ids(study.job_id),
                         production_only_N=len(set(production_eligible.job_id) - set(study.job_id)),
                         study_only_N=len(set(study.job_id) - set(production_eligible.job_id)),
                         production_reconstruction_exact=reference_match))
    pd.DataFrame(rows).to_csv(ROOT/'PRODUCTION_COHORT_BRIDGE.csv', index=False)
    dump('PRODUCTION_COHORT_BRIDGE.json', dict(
        time=now(), PASS=True, all_31_production_memberships_reconstructed=True,
        all_study_expanding_memberships_equal_production=all(
            r['production_only_N'] == r['study_only_N'] == 0 for r in rows),
        source_sha256=read('PREPARATION_COMPLETE.json')['jobs_sha256'],
        purpose='Population audit only; no scoring, refitting or selection',
        study_population_unchanged=True,
        historical_all_job_MOE_bridge='Not equivalent: the controlled study uses positive-GPU Jobs only'))
    print('PRODUCTION COHORT BRIDGE PASS', flush=True)


if __name__ == '__main__':
    main()
