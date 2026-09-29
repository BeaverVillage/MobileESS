from common import *
from audit import pareto
def main():
    c=pd.read_csv(ROOT/'CROSS_VERSION_Q50_COMPARISON.csv');eligible=c.scope.eq('FROZEN_CAUSAL_TOTAL')&c.same_Q50_as.isna()
    x=c[eligible].copy();x['time_ratio_distance']=abs(x.Q50_time_ratio-1)
    x['pareto_core']=pareto(x[['Q50_MAE_hours','Q50_calibration_error','time_ratio_distance']])
    x.to_csv(ROOT/'CROSS_VERSION_UNIQUE_CAUSAL_Q50.csv',index=False)
    choose=['V9::D2_extreme_1.0__NONE','V10::T3_LOGISTIC_ROLLING14_calibrated','V10::T3_ISOTONIC_ROLLING14_calibrated','V11::SELECTED_TOTAL','V12::EXPANDING_R2','V13::EXPANDING_S4','V15::R2','V16::R16-A','V16::R16-B','V16::R16-C']
    table='| 모델 | MAE [h] | C50 [%] | 시간비율 [x] | fold C50 min–max [%] | >12h C50 [%] |\n|---|---:|---:|---:|---:|---:|\n'
    ci=c.set_index('Model')
    for name in choose:
        a=ci.loc[name];table+=f'| {name} | {a.Q50_MAE_hours:.3f} | {100*a.Q50_coverage:.2f} | {a.Q50_time_ratio:.3f} | {100*a.min_fold_Q50_coverage:.2f}–{100*a.max_fold_Q50_coverage:.2f} | {100*a.GT12H_Q50_coverage:.2f} |\n'
    p=ci.loc['V9::D2_extreme_1.0__NONE'];v=ci.loc['V10::T3_ISOTONIC_ROLLING14_calibrated']
    assert v.Q50_MAE_hours<p.Q50_MAE_hours and v.Q50_calibration_error<p.Q50_calibration_error and abs(v.Q50_time_ratio-1)<abs(p.Q50_time_ratio-1)
    counts=c.groupby(['version','scope']).size()
    summary='; '.join(f'v{version} {scope}: {n}개' for (version,scope),n in counts.items())
    text='# 사용자 추가 요청: v1–v16 동결 Q50 확장 비교\n\n'+f'100개 저장 변형(고유 Q50 배열87개)을 원래230,237개 작업에 정확히 맞췄다. 이 중3개는 미래 학습/보정이 과거 fold에 적용된 비인과적 소급 참고치다. 같은 배열의 alias·Q90-only 차이를 독립 모델 개선으로 중복 계산하지 않는다. 고유 causal Q50 비교는 {len(x)}개다.\n\n'+table
    text+='\n**확장 비교는 결론을 보강한다. D2 extreme은 전체 모델 중 최선의 명목 Q50가 아니다.** V10 T3 isotonic rolling14가 MAE·pooled50% 근접성·시간 비율1 근접성이라는 사전 고정3축에서 D2 extreme을 엄격하게 지배한다. 이 모델의 coverage46.79%를90% 미달이라는 이유로 기각하지 않는다. Median으로는50%가 기준이다. 다만 fold36.35–63.08%, 실제>12h C50 19.01%라는 편차와 overrun 부담이 있으므로 이 감사에서 새 provider 승격이나 reserve 충분성을 주장하지 않는다.\n\n'
    text+=f'전체 unique causal 최저 MAE는 {x.loc[x.Q50_MAE_hours.idxmin(),"Model"]} ({x.Q50_MAE_hours.min():.6f}h)다. Pooled median coverage가 가장50%에 가까운 모델은 {x.loc[x.Q50_calibration_error.idxmin(),"Model"]}이지만, 그 pooled 수치만으로 시간적 안정성을 결론내리지 않는다.\n\n'
    text+='V13만 따로 본다면 expanding S4는 MAE6.575h, C50 64.88%, 시간 비율2.158이다. V15 R2는5.318h/68.05%/1.806배, V16 A/B/C는6.183/5.495/6.318h 및 C50 68.87/68.29/68.31%다. 더 뒤의 버전이라는 이유만으로 Q50가 우수하지 않다. 모든 원래5-fold 결과와 bucket/ratio분포는 CROSS_VERSION_Q50_*.csv에 있다.\n\n'
    text+='V10 rolling calibration은 당시 완료가 관측된 선행 이벤트로 업데이트한 기존 동결 확률 보정이다. 이번에는 저장 Q50/Q90만 읽었으며 보정값·모델을 새로 학습하지 않았다. 기존 causal audit의 미래 event/residual read=0 및 max_completion_used<day를 재검증한다. PR94의 CAL-only alpha 보간과 동일한 방법으로 혼동하지 않는다.\n\n'
    text+='계보별 범위: '+summary+'.\n\n'
    text+='v1–v5는 다른 issue/state 모집단, Running remaining 또는 May 노출 계보이므로 해당 payload를 새로 열어 비교하지 않았다. v6 constant/v8 M3_F2와 B0의 저장 소급 예측은 별도 NONCAUSAL_RETROSPECTIVE_REFERENCE이며 원래 모델 fit/보정이 과거 fold 이후라 causal 우승 후보가 아니다. v7은 source 포렌식, v14/J0·J1은 V13 재현이고 J2–J5 미실행, v14R1/R2도 포렌식이다. V13 ABL_E의 미완료 fold는 NOT_POOLED_INCOMPLETE_FROZEN_FOLDS이며 수치를 채우거나 새로 학습하지 않았다. 전체 계보/제외 근거는 RUNTIME_VERSION_INVENTORY.csv다.\n\n'
    text+='공식 PRIMARY_NOMINAL_RUNTIME_CANDIDATE는 NONE으로 유지한다. 이는 원 요청의 D2 extreme 채택 여부에 대한 결론이며, 확장100개 모두가 무용하다거나 모든 nominal 설계가 불가능하다는 뜻이 아니다. 후속 Planning reserve 연구에서는 V10 T3 isotonic rolling14와 최저 MAE logistic rolling14 등을 비교 기준으로 검토할 근거가 생겼다. 신규 선정 threshold·reserve/headroom·optimizer·remaining 모델은 이번 범위에 추가하지 않았다. PR94 NONE/alpha-null도 변경하지 않았다.\n'
    (ROOT/'CROSS_VERSION_REVIEW_KO.md').write_text(text,encoding='utf-8')
    marker='\n## 사용자 추가 요청에 따른 전체 버전 확장\n'
    for n in ['README.md','FINAL_REVIEW_KO.md']:
        pth=ROOT/n;original=pth.read_text(encoding='utf-8').split(marker)[0]
        pth.write_text(original+marker+'\n위 원 요청 비교표·50문답의 최선/Pareto는 고정6개 후보 범위다. 추가 요청으로100개 저장 변형까지 확장했고, **V10의 Q50가 D2 extreme보다 유리한 후보를 발견했다.** 아래 표와 [전체 버전 해석](CROSS_VERSION_REVIEW_KO.md)을 함께 읽어야 한다.\n\n'+table,encoding='utf-8')
    flags=read(ROOT/'FINAL_FLAGS.json');flags.update(CROSS_VERSION_VARIANTS_AUDITED=100,CROSS_VERSION_UNIQUE_Q50_ARRAYS=87,CROSS_VERSION_NONCAUSAL_REFERENCES=3);write('FINAL_FLAGS.json',flags)
    verdict=read(ROOT/'FINAL_VERDICT.json');verdict['cross_version_extension']=dict(variants=100,unique_Q50_arrays=87,primary_core_dominated_by='V10::T3_ISOTONIC_ROLLING14_calibrated',no_other_model_automatically_promoted=True,interpretation='NONE addresses the requested D2 extreme nomination. V10 provides stronger research comparators; no claim all100 models are unusable.')
    verdict['evidence'].extend(rec(ROOT/n) for n in ['CROSS_VERSION_Q50_COMPARISON.csv','CROSS_VERSION_PREREGISTRATION.json','CROSS_VERSION_REVIEW_KO.md']);write('FINAL_VERDICT.json',verdict)
if __name__=='__main__':main()
