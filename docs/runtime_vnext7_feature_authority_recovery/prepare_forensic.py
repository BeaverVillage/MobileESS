"""No deduplication, no fit: audit all pre-April archive records."""
from common7 import *
import zipfile,re,collections,gc
import numpy as np,pandas as pd,pyarrow.parquet as pq
CUTOFF=pd.Timestamp('2025-04-01T00:00Z')
FIELDS=['id','job_id','array_pos','array_range','name_hash','user_hash','account_hash','submit_line_hash','work_dir_hash','submit_script_hash','job_type_hash','python_job','reframe_job','partition','qos','state','state_simple','submit_time','start_time','end_time','nodes_req','processors_req','memory_req','wallclock_req','gpus_requested']
REQUEST=['wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','qos','partition','account_hash','user_hash']
def main():
    LOCAL.mkdir(exist_ok=True);index=[];gpu=[];state_rows=[];schemas=[];parts=[];nulls=collections.Counter();states=collections.Counter();total=0
    with zipfile.ZipFile(RAW) as z:
        write('ARCHIVE_MEMBER_INVENTORY.json',dict(source=record(RAW),members=[dict(name=i.filename,uncompressed_bytes=i.file_size,CRC=i.CRC) for i in z.infolist()],payload_policy='Only year/month <=2025/03; all later members metadata only.'))
        for name in sorted(z.namelist()):
            m=re.search(r'year=(\d{4})/month=(\d+)/.*\.parquet$',name)
            if not m or tuple(map(int,m.groups()))>(2025,3):continue
            with z.open(name) as stream:
                pf=pq.ParquetFile(stream);schema=pf.schema_arrow;cols=[k for k in FIELDS if k in schema.names]
                f=pf.read(columns=cols,use_threads=False).to_pandas()
            schemas.append(dict(member=name,fields=[dict(name=x.name,type=str(x.type)) for x in schema],metadata_keys=[k.decode() for k in (schema.metadata or {})]))
            n=len(f)
            for c in ['submit_time','start_time','end_time']:f[c]=pd.to_datetime(f[c],utc=True).astype('datetime64[ns, UTC]')
            f=f[f.submit_time.lt(CUTOFF)].copy();f['source_member']=name;f['source_row']=f.index
            f['end_available_preApril']=f.end_time.notna()&f.end_time.lt(CUTOFF)
            # End outcomes beyond cutoff are removed before label arithmetic.
            f.loc[~f.end_available_preApril,'end_time']=pd.NaT
            f.loc[f.start_time.ge(CUTOFF),'start_time']=pd.NaT
            f['runtime_seconds']=(f.end_time-f.start_time).dt.total_seconds()
            f['label_valid']=f.end_available_preApril&f.start_time.notna()&f.runtime_seconds.ge(0)&f.start_time.ge(f.submit_time)
            f['requested_seconds']=f.wallclock_req.dt.total_seconds()
            total+=len(f);nulls.update({c:int(f[c].isna().sum()) for c in cols});states.update(f.loc[f.end_available_preApril,'state_simple'].fillna('__NULL__'))
            # Keep full job and array identity; never collapse siblings into revisions.
            idx=f[['id','job_id','array_pos','submit_time','source_member','source_row']].copy()
            for k in ['id','source_member']:idx[k]=idx[k].astype('category')
            idx['request_fingerprint']=pd.util.hash_pandas_object(f[REQUEST].astype(str),index=False).to_numpy()
            index.append(idx)
            requeued=f.state.fillna('').str.contains('REQUE|RESTART|RESIZ',case=False,regex=True)&f.end_available_preApril
            if requeued.any():state_rows.append(f[requeued][FIELDS+['source_member','source_row']].copy())
            g=f[pd.to_numeric(f.gpus_requested,errors='coerce').gt(0)].copy()
            for c in g.select_dtypes('object'):g[c]=g[c].astype('category')
            gpu.append(g);parts.append(dict(member=name,raw_rows=n,preApril_rows=len(f),gpu_rows=len(g),mature_rows=int(f.label_valid.sum()),requeue_terminal_rows=int(requeued.sum())))
            print('AUDIT_PART',name,len(f),len(g),flush=True)
    allidx=pd.concat(index,ignore_index=True);index.clear();gc.collect()
    dup_id=allidx.id.duplicated(keep=False);dup_num=allidx.job_id.duplicated(keep=False)
    # Preserve candidate identity rows for exact second-pass field audit.
    candidates=allidx[dup_id|dup_num].copy();candidates.to_parquet(LOCAL/'DUPLICATE_INDEX.parquet',index=False)
    counts=allidx.groupby('job_id',observed=True).size();fullcounts=allidx.groupby('id',observed=True).size()
    summary=dict(total_preApril_rows=len(allidx),unique_full_id=allidx.id.nunique(),full_id_with_multiple_records=int((fullcounts>1).sum()),full_id_duplicate_rows=int(dup_id.sum()),
      numeric_job_id_with_multiple_records=int((counts>1).sum()),numeric_job_id_duplicate_rows=int(dup_num.sum()),
      candidate_ids_only_are_not_revision_history=True,before_any_deduplication=True)
    write('DUPLICATE_INDEX_SUMMARY.json',summary)
    candidates[['id','job_id','array_pos','submit_time','source_member','source_row','request_fingerprint']].to_parquet(ROOT/'DUPLICATE_IDENTITY_CANDIDATES.parquet',index=False)
    if state_rows:
        pd.concat(state_rows,ignore_index=True).to_parquet(ROOT/'REQUEUE_TERMINAL_STATE_ROWS.parquet',index=False)
    else:pd.DataFrame(columns=FIELDS+['source_member','source_row']).to_parquet(ROOT/'REQUEUE_TERMINAL_STATE_ROWS.parquet',index=False)
    del allidx,counts,fullcounts;gc.collect()
    g=pd.concat(gpu,ignore_index=True);g.to_parquet(LOCAL/'GPU_PREAPRIL.parquet',index=False)
    write('RAW_SCHEMA_AUDIT.json',dict(partitions=schemas,actual_union_fields=sorted(set(x['name'] for s in schemas for x in s['fields'])),
      documented_state_missing_correction='state/state_simple DO exist in raw archive. vNext6 loaded a restricted feature/label projection; absence there was not archive absence.',
      version_fields_present=[c for c in sorted(set(x['name'] for s in schemas for x in s['fields'])) if re.search('revision|update|effective|restart|requeue|ingest|original|sluid',c,re.I)]))
    write('PREPARATION_RECEIPT.json',dict(source=record(RAW),partitions=parts,total_rows=total,gpu_rows=len(g),null_counts=dict(nulls),mature_terminal_states=dict(states),
      all_rows_deduplicated=False,April_payload_opened=False,May_payload_opened=False,models_trained=0,gpu_local_data=record(LOCAL/'GPU_PREAPRIL.parquet'),
      note='Archive request descriptors inspected as provenance data, not promoted. Terminal state/requeue statistics limited to end-before-April records; missing end records cannot certify no requeue.'))
    print('PREPARATION',summary,'GPU',len(g),flush=True)
if __name__=='__main__':main()
