PR161의 C2에 남은 full-LP 중복 구조를 독립 증명으로 제거하고 C3A를 선택한다. PCS16 53,652행, 연결 Q 17,884행, 종단 위치 4행을 제거해 총 71,540행(10.93%)을 줄였다. 48,551개 열의 함의된 경계를 강화했으며 물리 변수, 목적함수, 경로/SOC/PQ, PCS16의 feasible set과 모든 수치 허용오차는 보존한다. C3A=C3B=C3C이다.

동일한 full MILP 설정으로 새로 측정한 C2/C3 root 시간은 212.29→180.21초(15.11% 감소), root Work는 452.05→359.99(20.37% 감소)다. 사전 등록된 15% 기준 A/B를 충족해 최종 상태를 `ULTRACOMPACT_EXACT_SELECTED`로 판정했다. Micro C2 root는 제한 시간 내 미완료했으며 다른 phase나 과거 실행의 수치와 비교하지 않았다. 원래 micro-only 자동 판정을 보존하고 완료된 full MILP 쌍에 같은 기준을 적용했다. 추가 solver 실행은 없다.

두 MILP arm 모두 root 이후 B&B node 0, 새 valid incumbent 없음, valid UB 0.6694159238756877, valid LB 약 0.56871160035, valid gap 약 15.0436%다. LB/gap 개선이나 0.5% gap 달성을 주장하지 않는다. MIPGap=.005와 FeasibilityTol=1e-8을 유지했다.

검증:

- 22개 row family와 15개 column family 및 모든 C2 행/열 ID를 감사 ledger에 기록했다.
- 원래 1,536 assignment, route path enumeration, 13개 신규 adversarial case 및 인증 변조 거절 모두 PASS.
- PR160 190,280개 인증, PR161 704,775개 C1행 매핑을 독립 재검증했다.
- C2 전체 654,348행, 제거행 71,540개 및 새 경계 48,551개를 production deletion 함수를 호출하지 않는 verifier로 재구성해 PASS.
- PR161 시작해의 route/PQ/SOC/mode 변경 없이 최대 잔차 1.3827730072080158e-9로 PASS.
- 읽기 전용 presolve: 행 535,063→407,856(23.77% 감소), nnz 4,668,412→4,498,109. Presolved 열은 280,359→287,699로 증가한 점을 명시했다.
- root 최대 240초/arm, MILP 최대 300초/arm에서 총 4개 arm을 순차 실행했다. 금지된 알고리즘·parameter sweep은 실행하지 않았다.

과학적 기준은 PR161 exact head `4f45f04d685d5d5e689463f953695fe40d52cf98`다. 실제 benchmark 실행 소스는 `0a27fb90dead2b944a72c31145f5a7bdc4dbb9ac`이며 후속 커밋은 측정 결과와 선택 판정·게시 정보를 포함한다. Parent 증거는 불변이고 모든 새 산출물은 `docs/v42_m1_ultracompact_exact_20261006/`에 격리했다.

40문항 답변과 계산 범위·미증명 후보 유지 사유는 `FINAL_REVIEW_KO.md`, 전체 증거 해시는 `SHA256_MANIFEST.json`, 선택 authority는 `ULTRACOMPACT_CURRENT_AUTHORITY_M1.json`을 참조한다. 선택된 C3를 고정하고 STOP한다.
