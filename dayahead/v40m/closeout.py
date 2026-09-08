"""Bind fresh raw searches to the original case universe and produce receipts."""
from .forensic import *
from .authority import classify,aggregate,timestamp,deduplicate_raw
from datetime import timedelta
import unittest

def build():
    identity=read(OUT/'V40M_72_BLOCKER_IDENTITY.json')
    sightings=pd.read_parquet(OUT/'V40M_TYPED_UID_SIGHTINGS.parquet')
    sources=pd.read_parquet(OUT/'V40M_SOURCE_SEARCH_RESULTS.parquet')
    sightings['sighting_row_0based']=range(len(sightings))
    prior=pd.read_parquet(OLD/'V40I_122_CASE_AUTHORITY_CLOSURE.parquet')
    proofs=read(OLD/'V40I_ACTUAL_TIMING_PROOFS.json')
    proofmap={(r['case_id'],r['uid']):r for r in proofs}
    # Recheck every input bound by the old timing proof, without importing its
    # replay runner or modifying any old artifact.
    bound={norm(r['path']):r for p in proofs for r in p['case_source_files']+p['timing']['authority_files']}
    verification=[]
    for r in bound.values():
        actual=sha(r['path']);assert actual==r['sha256'],r['path']
        verification.append({'path':r['path'],'sha256':actual,'verified':True})
    raw=[]
    for r in sightings[sightings.source_path.str.contains('esif.hpc.kestrel.job-anon.zip',regex=False)].to_dict('records'):
        f=json.loads(r['fields'])
        if str(f.get('id'))!=r['uid']:continue
        raw.append({'uid':r['uid'],'domain':'KESTREL_HISTORY','actual_start':f['start_time'],'actual_end':f['end_time'],
            'nodes':f.get('nodelist'),'gpus_requested':f.get('gpus_requested'),
            'source_path':r['source_path'],'source_sha256':r['source_sha256'],'member':r['member'],
            'member_sha256':r['member_sha256'],'row_key':r['row_key'],'sighting_row_0based':r['sighting_row_0based']})
    groups,raw_conflicts=deduplicate_raw(raw)
    raw_lineage=read(OLD/'V40I_RAW_TO_REPLAY_LINEAGE.json')
    expected_members={r['member']:r['sha256'] for r in raw_lineage['members']}
    assert all(r['source_sha256']==raw_lineage['raw_authority']['sha256'] and
               r['member_sha256']==expected_members[r['member']] for r in raw)
    original_uids={u for c in identity['cases'] for u in c['all_UIDs']}
    assert {u for u,d in groups}==original_uids
    obs_path=SOURCE/'dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet'
    obs=pd.read_parquet(obs_path);obs['id']=obs.id.astype(str)
    assert not obs.id.duplicated().any()
    obs=obs.set_index('id')
    observed_conflicts=[]
    for r in raw:
        o=obs.loc[r['uid']]
        fields=[]
        if timestamp(r['actual_start'])!=timestamp(o.start_time):fields.append('actual_start')
        if timestamp(r['actual_end'])!=timestamp(o.end_time):fields.append('actual_end')
        if int(r['gpus_requested'])!=int(o.gpus_requested):fields.append('gpus_requested')
        if timestamp(r['actual_start'])>=timestamp(r['actual_end']):fields.append('chronology')
        if fields:observed_conflicts.append({'key':[r['uid'],'KESTREL_HISTORY'],'source_A':r,
            'source_B':{**record(obs_path),'row_key':'id='+r['uid'],'actual_start':str(o.start_time),'actual_end':str(o.end_time)},
            'conflicting_fields':fields})
    raw_conflicts.extend(observed_conflicts)
    raw_digest=digest(raw)
    raw_path=write('V40M_RAW_UID_EVIDENCE.json',{'records':raw,'record_sha256':raw_digest,'raw_conflicts':raw_conflicts,
        'frozen_observations':record(obs_path),'all_original_UIDs_recovered':True,'observation_timestamp_GPU_match':True})

    # Candidate review remains explicit. Exact current-case rows whose producer
    # is a frozen Planning replay cannot supply independent allocation authority.
    old_adjudicated=read(OLD/'CENSUS_ADJUDICATED_CANDIDATES.json')
    old_adjudication_record=record(OLD/'CENSUS_ADJUDICATED_CANDIDATES.json')
    old_by_hash={r['sha256']:r for r in old_adjudicated}
    reviews=[];potential=[]
    missing_keys={(r.case_id,str(r.uid)) for r in prior[~prior.blocker_released].itertuples()}
    # Content deduplication must not erase date/baseline identity carried in a
    # path. Rebind canonical typed records for each exact-case alias.
    alias_audit=[];alias_rows=[]
    groups_by_path={p:g for p,g in sightings.groupby('source_path',sort=False)}
    for alias in sources[sources.reason=='HASH_IDENTICAL_TO_PARSED_SOURCE'].to_dict('records'):
        match=re.search(r'(2025-05-\d\d)[\\/](B[0-3])(?:[\\/]|$)',alias['path'])
        if not match or alias['canonical_path'] not in groups_by_path:continue
        cid='/'.join(match.groups());canonical=groups_by_path[alias['canonical_path']]
        matching=canonical[canonical.uid.map(lambda uid:(cid,uid) in missing_keys)]
        if matching.empty:continue
        alias_audit.append({'alias_path':alias['path'],'sha256':alias['sha256'],'canonical_path':alias['canonical_path'],
            'case_id':cid,'UIDs':sorted(set(matching.uid)),'canonical_sighting_rows':matching.sighting_row_0based.tolist()})
        for row in matching.to_dict('records'):
            row['source_path']=alias['path'];alias_rows.append(row)
    write('V40M_SOURCE_ALIAS_CASE_AUDIT.json',alias_audit)
    if alias_rows:sightings=pd.concat([sightings,pd.DataFrame(alias_rows)],ignore_index=True)
    for source,group in sightings.groupby('source_path',sort=True):
        dispositions=Counter(group.disposition);matched_keys=set();site_rows=[];explicit=[]
        for r in group.to_dict('records'):
            f=json.loads(r['fields']);ctx=json.loads(r['context'])
            match=re.search(r'(2025-05-\d\d)[\\/](B[0-3])(?:[\\/]|$)',source)
            cid=ctx.get('case_id') or f.get('case_id')
            day=ctx.get('day') or f.get('day');baseline=ctx.get('baseline') or f.get('baseline') or ctx.get('case') or f.get('case')
            if not cid and day and baseline:cid=str(day)[:10]+'/'+str(baseline)
            if not cid and match:cid='/'.join(match.groups())
            same=(cid,r['uid']) in missing_keys
            if same:matched_keys.add((cid,r['uid']))
            sites={k:v for k,v in f.items() if 'site' in k.lower() or k in ('AIDC_site','aidc_id')}
            if same and any(isinstance(v,str) and v.startswith('AIDC') for v in sites.values()):
                site_rows.append({'case_id':cid,'uid':r['uid'],'row_key':r['row_key'],'sites':sites,
                    'sighting_row_0based':r['sighting_row_0based']})
            if same and (f.get('authority_kind')=='ACTUAL_EXECUTION_SEGMENTS' or ctx.get('authority_kind')=='ACTUAL_EXECUTION_SEGMENTS'):
                explicit.append(r['sighting_row_0based'])
        h=group.source_sha256.iloc[0]
        old=old_by_hash.get(h)
        low=source.lower()
        if old:
            verdict='HASH_VERIFIED_PRIOR_PRODUCER_ADJUDICATION_RECONFIRMED'
            explanation=old.get('authority_loss_reason')
        elif 'esif.hpc.kestrel.job-anon.zip' in low:
            verdict='RAW_TIMESTAMPS_AND_PHYSICAL_NODES_ONLY'
            explanation='Kestrel historical execution; schema contains no synthetic current-case AIDC allocation or admission record.'
        elif any(k in low for k in ('decision','planning','snapshot','reference','freeze')):
            verdict='PLANNING_OR_SNAPSHOT_REJECTED'
            explanation='Frozen planning or reference assignment has no independent Actual allocation authority.'
        elif any(k in low for k in ('v40i','v40h','v40j','v40k','authority','runtime_prediction','per_job_runtime')):
            verdict='PRIOR_DIAGNOSTIC_OR_RUNTIME_RECORD'
            explanation='Diagnostic/derived runtime does not directly certify current-case execution site or admission.'
        elif not matched_keys:
            verdict='NO_EXACT_MISSING_CASE_UID_BINDING'
            explanation='UID sighting without exact date/baseline execution-domain binding is not authority for this case.'
        elif not site_rows and not explicit:
            verdict='NO_DIRECT_CURRENT_CASE_SITE_EVIDENCE'
            explanation='No complete current-case actual site/admission authority in matched typed records.'
        else:
            verdict='REQUIRES_ADJUDICATION'
            explanation='Exact missing-case site candidate requires explicit producer review before acceptance.'
            potential.append(source)
        reviews.append({'source_path':source,'source_sha256':h,'matched_original_UID_count':group.uid.nunique(),
            'exact_missing_UID_case_count':len(matched_keys),'exact_missing_case_keys':[list(k) for k in sorted(matched_keys)],
            'site_candidates':site_rows,'explicit_segment_candidates':explicit,'dispositions':dict(dispositions),
            'verdict':verdict,'reason':explanation,'prior_adjudication_source':old_adjudication_record if old else None})
    review_path=write('V40M_SOURCE_ADJUDICATION.json',reviews)
    write('V40M_CANDIDATES_REQUIRING_REVIEW.json',potential)
    if potential:
        raise ValueError('Unreviewed exact case authority candidates: '+repr(potential))

    sight_indices=sightings.groupby('uid').sighting_row_0based.apply(list).to_dict()
    missing_by_case=defaultdict(list);all_labels=defaultdict(list);preserved=[];job_conflicts=[]
    historical_pre_count=0
    for old in prior.to_dict('records'):
        cid,uid=old['case_id'],str(old['uid']);proof=proofmap[cid,uid];timing=proof['timing']
        rawrows=groups[uid,'KESTREL_HISTORY'];r=rawrows[0]
        boundary=timestamp(cid[:10]+'T00:00:00+10:00');issue=timestamp(proof['issue_time'])
        observed_start,observed_end=timestamp(r['actual_start']),timestamp(r['actual_end'])
        raw_pre=observed_end<=boundary
        accepted=[]
        if timing['counterfactual_timing_complete']:
            assert timing['proof_rule']=='RUNNING_CONTINUES_AT_ISSUE_WITHOUT_READMISSION_OR_MIGRATION'
            assert observed_start<=issue<observed_end<=boundary
            assert abs((observed_end-issue).total_seconds()/900-timing['actual_finish'])<1e-8
            accepted=[{**r,'case_id':cid,'domain':'CURRENT_CASE_EXECUTION','adjudicated':True,
                'source_hash_verified':True,'complete_timing':True,'actual_site':None,'site_origin':None,
                'binding_proof_source':str(OLD/'V40I_ACTUAL_TIMING_PROOFS.json'),
                'binding_proof_key':f'case_id={cid};uid={uid}','binding_rule':timing['proof_rule']}]
        result=classify(cid,uid,boundary.isoformat(),accepted)
        # Conflicting historical raw observations block the affected current
        # case without inventing a source priority.
        conflicts=[c for c in raw_conflicts if c['key'][0]==uid]
        if conflicts:result={'classification':CONFLICT,'conflicts':conflicts,'rejected':[]}
        all_labels[cid].append(result['classification'])
        if old['blocker_released']:
            assert result['classification']==PRE
            preserved.append({'case_id':cid,'uid':uid,'raw_evidence_key':'uid='+uid,'actual_start':r['actual_start'],
                'actual_end':r['actual_end'],'boundary':boundary.isoformat(),'proof_rule':timing['proof_rule']})
            continue
        historical_pre_count+=int(raw_pre)
        why=('Historical start/end and physical nodes are authoritative for Kestrel. This PENDING job has only observed service duration; '
             'case-specific capacity-delayed admission/end and synthetic AIDC allocation are absent. '
             'Historical end before D00 is not proof that this counterfactual case completed before D00.')
        item={'case_id':cid,'UID':uid,'date':cid[:10],'old_status':MISS,'new_classification':result['classification'],
            'required_authority_type':['CURRENT_CASE_ACTUAL_ADMISSION_START_END','DIRECT_ACTUAL_AIDC_EXECUTION_SITE','FULL_ACTIVE_INTERVAL_SITE_COVERAGE'],
            'actual_start':None,'actual_end':None,'actual_site':None,'observed_raw_start':r['actual_start'],
            'observed_raw_end':r['actual_end'],'observed_end_before_D_day':raw_pre,'D_day_boundary':boundary.isoformat(),
            'physical_nodes':r['nodes'],'physical_nodes_are_synthetic_AIDC':False,
            'evidence_strength':'DIRECT_HISTORICAL_TIMING_AND_PHYSICAL_ALLOCATION; CURRENT_CASE_ADMISSION_SITE_MISSING',
            'reason':why,'primary_sources':rawrows,'searched_families':list(FAMILIES),
            'all_UID_sighting_rows':sight_indices.get(uid,[]),'planning_fallback_used':False,'inferred_site_used':False,
            'conflicts':result['conflicts']}
        missing_by_case[cid].append(item)
        job_conflicts.extend(result['conflicts'])
    assert sum(map(len,missing_by_case.values()))==5126
    finalcases=[{**c,'new_classification':aggregate(all_labels[c['case_id']])} for c in identity['cases']]
    counts=Counter(c['new_classification'] for c in finalcases)
    ledger=[]
    for c in finalcases:
        if c['old_status']!=MISS:continue
        children=sorted(missing_by_case[c['case_id']],key=lambda r:r['UID'])
        ledger.append({'case_id':c['case_id'],'UID':[x['UID'] for x in children],'date':c['date'],'baseline':c['baseline'],
            'case_key_sha256':c['case_key_sha256'],'required_authority_type':['ACTUAL_EXECUTION_TIMING','ACTUAL_AIDC_SITE_AND_ACTIVE_SEGMENTS'],
            'old_status':MISS,'new_classification':c['new_classification'],'actual_start':None,'actual_end':None,'actual_site':None,
            'source_SHA256':sorted({r['source_sha256'] for x in children for r in x['primary_sources']}),
            'matched_row_key':f"V40M_TYPED_UID_SIGHTINGS.parquet:uid in case UID list; exact rows in uid_evidence",
            'searched_sources':[{'family':k,'description':v,'manifest_path':str(OUT/'V40M_AUTHORITY_SEARCH_MANIFEST.json')} for k,v in FAMILIES.items()],
            'evidence_strength':'RAW_OBSERVATION_RECOVERED; CURRENT_CASE_EXECUTION_AUTHORITY_INSUFFICIENT',
            'reason':'Case remains blocked unless every constituent UID has adequate current-case authority. See each UID evidence record.',
            'missing_UID_count':sum(x['new_classification']==MISS for x in children),
            'previously_closed_UID_count':len(c['all_UIDs'])-len(c['missing_UIDs']),
            'uid_evidence':children})
    write('V40M_72_CASE_AUTHORITY_LEDGER.json',ledger)
    # JSON strings preserve exact nested evidence and avoid lossy heterogeneous
    # Arrow inference. Scalar case fields remain native Parquet columns.
    complex_columns={'UID','required_authority_type','source_SHA256','searched_sources','uid_evidence'}
    pd.DataFrame([{k:dumps(v) if k in complex_columns else v for k,v in row.items()} for row in ledger]).to_parquet(OUT/'V40M_72_CASE_AUTHORITY_LEDGER.parquet',index=False)
    write('V40M_PRE_DAY_COMPLETE_EVIDENCE.json',{'newly_proven_cases':counts[PRE]-50,'preserved_cases':50,
        'preserved_UID_case_rows':len(preserved),'evidence':preserved,'raw_source':record(raw_path),
        'historical_pre_day_pending_UID_case_rows_not_promoted':historical_pre_count})
    write('V40M_EXECUTION_SITE_EVIDENCE.json',{'newly_proven_cases':counts[AUTH],'accepted':[],
        'physical_node_recovery_is_not_AIDC_authority':True,'candidate_review':record(review_path),
        'raw_evidence':record(raw_path),'planning_or_inferred_site_promotions':0})
    write('V40M_AUTHORITY_CONFLICTS.json',{'case_count':counts[CONFLICT],'conflicts':job_conflicts,
        'raw_duplicate_conflicts':raw_conflicts,'authoritative_source_priority_invented':False})
    write('V40M_AUTHORITY_MISSING_FINAL.json',{'case_count':counts[MISS],'UID_case_rows':sum(x['missing_UID_count'] for x in ledger),
        'cases':[c for c in finalcases if c['new_classification']==MISS],
        'required_external_evidence':'Source-bound current-case admission/end and direct AIDC active-interval allocation, or complete exact pre-D00 timing.'})
    transitions=Counter((c['old_status'],c['new_classification']) for c in finalcases)
    resolved=sum(c['new_classification'] in (PRE,AUTH) for c in finalcases if c['old_status']==MISS)
    classification=('V40M_ACTUAL_AUTHORITY_FULLY_CLOSED' if counts[MISS]==0 and counts[CONFLICT]==0 else
        'V40M_AUTHORITY_CONFLICT_REQUIRES_ADJUDICATION' if counts[CONFLICT]>36 else
        'V40M_ACTUAL_AUTHORITY_PARTIAL_CLOSURE' if resolved else 'V40M_EXTERNAL_AUTHORITY_STILL_MISSING')
    write('V40M_AUTHORITY_TRANSITION_MATRIX.json',{'old':{PRE:50,AUTH:0,CONFLICT:0,MISS:72},
        'new':{k:counts[k] for k in (PRE,AUTH,CONFLICT,MISS)},'transitions':[{'old':a,'new':b,'case_count':n} for (a,b),n in sorted(transitions.items())],
        'case_transitions':[{'case_id':c['case_id'],'old':c['old_status'],'new':c['new_classification']} for c in finalcases],
        'total':122,'resolved_original_72':resolved,'classification':classification,**HOLDS})
    write('V40M_BOUND_SOURCE_HASH_VERIFICATION.json',verification)
    print('CLOSURE',classification,dict(counts),'resolved',resolved,flush=True)

if __name__=='__main__':build()
