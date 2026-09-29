"""Close source audits after the mandatory identity stop; never fit or extend joins."""
from common14 import *
import pyarrow.parquet as pq
import re,collections

STOP='NOT_RUN_SOURCE_AUTHORITY_FAILURE'


def main():
    assert read(ROOT/'STOP_CONDITION_RECEIPT.json')['status']=='STOPPED_SOURCE_AUTHORITY_FAILURE'
    inv=pd.read_csv(ROOT/'RAW_SOURCE_INVENTORY.csv',keep_default_na=False)
    meta=read(ROOT/'RAW_SCHEMA_METADATA.json');byid={r['source_id']:r for r in meta['schemas']}
    selected=[];evidence=[]
    raddit=RAW_B/'RADDiT';scripts=raddit/'energy_aware_scheduling/scripts'
    for name in ['prep_for_embedding.py','embed_job_scripts.py','quickstart_embedding.py','semantic_search.py']:
        p=scripts/name;selected.append(record(p))
        text=p.read_text(encoding='utf-8');evidence.append(dict(path=str(p),lines=len(text.splitlines()),sha256=sha(p)))
    prep=(scripts/'prep_for_embedding.py').read_text(encoding='utf-8')
    render=prep.split('def prep_string_for_llm(row):',1)[1].split('return s',1)[0]
    actual_inputs=['user','account','partition','job_type','name','qos','submit_line','script']
    outcome_inputs=[s for s in ['wallclock_used_sec','end_time','start_time','avg_power_per_node','consumed_energy','state'] if s in render]
    assert not outcome_inputs
    chunk_rows=[];offset=0;lfscopies=[]
    for p in sorted((raddit/'data/encrypted_embeddings').glob('chunk_*.parquet')):
        pf=pq.ParquetFile(p);n=pf.metadata.num_rows
        # Hash included forensic inputs after inventory; do not decode vectors or outcomes.
        rec=record(p);selected.append(rec)
        pointer=RAW_B/'NLR_scheduler_authority/02_RADDiT/data/encrypted_embeddings'/p.name
        text=pointer.read_text(encoding='utf-8')
        oid=re.search(r'oid sha256:([0-9a-f]+)',text).group(1)
        assert rec['sha256']==oid
        lfscopies.append(dict(payload=rec,pointer=record(pointer),LFS_oid_matches=True))
        chunk_rows.append(dict(chunk=p.name,rows=n,global_offset_start=offset,global_offset_end_exclusive=offset+n,
                               footer_only=True,record_alignment_executed=False))
        offset+=n
    hist=read(ROOT/'RADDIT_KESTREL_JOIN_SUMMARY.json')['RADDiT_historic_jobs']
    write('RADDIT_EMBEDDING_ALIGNMENT_AUDIT.json',dict(time=now(),status=STOP,
        reason='Mandatory upstream physical-job identity stop. Chunk footer counts and source code audited; shared-field row alignment was not authorized after stop.',
        total_embedding_rows=offset,historic_trace_rows=hist,row_count_difference=hist-offset,
        chunk_count=len(chunk_rows),chunks=chunk_rows,global_chunk_order='lexicographic, as implemented by semantic_search.py',
        row_id_authority='semantic_search.py creates cumulative chunk row_id; this is not historic_job_trace.job_id authority.',
        chunk_generation_or_export_crosswalk_found=False,
        shared_fields=['submit_time','start_time','end_time','wallclock_used_sec','avg_power_per_node'],
        shared_field_exact_consistency_status=STOP,shared_field_exact_consistency=None,
        boundary_preflight_submit_only_chunks=['chunk_000.parquet','chunk_020.parquet','chunk_044.parquet'],
        boundary_preflight_scope='Only submit_time projection was inspected before identity stop; no embedding vectors or shared outcomes were decoded.',
        historic_timezone='explicit -06:00',embedding_timezone='naive timestamp[us]; conversion authority not established',
        RADDIT_EMBEDDING_ROW_MAPPING_PROVEN=False,RADDIT_EMBEDDING_JOB_JOIN_RATE=0.0,
        join_rate_scope='Authorized V13 job-to-semantic rows: zero because upstream physical-job mapping failed; not a measured historic-to-embedding tuple match rate.',
        RADDIT_EMBEDDING_AMBIGUOUS_ROWS=None,RADDIT_EMBEDDING_MISSING_ROWS=None,
        null_count_reason='Not measured after mandatory stop; no zero/estimated counts substituted.',
        vectors_decoded=False,source_code=evidence))
    write('RADDIT_EMBEDDING_PROVENANCE_AUDIT.json',dict(time=now(),
        RADDIT_EMBEDDING_OUTCOME_INPUT_FOUND=bool(outcome_inputs),inspected_render_inputs=actual_inputs,
        scope='Published prep_string_for_llm and quickstart render_job functions; not a cryptographic attestation of undisclosed chunk export.',
        published_construction_outcome_free=True,distributed_chunk_generation_fully_attested=False,
        original_vector='Linq-Embed-Mistral 4096-dimensional last-token pooled, L2-normalized in public code',
        distributed_vector='enc_embedding_int8; export/encryption transformation authority not located in inspected public scripts',
        provenance_mode='RADDIT_SEMANTIC_PROXY_CANDIDATE_NOT_AUTHORIZED',
        RADDIT_NEW_JOB_SEMANTIC_CALLABLE=False,
        reason='V42 input has no demonstrated path to original script/semantic metadata or identical distributed encrypted coordinate space; historical lookup is insufficient.',
        code=evidence,LFS_payload_identity_verified=lfscopies))
    (ROOT/'RADDIT_EMBEDDING_PROVENANCE_AUDIT.md').write_text(
        '# RADDiT embedding provenance\n\n'
        '공개 prep_for_embedding.py와 quickstart_embedding.py의 입력은 user/account/partition/job_type/name/qos/submit_line/script입니다. '
        '이 함수들에는 actual runtime, START/END, final state, power/energy 결과가 없습니다. '
        'RADDIT_EMBEDDING_OUTCOME_INPUT_FOUND=FALSE는 이 공개 입력 구성 코드의 검사 범위입니다. '
        'semantic_search.py가 runtime/power/END를 검색 DB의 별도 필드로 넣는 것은 현재 작업 embedding 입력에 넣는 것과 다릅니다.\n\n'
        '공개 생성 코드는 4096차원 last-token pooling과 L2 정규화를 사용합니다. 배포 파일은 enc_embedding_int8이며 '
        '40000행 단위 45개 chunk입니다. 공개 전처리는 4096행 단위 원본 순서를 사용하지만, '
        '배포 chunk의 필터·암호화·재정렬 과정과 historic job ID crosswalk는 확인하지 못했습니다. '
        'semantic_search.py의 row_id는 chunk를 합칠 때 새로 부여한 번호입니다. 원본 job identity 증명이 아닙니다.\n\n'
        '역사적 ingestion 시점은 입증되지 않아 submission-time semantic proxy 후보로만 설명합니다. '
        '실제 물리 작업 대응이 실패하여 SEM_SVD32와 k=10 semantic neighbor를 실행하지 않았습니다. '
        '기존 연구의 outcome-free 코드가 배포 암호화 벡터의 완전한 생성 이력을 증명하지는 않습니다.\n\n'
        '새 작업이 동일 입력/동일 암호화 좌표를 생성하는 V42 연결 경로는 확인되지 않았습니다. '
        'RADDIT_NEW_JOB_SEMANTIC_CALLABLE=FALSE, STRICT_CAUSAL_RUNTIME_PROVIDER_READY=FALSE입니다. '
        '원본 식별자 재식별이나 근사 시간 연결은 시도하지 않았습니다. 상세 코드 hash와 45개 LFS OID 일치는 JSON audit에 보존합니다.\n',encoding='utf-8')
    pue=RAW_B/'NLR ESIF PUE  IT Power/esif.influx.buildingData.PUE.combined.parquet'
    pf=pq.ParquetFile(pue);ts=pf.metadata.row_group(0).column(pf.schema_arrow.names.index('ts')).statistics
    write('FACILITY_STATE_AUTHORITY_AUDIT.json',dict(time=now(),status=STOP,FACILITY_STATE_JOIN_AUTHORIZED=False,
        facility_identity='ESIF data-center facility per local README; facility-wide IT power is not isolated Kestrel node telemetry.',
        same_facility_candidate=True,strict_Kestrel_specific_authority_proven=False,
        timestamp_timezone='Parquet ts is naive, isAdjustedToUTC=false; timezone and ingestion latency unverified',
        metadata_period_start=str(ts.min),metadata_period_end=str(ts.max),metadata_rows=pf.metadata.num_rows,
        nominal_calendar_overlap_with_five_folds=True,timezone_resolved_overlap_proven=False,
        sampling_interval_seconds=None,sampling_interval_status=STOP,contemporaneous_ingestion_authority='NOT_ESTABLISHED',
        backward_asof_join_executed=False,power_values_decoded=False,
        reason='Source-authority stop precedes feature construction; calendar overlap alone is insufficient.',
        source=record(pue),documentation=record(pue.parent/'README.md')))
    selected += [record(pue),record(pue.parent/'README.md')]
    genroot=RAW_B/'NLR_scheduler_authority/08_NLR_Kestrel_H100_GenAI_Power_Dataset312/dataset_v2'
    authority=RAW_B/'NLR_scheduler_authority/99_manifest/dataset312_h100_power/DATASET312_SOURCE_AUTHORITY.txt'
    gen=[r for r in meta['schemas'] if 'dataset_v2' in r['path'] and r['status']=='FOOTER_READ']
    write('GENAI_DATASET_JOINABILITY_AUDIT.json',dict(time=now(),status=STOP,GENAI_DIRECT_JOB_JOIN_AUTHORIZED=False,
        source_claim='NLR GenAI Dataset 312, Kestrel/H100 directory designation; no new per-job identity authority established',
        catalog_version_date='2026-04-10',catalog_date_is_not_measurement_period=True,measurement_period='UNESTABLISHED',
        workloads=['Llama2 training/fine-tuning','Stable Diffusion training','Llama3 offline/online inference'],
        inspected_aggregated_parquet_files=len(gen),aggregated_fields=sorted({f['name'] for r in gen for f in r['fields']}),
        authorized_Slurm_ID_found_in_aggregated_schema=False,absolute_timestamp_found_in_aggregated_schema=False,
        raw_record_content_inspected=False,exact_job_join_executed=False,
        reason='Relative timestep/power profiles are not an authorized historical job crosswalk. Publication in 2026 does not prove all observations were collected in 2026.',
        permissible_future_role='workload taxonomy/power-method context only; no Kestrel historical feature or runtime performance claim',
        documents=[record(genroot/'README.md'),record(authority)]))
    selected += [record(genroot/'README.md'),record(authority)]
    # Every discovered physical file gets one source classification and an explicit decision.
    decisions=[]
    identity=pd.read_parquet(LOCAL/'ORIGINAL_KESTREL_IDENTITY_PREAPRIL.parquet',columns=['submit_time'])
    original_times=pd.to_datetime(identity.submit_time,utc=True)
    original_period=(str(original_times.min()),str(original_times.max()))
    hbounds=read(ROOT/'RADDIT_KESTREL_JOIN_SUMMARY.json')['submit_row_group_boundaries']
    for ix,row in inv.iterrows():
        fam=row.dataset_family;schema=byid.get(row.source_id,{})
        names=[f['name'] for f in schema.get('fields',[])]
        if fam in ['KESTREL_JOBS','RADDIT']:
            category='A. SAME_KESTREL_JOB_LEVEL';system='Kestrel / published RADDiT Kestrel derivative'
            grain='job rows or accompanying source documentation'
        elif fam=='NLR_FACILITY':
            category='C. SAME_FACILITY_TIME_LEVEL';system='ESIF facility per README';grain='facility time series'
        elif fam=='EAGLE':category='E. OTHER_HPC_SYSTEM';system='Eagle';grain='job/node telemetry'
        elif fam in ['H100_B200_POWER','UNTANGLING_GPU_POWER','CORDOBA_POWER_QUALITY']:
            category='F. OTHER_DATACENTER_WORKLOAD';system='Other/unspecified datacenter testbed; no Kestrel identity authority';grain='benchmark/power trace'
        elif fam.startswith('NON_RUNTIME_') or fam=='WEATHER':
            category='G. GRID / TRAFFIC / WEATHER / NON_RUNTIME';system='grid/traffic/weather/geospatial';grain='non-runtime source'
        else:category='H. UNKNOWN_REQUIRES_FORENSIC';system='Unverified for direct historical Kestrel feature';grain='documentation or unverified data'
        inv.at[ix,'source_category']=category;inv.at[ix,'source_system']=system;inv.at[ix,'data_granularity']=grain
        reason=('Original Kestrel archive backs the unchanged V13 baseline; no new source feature authorized.' if fam=='KESTREL_JOBS' else
                'RADDiT physical-job crosswalk not proven; row-index IDs cannot substitute for Slurm identities.' if fam=='RADDIT' else
                'Different system or non-runtime source; cannot fill Kestrel features.' if category.startswith(('E.','F.','G.')) else
                'NOT_RUN_SOURCE_AUTHORITY_FAILURE; metadata alone is insufficient for inclusion.')
        period=(original_period if fam=='KESTREL_JOBS' and row.filename.endswith('.zip') else
                (hbounds[0]['submit_min'],hbounds[-1]['submit_max']) if row.filename=='historic_job_trace.parquet' else
                (str(ts.min),str(ts.max)) if 'PUE.combined' in row.filename and row.filename.endswith('.parquet') else
                ('UNASSESSED_OR_NOT_APPLICABLE','UNASSESSED_OR_NOT_APPLICABLE'))
        decisions.append(dict(source_id=row.source_id,system_identity=system,period_start=period[0],period_end=period[1],
            job_level_join_possible='SOURCE_IDENTITY_ONLY' if fam=='KESTREL_JOBS' else 'NOT_PROVEN',
            time_level_join_possible='CALENDAR_OVERLAP_TIMEZONE_UNRESOLVED' if fam=='NLR_FACILITY' else 'NOT_AUTHORIZED',
            prediction_time_observable_candidate=fam in ['KESTREL_JOBS','RADDIT','NLR_FACILITY'],
            outcome_risk='Outcome columns must not enter current-job predictors' if any(n in names for n in ['wallclock_used_sec','avg_power_per_node','end_time']) else 'NOT_AUTHORIZED_OR_UNASSESSED',
            direct_runtime_feature_candidate=fam in ['KESTREL_JOBS','RADDIT','NLR_FACILITY'],
            external_validation_candidate=fam in ['EAGLE','H100_B200_POWER','GENAI_POWER','UNTANGLING_GPU_POWER'],
            include_in_v14_ml=False,reason=reason))
    # Mark actual row inspection on exactly the permitted sources read during forensic.
    inspected=[str(RAW_B/'RADDiT/data/historic_job_trace.parquet'),str(RAW_B/'NLR Kestrel Jobs/esif.hpc.kestrel.job-anon.zip')]
    for ix,row in inv.iterrows():
        if str(RAW_A/row.relative_path) in inspected:
            inv.at[ix,'record_content_inspected']=True
            inv.at[ix,'notes']='Only pre-April projection inspected; original archive only id/job_id/submit_time; historic trace all submissions and ends verified pre-April.'
        if row.relative_path.startswith('데이터 센터/RADDiT/data/encrypted_embeddings/') and row.filename in ['chunk_000.parquet','chunk_020.parquet','chunk_044.parquet']:
            inv.at[ix,'record_content_inspected']=True
            inv.at[ix,'notes']='Pre-stop submit_time-only boundary projection inspected. No vectors or shared runtime/power outcomes decoded; alignment NOT_RUN after stop.'
    inv.to_csv(ROOT/'RAW_SOURCE_INVENTORY.csv',index=False)
    pd.DataFrame(decisions).to_csv(ROOT/'RAW_SOURCE_DECISION_MATRIX.csv',index=False)
    # Preserve duplicate evidence without treating byte-identical copies as extra information.
    groups=pd.read_csv(ROOT/'RAW_SOURCE_GROUPS.csv',keep_default_na=False)
    extras=[]
    for group,part in inv[inv.filename.str.contains(r'PUE\.combined.*parquet|outside\.combined.*parquet|historic_job_trace\.parquet|datacard.*\.md',regex=True)].groupby('size_bytes'):
        if len(part)<2:continue
        byhash=collections.defaultdict(list)
        for _,r in part.iterrows():
            p=RAW_A/r.relative_path;digest=sha(p);byhash[digest].append(r)
        for digest,items in byhash.items():
            if len(items)>1:
                for r in items:extras.append(dict(group_id='SHA_'+digest,source_id=r.source_id,dataset_family=r.dataset_family,
                    duplicate_basis='byte-identical SHA256',independent_information=False))
    # ZIP central directories use names, CRC32, and uncompressed/compressed sizes, not just file names.
    arch=collections.defaultdict(list)
    for r in meta['archive_directories']:
        if r.get('directory_signature'):arch[r['directory_signature']].append(r)
    for digest,items in arch.items():
        if len(items)>1:
            for r in items:extras.append(dict(group_id='ZIP_'+digest,source_id=r['source_id'],dataset_family='archive copy',
                duplicate_basis='identical ZIP member names/sizes/CRC32 directory; cryptographic payload equivalence not asserted',independent_information=False))
    for r in lfscopies:
        for kind in ['payload','pointer']:
            rel=Path(r[kind]['path']).relative_to(RAW_A).as_posix();sid=inv.loc[inv.relative_path.eq(rel),'source_id'].iloc[0]
            extras.append(dict(group_id='LFS_'+r['payload']['sha256'],source_id=sid,dataset_family='RADDIT',
                duplicate_basis='payload hash equals copied Git LFS OID; pointer is not another payload',independent_information=False))
    pd.concat([groups,pd.DataFrame(extras)],ignore_index=True).to_csv(ROOT/'RAW_SOURCE_GROUPS.csv',index=False)
    write('SELECTED_FORENSIC_INPUTS.json',dict(time=now(),files=selected,raw_modified=False))
    print('SOURCE_CLOSURE',len(inv),'files;',offset,'embedding rows; no new fits',flush=True)


if __name__=='__main__':main()
