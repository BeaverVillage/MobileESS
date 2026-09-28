"""Explain coverage of old April changes and exact continuing-resource conflicts."""
from build_evidence import *

def main(source):
    f=pd.read_parquet(HERE/'CANONICAL_REFERENCE_LEDGER.parquet')
    old=pd.read_parquet(source/'docs/v42_aidc_site_assignment_forensic/REFERENCE_SITE_ROW_LEDGER.parquet')
    old=old[old.stage.eq('APRIL_CAUSAL_REFERENCE')]
    before=old[old.operating_day.eq('2025-04-01')];after=old[old.operating_day.eq('2025-04-02')]
    p=before.merge(after,on='job_uid',suffixes=('_old1','_old2'))
    p=p[p.state_at_issue_old1.eq('PENDING') & p.state_at_issue_old2.eq('RUNNING')]
    p['old_site_changed']=p.reference_AIDC_site_old1.ne(p.reference_AIDC_site_old2)
    new1=f[f.operating_day.eq('2025-04-01')][['job_uid','episode_id','reference_AIDC_site','capacity_feasible','day_reference_ready']]
    new2=f[f.operating_day.eq('2025-04-02')][['job_uid','episode_id','reference_AIDC_site','capacity_feasible','day_reference_ready']]
    q=new1.merge(new2,on=['job_uid','episode_id'],suffixes=('_new1','_new2'))
    p=p[['job_uid','reference_AIDC_site_old1','reference_AIDC_site_old2','old_site_changed']].merge(q,on='job_uid',how='left')
    p['new_site_changed']=p.reference_AIDC_site_new1.ne(p.reference_AIDC_site_new2)
    p.to_csv(HERE/'OLD_87_APRIL_CHANGE_COVERAGE.csv',index=False)
    changed=p[p.old_site_changed]
    write('OLD_87_APRIL_CHANGE_COVERAGE.json',dict(old_pending_running_comparable=len(p),old_changed=len(changed),
        old_changed_UID_with_same_new_episode=int(changed.episode_id.notna().sum()),
        old_changed_UID_with_preserved_new_site=int((changed.reference_AIDC_site_new1.notna()&~changed.new_site_changed).sum()),
        old_changed_UID_both_new_rows_capacity_feasible=int((changed.capacity_feasible_new1 & changed.capacity_feasible_new2).sum()),
        April1_day_ready=bool(new1.day_reference_ready.all()),April2_day_ready=bool(new2.day_reference_ready.all()),
        full_412_day_ready=read(HERE/'REFERENCE_LEDGER_FREEZE.json')['ready']))
    records=[]
    lookup=f.set_index(['operating_day','episode_id'])
    audit=pd.read_csv(HERE/'REFERENCE_CAPACITY_RACK_AUDIT.csv',low_memory=False)
    for i in audit[audit.kind.eq('SITE_CAPACITY_VIOLATION')].itertuples():
        prior=(pd.Timestamp(i.day)-pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        for episode in i.episodes.split('|'):
            r=lookup.loc[(i.day,episode)];previous=lookup.loc[(prior,episode)] if (prior,episode) in lookup.index else None
            assert r.reference_site_origin=='INHERITED_EPISODE_REFERENCE','NEW_PLACEMENT_OVERLAPPED_RESERVED_OBLIGATION'
            records.append(dict(day=i.day,site=i.site,start=i.start,end=i.end,site_GPU=i.GPU,site_cap=i.capacity,
                job_uid=r.job_uid,episode_id=episode,requested_GPU=r.requested_GPU,state=r.state_at_issue,
                prior_state=None if previous is None else previous.state_at_issue,
                reference_start=r.reference_start_slot,duration=r.safe_duration_slots,duration_authority=r.duration_authority,
                cause='CONTINUING_OBLIGATIONS_INCONSISTENT_WITH_SYNTHETIC_SITE_CAPACITY_AND_CURRENT_CAUSAL_SERVICE',
                overlapping_new_placement=False,episode_identity_error_detected=False,
                future_runtime_used=False,runtime_dependent=True,site_preserved=True))
    pd.DataFrame(records).to_csv(HERE/'CONTINUING_CAPACITY_CONFLICT_DETAILS.csv',index=False)
    write('CONFLICT_CLASSIFICATION_SUMMARY.json',dict(site_time_segments=len(audit[audit.kind.eq('SITE_CAPACITY_VIOLATION')]),
        conflicting_episode_segment_rows=len(records),all_are_inherited_obligations=True,overlapping_new_placement=0,
        unresolved_service_start_job_days=int(audit.kind.eq('REFERENCE_START_STATE_CONFLICT').sum()),
        root_classification='Synthetic capacity + independent causal service-state reconstruction; no source-backed requeue/reconciliation authority. Attribution of a causal improvement from a different runtime is not attempted.',
        no_teleport_repair=True,no_capacity_rebase=True,no_new_episode_invention=True))
    print(read(HERE/'OLD_87_APRIL_CHANGE_COVERAGE.json'),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);main(p.parse_args().source)
