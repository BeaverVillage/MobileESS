"""Offline reference-only construction; never runs a policy/electrical solver."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO))
from v42_reference_episode import *
from dataclasses import fields
from datetime import datetime,timezone
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import argparse,random,shutil
import pandas as pd
import pyarrow as pa

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
@lru_cache(None)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(p):return dict(path=str(p),sha256=sha(p),bytes=Path(p).stat().st_size)
def write(name,obj):
    with (HERE/name).open('x',encoding='utf8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
def text(name,value):
    with (HERE/name).open('x',encoding='utf8') as f:f.write(value)
def day_hash(pair):
    directory,day=pair
    return day,digest(frozen_day(directory,day,audit_only=True))
def main(source,local,caproot):
    forensic=source/'docs/v42_aidc_site_assignment_forensic'
    protected={}
    for p in [forensic/'INPUT_PRESERVATION_BEFORE.json',forensic/'EVIDENCE_MANIFEST.json']:
        contents=read(p);records=contents if isinstance(contents,list) else contents['files']
        for r in records:
            assert sha(r['path'])==r['sha256'],'PROTECTED_DRIFT:'+r['path'];protected[r['path']]=r
        protected[str(p)]=rec(p)
    write('PROTECTED_INPUTS_BEFORE.json',list(protected.values()))
    code=rec(REPO/'v42_reference_episode.py')
    write('DESIGN_REGISTRATION.json',dict(contract=CONTRACT,created_utc=datetime.now(timezone.utc).isoformat(),code=code,
        role='Fixed implementation before any new April outcome/continuity/capacity metrics; no tuning from audit results',
        running_new='episode-keyed weighted preference; whole interval capacity check',pending_new='inherited numeric first-fit full requested-service reference rule',
        continuation='immutable site; RUNNING uses current causal remaining duration; PENDING retains absolute reference start; expired unexecuted reservation blocks rather than invents a requeue rule',
        independent_daily_workers=True,previous_policy_day_output_used=False,May_evaluation=False))
    caps=read(caproot/'V41R2_780GPU_CAPACITY_AUTHORITY.json')['site_capacity']
    racks=read(caproot/'V41R2_LOGICAL_RACK_AUTHORITY.json')['logical_Rack_pools']
    weights=local.parent/'ieee123_per_mess_pr/dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_PRIMARY_SITE_WEIGHTS.csv'
    w=pd.read_csv(weights)
    capacity=Capacity(tuple(sorted(caps.items())),tuple((r['rack_pool_id'],r['aidc_id'],r['compatibility_GPU_limit']) for r in racks),tuple(zip(w.site_id,w.capacity_weight)))
    write('CAPACITY_INPUT.json',dict(sites=capacity.sites,racks=capacity.racks,prior=capacity.prior,
        authority=[rec(caproot/'V41R2_780GPU_CAPACITY_AUTHORITY.json'),rec(caproot/'V41R2_LOGICAL_RACK_AUTHORITY.json'),rec(weights)],
        gang_splitting=False,logical_racks_nonadditive=True,physical_rack_claim=False))
    builder=ReferenceBuilder(capacity);repeat=ReferenceBuilder(capacity)
    frames=[];audits=[];day_hashes={};sources=[];ready_days=[];inherited_conflicts=[]
    snapshots=sorted((local/'policy_snapshots').glob('*/D1_AIDC_SNAPSHOT.parquet'))
    assert len(snapshots)==412 and snapshots[-1].parent.name=='2025-04-30'
    (HERE/'days').mkdir(exist_ok=False)
    for index,p in enumerate(snapshots):
        day=p.parent.name;assert day<'2025-05-01'
        f=pd.read_parquet(p);sources.append(rec(p))
        # Empty historical snapshots still have a defined causal issue boundary.
        issue=int((pd.Timestamp(day,tz='Etc/GMT-10')-pd.Timedelta(hours=6)).timestamp())
        observed=[]
        for r in f.itertuples():
            assert int(r.issue_time.timestamp())==issue
            observed.append(Observation(str(r.id),str(r.source_job_hash),int(r.submit_time.timestamp()),str(r.state_at_issue),
                int(r.gpus_requested) if pd.notna(r.gpus_requested) and float(r.gpus_requested).is_integer() else None,
                math.ceil(float(r.safe_duration_seconds)/900) if pd.notna(r.safe_duration_seconds) and r.safe_duration_seconds>0 else None,
                float(r.safe_duration_seconds) if pd.notna(r.safe_duration_seconds) and math.isfinite(r.safe_duration_seconds) else None,
                str(r.duration_authority),bool(r.resource_request_valid),str(r.qos),
                int(r.known_running_start.timestamp()) if pd.notna(r.known_running_start) else None))
        result=builder.day(day,issue,observed)
        reproduced=repeat.day(day,issue,list(reversed(observed)))
        assert digest(result)==digest(reproduced),'CANONICAL_RERUN_DRIFT'
        prior_sweep=HERE/'attempts/build_004/days'/f'{day}.json.gz'
        if prior_sweep.exists():
            assert digest(result)==digest(json.loads(gzip.decompress(prior_sweep.read_bytes()))),'ENDPOINT_INDEX_CHANGED_REFERENCE'
        day_hashes[day]=digest(result)
        (HERE/'days'/f'{day}.json.gz').write_bytes(gzip.compress(json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode(),mtime=0))
        ready_days.append(dict(day=day,ready=result['ready'],rows=len(result['rows'])))
        for row in result['rows']:
            row=dict(row,snapshot_sha256=sources[-1]['sha256'],day_reference_ready=result['ready'])
            frames.append(row)
            if row['status'] not in ('NEW_RESERVED','INHERITED_RESERVED'):
                audits.append(dict(day=day,kind=row['status'],site=row['reference_AIDC_site'],episodes=row['episode_id'],
                    GPU=row['requested_GPU'],start=row['reference_start_slot'],end=row['reference_end_slot'],
                    runtime_dependent=row['status']=='REFERENCE_START_STATE_CONFLICT'))
        for issue_row in result['issues']:
            audits.append(dict(issue_row,day=day,episodes='|'.join(issue_row['episodes'])))
        if index%60==0:print('Reference days',index+1,'/',len(snapshots),flush=True)
    ledger=pd.DataFrame(frames)
    ledger.to_parquet(HERE/'CANONICAL_REFERENCE_LEDGER.parquet',index=False)
    write('CANONICAL_REFERENCE_LEDGER_SCHEMA.json',dict(contract=CONTRACT,columns={field.name:str(field.type) for field in pa.Table.from_pandas(ledger,preserve_index=False).schema},
        temporal_null='Authority missing; not inferred false and not expanded',capacity_feasible='Row interval/rack check only; day_reference_ready also required',
        unresolved_sites='Retain assigned site on conflict; no assignment is null; never clip/split',
        source_record_hash='raw archive hash | member | row | UID inherited source_job_hash',
        interval_coordinates='15-minute issue-origin slots, full service/carry-out; no D-day clipping',
        start_authority='New PENDING issue release 0; continuing PENDING absolute reservation; RUNNING current causal remaining',
        eligibility='Reference resource eligibility only; native V42 time/migration domain not activated'))
    pd.DataFrame(audits).to_csv(HERE/'REFERENCE_CAPACITY_RACK_AUDIT.csv',index=False)
    problems=Counter(r['kind'] for r in audits)
    counts=dict(SITE_CAPACITY_VIOLATIONS=problems['SITE_CAPACITY_VIOLATION'],RACK_COMPATIBILITY_VIOLATIONS=problems['RACK_COMPATIBILITY_VIOLATION'],
        GANG_SPLITTING_EVENTS=0,UNASSIGNED_BY_CONTINUITY_CONFLICT=problems['UNASSIGNED_BY_CONTINUITY_CONFLICT'],
        OVERSIZE_PRESERVED_COUNT=sum(v for k,v in problems.items() if k.startswith('OUT_OF_DOMAIN_OVERSIZE')),
        REFERENCE_START_STATE_CONFLICT=problems['REFERENCE_START_STATE_CONFLICT'],EPISODE_BOUNDARY_UNRESOLVED=problems['EPISODE_BOUNDARY_UNRESOLVED'],
        scope='All 412 days and complete requested-service intervals; capacity violation count is site/time segments, oversize/conflict counts are job-days',
        issue_counts=dict(problems),days=ready_days,ready_days=sum(d['ready'] for d in ready_days),
        no_new_assignment_over_continuing_obligations=True,runtime_authority_unchanged=True,
        runtime_dependence='Overlapping obligations and expired PENDING reference reservations depend on inherited duration and independently reconstructed state. No alternative runtime or rescheduling contract was invented.')
    write('REFERENCE_CAPACITY_RACK_SUMMARY.json',counts)
    # Adjacent source-backed episodes; retain failures separately, never delete them.
    prior=ledger.copy();prior['next_day']=(pd.to_datetime(prior.operating_day)+pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    pairs=prior.merge(ledger,left_on=['job_uid','episode_id','next_day'],right_on=['job_uid','episode_id','operating_day'],suffixes=('_previous','_current'))
    pairs=pairs[pairs.continuation_from_previous_snapshot_current].copy()
    pairs['both_assigned']=pairs.reference_AIDC_site_previous.notna()&pairs.reference_AIDC_site_current.notna()
    pairs['site_changed']=pairs.both_assigned & pairs.reference_AIDC_site_previous.ne(pairs.reference_AIDC_site_current)
    cols=['job_uid','episode_id','operating_day_previous','operating_day_current','state_at_issue_previous','state_at_issue_current',
          'reference_AIDC_site_previous','reference_AIDC_site_current','both_assigned','site_changed','status_current','day_reference_ready_current']
    pairs[cols].to_csv(HERE/'CROSS_DAY_CONTINUITY_AUDIT.csv',index=False)
    continuing=pairs.episode_id.nunique()
    cross=dict(N_CROSS_DAY_CONTINUING_EPISODES=continuing,N_CONTINUATION_EDGES=len(pairs),N_SAME_REFERENCE_SITE=int((pairs.both_assigned & ~pairs.site_changed).sum()),
        N_EXPLAINED_SITE_CHANGES=0,N_UNEXPLAINED_REFERENCE_SITE_CHANGES=int(pairs.site_changed.sum()),
        MAX_REFERENCE_SITES_PER_CONTINUING_EPISODE=int(ledger[ledger.episode_id.isin(pairs.episode_id)].groupby('episode_id').reference_AIDC_site.nunique().max()),
        BOTH_ASSIGNED_EDGES=int(pairs.both_assigned.sum()),UNASSIGNED_OR_UNRESOLVED_EDGES=int((~pairs.both_assigned).sum()),
        count_semantics='Episode count is distinct; same/change counts are adjacent continuation edges. Missing assignments are not counted as preserved assigned sites.',
        no_rows_dropped=len(ledger)==sum(d['rows'] for d in ready_days))
    write('CROSS_DAY_CONTINUITY_SUMMARY.json',cross)
    april=pairs[(pairs.operating_day_previous=='2025-04-01')&(pairs.operating_day_current=='2025-04-02')&pairs.state_at_issue_previous.eq('PENDING')&pairs.state_at_issue_current.eq('RUNNING')]
    april[cols].to_csv(HERE/'APR1_APR2_PENDING_RUNNING_CONTINUITY.csv',index=False)
    write('APR1_APR2_CONTINUITY_SUMMARY.json',dict(APR1_PENDING_TO_APR2_RUNNING_COMPARABLE=len(april),
        APR1_PENDING_TO_APR2_RUNNING_UNEXPLAINED_SITE_CHANGE=int(april.site_changed.sum()),both_assigned=int(april.both_assigned.sum()),
        unavailable_assignments=int((~april.both_assigned).sum()),old_changes=87,
        interpretation='Zero unexplained changes is not evidence of feasible closure if reference assignments or full native state are blocked.'))
    ledger[['job_uid','episode_id','operating_day','state_at_issue','reference_AIDC_site','reference_start_slot','spatial_eligible','temporal_eligible_if_authorized','status','day_reference_ready']].to_csv(HERE/'SPATIAL_TEMPORAL_ELIGIBILITY_AUDIT.csv',index=False)
    mutations=0;attempts=0
    for r in ledger[ledger.state_at_issue.eq('RUNNING') & ledger.reference_AIDC_site.notna()].to_dict('records'):
        for s in caps:
            if s==r['reference_AIDC_site']:continue
            attempts+=1
            try:validate_initial_placement(r,s,r['reference_start_slot'])
            except ValueError:pass
            else:mutations+=1
    # Existing V42 validator evidence is protected, not overwritten or replaced.
    existing=read(forensic/'RUNNING_INITIAL_SITE_IMMUTABILITY.json')
    write('RUNNING_IMMUTABILITY_AUDIT.json',dict(RUNNING_INITIAL_SITE_MUTATION_OPTIONS=mutations,negative_tests=attempts,
        existing_V42_validator=existing,existing_source_changed=False,new_boundary_guard=True))
    ready=counts['ready_days']==len(ready_days) and cross['N_UNEXPLAINED_REFERENCE_SITE_CHANGES']==0 and mutations==0
    write('REFERENCE_LEDGER_FREEZE.json',dict(contract=CONTRACT,ready=ready,created_utc=datetime.now(timezone.utc).isoformat(),
        ledger=rec(HERE/'CANONICAL_REFERENCE_LEDGER.parquet'),code=code,day_hashes=day_hashes,
        daily_bytes={d:rec(HERE/'days'/f'{d}.json.gz')['sha256'] for d in day_hashes},
        construction='Precomputed once from causal snapshots; no previous policy worker output',
        PREVIOUS_POLICY_DAY_OUTPUT_USED=False,policy_optimization_has_run=False,May_evaluation=False))
    days=list(day_hashes);chrono=dict(day_hash((HERE,d)) for d in days);reverse=dict(day_hash((HERE,d)) for d in reversed(days))
    shuffled=days.copy();random.Random(42).shuffle(shuffled);randomized=dict(day_hash((HERE,d)) for d in shuffled)
    with ProcessPoolExecutor(max_workers=4) as pool:parallel=dict(pool.map(day_hash,[(HERE,d) for d in shuffled]))
    assert chrono==reverse==randomized==parallel==day_hashes
    write('WORKER_ORDER_REPRODUCIBILITY.json',dict(DAILY_WORKER_ORDER_INVARIANT=True,workers=4,mode='Independent OS processes',
        reads='Frozen manifest + own compressed day only; audit_only for blocked states; production reader fails closed',
        chronological=chrono,reverse=reverse,randomized=randomized,parallel=parallel,
        canonical_rerun_hash_equality=True,reversed_within_snapshot_inputs_tested=True,previous_worker_outputs_required=False))
    old=pd.read_parquet(forensic/'REFERENCE_SITE_ROW_LEDGER.parquet');oldhist=old[old.stage.eq('HISTORICAL_RUNNING_INITIALIZER')]
    comparisons=[]
    for scope,g in [('ALL_HISTORICAL',ledger),('APRIL',ledger[ledger.operating_day.ge('2025-04-01')])]:
        dayscope=set(g.operating_day);oldg=oldhist[oldhist.operating_day.isin(dayscope)]
        oldcounts=oldg.dropna(subset=['reference_AIDC_site']).groupby('job_uid').agg(days=('operating_day','nunique'),sites=('reference_AIDC_site','nunique'))
        ng=g[g.state_at_issue.eq('RUNNING')].dropna(subset=['reference_AIDC_site']).groupby('episode_id').agg(days=('operating_day','nunique'),sites=('reference_AIDC_site','nunique'))
        comparisons.append(dict(scope=scope,old_valid_multiday_RUNNING_UID=int((oldcounts.days>1).sum()),old_multisite_RUNNING_UID=int(((oldcounts.days>1)&(oldcounts.sites>1)).sum()),
            new_assigned_multiday_RUNNING_episodes=int((ng.days>1).sum()),new_multisite_RUNNING_episodes=int(((ng.days>1)&(ng.sites>1)).sum()),
            new_rows=len(g),new_site_unassigned_rows=int(g.reference_AIDC_site.isna().sum()),new_capacity_feasible_rows=int(g.capacity_feasible.sum()),
            new_spatial_eligible_rows=int(g.spatial_eligible.sum()),new_temporal_authority_rows=0,denominator_change_disclosed=True))
    pd.DataFrame(comparisons).to_csv(HERE/'OLD_VS_NEW_REFERENCE_COMPARISON.csv',index=False)
    # Exact old vs new April reference occupancy, including every post-H endpoint.
    occupancy=[]
    for day in ['2025-04-01','2025-04-02']:
        oldref=read(local.parent/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002'/day/'CAUSAL_REFERENCE.json')['jobs']
        for version,entries in [('OLD',oldref),('NEW',ledger[ledger.operating_day.eq(day)].to_dict('records'))]:
            points=defaultdict(lambda:defaultdict(int))
            for r in entries:
                s=r['AIDC_site'] if version=='OLD' else r['reference_AIDC_site'];start=r['start_slot'] if version=='OLD' else r['reference_start_slot'];end=r['end_slot'] if version=='OLD' else r['reference_end_slot']
                if s is None or s=='UNASSIGNED' or pd.isna(start) or pd.isna(end):continue
                points[s][int(start)]+=r['requested_GPU'];points[s][int(end)]-=r['requested_GPU']
            for s,pts in points.items():
                use=0;times=sorted(pts)
                for i,t in enumerate(times[:-1]):
                    use+=pts[t];occupancy.append(dict(day=day,version=version,site=s,start=t,end=times[i+1],GPU=use,capacity=caps[s]))
    pd.DataFrame(occupancy).to_csv(HERE/'OLD_NEW_REFERENCE_OCCUPANCY.csv',index=False)
    old_evidence=HERE/'prior_forensic';old_evidence.mkdir()
    for name in ['FINAL_VERDICT.json','UID_SITE_CONSISTENCY_SUMMARY.json','APRIL_REFERENCE_TRANSITION_AUDIT.json','PENDING_SPATIAL_ELIGIBILITY_SUMMARY.json','GRID_OUTCOME_LEAKAGE_AUDIT.json']:
        shutil.copyfile(forensic/name,old_evidence/name)
    rawschema=read(forensic/'RAW_KESTREL_LOCATION_FIELD_AUDIT.json')
    write('EPISODE_SOURCE_FIELD_AUDIT.json',dict(raw_archive=rawschema['archive'],schemas_inspected=len(rawschema['schema_inventory']),
        fields=rawschema['schema_inventory'][0]['columns'],explicit_restart_requeue_attempt_field=False,
        job_uid='normalized raw id, unique in GPU-H100 pre-May scanner; immutable source_record_hash links archive/member/row',
        scheduler_job_id_array_fields='job_id/array_pos/array_range exist in raw schema; they are not attempt counters and are not used to invent episodes',
        execution_start='only known_running_start <= issue; continuity consistency check, not a future start feature',
        state_transition='PENDING/RUNNING at issue from inherited causal snapshot; no future completion input',
        missing_or_changed_identity='EPISODE_BOUNDARY_UNRESOLVED; explicit causal attempt evidence required to establish a new attempt for a previously observed UID'))
    write('REFERENCE_GENERATOR_INPUT_AUDIT.json',dict(allowed_observation_fields=[f.name for f in fields(Observation)],
        REFERENCE_GENERATOR_POLICY_LABEL_READS=0,REFERENCE_GENERATOR_GRID_RESULT_READS=0,REFERENCE_GENERATOR_MAY_OUTCOME_READS=0,REFERENCE_GENERATOR_FUTURE_ACTUAL_READS=0,
        input_files=sources,capacity=rec(HERE/'CAPACITY_INPUT.json'),code=code,
        excluded_channels=['policy id/results','electrical kernel','MESS','actual future runtime/end','future workload','May outcomes'],
        no_future_timestamp_for_episode_reset=True,source_schema_proof=rec(HERE/'EPISODE_SOURCE_FIELD_AUDIT.json')))
    write('SOURCE_MANIFEST.json',dict(code=[code,rec(Path(__file__))],snapshots=sources,
        capacity=read(HERE/'CAPACITY_INPUT.json')['authority'],old_forensic=rec(forensic/'EVIDENCE_MANIFEST.json'),
        raw_contract=rec(source/'docs/v42_final/V42_POLICY_CAUSAL_SNAPSHOT_CONTRACT.json')))
    sha.cache_clear()
    for r in protected.values():assert sha(r['path'])==r['sha256'],'PROTECTED_AFTER_DRIFT'
    write('PROTECTED_INPUTS_AFTER.json',dict(PASS=True,unchanged=len(protected),changed=0))
    print(json.dumps(dict(ready=ready,rows=len(ledger),cross=cross,problems=dict(problems),ready_days=counts['ready_days']),indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--local',type=Path,required=True);p.add_argument('--capacity',type=Path,required=True)
    args=p.parse_args();main(args.source,args.local,args.capacity)
