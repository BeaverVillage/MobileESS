"""Evidence-backed closure of the unchanged 122-case diagnostic universe."""
from pathlib import Path
from collections import Counter, defaultdict
import json
import re
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, write_parquet
from dayahead.v40h.identity import file_record, require, verify_file
from dayahead.v40d_actual.inputs import frozen_jobs, observations
from .electrical import ROOT, now
from .authority import timing_from_observation, classify, PRE_COMPLETE, AUTHORIZED, MISSING, VERSION
from dayahead.v40d_actual.job_replay import timestamp
from datetime import datetime, timedelta, timezone
from .census import lineage


def adjudicate_census(repo):
    repo=Path(repo).resolve(); root=repo/ROOT
    census=read(root/'V40I_ACTUAL_EXECUTION_AUTHORITY_CENSUS.json'); raw=read(root/'V40I_RAW_TO_REPLAY_LINEAGE.json')
    require(not census['scan_errors'],'CENSUS_SCAN_ERRORS_MUST_BE_RESOLVED')
    blocked=pd.read_parquet(repo/'dayahead/artifacts/v40h_production_integrity/PRE_DAY_COMPLETE_RECLASSIFICATION.parquet')
    keys={(r.day,r.case,str(r.job_uid)) for r in blocked.itertuples()}
    actual_matches=[]; counts=Counter(); source_sightings=Counter()
    with (root/'CENSUS_TYPED_UID_SIGHTINGS.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line); path=row['path']; name=Path(path).name.lower()
            is_actual_ledger=name in ('job_ledger.parquet','rack_ledger.parquet','job_gpu_contributions.parquet')
            match=re.search(r'(2025-05-\d\d)[\\/](B[0-3])[\\/]',path)
            sites=[v for v in row['sites'].values() if isinstance(v,str) and v.startswith('AIDC')]
            if is_actual_ledger and match:
                same=(*match.groups(),row['uid']) in keys
                counts['actual_ledger_same_case_UID_rows' if same else 'actual_ledger_other_case_or_day_UID_rows']+=1
                if same and sites: actual_matches.append(row)
            source_sightings[path]+=1
    # Some historical ledgers assigned the common synthetic RUNNING snapshot.
    # Join them to their producer's frozen decision and full job ledger; never
    # promote the isolated rack/site label to a current execution authority.
    reviewed=[]; ledger_cache={}
    raw_jobs=pd.read_parquet(root/'RAW_BLOCKED_UID_NODE_EVIDENCE.parquet').set_index('id')
    for candidate in actual_matches:
        directory=Path(candidate['path']).parent; key=str(directory)
        if key not in ledger_cache:
            job_path=directory/'job_ledger.parquet'; decision_path=directory/'CORRECTED_PLANNING_DECISION_FREEZE.json'
            require(decision_path.is_file(),'HISTORICAL_ACTUAL_PRODUCER_BINDING_REQUIRED')
            frozen=read(decision_path); jobs=frozen['decision']['AIDC_decision']
            require(isinstance(jobs,list),'HISTORICAL_ACTUAL_DECISION_SCHEMA')
            ledger_cache[key]=(pd.read_parquet(job_path).set_index('job_uid'),{str(x['job_uid']):x for x in jobs},
                file_record(job_path),file_record(decision_path))
        ledger,decision,lr,dr=ledger_cache[key]; uid=candidate['uid']; actual=ledger.loc[uid]
        require(actual.state_at_issue=='RUNNING' and actual.actual_execution_end<=24 and not actual.migration_selected,
            'NEW_ACTIVE_ACTUAL_SITE_AUTHORITY_REQUIRES_REVIEW')
        require(actual.AIDC_site==decision[uid]['AIDC_site'],'HISTORICAL_ACTUAL_DECISION_SITE_DRIFT')
        day,case=re.search(r'(2025-05-\d\d)[\\/](B[0-3])[\\/]',candidate['path']).groups()
        issue=datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))-timedelta(hours=6)
        raw_job=raw_jobs.loc[uid];raw_start=timestamp(raw_job.start_time);raw_end=timestamp(raw_job.end_time)
        require(raw_start<=issue<raw_end and abs((raw_end-issue).total_seconds()/900-float(actual.actual_execution_end))<1e-8,
            'HISTORICAL_DERIVED_TIMING_DOES_NOT_MATCH_RAW')
        require(raw_end<=issue+timedelta(hours=6),'HISTORICAL_RAW_TIMING_NOT_PRE_DAY_COMPLETE')
        reviewed.append({**candidate,'job_ledger':lr,'producer_decision':dr,
            'case_id':day+'/'+case,'raw_timing_matches_derived':True,'raw_actual_end':raw_end.isoformat(),
            'raw_timing_source':raw['evidence'],'raw_record_identifier':'id='+uid,
            'producer_source':file_record(repo/'dayahead/v40e/smoke.py'),
            'source_lineage':'V40E.smoke.initial common RW planning snapshot -> corrected Planning freeze -> frozen-site Actual replay',
            'actual_finish':float(actual.actual_execution_end),'post_D_day_active_compute':False,
            'disposition':'HISTORICAL_PRE_DAY_RUNNING_TIMING_CORROBORATION_ONLY_SITE_NOT_PROMOTED'})
    write_json(root/'V40I_HISTORICAL_ACTUAL_SITE_ADJUDICATION.json',reviewed)
    prior44=read(repo/'dayahead/artifacts/v40h_production_integrity/PRE_DAY_COMPLETE_RECLASSIFICATION.json')['EXISTING_UNASSIGNED_44_CASE_BLOCKER']['cases']
    original_keys={d+'/'+c for d,c in prior44};found_keys={r['case_id'] for r in reviewed}
    old_case_uids={(r.day+'/'+r.case,str(r.job_uid)) for r in blocked.itertuples() if r.day+'/'+r.case in original_keys}
    matched=[r for r in reviewed if (r['case_id'],r['uid']) in old_case_uids]
    joined={'revision':'V40I','discovered_record_count':len(reviewed),'unique_job_uid_count':len({r['uid'] for r in reviewed}),
        'matched_original_blocked_case_count':len({r['case_id'] for r in matched}),
        'unmatched_record_count':len(reviewed)-len(matched),'unmatched_blocked_case_count':len(original_keys-{r['case_id'] for r in matched}),
        'matched_expanded_122_case_count':len(found_keys & {d+'/'+c for d,c,u in keys}),
        'original_blocker_universe':'EXISTING_UNASSIGNED_44_CASE_BLOCKER from V40H, joined on day/baseline/UID',
        'discovered_cases':sorted(found_keys),'original_blocked_cases':sorted(original_keys),
        'raw_derived_timing_matches':all(r['raw_timing_matches_derived'] for r in reviewed),
        'equal_numbers_do_not_imply_equal_sets':True,'site_authority_promoted':False}
    write_json(root/'V40I_44_JOB_VS_44_CASE_JOIN.json',joined)
    rows=read(root/'CENSUS_FILE_INDEX.json'); classified=[]
    source_lineage=lineage(repo)
    for row in rows:
        if not row['contains_UID']: continue
        p=row['path']; low=p.lower(); name=Path(p).name.lower()
        actual_ledger=name in ('job_ledger.parquet','rack_ledger.parquet','job_gpu_contributions.parquet')
        if 'frozen_job_observations' in low:
            source='dayahead/tools/audit_v40d_actual_replay.py'; label='ACTUAL_DURATION_AND_OBSERVED_TIMING_ONLY'
        elif actual_ledger or 'terminal_actual' in low or 'actual_10_migration' in low:
            source='dayahead/v40g_segments/actual.py' if 'v40g_segment' in low else 'dayahead/v40d_actual/job_replay.py'
            label='HISTORICAL_ACTUAL_OTHER_UID_DAY_OR_UNASSIGNED_PRE_DAY_ROW'
        elif any(k in low for k in ('kestrel','snapshot','job_ledger','runtime_prediction','per_job_runtime')):
            source='dayahead/v37/aidc_materializer.py'; label='RAW_OR_CAUSAL_TIMING_NO_COUNTERFACTUAL_AIDC_SEGMENTS'
        elif any(k in low for k in ('site_authority_audit','pre_day_complete')):
            source='dayahead/v40d_actual/site_audit.py'; label='PRIOR_DIAGNOSTIC_LABEL_NOT_ACTUAL_AUTHORITY'
        else:
            source='dayahead/v40d_actual/inputs.py'; label='PLANNING_OR_HISTORICAL_DIAGNOSTIC_NOT_CURRENT_ACTUAL_AUTHORITY'
        row.update(raw_authority_path=raw['raw_authority']['path'],raw_authority_hash=raw['raw_authority']['sha256'],
            source_code_path=str(repo/source), producer='SOURCE_LINEAGE:' + source,
            source_commit=next((x['source_commit'] for x in source_lineage if x['source'] and x['source']['path']==str(repo/source)),None),
            producer_attribution_semantics='Reader/producer lineage witness; exact historical writer commit may be unrecoverable.',
            authority_loss_stage='RAW_SYNTHETIC_AIDC_AUTHORITY_ABSENT',
            authority_loss_reason='Raw nodes omitted by parser are recoverable physical identifiers, not missing counterfactual AIDC allocations. Planning clips pre-D-day jobs and loader retains UNASSIGNED.',
            final_authority_classification=label, active_interval_coverage='NO_COMPLETE_CURRENT_BLOCKED_ACTIVE_INTERVAL_SITE_AUTHORITY',
            planning_fallback_used=False)
        classified.append(row)
    write_json(root/'CENSUS_ADJUDICATED_CANDIDATES.json',classified)
    census.update(status='FORENSIC_COMPLETE_FAIL_CLOSED',adjudicated_candidates=file_record(root/'CENSUS_ADJUDICATED_CANDIDATES.json'),
        raw_lineage=file_record(root/'V40I_RAW_TO_REPLAY_LINEAGE.json'),source_lineage=lineage(repo),
        historical_actual_case_join_counts=dict(counts),same_blocked_case_actual_site_match_count=len(actual_matches),
        historical_actual_site_adjudication=file_record(root/'V40I_HISTORICAL_ACTUAL_SITE_ADJUDICATION.json'),
        active_interval_authority_matches=0,
        raw_information_loss=raw['physical_node_information_loss'],upstream_authority_absence=raw['counterfactual_AIDC_authority_loss'],
        actual_AIDC_authority_candidates_accepted=0, timing_site_segment_authorities_are_separate=True)
    write_json(root/'V40I_ACTUAL_EXECUTION_AUTHORITY_CENSUS.json',census)
    lines=['# V40I Actual authority census','',f"총 {census['scanned_files']:,}개 파일, typed UID 후보 {len(classified):,}개, 읽기 오류 0개를 조사했다.",
        '', 'Raw 29개 Parquet member에서 blocked UID 2,543개를 모두 확인했으며, frozen observation의 시간·GPU와 일치한다.',
        'Raw nodelist는 실제 물리 노드 정보다. observation adapter에서 누락되지만 원본으로 복구 가능하다(Case 1).',
        '반면 현재 합성 AIDC 12개에 대한 counterfactual 실행 배치·구간 권위는 raw schema에 없다(Case 2). nodelist 복원만으로 해결되지 않는다.',
        '동일 day/case/UID의 V40E 과거 ledger에서 pre-day RUNNING 44개에 대한 job/rack 기록 88개를 추가 확인했다. 생산자 Planning freeze까지 연결했으며 모두 경계 전에 완료된다. 이 기록의 site를 현재 Actual 권위로 승격하지 않았다. 대기 작업의 active interval 전체를 증명하는 기록은 없었다.',
        '', '| 단계 | source | 확인된 lineage |','|---|---|---|']
    for row in census['source_lineage']: lines.append(f"| {row['stage']} | {row['source']['path'] if row['source'] else raw['raw_authority']['path']} | {row['finding']} |")
    (root/'V40I_ACTUAL_EXECUTION_AUTHORITY_CENSUS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return census


def build_closure(repo):
    repo=Path(repo).resolve(); root=repo/ROOT; old=repo/'dayahead/artifacts/v40d_actual_realized_replay'
    census=read(root/'V40I_ACTUAL_EXECUTION_AUTHORITY_CENSUS.json'); require(census['status']=='FORENSIC_COMPLETE_FAIL_CLOSED','CENSUS_ADJUDICATION_REQUIRED')
    prior=pd.read_parquet(repo/'dayahead/artifacts/v40h_production_integrity/PRE_DAY_COMPLETE_RECLASSIFICATION.parquet')
    universe={(r.day,r.case,str(r.job_uid)):r._asdict() for r in prior.itertuples(index=False)}
    obs=observations(old); obs_record=file_record(old/'V40D_FROZEN_JOB_OBSERVATIONS.parquet')
    contract=file_record(repo/'dayahead/v40d_actual/job_replay.py'); raw=read(root/'V40I_RAW_TO_REPLAY_LINEAGE.json')
    bindings=read(old/'V40D_ACTUAL_DECISION_BINDING_AUDIT.json')['cases']; rows=[]; proofs=[]
    for binding in bindings:
        jobs,issue=frozen_jobs(repo,binding)
        decision=file_record(binding['AIDC_decision_source']); certificate=file_record(binding['certificate'])
        ledger=file_record(repo/'dayahead/artifacts/v37_r4a_per_day_aidc/days'/binding['day']/'V37_R4A_JOB_LEDGER.parquet')
        for job in jobs:
            key=(binding['day'],binding['case'],str(job['job_uid']))
            if key not in universe: continue
            timing=timing_from_observation(job,obs[key[2]],issue,observation_record=obs_record,replay_contract_record=contract)
            result=classify(uid=key[2],day=key[0],timing=timing)
            proof={'case_id':key[0]+'/'+key[1],'uid':key[2],'timing':timing,
                'case_source_files':[decision,certificate,ledger], 'issue_time':issue.isoformat()}
            proofs.append(proof)
            row={'case_id':key[0]+'/'+key[1],'uid':key[2],'day':key[0],'baseline':key[1],
                'prior_block_reason':universe[key]['reason'],**result,
                'actual_start':timing['actual_start'],'actual_finish':timing['actual_finish'],
                'earliest_start':timing['earliest_start'],'earliest_finish':timing['earliest_finish'],
                'remaining_service_semantics':timing['remaining_service_semantics'],
                'authority_status':result['final_classification'],'classifier_version':VERSION,
                'raw_authority_path':raw['raw_authority']['path'],'raw_authority_hash':raw['raw_authority']['sha256'],
                'adapter_path':str(repo/'dayahead/tools/audit_v40d_actual_replay.py'),
                'materializer_path':str(repo/'dayahead/v39a/spatial.py'),
                'actual_replay_loader_path':str(repo/'dayahead/v40d_actual/inputs.py'),
                'authority_loss_stage':'TIMING_CLOSED_SITE_NOT_REQUIRED_AFTER_COMPLETION' if result['blocker_released'] else 'RAW_COUNTERFACTUAL_AIDC_ALLOCATION_ABSENT',
                'physical_node_loss_stage':'OBSERVATION_ADAPTER_COLUMN_PROJECTION_RECOVERABLE',
                'authority_loss_reason':'Physical node list omitted by timing parser; raw lacks case-specific synthetic AIDC allocation. Temporal-to-spatial clipping removes pre-day planning assignment; planning cannot supply Actual authority.',
                'planning_fallback_detected':True,'planning_fallback_used':False,
                'active_interval_coverage':'COMPLETE_TIMING_NO_POST_BOUNDARY_COMPUTE' if result['blocker_released'] else 'ACTUAL_ADMISSION_AND_SITE_INTERVAL_UNRESOLVED',
                'final_authority_classification':result['final_classification'],
                'frozen_decision_source':decision['path'],'frozen_decision_hash':decision['sha256'],
                'frozen_observation_source_member':obs[key[2]]['source_member']}
            rows.append(row)
        print(binding['day'],binding['case'],'closure rows',len(rows),flush=True)
    require(len(rows)==len(universe)==8786,'BLOCKED_JOB_UNIVERSE_CHANGED')
    groups=defaultdict(list)
    for row in rows: groups[row['case_id']].append(row)
    require(len(groups)==122,'BLOCKED_CASE_UNIVERSE_CHANGED')
    cases=[]
    for key,values in sorted(groups.items()):
        labels=Counter(r['final_classification'] for r in values)
        label=MISSING if labels[MISSING] else AUTHORIZED if labels[AUTHORIZED] else PRE_COMPLETE
        cases.append({'case_id':key,'classification':'ACTUAL_EXECUTION_AUTHORITY_MISSING' if label==MISSING else label,
            'job_counts':dict(labels),'blocker_released':label!=MISSING})
    counts=Counter(MISSING if r['classification']=='ACTUAL_EXECUTION_AUTHORITY_MISSING' else r['classification'] for r in cases)
    result={'revision':'V40I','classifier_version':VERSION,'TOTAL':122,'LEGITIMATE_PRE_DAY_COMPLETE':counts[PRE_COMPLETE],
        'ACTUAL_EXECUTION_AUTHORIZED':counts[AUTHORIZED],'AUTHORITY_MISSING':counts[MISSING],
        'ACTUAL_EXECUTION_AUTHORITY_MISSING':counts[MISSING],
        'BLOCKER_RELEASED':counts[PRE_COMPLETE]+counts[AUTHORIZED],'BLOCKER_REMAINING':counts[MISSING],
        'job_rows':len(rows),'job_classification_counts':dict(Counter(r['final_classification'] for r in rows)),
        'authority_loss_stage_case_counts':{'TIMING_CLOSED_SITE_NOT_REQUIRED':counts[PRE_COMPLETE],
            'RAW_COUNTERFACTUAL_AIDC_ALLOCATION_ABSENT':counts[MISSING]},
        'physical_node_adapter_loss_is_separate_recoverable_issue':True,'planning_fallback_used':False,
        'production_cohort_changed':False,'fresh_production_runs':0,'cases':cases,
        'UID_8749975':[r for r in rows if r['uid']=='8749975']}
    require(sum(result[k] for k in ('LEGITIMATE_PRE_DAY_COMPLETE','ACTUAL_EXECUTION_AUTHORIZED','AUTHORITY_MISSING'))==122,'CASE_PARTITION_INCONSISTENT')
    frame=pd.DataFrame(rows); frame.to_csv(root/'V40I_122_CASE_AUTHORITY_CLOSURE.csv',index=False,encoding='utf-8')
    write_parquet(root/'V40I_122_CASE_AUTHORITY_CLOSURE.parquet',frame)
    write_json(root/'V40I_ACTUAL_TIMING_PROOFS.json',proofs)
    result['timing_proofs']=file_record(root/'V40I_ACTUAL_TIMING_PROOFS.json')
    write_json(root/'V40I_122_CASE_AUTHORITY_CLOSURE.json',result)
    missing=[]
    for row in rows:
        if row['blocker_released']: continue
        missing.append({'case':row['case_id'],'UID':row['uid'],
            'missing_interval':{'earliest_ready_slot':row['earliest_start'],'earliest_finish_no_delay':row['earliest_finish'],
                'actual_admission_and_finish':'UNKNOWN_UNTIL_FULL_EXECUTION_TIMING_AUTHORITY','required_coverage':'Every active compute/service interval, including pre-D-day admission and all migration gaps.'},
            'missing_authority_type':['COUNTERFACTUAL_ACTUAL_ADMISSION_TIMING','ACTUAL_AIDC_EXECUTION_SITE','ACTUAL_COMPUTE_ACTIVE_SEGMENTS'],
            'searched_paths':census['search_roots'],'searched_source_classes':list(census['classification_counts']),
            'why_available_evidence_is_insufficient':row['authority_loss_reason'],
            'raw_physical_nodes_recoverable':True,'raw_physical_nodes_equal_synthetic_AIDC':False,
            'exact_evidence_required_to_release_blocker':'A source-bound exact completion/interval timing proof <= D00, or complete case/UID-bound Actual admission, AIDC-site and compute-active segment records with explicit zero-compute gaps and full service conservation.',
            'cohort_redesign':'Proposal only: define upstream counterfactual allocation authority for all temporal jobs under a separately reviewed common/case-specific contract. No redesign performed.'})
    write_json(root/'V40I_MISSING_ACTUAL_EXECUTION_AUTHORITY_REQUEST.json',{'revision':'V40I','remaining_cases':counts[MISSING],
        'missing_UID_case_rows':len(missing),'census':file_record(root/'V40I_ACTUAL_EXECUTION_AUTHORITY_CENSUS.json'),'requests':missing})
    return result


if __name__=='__main__':
    adjudicate_census(Path.cwd()); print(build_closure(Path.cwd()))
