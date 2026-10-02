# Final review — current V42 April B0

## Q1. B0에도 데이터센터가 있는가?

A. 계약상 AIDC와 workload 모두 존재한다. Physical 실행 검증은 아직 NOT_RUN이다.

## Q2. B0 AIDC power는 0인가?

A. 0으로 만들지 않는다. 실제 IT/PCC energy는 미산출이다.

## Q3. B0 workload를 모두 서비스하는가?

A. 모든 D-1 row를 보존했다. GPU demand 누락으로 실제 서비스 완료는 검증하지 못했다.

## Q4. B0와 B1의 차이는?

A. 동일 common reference를 사용하며 B1만 허용된 flexibility를 최적화한다.

## Q5. B0 MESS는?

A. OFF이며 P/Q/movement와 optimization calls는 0이다.

## Q6. 이번에 B1을 실행했는가?

A. 아니다. B1 NOT_RUN이다.

## Q7. 이번에 B2/B3를 실행했는가?

A. 아니다. B2/B3 NOT_RUN이다.

## Q8. 왜 B0만 먼저 보는가?

A. 공통 baseline의 Planning→Actual error부터 측정하기 위함이다. 현재 workload authority를 보완해야 한다.

## Q9. V_PLAN은?

A. 같은 B0 reference와 forecast에 대한 current V42 planning voltage다. 이번에는 미산출이다.

## Q10. V_DA_AC는?

A. 같은 frozen plan과 forecast의 Fresh OpenDSS diagnostic voltage다. 이번에는 NOT_RUN이다.

## Q11. V_DA_AC가 operational stage인가?

A. 아니다. OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=true이며 operational gate가 아니다.

## Q12. V_DDAY_AC는?

A. realized inputs와 실제 occupancy를 재구성한 physical AC voltage다. 이번에는 NOT_RUN이다.

## Q13. 동일 schedule인가?

A. 동일 SHA를 요구하는 검사는 구현·테스트했다. 실제 두 replay의 SHA 일치 증거는 아직 없다.

## Q14. Actual reoptimization이 있는가?

A. 없다. 호출 0이며 replay 자체도 NOT_RUN이다.

## Q15. P repair가 있는가?

A. 없다. 호출 0이다.

## Q16. Q repair가 있는가?

A. 없다. 호출 0이다.

## Q17. e_model은?

A. V_DA_AC−V_PLAN이다. 값은 미산출이다.

## Q18. e_forecast는?

A. V_DDAY_AC−V_DA_AC이다. 값은 미산출이다.

## Q19. e_total은?

A. V_DDAY_AC−V_PLAN이다. 값은 미산출이다.

## Q20. identity는?

A. 동일 axis에서 total=model+forecast를 voltage scale 8 ULP 이내로 검증한다. 실제 samples는 없다.

## Q21. upper residual은?

A. max(0,e_total)이다. lower와 분리한다.

## Q22. lower residual은?

A. max(0,−e_total)이다. upper와 분리한다.

## Q23. pointwise Q90?

A. q=0.90을 사전등록했다. pointwise delta_up/down은 null이다.

## Q24. Q95?

A. q=0.95를 사전등록했다. pointwise delta_up/down은 null이다.

## Q25. Q97.5?

A. q=0.975를 사전등록했다. pointwise delta_up/down은 null이다.

## Q26. Q99?

A. q=0.99를 사전등록했다. pointwise delta_up/down은 null이다.

## Q27. day-worst Q90?

A. 각 day의 방향별 최대 residual의 Q90이다. 실행 day가 없어 null이다.

## Q28. day-worst Q95?

A. 각 day의 방향별 최대 residual의 Q95이다. 실행 day가 없어 null이다.

## Q29. day-worst Q97.5?

A. 각 day의 방향별 최대 residual의 Q97.5이다. 실행 day가 없어 null이다.

## Q30. day-worst Q99?

A. 각 day의 방향별 최대 residual의 Q99이다. 실행 day가 없어 null이다. 30일만으로 tail safety를 주장하지 않는다.

## Q31. current 0.005 upper coverage?

A. 미산출이다. n=0을 0% coverage로 해석하지 않는다.

## Q32. current 0.005 lower coverage?

A. 미산출이다. n=0을 0% coverage로 해석하지 않는다.

## Q33. 0.005 exceedance day는?

A. 미산출이다. empty exceedance list는 안전하거나 exceedance가 없었다는 증거가 아니다.

## Q34. calibrated upper candidate?

A. 1.05−delta_up(q)이다. 실제 candidate upper는 null이다.

## Q35. calibrated lower candidate?

A. 0.95+delta_down(q)이다. 실제 candidate lower는 null이다.

## Q36. asymmetric인가?

A. 비대칭을 허용한다. 실제 delta가 없어 대칭성도 판단하지 못했다.

## Q37. physical Planning band는?

A. Primary S0는 0.95–1.05 pu다. Scientific production constants는 그대로 보존했다.

## Q38. S2를 primary로 썼는가?

A. 아니다. S2를 primary에 강제하지 않는다. Scientific 실행은 아직 0일이다.

## Q39. 왜 S0로 calibration했는가?

A. 0.005 필요성을 측정하기 전에 robust-margin infeasibility로 baseline을 제거하지 않기 위함이다.

## Q40. B0 S2 fail은 physical fail인가?

A. 아니다. S0 physical feasibility와 S2 robust-margin feasibility를 분리한다.

## Q41. April days는 몇 개인가?

A. Raw forecast/realized 위치와 hash를 감사한 날짜는 30일, executable input bundle은 0/30일이다. 초기 known-only 진단 5일은 승인 reference가 아니다. Input gate 이후 승인 common reference는 미생성이다.

## Q42. excluded days는?

A. 30일 모두 realized GPU request authority 누락으로 사전 exclusion했다. 일부 날짜는 known demand도 누락이다. Voltage 결과는 보지 않았다.

## Q43. AIDC IT energy는?

A. 미산출이다. Positive IT energy check를 contract flag와 구분했다.

## Q44. AIDC PCC energy는?

A. 미산출이다. Positive PCC energy check를 contract flag와 구분했다.

## Q45. served workload는?

A. 미산출이다. 29,350개 snapshot row 모두 retained이며 workload drop=false다.

## Q46. model error magnitude는?

A. RMSE/MAE/P95 absolute/day-worst를 계산하는 utility가 있지만 실제 model samples는 없다.

## Q47. forecast error magnitude는?

A. 동일 metrics를 구현했지만 실제 forecast samples는 없다.

## Q48. 어느 쪽이 더 큰가?

A. INCONCLUSIVE다. 모든 metrics가 같은 방향을 가리킬 때만 dominant cause를 표현한다.

## Q49. worst voltage event는?

A. 미산출이다. node/phase/slot/timestamp 없는 worst event를 만들지 않았다.

## Q50. D-Day physical pass days는?

A. 미산출이다. Physical PASS day 0이라고 실패율로 해석하지 않는다. 실행 day는 0이다.

## Q51. line violation은?

A. 미산출이며 null이다. NOT_RUN을 zero violations로 표시하지 않았다.

## Q52. transformer violation은?

A. Current/kVA를 각각 분리했으며 실제 수치는 null이다.

## Q53. May를 사용했는가?

A. Calibration에 May를 사용하지 않았고 May run은 없다. Known inference는 March/April request projection만 사용했다.

## Q54. margin을 final로 확정했는가?

A. 아니다. FINAL_MARGIN_ACCEPTED=false다.

## Q55. 왜 아직 final이 아닌가?

A. April residual도 아직 없고 May holdout, B1/B2/B3 및 policy transferability도 미검증이다.

## Q56. B1은 언제 볼 것인가?

A. 완전한 common workload authority와 B0 residual 검증 뒤 별도 authorized task에서 검토한다.

## Q57. PR118 architecture를 유지했는가?

A. 그렇다. 기존 2,144개 PR118 Git blob을 raw byte로 보존하며 coordinator/Actual은 수정하지 않았다. Test 중 .gitignore만 기존 receipt가 요구하는 CRLF checkout을 임시 사용하고 최종 exact BASE byte로 복구했다.

## Q58. separate Day-Ahead AC Validation을 되살렸는가?

A. 아니다. Offline DA-AC 계약만 있고 operational stage는 추가하지 않았다.

## Q59. Final margin candidate는?

A. 미산출이다. 모든 q의 directional candidate는 null이며 final margin이 아니다.

## Q60. final verdict는?

A. BLOCKED_AFTER_SOURCE_BACKED_RECOVERY_AUDIT다. 지정한 external raw 전체 23,601개 파일을 inventory하고 LFS payload 47개를 SHA로 해소했다. Known 5,173/Actual 16,284 observation 모두 요청 GPU를 exact source로 결정하지 못했다. Historical mapping 부재 때문이 아니다.

Known reference complete dates: 2025-04-02, 04-04, 04-05, 04-06, 04-28. These are known-only references, not complete Actual replay authorities.

GPU missing counts are date-row observations, not unique jobs. Raw per-day files also do not establish full carry-in coverage. The new common reference placement is a case-study rule, not observed Kestrel facility allocation.

Full March/April archive arrivals replace the incomplete per-day arrival inventory:
82,323 post-issue observations, including 20,459 missing GPU requests. All
29,350 known observations and all source arrivals remain. The expanded recovery
ledger has 25,632 missing observations and 16,574 unique jobs; every missing
request is SOURCE_FIELD_ABSENT after exact timestamp-normalized joins and
whole external source audit. Complete population GPUh remains unknown.

Current frozen Runtime identity/inference is PASS. Request submission-version
history is UNVERIFIED_SOURCE_PROXY; submission-cutoff PASS is reported
separately from full request-version causality. No strict causal authority PASS
is fabricated. Actual gang positivity and compatible-site fit are checked.
Scientific residual production must use complete_calibration_residuals with
authoritative node/phase pairs and all 96 slots per frozen date.

Validation: 983 tests passed; one inherited Runtime log1p warning. Scientific
voltage/energy/physical PASS/margin fields remain null or NOT_RUN.
