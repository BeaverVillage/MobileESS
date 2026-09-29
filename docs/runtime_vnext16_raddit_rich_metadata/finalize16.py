from common16 import *

def pct(x):return f'{100*float(x):.2f}%'
def main():
    v=read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json');runtime=read(ROOT/'RUNTIME_V16_SELECTION_FREEZE.json');cc4=read(ROOT/'CC4_RICH_SELECTION_FREEZE.json')
    assert not runtime['TOTAL_GATE_PASS'],'A successful TOTAL requires remaining/provider/April work before finalization'
    bridge_ran=runtime['status']=='COMPLETED'
    if v['deployable_bridge_authorized']:assert bridge_ran and runtime['new_deployable_arm_folds']==15
    cc4_ran=cc4['stage_run']
    if cc4_ran:assert read(ROOT/'CC4_RICH_CAUSALITY_AUDIT.json')['PASS']
    assert read(ROOT/'NATIVE_ADAPTER_REPLAY_AUDIT.json')['PASS']
    emb=read(ROOT/'RADDIT_EMBEDDING_DIAGNOSTIC_VERDICT.json');assert emb['status']=='COMPLETED'
    n=pd.read_csv(ROOT/'RADDIT_NATIVE_MODEL_COMPARISON.csv').set_index('arm')
    ef=pd.read_csv(ROOT/'RADDIT_EMBEDDING_MODEL_COMPARISON.csv').set_index('arm')
    cross=read(ROOT/'RADDIT_CROSSWALK_SUMMARY.json');a=pd.read_csv(ROOT/'RADDIT_GROUPED_ABLATION.csv')
    best=n.loc[['D1','D2','D3','D4']].sort_values('Q90_pinball').iloc[0];d0=n.loc['D0']
    flag=dict(FULL_RADDIT_SCHEMA_AUDITED=True,RADDIT_NATIVE_INFORMATION_VALUE_TESTED=True,
        RADDIT_RESEARCH_PROXY_CROSSWALK_USED=True,RADDIT_PRIVATE_EXPORTER_REQUIRED=False,RADDIT_PRIVATE_VECTOR_REQUIRED_FOR_PRODUCTION=False,
        RADDIT_DISTRIBUTED_VECTOR_DIAGNOSTIC_RUN=True,REAL_FREE_TEXT_AVAILABLE=False,MODULES_AVAILABLE=True,CONDA_ENVS_AVAILABLE=True,
        DEPLOYABLE_RICH_FIELDS=['user','submit_line'],DEPLOYABLE_RICH_FIELDS_SCOPE='Inherited immutable submission concepts; accepted receipt and namespace parity required. No newly promoted model.',
        RADDIT_NATIVE_INFORMATION_VALUE_SUPPORTED=v['native_information_success'],NATIVE_INFORMATION_VERDICT=v['conclusion'],
        NATIVE_SUPPORT_FLAG_SCOPE='Strict preregistered D1-D4 joint min-fold/tail criterion; not a claim that all metadata lacks information',
        NATIVE_PARTIAL_SOFTWARE_STACK_SIGNAL=bool(n.loc['SOFTWARE_STACK','ablation_trigger']),
        NATIVE_SIGNAL_AUTHORITY_SCOPE='Historical completed-export B-field association; original submission snapshot and production transfer unproven',
        CAUSAL_NEIGHBOR_FEATURES_IMPLEMENTED=True,RUNTIME_RICH_MODEL_SELECTED='NONE',RUNTIME_TOTAL_GATE_PASS=False,RUNTIME_PROVIDER_READY_FOR_V42=False,
        CC4_RICH_STAGE_RUN=cc4_ran,CC4_RICH_MODEL_SELECTED=cc4['selected'],APRIL_USED_FOR_SELECTION=False,MAY_PAYLOAD_OPENED=False,
        OPTIMIZER_CHANGED=False,MESS_CHANGED=False,OPENDSS_RUN=False,FLEXIBILITY_BRANCH_CHANGED=False,
        REMAINING_MODEL_RUN=False,STAGE_C_AUTHORIZED=False,APRIL_STATUS='NOT_RUN_GATE_FAILED',MAY_USED_FOR_SELECTION=False,MAY_USED_FOR_EVALUATION=False)
    write('FINAL_FLAGS.json',flag)
    native_table='| Arm | Pooled Q90 | Min-fold | >4h | >12h | >24h | Pinball (s) | Nodeh 예약/실제 |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for arm,r in n.iterrows():native_table+=f'| {arm} | {pct(r.Q90_coverage)} | {pct(r.min_fold_coverage)} | {pct(r.gt4h_coverage)} | {pct(r.gt12h_coverage)} | {pct(r.gt24h_coverage)} | {r.Q90_pinball:.2f} | {r.reservation_actual_nodeh:.3f} |\n'
    emb_table='| 동일 표본 진단 | Min-fold | >4h | >12h | Pinball (s) |\n|---|---:|---:|---:|---:|\n'
    for arm,r in ef.iterrows():emb_table+=f'| {arm} | {pct(r.min_fold_coverage)} | {pct(r.gt4h_coverage)} | {pct(r.gt12h_coverage)} | {r.Q90_pinball:.2f} |\n'
    ablation_text=('조건을 만족한 '+str(v['ablation_arm'])+'의 사전등록 그룹 제거 진단을 실행했다. '+', '.join(str(r.group)+': '+str(r.status) for r in a.itertuples())+
        '. 정보 그룹을 제거할 때 그 그룹을 사용하는 파생 채널도 제거했으므로 상호작용을 분리한 인과효과 추정은 아니다.') if v['ablation_authorized'] else '사전등록 material-win 조건을 충족한 arm이 없어 그룹 제거 학습은 NOT_RUN_NO_MATERIAL_WIN으로 기록했다. IDENTITY_ONLY와 SOFTWARE_STACK은 사전등록된 기본 정보 대비 실험이다.'
    ablation_text='전체 native D1–D4 범위: '+ablation_text
    pa=pd.read_csv(ROOT/'RADDIT_PAIRED_GROUPED_ABLATION.csv').set_index('group')
    stack=pd.read_csv(ROOT/'RADDIT_STACK_GROUPED_ABLATION.csv').set_index('group')
    ablation_text+=' 별도로 같은 매핑·TRAIN cap 표본의 EMB_D2가 >4h +5.29pp, pinball 약16.06% 개선으로 사용자 그룹 제거 조건을 만족해 A–E를 제거하는 후속 진단을 완료했다(F는 채널 없음). 원 사전등록의 primary ablation 범위를 넘는 조건부 진단 확장이며, paired 결과 확인 후 실행 동결을 공개했다. Primary 판정·Runtime 선택에 소급 적용하지 않는다.'
    paired_ablation_table='| 제거 그룹 | >4h | Pinball (s) |\n|---|---:|---:|\n'+''.join(f'| {g} | {pct(r.gt4h_coverage)} | {r.Q90_pinball:.2f} |\n' for g,r in pa.iterrows() if r.status=='COMPLETED')
    stack_ablation_table='| 제거 그룹 | 상태 | Min-fold | >4h | Pinball (s) |\n|---|---|---:|---:|---:|\n'+''.join(f'| {g} | {stack.loc[g,"status"]} | {pct(stack.loc[g,"min_fold_coverage"])} | {pct(stack.loc[g,"gt4h_coverage"])} | {stack.loc[g,"Q90_pinball"]:.2f} |\n' for g in ['A','E'])
    ablation_text+=f" 또한 사전등록 SOFTWARE_STACK 대비가 >4h {100*(n.loc['SOFTWARE_STACK','gt4h_coverage']-d0.gt4h_coverage):+.2f}pp와 pinball {100*(n.loc['SOFTWARE_STACK','Q90_pinball']/d0.Q90_pinball-1):+.2f}%로 사용자 조건을 만족해 별도 full-population 그룹 제거 진단을 완료했다. A는 실제 학습, E는 동일 설계행렬을 확인한 D0 재사용이며 B/C/D/F는 해당 채널이 없다. 이 역시 primary D1–D4 판정을 바꾸지 않는 공개된 조건부 진단 확장이다."
    rtab=pd.read_csv(ROOT/'RUNTIME_V16_MODEL_COMPARISON.csv')
    runtime_table='| Runtime arm | 상태 | Min-fold | >4h | Pinball (s) |\n|---|---|---:|---:|---:|\n'
    for r in rtab.itertuples():
        measured=pd.notna(r.Q90_pinball)
        runtime_table+=f'| {r.arm} | {r.status} | '+(f'{pct(r.min_fold_coverage)} | {pct(r.gt4h_coverage)} | {r.Q90_pinball:.2f}' if measured else '미실행 | 미실행 | 미실행')+' |\n'
    ans=[
    ('PR #89가 실제 추가한 필드는?', 'user와 submit_line의 익명 안정 ID이다. recurrence/co-occurrence/SVD32로 표현했다.'),
    ('왜 PR #89는 full RADDiT 실험이 아니었는가?', 'account, name/script/job_type, modules/conda, 공개 배포 벡터의 정보가치를 모두 평가하지 않았기 때문이다.'),
    ('historic_job_trace의 실제 필드는?', 'submit_time, start_time, end_time, nodes_req, processors_req, qos, wallclock_used_sec, avg_power_per_node, wallclock_req_sec, memory_req_raw, modules, conda_envs, user, name, account, partition, script, submit_line, job_type, job_id의 20개이다. 2,557,884행을 실제 감사했다.'),
    ('어떤 것이 익명 ID인가?', 'user/account/name/script/submit_line/job_type/partition 및 module/conda 토큰이다. 접미 숫자의 크기, 문자열 거리, 언어 임베딩 의미를 사용하지 않았다.'),
    ('실제 workflow/software-stack 정보는?', 'modules 225종과 conda 474종의 토큰 포함·반복 정보는 있다. 다만 익명 스택 정체성이고 실제 프로그램명·버전·스크립트 의미는 확인되지 않았다.'),
    ('어떤 것이 제출 시점에 관찰 가능한가?', '제출 이벤트와 요청 자원 및 일부 제출 메타데이터는 개념상 관찰 가능하다. 개념적 가능성과 이 아카이브의 초기값/수집 시점 증명은 별개이다. 각 source-field의 A/B/C를 authority CSV에 기록했다.'),
    ('미래 V42에서 무엇을 재현할 수 있는가?', '기존 user/submit_line 개념은 immutable accepted-submit receipt와 동일 namespace가 필요하다. 다른 rich field는 capture/version/namespace authority가 추가로 필요하다. 새 운영 모델을 승인하지 않았다.'),
    ('어떤 것은 diagnostic-only인가?', 'RADDiT rich metadata, software stack, 배포 좌표 및 초기값이 입증되지 않은 요청 snapshot이다. native 정보가치 시험의 B 정보가 운영 A 정보로 자동 승격되지 않는다.'),
    ('금지 필드는?', '실제 runtime/start/end, 실제 전력, 미래 queue/scheduler outcome이다. start/end는 인덱스·완료 자격·연결 감사에만, runtime은 label/엄격히 완료된 이웃 통계에만 사용했다. positional job_id는 예측변수가 아니다.'),
    ('연구용 proxy 연결률은?', f"Historic→Kestrel {cross['historic_to_Kestrel_status'].get('RESEARCH_PROXY_CROSSWALK',0):,}/2,557,884 ({pct(cross['historic_mapping_rate'])}). 두 단계 모두 유일한 embedding 연결은 1,504,846/1,780,972 ({pct(1504846/1780972)})이다. 운영 출처 증명은 아니다."),
    ('모호한 행은 몇 개인가?', 'Embedding→historic EKEY2에서 5,458행을 제외했다. 그 유일 후보 중 Kestrel 단계에서 270,668행이 추가로 모호했다. Historic 전체에서는 488,080행이 모호했다. 모호한 행을 임의 순서로 매칭하지 않았다.'),
    ('보류 필드 충돌은?', '비교 가능한 start_time/QoS 충돌은 0건이다. 첫 구현에서 서로 다른 partition namespace를 직접 비교한 오류를 수정했고 최초 결과·행 ledger를 보존했다. partition 대응표는 추정하지 않았으며 해당 필드는 NOT_COMPARABLE이다.'),
    ('rich metadata가 native Runtime을 개선하는가?', f"사전등록 판정은 {v['conclusion']}이다. D0–D4의 동일 세 expanding fold 지표는 위 표와 CSV에 고정했다. pooled 수치만으로 선택하지 않았다."),
    ('user/account identity는 도움이 되는가?', 'IDENTITY_ONLY는 user/account/name/script의 공동 대비이며 user/account 단독 효과를 입증하지 않는다. '+ablation_text),
    ('script/job identity는 도움이 되는가?', 'D1·IDENTITY_ONLY에 포함했으며 익명 script의 fold별 unseen 비율이 높다. 단독 원인의 증명으로 해석하지 않는다. '+('그룹 D 제거 결과도 별도 CSV에 기록했다.' if v['ablation_authorized'] else 'material-win 없는 자동 전수 ablation은 하지 않았다.')),
    ('modules/conda는 도움이 되는가?', f"SOFTWARE_STACK: min-fold {pct(n.loc['SOFTWARE_STACK','min_fold_coverage'])}, >4h {pct(n.loc['SOFTWARE_STACK','gt4h_coverage'])}, pinball {n.loc['SOFTWARE_STACK','Q90_pinball']:.2f}s. D1→D2와 함께 평가해야 하며 실제 소프트웨어 의미 복원의 증거는 아니다."),
    ('요청 자원은 도움이 되는가?', f"D0: min-fold {pct(d0.min_fold_coverage)}, >4h {pct(d0.gt4h_coverage)}, pinball {d0.Q90_pinball:.2f}s. 이 기준 대비 추가 정보의 효과를 측정했다. 초기 requested-walltime version의 운영 권한을 새로 인정한 것은 아니다."),
    ('완료 이웃은 도움이 되는가?', f"D4: min-fold {pct(n.loc['D4','min_fold_coverage'])}, >4h {pct(n.loc['D4','gt4h_coverage'])}, pinball {n.loc['D4','Q90_pinball']:.2f}s. D2에 추가한 k16/64 완료 이웃 통계의 대비이다. 제한 후보 집합에서의 결정적 검색이며 전역 완전 탐색은 아니다."),
    ('개선이 시간에 걸쳐 안정적인가?', '사전등록된 consistent_temporal_gain은 3개 중 2개 이상 fold에서 >4h와 pinball이 모두 개선되고 어느 fold도 >4h가 5pp 넘게 악화되지 않는 조건이다. 해당 여부: '+', '.join(arm+'='+str(n.loc[arm,'consistent_temporal_gain']) for arm in ['D1','D2','D3','D4'])),
    ('>4h 개선은?', f"D0 {pct(d0.gt4h_coverage)}; 가장 낮은 pinball의 rich arm {best.name} {pct(best.gt4h_coverage)}. 모든 arm을 공개했다."),
    ('>12h 개선은?', f"D0 {pct(d0.gt12h_coverage)}; {best.name} {pct(best.gt12h_coverage)}."),
    ('>24h 개선은?', f"D0 {pct(d0.gt24h_coverage)}; {best.name} {pct(best.gt24h_coverage)}. 지원 표본수는 tail CSV에 있다."),
    ('pinball은?', f"D0 {d0.Q90_pinball:.2f}s; {best.name} {best.Q90_pinball:.2f}s, 상대 변화 {100*(best.Q90_pinball/d0.Q90_pinball-1):+.2f}%. 이 순위는 보고용이며 배포 선택이 아니다."),
    ('예약 비율은?', f"Nodeh 예약/실제: D0 {d0.reservation_actual_nodeh:.3f}, {best.name} {best.reservation_actual_nodeh:.3f}. GPU량을 제공하지 않는 native에 GPUh를 만들어 넣지 않았다. short-job 비율과 requested-walltime 대비 비율도 공개했다."),
    ('randomized identity 대조군은?', 'user/account/script를 안정적인 무작위 ID로 일대일 치환해 전체 TRAIN/VALID 설계행렬이 정확히 같음을 확인했다. 같은 고정 모델 예측도 같다. 이는 이름 불변성 대조군이며 identity 정보를 제거하는 귀무 대조군이 아니다. 별도의 TRAIN 일별 공동 셔플 NEG_SHUFFLE은 실제로 재학습했다.'),
    ('target encoding에 미래 정답이 들어갔는가?', '아니다. 범주·토큰·recurrence는 label-free TRAIN fit이다. 이웃 target 통계는 엄격한 완료 시간 제한을 적용했다. VALID 정답과 이전 VALID 작업의 정답도 풀에 넣지 않았다.'),
    ('완료된 과거 이웃만 썼는가?', '그렇다. 모든 선택 이웃 ID의 strict end<submit을 검사했고 위반은 0건이다. end==submit 및 미완료 후보 강제 주입, 미래 poison, fresh-process 재생 검사를 수행했다.'),
    ('공개 배포 embedding의 진단 가치는?', f"동일 매핑·표본의 EMB_D0 min {pct(ef.loc['EMB_D0','min_fold_coverage'])}, >4h {pct(ef.loc['EMB_D0','gt4h_coverage'])}, pinball {ef.loc['EMB_D0','Q90_pinball']:.2f}s; 배포 좌표 모델 min {pct(ef.loc['D_EMB_DIAGNOSTIC_ONLY','min_fold_coverage'])}, >4h {pct(ef.loc['D_EMB_DIAGNOSTIC_ONLY','gt4h_coverage'])}, pinball {ef.loc['D_EMB_DIAGNOSTIC_ONLY','Q90_pinball']:.2f}s. TRAIN 10만 cap·고정 LightGBM·완료 export 표본의 범위이며 모든 잠재 표현에 대한 부정적 증명이 아니다."),
    ('그 벡터를 미래 V42 작업에 생성할 수 있는가?', '입증되지 않았다. 저장된 4,096차원 좌표만 직접 읽었고 private inverse transform이나 새 LLM은 사용하지 않았다. 운영 선택 금지이다.'),
    ('배포 필터 뒤에 무엇이 남는가?', '새 권한이 입증된 rich field는 없다. 기존 user/submit_line 개념만 receipt·namespace 조건부로 남고, modules/conda는 원본 Kestrel에 없다. Native 유일 매핑 행은 기존 GPU Runtime VALID 5개 fold와 교집합 0건이다.'),
    ('배포 모델에도 native 개선이 남는가?', '미평가이다. '+runtime['status']+'. 실행하지 않은 challenger를 실패 측정값이나 0으로 채우지 않았다.'),
    ('CatBoost가 동일 정보 V13 hazard보다 좋은가?', '비교하지 않았다. CatBoost가 동결 환경에 없어 허용된 TRAIN-only categorical LightGBM을 사용했다. gated bridge의 H1/H2를 실행하지 않았으므로 같은 정보의 모델 계열 우위를 주장하지 않는다.'),
    ('모델 개선인가 정보 개선인가?', 'D0–D4는 같은 LightGBM family·seed·hyperparameter·fold를 쓰므로 이 범위의 정보 대비이다. V13 hazard와의 architecture superiority는 별도 미평가이다.'),
    ('R0 baseline은 유지됐는가?', '그렇다. exact V13 EXPANDING_S4의 저장된 예측을 독립 재집계했다. pooled 91.84%, min-fold 70.70%, >4h 69.72%, >12h 64.25%, >24h 46.88%, pinball 4,752.7617s이다.'),
    ('결과 후 gate를 바꿨는가?', '성공·STOP·Runtime 안전 threshold, 모델 family·표현·fold·seed는 바꾸지 않았다. 다만 제가 추가했던 회색 구간 자동 중단은 원문의 명시한 STOP에서만 중단하라는 지시와 달라, 일부 native 결과 이후 전체 STOP이 아니면 고정 bridge 평가를 계속하도록 실행 경로를 정정했다. EXECUTION_ROUTING_CORRECTION.json에 시점과 당시 보인 결과를 공개했고 원 사전등록도 보존했다. partition namespace 연결 오류 수정은 ML 전에 이루어졌다.'),
    ('Runtime min-fold 85%를 통과했는가?', '아니다. 기존 R0는 70.70%; 새 R16 challenger는 미실행이다. Native 별도 모집단의 수치를 Runtime gate에 대입하지 않았다.'),
    ('Runtime >4h 85%를 통과했는가?', '아니다. 기존 R0 69.72%; 새 challenger 미실행.'),
    ('Runtime >12h 80%를 통과했는가?', '아니다. 기존 R0 64.25%; 새 challenger 미실행.'),
    ('Runtime >24h 70%를 통과했는가?', '아니다. 기존 R0 46.88%; 새 challenger 미실행.'),
    ('미래 작업에 provider를 호출할 수 있는가?', '새 V16 운영 provider는 승인·구현·실행하지 않았다. 연구용 adapter의 unseen 처리·저장 모델 재생 검사는 운영 권한이나 원본 namespace 재현 증명이 아니다.'),
    ('raw string이 optimizer 로그에 들어갔는가?', '아니다. optimizer를 실행하지 않았다. V2 명세는 허용된 pseudonym·숫자·bundle digest·Q50/Q90만 optimizer 경계에 전달하도록 제한한다.'),
    ('online refit이 필요한가?', '연구용 고정 adapter/model 재생에는 필요 없다. 새 운영 provider가 준비됐다는 뜻은 아니다.'),
    ('remaining-runtime을 조기에 실행했는가?', '아니다. NOT_RUN_TOTAL_GATE_FAILURE이다.'),
    ('CC4는 선행 증거에 의해 gate됐는가?', '그렇다. '+cc4['status']+'. Native/Runtme gate가 열리지 않은 상태에서 C3/C4를 학습하지 않았다.'),
    ('CC4가 미래 미제출 semantics를 봤는가?', '아니다. CC4 rich 단계는 미실행이고 기존 evidence를 보존했다.'),
    ('C0는 T0/B0인가?', '그렇다. hourly submitted-GPUh LightGBM T0/B0를 유지했다. T2_F0/T3_F2는 연구 후보 상태이며 승격하지 않았다.'),
    ('April을 선택에 썼는가?', '아니다. 별도 April 평가도 미실행이다. 다만 3월 원본 파일의 UTC 4월 경계 10,760행은 경계 검사에서 읽힌 뒤 즉시 제외됐다. 이를 April payload를 전혀 읽지 않았다고 표현하지 않는다.'),
    ('May를 열었는가?', '2025년 May holdout을 열지 않았다. 2024년 May는 기존 과거 TRAIN 기간으로 별개의 데이터이다.'),
    ('optimizer/MESS/OpenDSS를 변경했는가?', '아니다. V42 기존 파일·flexibility branch·optimizer·MESS를 변경하지 않았고 OpenDSS를 실행하지 않았다.'),
    ('정당화되는 최종 과학적 결론은?', f"{v['conclusion']}. 이번에 관측한 익명 rich metadata와 고정 모델 실험은 native 정보가치, 미래 제출 재현성, GPU Runtime 안전성의 세 질문을 구분한다. 새 Runtime provider 승격 근거는 없다. Runtime의 본질적 무작위성·예측 불가능성·current-state 무용성·hidden-variable 원인은 증명되지 않았다. 다음 연구는 실제 workflow/application 의미와 정확히 job-level join 가능한 external telemetry, 초기 제출 receipt를 별도 사전등록 실험으로 검증해야 한다.")]
    assert len(ans)==50
    ans[13]=(ans[13][0],ans[13][1]+f" Paired EMB_D2에서 user/account 그룹 C 제거: >4h {pct(pa.loc['C','gt4h_coverage'])}, pinball {pa.loc['C','Q90_pinball']:.2f}s.")
    ans[14]=(ans[14][0],ans[14][1]+f" Paired 그룹 D 제거: >4h {pct(pa.loc['D','gt4h_coverage'])}, pinball {pa.loc['D','Q90_pinball']:.2f}s.")
    ans[15]=(ans[15][0],ans[15][1]+f" Paired 그룹 E 제거: >4h {pct(pa.loc['E','gt4h_coverage'])}, pinball {pa.loc['E','Q90_pinball']:.2f}s.")
    ans[15]=(ans[15][0],ans[15][1]+f" 전체 native SOFTWARE_STACK에서 자원 A 제거: min-fold {pct(stack.loc['A','min_fold_coverage'])}, >4h {pct(stack.loc['A','gt4h_coverage'])}, pinball {stack.loc['A','Q90_pinball']:.2f}s. Stack E 제거는 정확히 D0이다. Stack 대비의 min-fold 개선은 {100*(n.loc['SOFTWARE_STACK','min_fold_coverage']-d0.min_fold_coverage):+.2f}pp로, 엄격한 +5pp 동시 개선 기준에는 미달한다. 이 신호는 workflow 의미를 복원하거나 미래 제출에서 같은 토큰을 확보했다는 증거가 아니다.")
    ans[49]=(ans[49][0],ans[49][1]+f" 특히 native SOFTWARE_STACK은 >4h {pct(d0.gt4h_coverage)}→{pct(n.loc['SOFTWARE_STACK','gt4h_coverage'])}의 부분적 정보가치를 보였으므로 정보가 전혀 없다고 결론내릴 수 없다. 다만 min-fold 동시 개선과 source authority, GPU 모집단 전이를 함께 확립하지 못했다.")
    if not cc4_ran:
        ans[43]=(ans[43][0],'Runtime 평가·선택을 먼저 동결한 뒤 CC4 선행 information-value 조건이 충족되지 않아 C3/C4를 실행하지 않았다. '+cc4['status']+'. C0는 유지했다.')
    if bridge_ran:
        ans[30]=(ans[30][0],'원래와 동일한 GPU Runtime 5개 fold에서 R16-A/B/C를 실행했다. 전체 gate를 통과한 모델은 없다. Native 모집단의 개선을 직접 옮기지 않고 기존 receipt/namespace 계약의 user/submit_line만 추가했다. PR #89 이후 새로운 원본 정보축을 확보한 것이 아니라 기존 두 개념을 다른 고정 표현으로 평가했다. 위 Runtime 표와 각 fold CSV가 실제 결과이다.')
        ans[31]=(ans[31][0],'CatBoost는 평가하지 않았다. 허용된 LightGBM direct quantile을 동일 입력의 V13 hazard와 비교했다. Direct quantile은 exact label TRAIN subset, hazard는 censoring likelihood도 사용하므로 순수 architecture 우위로 해석할 수 없다. H0=R0, H1=R16-A; H2는 modules/conda 권한 부재로 미실행이다.')
        ans[32]=(ans[32][0],'Native D0–D4는 같은 family의 정보 대비이다. GPU bridge에서는 H0→H1이 동일 hazard family의 user/submit_line 정보 대비이고 R16-C는 완료 이웃 추가 대비이다. R16-B는 architecture와 censoring 처리도 달라 단독으로 순수 정보 효과나 CatBoost 우위를 주장하지 않는다.')
        for position,column,gate in [(35,'min_fold_coverage','gate_B'),(36,'gt4h_coverage','gate_C'),(37,'gt12h_coverage','gate_D'),(38,'gt24h_coverage','gate_E')]:
            ans[position]=(ans[position][0],'; '.join(f'{r.arm}: {pct(getattr(r,column))}, 해당 gate={getattr(r,gate)}' for r in rtab.itertuples() if r.arm=='R0' or r.arm.startswith('R16'))+'. 개별 gate와 전체 TOTAL 승인은 별개이다.')
        ans[39]=(ans[39][0],'저장한 연구 모델과 receipt adapter의 재생·미지 ID 처리·시간/필드 거부를 검증했다. 실제 V42 운영 provider는 TOTAL 실패로 통합·승격하지 않았다. Operational namespace/capture service가 검증됐다는 주장도 하지 않는다.')
    if cc4_ran:
        ans[43]=(ans[43][0],'Runtime 결과를 먼저 동결하고 CC4_RICH_AUTHORIZATION.json의 조건을 확인한 후 실행했다. 최종 선택은 '+cc4['selected']+'이며 기존 frozen 평가 계약을 유지했다.')
        ans[44]=(ans[44][0],'아니다. 모든 issue에서 submit_time<t0인 과거 데이터만 사용했고 future-poison 및 재생 검사를 CC4_RICH_CAUSALITY_AUDIT.json에 기록했다.')
    stage_text=('R16-A/B/C의 exact 5-fold 평가를 완료했고 TOTAL 통과 모델은 없다. H1은 R16-A로 평가했다. ' if bridge_ran else runtime['status']+': R16-A/B/C, H1은 미실행이다. ')
    stage_text+='H2는 modules/conda 권한 부재로 미실행이다. Stage C/provider, remaining, April은 TOTAL 실패로 미실행이며 May는 unopened다. '+('CC4 rich 단계는 실행 후 '+cc4['selected']+'를 선택했다.' if cc4_ran else 'CC4 rich 단계는 조건 미충족으로 미실행이며 C0를 유지했다.')
    review='# Runtime-vNext16 최종 검토\n\n'+f"판정: **{v['conclusion']}**. 운영 Runtime 선택: **NONE**. CC4: **{cc4['selected']}**, rich 단계 **{'실행' if cc4_ran else '미실행'}**.\n\n"
    review+='## 확정된 native 결과\n\n'+native_table+'\n모집단은 RADDiT historic의 완료 export 작업이다. 유일하게 매핑된 행과 기존 GPU Runtime 검증 fold의 교집합은 0건이며, 미매핑 행까지 모두 CPU 전용이라고 증명한 것은 아니다. Nodeh와 GPUh를 혼동하지 않는다. 초기 제출 시점의 metadata snapshot이 입증되지 않은 B 필드의 역사적 예측 연관성이므로, 관측된 개선을 실제 제출 경계의 인과적 효용으로 단정하지 않는다.\n\n'
    review+='## 공개 embedding의 별도 진단\n\n'+emb_table+'\n두 단계 모두 유일한 연구용 매핑만 사용했고 각 fold TRAIN을 동일한 10만 행으로 제한했다. 전체 4,096차원 좌표를 사용했다. 원본 표본의 D0–D4 수치와 직접 비교하지 않는다.\n\n'
    review+='## 조건부 진단과 Runtime 단계\n\n'+ablation_text+'\n\n동일 매핑·TRAIN cap 표본의 EMB_D2 그룹 제거:\n\n'+paired_ablation_table+'\n전체 native SOFTWARE_STACK 그룹 제거:\n\n'+stack_ablation_table+'\n기존 GPU Runtime 5-fold 비교:\n\n'+runtime_table+'\n'+stage_text+' 미실행 지표는 빈 값이며 0·PASS·추정값으로 채우지 않았다.\n\n'
    review+='## 보존과 해석 한계\n\nV6–V15의 1,548개 tracked 파일, 531개 이전 local evidence, 원본 23,601개 크기/mtime fingerprint를 보존 대상으로 유지했다. 최종 재검증 결과는 VERIFICATION.json에 있다. 최초 경계 assertion과 잘못된 namespace 검사 결과도 삭제하지 않았다.\n\n'
    review+='\n\n'.join(f'### {i}. {q}\n\n{answer}' for i,(q,answer) in enumerate(ans,1))
    md('FINAL_REVIEW_KO.md',review)
    md('README.md','# Runtime-vNext16 rich RADDiT information-value study\n\nBase: PR #89, commit `'+BASE+'`.\n\n'+
        'Native information value, future submission reproducibility and Runtime safety are separate conclusions. Read FINAL_REVIEW_KO.md for all 50 requested questions and exact scope.\n\n'+
        native_table+'\nStudy order: source audits → corrected exact research-proxy crosswalk → preregistration SHA freeze → three native expanding folds D0–D4 and fixed information/control contrasts → matched-cohort public embedding diagnostic → triggered ablation → information freeze → gated Runtime/CC4 decision → verification.\n\n'+
        'Runtime: '+runtime['status']+'. The exact V13 R0 baseline remains unchanged. CC4 baseline remains T0/B0; selected='+cc4['selected']+'.\n\n'+
        'Reproduction requires the supplied original archive, public RADDiT files and existing SHA-bound V6–V15 local evidence in the exact recorded environment. Large matrices, selected-neighbor IDs, models, row predictions and logs are under ignored .local and bound by LOCAL_EVIDENCE_MANIFEST.json. A fresh BASE checkout is required by prepare16.py; it must not be rerun to overwrite a completed study. register16.py refuses registration after metrics. train_native16.py and embedding16.py check the frozen implementation hashes. Use collect_native16.py only after all folds finish, then authorized ablation/bridge stages. No validation-driven parameter tuning is performed.\n\n'+
        'Limitations: anonymized identity is not language semantics; unresolved exporter/timezone lineage; original initial mutable-request versions unproven; bounded candidate neighbor retrieval; uniquely mapped native rows do not overlap the existing GPU VALID folds (unmapped rows are not certified CPU-only); embedding TRAIN cap100000 with all4096 stored coordinates and no future-generation contract.\n')
    md('PR_BODY.md','## 문제와 결과\n\nPR #89가 평가한 user/submit_line 정보만으로 full RADDiT의 정보가치를 판단할 수 없었다. 실제 20개 필드·2,557,884행을 감사하고, native D0–D4와 identity/software-stack 대비, 완료 이웃, 대조군, 동일 매핑 표본의 공개 4,096차원 좌표를 평가했다. 기준은 PR #89 commit `'+BASE+'`이다.\n\n'+
        f"Native 판정: **{v['conclusion']}**. Primary 최저 pinball {best.name}: min-fold {pct(best.min_fold_coverage)}, >4h {pct(best.gt4h_coverage)}, pinball {best.Q90_pinball:.2f}s. Software-stack 대비는 >4h {pct(d0.gt4h_coverage)}→{pct(n.loc['SOFTWARE_STACK','gt4h_coverage'])}의 부분적 신호를 보였으나 엄격한 min-fold 동시 개선 조건은 통과하지 못했다.\n\n"+
        stage_text+' C0는 frozen T0/B0이며 T2_F0/T3_F2는 연구 후보로 유지했다.\n\n'+runtime_table+
        '\n## 과학적 해석과 공개된 정정\n\n정보가치, 미래 제출 재현성, Runtime 안전성을 별도로 판정한다. Native 유일 매핑 작업은 기존 GPU VALID 5개 fold와 교집합이 없다. Modules/conda는 원본 Kestrel 제출 데이터에 없어 운영 입력으로 승격하지 않았다. user/submit_line도 기존 receipt·namespace 계약을 조건으로 하는 연구 입력이다.\n\n'+
        '원 사전등록에 추가됐던 회색 구간 자동 중단은 사용자 원문의 명시한 STOP에서만 중단하라는 지시와 달라, 일부 native 결과 이후 실행 경로를 정정했다. 전체 native 판정·bridge 학습 전에 기록했으며 원 사전등록 bytes, 모델·fold·성공/STOP·안전 threshold를 보존했다. 모든 실행이 무수정 사전등록이었다고 주장하지 않는다.\n\n'+
        ablation_text+'\n\n'+
        '유일 연구용 연결은 historic 2,069,804행, embedding 1,504,846행이고 비교 가능한 holdout 충돌은 0건이다. 서로 다른 partition namespace를 직접 비교했던 최초 오류 결과도 보존했다. 3월 파일에서 읽힌 UTC 4월 경계 10,760행은 feature/selection 전에 제외했으며, 이를 April 바이트를 전혀 읽지 않았다고 표현하지 않는다. May 2025 payload는 열지 않았다.\n\n'+
        '## 검증 및 보존\n\n집중 테스트, 모든 선택 이웃의 strict 완료 시간 검사, 새 프로세스 모델·이웃 재생, 저장 예측의 지표/gate 재계산, exact R0/PR89 재집계, V6–V15 기존 hash와 원본 fingerprint 검증을 수행했다. 정확한 건수와 최종 PASS는 VERIFICATION.json에 있다. 대용량 모델·행 예측·로그는 `.local`에 보존하고 SHA256 manifest로 연결했다.\n\n'+
        '변경은 새 연구 디렉터리로 제한했다. 기존 V42/optimizer/MESS/flexibility를 수정하지 않았고 OpenDSS를 실행하지 않았다. FINAL_REVIEW_KO.md에 요청한 50개 질문을 모두 답했다.\n')
    print('FINAL_DOCUMENTS',v['conclusion'],flush=True)

if __name__=='__main__':main()
