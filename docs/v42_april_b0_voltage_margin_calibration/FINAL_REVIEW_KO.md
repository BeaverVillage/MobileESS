# April B0 voltage margin calibration 검토

실험을 authority gate에서 중단했다. 아래 미산출은 실패 수치나 zero residual을 의미하지 않는다.

**Q1. 왜 April을 calibration으로 선택했는가?**

A. 사용자가 April calibration / May holdout을 사전 지정했다. 결과를 보고 선택하지 않았다.

**Q2. 왜 May는 사용하지 않았는가?**

A. Out-of-sample holdout을 보존하기 위해 calibration 경로에서 May 결과를 열거나 실행하지 않았다.

**Q3. B0 authority는 무엇인가?**

A. PR117의 B0/C0 forecast 인터페이스는 확인되지만 operational B0 정의·Planning·Actual authority는 확정되지 않았다. B0_AUTHORITY_AUDIT.json A–G 참조.

**Q4. B0 Actual authority가 확인됐는가?**

A. 아니오. 일반 frozen replay validator는 있지만 B0 전용 실행 정책과 April Actual mapping이 없다. 따라서 gate FAIL이다.

**Q5. anonymous allocation을 사용했는가?**

A. 과학 실행을 하지 않았고 anonymous LP를 schedule로 승격하지 않았다.

**Q6. future information leakage가 있는가?**

A. 이번 task는 실험과 reconstruction을 하지 않아 future 입력을 사용하지 않았다. 미구현 B0 pipeline의 causal boundary가 검증됐다는 뜻은 아니다.

**Q7. V_PLAN은 무엇인가?**

A. Planning surrogate voltage다. 이번 task에서는 생성되지 않았다.

**Q8. V_DA_AC는 무엇인가?**

A. Frozen plan과 day-ahead forecast로 Fresh OpenDSS를 실행한 offline calibration diagnostic voltage다. 생성되지 않았다.

**Q9. V_DA_AC가 operational stage인가?**

A. 아니오. 운영 gate로 추가하지 않는다. 진단 실패는 plan 수정의 근거가 아니다.

**Q10. V_DDAY_AC는 무엇인가?**

A. 동일 frozen plan에 realized D-Day inputs를 적용한 Fresh OpenDSS voltage다. 생성되지 않았다.

**Q11. 동일 frozen schedule인가?**

A. 실제 schedule이 없어 실행 동일성을 주장할 수 없다. 계약 테스트는 SHA 일치를 강제한다.

**Q12. P/Q repair를 했는가?**

A. 아니오. P/Q·route·known schedule repair와 변경을 모두 금지했다.

**Q13. full reoptimization했는가?**

A. 아니오. Actual global optimization은 금지되고 이번 task optimizer 호출은 0이다.

**Q14. e_model은?**

A. V_DA_AC − V_PLAN이다. 관측치가 없어 미산출이다.

**Q15. e_forecast는?**

A. V_DDAY_AC − V_DA_AC이다. 관측치가 없어 미산출이다.

**Q16. e_total은?**

A. V_DDAY_AC − V_PLAN이다. 관측치가 없어 미산출이다.

**Q17. identity가 성립하는가?**

A. 동일 alignment에서 e_total ≈ e_model + e_forecast를 1e−12 absolute tolerance로 검사한다. Unit fixture만 PASS이며 실제 April identity 검증은 NOT_RUN이다.

**Q18. upper residual은?**

A. max(0, V_DDAY_AC − V_PLAN)이다.

**Q19. lower residual은?**

A. max(0, V_PLAN − V_DDAY_AC)이다.

**Q20. 왜 asymmetric margin을 허용하는가?**

A. 상승·하락 오차의 크기와 분포가 같다는 근거가 없으므로 두 방향을 따로 계산한다.

**Q21. pointwise residual은?**

A. 각 date/node/phase/time 관측치의 directional residual 분포다. Correlated sample을 IID로 주장하지 않는다.

**Q22. day worst residual은?**

A. 하루 내 모든 node-phase-time의 r_up, r_down 각각의 최댓값이다. 하루를 표본 단위로도 보고한다.

**Q23. 90% quantile은?**

A. 사전등록 q=.90이며 실제 값은 미산출이다.

**Q24. 95% quantile은?**

A. 사전등록 q=.95이며 실제 값은 미산출이다.

**Q25. 97.5% quantile은?**

A. 사전등록 q=.975이며 실제 값은 미산출이다.

**Q26. 99% quantile은?**

A. 사전등록 q=.99이며 실제 값은 미산출이다. 네 quantile 모두 보고하며 결과로 하나를 선택하지 않는다.

**Q27. current 0.005는 어느 수준인가?**

A. 관측치가 없어 empirical percentile을 산출할 수 없다. 값을 추정하지 않았다.

**Q28. 0.005가 너무 큰가?**

A. 판단 불가다. April 잔차와 별도 holdout 검증이 필요하다.

**Q29. 0.005가 너무 작은가?**

A. 판단 불가다. 상·하 방향별 pointwise/day-worst 검증이 필요하다.

**Q30. model error와 forecast error 중 무엇이 큰가?**

A. 실제 residual이 없어 미판정이다. 사전등록된 daily/overall RMSE로 비교한다.

**Q31. B0 S0 feasible인가?**

A. NOT_RUN / null이다. B0 infeasible로 분류하지 않는다.

**Q32. B0 S2 feasible인가?**

A. NOT_RUN / null이다. S2 sensitivity를 실행하지 않았다.

**Q33. S2 fail이면 physical fail인가?**

A. 아니오. S0 feasible/S2 infeasible이면 B0_PHYSICALLY_FEASIBLE=true, B0_ROBUST_MARGIN_FEASIBLE=false로 구분한다.

**Q34. Planning physical band는?**

A. Primary S0는 0.95–1.05 pu다. 다만 기존 authoritative B0 fixed definition이 있으면 먼저 따른다.

**Q35. D-Day physical band는?**

A. 0.95–1.05 pu와 line/transformer hard limits다.

**Q36. April physical violation count는?**

A. 미산출이다. 실행 0일을 violation 0으로 표현하지 않는다.

**Q37. worst lower event는?**

A. 관측치가 없어 node/phase/time은 null이다.

**Q38. worst upper event는?**

A. 관측치가 없어 node/phase/time은 null이다.

**Q39. line/transformer violation은?**

A. Fresh AC를 실행하지 않아 미측정이다. PASS를 주장하지 않는다.

**Q40. May를 봤는가?**

A. Calibration 경로에서는 May scientific output 값을 열지 않았다. Source authority 문서의 경로·Git blob metadata와 inherited regression evidence 점검은 margin fitting과 분리된다.

**Q41. May margin tuning을 했는가?**

A. 아니오. MAY_USED_FOR_CALIBRATION=false다.

**Q42. calibrated candidate band는?**

A. 0.95+delta_down(q), 1.05−delta_up(q)다. 실제 후보는 0개이며 미산출이다.

**Q43. symmetric인가 asymmetric인가?**

A. 두 방향별 값을 허용한다. 실제 April 값이 없으므로 이번 task에서 어느 형태도 추정하지 않는다.

**Q44. final margin을 확정했는가?**

A. 아니오. FINAL_MARGIN_ACCEPTED=false다.

**Q45. 왜 아직 확정하면 안 되는가?**

A. B0 authority와 April 실행이 먼저 필요하며 April 완료만으로도 최종 확정은 불가하다. 별도 May holdout이 필요하다.

**Q46. 다음 May experiment는 무엇인가?**

A. Authority와 April 후보를 먼저 확정·동결한 뒤 별도 PR에서 untouched May 입력으로 frozen replay/physical 검증을 한다. 이번 PR에서는 실행하지 않는다.

**Q47. B1/Proposed는 이번에 실행했는가?**

A. 아니오. B0 FAIL의 대체 실험을 하지 않았다.

**Q48. V42 architecture를 변경했는가?**

A. 아니오. 새 namespace만 추가하며 PR117 기존 tracked bytes와 다른 branch를 보존한다.

**Q49. Day-Ahead AC validation을 부활시켰는가?**

A. 아니오. V_DA_AC는 offline diagnostic만 허용한다. Operational chain은 Planning → freeze → D-Day Actual → Fresh OpenDSS다.

**Q50. final verdict는?**

A. BLOCKED_B0_ACTUAL_AUTHORITY다. B0_APRIL_EXECUTION_AUTHORIZED=false, 실행 0일, 실제 voltage/residual/quantile은 미산출이다.
