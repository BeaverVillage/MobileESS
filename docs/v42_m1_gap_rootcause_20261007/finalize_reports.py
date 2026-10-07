"""Read-only attribution and evidence sealing. Never builds a solver model."""
from common import *
from fractions import Fraction as F
import argparse

REQUIRED_FILES='''PREREGISTRATION.md BASE_IDENTITY.json UB_VALIDATION.json LB_VALIDATION.json NUMERICAL_BOUND_AUTHORITY.json UB_FIXED_DISCRETE_REOPT.json UB_LOCAL_NEIGHBORHOOD_RESULT.json MESS04_69_72_INTEGER_TRAJECTORIES.json MESS04_69_72_HULL_AUTHORITY.json MESS04_69_72_INDEPENDENT_VERIFICATION.json MESS04_69_72_LP_MEMBERSHIP.json MESS04_69_72_SEPARATION.json CRITICAL_GRID_COUPLING_AUDIT.csv MESS04_GRID_EFFECT.json SINGLE_WINDOW_STRENGTHENED_LP.json SINGLE_WINDOW_VALID_LB_CERTIFICATE.json SUBSTITUTION_EFFECT_AUDIT.json MULTIWINDOW_HULL_AUTHORITY.json MULTIWINDOW_STRENGTHENED_LP.json CROSS_MESS_COUPLING_AUDIT.json LONGER_HORIZON_DIAGNOSTIC.json SELECTIVE_INTEGRALITY_RESULTS.csv GAP_ATTRIBUTION.csv TRAJECTORY_FORMULATION_DESIGN.md VERIFICATION.json SHA256_MANIFEST.json FINAL_REVIEW_KO.md'''.split()

def main(pr_url):
    single=read(OUT/'SINGLE_WINDOW_STRENGTHENED_LP.json');multi=read(OUT/'MULTIWINDOW_STRENGTHENED_LP.json')
    assert not multi.get('postprocessing_pending',False)
    fixed=read(OUT/'UB_FIXED_DISCRETE_REOPT.json');near=read(OUT/'UB_LOCAL_NEIGHBORHOOD_RESULT.json')
    cross=read(OUT/'CROSS_MESS_COUPLING_AUDIT.json');long=read(OUT/'LONGER_HORIZON_DIAGNOSTIC.json')
    selective=[read(OUT/f'SELECTIVE_MESS04_69_{t}.json') for t in (72,76)]
    UBnew=min(UB,fixed['new_valid_UB'],near['new_valid_UB']);LBnew=max(LB,single['new_valid_LB'],multi['new_valid_LB'],cross['new_valid_global_LB'],*[r['valid_global_LB'] for r in selective])
    structural=max(single['new_valid_LB'],multi['new_valid_LB'])-LB
    deltaUB=UB-UBnew;deltaLB=LBnew-LB;separation=UB-LB
    # Classification selected only now, after all the authorized experiments.
    assert structural<.001 and all(r['delta_LB']<.001 for r in selective), 'UPDATE_CAUSAL_REVIEW_FOR_MATERIAL_BOUND_GAIN'
    assert deltaUB>.001
    primary='GAP_PARTIALLY_ATTRIBUTED';axis='UB_DOMINATED'
    rows=[]
    def item(mechanism,newLB=LB,newUB=UB,preserved=True,classification='',notes=''):
        rows.append(dict(mechanism=mechanism,baseline_LB=LB,new_valid_LB=newLB,delta_LB=newLB-LB,required_delta_LB=REQUIRED,percent_required_LB_recovered=100*(newLB-LB)/REQUIRED,baseline_UB=UB,new_valid_UB=newUB,delta_UB=UB-newUB,exact_integer_set_preserved=preserved,classification=classification,notes=notes))
    item('one-slot local hulls from PR167',classification='PR167_NEGATIVE_RESULT_PRESERVED',notes='Historical 320 rows/17837 nnz; no rerun; certified gain0, ROOT_GAP_NOT_EXPLAINED_BY_TESTED_LOCAL_HULLS.')
    item('MESS04 69-72 joint hull',single['new_valid_LB'],classification='NO_MATERIAL_CERTIFIED_GAIN_NUMERICAL_LIMIT',notes='Full free-boundary local hull; raw augmented FAIL0.01889765; saved dual certificate0.558165053005941 below reference; native ObjBound missing after postcapture failure. Not complete exclusion of temporal weakness.')
    item('multiwindow MESS04 + MESS03 69-72',multi['new_valid_LB'],classification='NO_MATERIAL_CERTIFIED_GAIN',notes='Only one generalization,2 blocks; Crossover1 correctness change, no tolerance relaxation. Raw and actual native bound reported separately.')
    item('cross-MESS coupling at72 sw1A+l3A',cross['new_valid_global_LB'],preserved=False,classification='TESTED_LOCAL_COUPLING_SMALL',notes='Exact one-time projection + simultaneous original grid faces; relaxation of global integer schedules, not global model replacement. Local integer feasible minus convex exact lower bound <0.001; MIPGap0.005, global96-slot coupling not excluded.')
    item('selective MESS04 4-slot',selective[0]['valid_global_LB'],preserved=True,classification='NO_MATERIAL_OBSERVED_BOUND_GAIN',notes='Original whole C3A; only100 original B retained, all others relaxed. All original integer schedules preserved; partial point not production UB; bounded diagnostic cannot exclude unseen branches.')
    item('longer-horizon MESS04 8-slot',selective[1]['valid_global_LB'],preserved=True,classification='NO_MATERIAL_OBSERVED_BOUND_GAIN',notes='One evidence-driven8-slot extension;200 original B; original whole SOC/route/grid rows kept. Selective integrality, not a full8-slot hull or global solution.')
    item('primal fixed-discrete dispatch',newUB=fixed['new_valid_UB'],preserved=False,classification='NO_MEANINGFUL_UB_GAIN',notes='Restricted search retains physics, not all feasible discrete schedules. Restricted ObjBound not global; improvement numeric-scale.')
    item('primal LP-guided neighborhood',newUB=near['new_valid_UB'],preserved=False,classification='VALID_UB_IMPROVEMENT',notes='Original physics/P1; restricted search only; Hamming24 in64..84,300s/Threads1. Whole all-integer physical replay PASS; neighborhood bound not global.')
    table('GAP_ATTRIBUTION.csv',rows)
    exactcross=read(OUT/'CROSS_MASTER_CONVEX.json')['exact_dual_certificate']['lower_bound']
    crossU=read(OUT/'CROSS_MASTER_INTEGER.json')['ObjVal'];crossupper=crossU-exactcross
    conclusion=dict(primary_classification=primary,LB_UB_axis=axis,axis_is_measured_improvement_not_proof_of_total_gap_dominance=True,baseline_UB=UB,baseline_LB=LB,baseline_gap_percent=100*separation/UB,best_valid_UB=UBnew,best_valid_LB=LBnew,final_gap_percent=100*(UBnew-LBnew)/UBnew,valid_structural_LB_gain=structural,valid_total_LB_gain=deltaLB,valid_UB_gain=deltaUB,guaranteed_old_incumbent_excess_removed=deltaUB,percent_of_initial_verified_separation_removed_by_UB=100*deltaUB/separation,remaining_verified_separation=UBnew-LBnew,required_LB_increase_at_unchanged_old_UB=REQUIRED,percent_required_LB_recovered=100*deltaLB/REQUIRED,poor_UB_proved_for_part_of_gap=True,total_gap_dominant_cause_not_proved=True,exact_mode_separator_violation=.2982020917827489,separator_does_not_require_temporal_SOC=True,objective_zero_mode_control_removes_separator=True,local_cross_coupling_integrality_gap_upper_bound=crossupper,full_B_and_B_run=False,physics_changed=False,next_experiment=dict(execute=False,exactly_one=True,kind='bounded_primal_neighborhood',start='UB_LOCAL_NEIGHBORHOOD_POINT.npz',slots=[64,84],Hamming_radius=48,TimeLimit=300,Threads=1,reason='Radius24 was saturated; charging/mobility discrete choices yielded a valid0.0354383 gain whereas certified structural gain was not material. Keep the existing settings and physics; no sweep/fullB&B.'))
    write('ROOT_GAP_ATTRIBUTION_CONCLUSION.json',conclusion)
    report=f'''# M1 gap 원인 귀속 최종 검토

초기 검증된 차이 {separation:.16f} 중 **{deltaUB:.16f} ({100*deltaUB/separation:.4f}%)**를 더 좋은 원래 정수 해로 줄였다. 원래 incumbent의 384개 charge_mode가 전부0이어서 Pch=0이고, 초기/종료SOC가 같으므로 비음수 방전·이동 에너지도0이다. 기존 해는 정적 무효전력 운용만 수행했다. 새 해는 mode14개와 node_activity10개를 바꾸어 유효한 충·방전과 이동을 사용한다. 고정 trajectory 연속 재최적화로는 의미 있는 개선이 없었다.

관측 개선 축은 **{axis}**, 전체 원인에 대한 primary 분류는 **{primary}**다. 개선된 부분은 poor incumbent에서 왔다는 증거가 있지만 남은 {UBnew-LBnew:.16f}의 주원인을 확정하지 못했다. 새 UB도 전역 최적성 증명이 아니다. 이 부분을 전체 gap의 poor-UB dominance로 확대하지 않는다.

PR167의 원래 B9,322개 중 fractional7,454개(약79.96%), node_activity7,070개 및 charge_mode384/384 fractional, 광범위한 위치·route 분할과 MOVE/STAY 혼합 결과를 그대로 보존한다. 입증된 한 슬롯 cut320개/추가nnz17,837의 certified ΔLB0 및 `ROOT_GAP_NOT_EXPLAINED_BY_TESTED_LOCAL_HULLS` 음성 결과도 유지한다. 같은 cut loop를 반복하지 않았다.

새 두block LP는 원래/augmented rows strict replay를 통과했다. 그러나 원래 B 기준 node_activity6,585개 및 charge_mode327개가 같은1e−6 지표에서 fractional이고, 원래 integrality 최대위반0.4546563811314338이다. 이 LP 점을 원래 production UB로 승격하지 않았다. fractionality 수는 점과 solver algorithm에 의존하는 관측이며, 그 자체는 gap 기여 인증이 아니다.

| 검증된 값 | 결과 |
|---|---:|
| 초기 UB | {UB:.16f} |
| 초기 LB | {LB:.16f} |
| 초기 gap `(UB-LB)/UB` | {100*separation/UB:.6f}% |
| 최선 원래 feasible UB | {UBnew:.16f} |
| 최선 valid global LB | {LBnew:.16f} |
| 최종 gap | {100*(UBnew-LBnew)/UBnew:.6f}% |
| 구조 강화 valid LB 증가 | {structural:.16f} |
| 모든 진단의 최대 valid LB 증가 | {deltaLB:.16f} |
| 기존 UB 유지시 필요한 LB 증가 | {REQUIRED:.16f} |
| 필요한 증가 회복률 | {100*deltaLB/REQUIRED:.8f}% |

## 요청한 33개 질문에 대한 답변

1. **Exact base commit:** PR167 `0d423626790a1102d42e6ba84beeb5f7d4ab1d4b`. scientific authority는 PR162 `1d922c91eb27056a5ccc79c92ef18146707099ab` selected exact C3A다.
2. **시작 valid UB:** {UB:.16f}.
3. **시작 valid LB:** {LB:.16f}. 기존 native global bound provenance를 보존했다.
4. **시작 gap:** {100*separation/UB:.6f}%, 차이 {separation:.16f}.
5. **UB 독립 feasibility:** PASS. 전체 C3A rows/bounds/integrality와 저장 inverse를 통한 원래 route/movement/SOC/PQ/PCS/grid/A1 frozen interface를 검사했다. 원래 행·모델·start SHA는 BASE_IDENTITY/UB_VALIDATION에 있다.
6. **고정 discrete 연속 재최적화:** valid UB {fixed['new_valid_UB']:.16f}, 개선 {fixed['delta_UB']:.4g}. numeric-scale로 의미 없는 개선이다. Runtime {fixed['Runtime']:.9f}s. 제한 모델의 native ObjBound는 전역 LB로 사용하지 않았다.
7. **local neighborhood:** 개선됐다. 64..84의 모든 unit node/mode B 중 Hamming≤24, 나머지 B 고정, Threads1/TimeLimit300 사전등록. Runtime {near['Runtime']:.9f}s, 원래 all-integer strict replay 및 전체 physical replay PASS. neighborhood ObjBound {near['native_neighborhood_ObjBound']:.16f}는 global LB가 아니다.
8. **최선 valid UB:** {UBnew:.16f}. reference 대비 {deltaUB:.16f} 개선. 전역 최적성은 주장하지 않는다.
9. **MESS04 69–72 LP projection이 hull 안인가:** NO. 슬롯71 exact rational separator의 양의 위반을 독립 검사했다. native membership INFEASIBLE만을 근거로 하지 않았다.
10. **불가능한 물리 조합:** 각 위치 Pch/Pdis/Q를 실현하는 데 필요한 방전 mode 질량 합0.7945999363442287이 단일 unit의 가용 질량0.49639784456147973을 초과한다. 동일 mode의 위치별 PCS half-polytope를 함께 만족하지 못한다. SOC temporal impossibility나 72 방전의 도달 불가능성은 입증되지 않았다. 목적함수 계수가0인 mode71만0.5036021554385203→0.20540005838815423으로 바꾸면 그 separator가 사라지고 모든 P/Q/route/SOC 및 목적값은 bit-identical이다. 이는 전체4-slot hull membership 증명은 아니다.
11. **Exact hull 크기:** 한 block 추가 rows3,479,007/private cols1,400,080/nnz11,664,103. C3A+한block rows4,061,815/cols1,706,120/nnz17,015,715. 두block rows7,540,822/cols3,106,200/nnz28,679,818. 실제 source PCS16/efficiency/movement coefficients를 사용했다.
12. **정수 궤적 수:** mobility paths149,817 × 16 mode words =2,397,072. transit의 독립 mode cube factoring 후 disjunction232,837. SOC/PQ는 원래 연속 집합이다. 관측 SOC에 고정하지 않았으며 boundary SOC69/SOC73은[440,1080] 자유 interface다. 전체96-slot global extendability hull은 아니다.
13. **정확한 separator:** `Σ_site support_site(Pch,Pdis,Q,stay)+charge_mode[MESS04,71]≤1`. 각 support는 원래 half-PCS row의 비음수 유리수 조합이며 소거 계수 합은 u:-1,qD:0. 정확한 모든 항·원래면·multipliers는 MESS04_69_72_SEPARATION.json. 위반0.2982020917827489. 독립 verifier가 원래 모든 half-polygon vertices와 계수·mutation을 검사했다. 전체 EF는 별도 독립 모든-row verifier PASS.
14. **단일 hull 뒤 valid LB:** {single['new_valid_LB']:.16f}. 독립 finite box 인증0.558165053005941 및 원래 homogeneous domain을 사용한 solver-free 인증{single.get('homogeneous_exact_certificate',{}).get('lower_bound')} 모두 기존 LB보다 약하다.
15. **단일 창 ΔLB:** {single['delta_LB']:.16f}. approximate primal0.5687610859560673을 LB로 승격하지 않았다.
16. **필요 LB 증가 회복률:** 단일 창0%; 전체 관측 {100*deltaLB/REQUIRED:.8f}%. 분모는 기존 UB 유지시0.097357243906476이며 새로운 UB의 목표와 혼합하지 않았다.
17. **substitution:** 새 approximate point에서 같은 grid row의 MESS04 효과를 다른 unit들이 보상하는9개 관측이 있다. MESS03 슬롯71 defect0.2934331526359996이 가장 커서 선택했다. 단일 point RAW FAIL이므로 엄격 feasible post-hull optimum의 대체라고 증명한 것은 아니다.
18. **multiwindow generalization:** 이 관측에 따라 허용된 한 번, MESS04+MESS03의69–72 두block만 실행했다. 최대4block 이내. 같은 exact joint hull이며 반복 one-slot cut 전략을 사용하지 않았다.
19. **multiwindow valid LB:** {multi['new_valid_LB']:.16f}, ΔLB {multi['delta_LB']:.16f}. ObjVal {multi.get('ObjVal')}, 실제 native ObjBound {multi.get('native_ObjBound')}, exact box certificate {multi.get('exact_certificate',{}).get('lower_bound')}, homogeneous domain certificate {multi.get('homogeneous_exact_certificate',{}).get('lower_bound')}. Runtime {multi['Runtime']}s/Work {multi['Work']}. RAW 결과는 아래 표와 원본 JSON에 보존한다.
20. **cross-MESS/grid coupling 유의성:** 실제72 동시 active branch는 sw1A+l3A이며 l10A는71/79에서 relevant하다. 두branch 모든 retained16faces/actual C3A binding closure/4units×24sites×2modes의 작은 exact local injection master를 검사했다. convex certificate {exactcross:.16f}, local integer feasible objective {crossU:.16f}. local integrality gap의 상한 {crossupper:.16f}<0.001. MIPGap0.005에서 얻은 feasible integer objective를 정확한 최적값으로 부르지 않는다. 이 특정 one-time coupling은 작으나 전체 horizon/다른 grid coupling은 배제되지 않았다.
21. **긴 horizon 진단:** 단일4-slot 인증 증가0과 다음 active75–76으로 이어지는 SOC/mobility 영향을 근거로 한 번만69–76,8슬롯 선택적 정수화했다. full8-slot hull은 아니다. 8슬롯은 root crossover 도중 time limit으로 끝났으며 native bound0.3955868065146082는 baseline보다 약하다. 따라서 장기 reachability의 실제 bound 효과는 미확정이다.
22. **처음 material 강화가 생기는 horizon:** 이번 테스트에서 발견되지 않았다.8슬롯 root 미완료와4슬롯 bounded search 때문에 모든 장기 원인을 배제할 수 없다.
23. **선택적 정수화 결과:** coupling master를 포함해 정확히3회. original4-slot100B와8-slot200B를 각각300초/Threads1로 지정했다. 아래 실제 Runtime/status/bound를 보고하며 partial point를 production UB로 승격하지 않았다. material ΔLB≥0.001은 관측하지 못했다.
24. **다기간 궤적 약함에 귀속된 양:** 검증된 structural recovery {structural:.16f}. 위반 존재와 global gap 기여는 구별한다. 첫 hull의 수치 실패와 bounded diagnostics 때문에 다기간 약함의 실제 기여를0이라고 증명한 것은 아니다.
25. **poor UB에 귀속된 양:** 최소 {deltaUB:.16f}, 초기 검증 차이의 {100*deltaUB/separation:.4f}%. 개선된 원래 feasible point가 그만큼 기존 incumbent의 excess를 증명한다. mode14/node10 변경의 개별 기여를 분해한 실험은 하지 않았다.
26. **주원인:** 관측 개선은 UB 축이 우세하나 전체 gap의 dominant cause는 미확정이다. 원래 incumbent 선택의 명확한 약점, 국소 mode/위치/PQ defect, 수치 인증 한계가 함께 관측됐다. 숫자만으로 multi-period/cross/long-horizon/numerical dominance를 주장하지 않는다.
27. **모든 정수 schedule에 exact/valid한가:** YES, source 계수에 대한 local hull/분리 부등식은 모든 원래 global integer schedule의 projection을 보존한다. exactness는 자유 경계 local physical set에 관한 것이며 global96-slot hull 주장과 다르다. coupling master는 약한 전역 relaxation, primal neighborhood는 의도된 검색 제한이다.
28. **물리 변경:** NO. MESS수/route/time/energy/PQ/PCS/SOC/효율/초기·최종/A1/voltage/rating/P1/P2를 변경하지 않았다. EF 추가와 attribution용 integrality relaxation만 사용했다. 원래 모델 SHA 및 이전 namespace 해시 unchanged.
29. **full B&B:** NO. 새로운3600초/2시간 fullMILP/Benders/DW/B&P/tournament 없음. 허용된 제한 neighborhood1회와 selective3회 외 정수 solve 없음.
30. **다음 해결 방식:** improved primal search를 우선 권고한다. 정확히 하나의 다음 실험은 새 valid incumbent에서 같은64..84 블록/Hamming radius48/300초/Threads1, 설정·물리 유지다. 기존radius24가 포화됐고 valid UB 개선 증거가 있다. **이 실험은 실행하지 않았다.** compact/global trajectory/B&P를 채택할 dominance 증거는 아직 부족하다. static design만 TRAJECTORY_FORMULATION_DESIGN.md에 있다.
31. **최종 분류:** primary **{primary}** 하나. LB/UB 관측 개선 축 **{axis}**. 전체 원인 확정과 같은 의미가 아니다.
32. **최종 commit SHA:** 이 보고서와 manifest를 포함한 최종 PR HEAD. 자체 commit SHA를 그 commit 안에 쓰는 순환을 피하며 정확한 값은 PR body 및 최종 응답에 별도로 기록한다.
33. **Draft PR:** {pr_url or '생성 전; 최종 봉인에서 URL 기록'}.

## 수치·capture 제한

| 점 | strict original C3A | strict augmented | valid LB 권위 |
|---|---|---|---|
| PR167 pureLP | FAIL2.805600374244932e-8 | 해당 없음 | 기존 native global LB 보존 |
| MESS04 단일 창 | FAIL2.3785754346083987e-5 | FAIL0.01889765176353009 | exact certificate0.558165053005941, carry LB_ref |
| multiwindow | {multi.get('original_C3A_replay')} | {multi.get('raw_augmented_replay')} | 두 exact certificate와 기존 LB 최대값 |

단일 창은 native optimize를 정확히 한 번 끝낸 후 제 postprocessing 코드의 types 누락으로 receipt 작성이 실패했다. primal과 dual/RC/slack은 이미 저장됐으며 읽기 전용으로 회수했다. native API ObjBound와 정확한 API Runtime/Work는 손실됐고, Runtime826.38/Work1200.23은 완료 로그의 **소수2자리 값**이다. barrier 마지막 dual 열을 ObjBound로 추정하지 않았다. 재solve하지 않았으며 실패 코드/로그를 failed_capture_provenance에 보존했다. 이 capture 항목은 미완전이며 all-PASS로 숨기지 않는다.

두block의 새 LP에서는 이 correctness issue 때문에 Crossover0→1만 변경했고 tolerance1e-8은 그대로다. native OPTIMAL은 설정 tolerance를 기준으로 한 종료이며 strict raw PASS와 같지 않다. [Gurobi status 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/statuscodes.html), [ObjBound 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound).

| 선택적 진단 | Status | native Runtime(s) | native ObjBound | valid global LB |
|---|---:|---:|---:|---:|
'''
    for r in selective:report+=f"| {r['case']} | {r['Status']} | {r['Runtime']} | {r['native_ObjBound']} | {r['valid_global_LB']} |\n"
    ci=read(OUT/'CROSS_MASTER_INTEGER.json');report+=f"| CROSS_MASTER_INTEGER | {ci['Status']} | {ci['Runtime']} | {ci['native_ObjBound']} | {max(LB,ci['conservative_global_LB'])} |\n"
    report+='\n각 native TimeLimit은300이며 종료 정리로 Runtime이 limit을 초과하면 실제 값을 그대로 보존한다. 실행 중인 다른 A-stage worker는 종료하거나 수정하지 않았다. concurrency snapshot을 저장했으며 겹친 Runtime을 통제 성능 비교로 사용하지 않는다.\n\n## 저장 LP의 실제 물리·grid 수치\n\n다음 값은 저장된 approximate LP의 물리 좌표이며 valid UB/LB가 아니다. 단순 row 기여와 counterfactual gap 귀속을 구별한다.\n\n| 슬롯 | SOC 전→후(kWh) | Pch(kW) | Pdis(kW) | Q(kVAr) | 가중 이동에너지(kWh) |\n|---|---|---:|---:|---:|---:|\n'
    census=read(OUT/'MESS04_PHYSICAL_WINDOW_CENSUS.json')
    for r in census['rows']:report+=f"| {r['slot']} | {r['SOC_before']:.9f}→{r['SOC_after']:.9f} | {r['Pch']:.9f} | {r['Pdis']:.9f} | {r['Q']:.9f} | {r['movement_energy']:.12f} |\n"
    report+='\n69 출발 route 질량은 IDC12→IDC01 0.13388158283044294(원래에너지3.1203025798640622), IDC12→STA02 0.05229735420371386(3.090518352649966), STA12→IDC03 0.07149082674352064(2.05222168563522)다. 원래arrival70/connect71을 유지한다. 슬롯71의 주요 stay/location 질량은 다음과 같다. 모든 작은 질량과 exact separator 항은 원본 JSON에 남긴다.\n\n| site | stay 질량 | Pch | Pdis | Q | 필요한 방전mode 질량 |\n|---|---:|---:|---:|---:|---:|\n'
    for r in read(OUT/'MESS04_69_72_COMMON_MODE_SEPARATION.json')['strongest']['details']:
        v=r['input_values']
        if v['y']>1e-5:report+=f"| {r['site']} | {v['y']:.12f} | {v['C']:.9f} | {v['D']:.9f} | {v['Q']:.9f} | {r['required_discharge_mode_mass']:.12f} |\n"
    report+='\nMESS04의 t72 sw1A 대표 active face 기여는 Pdis −0.0246705821384319, Q +0.0005768856148293971, Pch +3.298340163974514e−11, 합 −0.024093696490619102이다. 모든 unit과 frozen grid 항을 합친 required rho는0.568711942987684다. 이 기여 자체는 hull 밖 행동의 causal advantage가 아니다. mode-only 대조는 이 P/Q 기여를 전혀 바꾸지 않고 separator를 제거한다. l10A의71/79와 l3A의72를 포함한 실제 동시 active faces 및 새 approximate 점의 보상은 CRITICAL_GRID_COUPLING_AUDIT.csv / MESS04_GRID_EFFECT.json에 보존했다.\n\n`GAP_ATTRIBUTION.csv`는 valid 회복만 집계한다. `VERIFICATION.json`은 proof/hash/workflow와 strict raw 수치/capture 결과를 분리한다. `SHA256_MANIFEST.json`은 자신과 Python cache 및 lossless 분할로 대체한 local ZIP을 제외한 파일을 봉인한다. optimize 포함 코드는 ONCE 토큰을 삭제하거나 재실행하지 않는다.\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf-8')
    verify(single,multi,near,selective,pr_url)

def verify(single,multi,near,selective,pr_url):
    identity=read(OUT/'BASE_IDENTITY.json');history_bad=[p for p,h in identity['previous_namespace_hashes'].items() if sha(ROOT/p)!=h]
    assert not history_bad
    assert sha(history_authority.SOURCE/'FULL_A.npz')==history_authority.FULL_A_SHA
    assert sha(history_authority.SOURCE/'FULL_DATA.npz')==history_authority.FULL_DATA_SHA
    copied=read(OUT/'SOURCE_AUTHORITY_COPIES.json');assert copied['PASS']
    for source in copied['source_files_copied_byte_identically']:
        assert sha(OUT/source['committed_path'])==source['SHA256']
        if Path(source['original_path']).exists():assert sha(source['original_path'])==source['SHA256']
    assert read(OUT/'UB_VALIDATION.json')['PASS'] and read(OUT/'LB_VALIDATION.json')['PASS']
    for label in ('MESS04_69_72','MESS03_69_72'):
        h=read(OUT/(label+'_HULL_AUTHORITY.json'));v=read(OUT/(label+'_INDEPENDENT_VERIFICATION.json'))
        assert v['PASS'] and not v['production_constructor_imported'] and v['optimize_calls']==0
        assert sha(OUT/(label+'_EF_MATRIX.npz'))==h['matrix_SHA256'] and sha(OUT/(label+'_EF_DATA.npz'))==h['data_SHA256']
        assert sha(OUT/(label+'_INTEGER_TRAJECTORIES.json'))==h['trajectories_SHA256']
    assert read(OUT/'CAUSAL_CONTROLS_INDEPENDENT_VERIFICATION.json')['PASS']
    assert read(OUT/'CROSS_MASTER_INDEPENDENT_VERIFICATION.json')['PASS']
    assert not read(OUT/'MULTIWINDOW_ORIGINAL_INTEGRALITY_AUDIT.json')['original_integrality_replay']['PASS']
    for stage in ('SINGLE_WINDOW_STRENGTHENED_LP','MULTIWINDOW_STRENGTHENED_LP'):
        cert=read(OUT/(stage+'_HOMOGENEOUS_VALID_LB_CERTIFICATE.json'))
        total=sum(F(cert[k]) for k in ('exact_pi_rhs_and_constant','exact_original_box_correction','exact_homogeneous_private_correction'))
        assert total==F(cert['exact_rational']) and F.from_float(cert['lower_bound'])<=total
        assert cert['optimize_calls']==0 and cert['valid_for_every_original_integer_schedule']
        bundle=OUT/(stage+'_DUAL_RC_SLACK.npz')
        if bundle.exists():
            with np.load(bundle) as z:dual=z['dual']
        else:
            with np.load(OUT/'MULTIWINDOW_CAPTURE_DUAL.npz') as z:dual=z['dual']
        assert hashlib.sha256(dual.tobytes()).hexdigest()==cert['input_dual_array_bytes_SHA256']
    assert near['original_all_integer_replay']['PASS'] and near['physical_replay']['PASS']
    A,d,_=load()
    with np.load(OUT/'UB_LOCAL_NEIGHBORHOOD_POINT.npz') as z:point=z['x']
    newraw=replay(A,d,point,True);assert newraw['PASS']
    tokens=[read(p) for p in sorted(OUT.glob('*_ONCE.json'))]
    expected={'UB_FIXED_DISCRETE_REOPT','UB_LOCAL_NEIGHBORHOOD','MESS04_69_72_MEMBERSHIP','SINGLE_WINDOW_STRENGTHENED_LP','MULTIWINDOW_STRENGTHENED_LP','CROSS_MASTER_CONVEX','CROSS_MASTER_INTEGER','SELECTIVE_MESS04_69_72','SELECTIVE_MESS04_69_76'}
    actual={t['stage'] for t in tokens};assert actual==expected and len(tokens)==9 and all(t['optimize_calls']==1 for t in tokens)
    ledger=[]
    for token in tokens:
        stage=token['stage'];filename='UB_LOCAL_NEIGHBORHOOD_RESULT.json' if stage=='UB_LOCAL_NEIGHBORHOOD' else stage+'.json'
        record=read(OUT/filename)
        ledger.append(dict(stage=stage,token_UTC=token['UTC'],optimize_calls=1,Method=token['settings'].get('Method'),Threads=token['settings'].get('Threads'),TimeLimit=token['settings'].get('TimeLimit'),Crossover=token['settings'].get('Crossover'),Status=record['Status'],native_Runtime=record['Runtime'],native_Work=record['Work'],Runtime_precision='native completion log rounded2 decimals; API missing' if stage=='SINGLE_WINDOW_STRENGTHENED_LP' else 'native API',native_ObjVal=None if stage=='SINGLE_WINDOW_STRENGTHENED_LP' else record.get('ObjVal'),saved_point_objective=record.get('ObjVal'),native_ObjBound=record.get('native_ObjBound',record.get('native_neighborhood_ObjBound')),overlap_not_controlled_benchmark=True))
    table('EXECUTION_LEDGER.csv',ledger)
    phase=[]
    for r in selective:
        log=(OUT/(r['case']+'.log')).read_text(encoding='utf-8',errors='replace')
        phase.append(dict(case=r['case'],root_completed='Root relaxation: objective' in log,root_crossover_timed_out='Crossover changed status from Optimal to Time Limit' in log,original_integer_optimality_proved=False,native_TimeLimit=r['settings']['TimeLimit'],actual_Runtime=r['Runtime'],finish_overrun_seconds=max(0,r['Runtime']-r['settings']['TimeLimit']),native_ObjBound=r['native_ObjBound'],valid_global_LB=r['valid_global_LB'],absence_of_material_bound_gain_does_not_exclude_mechanism=True))
    write('SELECTIVE_PHASE_AUDIT.json',dict(optimize_calls=0,source='Completed native logs and saved attributes, not rerun',results=phase))
    native_phases=[]
    for stage in ('UB_FIXED_DISCRETE_REOPT','UB_LOCAL_NEIGHBORHOOD','SINGLE_WINDOW_STRENGTHENED_LP','MULTIWINDOW_STRENGTHENED_LP','SELECTIVE_MESS04_69_72','SELECTIVE_MESS04_69_76'):
        logname='UB_LOCAL_NEIGHBORHOOD.log' if stage=='UB_LOCAL_NEIGHBORHOOD' else stage+'.log'
        lines=(OUT/logname).read_text(encoding='utf-8',errors='replace').splitlines()
        native_phases.append(dict(stage=stage,native_scale_presolve_factor_and_warning_lines=[s for s in lines if any(key in s for key in ('Matrix range','Objective range','Bounds range','RHS range','Warning:','Presolve time:','Presolved:','Factor NZ','Factor Ops','Barrier solved','Crossover time:','Crossover changed status','Restart crossover','variables added to crossover basis','Root relaxation:','Best objective'))],scale_or_warning_lines_not_used_as_proof_of_gap_dominance=True))
    write('NATIVE_NUMERICAL_PHASE_AUDIT.json',dict(optimize_calls=0,source='Existing completed native logs',stages=native_phases,Kappa_not_requested_by_new_solve=True))
    for r in selective+[near]:assert r['settings']['TimeLimit']==300 and r['settings']['Threads']==1
    assert single['optimize_calls']==1 and multi['optimize_calls']==1
    snapshot('CONCURRENCY_FINAL.json')
    import psutil
    running=[]
    for process in psutil.process_iter(['pid','cmdline']):
        try:
            command=' '.join(process.info['cmdline'] or [])
            if any('v42_m1_gap_rootcause_20261007'+separator+name in command for separator in ('/','\\') for name in ('multiwindow.py','selective_blocks.py','solve_window.py','solve_neighborhood.py','solve_dispatch.py','coupling_master.py')):
                if Path(process.cwd()).resolve()==ROOT.resolve():running.append(process.info['pid'])
        except (psutil.AccessDenied,psutil.NoSuchProcess):pass
    assert not running, 'OWN_AUTHORIZED_SOLVER_WORKER_STILL_RUNNING'
    missing=[p for p in REQUIRED_FILES if p not in ('VERIFICATION.json','SHA256_MANIFEST.json') and not (OUT/p).is_file()];assert not missing
    numeric=dict(PR167_proxy_raw_PASS=False,single_original_raw=single['original_C3A_replay'],single_augmented_raw=single['raw_augmented_replay'],multi_original_raw=multi.get('original_C3A_replay'),multi_augmented_raw=multi.get('raw_augmented_replay'),best_UB_original_all_integer_raw=newraw)
    write('VERIFICATION.json',dict(workflow_and_proof_integrity_PASS=True,all_raw_numeric_points_PASS=False,all_required_single_window_native_API_capture_complete=False,single_window_ObjBound_missing=True,native_capture_failure_disclosed=True,required_artifacts_present=True,historical_namespaces_checked=len(identity['previous_namespace_hashes']),historical_namespaces_unchanged=True,model_data_start_hashes_unchanged=True,independent_hull_verification_PASS=True,independent_separator_and_causal_control_PASS=True,numerical_replays=numeric,authorized_optimize_call_count=len(tokens),calls=sorted(expected),selective_integrality_call_count=3,primal_neighborhood_call_count=1,generalization_call_count=1,full_B_and_B_run=False,physics_changed=False,next_repair_experiment_executed=False,other_workers_untouched=True,overlap_not_used_as_performance_benchmark=True,Draft_PR_URL=pr_url,final_HEAD_authority='Final PR remote HEAD / PR body; self-referential SHA excluded from file content'))
    excluded=set()
    if (OUT/'MULTIWINDOW_CAPTURE_TRANSPORT.json').exists():
        transport=read(OUT/'MULTIWINDOW_CAPTURE_TRANSPORT.json');assert transport['PASS']
        excluded.add(transport['original_local_bundle'])
        for piece in transport['pieces']:assert sha(OUT/piece['file'])==piece['file_SHA256']
    files=[p for p in OUT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='SHA256_MANIFEST.json' and p.name not in excluded]
    write('SHA256_MANIFEST.json',dict(algorithm='SHA256',scope='This namespace excluding manifest itself, Python caches and optional local oversize ZIP bundle represented losslessly by committed pieces',excluded_local_redundant_bundles=sorted(excluded),files={p.relative_to(OUT).as_posix():sha(p) for p in sorted(files)}))
    assert all((OUT/p).is_file() for p in REQUIRED_FILES)
    print('FINAL_ATTRIBUTION_SEALED',read(OUT/'ROOT_GAP_ATTRIBUTION_CONCLUSION.json'),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pr-url',default='');main(p.parse_args().pr_url)
