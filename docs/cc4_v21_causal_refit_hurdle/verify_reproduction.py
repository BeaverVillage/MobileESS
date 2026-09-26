"""Audit a fresh unchanged registration; historical amendments use verify.py."""
from experiment import *


def main():
    for name in ['CODE_FREEZE.json', 'FINAL_SELECTION_FREEZE.json']:
        evidence = read(name)
        for filename, digest in evidence.get('files', evidence.get('code_hashes', {})).items():
            require(sha(ROOT/filename) == digest, 'FRESH_REGISTRATION_CODE_CHANGED')
    for name, digest in read('SOURCE_MANIFEST.json')['hashes'].items():
        require(sha(BASE/name) == digest, 'PARENT_AUTHORITY_CHANGED')
    count = 0
    for path in (ROOT/'fits').glob('*/*/MEMBERSHIP.json'):
        evidence = json.loads(path.read_text(encoding='utf-8'))
        cutoff = pd.Timestamp(evidence['cutoff'])
        indexes = np.flatnonzero(np.isin(DAYS, evidence['train_days']))
        require(np.array_equal(indexes, membership(evidence['policy'], cutoff)), 'MEMBERSHIP_NOT_EXACT')
        require((AV.iloc[indexes] < cutoff).all(), 'IMMATURE_TRAINING_LABEL')
        if path.parent.name >= '2025-05-01' and evidence['policy'] != 'fixed':
            require(evidence['Mar_Apr_2025_days'] > 0, 'LATEST_CAUSAL_HISTORY_MISSING')
        count += 1
    for path in (ROOT/'calibration').glob('*.json'):
        for evidence in json.loads(path.read_text(encoding='utf-8')):
            indexes = np.flatnonzero(np.isin(DAYS, evidence['source_days']))
            require((AV.iloc[indexes] < pd.Timestamp(evidence['issue_time'])).all(), 'RESIDUAL_MATURITY')
    frame = pd.read_parquet(ROOT/'PREDICTIONS.parquet')
    require(np.isfinite(frame[['actual_GPUh', 'Q50', 'Q90']]).all().all(), 'NONFINITE')
    require((frame.Q90 >= frame.Q50).all() and (frame.Q50 >= 0).all(), 'QUANTILE_SUPPORT')
    for (split, tag, variant), group in frame.groupby(['split', 'tag', 'variant']):
        expected = DAYS[(L.split.eq(split) & L.eligible).to_numpy()]
        require(sorted(group.target_day.unique()) == list(expected) and len(group) == 24*len(expected),
                'EVALUATION_POPULATION_CHANGED')
    import verify_fit_receipts
    verify_fit_receipts.main()
    dump('VALIDATION.json', dict(time=now(), PASS=True, fresh_registration=True,
         fit_memberships=count, source_unchanged=True, strict_maturity=True,
         production_changed=False, optimizer_executions=0, grid_executions=0))
    print('FRESH REPRODUCTION VALIDATION PASS', count, flush=True)


if __name__ == '__main__':
    main()
