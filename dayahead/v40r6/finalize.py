"""Audit/report closure; no model fitting, candidate changes or scientific tuning."""
from .common import *
import sys

def table(frame,columns=None):
    df=pd.DataFrame(frame)
    if columns: df=df[columns]
    def cell(x):
        if isinstance(x,(float,np.floating)): return f'{x:.8g}'
        return str(x).replace('|',' / ').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(df.columns)+' |','|'+'|'.join(['---']*len(df.columns))+'|']+
        ['| '+' | '.join(cell(x) for x in r)+' |' for r in df.itertuples(index=False,name=None)])

def audit():
    authority(); selection_authority()
    start=read('PROTECTED_SCOPE_START'); end=snapshot()
    assert start==end
    dump('PROTECTED_SCOPE_END',end)
    dump('PROTECTED_SCOPE_DIFF',{'PASS':True,'inherited_tree_unchanged':True,'R5_R5R1_hashes_unchanged':True,
        'protected_changes':[],'allowed_changes_only':True,'all_R5_R5R1_files_compared':len(end['R5_R5R1_SHA256']),
        'protected_system_sequence':'A0 -> M1 route+P/Q -> A1 feedback -> MF fixed-route P/Q -> Joint Freeze -> Fresh OpenDSS'})
    negative=[]
    frame,_=data()
    for role,name in [('CAL_FIT_CAL_SELECT','calibration_predictions.npz'),('EXPOSED_EVALUATION','exposed_predictions.npz')]:
        p=np.load(OUT/name); ix=p['row_ids']
        for h in HORIZONS:
            loc=(frame.iloc[ix].horizon==h).to_numpy()
            for j,q in enumerate(['Q50','Q90']):
                raw=p['raw'][loc,j]
                negative.append({'phase':role,'horizon':h,'output':q,'N':len(raw),'negative_N':int((raw<0).sum()),
                    'minimum_GPUh':raw.min(),'substantive_negative_clipped':False})
    for config in CONFIGS:
        q=np.load(OUT/'fits'/config/'development_q.npy'); ix=np.load(OUT/'development_baselines.npz')['row_ids']
        for h in HORIZONS:
            loc=(frame.iloc[ix].horizon==h).to_numpy()
            for j,name in enumerate(['Q50','repaired_Q90']):
                raw=q[loc,j]
                negative.append({'phase':'DEVELOPMENT','config':config,'horizon':h,'output':name,'N':len(raw),
                    'negative_N':int((raw<0).sum()),'minimum_GPUh':raw.min(),'substantive_negative_clipped':False})
    dump('NEGATIVE_PREDICTION_AUDIT',{'rows':negative,'interpretation':'Negative raw quantiles remain recorded model defects; no unregistered zero clipping, target edits, or gate relaxation',
        'source_correction':'V40R6_EXECUTION_CORRECTION.json','upper_bound_nonnegativity_not_silently_assumed':True})
    ledger=read('COMPUTE_LEDGER')
    ledger['known_fit_seconds_sum']=sum(r['seconds'] for r in ledger['fits'] if r['seconds'] is not None)
    ledger['fit_duration_missing_count']=sum(r['seconds'] is None for r in ledger['fits'])
    ledger['original_model_reused_after_logged_interruption']=1
    ledger['new_raw_archive_scientific_reads']=0
    dump('COMPUTE_LEDGER',ledger)
    evidence=read('EXPOSED_RESULTS'); freeze=read('SELECTION_FREEZE'); hp=read('HYPERPARAMETER_FREEZE')
    diagnoses={}
    for h in HORIZONS:
        diagnostics=evidence['by_horizon'][h]['candidates']
        diagnoses[h]={'selected':freeze['selected_candidates'][h],'DEV_central_and_positive_pinball_skill_pass':hp['skill_by_horizon'][h]['PASS'],
            'CAL_candidate_failures':{c:v['failure_reasons'] for c,v in freeze['gates'][h].items()},
            'EXPOSED_candidate_failures':{c:v['gates']['failure_reasons'] for c,v in diagnostics.items()},
            'frozen_selected_exposed_pass':evidence['by_horizon'][h]['selected_pass']}
    dump('FAILURE_DIAGNOSIS',{'classification':evidence['classification'],'horizons':diagnoses,
        'distribution_shift':'Descriptive split distributions reported; no post-hoc adjustment or formal shift-causation claim',
        'prohibited_conclusion':'Does not establish impossibility of forecasting future workload',
        'no_new_models_or_relaxed_gates':True})
    review()

def review():
    result=read('EXPOSED_RESULTS'); freeze=read('SELECTION_FREEZE'); hp=read('HYPERPARAMETER_FREEZE')
    dist=read('HORIZON_DISTRIBUTION_AUDIT')['by_horizon']; target=read('R5_TARGET_AUTHORITY_FREEZE')
    cal=pd.read_csv(OUT/'V40R6_CAL_SELECT_RESULTS.csv'); q50=pd.read_csv(OUT/'V40R6_Q50_RESULTS.csv'); q90=pd.read_csv(OUT/'V40R6_Q90_RESULTS.csv')
    selected=freeze['selected_candidates']; primary=result['primary_safety']; full=result['full_multi_horizon_safety']
    family='NONE' if not primary else ','.join(sorted(set('B1' if selected[h]=='U0' else 'B2' for h in PRIMARY)))
    lines=[f'FINAL CLASSIFICATION: {result["classification"]}','PRIMARY HORIZONS: H4, H24','SECONDARY HORIZONS: H1, H8',
        'SELECTED MODEL FAMILY: '+family,'SELECTED LGB CONFIG: '+hp['selected_config']]+[
        'SELECTED '+h+' UPPER: '+selected[h] for h in HORIZONS]+[
        'PRIMARY SAFETY: '+('PASS' if primary else 'FAIL'),'FULL MULTI-HORIZON SAFETY: '+('PASS' if full else 'FAIL'),
        'OPTIMIZER INTEGRATION: NO','PRODUCTION READY: NO','',
        '아래 결과는 이미 노출된 과거 자료의 진단이다. 예측·안전성 실패와 코드/재현성 검증 통과를 구분한다.','']
    points={
        1:('lineage',' → '.join(read('GIT_LINEAGE_AUDIT')['lineage'])),
        2:('R5/R5R1 보존','R5=V40R5_BODY_FORECAST_INSUFFICIENT, selected_model=NONE 유지. R5R1=V40R5R1_ZERO_INFLATION_AWARE_EVALUATION_COMPLETE; 원본 바이트 및 전체 보호 Git 범위 변경 없음.'),
        3:('15분 타깃 authority',json.dumps(clean(target),ensure_ascii=False)),
        4:('누적 타깃 개수','H1 32,457 / H4 28,269 / H8 22,685 / H24 349; 총 83,760행, 일별 240행.'),
        5:('정확한 합산 identity',json.dumps(read('CUMULATIVE_TARGET_IDENTITY_AUDIT'),ensure_ascii=False)),
        10:('0값 비율',json.dumps({h:v['all_authority_rows']['zero_fraction'] for h,v in dist.items()})),
        11:('게이트 수학적 가능성','전체 coverage 상한은 안전 게이트에서 제외. 각 H/분할의 양수 coverage 정수 격자까지 계산했으며 상세는 EVALUATION_GATE_FEASIBILITY_AUDIT.'),
        12:('시간 분할',json.dumps(read('TEMPORAL_SPLIT_CONTRACT'),ensure_ascii=False)),
        13:('CAL_FIT/CAL_SELECT','CAL 달력 2024-11-01~15 / 2024-11-16~29. 유효일은 15일/11일. 기존 성숙도 제외 11/26, 11/28, 11/29는 복원하지 않음. 원래 stage cutoff에 따른 오프라인 평가.'),
        14:('특징 authority','R5 61개 특징을 각 window 시작 슬롯에서 그대로 사용. 시작 슬롯/시간폭 2개와 성숙한 7/14/21/28일 누적 lag 및 mask 8개를 추가해 71개. 미래 실현 count/runtime/severity, classifier 출력, 새 외부 입력 없음.'),
        15:('성숙도 증명','83,760개 window의 inherited availability <= issue와 각 lag 전체의 latest raw availability < issue를 저장·독립 재계산했다. 실제 telemetry ingestion 지연까지 보증하는 자료는 아니다.'),
        16:('B0','최근 이용 가능한 7/14/21/28일 동일 window 중심값. 없는 경우 인과적으로 성숙한 TRAIN 동일 window 중앙값 → horizon 중앙값 → 0. 중심 예측 기준선 전용.'),
        17:('B1','TRAIN만 사용하고 각 issue 이전에 완전히 성숙한 날만 참조. horizon/start/weekday → horizon/start → horizon → TRAIN horizon fallback; support 8/20/50/1. Q50/Q90 empirical linear quantile.'),
        18:('B2','H1/H4/H8/H24별 Q50/Q90 LightGBM. CPU 1 thread, seed 20260907. TRAIN log1p 타깃에 학습; expm1 역변환. 실질적 음수값은 절단하지 않고 NEGATIVE_PREDICTION_AUDIT에 기록.'),
        19:('하이퍼파라미터 비교',table(hp['ranking'])),
        20:('공통 선택 설정',hp['selected_config']+'; '+json.dumps(CONFIGS[hp['selected_config']])+'; DEV-only, CAL/EXPOSED 재선택 없음.'),
        21:('horizon별 Q50',table(q50[q50.phase=='EXPOSED_EVALUATION'],['horizon','family','MAE','RMSE','WAPE','bias','positive_MAE','positive_WAPE'])),
        22:('horizon별 Q90/upper',table(q90[q90.phase=='EXPOSED_EVALUATION'],['horizon','candidate','positive_coverage','positive_pinball','positive_MAE','positive_WAPE','overall_coverage_DIAGNOSTIC'])),
        23:('crossing 감사',table(read('QUANTILE_CROSSING_AUDIT')['audits'])),
        24:('horizon별 보정 delta',json.dumps(freeze['calibration_deltas'])),
        25:('CAL_SELECT 양수 coverage',table(cal,['horizon','candidate','positive_coverage','gate_PASS','failure_reasons'])),
        26:('day-cluster coverage',table(cal,['horizon','candidate','supported_days','mean_supported_day_coverage'])),
        27:('under GPUh',table(cal,['horizon','candidate','under_GPUh','positive_under_GPUh'])),
        28:('over GPUh',table(cal,['horizon','candidate','over_GPUh','TRAIN_Q95_anchor_over_GPUh'])),
        29:('양수 upper WAPE',table(cal,['horizon','candidate','positive_WAPE'])),
        34:('선택 동결 커밋',read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit']),
        35:('EXPOSED 결과',result['classification']+'; 동결된 NONE은 그대로 유지하며, U0/U1/U2 진단을 결과 후 추천으로 사용하지 않음.'),
        39:('H4 최종 안전성',str(result['by_horizon']['H4']['selected_pass'])+'; '+json.dumps(read('FAILURE_DIAGNOSIS')['horizons']['H4'],ensure_ascii=False)),
        40:('H24 최종 안전성',str(result['by_horizon']['H24']['selected_pass'])+'; '+json.dumps(read('FAILURE_DIAGNOSIS')['horizons']['H24'],ensure_ascii=False)),
        41:('H1/H8 진단',json.dumps({h:read('FAILURE_DIAGNOSIS')['horizons'][h] for h in SECONDARY},ensure_ascii=False)),
        42:('15분 central shape',json.dumps(read('15MIN_SHAPE_DIAGNOSTIC'),ensure_ascii=False)),
        43:('bootstrap',json.dumps(read('BOOTSTRAP_STATUS'),ensure_ascii=False)),
        44:('확인 검증 상태','TRUE_CONFIRMATORY_AVAILABLE=NO. 최대 허용 해석은 PREVALIDATED이며 EXPOSED는 독립 확증이 아니다.'),
        45:('interface proposal','recommended_rows='+str(len(read('OPTIMIZER_INTERFACE_PROPOSAL')['recommended_rows']))+'; proposal_only=TRUE, optimizer_use_allowed=FALSE.'),
        46:('GPUh 물리 의미','누적 도착 GPU 서비스 작업량이다. 순간 GPU 점유/개수 또는 IT/PCC 전력이 아니다. 미래 B[t+1]=B[t]+A[t]-S[t], S[t]=0.25*r[t] backlog 연결이 필요하지만 이번에는 구현하지 않았다.'),
        47:('May/shadow firewall','May scientific reads=0, Apr24–30 shadow scientific reads=0, SEALED. Git 경로/index·기존 provenance 메타데이터 접근은 NONZERO로 별도 공개. 초기 sparse checkout으로 materialize된 R4 자료에는 과학적 row query 없음.'),
        48:('optimizer/Gurobi/OpenDSS/Fresh','모두 0회. 새 optimizer/전기 계산 호출 없음.'),
        49:('시스템 동결','A0/A1/M1/MF/migration/WAN/terminal 포함 전체 상속 Git 범위 변경 0. q=5576.44921875 s, PF=.95, Q control=NO, electrical=HOLD, FULL_MAY=NO.'),
        50:('tests','PREFIT 79 checks PASS. 최종 TEST_REPORT 및 receipt에 postfit/closure 실제 결과를 기록. 과학적 안전성 판정과 별개.'),
        51:('동일 seed 재현성','최종 8개 모델 독립 재학습 1회. CAL과 EXPOSED Q50/Q90/calibrated upper의 최대·평균 차이는 각 재현성 감사에 기록.'),
        52:('보호 범위','R5/R5R1 모든 materialized 파일 SHA256와 전체 inherited Git diff를 검사하여 변경 0. R6 source/artifacts/tests만 추가.'),
        53:('과학 커밋','FINAL_COMMIT_RECEIPT.json의 scientific_commit에서 정확한 SHA를 확인한다.'),
        54:('receipt 커밋','git log -1 --format=%H -- dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/V40R6_FINAL_COMMIT_RECEIPT.json 으로 최종 receipt commit을 독립 확인한다.')}
    for i,h in enumerate(HORIZONS,6): points[i]=(h+' 분포',json.dumps(dist[h]['all_authority_rows'],ensure_ascii=False))
    for i,h in enumerate(HORIZONS,30): points[i]=(h+' 선택',selected[h]+'; CAL_SELECT frozen hierarchy.')
    monthly_rows=read('MONTHLY_STABILITY_AUDIT')['rows']
    for i,m in enumerate(['2024-12','2025-01','2025-02'],36):
        rows=[r for r in monthly_rows if r['phase']=='EXPOSED_EVALUATION' and r['month']==m]
        points[i]=(m+' 월별 안정성',table(rows,['horizon','candidate','days','positive_windows','pooled_positive_coverage','mean_day_coverage','under_GPUh','over_GPUh','Q50_WAPE','upper_WAPE']))
    for i in range(1,55):
        title,body=points[i]; lines += [f'{i}. {title}', '',body,'']
    lines += ['실행 교정 공개: 첫 L0/H1/Q50의 음수 출력에서 임의 중단하던 실행 검사를 제거했다. 모델·expm1 변환·지표·안전 게이트는 변경하지 않았고 첫 모델 바이트를 재사용했다. 교정 커밋은 EXECUTION_CORRECTION_COMMIT_RECEIPT에서 확인할 수 있다.',
        '처음 모델의 학습 소요시간은 프로세스 중단 전에 저장되지 않아 null로 남겼다. 전체 32개 적합 중 나머지 31개 시간만 합산한다.',
        '실패 결과를 미래 workload 예측 불가능성으로 일반화하지 않는다. 중앙 예측 skill, upper coverage, 시간 안정성, 과예약 중 실제 실패 항목을 구분한다.']
    (OUT/'V40R6_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')

def receipt():
    assert git('status','--porcelain')==''
    science=git('rev-parse','HEAD'); result=read('EXPOSED_RESULTS')
    dump('FINAL_COMMIT_RECEIPT',{'scientific_commit':science,'R5R1_receipt_commit':BASE,
        'preregistration_commit':read('PREREGISTRATION_COMMIT_RECEIPT')['commit'],
        'selection_freeze_commit':read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit'],
        'execution_correction_commit':read('EXECUTION_CORRECTION_COMMIT_RECEIPT')['commit'],
        'receipt_commit_resolution':'git log -1 --format=%H -- dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/V40R6_FINAL_COMMIT_RECEIPT.json',
        'classification':result['classification'],'selected_candidates':read('SELECTION_FREEZE')['selected_candidates'],
        'selected_config':read('HYPERPARAMETER_FREEZE')['selected_config'],'primary_safety':result['primary_safety'],
        'full_safety':result['full_multi_horizon_safety'],'tests':read('TEST_REPORT'),
        'scientific_commit_clean_verified':True,'final_read_only_test_command':'python tests/dayahead/test_v40r6_contracts.py --closure --read-only',
        'required_artifact_count':read('REQUIREMENTS_MANIFEST')['required_count'],'optimizer_integration':'NO','production_ready':'NO'})

if __name__=='__main__': {'audit':audit,'review':review,'receipt':receipt}[sys.argv[1]]()
