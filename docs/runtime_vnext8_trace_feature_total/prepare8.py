from common8 import *
from features8 import *
import pandas as pd,numpy as np

def main():
    LOCAL.mkdir(exist_ok=True)
    source=V6/'PREAPRIL_JOBS.parquet';old=pd.read_parquet(source)
    cache=V7/'.local/GPU_PREAPRIL.parquet';raw=pd.read_parquet(cache)
    assert sha(cache)==read(V7/'PREPARATION_RECEIPT.json')['gpu_local_data']['sha256']
    assert sha(source)==read(V6/'DATA_SPLIT_AND_MATURITY.json')['data']['sha256']
    raw['job_id_public']=raw.id.astype(str)
    extra=['job_name_token','submitline_token','script_token','workdir_token','array_index']
    r=raw.rename(columns={k:v for k,v in RAW_MAP.items() if k not in ['gpus_requested','nodes_req','processors_req','user_hash','account_hash']})
    f=old.merge(r[['job_id_public']+extra],left_on='job_id',right_on='job_id_public',validate='one_to_one').drop(columns='job_id_public')
    target=old[['job_id','runtime_seconds','label_valid']].merge(raw[['job_id_public','start_time','end_time']],left_on='job_id',right_on='job_id_public',validate='one_to_one')
    cutoff=pd.Timestamp(read(ROOT/'EXPERIMENT_PROTOCOL.json')['logical_freeze_cutoff'])
    exact=(target.end_time-target.start_time).dt.total_seconds()
    valid=target.label_valid&target.end_time.lt(cutoff)
    error=float(np.abs(exact[valid]-target.loc[valid,'runtime_seconds']).max())
    assert error==0 and (exact[valid]>=0).all()
    # Official downstream source explicitly maps end_time-start_time; no reinterpretation.
    desc=HPC/'src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml'
    assert 'runtime_seconds: { derive: "end_time - start_time" }' in desc.read_text()
    write('RUNTIME_TARGET_AUTHORITY_AUDIT.json',dict(TARGET_IS_EXECUTION_RUNTIME=True,TARGET_RUNTIME_AUTHORITY_PASS=True,QUEUE_WAIT_INCLUDED_IN_TARGET=False,REQUESTED_WALLTIME_USED_AS_LABEL=False,
      target='end_time-start_time seconds: accounting execution interval, not CPU busy time and not cumulative work across unobserved requeues',
      normalized_equivalence_max_abs_seconds=error,verified_rows=int(valid.sum()),invalid_order_excluded=True,zero_duration_retained=True,
      start_end_source='NLR data card Start/End, public offset timestamp; hpc-oda descriptor runtime_seconds derive; exact rowwise agreement with raw pre-April start/end',
      limitations='May include suspension/failed executions; not a proof of successful task or original-attempt cumulative runtime. Requeue identity limits preserved.',
      evidence=[record(desc),record(RAW.parent/'datacard.md'),record(source),record(cache)],target_used_as_feature=False,checked_at=now()))
    f.to_parquet(ROOT/'PREAPRIL_JOBS.parquet',index=False);data=roles(f);p=read(ROOT/'EXPERIMENT_PROTOCOL.json')
    details={}
    for role,g in data.items():
        expected=read(V6/'DATA_SPLIT_AND_MATURITY.json')['roles'][role]['mature_membership'];assert ids(g)==expected
        details[role]=dict(N=len(g),membership=ids(g),unresolved=int(f.role.eq(role).sum()-len(g)),zero=int(g.runtime_seconds.eq(0).sum()),cutoff=p['TRAIN']['end_before'] if role=='TRAIN' else p[role]['mature_before'])
    write('DATA_SPLIT_AND_MATURITY.json',dict(roles=details,exact_vNext6_mature_membership=True,source=record(source),raw_cache=record(cache),data=record(ROOT/'PREAPRIL_JOBS.parquet'),
      boundary='Same v6 pre-April logical freeze March31T08Z; v7 wider descriptive cohort not used as training membership',
      censorship='Excluded when no valid start/end before role cutoff; no unknown end converted to zero',April_payload_read=False,May_payload_read=False))
    f[['job_id','role','label_valid','submit_time','start_time','end_time']].to_parquet(ROOT/'RUNTIME_LABEL_MATURITY_AUDIT.parquet',index=False)
    tr=data['TRAIN'];maps={};screen=[];accepted=[]
    for c in ['qos','partition']+IDENTITIES:
        counts=tr[c].astype('string').fillna('__MISSING__').value_counts();minimum=1 if c in ['qos','partition'] else p['identity_screen']['train_min_count']
        supported=set(counts[counts>=minimum].index);mapping={k:i+1 for i,k in enumerate(sorted(supported))};maps[c]=mapping
        row=dict(feature=c,train_cardinality=len(counts),supported_cardinality=len(supported),train_supported_row_fraction=float(tr[c].astype('string').fillna('__MISSING__').isin(supported).mean()))
        for role in ['DEV','CAL_FIT','CAL_VALID']:
            x=data[role][c].astype('string').fillna('__MISSING__');row[role+'_unseen_rate']=float((~x.isin(supported)).mean())
        okay=c in ['qos','partition'] or (len(counts)<=5000 and row['train_supported_row_fraction']>=.8 and all(row[x+'_unseen_rate']<=.25 for x in ['DEV','CAL_FIT','CAL_VALID']))
        row['included_F2']=okay;row['reason']='SUPPORTED' if okay else 'HIGH_CARDINALITY_OR_RARE_OR_CHRONOLOGICAL_UNSEEN';screen.append(row)
        if okay and c not in ['qos','partition']:accepted.append(c)
    sets=families(accepted);active=set(c for v in sets.values() for c in v);maps={k:v for k,v in maps.items() if k in active}
    write('PREPROCESSING.json',dict(categorical_mappings=maps,unknown_code=0,unknown_name='__UNKNOWN__',fit_scope='TRAIN ONLY; count>=20 identity; count>=1 scheduler',feature_sets=sets,accepted_identities=accepted))
    pd.DataFrame(screen).to_csv(ROOT/'IDENTITY_SUPPORT_SCREEN.csv',index=False)
    inventory=[];trans=engineer(tr.to_dict('records'),maps)
    decision=pd.read_csv(V7/'FEATURE_AUTHORITY_DECISION.csv')
    for c in sorted(set(active)|set(IDENTITIES)|{'job_type_hash','python_job','reframe_job','submit_hour','submit_dow','runtime_seconds','start_time','end_time','state','queue_wait'}):
        numeric=c in trans.columns and c not in maps
        sourcecol=next((src for src,dst in RAW_MAP.items() if dst==c),c)
        rawcol={'requested_seconds':'wallclock_req','requested_memory_mib':'memory_req'}.get(c,sourcecol)
        x=trans[c] if c in trans else tr[c] if c in tr else pd.Series(dtype=float)
        row=dict(archive_field=rawcol,normalized_field=c,missing_rate=float(x.isna().mean()) if len(x) else None,cardinality=int(x.nunique()) if len(x) else None,
          future_or_outcome_derived=c in FORBIDDEN,PR78_class='F/E' if c in FORBIDDEN else 'G' if c in ['job_type_hash','python_job','reframe_job'] else 'D',
          F0=c in sets['F0'],F1=c in sets['F1'],F2=c in sets['F2'],transform='features8.engineer; raw numeric/missing mask or log1p/ratio/product; frozen category code0UNKNOWN',
          accepted=c in active,exclusion_reason='' if c in active else 'Unsupported timing, outcome, unresolved clock, or category support gate',original_request_version_verified=False)
        for role in ['DEV','CAL_FIT','CAL_VALID']:row[role+'_unseen_rate']=next((z[role+'_unseen_rate'] for z in screen if z['feature']==c),None)
        inventory.append(row)
    pd.DataFrame(inventory).to_csv(ROOT/'RAW_FEATURE_INVENTORY.csv',index=False)
    write('RESEARCH_TRACE_RUNTIME_FEATURE_CONTRACT.json',dict(version='vnext8-trace-features-v1',created_at=now(),provenance_mode='Kestrel_trace_proxy',STRICT_CAUSAL_FEATURE_COUNT=0,REQUEST_VERSION_AUTHORITY_FOUND=False,
      feature_sets=sets,feature_order_candidates=sorted(active),categorical_unknown=0,maps=record(ROOT/'PREPROCESSING.json'),transform_source=record(ROOT/'features8.py'),
      forbidden=sorted(FORBIDDEN),job_id_used=False,submit_clock_used=False,outcome_derived_allowed=False,
      memory_semantics='Archive numeric amount converted to MiB; per-node/per-CPU scope not certified. Ratios are trace descriptor arithmetic, not certified total physical memory.',
      invalid_values='Nonfinite/nonpositive resources and walltime, noninteger counts -> NaN with flags. Nonnegative integer array index only. Native LightGBM missing branches, no zero denominator fill.',
      gpu_nodes_inconsistency='Flag recorded GPU>4*nodes; no request silently repaired; min-node versus final-GPU ambiguity retained.',
      legacy_authority=record(V7/'FEATURE_AUTHORITY_FREEZE.json'),support_screen=record(ROOT/'IDENTITY_SUPPORT_SCREEN.csv'),final_selected_features='Frozen later in FEATURE_CONTRACT_FREEZE.json before April'))
    (ROOT/'FEATURE_ENGINEERING_SPEC.md').write_text('''# 연구 trace 변환 명세

`features8.py::engineer`가 정확한 구현이다. GPU/nodes/cores/memory 및 walltime을 수치화하고 비양수·비정수 count·비유한 값은 NaN과 별도 indicator로 표현한다. 0/누락 분모는 NaN이며 임의 물리값으로 대체하지 않는다. log1p walltime/GPU/nodes/cores/memory, GPU/node, cores/node, cores/GPU, memory/GPU, memory/node, GPU×walltime과 그 log1p를 평가한다. F0에는 walltime이나 그 곱이 없다.

메모리는 공개 문자열의 MiB 수치이며 total/per-node/per-CPU 원래 범위는 확정되지 않았다. memory 비율은 연구 trace 산술이라는 한계를 유지한다. GPU>4×nodes도 값을 자동 수정하지 않고 inconsistency flag를 추가한다. array index는 원본 ID lookup이 아닌 공개 구조 descriptor이며 null을 non-array 확정으로 간주하지 않는다.

범주 mapping은 TRAIN에서만 만든다. 지원하지 않는 값은 코드0 UNKNOWN이다. identity는 최소빈도20, cardinality≤5000, TRAIN 지원행≥80%, DEV/CAL 각 unseen≤25%일 때만 F2에 포함한다. 이름·스크립트 등을 역식별하지 않는다. job_type/python/reframe은 생성시점이 검증되지 않아 제외한다. submit clock과 모든 execution outcome은 입력에서 제외한다.

M3의 변환은 log((T+1)/(walltime+1))이며 역변환은 exp(pred)×(walltime+1)-1이다. 0초 runtime을 보존하는 단조변환이고 walltime을 실제 라벨로 바꾸지 않는다. M3 inference에 양수 walltime이 없으면 fail-closed한다.
''',encoding='utf-8')
    print('TARGET_PASS',error,'ROLES',details,'F2_ACCEPTED',accepted,flush=True)
if __name__=='__main__':main()
