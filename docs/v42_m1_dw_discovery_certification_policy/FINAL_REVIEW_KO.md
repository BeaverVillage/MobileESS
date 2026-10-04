1. Old-policy STOP SHA 4fc7df0e309c348853f0364dc5a9f866f2310e93; POLICY_EXPERIMENT_PARTIAL / scientific INCONCLUSIVE. 정상 native terminal receipt가 없는 중단 call21 제외.
2. Old-policy preregistration, source, receipts, certificates, logs, columns, tests 모두 바이트 보존.
3. Checkpoint retained columns 1066=4+1044+18.
4. Old TIME_LIMIT incumbent 2개 제외; call21도 제외.
5. 새 policy preregistration commit e477d3a08de2a65e0ff05a84fdc0d48b0090e40c. Original policy source/preregistration commit6716e136527db8332eefc982b33e85379de335a1도 변경 없이 보존.
6. Pricing concurrency 1; resource PASS True.
7. 4-way observed peak pricing RSS 3749642240; parent 7786950656; min available RAM 7461302272 bytes. 정확한 unsampled peak는 주장하지 않음. 4-way worker-residency gate가 pricing 시작 전에 실패했으며 actual4-way pricing calls=0. 2-way도 이후 실패해1-way 선택.
8. Discovery pricing cap20초.
9. Certification cap60초; final cap최대120초.
10. Discovery rounds 3.
11. Certification rounds 2 (final 포함).
12. 새 RMP solves 7.
13. 새 pricing calls 24.
14. Validated discovery columns 12.
15. Median discovery round wall 88.07946670003003초.
16. Median certification round wall 222.48962115001632초.
17. Columns/min old 0.2962470482195092 vs new 0.80998069224726; build/audit 포함 observed elapsed 기준, 인과 speedup 주장 없음.
18. 첫 새 corrected certified LB까지 elapsed 706.4188922999892초; optimize 533.6906489998801초.
19. Best corrected LB 0.5215744487783405 (old inherited certificate 포함).
20. Smallest RMP upper 0.5872526721935815; original integer UB 아님.
21. 최종 certified interval [0.5215744487783405, 0.5872526721935815].
22. Scientific materiality INCONCLUSIVE; threshold 0.5737116103498322.
23. Policy canary NOT_SUPPORTED; optimize wall union 688.9794656998129/900초; stop POLICY_CANARY_FINAL_CERTIFICATION_COMPLETE. Available-RAM gate 실패 이력이 있어PROMISING 조건을 충족하지 못함; selected1-way는PASS.
24. Branch-and-Price NOT_RUN.
25. May day workers B0/B1/B2/B3=4/1/4/1, Threads1.
26. B2 inner1 / B3 inner 1, resource gate 이후만 허용.
27. May optimizer/Actual/Fresh AC=0/0/0; scientific1458-node계획/firewall 보존.
28. Semantic 315 / full 1762 PASS. Draft PR 게시 전; result SHA 게시 전; 최종 SHA/remote/clean은 최종 응답에서 확인.

기존 exact-optimal-pricing-every-round 실험은 계산정책 병목이 확인되어 사용자 지시에 따라 중단했으며, 그 partial scientific result는 INCONCLUSIVE로 보존했다. 중단된 활성 call은 정상 native terminal receipt를 확인하지 못해 인증에서 제외했다.

새 Discovery round의 time-limited pricing은 full original pricing domain을 유지하고 valid negative trajectory만 column으로 추가했으며, pricing optimality를 주장하지 않았다.

Global D-W lower-bound 및 materiality certificate는 same-dual pricing global BestBd를 사용하는 Certification round에서만 증명했다. 이번 materiality 결과가 INCONCLUSIVE이면 material/nonmaterial 판정이 증명됐다는 뜻은 아니다.

B0/B1/B2/B3 May main campaign worker policy는 각각4/1/4/1 day-workers, Gurobi Threads=1로 동결했으며, B2는 outer-day 병렬화를 우선하고 B3는 resource canary 통과 시 inner four-MESS pricing 병렬화를 사용할 수 있도록 분리했다.

이번 task에서 May production, Branch-and-Price, production M1/P2/A2/M2/Actual/Fresh AC는 실행하지 않았다.
