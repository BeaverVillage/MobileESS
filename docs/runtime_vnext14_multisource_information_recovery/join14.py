"""Exact source-ID forensic only. No learner, no approximate timestamp joins."""
from common14 import *
import pyarrow.parquet as pq
import zipfile,io,re


def keys_summary(a,b,keys):
    left=a.groupby(keys,dropna=False).size().reset_index(name='left_N')
    right=b.groupby(keys,dropna=False).size().reset_index(name='right_N')
    # pandas can match null to null; missing identity/timestamp is not exact evidence.
    shared=left.dropna(subset=keys).merge(right.dropna(subset=keys),on=keys,how='inner')
    return dict(keys=keys,left_N=len(a),right_N=len(b),left_unique_keys=len(left),right_unique_keys=len(right),
        left_duplicate_rows=int(a.duplicated(keys,keep=False).sum()),right_duplicate_rows=int(b.duplicated(keys,keep=False).sum()),
        common_keys=len(shared),one_to_one_exact_matches=int(((shared.left_N==1)&(shared.right_N==1)).sum()),
        ambiguous_shared_keys=int(((shared.left_N>1)|(shared.right_N>1)).sum()))


def main():
    assert read(ROOT/'RAW_INVENTORY_RECEIPT.json')['complete']
    assert read(ROOT/'V13_BASELINE_REPRODUCTION.json')['PASS']
    assert (ROOT/'PREREGISTRATION.json').exists()
    archive=RAW_B/'NLR Kestrel Jobs/esif.hpc.kestrel.job-anon.zip'
    path=LOCAL/'ORIGINAL_KESTREL_IDENTITY_PREAPRIL.parquet';members=[];schema=None
    if not path.exists():
        parts=[]
        with zipfile.ZipFile(archive) as z:
            for name in sorted(z.namelist()):
                match=re.search(r'year=(\d+)/month=(\d+)/',name)
                if not match or (int(match[1]),int(match[2]))>=(2025,4) or not name.endswith('.parquet'):continue
                pf=pq.ParquetFile(io.BytesIO(z.read(name)))
                if schema is None:schema=[dict(name=f.name,type=str(f.type)) for f in pf.schema_arrow]
                f=pf.read(columns=['id','job_id','submit_time']).to_pandas()
                f['submit_time']=pd.to_datetime(f.submit_time,utc=True)
                f=f[pd.to_datetime(f.submit_time,utc=True).lt(CUTOFF)].copy()
                f['source_member']=name;parts.append(f);members.append(name)
        k=pd.concat(parts,ignore_index=True);k.to_parquet(path,index=False)
        write('ORIGINAL_KESTREL_PROJECTION_AUDIT.json',dict(time=now(),columns=['id','job_id','submit_time'],
            permitted_members=members,postApril_members_opened=[],runtime_columns_decoded=[],rows=len(k),schema=schema,output=record(path)))
    else:k=pd.read_parquet(path)
    k['submit_time']=pd.to_datetime(k.submit_time,utc=True)
    hist=RAW_B/'RADDiT/data/historic_job_trace.parquet'
    # Check each row group's submission extent before reading additional historic fields.
    pf=pq.ParquetFile(hist);bounds=[]
    for i in range(pf.num_row_groups):
        t=pf.read_row_group(i,columns=['submit_time']).to_pandas().submit_time
        assert pd.to_datetime(t,utc=True).lt(CUTOFF).all()
        bounds.append(dict(row_group=i,N=len(t),submit_min=str(t.min()),submit_max=str(t.max()),all_preApril=True))
    h=pd.read_parquet(hist,columns=['job_id','submit_time','start_time','end_time','wallclock_used_sec','avg_power_per_node'])
    for c in ['submit_time','start_time','end_time']:h[c]=pd.to_datetime(h[c],utc=True)
    assert h.end_time.dropna().lt(CUTOFF).all()
    gpu_source=REPO/'docs/runtime_vnext7_feature_authority_recovery/.local/GPU_PREAPRIL.parquet'
    gpu=pd.read_parquet(gpu_source,columns=['id','job_id','submit_time','start_time','end_time','gpus_requested'])
    # The existing pre-April derivative is backed by original archive identity triples.
    proof=gpu[['id','job_id','submit_time']].merge(k[['id','job_id','submit_time']].drop_duplicates(),on=['id','job_id','submit_time'],how='left',indicator=True)
    assert len(proof)==len(gpu) and proof._merge.eq('both').all()
    all_hierarchy=[keys_summary(k,h,['job_id']),keys_summary(k,h,['job_id','submit_time'])]
    gpu_hierarchy=[keys_summary(gpu,h,keys) for keys in [['job_id'],['job_id','submit_time'],
        ['job_id','submit_time','start_time'],['job_id','submit_time','start_time','end_time']]]
    for item in gpu_hierarchy:print('EXACT_GPU_JOIN',item,flush=True)
    # Retain every V13 job, even when no RADDiT mapping can be authorized.
    permitted=h[~h.duplicated(['job_id','submit_time'],keep=False)][['job_id','submit_time']].assign(raddit_match=True)
    ledger=gpu.merge(permitted,on=['job_id','submit_time'],how='left',validate='many_to_one')
    ledger['raddit_match']=ledger.raddit_match.fillna(False).astype(bool)
    ledger.rename(columns={'id':'v13_job_id','job_id':'slurm_job_id'},inplace=True)
    ledger.to_parquet(LOCAL/'RADDIT_KESTREL_JOIN_LEDGER.parquet',index=False)
    matched=set(ledger.loc[ledger.raddit_match,'v13_job_id'].astype(str))
    strata=[]
    for i in range(1,6):
        for role in ['TRAIN','CAL','VALID']:
            f=pd.read_parquet(V9/'.local'/f'fold{i}'/(role+'.parquet'));m=f.job_id.astype(str).isin(matched)
            selections=[('ALL',pd.Series(True,index=f.index))]+[(f'gt{t}h',f.event&f.runtime_seconds.gt(t*3600)) for t in [4,12,24]]
            selections += [(f'GPU_{lo}_{hi}',f.num_gpus_req.ge(lo)&f.num_gpus_req.lt(hi)) for lo,hi in [(1,4),(4,16),(16,64),(64,float('inf'))]]
            for label,mask in selections:
                strata.append(dict(fold=i,role=role,stratum=label,N=int(mask.sum()),matched=int((mask&m).sum()),
                    join_rate=float(m[mask].mean()) if mask.any() else None,scope='FULL_V13_POPULATION; exact ID+submit; no unmatched rows dropped'))
    pd.DataFrame(strata).to_csv(ROOT/'SEMANTIC_SUPPORT_METRICS.csv',index=False)
    summary=dict(time=now(),scope='Original pre-April Kestrel archive identity universe plus separate fixed V13 GPU population',
        Kestrel_candidate_jobs=len(k),Kestrel_V13_GPU_jobs=len(gpu),RADDiT_historic_jobs=len(h),
        Kestrel_unique_numeric_IDs=int(k.job_id.nunique()),Kestrel_duplicate_numeric_ID_rows=int(k.job_id.duplicated(keep=False).sum()),
        RADDiT_unique_IDs=int(h.job_id.nunique()),RADDiT_duplicate_ID_rows=int(h.job_id.duplicated(keep=False).sum()),
        RADDiT_ID_equals_zero_based_row_position=bool(np.array_equal(h.job_id.to_numpy(),np.arange(len(h)))),
        original_identity_hierarchy=all_hierarchy,V13_GPU_hierarchy=gpu_hierarchy,
        exact_matched_jobs=len(matched),ambiguous_matches=gpu_hierarchy[1]['ambiguous_shared_keys'],
        timestamp_consistent_matches=0,runtime_consistent_matches=0,
        runtime_consistency_scope='No exact ID+submit matches; runtime consistency not assessable. Zero denotes no qualifying matches, not a successful outcome comparison.',
        unmatched_Kestrel_GPU_jobs=len(gpu)-len(matched),unmatched_RADDiT_jobs=len(h),
        RADDIT_KESTREL_JOIN_PROVEN=False,RADDIT_KESTREL_JOIN_RATE=len(matched)/len(gpu),
        source_identity='Kestrel according to local RADDiT README; published job_id is a row index, not a proven Slurm ID crosswalk.',
        timezone='Original timestamps UTC and historic timestamps explicitly -06:00; only normal tz-aware UTC conversion, no fitted shifts.',
        original_archive_identity_verified_for_all_V13_jobs=True,submit_row_group_boundaries=bounds,
        preApril_RADDiT_end_max=str(h.end_time.max()),ledger=record(LOCAL/'RADDIT_KESTREL_JOIN_LEDGER.parquet'),
        inputs=[record(archive),record(hist),record(gpu_source)],
        stop_condition='RADDiT job mapping cannot be proven with the published identity hierarchy. No approximate join or positional-ID substitution is authorized.',
        postApril_outcome_statistics_computed=False,May_payload_opened=False)
    assert len(matched)==0 and all_hierarchy[1]['one_to_one_exact_matches']==0
    write('RADDIT_KESTREL_JOIN_SUMMARY.json',summary)
    write('STOP_CONDITION_RECEIPT.json',dict(time=now(),status='STOPPED_SOURCE_AUTHORITY_FAILURE',
        trigger='RADDIT_JOB_MAPPING_NOT_PROVEN',instruction_section=39,join_summary=record(ROOT/'RADDIT_KESTREL_JOIN_SUMMARY.json'),
        ML_authorized=False,new_model_fits=0,semantic_reducer_fits=0,semantic_neighbor_models_run=0,
        followup_scope='Preserve negative forensic result and complete evidence/reporting only. No V14 model comparison or source-authority workaround.'))
    print('V14_STOPPED_SOURCE_AUTHORITY_FAILURE',len(k),len(h),len(matched),flush=True)


if __name__=='__main__':main()
