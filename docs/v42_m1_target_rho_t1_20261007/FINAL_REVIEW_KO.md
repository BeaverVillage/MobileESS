# M1 T1 exact feasibility 최종 검토

판정: **TARGET_RHO_T1_TIME_LIMIT_INCONCLUSIVE**

1. **Exact base HEAD**: 5d5718f5cfdc173eb2dd0a4c9f1ee3da8a833667

2. **Exact T1**: 0.5996810901851135

3. **전체 C3A scientific domain 보존**: YES. 모든 원래 582,808행/306,040열/B9322/C296718 및 모든 경계·타입을 그대로 유지했다.

4. **추가 valid cuts**: 364

5. **Cross-MESS cover cuts**: 236개: single-time support30 + integer2 + two-time support204

6. **Multi-time route/SOC cuts**: 332개: two-time fleet support204 + route conflicts128; two-time integer covers0, SOC-only conflicts0. 두시점 커버204는 5번에도 포함된다.

7. **최대 저장 LP 위반**: -0.12935067925339261; 1e-8 초과 위반0개. 강화 효과를 입증하지 못했다.

8. **Native status**: TIME_LIMIT (9); TARGET_RHO_T1_TIME_LIMIT_INCONCLUSIVE

9. **Runtime**: 600.033999920s; Work=706.326092449; build=5.135291s는 native TimeLimit 밖이다.

10. **Root 완료**: LP 완료=YES, Runtime timestamp=349.42400002479553; nonroot 증거=None

11. **Nodes**: 1.0

12. **Feasible witness**: NO

13. **Feasible일 때 새 valid UB**: UB 유지=0.6306505800203936

14. **Full replay**: 해 없음: 미적용

15. **Infeasible일 때 T1 valid global LB**: NO: LB 유지=0.5687116003498334

16. **새 global interval**: [0.5687116003498334, 0.6306505800203936]

17. **새 global gap**: 9.821441798810% = (UB-LB)/UB

18. **Old D-W/B&P/local-hull rerun**: NO

19. **Physics 변경**: NO. 원래 objective는 witness rho 평가에 보존하고, 요청된 실험 objective만0으로 설정했다.

20. **Parameter sweep**: NO. 정확히 native optimize1회,600초,Threads1.

21. **정확히 하나의 next action**: 같은 T1·전체 도메인·600초를 유지하고 MIPFocus만3→1로 바꾸는 단일 feasibility pilot을 별도로 사전등록할 것. 이번 작업에서는 실행하지 않는다.

22. **Final HEAD**: 이 파일을 포함하는 최종 commit의 HEAD는 PR 본문 Final HEAD와 최종 대화에 40자리로 기록한다. Native 실행 소스 HEAD=9dfb1165c857d63d5ca57d87293ae6be4e703254

23. **Draft PR URL**: https://github.com/BeaverVillage/MobileESS/pull/173

정적 검증: 30개 원래 grid row, 2880개 exact support dual, 9038개 compact binary node mass, 6852개 변조 거절, 31714개 경로 adversarial 검사 PASS. 원래 정수 reference2개도 새 컷을 만족했다.

Presolve 15.08초; presolved 322899행/283230열/3908122nnz. Barrier iterations=19; crossover 시작/끝=75.21900010108948/348.88700008392334. Factor NZ≈44260000.0, factor memory≈600.0MB. 표본 peak RSS=2669395968bytes, process lifetime peak working set=2741657600bytes. 미노출 값은 null로 남겼다.

계수 범위 경고는 PR167 pure LP와 PR171 native에서도 동일하게 존재했다. 원래 행·계수는 native에서 값이 정확히 같고, 이 advisory와 실제 수치 오류를 구분한 postsolve review를 보관했다. native feasibility ObjBound는 rho의 global LB로 사용하지 않았다. TIME_LIMIT/INTERRUPTED이면 두 global bounds를 유지한다.

최초 관측된 OPTIMAL root MIPNODE(Runtime=505.3770000934601)에서 새 컷 active=0, 최대 잔차=-0.09573203453200707. 최초 root relaxation 로그의 해와 동일하다고 가정하지 않는다. Root LP는 완료됐지만 nonroot 진입/전체 root 처리 완료 증거는 없다. Bound 개선과 T1 infeasible/feasible 증명 모두 미달이다.

solve 전 문자열 배열 구성 오류1회는 optimize0회인 preflight에서 발생했고 수정 후 실행했다. 컷 후보 정적 구성·검증의 반복은 추가 solve가 아니다. OPTIMIZE_ONCE.json과 native log가 유일한 native 호출을 기록한다. 새 solve, threshold, May/P2/M2/A2는 실행하지 않았다.
