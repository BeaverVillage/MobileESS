"""Project only original pre-April Kestrel submission-side fields; no outcome read."""
from common15 import *
import io,re,zipfile
from collections import Counter
import pyarrow.parquet as pq
FIELDS=dict(user='user_hash',account='account_hash',partition='partition',qos='qos',
            job_type='job_type_hash',name='name_hash',submit_line='submit_line_hash',
            script='submit_script_hash',modules='modules',conda_envs='conda_envs',
            workdir='work_dir_hash',reservation='reservation',array_pos='array_pos',
            array_range='array_range',dependency='dependency')
def main():
    assert (ROOT/'BASE_PRESERVATION_RECEIPT.json').exists()
    counters={f:Counter() for f in FIELDS};total=0;missing=Counter();members=[];parts=[];schemas={}
    with zipfile.ZipFile(ARCHIVE) as z:
        for n in sorted(z.namelist()):
            match=re.search(r'year=(\d+)/month=(\d+)/',n)
            if not match or (int(match[1]),int(match[2]))>=(2025,4) or not n.endswith('.parquet'):continue
            pf=pq.ParquetFile(io.BytesIO(z.read(n)))
            wanted=['id','job_id','submit_time','gpus_requested']+list(FIELDS.values())
            cols=[c for c in wanted if c in pf.schema_arrow.names]
            d=pf.read(columns=cols).to_pandas()
            d['submit_time']=pd.to_datetime(d.submit_time,utc=True)
            d=d[d.submit_time.lt(pd.Timestamp('2025-04-01',tz='UTC'))]
            total+=len(d)
            for f,c in FIELDS.items():
                if c not in d:missing[f]+=len(d);continue
                values=d[c].astype('string');valid=values.notna()&values.str.strip().ne('')
                missing[f]+=int((~valid).sum());counters[f].update(values[valid].value_counts().to_dict())
            gpu=d[d.gpus_requested.fillna(0).gt(0)].copy()
            gpu['source_member']=n;parts.append(gpu)
            members.append(dict(member=n,rows=len(d),gpu_rows=len(gpu),projected_columns=cols))
            schemas[n]=str(pf.schema_arrow)
            print('PROJECTED',n,len(d),len(gpu),flush=True)
    g=pd.concat(parts,ignore_index=True)
    assert g.id.is_unique and len(g)==621583
    old=pd.read_parquet(REPO/'docs/runtime_vnext7_feature_authority_recovery/.local/GPU_PREAPRIL.parquet')
    check=['id','job_id','submit_time','gpus_requested']+list(set(FIELDS.values())&set(old.columns)&set(g.columns))
    a=g.set_index('id').sort_index();b=old.set_index('id').sort_index()
    pd.testing.assert_frame_equal(a[[c for c in check if c!='id']],b[[c for c in check if c!='id']],check_dtype=False)
    g.to_parquet(LOCAL/'GPU_SUBMISSION_METADATA.parquet',index=False)
    rows=[]
    for f,c in FIELDS.items():
        counts=counters[f];nn=sum(counts.values());opaque=sum(v for k,v in counts.items() if re.fullmatch(r'[0-9a-fA-F]{7}',str(k)))
        classification=('MISSING' if not nn else 'STABLE_ANON_IDENTITY' if c.endswith('_hash') and opaque/nn>.95
                        else 'STRUCTURED_SEMANTIC' if f in ['partition','qos','array_pos','array_range'] else 'OPAQUE_UNSTABLE_TOKEN')
        # Immutable identity / original invocation are distinguished from updatable job attributes.
        allowed=f in ['user','submit_line'] and nn>0
        mutable=f in ['account','partition','qos','name','reservation','dependency']
        for i in range(1,6):
            tr=pd.read_parquet(V9/'.local'/f'fold{i}/TRAIN.parquet',columns=['job_id'])
            va=pd.read_parquet(V9/'.local'/f'fold{i}/VALID.parquet',columns=['job_id'])
            if c in a:
                tv=a.loc[tr.job_id,c].astype('string');vv=a.loc[va.job_id,c].astype('string')
                known=set(tv.dropna());observed=vv.notna()
                unseen=float((~vv[observed].isin(known)).mean()) if observed.any() else None
                card=int(tv.nunique())
            else:unseen=None;card=0
            rows.append(dict(field=f,source_column=c,classification=classification,scope='ALL_ORIGINAL_PREAPRIL; fold unseen on fixed GPU roles',
                population_N=total,missing_rate=missing[f]/total,unique_count=len(counts),
                repetition_rate=1-len(counts)/nn if nn else None,opaque_7hex_fraction=opaque/nn if nn else None,
                fold=i,TRAIN_unique=card,VALID_unseen_rate_nonmissing=unseen,
                observation_time='SUBMIT_CONCEPT; archive collection/ingestion timestamp not supplied',
                known_at_submit=allowed,mutable_after_submit=mutable if nn else None,
                archive_original_version_certified=False,allowed_for_historical_semantics=allowed,
                future_v42_support='ACCEPTED_SUBMISSION_RECEIPT_REQUIRED',
                exclusion_reason='' if allowed else 'MISSING_OR_MUTABLE_VERSION_OR_DERIVATION_TIMING_UNPROVEN',
                interpretation='Stable anonymized identity only; truncated hash collisions possible, no linguistic or numeric-ID semantics' if classification=='STABLE_ANON_IDENTITY' else classification))
    pd.DataFrame(rows).to_csv(ROOT/'KESTREL_SUBMISSION_SEMANTIC_FIELD_AUDIT.csv',index=False)
    datacard=ARCHIVE.parent/'datacard.md'
    write('KESTREL_ORIGINAL_PROJECTION_RECEIPT.json',dict(time=now(),members=members,rows=total,gpu_rows=len(g),
        old_GPU_projection_exact=True,schemas=schemas,output=rec(LOCAL/'GPU_SUBMISSION_METADATA.parquet'),
        archive=rec(ARCHIVE),datacard=rec(datacard),April_members_opened=False,May_members_opened=False,outcome_columns_read=False))
    write('SUBMISSION_SEMANTIC_AUTHORITY.json',dict(time=now(),allowed_historical_fields=['user','submit_line'],
        source=rec(datacard),basis='Datacard User=identity of submitting user and SubmitLine=original submission command; field-level immutable submission concepts, not later mutable job settings.',
        excluded_mutable=['account','partition','qos','name','reservation','dependency'],
        excluded_derivation_or_capture_unproven=['job_type','script','modules','conda_envs','workdir','array_pos','array_range'],
        collection='Periodic sacct snapshot, no ingestion time or field revision log. Event-time research replay is not attestation of historical ingestion latency.',
        existing_R0_features='Exact frozen V13 trace-proxy baseline retained, not recertified by semantic audit.',
        future='Future real input requires accepted-submit immutable payload receipt and same identity namespace; no attempt to recover source hash algorithm. Unknown namespaces cannot pretend to match archive IDs.',
        field_mutation_sources=['https://slurm.schedmd.com/scontrol.html','https://slurm.schedmd.com/sacct.html'],
        raw_string_storage=False,PRIVATE_RADDIT_EXPORT_REQUIRED=False))
    print('FIELD AUDIT COMPLETE',total,len(g),flush=True)
if __name__=='__main__':main()
