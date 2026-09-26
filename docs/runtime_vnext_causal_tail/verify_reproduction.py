"""Audit a fresh unchanged registration; historical amendments use verify.py."""
from experiment import *


def main():
    for name in ['CODE_FREEZE.json', 'FINAL_SELECTION_FREEZE.json']:
        evidence = read(name)
        for filename, digest in evidence.get('files', evidence.get('code_hashes', {})).items():
            require(sha(ROOT/filename) == digest, 'FRESH_REGISTRATION_CODE_CHANGED')
    for name in ['MOE_BASELINE_REPRODUCTION.json', 'MODERN_BASELINE_REPRODUCTION.json']:
        require(read(name)['PASS'], 'BASELINE_REPRODUCTION_FAILED')
    jobs, panel = data()
    count = 0
    for path in (ROOT/'fits').glob('*/*/MEMBERSHIP.json'):
        evidence = json.loads(path.read_text(encoding='utf-8'))
        membership_path = path.parent/'train_membership.npz'
        require(sha(membership_path) == evidence['row_ids_sha256'], 'MEMBERSHIP_DIGEST')
        expected = member(evidence['policy'], pd.Timestamp(evidence['issue_time']))
        require(np.array_equal(np.load(membership_path)['row_ids'], expected.row_id.to_numpy()), 'MEMBERSHIP_NOT_EXACT')
        require(ids(expected.job_id) == evidence['job_ids_sha256'], 'MEMBERSHIP_ID_DIGEST')
        count += 1
    indexed = panel.set_index('job_issue_id')
    for path in (ROOT/'calibration').glob('*.json'):
        for evidence in json.loads(path.read_text(encoding='utf-8')):
            history = indexed.loc[evidence['pool_job_issue_ids']]
            require(history.end_time.lt(pd.Timestamp(evidence['issue_time'])).all(), 'RESIDUAL_MATURITY')
    frame = pd.read_parquet(ROOT/'PREDICTIONS.parquet')
    require(np.isfinite(frame.Q90).all() and (frame.Q90 >= 0).all(), 'INVALID_PREDICTION')
    expected = set(panel.loc[panel.role.isin(['EXPOSED_EVALUATION', 'MAY_HISTORICAL']), 'job_issue_id'])
    for model in ['MOE_POOLED', 'MULTI_QUANTILE', 'MULTI_QUANTILE_HIERARCHICAL', 'MOE_CURRENT_TEMPORAL_GPU_COHORT']:
        group = frame[frame.model.eq(model)]
        require(set(group.job_issue_id) == expected and group.job_issue_id.is_unique, 'EVALUATION_POPULATION_CHANGED')
    import verify_fit_receipts
    verify_fit_receipts.main()
    dump('VALIDATION.json', dict(time=now(), PASS=True, fresh_registration=True,
         fit_memberships=count, exact_baselines=True, strict_job_end_maturity=True,
         production_changed=False, optimizer_executions=0, grid_executions=0))
    print('FRESH REPRODUCTION VALIDATION PASS', count, flush=True)


if __name__ == '__main__':
    main()
