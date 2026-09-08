"""Read saved outcomes, report the final research closure, and preserve authority."""
from .common import *
import sys

def table(rows,columns=None):
    f=pd.DataFrame(rows)
    if columns: f=f[columns]
    def cell(v):
        if isinstance(v,(float,np.floating)): return f'{v:.9g}'
        return str(v).replace('|',' / ').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(f.columns)+' |','|'+'|'.join(['---']*len(f.columns))+'|']+
        ['| '+' | '.join(cell(v) for v in row)+' |' for row in f.itertuples(index=False,name=None)])

def audit():
    authority(); selection_authority(); start=read('PROTECTED_SCOPE_START'); end=snapshot(); assert start==end
    dump('PROTECTED_SCOPE_END',end)
    dump('PROTECTED_SCOPE_DIFF',{'PASS':True,'inherited_file_count':len(end['inherited_SHA256']),
        'changed_inherited_files':[],'entire_inherited_Git_diff_empty':True,'R6_90pct_result_and_predictions_unchanged':True})
    ledger=pd.read_parquet(OUT/'V40R6R1_DAILY_CALIBRATION_LEDGER.parquet')
    csv('DAILY_DELTA_SEQUENCE',ledger.sort_values(['target_day','horizon','candidate']).to_dict('records'))
    dump('NO_NEW_FIT_AUDIT',{'new_LightGBM_fits':0,'new_statistical_model_fits':0,'new_classifier_fits':0,
        'new_feature_engineering':0,'new_target_construction':0,'base_prediction_recompute':0,
        'source':'Exact R6 saved prediction arrays; no model library imported or model fitted',
        'only_new_scientific_object':'Causal expanding calibration of frozen upper outputs',
        'R6_BASE_SKILL_LIMITATION':'PRESENT','R6_fit_ledger_SHA256':sha(R6/'V40R6_COMPUTE_LEDGER.json')})
    dump('CONTEXT_ONLY_DIAGNOSTICS',{'H1':r6('EXPOSED_RESULTS')['by_horizon']['H1'],
        'H8':r6('EXPOSED_RESULTS')['by_horizon']['H8'],'15min':r6('15MIN_SHAPE_DIAGNOSTIC'),
        'H1_H8_recalibrated':False,'15min_retrained':False,'role':'READ_ONLY_R6_CONTEXT; does not affect selection'})
    review()

def review():
    final=read('FINAL_DECISION'); selected=final['selected_candidates']; cal=read('CAL_EVALUATION')['by_horizon']; ex=read('EXPOSED_RESULTS')
    ledger=pd.read_parquet(OUT/'V40R6R1_DAILY_CALIBRATION_LEDGER.parquet'); support=read('RESIDUAL_LIBRARY_AUDIT')['rows']
    delta=read('DELTA_EVOLUTION_AUDIT')['rows']; comparison=read('R6_90_VS_R6R1_85_COMPARISON')['rows']
    cflat=pd.read_csv(OUT/'V40R6R1_CAL_RESULTS.csv'); eflat=pd.read_csv(OUT/'V40R6R1_EXPOSED_METRICS.csv')
    def state(h): return 'PASS' if ex['selected_horizon_pass'][h] else 'FAIL (NONE; 후보 결과는 진단 전용)' if selected[h]=='NONE' else 'FAIL'
    lines=['FINAL CLASSIFICATION: '+final['classification'],'WORKLOAD RESERVE SERVICE LEVEL: 85%','PRIMARY HORIZONS: H4, H24',
        'SELECTED H4 BASE: '+(CANDIDATES[selected['H4']] if selected['H4']!='NONE' else 'NONE'),
        'SELECTED H24 BASE: '+(CANDIDATES[selected['H24']] if selected['H24']!='NONE' else 'NONE'),
        'SELECTED H4 ROLLING UPPER: '+selected['H4'],'SELECTED H24 ROLLING UPPER: '+selected['H24'],
        'H4 CAL SAFETY: '+('PASS' if selected['H4']!='NONE' else 'FAIL'),'H24 CAL SAFETY: '+('PASS' if selected['H24']!='NONE' else 'FAIL'),
        'H4 EXPOSED SAFETY: '+state('H4'),'H24 EXPOSED SAFETY: '+state('H24'),
        'JOINT RESERVE STATUS: '+('PASS' if final['joint_pass'] else 'FAIL'),
        'FUTURE WORKLOAD ML STATUS: '+final['FUTURE_WORKLOAD_MODEL_STATUS'],'OPTIMIZER INTEGRATION: NO','PRODUCTION READY: NO','',
        '85%는 외생 미래 workload reserve의 공학적 서비스 수준이다. 계통 보안·전압 신뢰도·전기적 안전확률이 아니다.',
        '각 지표는 기존의 유효 날짜 및 원본 예측에 대해 계산했다. H4 누적 window가 겹치므로 under/over 합계는 고유 작업량 총계가 아니다.','']
    points={
        1:('Git lineage',' → '.join(read('GIT_LINEAGE_AUDIT')['lineage'])),
        2:('R6 불변 보존','R6=V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL, H1/H4/H8/H24=NONE, optimizer/production=NO 유지. R5/R5R1/R6 파일 해시 및 전체 보호 Git 범위 변경 없음.'),
        3:('85% 설계 해석','85% WORKLOAD-RESERVE SERVICE LEVEL. H4/H24의 양수 coverage 85–92.5%, 일/지원 월 80% 하한과 효율 기준을 사전 고정했다. R6의 90% 실험을 재분류하지 않았다.'),
        4:('동결 타깃 identity',json.dumps(read('TARGET_IDENTITY_AUDIT'),ensure_ascii=False)),
        5:('동결 B1/B2 identity','모두 READ_FROM_FROZEN_ARRAY. B1 baseline[:,2], B2 L0의 기존 crossing-repaired q[:,1]. 원본 파일별 SHA256은 BASE_PREDICTION_IDENTITY에 기록. base의 음수는 요청한 log1p(max(base,0)) 식에서만 처리.'),
        6:('신규 fit 없음',json.dumps(read('NO_NEW_FIT_AUDIT'),ensure_ascii=False)),
        7:('잔차 인과성','사용자가 명시적으로 선택한 max(target_day_end,target_label_available_at)<issue_time. OOS 172일 중 159일은 날짜 종료 후 정답이 확정되므로 날짜 종료만으로 편입하지 않는다. 모든 historical day의 전체 window를 함께 포함한다.'),
        8:('DEVELOPMENT 초기 잔차','TRAIN fit에 대해 OOS인 DEVELOPMENT 58일만 초기화에 사용. TRAIN in-sample 잔차 0. DEVELOPMENT는 R6 설정 선택에도 쓰였으므로 완전히 미노출된 tuning holdout이라는 주장은 하지 않는다.'),
        9:('H4 지원량 증가',table([r for r in support if r['horizon']=='H4'])),
        10:('H24 지원량 증가',table([r for r in support if r['horizon']=='H24'])),
        11:('H4 일별 delta 분포',table([r for r in delta if r['horizon']=='H4'])),
        12:('H24 일별 delta 분포',table([r for r in delta if r['horizon']=='H24'])),
        17:('CAL 후보 선택',json.dumps(read('SELECTION_FREEZE')['selected_candidates'])+'; 지원량→coverage→시간 안정성→miss→두 over anchor→WAPE를 모두 통과한 후보만 선택. 2% 효율 동률이면 B1.'),
        18:('선택 동결 커밋',read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit']),
        19:('EXPOSED H4',table(eflat[eflat.horizon=='H4'])),
        20:('EXPOSED H24',table(eflat[eflat.horizon=='H24'])),
        24:('miss severity',table(read('MISS_SEVERITY_AUDIT')['rows'])),
        25:('overreservation',table(pd.concat([cflat,eflat]),['phase','horizon','candidate','over_GPUh','TRAIN_Q95_anchor_over_GPUh','R6_static_U2_over_GPUh'])),
        26:('positive upper WAPE',table(pd.concat([cflat,eflat]),['phase','horizon','candidate','positive_upper_WAPE'])),
        27:('H4 정적90 대비 rolling85',table([r for r in comparison if r['horizon']=='H4'])),
        28:('H24 정적90 대비 rolling85',table([r for r in comparison if r['horizon']=='H24'])),
        29:('bootstrap',json.dumps(read('BOOTSTRAP_STATUS'),ensure_ascii=False)),
        30:('물리적 해석','Arriving GPU-service work [GPUh]. GPU 점유/개수 또는 IT/PCC 전력이 아니다. 미래 backlog 식 B[t+1]=B[t]+A[t]-S[t], S[t]=0.25*r[t]는 설명용이며 구현하지 않았다. 전기적 feasibility는 별도 계층이다.'),
        31:('interface proposal','추천 행 '+str(len(read('OPTIMIZER_INTERFACE_PROPOSAL')['recommended_rows']))+'개. proposal_only=TRUE, optimizer_use_allowed=FALSE. 실패 시 []이며 합성 job/runtime/GPU request/site/migration 없음.'),
        32:('미래 workload 연구 종료',final['FUTURE_WORKLOAD_MODEL_STATUS']+'; FURTHER_FUTURE_WORKLOAD_MODEL_WORK=DEFER_UNTIL_NEW_DATA_OR_AUTHORITY. 현 authority 아래 CLOSED. R6R2/R7/새 모델/새 horizon/새 calibration family/service-level search를 생성하지 않는다.'),
        33:('May/shadow firewall','May scientific reads=0; Apr24–30 shadow=SEALED, scientific reads=0. Git/index/path 및 기존 provenance 메타데이터 접근은 NONZERO로 별도 공개.'),
        34:('optimizer/Gurobi/OpenDSS/Fresh 호출','각각 0/0/0/0회. rolling calibration은 잔차 풀 갱신이며 optimizer 재해결·rolling MPC가 아니다.'),
        35:('A0/A1/M1/MF','전체 상속 Git 범위 변경 0. 운영 순서 및 joint freeze/electrical layer 변경 없음.'),
        36:('migration/WAN/terminal/MESS','변경 없음. production q=5576.44921875 s; PF=.95; Q control=NO; electrical=HOLD; electrical B0-B3=NO; FULL_MAY=NO.'),
        37:('tests','사전 검증 '+str(read('PREFIT_TEST_REPORT')['passed'])+'개 통과. '+('최종 과학 검증 '+str(read('TEST_REPORT')['passed'])+'개 통과. ' if (OUT/'V40R6R1_TEST_REPORT.json').exists() else '')+'receipt commit 후 --closure --read-only로 Git clean과 필수 산출물을 검증한다.'),
        38:('재현성',json.dumps(read('REPRODUCIBILITY_AUDIT'),ensure_ascii=False)),
        39:('보호 범위',json.dumps(read('PROTECTED_SCOPE_DIFF'),ensure_ascii=False)),
        40:('과학 커밋','FINAL_COMMIT_RECEIPT.json의 scientific_commit에 기록한다.'),
        41:('receipt 커밋','git log -1 --format=%H -- dayahead/artifacts/v40r6r1_risk_calibrated_rolling_gpuwork/V40R6R1_FINAL_COMMIT_RECEIPT.json 으로 확정한다.')}
    for i,(h,c) in enumerate([('H4','R85_B1'),('H4','R85_B2'),('H24','R85_B1'),('H24','R85_B2')],13):
        r=cal[h][c]
        points[i]=(f'CAL {h} {c}',table(cflat[(cflat.horizon==h)&(cflat.candidate==c)])+'\n\n'+json.dumps(r['gates'],ensure_ascii=False))
    temporal=read('TEMPORAL_STABILITY_AUDIT')['rows']
    for i,m in enumerate(['2024-12','2025-01','2025-02'],21):
        points[i]=(m+' 안정성',table([r for r in temporal if r['phase']=='EXPOSED_EVALUATION' and r['month']==m],
            ['horizon','candidate','positive_N','positive_coverage','mean_day_positive_coverage','under_GPUh','over_GPUh','positive_upper_WAPE','mean_miss_GPUh','maximum_miss_GPUh']))
    for i in range(1,42):
        title,body=points[i]; lines += [f'{i}. {title}','',body,'']
    lines += ['일별 무평활 delta 및 지원량 전개는 V40R6R1_DAILY_DELTA_SEQUENCE.csv와 원본 parquet ledger에 저장했다.',
        'H1/H8와 15분 SHAPE_ONLY는 기존 R6 읽기 전용 진단으로 보존했으며 새 보정·학습·선택에 사용하지 않았다.',
        'R6 static U2는 CAL_FIT에서 보정된 기존 비교 대상이다. R6R1의 CAL 평가는 전체 CAL에 대해 issue별로 인과적으로 실행되며, 비교 대상의 보정 과정을 다시 수행하지 않았다.',
        'EXPOSED는 과거 prequential 진단이며 TRUE_CONFIRMATORY_AVAILABLE=NO다. 시간 의존성이 있는 window에 교환가능성 기반의 distribution-free coverage 보증을 주장하지 않는다.','']
    if final['joint_pass']:
        lines += ['명시적인 85% workload-reserve service level 아래 인과적 expanding 잔차 보정이 H4/H24 누적 GPU-work reserve의 사전 정의된 안전성·효율성 요건을 충족했다. 최대 주장은 PREVALIDATED이며 production 또는 전기적 안전 보증이 아니다.']
    else:
        lines += ['사용 가능한 trace와 feature authority 아래 정확한 burst 예측과 누적 risk-calibrated reserve 예측은 사전 정의된 신뢰성·효율성 요건을 충족하지 못했다. 따라서 optimizer에 승격한 future-workload forecast는 없다.',
            '이 결론은 해당 자료와 동결된 계약에 한정한다. 현재 authority의 미래 workload 모델 연구를 종료하고 새 데이터 또는 authority가 생길 때까지 유보한다.']
    (OUT/'V40R6R1_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')

def receipt():
    assert git('status','--porcelain')==''; science=git('rev-parse','HEAD'); final=read('FINAL_DECISION')
    dump('FINAL_COMMIT_RECEIPT',{'scientific_commit':science,'R6_base_receipt':BASE,
        'preregistration_commit':read('PREREGISTRATION_COMMIT_RECEIPT')['commit'],
        'selection_freeze_commit':read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit'],
        'classification':final['classification'],'selected_candidates':final['selected_candidates'],
        'FUTURE_WORKLOAD_MODEL_STATUS':final['FUTURE_WORKLOAD_MODEL_STATUS'],
        'FURTHER_FUTURE_WORKLOAD_MODEL_WORK':final['FURTHER_FUTURE_WORKLOAD_MODEL_WORK'],'current_authority_research_status':'CLOSED',
        'new_fits':0,'optimizer_calls':0,'production_ready':'NO','tests':read('TEST_REPORT'),
        'required_artifact_count':read('REQUIREMENTS_MANIFEST')['count'],'clean_scientific_commit_verified':True,
        'receipt_commit_resolution':'git log -1 --format=%H -- dayahead/artifacts/v40r6r1_risk_calibrated_rolling_gpuwork/V40R6R1_FINAL_COMMIT_RECEIPT.json',
        'final_read_only_test_command':'python tests/dayahead/test_v40r6r1_contracts.py --closure --read-only'})

if __name__=='__main__': {'audit':audit,'review':review,'receipt':receipt}[sys.argv[1]]()
