"""One-origin production training replay; no held-out outcomes or selection."""
from reproduce import *
from experiment import member


def main():
    day = '2025-05-01'
    issue = pd.Timestamp('2025-04-30T08:00:00Z')
    train = member('expanding', issue)
    reference = read('MODERN_BASELINE_REPRODUCTION.json')['days'][0]
    require(reference['day'] == day and len(train) == reference['training_N'], 'TRAINING_COUNT')
    require(ids(train.job_id) == reference['training_membership_hash'], 'TRAINING_MEMBERSHIP')
    snapshot = Path('D:/ChatGPT/Mobile ESS 2/CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4')/day/'B0/dayahead/ml/ML_SNAPSHOT.json'
    authority = json.loads(snapshot.read_text(encoding='utf-8'))
    frozen_pre = json.loads(Path(authority['preprocessing']['path']).read_text(encoding='utf-8'))
    pre = Preprocess(issue).fit(train)
    require(pre.medians == frozen_pre['medians'] and pre.vocab == frozen_pre['vocab'], 'PREPROCESSING_REFIT_DRIFT')
    columns = ['id','submit_time','wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','partition','qos']
    queries = normalize(pq.read_table(SNAP/day/'V37_R4A_D1_SNAPSHOT.parquet', columns=columns,
                                    filters=[('state_at_issue','==','PENDING')]).to_pandas())
    start = time.perf_counter()
    model = lgb.LGBMRegressor(objective='quantile', alpha=.9, **FIXED).fit(
        pre.transform(train), train.runtime_seconds.to_numpy(float)).booster_
    got = model.predict(pre.transform(queries), num_threads=1)
    expected = np.array([authority['PENDING_JOB_Q90_SECONDS'][job] for job in queries.job_id])
    frozen_text = gzip.decompress(Path(authority['model']['path']).read_bytes()).decode('utf-8')
    frozen_model = lgb.Booster(model_str=frozen_text)
    folder = ROOT/'baseline'/'modern_refit_2025-05-01'
    folder.mkdir(exist_ok=False)
    model_text = model.model_to_string().encode('utf-8')
    (folder/'Q90.txt.gz').write_bytes(gzip.compress(model_text, compresslevel=6, mtime=0))
    pd.DataFrame(dict(job_id=queries.job_id, reproduced_Q90=got, frozen_Q90=expected)).to_parquet(
        folder/'PREDICTION_COMPARISON.parquet', index=False)
    passed = np.array_equal(got, expected)
    dump('MODERN_REFIT_REPRODUCTION.json', dict(time=now(), PASS=passed, day=day,
         training_N=len(train), training_membership_hash=ids(train.job_id), query_N=len(queries),
         maximum_prediction_difference=float(np.max(abs(got-expected))),
         all_tree_info_identical=model.dump_model()['tree_info'] == frozen_model.dump_model()['tree_info'],
         reproduced_model_text_sha256=hashlib.sha256(model_text).hexdigest(),
         frozen_model_text_sha256=hashlib.sha256(frozen_text.encode('utf-8')).hexdigest(),
         latest_training_end=train.end_time.max(), issue_time=issue,
         preprocessing_refit_exact=True, threads=1, seconds=time.perf_counter()-start,
         evaluation_outcomes_read=False, scientific_choices_changed=False))
    require(passed, 'PRODUCTION_REFIT_PREDICTIONS_DIFFER')
    print('MODERN TRAINING REPLAY PASS', len(train), len(queries), flush=True)


if __name__ == '__main__':
    main()
