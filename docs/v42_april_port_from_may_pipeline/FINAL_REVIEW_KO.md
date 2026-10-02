# May blueprint → April current V42 후속 감사

PR121 exact head c0783fadbbca282f2ce580c45fe82feaed71584c 위에서 기존 evidence와 983개 테스트를 보존했다. May raw→canonical→known/Actual→GPU→Runtime→site/rack/capacity→IT/PCC/Q→grid→Planning/Actual/OpenDSS chain을 17단계로 복원하고, 36개 field crosswalk와 날짜 독립 builder를 추가했다.

May GPU authority는 raw `gpus_requested` → V37 ledger → frozen temporal schedule → V40d requested_GPU → V41 common reference → V42 GPU_gang 상속이다. V42 final은 current Q50 duration만 교체한다. request-version reconciliation, node 기반 exact derivation, missing GPU imputation은 발견되지 않았다. upstream `_submission_complete`/`_jobs_and_ledger`에는 missing/invalid resource exclusion이 있으나, 숫자 May 재현을 수행하지 않았으므로 특정 May 실행이 누락 row를 제거해 성공했다고 단정하지 않는다. 이 역사적 exclusion은 이번 no-drop contract에서 port하지 않았다.

April 원본 재처리: known missing 5,173, initial Actual missing 16,284, expanded 25,632 observations / 16,574 unique jobs. Recovered 0, unresolved 25,632, ambiguous 0. known 29,350와 post-issue Actual 82,323 observations를 모두 유지했다. 30일 input inventory를 새 builder로 생성하고 PR121 UID/GPU/Q50/service population과 대조했다. Known과 Actual completeness는 별도이며 input PASS는 0/30이다.

Current frozen V10 Runtime inference를 실제 사용했으며 requested walltime은 feature only다. B0 AIDC/workload/ML flags는 true, flexibility/MESS는 off다. 그러나 input gate가 실패하여 executable common reference와 B0 Planning/AC는 생성·실행하지 않았다. AIDC energy/served workload, physical PASS, voltage, Q95/Q99, .005 coverage, candidate band는 측정되지 않았다. null과 n=0은 무측정이며 zero power 또는 physical PASS가 아니다.

추가 prerequisite는 submission-version causality 증거, April current CC4 date binding, April planning coefficient/anchor 재생성과 concrete independent Actual adapter다. historical known-only Actual, requested-duration service, contention 기반 start 변경, legacy eligibility masking, May 숫자 계수는 현재 contract를 대체하지 않는다.

May forensic과 April builder는 코드/schema/provenance/input metadata만 사용했다. 이 두 경로에서 May job values/outcomes/voltage/policy/calibration 결과를 읽거나 donor로 쓰지 않았다. 기존 983 regression에는 sealed native matrix/solution/validation fixture를 읽는 fidelity/contract 검증이 포함된다. 이 조회는 MAY_HOLDOUT_GUARD.json에 별도 공개했으며 April input/보정 donor가 아니다. 전체 테스트가 모든 May artifact를 읽지 않았다고 주장하지 않는다. B1/B2/B3/May/M1/A2/M2 production NOT_RUN, Actual P/Q/route/schedule repair 및 full reoptimization=0. FINAL_MARGIN_ACCEPTED=false. 검증 결과와 PR121 모든 base 파일 보존 여부는 VERIFICATION.json에 기록한다.
