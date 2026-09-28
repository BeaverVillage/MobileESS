from core import *
def table(frame,columns=None):
    f=frame if columns is None else frame[columns]
    def val(x):return f'{x:.5g}' if isinstance(x,(float,np.floating)) else str(x)
    return '| '+' | '.join(f.columns)+' |\n| '+' | '.join(['---']*len(f.columns))+' |\n'+'\n'.join('| '+' | '.join(val(x) for x in row)+' |' for row in f.itertuples(index=False,name=None))
def main():
    assert read(ROOT/'VALIDATION.json')['PASS']
    m=pd.read_csv(ROOT/'ARM_METRICS.csv');u=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');d=pd.read_csv(ROOT/'TARGET_DISTRIBUTION.csv');align=pd.read_csv(ROOT/'TARGET_OPERATIONAL_ALIGNMENT.csv');b=pd.read_csv(ROOT/'TARGET_BOUNDARY_AUDIT.csv');s2=pd.read_csv(ROOT/'STAGE2_MODEL_METRICS.csv');ab=pd.read_csv(ROOT/'FEATURE_ABLATION.csv');lead=pd.read_csv(ROOT/'LEAD_GROUP_METRICS.csv');res=pd.read_csv(ROOT/'RESOLUTION_COMPARISON.csv')
    p=read(ROOT/'TARGET_POPULATION_AUDIT.json');placement=read(ROOT/'LIFETIME_PLACEMENT_AUDIT.json');freeze=read(ROOT/'FEATURE_SELECTION_FREEZE.json');tfreeze=read(ROOT/'TARGET_SELECTION_FREEZE.json')
    roles=['EXPOSED_EVALUATION','OOS_EXTENSION'];support={};reasons=[]
    for t in ['T0','T1','T2','T3']:
        for f in ['F1','F2','F3','F4','F5']:
            arm=t+'_'+f;ok=True;checks=[]
            for role in roles:
                ci=u[u.contrast.eq(arm+' minus '+t+'_F0')&u.role.eq(role)&u.variant.eq('RAW')&u.block_days.eq(7)&u.metric.eq('Q90_pinball')].iloc[0]
                raw=m[m.arm.eq(arm)&m.role.eq(role)&m.variant.eq('RAW')].iloc[0];base=m[m.arm.eq(t+'_F0')&m.role.eq(role)&m.variant.eq('RAW')].iloc[0];cal=m[m.arm.eq(arm)&m.role.eq(role)&m.variant.eq('CALIBRATED')].iloc[0];calbase=m[m.arm.eq(t+'_F0')&m.role.eq(role)&m.variant.eq('CALIBRATED')].iloc[0]
                passed=bool(ci.CI_high<0 and raw.Q50_MAE<=base.Q50_MAE and raw.requirement_ratio<=base.requirement_ratio and cal.requirement_ratio<=calbase.requirement_ratio and .88<=cal.Q90_coverage<=.92)
                checks.append(dict(role=role,passed=passed,pinball_CI_high=ci.CI_high,raw_MAE_delta=raw.Q50_MAE-base.Q50_MAE,raw_ratio_relative=raw.requirement_ratio/base.requirement_ratio,calibrated_ratio_relative=cal.requirement_ratio/calbase.requirement_ratio,calibrated_coverage=cal.Q90_coverage));ok &= passed
            support[arm]=bool(ok);reasons.append(dict(arm=arm,supported=bool(ok),period_checks=checks))
    write('SUPPORT_GATES.json',dict(feature_support=reasons,selection_unchanged=True,May_is_diagnostic=True))
    selected=freeze['candidates'];near=True
    for arm in selected:
        q=m[m.arm.eq(arm)&m.role.isin(roles)&m.variant.eq('CALIBRATED')];near &= bool(q.Q90_coverage.between(.88,.92).all())
    t2robust=any(support.get('T2_'+f,False) for f in ['F1','F2','F4','F5']);t3robust=any(support.get('T3_'+f,False) for f in ['F1','F2','F4','F5'])
    flags=dict(CURRENT_TARGET_REPRODUCED=True,POST_ISSUE_PRE_D00_BOUNDARY_AUDITED=True,T0_VALID=True,T1_VALID=True,T2_VALID=True,T3_VALID=True,TARGET_MAPPING_IS_MAJOR_BOTTLENECK='INCONCLUSIVE',FEATURE_MAPPING_IS_MAJOR_BOTTLENECK=True if any(support.values()) else 'INCONCLUSIVE',SAME_CLOCK_FEATURE_SUPPORTED=any(v for k,v in support.items() if k.endswith('F1')),FINE_RECENCY_FEATURE_SUPPORTED=any(v for k,v in support.items() if k.endswith('F2')),ISSUE_STATE_FEATURE_SUPPORTED=False,CALENDAR_REGIME_FEATURE_SUPPORTED=any(v for k,v in support.items() if k.endswith('F4')),HOURLY_ACTIVE_OCCUPANCY_SUPPORTED=t2robust,FIFTEEN_MIN_ACTIVE_OCCUPANCY_SUPPORTED=t3robust,TARGET_FEATURE_REDIRECTION_SUPPORTED=t2robust or t3robust,Q90_CALIBRATION_NEAR_NOMINAL=near,SHARPNESS_IMPROVEMENT_SUPPORTED=any(support.values()),STAGE2_MODEL_SEARCH_AUTHORIZED=True,CC4_V27_REPLACEMENT_SUPPORTED=False,CC4_V27_OPTIMIZER_INTEGRATION_READY=False)
    write('FINAL_VERDICT.json',dict(**flags,OPERATIONAL_TARGET_MISALIGNMENT_ESTABLISHED=True,flag_semantics='VALID means mathematical label implementation and event-time checks pass, not certified telemetry snapshot or operational readiness. SUPPORTED means registered multi-period forecast support gate, not merely definitional occupancy alignment. Target-relative ratio non-inferiority is conservatively required for both raw and calibrated forecasts.',mapping_conclusion='Temporal concentration and electrical mismatch established; fraction of previous forecast difficulty causally attributable versus irreducible shift is not identified by target changes alone.',unavailable=['exact historical RUNNING/PENDING snapshot','source-jurisdiction holiday calendar','authorized PCC conversion','request-version and ingestion-time certification'],operational_promotion='No automatic promotion, no optimizer edits/runs; separate interface verification and integration task required',NO_UNTOUCHED_CONFIRMATION=True,May_used_for_selection=False))
    boundary=[]
    for role,g in b.groupby('role'):
        boundary.append(dict(role=role,days=len(g),preD00_submissions=g.eligible_submissions.sum(),preD00_overlap_GPUh=g.Dday_overlap_GPUh.sum(),unknown_GPUh=g.Dday_unknown_GPUh.sum(),mass_fraction=g.Dday_overlap_GPUh.sum()/g.Dday_unknown_GPUh.sum(),mean_peak_fraction=g.unknown_peak_fraction.mean()))
    train=d[d.role.eq('TRAIN')];critical=m[m.arm.isin(['T0_F0','T0_F5','T3_F0','T3_F5','T2_F0','T2_F5'])&m.role.isin(roles+['MAY_HISTORICAL'])]
    cols=['arm','role','variant','Q90_coverage','Q90_pinball','requirement_ratio','Q50_MAE','Q50_WAPE']
    supported=[k for k,v in support.items() if v]
    def groupsuffix(f):return ', '.join(k for k in supported if k.endswith(f)) or '등록된 다기간 지지 기준을 통과한 조합 없음'
    rawbase=m[m.features.eq('F0')&m.variant.eq('RAW')&m.role.isin(roles+['MAY_HISTORICAL'])]
    cires=u[u.contrast.str.contains('hourly aggregate')&u.metric.eq('Q90_pinball')&u.block_days.eq(7)]
    cis2=u[u.contrast.str.contains('M1 minus M0')&u.metric.eq('Q90_pinball')&u.variant.eq('RAW')&u.block_days.eq(7)]
    spans=lead[lead.arm.isin(selected)&lead.role.isin(roles)].groupby(['arm','variant','role']).Q90_coverage.agg(['min','max']).reset_index();spans['spread']=spans['max']-spans['min']
    f5=ab[ab.arm.str.endswith('F5')&ab.role.isin(roles+['MAY_HISTORICAL'])&ab.variant.eq('RAW')]
    ratio=[]
    for (t,role,var),g in m[m.role.isin(roles)].groupby(['target','role','variant']):
        within=g[g.Q90_coverage.between(.88,.92)];r=within.sort_values('requirement_ratio').iloc[0] if len(within) else None
        ratio.append(dict(target=t,role=role,variant=var,arm=r.arm if r is not None else 'NONE_IN_BAND',ratio=r.requirement_ratio if r is not None else np.nan,coverage=r.Q90_coverage if r is not None else np.nan))
    parts=['# CC4-v2.7 최종 검토',
        'PR #74의 `bae7916c759e1c845bb87a8ee0dff761b5db7f7a`에서 분기한 독립 오프라인 실험이다. 이전 증거와 V42/optimizer/MESS/IEEE/OpenDSS는 변경하지 않았다. 원 타깃과 기준 예측은 정확히 재현했다. 타깃 정합성, 특징 효과, 해상도 효과, 모델 분할 효과를 별도 평가했다.',
        '## 20개 필수 질문에 대한 답변',
        '**1. T0를 정확히 재구성했는가?** 예. 1,056만 원시 행에서 같은 1,030,506개 적격 작업을 복원했고 443일 T0 배열과 성숙 시각이 비트 단위로 같다. A0의 273일 일별 재학습 Q50/Q90도 원 결과와 완전히 같다. `A0_VERIFIED.json`은 초기 모델 검증 후 완료한 타깃 검증을 연결한다.',
        f'**2. 발행 후 자정 전 제출의 기여는?** 전체 일 적분량의 {p["preD00_mass_fraction"]:.3%} ({p["preD00_total_GPUh"]:,.3f} GPUh / {p["unknown_total_GPUh"]:,.3f} GPUh)다. 일별 미지 부하 피크 시점의 해당 모집단 기여율 평균은 {p["mean_daily_peak_fraction"]:.3%}다. 이는 최대값끼리의 비율이 아니라 같은 피크 시점에서 평가한 비율이다.',table(pd.DataFrame(boundary)),
        '**3. 수명 GPUh를 제출 시간에 몰아넣으면 버스트성이 커지는가?** 이 자료에서는 그렇다. 런타임 곱을 제거한 T1도 T0보다 변동계수와 상위 1% 질량 비중이 작다. T2/T3에서는 실행시간 분산과 발행 후 6시간 모집단 보완이 함께 달라지므로 그 차이 전부를 한 원인에만 배분할 수는 없다.',table(train,['target','zero_fraction','CV','skewness','top1_mass_share','max_positive_median']),
        f'T0 버스트 슬롯 질량 중 실행 24시간 초과 작업 기여는 {p["burst_long_runtime_mass_share"]:.2%}, 4 GPU 초과 작업 기여는 {p["burst_large_GPU_mass_share"]:.2%}다. 두 범주는 겹칠 수 있다. 슬롯 질량의 10/25/50% 초과 작업 수는 TARGET_SLOT_CONTRIBUTIONS.csv에 모두 보존했다. 같은 D일 제출 모집단의 전체 수명량 중 실제로 D일 이후에 실행되는 비중은 전체 {placement["all_days_outside_D_mass_fraction"]:.2%}, TRAIN {placement["TRAIN_outside_D_mass_fraction"]:.2%}다. T2 일 적분량 = 같은 D일 제출 작업의 D일 실행량 + 발행 후 자정 전 제출 작업의 D일 실행량 항등식도 독립 검증했다.',
        '**4. T1이 더 예측하기 쉬운가?** 단위가 달라 절대 MAE·pinball을 비교하지 않는다. 아래 F0의 WAPE와 TRAIN 평균으로 나눈 pinball을 기간별로 비교한다. 분포 완화만으로 전력 타깃 적합성이나 일반적 예측 우위를 주장하지 않는다.',table(rawbase,['target','role','Q90_coverage','Q90_pinball_per_TRAIN_mean','Q50_WAPE','requirement_ratio']),
        '**5. T2가 T0보다 쉽고 안정적인가?** 라벨 분포는 훨씬 안정적이다. 예측 측면은 위 무차원 오차·보정·비율과 아래 기간별 결과로 분리한다. 서로 다른 라벨의 절대 손실 감소는 통계적 우위 증거로 쓰지 않는다.',
        '**6. T3는 T2보다 정확한가, 더 시끄러운가?** T3의 TRAIN 변동계수·0 비율은 T2보다 높다. 공통 시간별로 T3 평균을 만든 해상도 대조를 별도 보고했다. 아래 CI가 0을 포함하면 우위를 주장하지 않는다. 네 주변 Q90의 평균은 다시 추정한 시간별 Q90이나 공동 일 Q90이 아니다.',table(cires,['contrast','role','delta','CI_low','CI_high']),
        '**7. 어떤 타깃이 전기적 미지 점유에 정합적인가?** T2/T3다. 시간별 상관 1과 피크 오차 0은 정의상 항등식이며 예측 성공이 아니다. T0/T1은 도착량이다. 허가된 PCC 변환이 없어 GPU 점유까지만 결론 낸다.',table(align[align.role.eq('TRAIN')],['target','Pearson','Spearman','peak_time_MAE_hours','top10_slot_overlap','top5_slot_overlap']),
        '**8. 명시적 1/2/3일 동일 시각 정보가 개선하는가?** '+groupsuffix('F1')+'. 성숙한 값만 사용했다. F1은 1/2/3/7/14/21/28일과 최신 가용 후보의 묶음이므로 1/2/3일 단독 효과는 식별하지 못한다.',
        '**9. 세밀한 최근 도착 정보가 버스트 예측을 개선하는가?** '+groupsuffix('F2')+'. 전체·양수·버스트 coverage는 STRATIFIED_METRICS.csv에 분리했다. 버스트 coverage 상승 하나만으로 reserve 팽창을 정당화하지 않는다.',
        '**10. RUNNING/PENDING 특징이 정보를 추가하는가?** 판정 불가. 정확한 과거 발행 시점 스냅샷이 없어 NOT_AVAILABLE로 제외했다. F3=F0는 결측 대조군이며 상태 특징이 무용하다는 결과가 아니다.',
        '**11. 공휴일·레짐 특징이 중요한가?** 요일·월·계절 F4에 대해서는 '+groupsuffix('F4')+'. 공휴일 관할과 원본 달력이 없어 공휴일 및 전후일 효과는 미검증이다.',
        '**12. 가장 큰 강건한 개선 그룹은?** 등록된 다기간 조건을 통과한 조합: '+(', '.join(supported) or '없음')+'. 서로 다른 타깃의 원 단위 손실을 섞어 단일 우승 그룹을 만들지 않았다. FEATURE_ABLATION.csv와 아래 CI에 상대 개선을 보존했다.',
        '**13. F5가 여러 OOS 기간에서 F0를 이기는가?** 아래 상대 손실·요구량·MAE를 확인한다. 지지 조건을 통과한 F5는 '+groupsuffix('F5')+'. 5월은 진단이며 선택에 쓰지 않았다.',table(f5,['arm','role','pinball_relative','delta_coverage','requirement_ratio_relative','delta_MAE']),
        '**14. 리드타임별 성능이 다른가?** 아래 coverage 범위와 HOUR_SLOT_METRICS/LEAD_GROUP_METRICS의 손실·비율을 함께 본다. 네 그룹은 [6,12), [12,18), [18,24), [24,30)시간이다.',table(spans),
        '**15. pooled LightGBM이 여전히 적절한가?** 타깃·특징 고정 후 동일 설정의 네 리드 그룹 M1과 비교했다. 아래 Stage2 CI가 0을 포함하거나 악화되면 복잡도를 늘릴 근거가 부족하다. DEV에서 선택된 모델도 확인되지 않은 운영 승격을 뜻하지 않는다.',
        '**16. 리드 그룹 모델이 도움이 되는가?** 아래 M1−M0 raw pinball의 일 단위 7일 블록 CI로 판정한다.',table(cis2,['contrast','role','delta','CI_low','CI_high']),
        '**17. 큰 reserve 팽창 없이 90%에 접근하는가?** RAW와 고정 보정 결과를 아래 필수 비교표에서 함께 보고한다. 88~92% 밴드를 넘긴 coverage는 자동 개선이 아니다. 두 연구 후보가 기존 평가와 확장 평가에서 모두 밴드 안에 있는지: '+str(near)+'.',
        '**18. 타깃별 최선의 요구량 비율은?** 아래는 각 보고 기간에서 밴드 안인 조합 중 최소 비율의 사후 기술통계다. 선택 동결을 바꾸지 않는다. NONE_IN_BAND면 조건을 만족한 조합이 없다. T1 적분량 단위는 requested GPU이며 GPUh가 아니다.',table(pd.DataFrame(ratio)),
        '**19. 개선이 통계적으로 지지되는가?** PAIRED_UNCERTAINTY.csv에 같은 날짜를 쌍으로 resample한 1일/7일 circular block, 2,000회 95% CI를 보존했다. 전 슬롯과 0 라벨을 유지하고 각 draw의 비율을 다시 계산했다. CI가 0을 포함하면 우위를 주장하지 않는다. 다중 비교 미보정 탐색적 CI이며 모델 재학습·선택 불확실성이나 독립 확인시험을 포함하지 않는다.',
        '**20. V42 통합 전에 운영 타깃을 바꿔야 하는가?** 도착 수명량과 실행 점유량은 별도 인터페이스로 구분해야 한다는 근거는 있다. 그러나 이 연구만으로 운영 교체를 승인하지 않는다. 요청 버전·수집 지연·상태 스냅샷·정책에 따른 실행 변경·PCC 변환 계약을 별도 검증하고 독립 V42 통합 작업에서 결정해야 한다. 본 작업의 교체·통합 준비 플래그는 FALSE다.',
        '## 필수 A/B/C/D 및 시간 해상도 대조',table(critical,cols),
        '## Stage2 결과',table(s2[s2.role.isin(roles+['MAY_HISTORICAL'])],['arm','model','role','variant','Q90_coverage','Q90_pinball','requirement_ratio','Q50_MAE']),
        'M2 기간별 독립 모델, M3 적응형 보정, M4 신경 모델은 이번 고정 프로토콜에서 보류했다. M0/M1의 비교가 Stage2 범위이며 미실행 모델을 검증한 것으로 표시하지 않는다.',
        '## 해석 범위와 재현',
        '전기적 매핑 불일치와 시간 집중은 입증됐다. 아키텍처, 특징 매핑, 운영 타깃, 분포 이동 중 과거 어려움의 몫을 하나의 원인으로 완전히 분해한 것은 아니다. 실패한 조합·hard day·0 라벨·5월 진단을 모두 남겼다. 버스트 임계값은 TRAIN 양수 Q95로 고정했다. 보정은 CAL 성숙 잔차로 고정했고 평가 기간에 업데이트하지 않았다. 원 baseline의 raw 재현과 새 보정 절차의 효과를 구분한다.',
        'SOURCE_MANIFEST는 이전 증거 해시를 검증한다. 새 실험 코드는 EXPERIMENT_CODE_FREEZE에, 선택은 TARGET/FEATURE/STAGE2_SELECTION_FREEZE에, 모든 새 재학습 날짜·가중치·모델 digest는 runs에 저장했다. 학습 모델의 전체 텍스트 대신 결정론적 재학습 recipe와 digest를 보존한다. FEATURE_IMPORTANCE는 마지막 적격 CAL 날짜의 Q50/Q90 합산 gain/split이며 선택에 사용하지 않았다. 후속 재현은 README의 새 디렉터리 절차를 따른다.',
        '## 최종 플래그',table(pd.DataFrame([dict(flag=k,value=v) for k,v in flags.items()]))]
    (ROOT/'FINAL_REVIEW_KO.md').write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    print('FINAL_REVIEW_COMPLETE')
if __name__=='__main__':main()
