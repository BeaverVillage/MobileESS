# 최종 보고 — DUAL_AUTHORITY_UNRESOLVED

PR155의 원본 증거를 보존한 child branch에서 dual forensic과 영구 guard를 구현했다.
사용자 지정 STOP 조건에 따라 exact dual authority가 해결되기 전 모든 full-scale
최적화와 B&P 개발 실행을 중지했다. sign gate를 우회하지 않았다.

| 항목 | 결과 |
|---|---|
|1. exact dual-sign root cause|RMP43 원시 Pi/X/RC 미저장으로 첫 실패 행/원인 미확정. assertion 후 저장한 증거 유실은 확인.|
|2. exact fix|거부 전 durable snapshot 및 독립 terminal dual guard. 실제 RMP43 부호 오류 해결은 미확정.|
|3. strong duality|bound terms 포함 tiny fixtures PASS. 저장된 full-scale point의 native RC/bound dual vectors 미보존으로 요청된 완전 감사 미해결.|
|4. existing-column RC|1841개 two-path transport 오차 최대5.204e-18. native per-column RC 비교는 미해결. RMP42 활성1825개와 추가16개 분리.|
|5. restricted integer UB|없음; integer master NOT_RUN. LP .5729695797088222를 UB로 사용하지 않음.|
|6. starting certified LB|.5687115725336208 보존. corrected-bound 기존 rational arithmetic PASS.|
|7. early B&P branch rule|미구현/NOT_RUN. PR145 original-space exhaustive branch만 조건부 계획.|
|8. child inheritance|조건부 수학 계획 LB_child>=LB_parent. 실제 child proof/test NOT_RUN.|
|9.600s benchmark|NOT_RUN_DUAL_AUTHORITY_UNRESOLVED.|
|10. root-CG baseline|기존1010.136 native union 동안 aggregate LB 증가0; restricted LP 감소는 integer gap 진척으로 간주하지 않음.|
|11. early-B&P gap progress|측정 없음.|
|12. selected/rejected|선택 안 함; 성능 비교를 평가하지 않아 EARLY_BAP_REJECTED로 오표시하지 않음.|
|13.7200s run|실행 안 함, grant debit0.|
|14. B&P nodes|0.|
|15. best integer UB|null.|
|16. global certified LB|새 B&P global LB 없음; starting root certificate만 보존.|
|17. global MIP gap|null (valid integer UB 없음).|
|18. P1 accepted|false.|
|19. P2 movement energy|NOT_RUN.|
|20. P2 movement count|NOT_RUN.|
|21. native runtime|새 full-scale0초. tiny Gurobi LP 0.001000초/29calls; 개발 grant와 분리.|
|22. resource peak|offline forensic OS process high-water 1.048GiB; peak machine memory/optimization RSS라고 주장하지 않음.|
|23. tests|35 PASS, errors/failures0. 신규 guard15개 및 기존 corrected-bound 회귀. branch/B&P tests NOT_RUN.|
|24. commit / Draft PR|guard repair cb6ed3f1b7b472b2073e074b34334577b3b25f56; child Draft PR publication receipt 참조.|

## 요구된 종료 문구의 사실관계

“RMP dual 부호 오류를 해결했다”는 선언은 현재 할 수 없다. row convention과
fixture는 검증했지만 RMP43 raw evidence가 없어 EXACT_DUAL_AUTHORITY_PASS=false다.
Exact root convergence가 early B&P의 논리적 선행조건이 아니라는 설계는 명시했으나
B&P를 실행하지 않아 node/global-bound 사용·0.5% 종료 달성을 주장하지 않는다.
Restricted LP objective를 global LB/integer UB로 사용하지 않았다.
휴리스틱-only pruning, approximate pricing, convergence tolerance 완화는 사용하지 않았다.

## 보존 및 중단

원본 PR155 docs의 byte hashes,1841-column checkpoint, valid RMP42,
PROVEN_NONMATERIAL, ROOT_CG_CONVERGED=false 및 B&P NOT_RUN 상태를 그대로 보존했다.
Full-scale 추가 실행/재현으로 없는 RMP43 point를 만들어 과거 증거처럼 쓰지 않았다.
증거가 없는 상태에서 임의 부호를 뒤집거나 guard를 끄지 않았다.
May campaign과 다른 downstream production을 재개하지 않았다.
