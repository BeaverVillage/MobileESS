from common16 import *
import gc

def main():
    old=pd.read_parquet(R1/'.local/EKEY2_NEGATIVE_FORENSIC_LEDGER.parquet')
    h=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet',columns=['job_id','submit_time','start_time','end_time','wallclock_used_sec','wallclock_req_sec','nodes_req','processors_req','qos','partition'])
    good=old.diagnostic_status.eq('EXACT_RAW_REPRESENTATION_ONLY')&old.holdout_consistent.eq(True)
    assert int(good.sum())==1775514 and int(old.diagnostic_status.eq('AMBIGUOUS').sum())==5458
    e=old.loc[good,['embedding_global_row','embedding_chunk','embedding_row_in_chunk','historic_row']].copy()
    e['historic_row']=e.historic_row.astype('int64')
    # Cached exact ledger must still have the hash bound by previous evidence.
    previous=read(R1/'LOCAL_EVIDENCE_MANIFEST.json')['files']
    p=R1/'.local/EKEY2_NEGATIVE_FORENSIC_LEDGER.parquet'
    expected=next(r['sha256'] for r in previous if r.get('relative')=='.local/EKEY2_NEGATIVE_FORENSIC_LEDGER.parquet')
    assert sha(p)==expected
    for c in ['submit_time','start_time','end_time']:
        h[c+'_display_us']=h[c].dt.tz_localize(None).astype('datetime64[us]').astype('int64')
    h=h.rename(columns={'job_id':'historic_row'})
    k=pd.read_parquet(LOCAL/'KESTREL_RICH_PROJECTION.parquet',columns=['id','job_id','submit_time','submit_time_display_us','start_time_display_us','end_time_display_us',
        'wallclock_used_sec','wallclock_req_sec','nodes_req','processors_req','gpus_requested','qos','partition'])
    keys=['submit_time_display_us','end_time_display_us','wallclock_used_sec','wallclock_req_sec','nodes_req','processors_req']
    usable=k[keys].notna().all(axis=1)&k[keys[:2]].gt(np.iinfo(np.int64).min).all(axis=1)
    kg=k.loc[usable].copy();counts=kg.groupby(keys,dropna=False,sort=False).size().rename('kestrel_count').reset_index()
    unique=kg.drop_duplicates(keys,keep=False)
    hc=h.groupby(keys,dropna=False,sort=False).size().rename('historic_count').reset_index()
    match=h.merge(counts,on=keys,how='left',validate='many_to_one').merge(hc,on=keys,how='left',validate='many_to_one')
    match=match.merge(unique[keys+['id','job_id','start_time_display_us','gpus_requested','qos','partition']],on=keys,how='left',validate='many_to_one',suffixes=('_h','_k'))
    unambiguous=match.kestrel_count.eq(1)&match.historic_count.eq(1)
    start_conflict=unambiguous&match.start_time_display_us_h.ne(match.start_time_display_us_k)
    qos_conflict=unambiguous&match.qos_h.ne(match.qos_k)
    # Source audit: partition_0000002 and Kestrel 'standard' are different namespaces.
    # Without a published codebook, lexical inequality is NOT a row contradiction.
    partition_incomparable=unambiguous&match.partition_h.ne(match.partition_k)
    conflict=start_conflict|qos_conflict
    match['status']=np.select([match.kestrel_count.isna(),~unambiguous,conflict],['UNMATCHED','AMBIGUOUS','HOLDOUT_CONFLICT'],default='RESEARCH_PROXY_CROSSWALK')
    matched=match[match.status.eq('RESEARCH_PROXY_CROSSWALK')]
    mapping=e.merge(match[['historic_row','id','status','gpus_requested']],on='historic_row',how='left',validate='one_to_one')
    mapping.to_parquet(LOCAL/'EMBEDDING_KESTREL_PROXY.parquet',index=False)
    match[['historic_row','id','status','gpus_requested']].to_parquet(LOCAL/'HISTORIC_KESTREL_PROXY.parquet',index=False)
    # A public aggregate, not millions of row-level anonymous IDs; exact ledger stays local and hash bound.
    distribution=[]
    for scope,d in [('NATIVE_ALL',match),('EKEY2_UNIQUE',match[match.historic_row.isin(e.historic_row)])]:
        for cfg in read(ROOT/'NATIVE_FOLD_CONTRACT.json')['folds']:
            mask=d.submit_time.ge(pd.Timestamp(cfg['valid_from'],tz='UTC'))&d.submit_time.lt(pd.Timestamp(cfg['valid_to'],tz='UTC'))
            for tail,hours in [('ALL',0),('GT4H',4),('GT8H',8),('GT12H',12),('GT24H',24)]:
                a=d.loc[mask&(True if tail=='ALL' else d.wallclock_used_sec.gt(hours*3600))]
                for status,n in a.status.value_counts().items():distribution.append(dict(scope=scope,fold=cfg['fold'],runtime_stratum=tail,status=status,N=int(n),denominator=len(a),rate=float(n/len(a))))
    pd.DataFrame(distribution).to_csv(ROOT/'RADDIT_Kestrel_RESEARCH_PROXY_CROSSWALK.csv',index=False)
    write('RADDIT_CROSSWALK_SUMMARY.json',dict(time=now(),classification='RESEARCH_PROXY_CROSSWALK',PRODUCTION_AUTHORITY_CROSSWALK=False,
        embedding_rows=len(old),unique_EKEY2_candidates=len(e),ambiguous_EKEY2_excluded=5458,EKEY2_unmatched=0,EKEY2_holdout_conflicts=0,
        historic_rows=len(h),historic_to_Kestrel_status=match.status.value_counts().to_dict(),
        unique_embedding_to_Kestrel_status=mapping.status.value_counts().to_dict(),
        historic_mapping_rate=len(matched)/len(h),holdout_conflicts=dict(start=int(start_conflict.sum()),qos=int(qos_conflict.sum())),
        partition_holdout='NOT_COMPARABLE_DIFFERENT_UNMAPPED_NAMESPACES',partition_lexical_inequality_not_conflict=int(partition_incomparable.sum()),
        audit_correction='Before ML: removed invalid cross-namespace partition equality check; first attempt and ledgers preserved. No inferred token mapping, key relaxation, timezone shift or fuzzy match.',
        keys=keys,timezone_policy='Historic literal fixed -06 display; original Kestrel projected to fixed -06. Exact only; no inferred shift or fuzzy recovery.',
        upstream_export_proven=False,duplicates_excluded=True,May_payload=False,
        source_ledgers=[rec(p),rec(LOCAL/'KESTREL_RICH_PROJECTION.parquet')],outputs=[rec(LOCAL/'EMBEDDING_KESTREL_PROXY.parquet'),rec(LOCAL/'HISTORIC_KESTREL_PROXY.parquet')]))
    print('CROSSWALK',match.status.value_counts().to_dict(),mapping.status.value_counts().to_dict(),flush=True)

if __name__=='__main__':main()
