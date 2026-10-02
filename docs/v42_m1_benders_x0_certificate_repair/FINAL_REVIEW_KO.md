# 동일 PR117 x0 certificate repair 검토

INCONCLUSIVE

### Q1. 왜 PR117 x0를 다시 쓰는가?

이번 primary는 같은 저장 candidate의 certificate engine repair다. 새 x0 master solve는 0회다.

### Q2. 정확한 base는?

e2d4779685fff6d0cf022c649733b2ca41fdfc08

### Q3. x0 이름은?

NEW_V2_EXPERIMENT_X0 (PR117 저장본). PR115 historical x가 아니다.

### Q4. x0 vector hash는?

5c8702f5d7cf2e1e278e195f89a9f034c7e5ffbb6440e0f0b4931a0ee9b6e3f3

### Q5. x0 axis hash는?

d8c189480fe5fc0809d833c7df9207ec010c84580bf66783422456d32dcc83bb

### Q6. x0 bit-exact인가?

True; NPZ/bit vector/ordered names/indices/receipt를 검증했다.

### Q7. master count는?

B3 85744 = route 85592 + mode 152. 밖의 원래 binary 122568개는 native continuous [0,1]이다.

### Q8. recourse continuous count는?

230999개. 원래 물리 변수와 outside-B3 relaxed 변수를 보존했다.

### Q9. 1589개 family는?

{'injection_P': 792, 'injection_Q': 792, 'response_line_Q': 4, 'response_line_P': 1}

### Q10. 1589개의 bound class는?

전부 LB=-inf, UB=+inf인 truly free 변수다.

### Q11. A: free exact zero는?

79627개다.

### Q12. B: free nonzero는?

1589개다. 작다는 이유로 exact zero로 승인하지 않았다.

### Q13. C/D: one-sided support는?

{'C_ONE_SIDED_COMPATIBLE': 0, 'D_ONE_SIDED_INCOMPATIBLE': 0}

### Q14. E: finite support 누락인가?

0개. 이번 raw ray 실패는 finite bound를 누락한 문제가 아니다.

### Q15. F: numerical near-zero는?

1589개 모두 near-zero overlay에 속하지만 정확한 유리수 계수는 비영이다.

### Q16. coefficient provenance를 보존했는가?

UNSUPPORTED_COEFFICIENT_PROVENANCE.jsonl.gz에 모든 해당 열의 row/coefficient/multiplier/product를 보존했다.

### Q17. native RC는 있었는가?

INFEASIBLE raw record에 RC/basis는 NOT_AVAILABLE이었다. 가짜 RC를 만들지 않았다.

### Q18. 공식 Farkas semantics는?

Native inequality lambda signs와 A^T lambda의 bound support를 함께 사용한다. 자유 변수에서는 weighted coefficient=0이어야 한다.

### Q19. native FarkasProof를 정확히 재구성할 수 있었는가?

원래 float ray에서는 full support가 unbounded이므로 finite exact proof가 없다. partial sum을 proof로 사용하지 않았다.

### Q20. 왜 42.159 scalar만으로 승인하지 않았는가?

Floating solver scalar와 원래 IEEE-rational 행렬에서의 exact stationarity는 별도 조건이다.

### Q21. repair는 무엇인가?

원래 inequality multiplier를 유지하고 defining equality multiplier를 exact rational 역삼각 대입으로 유도했다.

### Q22. free-variable pivots는?

81216개 모두 원래 defining equality의 +1 pivot을 가진다. 원래 primal LP는 변경하지 않았다.

### Q23. offline equality changes는?

1589개. 모든 delta와 before/after 유리수를 별도 certificate에 저장했다.

### Q24. clamp/flip/tiny-delete 했는가?

모두 false. 근사 residual을 지우는 대신 equality multiplier를 정확히 다시 계산했다.

### Q25. 새 certificate인가?

예. 원래 raw ray는 계속 rejected이다. 새로운 completed rational ray를 독립 검증한다.

### Q26. standard form을 실행했는가?

생산 표현은 원래 native LP다. primal transform은 identity bijection이다.

### Q27. free plus/minus split이 bijective인가?

아니다. 둘을 함께 증가시킬 수 있다. 그 split을 bijection이라고 주장하거나 사용하지 않았다.

### Q28. 양방향 solution mapping은?

생산 표현은 y→y identity이며 역방향도 동일하다. Fixture mapped points와 원래 residual을 검증했다.

### Q29. scaling은?

실제 recourse row/column scaling은 2^0. 별도 fixture에서 fixed positive power-of-two scaling을 검증했다.

### Q30. Phase-I dual normalization은?

사전 등록된 양의 유리수 1/2다. sign flip이 아니며 exact weak-duality separating proof를 요구한다.

### Q31. fixture assignments는?

1536개: feasible 49 / infeasible 1487. Native/identity/scaled 분류와 최적값을 다시 비교했다.

### Q32. N1–N10은?

모두 PASS. N6의 guard 아래 margin은 INCONCLUSIVE로 거부한다.

### Q33. 축소 재현 fixture는?

N11이 free injection/response와 boxed P의 unsupported support를 재현하며 PASS다.

### Q34. known feasible assignment는?

49개가 모두 cut을 통과했다. 전체 original x box에 대한 global proof도 검사한다.

### Q35. isolated representation을 언제 freeze했는가?

Fixture/preflight PASS 후 source commit과 EXECUTION_FREEZE를 저장하고 optimize 전에 검증했다.

### Q36. x0 native status/time는?

3 / 1367.1589999198914초.

### Q37. x0 Kappa/warnings는?

7816110377241435.0 / ['Warning: Model contains large matrix coefficient range', 'Warning: very big Kappa = 7.81611e+15, try parameter NumericFocus']

### Q38. raw native certificate valid인가?

False; 원래 PR116 raw validator 결과다.

### Q39. completed x0 certificate valid인가?

True

### Q40. Phase-I terminal인가?

False; used=False. 미실행이면 terminal이라고 주장하지 않는다.

### Q41. Phase-I budget은?

Native와 별도 1800초다. 동일 candidate에서 sequential이며 parameter search는 없다.

### Q42. valid cut count는?

2

### Q43. cut source separation은?

[42.15907601900593, 3902602.693678552]; exact/rounded >1e-8을 요구한다.

### Q44. cut insertion 전 replay했는가?

Independent COO rational products, sign, free stationarity, bounds, global outward domination 및 원래 source x separation을 재검증한다.

### Q45. x1 생성됐는가?

True; valid cut 이전에는 master optimize 0회다.

### Q46. x1은 저장됐는가?

생성 시 vector/ordered axis/NPZ/hash/receipt/new commit/prereg/freeze lineage를 recourse 전에 atomic 저장하고 reload한다.

### Q47. distinct x는?

2

### Q48. recourse1 결과는?

CERTIFIED_SEPARATING_CUT / native seconds=1031.12700009346

### Q49. minimum pilot 완료인가?

True

### Q50. B3 classification은?

B3_INCONCLUSIVE

### Q51. full B3 실행은?

False; 이번 preregistration은 isolated x0/x1 pilot 범위다.

### Q52. full M1 canary 실행은?

False; certificate 또는 cuts>=2/distinct x>=3/stability gate가 필요하다.

### Q53. original M1 UB/LB/gap은?

0.5912812634331275 / 0.5722125039436496 / 0.03224989640084286. 새로운 V2 LB는 없다.

### Q54. M1 P1 accepted인가?

False; zero-objective B3 bound를 rho LB로 쓰지 않는다.

### Q55. production/P2/A2/M2는?

전부 NOT_RUN. 이번 사용자 지시가 금지했다.

### Q56. M1 accepted / Problem13 final인가?

False / False

### Q57. global route domain 유지?

Top-K/route pruning/Hamming/pool=0. 원래 restored master domain 전체를 유지했다.

### Q58. 물리 조건 유지?

P/Q/SOC/initial/terminal equality/travel debit/PCS16/all96 voltage/line/transformer/fixed A1/Planning .955–1.045를 유지했다. Actual P/Q repair OFF.

### Q59. threads 및 병렬 solve는?

Master 1, 독립 heavy solve가 없음을 확인하고 recourse 4. Native/Phase-I와 x1 모두 sequential. B0/B1을 실행하지 않았다.

### Q60. next blocker는?

No full B3 witness/proof or original M1 optimization in isolated certificate pilot; 이번 성공을 original M1 acceptance 또는 PR115 causal speedup으로 확대하지 않는다.
