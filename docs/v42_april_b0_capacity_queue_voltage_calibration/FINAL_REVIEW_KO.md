# April V42 B0 capacity queue / Planning–Actual voltage 검증

PR123 exact base `81118271a837648da13146fb6ffdc8e3de8d95ab`에서 시작했다. PR124/M1 sibling 코드와 cache를 import/merge/cherry-pick하지 않았다. 새 `v42_capacity` producer가 이번 current V42 common reference 및 B0 execution authority이다. 이전 generator와 evidence는 exact-base 기록으로 보존하며 이 campaign에서 호출하지 않는다.

## 실행과 physical 결과

April 30/30일 B0 및 Fresh Actual OpenDSS를 실행했다. 각 날짜 96 slots, 386 node-phase, 총 1,111,680 points를 exact alignment했다. 모든 AC slot이 수렴했다. Planning/Actual GPU capacity violation은 각각 0이고 780 GPU 및 site/rack authority를 그대로 유지했다. Actual 전압 위반은 4/15 3개, 4/16 17개, 4/30 2개 node-phase-slot cells이며 line/transformer current/kVA violation은 0이다. 수렴 성공은 모든 physical security constraint가 통과했다는 의미가 아니다. 전압 위반 3일을 그대로 포함했다.

Q50-expired RUNNING 4,997 day-job rows(3,812 unique jobs, GPU sum 11,378)의 미래 nominal occupancy를 0으로 두었다. D-1 current physical placement와 Actual causal running state는 유지한다. frozen gamma 2.423057443558147 및 survival kernel은 변경하지 않았다. 만료 row의 overrun kernel exposure 3,771.818973536571 GPUh가 계속 존재한다. 기존 overflow 15일 중 12일은 이 nominal release 수정으로 해소되고 나머지 3일은 forward CC4 backlog로 처리됐다. workload advance/drop/clipping과 grid optimization은 없다. CC4 Q50 71,182.4908646955 GPUh = admitted 48,096.157603418425 GPUh + natural post96 tail 23,086.333261275413 GPUh + final capacity backlog 0 GPUh, pooled rounding error −1.6524e−9 GPUh. 모든 day의 사전 고정 absolute 1e−9 + relative 1e−12 tolerance가 통과했다.

Actual private environment duration은 원본 UID/submission/source-row에 exact join한 observed end−start로 54,492 unique J_phys jobs 모두 확인했다. RUNNING은 source causal completion까지 유지하고, PENDING/new arrivals는 simulated admission + source realized duration으로 completion event를 환경 내부에서 예약한다. Controller에는 duration/end/future receipt를 전달하지 않는다. submission/UID strict FCFS, head-of-line blocking, first compatible ascending AIDC free site, ceil-900-second causal release를 사용한다. known PENDING 및 realized arrival의 reference policy replay는 Actual physical capacity와 observed completion에 의해 달라지며 grid signal로 retime하지 않는다. pending/running carry-out은 ledger에 보존한다. Actual에 CC4 load를 더하지 않는다.

Actual served physical GPUh 439928.095555556, IT energy 299455.783312269 kWh, PCC energy 342502.768472630 kWh가 모두 양수다. D-Day served day-job rows 52,741, capacity-wait day-job rows 56,161, carry-out day-job rows 24,947이다. 이는 독립 daily replay의 row count이며 unique throughput으로 합산 해석하지 않는다. 원본 전체가 아니라 PR123에서 이미 frozen된 modelable J_phys population이다. 이번 변경의 추가 workload exclusion/drop은 0이다.

## Primary voltage evidence

Primary e_total = V_ACTUAL_AC − V_PLAN. V_PLAN은 기존 affine squared-voltage response의 `v2_anchor + H*(control−anchor)`를 새 April forecast/B0 reference로 rematerialize하고 sqrt로 magnitude pu 변환한 값이다. B0 fixed controls는 해당 새 April reference anchor와 같다. 따라서 이 실험은 off-anchor flexible-control linearization error를 평가하지 않는다. DA_AC를 primary residual이나 operational gate로 사용하지 않는다. Planning response/freeze 다음에 Actual causal replay와 독립 fresh engine 평가를 실행했다. Actual은 frozen April Planning tap/capacitor states를 사용한다.

Mean signed error -0.002652077376 pu, MAE 0.002726309883, RMSE 0.003252295678, median absolute error 0.002551620929, maximum absolute error 0.012229724342. Worst: 2025-04-25, idc_idc10_pcc, phase A, slot 55 (13:45–14:00 fixed AEST); Plan 1.0313994222985416, Actual 1.0191696979567557 pu.

Plan overall min/max 0.9789396322541122 / 1.049656898373296 pu; Actual 0.9729176245045357 / 1.0520682205741854 pu. Planning primary band 0.95–1.05. Actual P/Q/local PQ/global optimization/grid schedule repair = 0; MESS P/Q/movement/optimization = 0.

Empirical quantile method `higher` was frozen before execution. Candidate bands use .95+delta_down and 1.05−delta_up independently; no final choice has been made.

| q | Point up / down (pu) | Day-worst up / down (pu) | Point candidate band | Day candidate band |
|---|---|---|---|---|
| Q90 | 0.000000000 / 0.005104494 | 0.003687776 / 0.011275945 | 0.955104494–1.050000000 | 0.961275945–1.046312224 |
| Q95 | 0.000000000 / 0.005927587 | 0.004559693 / 0.012125419 | 0.955927587–1.050000000 | 0.962125419–1.045440307 |
| Q97.5 | 0.000437244 / 0.006700580 | 0.005460484 / 0.012229724 | 0.956700580–1.049562756 | 0.962229724–1.044539516 |
| Q99 | 0.001325061 / 0.007588593 | 0.005460484 / 0.012229724 | 0.957588593–1.048674939 | 0.962229724–1.044539516 |


Current ±0.005 upper point coverage 99.993073546%, lower 89.164867588%, joint 89.157941134%; joint day coverage 0/30. All April days contain an exceedance; maximum excess over 0.005 = 0.007229724342 pu at the same worst location. Current symmetric margin does not cover the observed lower-direction daily extremes. No margin was applied to repair these outputs.

## Evidence와 검증

Full pytest 1,200 PASS; inherited Runtime inference log1p warning 1건이며 existing finite-output checks가 통과했다. 독립 audit가 CSV/NPZ 1,111,680 points의 exact identity, squared-to-magnitude conversion, residual formulas, full per-site capacity와 Actual power 재계산, frozen native states를 확인했다. PR123 3,189 base files는 byte-identical이며 unrelated M1/Benders source도 보존한다. Baseline M1 unit fixtures는 full regression tests의 일부로만 실행됐고 M1 scientific campaign 또는 PR124 code는 실행하지 않았다.

145,174,676-byte full-precision residual CSV는 local output으로 보존한다. GitHub single-blob limit 때문에 Git에는 byte-identical gzip copy와 CSV SHA/size receipt를 저장한다. 압축 해제하면 동일 CSV를 복구할 수 있으며 rounding이나 row omission이 없다. 모든 April response NPZ와 Actual measurements도 새 namespace에 보존한다. 외부 raw source를 Git에 복사하지 않았다.

FINAL_MARGIN_ACCEPTED=false. PROBLEM13_FINAL_VALIDATED=false. B1/B2/B3/May/M1/A2/M2 NOT_RUN. April 실행 blocker는 없으며 final margin acceptance에는 아직 실행하지 않은 May holdout이 필요하다.
