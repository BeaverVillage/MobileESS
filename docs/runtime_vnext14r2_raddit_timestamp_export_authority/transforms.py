from common import *
import sys,importlib.util
import pyarrow.parquet as pq
spec=importlib.util.spec_from_file_location('frozen_r1_exact',R1/'embedding_audit.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
COLS=mod.COLS;KEYS=[['submit_time','end_time'],['submit_time','end_time','wallclock_used_sec'],['submit_time','end_time','wallclock_used_sec','avg_power_per_node']]
def digest_frame(d):return hashlib.sha256(pd.util.hash_pandas_object(d,index=False).to_numpy().tobytes()).hexdigest()
def run(replay=False):
    h=pd.read_parquet(R1/'.local/HISTORIC_SHARED_METADATA.parquet');e=pd.read_parquet(R1/'.local/EMBEDDING_SHARED_METADATA.parquet')
    original_digest=digest_frame(e);chunks=sorted(e.embedding_chunk.unique());rng=np.random.default_rng(1402);shuffled=list(rng.permutation(chunks))
    pieces={int(c):e[e.embedding_chunk.eq(c)] for c in shuffled}
    ordered=pd.concat([pieces[c] for c in sorted(pieces)],ignore_index=True)
    assert digest_frame(ordered)==original_digest
    e=ordered if replay else e
    transformations={t:hashlib.sha256(np.ascontiguousarray(h[[c+('_utc' if t=='T1' else '') for c in COLS[:3]]].to_numpy()).tobytes()).hexdigest() for t in ['T0','T1']}
    base=read(R1/'EMBEDDING_EXACT_AUDIT_DETAIL.json');rows=[];digests=[]
    for i,s in enumerate(base['stats']):rows.append(dict(transformation='T0',**s,ordering='REORDERED_RAW_CANDIDATES; R1 order audit',approved=False,source_authority='UNRESOLVED',measurement='REUSED_HASH_VERIFIED_R1'))
    hu=h.copy()
    for c in COLS[:3]:hu[c]=h[c+'_utc']
    for i,keys in enumerate(KEYS):
        s,ledger,hold=mod.exact_audit(hu,e,keys);ledger=ledger.sort_values('embedding_global_row').reset_index(drop=True)
        dg=digest_frame(ledger);digests.append(dg)
        idx=ledger.loc[ledger.holdout_consistent.eq(True),'historic_row'].to_numpy(dtype=np.int64)
        ordering=dict(consistent_rows=len(idx),adjacent_inversions=int((np.diff(idx)<0).sum()),monotonic=bool((np.diff(idx)>0).all()) if len(idx)>1 else None)
        rows.append(dict(transformation='T1',key='EKEY'+str(i),**s,ordering=str(ordering),approved=False,source_authority='UNRESOLVED',measurement='NEW_AUTHORIZED_DIAGNOSTIC'))
        if not replay:
            ledger.to_parquet(LOCAL/f'T1_EKEY{i}_DIAGNOSTIC_LEDGER.parquet',index=False)
            write(f'T1_EKEY{i}_DETAIL.json',dict(stats=s,holdouts=hold,ordering=ordering,ledger_content_sha256=dg))
        print('T1',i,json.dumps(clean(s)),flush=True)
    # Reconstruct the strongest T0 mapping once in the fresh/shuffled process, not another raw scan.
    t0replay=None
    if replay:
        s,ledger,_=mod.exact_audit(h,e,KEYS[2]);t0replay=digest_frame(ledger.sort_values('embedding_global_row').reset_index(drop=True))
        assert t0replay==base['ledger_digests'][2]
        previous=read(ROOT/'TRANSFORM_RUN_RECEIPT.json')
        assert transformations==previous['timestamp_digests'] and digests==previous['T1_mapping_digests']
        write('TRANSFORM_REPLAY_RECEIPT.json',dict(TIMESTAMP_TRANSFORM_REPLAY_IDENTICAL=True,MAPPING_REPLAY_IDENTICAL=True,scope='Diagnostic T0/T1 only; no authority approval',fresh_process=True,shuffle_seed=1402,shuffled_chunk_order=[int(x) for x in shuffled],canonical_sort_restores_metadata=True,metadata_digest=original_digest,T0_EKEY2_mapping_digest=t0replay,T1_mapping_digests=digests,timestamp_digests=transformations))
    else:
        table('TIMESTAMP_TRANSFORMATION_TESTS.csv',rows)
        write('TRANSFORM_RUN_RECEIPT.json',dict(timestamp_digests=transformations,T1_mapping_digests=digests,continuous_input_shuffle_sort_identical=True,metadata_digest=original_digest))
        footer_rows=[]
        for p in sorted((RAD/'data/encrypted_embeddings').glob('*.parquet')):
            pf=pq.ParquetFile(p)
            for c in ['submit_time','end_time']:
                idx=pf.schema.names.index(c);col=pf.schema.column(idx);field=pf.schema_arrow.field(c)
                stats=[pf.metadata.row_group(g).column(idx).statistics for g in range(pf.metadata.num_row_groups)]
                footer_rows.append(dict(chunk=p.name,field=c,physical_type=col.physical_type,logical_type=str(col.logical_type),arrow_type=str(field.type),timezone=field.type.tz,precision=field.type.unit,timezone_metadata_present=field.type.tz is not None,minimum=min(str(s.min) for s in stats if s and s.has_min_max),maximum=max(str(s.max) for s in stats if s and s.has_min_max),created_by=pf.metadata.created_by,rows=pf.metadata.num_rows))
        table('EMBEDDING_TIMESTAMP_SCHEMA_AUDIT.csv',footer_rows)
        hp=pq.ParquetFile(RAD/'data/historic_job_trace.parquet')
        write('HISTORIC_TIMESTAMP_AUTHORITY.json',dict(stored_arrow_type=str(hp.schema_arrow.field('submit_time').type),stored_timezone=hp.schema_arrow.field('submit_time').type.tz,source_timezone_claim='No upstream acquisition/conversion claim proven for this historic export; Kestrel datacard cannot be transferred without lineage.',DST_handling_claim='Arrow column fixed -06:00, not an America/Denver timezone identifier. No upstream DST conversion code found.',absolute_instant_interpretation='Stored timezone-aware Arrow epoch has a defined UTC interpretation; upstream correctness and later timezone stripping provenance remain unproven.',evidence_source=[str(RAD/'data/historic_job_trace.parquet'),'V14R1 EMBEDDING_SCHEMA_AUDIT.json','R2 Git/notebook/LFS/public audit'],authority_status='STORAGE_METADATA_PROVEN_UPSTREAM_EXPORT_UNRESOLVED',stored_absolute_interpretation_proven=True,HISTORIC_TIMESTAMP_AUTHORITY_RESOLVED=False))
        # Deterministic sparse DST examples from existing exact raw candidates. No nearest-time linkage.
        ledger=pd.read_parquet(R1/'.local/EKEY2_NEGATIVE_FORENSIC_LEDGER.parquet');u=ledger[ledger.holdout_consistent.eq(True)]
        ep=e.iloc[u.embedding_global_row.to_numpy()];dates=pd.to_datetime(ep.submit_time,unit='us').dt.strftime('%Y-%m-%d').to_numpy();dst=[]
        for event in read(ROOT/'PREREGISTRATION.json')['DST_dates']:
            for day in pd.date_range(pd.Timestamp(event)-pd.Timedelta(days=2),pd.Timestamp(event)+pd.Timedelta(days=2)):
                sel=np.flatnonzero(dates==day.strftime('%Y-%m-%d'))
                if not len(sel):dst.append(dict(date=str(day.date()),historic_timestamp=None,historic_offset=None,historic_utc=None,embedding_naive=None,matches_local_wall_clock=None,matches_utc_wall_clock=None,notes='NO_UNIQUE_RAW_CANDIDATE_ON_DATE'));continue
                for pos in sorted(set([int(sel[0]),int(sel[-1])])):
                    er=int(u.iloc[pos].embedding_global_row);hr=int(u.iloc[pos].historic_row);ht=h.iloc[hr];et=e.iloc[er]
                    local=pd.Timestamp(ht.submit_time,unit='us');utc=pd.Timestamp(ht.submit_time_utc,unit='us');naive=pd.Timestamp(et.submit_time,unit='us')
                    dst.append(dict(date=str(day.date()),historic_timestamp=local.isoformat()+'-06:00',historic_offset='-06:00',historic_utc=utc.isoformat()+'Z',embedding_naive=naive.isoformat(),matches_local_wall_clock=local==naive,matches_utc_wall_clock=utc==naive,notes=f'DST event {event}; existing exact raw candidate E={er}, H={hr}; diagnostic only, no offset fitted'))
        table('DST_TIMESTAMP_DIAGNOSTIC.csv',dst)
if __name__=='__main__':run('--replay' in sys.argv)
