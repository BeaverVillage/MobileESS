Clean PR153 재검증: **MICROBENCHMARK_INCONCLUSIVE / MULTICOLUMN_SELECTED=false**.

PR152 exact head `63e81dc3b6d236549f566e65e07dcd05ac0a160c`, immutable1,604-column checkpoint. 각 leg 정확히1Discovery(4 pricing)+1RMP; Threads=1. Alpha=.1/physics/domain/true-dual authority/Certification unchanged.

A-stage 전용 supervisor/worker 모두 종료 후 시작. 총 continuous pair wall **352.695/600s**, clock reset/extension/replay0. Full leg wall includes source-hash checks, resource admission, model builds, candidate/matrix audits and cleanup.

| Metric | Baseline | Challenger |
|---|---:|---:|
| 새 retained columns | 15 | 21 |
| 끝 pool | 1619 | 1625 |
| Pricing native sum / batch wall (s) | 53.147 / 21.868 | 70.276 / 24.380 |
| RMP native (s) | 39.669 | 36.478 |
| Full leg wall (s) | 213.585 | 136.596 |
| Audited upper before | 0.5741861223241257 | 0.5741861223241257 |
| Audited upper after | 0.574115768594322 | 0.5741155437914072 |
| Audited upper decrease | 7.03537298037e-05 | 7.05785327185e-05 |
| Upper decrease / full wall-second | 3.29393987463e-07 | 5.16696698635e-07 |
| Retained / pricing native minute | 16.934 | 17.929 |
| Sampled peak RSS GiB | 10.928 | 11.069 |
| Min available RAM GiB | 8.816 | 7.411 |
| Max commit % | 45.117 | 50.537 |
| Guard interruptions | 0 | 0 |

Full-wall arithmetic: scientific equivalence PASS; invalid admission=0; guard interruption=0; registered full-wall ratio=1.568628, improvement=56.863%. 산술 gate는 통과했지만 timing scope validity FAIL로 selected=false다.

Timing audit: 기존 PR153 Discovery→RMP timer 구간은 Baseline 130.257s / Challenger 129.126s; efficiency 5.40116721301e-07 / 5.46586701924e-07, ratio 1.011979 (+1.198%). 기존 구간 밖 source-hash/admission/cleanup overhead가 83.329s / 7.470s로 달랐다. 포함 범위를 불필요하게 넓힌 측정 때문에 full-wall20%를 신뢰할 만한 알고리즘 개선으로 해석할 수 없다. Registered 값은 보존하며 core diagnostic을 사전 등록 primary로 사후 대체하지 않는다. 성능 선택 결과 INCONCLUSIVE, false 유지, 추가 native 재실행0. 통계적 또는 causal uniqueness를 주장하지 않는다.

Guard는 PID/create_time/native mapping/live source call site를 함께 확인하는 nonblocking observation으로 변경했다. Import/reservation/mock/unobservable 상태만으로 WAIT_RESOURCE 하지 않는다. 샘플 관측의 미관측 구간까지 실제 foreign optimize 부재를 보증하지 않는다.

Lightweight fixtures21/21 PASS; independent original full matrix saved-point audit PASS; inherited12,919 tracked files와 terminal2,033 hash bindings 보존. source freeze PASS. Post-benchmark optimize is monkeypatch-forbidden and attempted calls0.

Harvested candidates/MESS: Baseline [8, 7, 6, 5], Challenger [8, 13, 6, 5].

Validated negative/MESS: Baseline [6, 6, 4, 3], Challenger [6, 10, 4, 3].

Duplicate/projection/dominance recount: Baseline [{'MESS': 'MESS01', 'candidates_encountered': 8, 'negative_callback_candidates': 8, 'captured_distinct_vectors': 8, 'validated_negative_columns': 6, 'independently_validated_columns': 7, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 2, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 0, 'dominated_removed': 0, 'retained_columns': 4}, {'MESS': 'MESS02', 'candidates_encountered': 7, 'negative_callback_candidates': 7, 'captured_distinct_vectors': 7, 'validated_negative_columns': 6, 'independently_validated_columns': 7, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 2, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 0, 'dominated_removed': 0, 'retained_columns': 4}, {'MESS': 'MESS03', 'candidates_encountered': 6, 'negative_callback_candidates': 6, 'captured_distinct_vectors': 6, 'validated_negative_columns': 4, 'independently_validated_columns': 5, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 0, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 0, 'dominated_removed': 0, 'retained_columns': 4}, {'MESS': 'MESS04', 'candidates_encountered': 5, 'negative_callback_candidates': 5, 'captured_distinct_vectors': 5, 'validated_negative_columns': 3, 'independently_validated_columns': 4, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 0, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 0, 'dominated_removed': 0, 'retained_columns': 3}]; Challenger [{'MESS': 'MESS01', 'candidates_encountered': 8, 'negative_callback_candidates': 8, 'captured_distinct_vectors': 8, 'validated_negative_columns': 6, 'independently_validated_columns': 7, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 0, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 6, 'dominated_removed': 0, 'retained_columns': 6}, {'MESS': 'MESS02', 'candidates_encountered': 13, 'negative_callback_candidates': 13, 'captured_distinct_vectors': 13, 'validated_negative_columns': 10, 'independently_validated_columns': 11, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 2, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 10, 'dominated_removed': 0, 'retained_columns': 8}, {'MESS': 'MESS03', 'candidates_encountered': 6, 'negative_callback_candidates': 6, 'captured_distinct_vectors': 6, 'validated_negative_columns': 4, 'independently_validated_columns': 5, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 0, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 4, 'dominated_removed': 0, 'retained_columns': 4}, {'MESS': 'MESS04', 'candidates_encountered': 5, 'negative_callback_candidates': 5, 'captured_distinct_vectors': 5, 'validated_negative_columns': 3, 'independently_validated_columns': 4, 'captured_trajectory_duplicates': 0, 'nonduplicate_policy_rejections': 0, 'callback_raw_duplicates': 0, 'exact_projection_duplicates': 0, 'postsolve_repeat_observations': 3, 'dominated_removed': 0, 'retained_columns': 3}]. Batch quota rejection은 duplicate로 계산하지 않았다.

Benchmark 출력은 read-only 개발 snapshot에만 기록했다. Authoritative continuation / Certification / B&P=0; May production0/0/0; 다른 Lane kill/terminate/edit0. PR152의 certified interval/materiality/CG convergence는 그대로다.

이 pair 뒤 STOP. 장시간 root-CG나 추가 native 검증은 실행하지 않았다. PR153 publication/local-remote SHA/clean evidence는 별도 publication receipt와 최종 응답에 기록한다.

PR152의 1,604-column checkpoint는 immutable baseline으로 보존했으며, 동일 checkpoint의 read-only copies에서 기존 방식과 multi-column 방식을 각각 정확히 1 Discovery round + 1 RMP로 비교했다.

이번 실험은 최대 600초의 development microbenchmark이며, 결과를 authoritative D-W root certificate에 합치지 않았다.

선택 기준은 raw column 수가 아니라 audited upper-bound improvement per wall-clock second였다.
