"""Actual native columns and bounded original Kestrel projection, before any model fit."""
from common16 import *
import pyarrow.parquet as pq
import re,zipfile,gc
IDENTITY=['user','account','partition','qos','job_type','name','script','submit_line']
STACK=['modules','conda_envs']
RESOURCE=['nodes_req','processors_req','memory_req_raw','wallclock_req_sec']
FORBIDDEN=['start_time','end_time','wallclock_used_sec','avg_power_per_node','job_id']

def audit_native():
    f=pq.ParquetFile(HIST);schema=f.schema_arrow;bounds=[]
    for j in range(f.num_row_groups):
        group=f.metadata.row_group(j)
        for k in range(group.num_columns):
            c=group.column(k)
            if c.path_in_schema in ['submit_time','start_time','end_time']:
                assert c.statistics.has_min_max and c.statistics.max<pd.Timestamp('2025-04-01',tz='UTC')
                bounds.append(dict(group=j,field=c.path_in_schema,min=str(c.statistics.min),max=str(c.statistics.max)))
    t=f.read(columns=['submit_time','start_time','end_time','wallclock_used_sec','job_id']).to_pandas()
    valid=(t.end_time>=t.start_time)&(t.start_time>=t.submit_time)&np.isfinite(t.wallclock_used_sec)&t.wallclock_used_sec.ge(0)
    folds=[];roles=[]
    for cfg in read(ROOT/'AUDIT_PROTOCOL.json')['native_folds']:
        a=pd.Timestamp(cfg['valid_from'],tz='UTC');b=pd.Timestamp(cfg['valid_to'],tz='UTC')
        tr=valid&t.submit_time.lt(a)&t.end_time.lt(a)
        va=valid&t.submit_time.ge(a)&t.submit_time.lt(b)
        np.savez_compressed(LOCAL/f'native_fold{cfg["fold"]}_roles.npz',TRAIN=np.flatnonzero(tr),VALID=np.flatnonzero(va))
        folds.append(dict(**cfg,TRAIN_N=int(tr.sum()),VALID_N=int(va.sum()),TRAIN_ids=ids(t.loc[tr,'job_id']),VALID_ids=ids(t.loc[va,'job_id'])))
        roles.append((cfg['fold'],tr,va))
    rows=[];authority=[];data=t.copy()
    for c in schema.names:
        s=t[c] if c in t else f.read(columns=[c]).column(0).to_pandas()
        islist=c in STACK
        values=s.map(lambda x:'|'.join(sorted(set(x))) if x is not None else None) if islist else s
        present=s.notna()
        if islist:present=values.notna()&values.ne('')
        counts=values[present].value_counts(dropna=True)
        categorical=c in IDENTITY+STACK
        if c in STACK:
            token=pd.Series([v for a in s if a is not None for v in a],dtype='string')
            opaque=float(token.str.fullmatch(r'(module|condaenv)_?\d+').mean()) if len(token) else None
            tokens=dict(nonempty_rows=int(present.sum()),token_cardinality=int(token.nunique()),tokens=int(len(token)))
        else:
            opaque=float(values[present].astype(str).str.fullmatch(r'(user|name|script|job_type|account|submit_line)_\d+').mean()) if categorical and present.any() else None
            tokens={}
        meaning='ANONYMIZED_SOFTWARE_STACK_IDENTITIES' if islist else 'STABLE_ANON_IDENTITY' if opaque is not None and opaque>.95 else 'STRUCTURED_CATEGORY' if categorical else 'NUMERIC_OR_TIMESTAMP'
        klass='FORBIDDEN_OUTCOME_OR_FUTURE' if c in FORBIDDEN else 'DEPLOYABLE_SUBMISSION_TIME' if c=='submit_time' else 'HISTORICAL_DIAGNOSTIC_ONLY'
        reason=('Target/outcome/positional row identifier; allowed only as labels, maturity checks or audit linkage, never predictor' if c in FORBIDDEN else
                'Submission event time itself is observable; exported fixed-offset lineage is still only a storage fact' if c=='submit_time' else
                'Candidate submission concept, but exact anonymization/capture time or initial mutable request version is not certified for this export')
        authority.append(dict(source='RADDiT historic',field=c,information_class=klass,meaning=meaning,available_as_submission_concept=c not in FORBIDDEN,
            archived_initial_version_proven=c=='submit_time',same_value_future_V42_reproducible=c=='submit_time',predictor_scope='NATIVE_DIAGNOSTIC_ONLY' if c not in FORBIDDEN else 'NEVER',reason=reason))
        for i,tr,va in roles:
            unseen=float((~values[va].isin(set(values[tr].dropna()))).mean()) if categorical else None
            rows.append(dict(field=c,dtype=str(schema.field(c).type),N=len(s),non_null_fraction=float(s.notna().mean()),nonempty_fraction=float(present.mean()),
                cardinality=int(len(counts)),recurring_row_fraction=float(counts[counts>1].sum()/present.sum()) if present.sum() else None,
                first_submit=str(t.loc[present,'submit_time'].min()),last_submit=str(t.loc[present,'submit_time'].max()),
                fold=i,TRAIN_nonempty=float(present[tr].mean()),VALID_nonempty=float(present[va].mean()),VALID_unseen_rate=unseen,
                representation=meaning,opaque_token_fraction=opaque,**tokens))
        if c not in data:data[c]=values
        print('FIELD_AUDITED',c,len(counts),flush=True)
        del s,values,counts;gc.collect()
    data.to_parquet(LOCAL/'NATIVE_TABLE.parquet',index=False)
    pd.DataFrame(rows).to_csv(ROOT/'RADDIT_FULL_SCHEMA_AUDIT.csv',index=False)
    pd.DataFrame(authority).to_csv(ROOT/'RADDIT_FIELD_AUTHORITY_AUDIT.csv',index=False)
    write('NATIVE_FOLD_CONTRACT.json',dict(time=now(),folds=folds,rows=len(t),excluded_invalid_rows=int((~valid).sum()),
        retained_ids=ids(t.loc[valid,'job_id']),source=rec(HIST),footer_date_bounds=bounds,April_payload=False,May_payload=False,
        population='All RADDiT historic jobs; not a GPU-only population. No unprovided GPU quantity is imputed.',
        runtime_unit='seconds',reservation_unit='node-hours using nodes_req; also unweighted seconds ratio. Not falsely reported as GPU-hours.'))
    md('RADDIT_INFORMATION_CLASSIFICATION.md','''# Information authority

Each source-field pair has exactly one A/B/C class in RADDIT_FIELD_AUTHORITY_AUDIT.csv. A is observable and reproducible at future submission; B is a historical diagnostic upper bound with unproven original version/capture/anonymization; C never enters predictor matrices. C timestamps and outcomes may be used as labels, completion eligibility and forensic linkage only. job_id is a positional audit key, not an identity predictor.

All native rich metadata is B until a separate source-backed bridge is established. Conceptual future capture does not prove that archived final request/account/QoS snapshots were original submission values. A native gain does not establish a deployable gain or causal application semantics. modules/conda are set-valued anonymized software-stack identities, not missing Kestrel fields to impute.
''')
    md('RADDIT_ANONYMIZATION_SEMANTICS_AUDIT.md','''# Anonymous categories

Actual source columns are inspected, not inferred from names. user/name/script/account/job_type/submit_line and module/conda tokens contain opaque identifiers. Equality and recurrence are usable; numeric suffix magnitude, edit distance, character ngrams and linguistic embeddings are prohibited. Module/conda set membership is workflow-stack identity information, but actual software names, versions and semantics are not recoverable from these tokens. No real source text is claimed.

Time boundaries use stored timezone-aware epochs for the native experiment; T0 displayed wallclock is restricted to explicitly labelled crosswalk diagnostics. Upstream timestamp/export provenance remains unresolved.
''')

def raw_projection():
    parts=[];receipts=[]
    cols=['id','job_id','submit_time','start_time','end_time','nodes_req','processors_req','wallclock_used','wallclock_req','memory_req','gpus_requested',
          'user_hash','account_hash','partition','qos','job_type_hash','name_hash','submit_line_hash','submit_script_hash','work_dir_hash','array_pos','array_range']
    with zipfile.ZipFile(ARCHIVE) as z:
        for name in sorted(z.namelist()):
            m=re.search(r'year=(\d+)/month=(\d+)/',name)
            if not m or not name.endswith('.parquet') or tuple(map(int,m.groups()))>=(2025,4):continue
            with z.open(name) as stream:
                f=pq.ParquetFile(stream);present=[c for c in cols if c in f.schema_arrow.names]
                d=f.read(columns=present).to_pandas()
                source_rows=len(d)
                # Monthly files use local dates: March can contain UTC April boundary rows.
                # Discard those rows before features, linkage, or any metrics are computed.
                outside=d.submit_time.ge(pd.Timestamp('2025-04-01',tz='UTC'))
                boundary_rows=int(outside.sum())
                d=d.loc[~outside].copy()
                # Only declared linkage metadata and submission candidates are projected.
                # Missing historical outcomes remain missing and never produce a match.
                for c in ['submit_time','start_time','end_time']:
                    d[c+'_utc_us']=d[c].dt.tz_convert('UTC').astype('datetime64[us, UTC]').astype('int64')
                    # Original submit is stored UTC; local comparison is fixed -06:00, explicitly a proxy.
                    d[c+'_display_us']=d[c].dt.tz_convert('Etc/GMT+6').dt.tz_localize(None).astype('datetime64[us]').astype('int64')
                d['wallclock_used_sec']=d.wallclock_used.dt.total_seconds();d['wallclock_req_sec']=d.wallclock_req.dt.total_seconds()
                d=d.drop(columns=['wallclock_used','wallclock_req','start_time','end_time'])
                parts.append(d);receipts.append(dict(member=name,N=len(d),source_rows=source_rows,UTC_April_boundary_rows_excluded=boundary_rows,columns=present,modules_present='modules' in f.schema_arrow.names,conda_present='conda_envs' in f.schema_arrow.names))
            print('KESTREL_PROJECTED',name,len(d),flush=True)
    raw=pd.concat(parts,ignore_index=True)
    raw.to_parquet(LOCAL/'KESTREL_RICH_PROJECTION.parquet',index=False)
    write('KESTREL_SOURCE_REAUDIT.json',dict(time=now(),rows=len(raw),members=receipts,output=rec(LOCAL/'KESTREL_RICH_PROJECTION.parquet'),
        April_members_opened=False,May_members_opened=False,unused_outcome_columns_read=False,
        linkage_outcomes='start/end/runtime projected for exact mapping only; excluded from all predictors'))

if __name__=='__main__':
    {'native':audit_native,'kestrel':raw_projection}[sys.argv[1]]()
