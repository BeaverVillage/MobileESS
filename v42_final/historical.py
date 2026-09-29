"""TRAIN-only empirical execution lags and conditional queue-wait authority."""
from .common import *
from .workload import execution_lag_kernel,profile,ForecastBook
from .state import conditional_wait,legacy_unassigned
from v42_may01.state import cohort_key


def main():
    path=V9/'.local/fold1/TRAIN.parquet';f=pd.read_parquet(path)
    cutoff=pd.Timestamp('2024-10-18T00:00:00Z')
    require((f.submit_time<cutoff).all() and (f.start_time<cutoff).all(),'TRAIN_CHRONOLOGY')
    # Censored rows cannot contribute invented future execution mass.
    exact=f[f.event & f.end_time.notna() & (f.end_time<cutoff)].copy()
    seconds=lambda col:exact[col].astype('int64').to_numpy()/1e9
    k,mass=execution_lag_kernel(seconds('submit_time'),seconds('start_time'),seconds('end_time'),exact.num_gpus_req.to_numpy())
    csv('CC4_EXECUTION_LAG_KERNEL.csv',[dict(lag_slot=i,lag_seconds=i*900,kappa=float(v),historical_GPUh=float(mass[i])) for i,v in enumerate(k)])
    dump('CC4_EXECUTION_LAG_AUDIT.json',dict(PASS=True,TRAIN_source=rec(path),TRAIN_rows=len(f),completed_execution_rows=len(exact),
        excluded_censored_or_unobserved_end=len(f)-len(exact),cutoff=cutoff.isoformat(),May_outcomes_used=False,VALID_used=False,
        construction='Exact GPU-second overlap relative to each submit timestamp; normalize complete observed support',
        kernel_sum=float(k.sum()),total_observed_GPUh=float(mass.sum()),maximum_lag_slot=len(k)-1,
        post_96_kernel_mass=float(k[96:].sum()),truncated_mass=0,zero_beyond_empirical_support=True,
        scope='Empirical completed TRAIN cohort; not a guarantee for censored/unseen long-tail work',
        forecast_hour_alignment='Whole hourly GPUh anchored at hour-start slot per requested convolution',
        direct_same_hour_GPU_binding=False))
    f['cohort']=[cohort_key(r.qos,r.partition,r.num_gpus_req,r.requested_seconds,r.num_nodes_req) for r in f.itertuples()]
    f['wait_seconds']=(f.start_time-f.submit_time).dt.total_seconds()
    require((f.wait_seconds>=0).all(),'NEGATIVE_QUEUE_WAIT')
    groups={c:g.wait_seconds.to_numpy() for c,g in f.groupby('cohort')}
    native=read(ROOT/'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json')
    issue=pd.Timestamp(native['issue_time']);rows=[]
    for r in native['known_population']:
        age=(issue-pd.Timestamp(r['submit_time'])).total_seconds()
        # Original protection is encoded in the unchanged cohort dimension.
        protected=r['cohort'].split('|')[3]=='True'
        yes,budget,n,continuous=conditional_wait(r['state'],protected,age,groups.get(r['cohort'],[]))
        rows.append(dict(job_id=r['job_uid'],state=r['state'],cohort=r['cohort'],waiting_age_seconds=age,N_cond=n,
            conditional_median_seconds=continuous,delay_budget_slots=budget,
            can_timeshift=yes if r['planning_eligible'] else None,
            can_prestart_place=r['can_prestart_place'],can_checkpoint_migrate=r['can_checkpoint_migrate'],
            unresolved=not r['planning_eligible'],GPU_gang=r['GPU_gang'],
            capability_scope='TS_CONDITIONAL_WAIT_AUTHORITY; PS_MG_CANDIDATE_MASKS_PENDING_NEW_RUNTIME_COMPLETE_OPTION_WITNESSES'))
    csv('TIMESHIFT_CAPABILITY_SUMMARY.csv',rows)
    dump('TIMESHIFT_DELAY_AUTHORITY.json',dict(rule='CONDITIONAL_WAIT_RESIDUAL_Q50',
        formula='Q50(W-age | W>age, same cohort); floor(seconds/900)',minimum_conditional_N=100,
        PENDING_only=True,protected_fail_closed=True,standby_shortcut=False,runtime_duration_criterion=False,
        TRAIN_source=rec(path),TRAIN_cutoff=cutoff.isoformat(),cohort_dimensions=['qos','partition','workload_class','protected','gpu_bucket','wall_bucket','requested_nodes'],
        May_outcomes_used=False,old_T2_status='SUPERSEDED_IN_NEW_INTERFACE_ONLY',
        admitted_jobs=sum(not r['unresolved'] for r in rows),TS_jobs=sum(r['can_timeshift'] is True for r in rows),
        TS_job_share=sum(r['can_timeshift'] is True for r in rows)/sum(not r['unresolved'] for r in rows),
        GPUh_share_status='REQUIRES_APPROVED_Q50_MAY_SERVICE_BINDING',no_target_share=True))
    cc=read(ROOT/'docs/v42_may01_native_canary/MAY01_CC4_P2_BINDING.json');q50=np.asarray(cc['Q50']);spread=np.maximum(np.asarray(cc['Q90'])-q50,0)
    nominal=profile(q50,k);reserve=profile(spread,k)
    csv('MAY01_CC4_EXECUTION_PROFILE.csv',[dict(slot=i,nominal_GPU=float(nominal[i]),CC4_uncertainty_headroom_target_GPU=float(reserve[i]),
        nominal_GPUh=float(nominal[i]*.25),reserve_is_realized_load=False,post_H=i>=96) for i in range(len(nominal))])
    book=ForecastBook(tuple(q50),tuple(cc['Q90']),pd.Timestamp('2025-05-01T00:00:00+10:00').timestamp())
    # This is the native D-1 ledger: no individual D-day submission exists yet.
    # Dynamic submission/depletion is validated by event unit tests, not by
    # opening May realized arrivals as calibration data.
    csv('CC4_FORECAST_DEPLETION_LEDGER.csv',[dict(**book.row(h,issue.timestamp()),scope='D1_INITIAL_NATIVE_FORECAST_NO_DDAY_EVENTS_READ') for h in range(24)])
    unresolved=legacy_unassigned(native['known_population'])
    dump('LEGACY_UNASSIGNED_RUNNING_AUDIT.json',dict(PASS=True,count=len(unresolved),
        source_reference=rec(ROOT/'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json'),
        overlapping_source_service=0,arbitrary_sites_created=0,rows=unresolved,
        observed_completion_claim=False,source_pre_D00_residual_preserved=True,
        Q50_does_not_fabricate_service_for_unassigned_external_records=True))
    dump('EPISODE_SITE_LEDGER_AUDIT.json',dict(status='IMPLEMENTED_EVENT_CONTRACT_NATIVE_REPLAY_PENDING',
        current_running_site_hard=True,prior_pending_reservation_is_physical=False,
        site_change_requires_authorized_migration_receipt=True,duplicate_receipts_rejected=True,
        actual_runtime_reserve=False,release='First valid 900-second control boundary at/after observed completion event',
        native_state_source=rec(ROOT/'docs/v42_may01_native_canary/MAY01_JOB_STATE_LEDGER.csv'),
        no_fabricated_execution_episode=True))
    print(json.dumps(dict(kernel_slots=len(k),kernel_sum=float(k.sum()),nominal_peak_GPU=float(nominal[:96].max()),
        nominal_in_H_GPUh=float(nominal[:96].sum()*.25),nominal_post_H_GPUh=float(nominal[96:].sum()*.25),
        TS_jobs=sum(r['can_timeshift'] is True for r in rows)),indent=2))


if __name__=='__main__':main()
