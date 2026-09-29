"""Deliver the mandatory source-authority stop; do not label unrun ML as failed ML."""
from common14 import *
from close_sources14 import STOP
import re,shutil

ARMS=['J0_STATIC','J1_CURRENT_STATE','J2_STATIC_SEMANTIC','J3_CURRENT_STATE_SEMANTIC','J4_CURRENT_STATE_SEMANTIC_NN','J5_ALL_AUTHORIZED']


def main():
    stop=read(ROOT/'STOP_CONDITION_RECEIPT.json');assert not stop['ML_authorized']
    join=read(ROOT/'RADDIT_KESTREL_JOIN_SUMMARY.json');inventory=read(ROOT/'RAW_INVENTORY_RECEIPT.json')
    base=read(ROOT/'V13_BASELINE_REPRODUCTION.json');assert base['PASS']
    alignment=read(ROOT/'RADDIT_EMBEDDING_ALIGNMENT_AUDIT.json')
    comp=pd.read_csv(ROOT/'BASELINE_MODEL_COMPARISON.csv').assign(status='REPRODUCED_FROZEN_V13_BASELINE',metrics_available=True)
    unrun=pd.DataFrame([dict(arm=a,status=STOP,metrics_available=False,scope='NOT_EVALUATED',reason='Physical-job semantic crosswalk not proven') for a in ARMS[2:]])
    comp=pd.concat([comp,unrun],ignore_index=True);comp.to_csv(ROOT/'MODEL_COMPARISON.csv',index=False)
    fold=pd.read_csv(ROOT/'BASELINE_FOLD_METRICS.csv').assign(status='REPRODUCED_FROZEN_V13_BASELINE',metrics_available=True)
    fold=pd.concat([fold,pd.DataFrame([dict(arm=a,fold=i,status=STOP,metrics_available=False) for a in ARMS[2:] for i in range(1,6)])],ignore_index=True)
    fold.to_csv(ROOT/'FOLD_METRICS.csv',index=False)
    tails=pd.read_csv(V13/'TOTAL_LONG_TAIL_METRICS.csv');tails=tails[tails.arm.isin(['EXPANDING_S0','EXPANDING_S4'])].copy()
    tails['original_arm']=tails.arm;tails['arm']=tails.arm.map({'EXPANDING_S0':ARMS[0],'EXPANDING_S4':ARMS[1]})
    tails['status']='REPRODUCED_FROZEN_V13_BASELINE';tails['metrics_available']=True
    tails=pd.concat([tails,pd.DataFrame([dict(arm=a,fold=i,cohort=f'gt{h}h',status=STOP,metrics_available=False) for a in ARMS[2:] for i in range(1,6) for h in [4,8,12,24]])],ignore_index=True)
    tails.to_csv(ROOT/'LONG_TAIL_METRICS.csv',index=False)
    comp[['arm','status','metrics_available','Q90_pinball','Q50_MAE','reservation_actual_GPUh','reservation_to_W0',
          'short_job_reservation_inflation','Q90_actual_ratio_median','Q90_actual_ratio_P90']].to_csv(ROOT/'SHARPNESS_METRICS.csv',index=False)
    fold[['arm','fold','status','metrics_available','proper_interval_NLL','proper_NLL_N','proper_score_finite','monotonicity_pass','zero_support_count']].to_csv(ROOT/'PROPER_SCORE_METRICS.csv',index=False)
    pd.DataFrame([dict(contrast=x,status=STOP,paired_jobs=0,metrics_available=False,
        delta_min_fold=None,delta_gt4h=None,delta_pinball=None,reason='COMMON_JOINED_POPULATION empty under authorized identity rule')
        for x in ['J2-J0','J3-J1','J4-J3','J5-J4']]).to_csv(ROOT/'SOURCE_FAMILY_CONTRASTS.csv',index=False)
    bias=[]
    for i in range(1,6):
        f=pd.read_parquet(V9/'.local'/f'fold{i}/VALID.parquet')
        subsets=[('ALL',pd.Series(True,index=f.index))]+[(f'gt{h}h',f.event&f.runtime_seconds.gt(h*3600)) for h in [4,12,24]]
        for field in ['qos','partition','num_gpus_req']:
            for val in f[field].dropna().unique():subsets.append((field+'='+str(val),f[field].eq(val)))
        for name,mask in subsets:
            g=f[mask];y=g.loc[g.event,'runtime_seconds']
            bias.append(dict(fold=i,stratum=name,N=len(g),matched_N=0,unmatched_N=len(g),matched_fraction=0.0 if len(g) else None,
                unmatched_fraction=1.0 if len(g) else None,matched_runtime_mean=None,matched_runtime_q90=None,
                unmatched_runtime_mean=float(y.mean()) if len(y) else None,unmatched_runtime_q90=float(y.quantile(.9)) if len(y) else None,
                matched_unmatched_runtime_difference=None,status='NO_AUTHORIZED_JOINED_POPULATION',
                inference='No semantic effect or joined-subset advantage can be estimated.'))
    pd.DataFrame(bias).to_csv(ROOT/'JOINED_POPULATION_BIAS_AUDIT.csv',index=False)
    candidates={
        'job name token':'name_hash','submit_line token':'submit_line_hash','script token':'submit_script_hash','workdir token':'work_dir_hash',
        'job_type':'job_type_hash','array metadata':'array_range','array parent/task identity':'array_pos','account recurrence':'account_hash',
        'user recurrence':'user_hash','node list':'nodelist','nodes used':'nodes_used','GPU node occupancy':'gpu_nodes_occupied',
        'request shape':'nodes_req;processors_req;gpus_requested','resource ratios':'requested resource columns',
        'state-transition descriptors':'state;state_simple (snapshot only)','requeue indicators':'NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY',
        'restart / attempt evidence':'NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY','dependency information':'NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY',
        'reservation':'NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY','scheduler flags':'NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY'}
    rows=[]
    for name,field in candidates.items():
        for i in range(1,6):
            post=name in ['node list','nodes used','GPU node occupancy','state-transition descriptors']
            rows.append(dict(field=name,source_column=field,fold=i,TRAIN_cardinality=None,VALID_unseen_rate=None,missing_rate=None,
                apparent_mutability='post-start/final snapshot' if post else 'original revision not proven',
                submit_time_authority=False,outcome_leakage_risk='HIGH_POST_START' if post else 'UNRESOLVED_ARCHIVE_AUTHORITY',
                decision='EXCLUDE_FROM_V14_ML_AFTER_SOURCE_STOP',statistics_status=STOP,statistics_available=False))
    pd.DataFrame(rows).to_csv(ROOT/'KESTREL_UNUSED_FIELD_AUDIT.csv',index=False)
    existing=read(V13/'CURRENT_STATE_FEATURE_CONTRACT.json')['columns']
    static=read(V9/'FOLD_1_PREPROCESSING.json')['columns'];families=[]
    for family,names in [('STATIC_V13',static),('CURRENT_STATE_V13',existing),
                         ('RADDIT_SEMANTIC_SVD',[f'SEM_SVD32_{i:02}' for i in range(32)]),
                         ('RADDIT_SEMANTIC_NEIGHBOR',read(ROOT/'PREREGISTRATION.json')['semantic_neighbors']['fields']),
                         ('KESTREL_NEW_STATIC',list(candidates)),
                         ('FACILITY_CURRENT_STATE',['IT_power_current','PUE_current','IT_power_lag15m_mean','IT_power_lag1h_mean','IT_power_lag6h_mean','IT_power_1h_delta','PUE_lag1h_mean'])]:
        for name in names:
            reused=family in ['STATIC_V13','CURRENT_STATE_V13']
            families.append(dict(name=name,family=family,source='Frozen V13' if reused else family,
                event_time_semantics='V13 t-exclusive event contract' if family=='CURRENT_STATE_V13' else
                    'neighbor END<t required; NOT_RUN' if family=='RADDIT_SEMANTIC_NEIGHBOR' else
                    'observation timestamp<=t backward-asof required; NOT_RUN' if family=='FACILITY_CURRENT_STATE' else 'submission/request candidate',
                authority='Kestrel_trace_proxy' if reused else 'UNPROVEN_FOR_V14',
                train_time_availability='frozen baseline only' if reused else 'NOT_AUTHORIZED',
                inference_time_availability='existing research component only' if reused else 'NOT_PROVEN',
                outcome_leakage_risk='inherits V13 audit' if reused else 'NO_NEW_FEATURE_CONSTRUCTION_ALLOWED',
                allowed=reused,allowed_scope='baseline reproduction only' if reused else 'none',
                reason='No new model fit; mandatory source-identity stop.'))
    write('AUTHORIZED_FEATURE_FAMILIES.json',dict(time=now(),ML_AUTHORIZED=False,features=families))
    write('FEATURE_CONTRACT.json',dict(time=now(),status=STOP,V13_folds=record(V13/'TEMPORAL_FOLD_CONTRACT.json'),
        preprocessing_fits=0,SEM_SVD32_executed=False,semantic_kNN_executed=False,facility_asof_executed=False,
        unauthorized_missing_semantics_filled=False,new_job_callability_proven=False,authorized_features=record(ROOT/'AUTHORIZED_FEATURE_FAMILIES.json')))
    items=['application/workflow identity','original script / command information','input dataset size','iteration / epoch count',
           'job-step records','requeue history','preemption','retry / restart attempt','scheduler internal priority','reservation',
           'job dependency / DAG','assigned hardware','GPU model','GPU utilization','GPU memory utilization','CPU utilization',
           'node power','filesystem I/O','network I/O','node contention','application phase','checkpoint/restart behavior','queue topology/state','job revision history']
    gaps=[]
    for n,item in enumerate(items,1):
        if n in [1,2]:status='AVAILABLE_NOT_JOINABLE';reason='RADDiT semantic fields/code exist, but physical-job crosswalk is unproven; Kestrel publishes hashed tokens.'
        elif n in [12,20]:status='AVAILABLE_POST_START_ONLY';reason='Original Kestrel schema exposes nodelist/shared-node final-state fields; not submission authority.'
        elif n in [14,15,16,17]:status='AVAILABLE_OTHER_SYSTEM_ONLY';reason='Eagle telemetry schemas/catalogs are present; no direct Kestrel historical job join established. GenAI relative power is not a crosswalk.'
        elif n==23:status='AVAILABLE_AND_JOINABLE';reason='Existing V13 causal arrival/pending/running trace proxy already tested; does not recover scheduler internal priority.'
        elif n in [13,21,22]:status='AUTHORITY_UNCLEAR';reason='Hardware/application documentation and examples exist; per-episode historical values are not established.'
        else:status='NOT_FOUND_IN_LOCAL_RAW';reason='Not found as a Kestrel V13-episode-joinable historical authority in the inventoried schema and searched source/docs; not a global nonexistence claim.'
        gaps.append(dict(item_number=n,information=item,classification=status,reason=reason,
            scope='LOCAL_METADATA_AND_DOCUMENTATION_CLOSURE_AFTER_SOURCE_STOP',record_level_gap_experiment_run=False))
    pd.DataFrame(gaps).to_csv(ROOT/'MISSING_INFORMATION_GAP_ANALYSIS.csv',index=False)
    (ROOT/'MISSING_INFORMATION_GAP_ANALYSIS_KO.md').write_text(
        '# 정보 공백: source-authority 중단의 정리\n\n'
        'V14 challenger의 예측 성능은 평가하지 않았습니다. 따라서 이 표는 모든 primary arm의 성능 실패 뒤 수행하는 Stage G 실험 결과가 아닙니다. '
        '전수 inventory·schema·623개 로컬 문서/코드 검색에서 확인한 정보 위치와 권위의 한계를 정리합니다. '
        'MISSING_INFORMATION_GAP_ANALYSIS_RUN=TRUE의 범위는 이 로컬 근거 정리입니다. STAGE_G_POST_MODEL_FAILURE_RUN=FALSE입니다.\n\n'
        '우선 필요한 것은 ① 원 Slurm episode ↔ RADDiT row의 공인 대응표, ② historic row ↔ encrypted chunk의 생성·필터·재정렬 이력, '
        '③ naive embedding/facility timestamp의 timezone과 관측·ingestion 시점, ④ 새 작업에서 동일 semantic 좌표를 만드는 입력·변환 계약입니다. '
        '이 권위가 확보되기 전에는 SVD나 더 복잡한 모델이 identity 문제를 해결하지 못합니다.\n\n'
        'RAW에 자료가 있다는 것, 같은 시설이라는 것, generic Slurm 문서에 필드가 설명돼 있다는 것은 해당 역사적 작업에 연결 가능한 관측값을 확보했다는 뜻이 아닙니다. '
        '세부 24개 항목은 CSV에 기록했습니다. 중단 조건에 따라 외부 신규 다운로드와 후속 연구 실험은 실행하지 않았습니다.\n',encoding='utf-8')
    (ROOT/'EXTERNAL_MISSING_SOURCE_DISCOVERY.md').write_text(
        '# NOT_RUN_SOURCE_AUTHORITY_FAILURE\n\n'
        '모델 비교 전 §39의 mandatory identity stop이 발생했습니다. All-primary-model-failure 후 Stage G는 실행되지 않았으므로 외부 신규 탐색도 실행하지 않았습니다. '
        '로컬 datacard/README에 NLR catalog와 RADDiT GitHub 주소가 존재하지만 이번 실행에서 추가 공개 authority를 발견·검증했다는 주장은 하지 않습니다. '
        '원 데이터 소유자의 Slurm↔RADDiT crosswalk 및 encrypted chunk export provenance가 다음 권위 회복 대상입니다.\n',encoding='utf-8')
    flags=dict(time=now(),status='STOPPED_SOURCE_AUTHORITY_FAILURE',RAW_SOURCE_INVENTORY_COMPLETE=inventory['complete'],
        RAW_PHYSICAL_FILES=inventory['physical_files'],RAW_INITIAL_FAMILY_GROUPS=len(inventory['families']),
        RADDIT_HISTORIC_TRACE_FOUND=True,RADDIT_EMBEDDINGS_FOUND=True,RADDIT_KESTREL_JOIN_PROVEN=False,RADDIT_KESTREL_JOIN_RATE=0.,
        RADDIT_EMBEDDING_ROW_MAPPING_PROVEN=False,RADDIT_EMBEDDING_OUTCOME_INPUT_FOUND=False,
        RADDIT_HISTORICAL_SEMANTIC_VALUE_SUPPORTED=False,RADDIT_HISTORICAL_SEMANTIC_VALUE_STATUS=STOP,
        RADDIT_NEW_JOB_SEMANTIC_CALLABLE=False,FACILITY_STATE_JOIN_AUTHORIZED=False,GENAI_DIRECT_JOB_JOIN_AUTHORIZED=False,
        EAGLE_USED_AS_KESTREL_FEATURE=False,V13_S0_REPRODUCED=True,V13_S4_REPRODUCED=True,SELECTED_V14_ARM='NONE',
        TOTAL_RUNTIME_MODEL_VALIDATED=False,TOTAL_OVERALL_Q90_GATE_PASS=False,TOTAL_MIN_FOLD_GATE_PASS=False,
        TOTAL_GT4H_GATE_PASS=False,TOTAL_GT12H_GATE_PASS=False,TOTAL_GT24H_GATE_PASS=False,
        final_gate_flag_scope='No authorized selected V14 provider; not a fabricated numerical failure for unrun J2-J5. Baseline numerical gates remain in MODEL_COMPARISON.',
        C1_ROLLING14_EVALUATED=False,STAGE_C_AUTHORIZED=False,REMAINING_MODEL_RUN=False,REMAINING_RUNTIME_MODEL_VALIDATED=False,
        V42_RESEARCH_RUNTIME_PROVIDER_READY=False,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,REQUEST_VERSION_AUTHORITY_FOUND=False,
        APRIL_STATUS='EXPOSED_REGRESSION_ONLY',APRIL_EVALUATION_STATUS=STOP,APRIL_USED_FOR_SELECTION=False,APRIL_MODEL_CHANGED_AFTER_EVALUATION=False,
        MAY_PAYLOAD_OPENED=False,MAY_USED_FOR_SELECTION=False,MAY_USED_FOR_EVALUATION=False,
        MISSING_INFORMATION_GAP_ANALYSIS_RUN=True,MISSING_INFORMATION_GAP_ANALYSIS_SCOPE='Local metadata/documentation closure; no post-model-failure experiment',
        STAGE_G_POST_MODEL_FAILURE_RUN=False,EXTERNAL_SOURCE_SEARCH_RUN=False,NEW_ML_FITS=0,SEMANTIC_REDUCER_FITS=0,
        scientific_conclusion='A physical-job semantic crosswalk was not established. V14 information-value hypothesis was not evaluated; no runtime unpredictability or hidden-cause conclusion is supported.')
    write('FINAL_VERDICT.json',flags)
    write('FINAL_SELECTION_FREEZE.json',dict(time=now(),selected='NONE',status=STOP,all_primary_challengers_evaluated=False,
        baseline_reproductions=2,challengers_evaluated=0,reason=stop['trigger'],files=[record(ROOT/n) for n in ['PREREGISTRATION.json','MODEL_COMPARISON.csv','FOLD_METRICS.csv','RADDIT_KESTREL_JOIN_SUMMARY.json']]))
    answer_report(comp,join,inventory,alignment)
    (ROOT/'README.md').write_text('# Runtime-vNext14 multisource information recovery\n\n'
        'Result: **STOPPED_SOURCE_AUTHORITY_FAILURE**. No new ML fit. [한국어 최종 50문항 검토](FINAL_REVIEW_KO.md), [판정](FINAL_VERDICT.json).\n\n'
        'RADDiT job_id is a positional index, not an established original Slurm ID. Original Kestrel ID+submit exact matches: 0. '
        'J0/J1 are exact frozen V13 baseline reproductions; J2–J5 are explicitly NOT_RUN. This is a negative joinability finding, not negative semantic predictive performance.\n\n'
        '23,601 filesystem entries in both nested raw roots were inventoried once; 27 initial family groups include documentation/non-runtime material. '
        'Copies are grouped separately and never counted as independent information. Large ledgers remain .local and are hash-bound. Raw data and V6–V13 are unchanged.\n\n'
        'Reproduction of the stopped research path: inventory14.py → schema14.py → baseline14.py → preregister14.py (once) → join14.py → '
        'close_sources14.py → authority14.py → finalize14.py → verify14.py. Existing PREREGISTRATION.json is not overwritten. '
        'No script fits a V14 learner or reducer. Original Windows raw paths and the frozen V9/V13 local caches are required.\n',encoding='utf-8')
    logs=[];(ROOT/'EXECUTION_LOGS').mkdir(exist_ok=True)
    for p in sorted(LOCAL.glob('*.log')):
        dest=ROOT/'EXECUTION_LOGS'/p.name;shutil.copyfile(p,dest)
        logs.append(dict(original=record(p),archived=record(dest)))
    write('EXECUTION_LOG_PRESERVATION.json',dict(time=now(),logs=logs,
        implementation_repair='First join attempt encountered mixed aware-timestamp pandas dtype on archive concat. Retry normalizes explicit offsets to UTC without changing timestamps or source files. Both logs retained.'))


def answer_report(comp,join,inventory,alignment):
    s0=comp[comp.arm.eq(ARMS[0])].iloc[0];s4=comp[comp.arm.eq(ARMS[1])].iloc[0]
    nr='NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다.'
    answers=[
        'V13 6개 후보의 all-gate 통과는0개였습니다. S4 pooled 91.84%는 단독 범위 내지만 min-fold70.70%, >4h69.72%, >12h64.25%, >24h46.88%로 temporal/long-runtime 기준에 미달했습니다. V13 결과를 재해석하거나 변경하지 않았습니다.',
        f'ROOT_A={RAW_A}; ROOT_B={RAW_B}. ROOT_B는 ROOT_A 안에 있으므로 물리 경로는 한 번만 집계하고 root membership 두 개를 표시했습니다.',
        f'{inventory["physical_files"]:,}개 파일을 {len(inventory["families"])}개 초기 family군으로 분류했습니다. 여기에는 코드·문서·비런타임 자료가 포함됩니다. 독립된 유효 데이터셋 27개라는 뜻이 아닙니다. 파일별 A–H 분류와 복사본 grouping을 별도로 제공했습니다.',
        '원래 Kestrel archive는 기존 V13 작업 identity를 모두 재확인하는 데 사용했습니다. 새 semantic source의 physical-job join은 입증되지 않았습니다. 시설 time-level 후보와 다른 HPC 자료를 직접 job feature로 연결하지 않았습니다.',
        f'원본 pre-April archive {join["Kestrel_candidate_jobs"]:,}행과 RADDiT {join["RADDiT_historic_jobs"]:,}행의 ID+submit exact match는0개입니다. V13 GPU {join["Kestrel_V13_GPU_jobs"]:,}행의 authorized join rate도0%입니다. RADDiT ID는0~2,557,883의 row position입니다. 원본 전체에서 ID 단독 우연 일치1,159,305 keys가 있어도 submit을 추가하면0개이며 이를 실제 연결로 인정하지 않았습니다.',
        '5개 fold의 TRAIN/CAL/VALID 모두 authorized join rate0%입니다. 분모와 >4h/>12h/>24h 및 GPU strata는 SEMANTIC_SUPPORT_METRICS.csv에 있습니다.',
        'Joined population 자체가0이므로 matched/unmatched runtime 차이나 semantic bias 효과를 추정할 수 없습니다. Long-job별 matched0 및 원래 unmatched 모집단 통계만 보고했습니다.',
        f'FALSE. 45개 chunk의 footer 총행수는{alignment["total_embedding_rows"]:,}, historic trace는2,557,884입니다. 동일 순서를 가정하지 않았습니다. Source stop 이후 payload shared-field alignment는 미실행이며 ambiguous/missing count는 null로 남겼습니다. 45개 실제 파일의 SHA256은 별도 사본의 LFS OID와 일치합니다.',
        '공개 job-string 생성 함수에는 actual runtime/START/END/power가 없었습니다. 이 범위에서 OUTCOME_INPUT_FOUND=FALSE입니다. 검색 DB의 별도 outcome column은 vector 생성 입력과 다릅니다. 비공개 배포 chunk 변환 이력까지 입증한 것은 아닙니다.',
        '공개 생성법은 submission semantic proxy 후보로 방어할 수 있습니다. 그러나 current trace의 물리 작업 대응·배포 vector provenance가 확정되지 않아 V14 입력으로 승인하지 않았습니다. Strict causal authority가 아닙니다.',
        'FALSE. 공개 LLM 생성 예시는 있지만 V42가 원 script/metadata와 동일 encrypted coordinate transform을 제공받는 경로는 입증되지 않았습니다. 역사적 lookup은 새 작업 provider가 아닙니다.',
        nr+' SEM_SVD32 차원은32로 사전 고정했지만 reducer fit은0회입니다.',
        nr+' k=10과 END<t 조건은 계약에만 동결했으며 neighbor search를 실행하지 않았습니다.',
        'name/submit-line/script/workdir/job-type hash와 array 관련 column은 schema에 존재합니다. §39 stop으로 TRAIN cardinality/VALID unseen 통계를 새로 계산하지 않았고 새로운 static family를 승인하지 않았습니다. 미실행 값을0으로 채우지 않았습니다.',
        '일반 Slurm 문서/예시는 있으나 검색한 로컬 권위에서 해당 V13 episode의 역사적 requeue/attempt ledger를 찾지 못했습니다. NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY입니다.',
        'job-step을 설명하는 sacct 문서는 있지만 해당 기간의 원 작업과 연결할 historical job-step record authority를 찾지 못했습니다.',
        '로컬 README는 ESIF 시설 PUE/IT-power임을 명시합니다. 같은 시설의 후보이나 facility-wide power를 Kestrel 전용 node telemetry로 간주하지 않았습니다.',
        'Footer ts 범위2015-11-10~2025-08-29는 달력상5개 fold와 겹칩니다. ts는 timezone-naive이며 UTC/ingestion timing이 확정되지 않아 정확한 시간 join 승인을 내리지 않았습니다. Power 값과 post-April runtime outcome은 읽지 않았습니다.',
        nr+' backward-asof만 허용한다는 규칙은 유지했고 실제 facility join은0회입니다.',
        '승인하지 않았습니다. 검사된 aggregated schema는 power[W], timestep[s]이며 공인 Slurm ID/절대 시각 연결이 없습니다. Catalog version2026-04-10은 수집 기간이2026-only라는 증거가 아니므로 그 주장은 하지 않았습니다.',
        'Eagle은 별도 HPC system입니다. node telemetry가 존재해도 Kestrel 작업의 결측 feature를 채우는 데 사용하지 않았습니다.',
        'TRUE. S0의5개 fold 전체 VALID Q50/Q90가 저장값과 bit-identical하고 V9 full VALID hazard parameters도 동일합니다. 새 fit은 없습니다.',
        'TRUE. S4의5개 fold 전체 VALID Q50/Q90가 저장값과 bit-identical합니다. 두 baseline 각각234,036 VALID행을 확인했고 pooled exact-completed 평가는230,237행입니다.',
        nr,nr,nr,nr,
        '평가 불가. 새 information family가 실행되지 않아 predictive contribution을 비교할 수 없습니다.',
        '평가 불가. J2-J0/J3-J1/J4-J3/J5-J4의 paired delta는 null이며 유효 paired jobs는0입니다.',
        'V14 selected model은 없습니다. 재현한 V13 S0/S4 pooled는91.74%/91.84%입니다. 미실행 challenger coverage를 생성하지 않았습니다.',
        'V13 S0/S4 재현 min-fold는66.47%/70.70%입니다. V14 신규 모델의 min-fold는 미측정입니다.',
        'V13 S4 재현 >4h69.72%, >12h64.25%, >24h46.88%입니다. 이는 새 semantic 모델 성능이 아닙니다.',
        'V13 S0/S4 재현 Q90 pinball은4923.74s/4752.76s입니다. J2–J5 값은 없습니다.',
        f'V13 S4 재현 reservation/actual={s4.reservation_actual_GPUh:.6f}, W0-relative={s4.reservation_to_W0:.6f}입니다. 새 semantic arm ratio는 미실행입니다.',
        f'V13 S4 재현 short-job GPUh 예약/실제={s4.short_job_reservation_inflation:.6f}입니다. 새 arm 비교는 없습니다.',
        'Semantic improvement를 주장하지 않았습니다. COMMON_JOINED_POPULATION은0행이고 FULL_V13_POPULATION baseline과 결측 범위만 유지했습니다.',
        '아니요. 신규 challenger가 미실행이며 기존 S0/S4도 C1 min-fold≥80% AND >4h≥80% 조건을 만족하지 못합니다.',
        '없습니다. Baseline은 기존 gate 실패를 재현했고 J2–J5는 성능 실패가 아니라 source-authority 미충족으로 미실행입니다.',
        'V14의 Stage C unused-field 정밀 분석은 source stop 후 미실행입니다. 최종 flag의 legacy STAGE_C_AUTHORIZED(remaining/provider 단계)도FALSE입니다. 혼동하지 않도록 두 범위를 구분합니다.',
        nr+' REMAINING_MODEL_RUN=FALSE, validation도FALSE입니다.',
        '새 provider를 만들지 않았고 new-job semantic callability를 입증하지 못했습니다.',
        '아니요. April의 자료 지위는 EXPOSED_REGRESSION_ONLY이고 이번 평가는 미실행입니다.',
        'NO. April selection/tuning은 수행하지 않았습니다.',
        'NO. May의 runtime payload/labels/outcomes를 decode·요약·평가하지 않았습니다. 원 archive의 May member는 열지 않았고 path/schema inventory 및 전체 파일 hash는 record decoding과 구분했습니다.',
        '아니요. V42_RESEARCH_RUNTIME_PROVIDER_READY=FALSE입니다.',
        '아니요. STRICT_CAUSAL_RUNTIME_PROVIDER_READY=FALSE, REQUEST_VERSION_AUTHORITY_FOUND=FALSE입니다.',
        'V14는 semantic 성능검증에 실패한 것이 아니라 physical-job identity 연결을 확보하지 못한 forensic stop입니다. 우선 필요한 정보는 공인 Slurm↔RADDiT↔embedding crosswalk와 chunk export/timezone/ingestion 계약입니다.',
        '자료·source code·generic Slurm docs는 있으나 필요한 historical crosswalk/export receipt는 검색 범위에서 찾지 못했습니다. 관련24개 정보축의 로컬 근거와 미확인을 gap CSV/문서에 구분했습니다.',
        '이번 mandatory stop에서 외부 신규 source 탐색은 실행하지 않았습니다. 모델 실패 이후 Stage G는 발동되지 않았습니다. 로컬에 저장된 공개 source 주소를 새 발견이나 검증으로 계산하지 않았습니다.',
        '알려진 한계: positional ID, ID+submit exact join0, 미입증된 embedding row/export mapping, 미확인 new-job callability입니다. 미검증 가설: semantic/telemetry가 runtime robustness를 개선할 수 있는지입니다. 이번에 시험하지 않은 정보를 무용하다고 보거나 runtime randomness/예측 불가능/hidden-variable causality를 주장하지 않습니다.'
    ]
    request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig')
    portion=request.split('37. REQUIRED FINAL KOREAN REPORT QUESTIONS',1)[1].split('38. FINAL FLAGS',1)[0]
    questions=re.findall(r'(?m)^(\d+)\. (.+)$',portion);assert len(questions)==len(answers)==50,(len(questions),len(answers))
    lines=['# Runtime-vNext14 최종 검토','',
        '**판정: STOPPED_SOURCE_AUTHORITY_FAILURE. 신규 ML fit 0회.**',
        '이 결과는 semantic 정보의 예측 효용 실패가 아니라, 원 물리 작업과의 연결을 입증하지 못해 §39에서 중단한 negative forensic result입니다.','',
        '## 완료 범위','',
        '- 두 중첩 raw root의23,601개 파일을 한 번씩 inventory하고27개 초기 family군으로 정리했습니다. 후보 Parquet schema2,588개, ZIP 내부 목록17개를 검사했습니다.',
        '- V13 S0/S4의 전체 VALID 예측을 정확히 재현했습니다. V6–V13 원 파일 hash를 유지했습니다.',
        '- 원본 Kestrel pre-April identity6,326,884행을 복구하고 기존 V13 GPU621,583행의 identity를 모두 원본 archive에 대조했습니다.',
        '- RADDiT2,557,884행의 ID는 연속 row position입니다. 원본 ID+submit exact match0이며, V13 GPU의 JKEY0–3도모두0입니다.',
        '- 배포 embedding45개 chunk/1,780,972행의 schema·offset을 기록하고 LFS OID 일치를 검증했습니다. Raw vector와 payload shared-field alignment는 중단 뒤 실행하지 않았습니다.','',
        '## 미실행 범위','',
        'J2–J5, SVD32, semantic kNN, facility join, grouped ablation, C1, remaining/provider, April 평가, May 열람은 미실행입니다. '
        '미측정 성능·ambiguity·missing count를0/PASS로 채우지 않았습니다. Embedding audit의 null count는 중단 때문에 미측정이라는 뜻입니다.',
        'Unused-field cardinality와 실제 facility sampling/latency 분석도 미실행이며, metadata에서 확인한 사실만 별도로 기록했습니다. '
        '요청된 source-gap 표는 로컬 근거 정리이고, 모든 challenger 성능 실패 후 수행하는 Stage G나 외부 신규 탐색이 아닙니다.','',
        '## 해석 한계','',
        'ID 단독 숫자 일치와 같은 과거 작업임을 증명하는 exact identity를 구분합니다. 임의 시간 offset, nearest timestamp, row number 대입으로 join rate를 높이지 않았습니다. '
        'S0/S4 수치는 baseline 재현이며 V14 semantic arm의 결과가 아닙니다. Raw source는 수정하지 않았고 V42/CC4/MESS/kernel/optimizer/OpenDSS를 수정·실행하지 않았습니다.']
    for (n,q),a in zip(questions,answers):lines+=['',f'## {n}. {q}','',a]
    lines+=['','검증 결과는 VERIFICATION.json, 입력/로컬 ledger/전달 파일 hash는 각 manifest에 있습니다. '
             '초기 archive concat의 mixed timezone dtype 오류와 UTC 정규화 후 성공 로그를 모두 보존했습니다. Timestamp를 fitting하거나 근사 매칭하지 않았습니다.']
    (ROOT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()
