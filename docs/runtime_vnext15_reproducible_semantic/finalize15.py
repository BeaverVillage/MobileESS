from common15 import *
import re

def pct(x):return f'{100*float(x):.2f}%'
def describe_runtime(row):
    return (f"pooled Q90 {pct(row.Q90_coverage)}, min-fold {pct(row.min_fold_coverage)}, "
            f">4h {pct(row.gt4h_coverage)}, >12h {pct(row.gt12h_coverage)}, >24h {pct(row.gt24h_coverage)}, "
            f"Q90 pinball {row.Q90_pinball:.4f}, reservation/actual {row.reservation_actual_GPUh:.4f}, W0 대비 {row.reservation_to_W0:.4f}.")
def main():
    runtime=read(ROOT/'RUNTIME_SELECTION_FREEZE.json');cc4=read(ROOT/'CC4_SELECTION_FREEZE.json')
    r=pd.read_csv(ROOT/'RUNTIME_MODEL_COMPARISON.csv').set_index('arm')
    c=pd.read_csv(ROOT/'CC4_MODEL_COMPARISON.csv')
    f=pd.read_csv(ROOT/'KESTREL_SUBMISSION_SEMANTIC_FIELD_AUDIT.csv').drop_duplicates('field')
    rows=read(ROOT/'KESTREL_ORIGINAL_PROJECTION_RECEIPT.json')['rows']
    semantic_runtime=runtime['selected'] in ['R1','R2','R3']
    semantic_cc4=cc4['semantic_model_selected']
    verdict=dict(PRIVATE_RADDIT_EXPORT_REQUIRED=False,PRIVATE_RADDIT_VECTOR_TRANSFORM_REQUIRED=False,
        RADDIT_DISTRIBUTED_VECTOR_USED_FOR_V42=False,REPRODUCIBLE_SEMANTIC_PIPELINE_IMPLEMENTED=True,
        SEMANTIC_REPRESENTATION='SEM_COOCCUR32_V1',TEXT_SEMANTIC_CHANNEL_AVAILABLE=False,
        SEMANTIC_INTERFACE_READY=True,NEW_JOB_SEMANTIC_CALLABLE=read(ROOT/'NEW_JOB_CALLABILITY_TEST.json')['PASS'],
        RUNTIME_SEMANTIC_EXPERIMENT_RUN=True,RUNTIME_SEMANTIC_MODEL_SELECTED=semantic_runtime,
        SELECTED_RUNTIME_ARM=runtime['selected'] or 'NONE',CC4_SEMANTIC_EXPERIMENT_RUN=True,
        CC4_SEMANTIC_MODEL_SELECTED=semantic_cc4,SELECTED_CC4_ARM=cc4['selected'],
        RUNTIME_FUTURE_LEAKAGE_COUNT=0,CC4_FUTURE_LEAKAGE_COUNT=0,V42_SUBMISSION_INTERFACE_EXTENDED=True,
        V42_RUNTIME_USES_SEMANTICS=False,V42_CC4_USES_SEMANTICS=False,
        ENABLE_SUBMISSION_SEMANTICS_DEFAULT=False,APRIL_USED_FOR_SELECTION=False,MAY_PAYLOAD_OPENED=False,
        V42_OPTIMIZER_CHANGED=False,MESS_PHYSICS_CHANGED=False,OPENDSS_EXECUTED_FOR_SELECTION=False,
        RUNTIME_ALL_FROZEN_GATES_PASS=runtime['all_safety_gates_pass'],
        CC4_ALL_FROZEN_GATES_PASS=semantic_cc4,STAGE_C_RUN=False,APRIL_EVALUATED=False,
        HISTORICAL_SEMANTIC_FIELDS=['user','submit_line'],ARCHIVE_INGESTION_OR_REQUEST_VERSION_CERTIFIED=False,
        HISTORICAL_ANON_TO_REAL_FUTURE_IDENTITY_ALIGNMENT_PROVEN=False,
        RUNTIME_NEW_HAZARD_FITS=10,RUNTIME_BASELINE_REFITS=0,CC4_BASELINE_REFITS=0,
        CC4_NEW_QUANTILE_BOOSTERS=2*sum(cc4['exact_daily_refit_counts'].values()),
        HISTORICAL_SVD_FITS=6,HISTORICAL_KMEANS_FITS=1,SYNTHETIC_TEST_SVD_FITS=2,SYNTHETIC_TEST_KMEANS_FITS=1,
        FAILED_CC4_NATIVE_SVD_PREPARATION_ATTEMPTS=1,
        activation='Feature interfaces are implemented and tested; defaults remain legacy. No scheduler run or automatic promotion of an unbound model.',
        STATUS='SEMANTIC_INTERFACE_READY_MODELS_NOT_PROMOTED' if not (semantic_runtime or semantic_cc4) else 'RESEARCH_SELECTION_FROZEN_OPERATIONAL_ACTIVATION_PENDING_AUTHORITY')
    write('FINAL_VERDICT.json',verdict)
    write('FINAL_SELECTION_FREEZE.json',dict(time=now(),Runtime=runtime,CC4=cc4,
        interface_ready=True,feature_flag_default=False,operational_runtime_selected=semantic_runtime,
        operational_CC4_activation=False,private_RADDiT_required=False,
        artifact_hashes={n:sha(ROOT/n) for n in ['PREREGISTRATION.json','RUNTIME_MODEL_COMPARISON.csv','CC4_MODEL_COMPARISON.csv','SEMANTIC_FIELD_WHITELIST.json','FINAL_VERDICT.json']},
        no_reselection_using_April_or_May=True))
    parity=[read(LOCAL/f'runtime_fold{i}/SEMANTIC_FOLD_PARITY.json') for i in range(1,6)]
    write('SEMANTIC_ADAPTER_PARITY_AUDIT.json',dict(PASS=all(p['PASS'] for p in parity),folds=parity,
        synthetic_unit_receipt=rec(ROOT/'SEMANTIC_UNIT_TEST_RESULTS.json'),fresh_process_future_callability=rec(ROOT/'NEW_JOB_CALLABILITY_TEST.json'),
        shared_code='v42/semantic_adapter.py',historical_replay_bitwise=True,online_refit=False,
        actual_rows_checked_per_fold=dict(persisted_shuffled=64,direct_record=8),scope='Bitwise parity on recorded samples; same transformer implementation for all rows'))
    # Supplement the existing per-fold sharpness CSV using actual completed predictions.
    folds=pd.read_csv(ROOT/'RUNTIME_FOLD_METRICS.csv')
    cols=['arm','fold','reserved_GPUh','actual_GPUh','reservation_actual_GPUh','Q90_actual_ratio_median','Q90_actual_ratio_P90',
          'short_job_N','short_job_reserved_GPUh','short_job_actual_GPUh','short_job_reservation_inflation']
    sharp=folds[cols].copy()
    for idx,row in sharp.iterrows():
        folder=V13/'.local'/f'fold{int(row.fold)}' if row.arm=='R0' else LOCAL/f'runtime_fold{int(row.fold)}'
        name='EXPANDING_S4' if row.arm=='R0' else row.arm
        pred=pd.read_parquet(folder/(name+'.parquet'),columns=['requested_seconds','num_gpus_req'])
        w0=float((np.ceil(pred.requested_seconds/900)*pred.num_gpus_req*.25).sum())
        sharp.loc[idx,'reservation_to_W0']=row.reserved_GPUh/w0
    pooled=r.reset_index()[[x for x in cols if x!='fold']].copy();pooled['fold']='POOLED'
    pooled['reservation_to_W0']=r.reservation_to_W0.to_numpy();pd.concat([sharp,pooled],ignore_index=True).to_csv(ROOT/'RUNTIME_SHARPNESS_METRICS.csv',index=False)
    def cc(arm):
        out=[]
        for role in ['EXPOSED_EVALUATION','OOS_EXTENSION']:
            row=c[c.arm.eq(arm)&c.role.eq(role)&c.variant.eq('CALIBRATED')].iloc[0]
            raw=c[c.arm.eq(arm)&c.role.eq(role)&c.variant.eq('RAW')].iloc[0]
            out.append(f"{role}: calibrated hourly Q90 {pct(row.hourly_Q90_coverage)}, daily requirement coverage {pct(row.daily_Q90_coverage)}, pinball {row.Q90_pinball:.4f}, requirement ratio {row.requirement_ratio:.4f}, burst {pct(row.burst_coverage)}, WAPE {row.WAPE:.4f}; raw hourly Q90 {pct(raw.hourly_Q90_coverage)}.")
        return ' '.join(out)
    compared=[]
    for arm in ['R1','R2']:
        z=r.loc[arm];compared.append(f"{arm}−R0: min-fold {(z.min_fold_coverage-r.loc['R0','min_fold_coverage'])*100:+.2f}pp, >4h {(z.gt4h_coverage-r.loc['R0','gt4h_coverage'])*100:+.2f}pp, pinball {(z.Q90_pinball/r.loc['R0','Q90_pinball']-1)*100:+.2f}%")
    incremental=f"R2−R1: pinball {(r.loc['R2','Q90_pinball']/r.loc['R1','Q90_pinball']-1)*100:+.2f}%, min-fold {(r.loc['R2','min_fold_coverage']-r.loc['R1','min_fold_coverage'])*100:+.2f}pp."
    answers=[
        'V14R2 종료와 사용자 결정에 따라 비공개 exporter/stripping/vector 환경 복구를 재개하지 않았다. V6–V14R2는 해시로 보존했다.',
        'RADDiT의 제출 정보 활용 개념에서 영감을 받은 독립적인 submission-metadata latent representation이다. 배포 RADDiT embedding, private script 또는 Linq 모델을 사용하지 않았다.',
        f'원본 pre-April {rows:,}행을 조사했다. user/account/name/submit_line/script/job_type/workdir의 hash, partition/qos 및 array_pos/array_range가 있다. GPU {621583:,}행은 V13 원본 모집단과 정확히 일치한다.',
        'Hash 필드는 STABLE_ANON_IDENTITY, partition/qos/array metadata는 STRUCTURED_SEMANTIC이다. modules/conda_envs/reservation/dependency는 MISSING이다. 안정된 토큰 반복과 원래 의미의 보존은 다르며 7자리 hash collision 가능성도 남는다.',
        '사용 가능한 실제 free text는 없다. name/submit_line/script의 비결측 값은 익명 hash이므로 TEXT_SEMANTIC_CHANNEL_AVAILABLE=FALSE, R3는 NOT_APPLICABLE이다.',
        '새 historical whitelist는 제출자 user와 원래 제출 명령 submit_line이다. account/partition/qos/name 등의 최종 snapshot은 mutable하며 최초 버전이 미확인이고, custom script/job_type capture·derivation 시점도 입증되지 않아 새 semantic family에서 제외했다. 기존 R0는 원래 trace-proxy 한계를 그대로 유지한다.',
        'SubmissionRuntimeRequest에 optional semantic_payload, semantic_observed_at, semantic_feature_version을 추가했다. Payload는 10개 후보 개념을 표현할 수 있지만 현재 학습 whitelist는 2개다. Policy Arrival에는 raw 문자열 대신 NumericSemanticFeatures만 추가했고, 별도 adapter가 제출 경계에서 변환한다.',
        '새 adapter는 허용한 두 필드만 투영한다. runtime/start/end/final state/future queue의 교란은 새 semantic 특징을 바꾸지 않는다. Logical event-time 검증이며 archive ingestion latency나 mutable request의 최초 버전까지 인증한 것은 아니다.',
        'NFC·바깥 공백 정리 → field/namespace별 SHA256 pseudonym → 정렬·중복 제거한 field-prefixed token → FeatureHasher(262144,string,alternate_sign=False) → TRAIN-only TruncatedSVD(32,seed1401) → float32 sem_00..31이다. Linguistic embedding이 아니다.',
        '익명화 ID의 숫자는 의미나 순서를 보증하지 않는다. 전체 값을 하나의 범주로 처리하고 숫자 magnitude·ID 문자 ngram·인접 ID 유사도를 사용하지 않는다.',
        '예. Runtime은 각 기존 fold TRAIN에서만 SVD를 fit했다. CC4는 최초 DEVELOPMENT issue 전의 기존 TRAIN 날짜에 제출된 작업으로 한 번 fit하고 이후 transform-only다.',
        '예. user/submit_line 각각과 user-submit_line 조합의 TRAIN count/log1p/seen만 사용한다. VALID 빈도나 runtime target encoding은 없다.',
        '예. 5개 fold 각각에서 64개 행의 저장 후 로드·shuffled transform, 그중 8개 행의 direct·record 변환을 bitwise 확인했다. 전체 행이 같은 transformer 코드를 사용하지만 전수 replay 검사를 했다고 주장하지 않는다. 별도 fresh process에서도 미래 입력 변환을 검사했다.',
        '예. 알려진 범주, 새 user/command, 결측 optional, 새 account, Unicode 입력 5사례 × R1/R2 10개에서 finite 특징·Q50/Q90을 얻었다. 새 account는 현재 whitelist에서 제외되므로 수용하되 특징에는 사용하지 않는다. 이것은 연구 모델 호출성이고 운영 승인과 별개다.',
        '전달하지 않는다. Runtime request 경계의 payload만 원문을 일시 처리하고 policy Arrival은 숫자 타입만 허용한다. 기본 repr도 원문을 가린다.',
        '저장은 pseudonym 빈도·numeric vector·feature version·bundle digest로 제한한다. 미래 실제 값은 archive hash와 자동 정렬되지 않으므로 별도 namespace의 unseen으로 처리한다. SHA256은 작은 후보 공간의 역추측 방지까지 보장하지 않는다.',
        '정확한 V13 EXPANDING_S4 저장 예측과 해시를 재사용하고 pooled 주요 지표를 독립 재계산했다. R0 재학습은 0회다. '+describe_runtime(r.loc['R0']),
        describe_runtime(r.loc['R1']),describe_runtime(r.loc['R2']),
        '실행하지 않았다. 실제 free text가 없어 NOT_APPLICABLE이며 대형 LLM 다운로드는 0이다.',
        ' / '.join(f'{a}: {pct(r.loc[a,"Q90_coverage"])}' for a in r.index),
        ' / '.join(f'{a}: {pct(r.loc[a,"min_fold_coverage"])}' for a in r.index)+'; 고정 하한은 85%다.',
        ' / '.join(f'{a}: >4h {pct(r.loc[a,"gt4h_coverage"])}, >12h {pct(r.loc[a,"gt12h_coverage"])}, >24h {pct(r.loc[a,"gt24h_coverage"])}' for a in r.index),
        ' / '.join(f'{a}: Q90 pinball {r.loc[a,"Q90_pinball"]:.4f}, proper interval NLL {r.loc[a,"proper_interval_NLL"]:.4f}' for a in r.index)+'; V13의 동일 1초 event-interval likelihood와 censor score다.',
        ' / '.join(f'{a}: actual 대비 {r.loc[a,"reservation_actual_GPUh"]:.4f}, W0 대비 {r.loc[a,"reservation_to_W0"]:.4f}' for a in r.index)+'; short-job inflation과 Q90/runtime median/P90도 별도 CSV에 보존했다.',
        '; '.join(compared)+'. '+incremental+' 이는 predictive contribution 비교이며 causal effect가 아니다.',
        f'Fold별 결과를 모두 유지했다. 선택은 {runtime["selected"] or "NONE"}; 첫 fold를 포함한 전체 safety gate를 만족하지 않으면 pooled 개선으로 대체하지 않았다.',
        'NO. CC4는 미제출 미래 작업의 개별 semantic을 사용하지 않는다. issue와 같은 시각의 제출도 제외한다.',
        '1h/6h/24h/72h 과거 제출의 32D centroid·count·dispersion·recurrence와 두 centroid L2 변화를 사용한다. C2는 1h/6h/24h K=8 count/fraction/entropy 및 composition change를 추가한다. 미승인 account/script-family 비율은 만들지 않았다.',
        '예. Synthetic poisoned future payload와 실제 12개 무작위 issue-time의 미래 vector/recurrence/cluster 교란에서 특징이 같았다. 한 과거 작업의 user를 바꾸는 positive control도 확인했다. 별도 12개 issue에서는 저장 cluster 중심과 future-facing record 경로로 재구성한 201개 특징이 historical 상태와 bitwise 일치했다. 빈 window가 있으면 해당 지원 범위를 명시한다.',
        '사용자 지정 기존 T0/B0다. 타깃은 제출 시간대에 귀속한 요청 GPU 수 × 실제 runtime GPUh이며 24개 hourly 출력, 71개 기본 특징, 동결 LightGBM·일별 expanding refit·30일 가중치를 유지한다. '+cc('C0'),
        cc('C1'),cc('C2'),
        '각 arm의 raw/calibrated hourly Q90은 CC4_MODEL_COMPARISON.csv에 DEV/CAL/EXPOSED/OOS_EXTENSION으로 분리했다. '+cc(cc4['selected']),
        'Daily coverage는 24개 marginal hourly Q90 requirement 합의 coverage다. 이것을 별도로 적합한 joint daily 90% quantile이라고 부르지 않는다. 수치는 각 arm/period CSV에 있다.',
        'C0/C1/C2의 requirement/actual 비율을 raw와 calibrated 양쪽에서 비교했다. '+cc(cc4['selected']),
        f'기존 TRAIN positive target Q95={cc4["TRAIN_burst_threshold"]:.6f} GPUh를 사용했다. Validation으로 threshold를 고르지 않았고 각 arm/기간의 burst N과 coverage를 보존했다.',
        'Coverage 단독으로 선택하지 않았다. 고정 기준은 raw pinball paired CI, WAPE, raw/calibrated requirement 비율, calibrated nominal band 및 burst coverage를 함께 요구한다. 실패한 조건 전체는 CC4_SELECTION_FREEZE.json에 있다.',
        f'{semantic_runtime}. SELECTED_RUNTIME_ARM={runtime["selected"] or "NONE"}. 안전 gate 실패 arm을 provider로 승격하지 않았다.',
        f'{semantic_cc4}. SELECTED_CC4_ARM={cc4["selected"]}. DEVELOPMENT에서 후보를 고정한 뒤 독립 gate를 적용했고 평가 결과로 차선 arm을 다시 고르지 않았다.',
        '구현 경계는 D-1의 관측된 과거 semantic state와 D-day 실제 SUBMIT payload다. 기본 flag는 FALSE이며 운영 policy에 새 semantic 모델을 활성화하거나 optimizer를 실행하지 않았다.',
        'NO. D-1에는 submit_time < issue_time인 작업만 쓴다. 미제출 작업의 payload를 읽지 않는다.',
        '제출 시점 receipt가 있는 payload는 도착 handler에서 변환할 수 있다. 단, 모델의 실제 사용은 별도 선택·검증 gate를 통과해야 한다.',
        '제출 때 동결한 NumericSemanticFeatures와 bundle/version을 유지한다. End/runtime outcome으로 재계산하지 않으며 duplicate submit의 덮어쓰기를 거부한다.',
        'Semantic inference에는 refit이 없다. CC4의 기존 offline daily expanding 학습 cadence와 actual-arrival handler의 online refit은 다르다. 실제 도착 handler는 저장된 transformer만 사용한다.',
        'NO. PRIVATE_RADDIT_EXPORT_REQUIRED=FALSE. 추가 비공개 provenance 검색을 하지 않았다.',
        'NO. RADDIT_DISTRIBUTED_VECTOR_USED_FOR_V42=FALSE 및 PRIVATE_RADDIT_VECTOR_TRANSFORM_REQUIRED=FALSE다.',
        'NO. 모델 선택은 기존 pre-April 역할만 사용했다. CC4의 March26/27/28/31은 label이 April에 성숙하므로 동일 기준으로 양쪽 평가에서 제외했다. April target-day 배열이나 평가를 열지 않았다.',
        'NO. 원본 May archive member 및 CC4 May array rows를 디코딩하지 않았다. 전체 파일의 byte hash 검증과 payload row 해석을 구분했다.',
        '실제 완료된 기능은 backward-compatible payload/receipt, 공통 adapter, numeric arrival/cache, causal CC4 state 입력과 validation gate다. 기본 실행은 legacy이며 V42_RUNTIME_USES_SEMANTICS=FALSE, V42_CC4_USES_SEMANTICS=FALSE다. 연구 결과·호출 가능성·운영 활성화를 구분한다.'
    ]
    block=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig').split('FINAL_REVIEW_KO.md must answer:')[1].split('50. GIT / DELIVERY')[0]
    questions=re.findall(r'^\d+\. (.+)$',block,re.M);assert len(questions)==len(answers)==50
    table='| Runtime | pooled Q90 | min-fold | >4h | >12h | >24h | Q90 pinball |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for arm,z in r.iterrows():
        table+=f'| {arm} | {pct(z.Q90_coverage)} | {pct(z.min_fold_coverage)} | {pct(z.gt4h_coverage)} | {pct(z.gt12h_coverage)} | {pct(z.gt24h_coverage)} | {z.Q90_pinball:.4f} |\n'
    lead=f'# V42 / Runtime-vNext15 / CC4 최종 검토\n\n{verdict["STATUS"]}. Runtime 선택: {verdict["SELECTED_RUNTIME_ARM"]}, CC4 기준 유지/선택: {verdict["SELECTED_CC4_ARM"]}. 이 구현은 원래 RADDiT 배포 embedding이 아니다.\n\n'+table+'\n'
    lead+='이 실험의 새 정보는 user/submit_line 익명 범주의 recurrence와 co-occurrence다. 실제 application 설명·script 내용·workflow 의미를 평가한 실험은 아니다. 따라서 runtime의 본질적 무작위성, 예측 불가능성, semantic 정보의 무용성 또는 hidden-variable 원인을 증명하지 않는다. 다음 연구에서는 시점과 join이 입증된 workflow/application semantic information 및 external telemetry의 추가 가치를 별도 preregistered experiment로 평가해야 한다.\n\n'
    lead+='실행 수리: 기존 CC4 환경에서 첫 SVD 준비가 네이티브 접근 위반으로 종료되어 실패 로그와 Windows 이벤트를 보존했다. CC4 validation을 보기 전에, 같은 학습 코드·TRAIN membership·차원·seed로 Runtime에서 검증한 환경을 사용해 semantic 준비만 완료했다. CC4 LightGBM은 원래 환경을 유지했다. 완료한 historical SVD 6회와 실패한 준비 시도 1회를 구분한다.\n\n'
    md('FINAL_REVIEW_KO.md',lead+'\n\n'.join(f'## {i}. {q.strip()}\n\n{a}' for i,(q,a) in enumerate(zip(questions,answers),1)))
    md('README.md',f'''# V42 reproducible submission-semantic integration

Base: Runtime-vNext14R2 PR #88, `{BASE}`. 결과: `{verdict['STATUS']}`.

원본 Kestrel {rows:,}행을 감사하고 V13 GPU 621,583행의 source identity를 확인했다. 새 historical semantic whitelist는 user/submit_line 두 개다. Mutable 최종 snapshot과 시점이 미확인인 derived/custom field는 제외했다. 인터페이스는 10개 optional 개념을 지원하되 현 모델은 고정 whitelist만 쓴다.

공통 `v42/semantic_adapter.py`가 namespace-separated categorical token, FeatureHasher262144, TRAIN-only SVD32(seed1401), TRAIN recurrence를 제공한다. 과거·재생·새 입력의 코드는 동일하다. CC4는 사용자가 지정한 기존 T0/B0의 target·hourly resolution·LightGBM family를 유지하고 과거 1/6/24/72h semantic state와 KMeans8 composition만 추가했다.

Runtime 선택은 `{verdict['SELECTED_RUNTIME_ARM']}`, CC4는 `{verdict['SELECTED_CC4_ARM']}`다. 안전 조건·sharpness 기준을 낮추지 않았고 legacy feature flag 기본값은 FALSE다. 큰 모델/행별 예측은 `.local`에 유지하고 local manifest로 결속한다. 50개 답변은 FINAL_REVIEW_KO.md, 정확한 수치와 gate는 비교 CSV 및 selection freeze에 있다.

원본 RADDiT vector·private exporter·원본 암호화 좌표·대형 LLM은 필요하지 않다. April 선택·May payload 해석·optimizer physics 변경·OpenDSS selection은 없다. 본 결과는 제한된 제출 identity/co-occurrence 표현의 predictive contribution 실험이다.

재현은 prior namespace를 읽기 전용으로 보존하고 별도 출력 위치에서 수행한다. prepare15 → audit_fields15 → test_semantics15/test_integration15 → register15 → runtime15 순서다. 그 후 prepare_cc415와 cc415 register/prepare/run을 실행한다. Runtime 및 CC4 semantic prepare/replay는 V13 exact environment를, CC4 LightGBM run은 CC4_EXECUTION_ENVIRONMENT.json의 원래 NumPy1.26.4 환경을 쓴다. 환경 분리 이유와 실패 시도는 CC4_SEMANTIC_ENVIRONMENT_REPAIR.json에 있다. 중간에 code hash가 바뀌면 guard가 거부한다. 이미 끝난 모델을 재학습할 필요 없이 stored artifacts와 verify15로 재검증할 수 있다.

이 commit의 결과를 바꾸지 않는 전달 검증은 `python -B docs/runtime_vnext15_reproducible_semantic/verify15.py --check-delivery`다. 인자 없는 verify15는 과학적 지표를 다시 확인한 후 현재 파일의 manifest와 검증 receipt를 새로 쓴다. 전체 재학습에는 원본 archive와 선행 local evidence가 필요하며, `prepare15`는 정확한 base commit에서만 허용한다. 완료된 이 폴더에서 등록 파일을 덮어쓰거나 모델을 재학습하지 않는다.
''')
    md('PR_BODY.md',f'''원본 Kestrel 제출 정보를 동일 코드로 historical replay와 미래 V42 입력에서 변환하는 독립적인 semantic 경로를 추가했다. 비공개 RADDiT exporter/vector 복구와의 의존성을 제거하며 원래 RADDiT embedding을 사용했다고 주장하지 않는다.

원본 {rows:,}행 감사 후 최초 제출 값의 의미가 확인되는 user/submit_line identity만 historical whitelist에 포함했다. Mutable account/name/partition/qos snapshot과 custom script/job_type의 시점 미확인 필드는 제외했다. 10개 optional payload 개념, 기본 OFF flag, 숫자 전용 policy 경계 및 제출 vector 보존 cache를 구현했다.

- Runtime R0는 정확한 V13 S4 예측을 재사용하고 R1/R2만 5개 fold에서 평가했다. {describe_runtime(r.loc['R1'])} R2: {describe_runtime(r.loc['R2'])} 선택은 `{verdict['SELECTED_RUNTIME_ARM']}`다.
- CC4는 사용자 지정 T0/B0 hourly 제출 GPUh LightGBM을 유지하고 C1/C2 특징만 추가했다. 선택/유지는 `{verdict['SELECTED_CC4_ARM']}`이며 nominal coverage와 pinball·requirement·burst 기준을 함께 적용했다.
- TRAIN-only SVD/recurrence/KMeans, parity, future/past perturbation, 새 입력 호출성, legacy 호환성과 기존 증거 보존을 검증했다. April selection·May payload·optimizer/전력 모델 변경·OpenDSS 실행은 없다.

연구 interface 준비와 모델 승격은 별도다. 기본 실행은 legacy이고 운영 V42에 semantic 모델을 자동 활성화하지 않았다. 큰 모델/예측/logs는 .local에 보존하며 source/local/delivery manifests 및 한국어 50문항 최종 검토를 제공한다.
''')
    print('FINAL REPORTS WRITTEN',verdict['STATUS'],flush=True)
if __name__=='__main__':main()
