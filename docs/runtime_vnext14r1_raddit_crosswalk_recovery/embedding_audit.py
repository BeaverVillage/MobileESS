from common import *
import pyarrow as pa
import pyarrow.parquet as pq
import sys
COLS=['submit_time','start_time','end_time','wallclock_used_sec','avg_power_per_node']
TIMES=COLS[:3]
def projection():
    assert read(ROOT/'V14_BASE_VERIFICATION.json')['V14_BASE_VERIFIED']
    assert read(ROOT/'PREREGISTRATION.json')['before_match_rates']
    inputs=[];chunks=[];parts=[];offset=0
    for chunk,p in enumerate(sorted((RAD/'data/encrypted_embeddings').glob('*.parquet'))):
        pf=pq.ParquetFile(p)
        # Check dates without reading outcome columns, then use footer bounds + full submit projection.
        submit=pf.read(columns=['submit_time']).to_pandas()['submit_time']
        assert submit.max()<pd.Timestamp('2025-04-01'),str(p)
        d=pf.read(columns=COLS).to_pandas()
        for c in TIMES:assert d[c].dt.tz is None;d[c]=d[c].astype('datetime64[us]').astype('int64')
        d['embedding_global_row']=np.arange(offset,offset+len(d),dtype=np.int64)
        d['embedding_chunk']=np.int16(chunk);d['embedding_row_in_chunk']=np.arange(len(d),dtype=np.int32)
        chunks.append(dict(chunk=p.name,rows=len(d),global_offset=offset,schema=str(pf.schema_arrow),submit_min=str(submit.min()),submit_max=str(submit.max())))
        parts.append(d);offset+=len(d)
        inputs.append(dict(path=str(p),bytes=p.stat().st_size,sha256=next(r['sha256'] for r in read(V14/'SELECTED_FORENSIC_INPUTS.json')['files'] if r['path']==str(p)),hash_authority='V14 hash, size/mtime reverified; payload vectors not decoded'))
    e=pd.concat(parts,ignore_index=True);e.to_parquet(LOCAL/'EMBEDDING_SHARED_METADATA.parquet',index=False)
    p=RAD/'data/historic_job_trace.parquet';pf=pq.ParquetFile(p)
    h=pf.read(columns=COLS+['job_id']).to_pandas()
    assert h.submit_time.max().tz_convert('UTC')<pd.Timestamp('2025-04-01',tz='UTC')
    fields={}
    for c in TIMES:
        fields[c]=dict(timezone=str(h[c].dt.tz),min=str(h[c].min()),max=str(h[c].max()))
        h[c+'_utc']=h[c].dt.tz_convert('UTC').dt.tz_localize(None).astype('datetime64[us]').astype('int64')
        # Literal representation audit only: this is NOT an inferred timezone assignment to E.
        h[c]=h[c].dt.tz_localize(None).astype('datetime64[us]').astype('int64')
    h['historic_row']=np.arange(len(h),dtype=np.int64)
    assert np.array_equal(h.job_id,h.historic_row)
    h.to_parquet(LOCAL/'HISTORIC_SHARED_METADATA.parquet',index=False)
    inputs.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
    write('EMBEDDING_SCHEMA_AUDIT.json',dict(embedding_rows=len(e),historic_rows=len(h),row_difference=len(h)-len(e),chunks=chunks,historic_schema=str(pf.schema_arrow),historic_time=fields,projected_columns=COLS,vector_payload_read=False,positional_job_id_verified=True,inputs=inputs,null_counts_embedding=e[COLS].isna().sum().to_dict(),null_counts_historic=h[COLS].isna().sum().to_dict(),subsecond_nonzero_embedding={c:int((e[c]%1000000!=0).sum()) for c in TIMES},subsecond_nonzero_historic={c:int((h[c]%1000000!=0).sum()) for c in TIMES}))
    print('PROJECTED',len(e),len(h),flush=True)

def exact_audit(h,e,keys):
    hg=h.dropna(subset=keys).groupby(keys,sort=False,dropna=False).size().rename('historic_count').reset_index()
    eg=e.dropna(subset=keys).groupby(keys,sort=False,dropna=False).size().rename('embedding_count').reset_index()
    m=hg.merge(eg,on=keys,how='inner',validate='one_to_one')
    both=(m.historic_count==1)&(m.embedding_count==1)
    stat=dict(historic_distinct_keys=len(hg),embedding_distinct_keys=len(eg),historic_unique_keys=int((hg.historic_count==1).sum()),embedding_unique_keys=int((eg.embedding_count==1).sum()),exact_matched_keys=len(m),exact_pair_count=int((m.historic_count*m.embedding_count).sum()),matched_historic_rows=int(m.historic_count.sum()),matched_embedding_rows=int(m.embedding_count.sum()),unique_1to1=int(both.sum()),keys_1toMany=int(((m.historic_count==1)&(m.embedding_count>1)).sum()),keys_manyTo1=int(((m.historic_count>1)&(m.embedding_count==1)).sum()),keys_manyToMany=int(((m.historic_count>1)&(m.embedding_count>1)).sum()),unmatched_historic_rows=len(h)-int(m.historic_count.sum()),unmatched_embedding_rows=len(e)-int(m.embedding_count.sum()),ambiguous_embedding_rows=int(m.loc[~both,'embedding_count'].sum()),historic_duplicate_key_rows=int(hg.loc[hg.historic_count>1,'historic_count'].sum()),embedding_duplicate_key_rows=int(eg.loc[eg.embedding_count>1,'embedding_count'].sum()),historic_null_key_rows=int(h[keys].isna().any(axis=1).sum()),embedding_null_key_rows=int(e[keys].isna().any(axis=1).sum()))
    u=m.loc[both,keys].merge(h.drop_duplicates(keys,keep=False),on=keys,validate='one_to_one').merge(e.drop_duplicates(keys,keep=False),on=keys,validate='one_to_one',suffixes=('_h','_e'))
    bad=np.zeros(len(u),dtype=bool);diffs={}
    for c in COLS:
        if c in keys:continue
        a=u[c+'_h'].to_numpy();b=u[c+'_e'].to_numpy();valid=pd.notna(a)&pd.notna(b)
        conflict=~valid|(a!=b);bad|=conflict
        diff=(a[valid]-b[valid]).astype(float)
        diffs[c]=dict(compared=len(u),missing=int((~valid).sum()),numeric_unequal=int((valid&(a!=b)).sum()),difference_quantiles=np.quantile(diff,[0,.5,.9,.99,1]).tolist() if len(diff) else None)
        if c in COLS[3:]:diffs[c]['binary_unequal']=int((a.view('uint64')!=b.view('uint64')).sum())
    stat['contradictory_1to1_rows']=int(bad.sum());stat['consistent_1to1_rows']=int((~bad).sum());stat['contradiction_scope']='All unused shared fields on 1:1 pairs; ambiguous pairs never authorized'
    u['holdout_consistent']=~bad
    ledger=e[['embedding_global_row','embedding_chunk','embedding_row_in_chunk']+keys].merge(m[keys+['historic_count','embedding_count']],on=keys,how='left',validate='many_to_one')
    ledger=ledger.drop(columns=keys).merge(u[['embedding_global_row','historic_row','holdout_consistent']],on='embedding_global_row',how='left',validate='one_to_one')
    ledger['diagnostic_status']=np.where(ledger.historic_count.isna(),'UNMATCHED',np.where((ledger.historic_count!=1)|(ledger.embedding_count!=1),'AMBIGUOUS',np.where(ledger.holdout_consistent.fillna(False),'EXACT_RAW_REPRESENTATION_ONLY','CONTRADICTION')))
    return stat,ledger,diffs

def audit(replay=False):
    h=pd.read_parquet(LOCAL/'HISTORIC_SHARED_METADATA.parquet');e=pd.read_parquet(LOCAL/'EMBEDDING_SHARED_METADATA.parquet')
    stats=[];detail=[]
    for i,keys in enumerate([['submit_time','end_time'],['submit_time','end_time','wallclock_used_sec'],['submit_time','end_time','wallclock_used_sec','avg_power_per_node']]):
        stat,ledger,diffs=exact_audit(h,e,keys)
        stat.update(key='EKEY'+str(i),representation='RAW_REPRESENTATION',status='DIAGNOSTIC_TIMEZONE_AUTHORITY_UNRESOLVED')
        ledger=ledger.sort_values('embedding_global_row').reset_index(drop=True)
        digest=hashlib.sha256(pd.util.hash_pandas_object(ledger,index=False).to_numpy().tobytes()).hexdigest()
        stat['ledger_content_sha256']=digest;detail.append(dict(key=stat['key'],unused_fields=diffs))
        if not replay:ledger.to_parquet(LOCAL/(stat['key']+'_NEGATIVE_FORENSIC_LEDGER.parquet'),index=False)
        stats.append(stat);print(json.dumps(clean(stat)),flush=True)
    if replay:
        prev=read(ROOT/'EMBEDDING_EXACT_AUDIT_DETAIL.json')
        assert [s['ledger_content_sha256'] for s in stats]==prev['ledger_digests']
        write('EMBEDDING_FRESH_PROCESS_REPLAY.json',dict(pass_replay=True,scope='Diagnostic exact raw-representation ledgers; replay does not establish timezone authority',ledger_digests=[s['ledger_content_sha256'] for s in stats]))
    else:
        rows=stats+[dict(key='EKEY'+str(i),representation='UTC_CANONICAL',status='NOT_RUN_NAIVE_EMBEDDING_TIMEZONE_UNPROVEN') for i in range(3)]
        pd.DataFrame(rows).to_csv(ROOT/'EMBEDDING_HISTORIC_KEY_AUDIT.csv',index=False)
        write('EMBEDDING_EXACT_AUDIT_DETAIL.json',dict(stats=stats,holdouts=detail,ledger_digests=[s['ledger_content_sha256'] for s in stats]))
if __name__=='__main__':
    if '--replay' in sys.argv:audit(True)
    elif '--cached' in sys.argv:audit()
    else:projection();audit()
