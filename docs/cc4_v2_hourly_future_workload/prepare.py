"""Rebuild the frozen population from raw Job parquet and audit before fitting."""
from common import *
import argparse
import re
import subprocess
import zipfile
import pyarrow.parquet as pq


def eligible(r):
    return (r.gpus_requested.gt(0) & np.isfinite(r.gpus_requested) & r.start_time.notna()
            & r.end_time.notna() & r.end_time.gt(r.start_time) & r.start_time.ge(r.submit_time))


def history(b, index, origin):
    require(index.isin(b.index).all(), 'history source coverage')
    a = b.loc[index]
    right = pd.Series(index + pd.Timedelta(minutes=30), index=index)
    close = a.max_observed_end.where(a.max_observed_end.notna() & a.max_observed_end.gt(right), right)
    mature = close.le(origin) & a.unresolved_end_count.eq(0)
    values = np.column_stack([a.submit_count, np.where(mature, a.work_GPUh, 0), mature,
                              np.where(mature, (origin - close).dt.total_seconds() / 3600, 0)]).astype('float32')
    # A still-open job's end value is never exposed. The completion/not-completed
    # mask is observable at origin. The latest used completed value is bounded.
    available = close.where(mature, origin).max()
    require(available <= origin and index.max() + pd.Timedelta(minutes=30) <= origin, 'history maturity')
    return values, available


def features(day, bins, work):
    origin = issue(day).tz_convert('UTC')
    begin = origin + pd.Timedelta(hours=6)
    index = pd.date_range(origin - pd.Timedelta(days=7), periods=336, freq='30min')
    hv, hav = history(bins, index, origin)
    values, names, maturity = [], [], []

    def add(name, value, available):
        names.append(name)
        values.append(np.broadcast_to(value, (24,)))
        maturity.append(available)

    for window in (12, 48, 336):
        for col, field in enumerate(('submit_count', 'mature_GPUh', 'mature_mask', 'maturity_age_hours')):
            for stat in ('mean', 'std', 'max'):
                add(f'history_{field}_{window}_{stat}', getattr(np, stat)(hv[-window:, col]), hav)
    for col, field in enumerate(('submit_count', 'mature_GPUh', 'mature_mask', 'maturity_age_hours')):
        add(f'history_{field}_last', hv[-1, col], hav)
    hour = np.arange(24)
    slot = hour * 4
    dow = pd.Timestamp(str(day)).weekday()
    for name, value in dict(slot15_fraction=slot/95, minute_of_day=slot*15,
                           hour_sin=np.sin(2*np.pi*hour/24), hour_cos=np.cos(2*np.pi*hour/24),
                           weekday_sin=np.sin(2*np.pi*dow/7), weekday_cos=np.cos(2*np.pi*dow/7),
                           weekend=float(dow >= 5), target_hour=hour, lead_hours=6+hour).items():
        add(name, value, origin)
    seasonal = []
    for lag in (7, 14, 21, 28):
        starts = pd.date_range(begin - pd.Timedelta(days=lag), periods=96, freq='15min')
        parents = starts.floor('30min')
        require(parents.isin(bins.index).all(), 'seasonal source coverage')
        b = bins.loc[parents]
        right = pd.Series(parents + pd.Timedelta(minutes=30))
        close = b.max_observed_end.reset_index(drop=True)
        close = close.where(close.notna() & close.gt(right), right)
        mature = (b.unresolved_end_count.to_numpy() == 0) & close.le(origin).to_numpy()
        subset = work[work.submit_time.ge(starts[0]) & work.submit_time.lt(starts[-1] + pd.Timedelta(minutes=15))]
        pos = ((subset.submit_time.astype('int64').to_numpy() - starts[0].value) // 900_000_000_000).astype(int)
        w = np.bincount(pos, weights=subset.work_GPUh, minlength=96)
        count = np.bincount(pos, minlength=96)
        w = np.where(mature, w, 0.)
        available = close.where(mature, origin).max()
        for field, val in [('GPUh', w), ('count', np.where(mature, count, 0)), ('mature', mature)]:
            add(f'seasonal15_{lag}d_{field}', val[::4], available)
        strict = mature & close.lt(origin).to_numpy()
        hourly_mask = strict.reshape(24, 4).all(axis=1)
        seasonal.append((lag, np.where(hourly_mask, w.reshape(24, 4).sum(axis=1), 0), hourly_mask, available))
    add('window_start_slot', slot, origin)
    add('horizon_hours', 1, origin)
    for lag, w, mask, available in seasonal:
        add(f'cumulative_lag_{lag}d_GPUh', w, available)
        add(f'cumulative_lag_{lag}d_mature', mask, available)
    local = index.tz_convert(TZ)
    hr = local.hour + local.minute / 60
    past = np.column_stack([hv, np.sin(2*np.pi*hr/24), np.cos(2*np.pi*hr/24),
                            np.sin(2*np.pi*local.dayofweek/7), np.cos(2*np.pi*local.dayofweek/7)]).astype('float32')
    x = np.stack(values, axis=1).astype('float32')
    require(x.shape == (24, 71) and np.isfinite(x).all(), 'feature shape or finite')
    require(all(v <= origin for v in maturity), 'feature available after issue')
    return x, past, names, maturity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authority', type=Path, required=True, help='Original PR59 local experiment directory')
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--oracle', type=Path, required=True)
    args = parser.parse_args()
    require(not (ROOT/'DATA.npz').exists(), 'immutable prepared output already exists')
    a = args.authority.resolve()
    r5 = a/'history/B/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'
    sources = [source_record(p, why) for p, why in [
        (args.raw, 'raw Job authority, all parquet partitions'),
        (a/'raw_work.parquet', 'frozen CC4 eligible job population'),
        (a/'raw_bins.parquet', 'frozen causal history bins'),
        (a/'DATA.npz', 'PR59 target and 71-feature lineage'),
        (a/'DAY_LEDGER.parquet', 'PR59 historical membership and maturity'),
        (r5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet', 'original split authority'),
        (a/'history/A/dayahead/v41/data.py', 'PR42 eligibility code'),
        (a/'history/A/dayahead/v41/workload.py', 'PR42 causal feature code'),
        (a/'models_offline.py', 'PR59 TFT/DeepAR code'),
        (a/'run_experiment.py', 'PR59 LightGBM settings and workflow'),
        (args.oracle/'SUMMARY.json', 'PR57 immutable ceiling finding'),
        (args.oracle/'SOURCE_MANIFEST.json', 'PR57 source hashes')]]
    require(sources[0]['sha256'] == '3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f', 'raw archive hash drift')
    manifest = dict(created_at=now(), repository='BeaverVillage/MobileESS',
         base_commit='659a0a66a76d28d1f8103a2f2976ec4cda410136',
         PR42='04f9c738ad80786b3860638304043b06129c04ef', PR57='3c9ce99acd8ed64f9993f3f2b6efa7e5d9c17708',
         PR59='659a0a66a76d28d1f8103a2f2976ec4cda410136', sources=sources)
    if (ROOT/'SOURCE_MANIFEST.json').exists():
        require(json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['sources']==sources, 'authority changed during preparation retry')
    else:
        dump('SOURCE_MANIFEST.json', manifest, exclusive=True)
    jobs, groups, inventory = [], [], []
    seen = set()
    with zipfile.ZipFile(args.raw) as z:
        for name in sorted(z.namelist()):
            if not re.search(r'year=\d{4}/month=\d+/.*\.parquet$', name):
                continue
            with z.open(name) as stream:
                r = pq.read_table(stream, columns=['id', 'submit_time', 'start_time', 'end_time', 'gpus_requested'], use_threads=False).to_pandas()
            ids = set(r.id.astype(str))
            require(len(ids) == len(r) and not ids & seen, 'duplicate raw IDs')
            seen.update(ids)
            for col in ['submit_time', 'start_time', 'end_time']:
                r[col] = pd.to_datetime(r[col], utc=True).astype('datetime64[ns, UTC]')
            require(r.submit_time.notna().all(), 'unknown raw submit time')
            r['gpus_requested'] = pd.to_numeric(r.gpus_requested, errors='raise').astype(float)
            valid = eligible(r)
            w = r.loc[valid].copy()
            w['work_GPUh'] = w.gpus_requested * (w.end_time-w.start_time).dt.total_seconds()/3600
            jobs.append(w)
            r['bin'] = r.submit_time.dt.floor('30min')
            r['unresolved'] = r.end_time.isna().astype(int)
            r['gpu_unresolved'] = (r.gpus_requested.gt(0) & r.end_time.isna()).astype(int)
            groups.append(r.groupby('bin').agg(submit_count=('id','size'), max_observed_end=('end_time','max'),
                          unresolved_end_count=('unresolved','sum'), gpu_unresolved=('gpu_unresolved','sum')))
            inventory.append(dict(member=name, raw_jobs=len(r), eligible_jobs=len(w), eligible_GPUh=w.work_GPUh.sum()))
            print('RAW', name, len(r), len(w), flush=True)
    w = pd.concat(jobs, ignore_index=True)
    oldw = pd.read_parquet(a/'raw_work.parquet')
    wc = w.set_index('id').sort_index()
    oc = oldw.set_index('id').sort_index()
    require(wc.index.equals(oc.index), 'population ID difference: stop promotion')
    require(np.array_equal(wc.work_GPUh, oc.work_GPUh), 'population GPUh difference')
    for col in ('submit_time', 'start_time', 'end_time', 'gpus_requested'):
        require(np.array_equal(wc[col], oc[col]), 'population field difference '+col)
    dump('POPULATION_COMPARISON.json', dict(status='PASS', raw_jobs=len(seen), eligible_jobs=len(w),
         eligible_GPUh=w.work_GPUh.sum(), IDs_equal=True, affected_job_count=0, affected_GPUh=0,
         missing_GPU_imputation=False, population_change=False,
         predicate='finite GPU>0; start/end present; end>start; start>=submit', partitions=inventory))
    b = pd.concat(groups).groupby(level=0).agg(submit_count=('submit_count','sum'),
        max_observed_end=('max_observed_end','max'), unresolved_end_count=('unresolved_end_count','sum'),
        gpu_unresolved=('gpu_unresolved','sum')).sort_index()
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq='30min'))
    for col in ['submit_count', 'unresolved_end_count', 'gpu_unresolved']:
        b[col] = b[col].fillna(0).astype(int)
    b = b.join(w.groupby(w.submit_time.dt.floor('30min')).work_GPUh.sum())
    b.work_GPUh = b.work_GPUh.fillna(0)
    oldb = pd.read_parquet(a/'raw_bins.parquet')
    require(np.array_equal(b.work_GPUh, oldb.work_GPUh), 'raw bin workload drift')
    for col in ['submit_count','unresolved_end_count','gpu_unresolved']:
        require(np.array_equal(b[col], oldb[col]), 'raw bin count drift')
    old = np.load(a/'DATA.npz')
    ledger = pd.read_parquet(a/'DAY_LEDGER.parquet')
    dates = old['days'].astype(str)
    require(np.array_equal(dates, ledger.operating_day.to_numpy()), 'ledger alignment')
    xx, past, yy, proofs, daily = [], [], [], [], []
    feature_error = 0.
    for day in dates:
        origin = issue(day).tz_convert('UTC')
        begin, end = origin + pd.Timedelta(hours=6), origin + pd.Timedelta(hours=30)
        ss = w[w.submit_time.ge(begin) & w.submit_time.lt(end)]
        pos = ((ss.submit_time.astype('int64').to_numpy()-begin.value)//3_600_000_000_000).astype(int)
        y = np.bincount(pos, weights=ss.work_GPUh, minlength=24)
        atomicpos = ((ss.submit_time.astype('int64').to_numpy()-begin.value)//900_000_000_000).astype(int)
        atomic = np.bincount(atomicpos, weights=ss.work_GPUh, minlength=96)
        i = len(yy)
        require(np.allclose(atomic, old['atomic'][i], rtol=0, atol=1e-7), 'raw target reconstruction')
        require(abs(y.sum()-ss.work_GPUh.sum()) < 1e-7, 'daily reconstruction')
        x, p, names, av = features(day, b, w)
        keep = np.arange(71) != 47  # sole renamed field: constant child15_position -> target_hour
        error = np.max(abs(x[:,keep] - old['X1'][i,::4][:,keep]))
        feature_error = max(feature_error, float(error))
        require(error < .01, 'feature lineage numerical drift')
        require(np.array_equal(p, old['past'][i]), 'history lineage drift')
        for name, available in zip(names, av):
            proofs.append(dict(target_day=day, feature=name, feature_available_at=available,
                               issue_time=origin, valid=available<=origin, target_hours='0..23'))
        db = b.loc[(b.index >= begin) & (b.index < end)]
        maturity = max(end, ss.end_time.max()) if len(ss) else end
        if db.gpu_unresolved.sum():
            maturity = pd.Timestamp.max.tz_localize('UTC')
        daily.append(dict(target_day=day, issue_time=origin, label_matured_at=maturity,
                          jobs=len(ss), daily_GPUh=y.sum(), direct_GPUh=ss.work_GPUh.sum(),
                          absolute_error=abs(y.sum()-ss.work_GPUh.sum()), atomic_max_error=float(abs(atomic-old['atomic'][i]).max())))
        xx.append(x); past.append(p); yy.append(y)
    d = pd.DataFrame(daily)
    for col in ['issue_time','label_matured_at']:
        d[col] = pd.to_datetime(d[col], utc=True)
    d['original_role'] = ledger.role
    d['original_eligible'] = ledger.stage_maturity_eligible
    d['split'] = ledger.role
    d['eligible'] = ledger.stage_maturity_eligible & ledger.role.isin(ROLES)
    cuts = {role: issue(day).tz_convert('UTC') for role, day in
            [('TRAIN','2024-09-01'), ('DEVELOPMENT','2024-11-01'), ('CALIBRATION','2024-12-01')]}
    for role, cut in cuts.items():
        mask = d.split.eq(role)
        d.loc[mask, 'eligible'] &= d.loc[mask, 'label_matured_at'].lt(cut)
    d['reason'] = np.where(d.eligible, 'eligible; issue-time features mature; labels before next-stage cutoff',
                           np.where(~d.original_eligible, 'original exclusion/purge preserved',
                                    np.where(~d.split.isin(ROLES),'out of registered calendar','new label maturity exclusion')))
    d.to_csv(ROOT/'DAY_LEDGER.csv', index=False)
    memberships = {}
    for role in ROLES:
        members = d[d.split.eq(role) & d.eligible]
        members.to_csv(ROOT/f'{role}_MEMBERSHIP.csv', index=False)
        memberships[role] = dict(N_days=len(members), N_rows=24*len(members), dates=members.target_day.tolist(),
                                cutoff=cuts.get(role), latest_label_matured_at=members.label_matured_at.max())
    diff = d[['target_day','original_role','split','original_eligible','eligible','reason']].rename(
        columns={'target_day':'date','split':'cc4_v2_role','eligible':'cc4_v2_eligible'})
    diff.to_csv(ROOT/'SPLIT_MEMBERSHIP_DIFF.csv', index=False)
    changed = diff[diff.original_role.isin(ROLES) & (diff.original_eligible != diff.cc4_v2_eligible)]
    dump('DATA_SPLITS_AND_MATURITY.json', dict(status='PASS', split_unit='target_day', timezone=TZ,
        issue='D-1 18:00 fixed UTC+10', memberships=memberships, changed_days=changed.to_dict('records'),
        exact_PR59_day_membership=len(changed)==0, purge_dates=d.loc[d.split.eq('PURGE'),'target_day'].tolist(),
        label_rule='max(day end, all eligible GPU-job observed ends), unresolved positive GPU => unavailable; strictly before consuming issue',
        evaluation_labels='future supervised outcomes; never consumed at their own issue', NO_UNTOUCHED_CONFIRMATION=True))
    y = np.array(yy)
    train = d.split.eq('TRAIN') & d.eligible
    threshold = float(np.quantile(y[train][y[train]>0], .95))
    long = pd.DataFrame(dict(target_day=np.repeat(dates,24), target_hour=np.tile(np.arange(24),len(dates)),
        issue_time=np.repeat([issue(day).isoformat() for day in dates],24), lead_hours=np.tile(np.arange(6,30),len(dates)),
        actual_GPUh=y.ravel(), split=np.repeat(d.split.to_numpy(),24), eligible=np.repeat(d.eligible.to_numpy(),24)))
    long.to_parquet(ROOT/'HOURLY_DATASET.parquet', index=False)
    stats = []
    for role in ROLES:
        z = y[d.split.eq(role) & d.eligible]
        stats.append(dict(split=role,N_days=len(z),N_hours=z.size,zero_hours=int((z==0).sum()),
                          positive_hours=int((z>0).sum()),burst_hours=int((z>threshold).sum()),
                          Q50_GPUh=np.quantile(z,.5),Q90_GPUh=np.quantile(z,.9),max_GPUh=z.max(),total_GPUh=z.sum()))
    pd.DataFrame(stats).to_csv(ROOT/'TARGET_DISTRIBUTION.csv',index=False)
    for col, filename in [('target_hour','TARGET_HOUR_DISTRIBUTION.csv'),('weekday','TARGET_WEEKDAY_DISTRIBUTION.csv')]:
        if col=='weekday':
            long[col]=pd.to_datetime(long.target_day).dt.dayofweek
        long[long.eligible].groupby(['split',col]).actual_GPUh.agg(['size','sum','mean','median','max']).to_csv(ROOT/filename)
    np.savez_compressed(ROOT/'DATA.npz', X=np.array(xx), past=np.array(past), y=y, days=dates)
    pd.DataFrame(proofs).to_parquet(ROOT/'FEATURE_MATURITY_PROOF.parquet',index=False)
    d[['target_day','jobs','daily_GPUh','direct_GPUh','absolute_error','atomic_max_error']].to_csv(ROOT/'DAILY_TARGET_RECONSTRUCTION.csv',index=False)
    dump('TARGET_RECONSTRUCTION_AUDIT.json', dict(status='PASS', days=len(d), hourly_rows=y.size,
        direct_raw_daily_max_error_GPUh=d.absolute_error.max(), frozen_atomic_max_error_GPUh=d.atomic_max_error.max(),
        nonnegative=bool((y>=0).all()), unit='GPU*h', runtime='(end_time-start_time).total_seconds()/3600',
        TRAIN_positive_Q95_burst_threshold_GPUh=threshold, target_cap=None))
    # Counterfactual as-of reconstruction: remove future jobs; replace all future
    # end times by unresolved. This destroys hidden runtimes while preserving
    # what a historical issue could actually observe.
    invariance = []
    for day in ['2024-09-01','2024-11-01','2024-12-01','2025-05-01','2025-05-31']:
        origin = issue(day).tz_convert('UTC')
        bb = b[b.index < origin].copy()
        future = bb.max_observed_end.gt(origin)
        bb.loc[future,'max_observed_end']=pd.NaT
        bb.loc[future,'unresolved_end_count'] += 1
        ww = w[w.submit_time.lt(origin) & w.end_time.le(origin)].copy()
        bb['work_GPUh'] = ww.groupby(ww.submit_time.dt.floor('30min')).work_GPUh.sum().reindex(bb.index).fillna(0)
        cx, cp, _, _ = features(day, bb, ww)
        j = list(dates).index(day)
        require(np.array_equal(cx, xx[j]) and np.array_equal(cp,past[j]), 'as-of invariance failure')
        invariance.append(dict(day=day, hidden_future_jobs_removed=True, hidden_runtime_removed=True, exact_equal=True))
    dump('FEATURE_CONTRACT.json', dict(feature_count=71, feature_names=names, history_shape=[336,8], target_shape=[24],
        lineage='PR59 H1 at 15-minute start slots 0,4,...,92; child15_position replaced by target_hour',
        unchanged_70_features_max_abs_error=feature_error, seasonal15_context='15-minute historical sub-bin, not target-day realized value',
        availability='full proof per feature/day; same maturity applies to each of 24 target hours',
        limitations='logical event-time reconstruction; telemetry ingestion latency and mutable request versions not certified'))
    dump('LEAKAGE_AUDIT.json', dict(status='PASS', proof_rows=len(proofs), target_days=len(d),
        features=71, expanded_feature_hour_checks=len(proofs)*24, invalid_maturity_count=0,
        asof_invariance=invariance, TRAIN_only_scaling_required=True,
        evaluation_label_usage='labels only; no fitting/calibration/selection', full_day_split=True,
        no_future_queue=True, no_future_actual=True, timezone=TZ))
    print('PREPARATION PASS', {k:v['N_days'] for k,v in memberships.items()}, 'feature_error',feature_error,flush=True)


if __name__ == '__main__':
    main()
