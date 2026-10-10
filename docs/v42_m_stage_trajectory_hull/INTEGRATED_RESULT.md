# May01 integrated trajectory CG: no new certified LB

The bounded pilot stopped after one Discovery solve with a software adapter error,
before Master optimization or new pricing certificates. The frozen LB remains
0.38895900867731903; certified gain is zero. Source repair and saved-data admission
replay subsequently passed without any further optimize call. The pilot was not
restarted. Trial source was `43d7adc52ccb404f248a05e42c7402b256e8dbed`;
post-trial source and fixture gate are separately identified in the manifest.

| 지표 | Before | After |
|---|---|---|
| 총 Master Column 수 | 12 | 12, 변경 없음 |
| 신규 유효 Column 삽입 | 0 | 0; 오프라인 적격 후보 4개는 미삽입 |
| Restricted Master objective | 0.5406756909532953 | 재최적화 NOT_RUN |
| True negative RC 현황 | 현재 Dual 후보 미검산 | 오프라인 -0.340751/-0.395216/-0.372748/-0.370016 |
| Pricing certified LB (MESS01~04) | -4.349256/-4.350386/-4.346581/-4.347727 | 새 인증 NOT_RUN; 기존 증거 유지 |
| Certified DW Global LB | -16.898190436665164 | 새 인증 NOT_RUN |
| Published Global LB | 0.38895900867731903 | 0.38895900867731903 |
| Certified Delta LB | — | 0 |
| Global Gap | 28.060570285386962% | 28.060570285386962% |
| 전체 Native Runtime | 136.16500186920166초 | 141.40300178527832초 |
| Full Pricing Closure | NOT_PROVEN | NOT_PROVEN |

Actual additional Native: 5.23799991607666 seconds, one MESS01 discovery MILP,
Threads=1, requested 6 seconds, OPTIMAL. The objective -1.177870834760 is the
**smoothed discovery** objective, not a certified current integer pricing minimum.
Original local replay passed, all 2,329 binaries were literal 0/1; maximum observed
row violation 3.55e-14 and bound violation zero. This is numerical feasibility,
not exact trajectory membership. No Master optimize and no certification pricing
optimize followed. Pilot wall 27.6272469 seconds; discovery build 0.1337631 seconds;
new independent global certification time zero because that phase was not reached.

## First-round anomaly

The previous four columns changed route/location/mode/SOC and coupling projections:
5,837--5,932 projected rows changed; maximum coefficient differences were
392.314--469.227. They are not identical to their seed projections. Original
binding equations imply nonzero line26 P/Q changes at slots29--32. In the actual
verified BEST UB, line26 is tight at slots31/32; slots29/30 have positive slacks
0.0035509538/0.0038653926. Therefore a stationary-only four-slot bottleneck claim
and a general "no critical-line influence" explanation are unsupported.

The new lambdas were approximately 1.39e-12, 7.51e-13, -2.07e-13, -1.21e-12,
with zero post-update RC, while 553 dual rows changed and objective changed only
-1.85e-13. This supports dual degeneracy and effectively unused columns. Before
that update an existing seed lambda was upper-active at one with RC
-0.08338620912067166; its bound-dual contribution matters in master strong-duality
accounting. Afterward upper-active seed RC was zero. These observations do not
prove a unique cause for unchanged objective. Scaling/readback evidence reports
zero coefficient loss; no objective, grid row or lambda bound was changed.

## Six scientific answers

1. **실제 보완:** raw Pi, 부호 거부 이유, current bounds/objective, exact RHS·box·rounding,
   부모 상속 이유를 저장하고 같은 차량의 저장 Dual을 현재 가격/분기에서 재검산한다.
   MESS01 r01 및 MESS03 실제 저장 회귀가 통과했다. 이번 Native 파일럿에서는 이 새
   인증 단계까지 도달하지 못했으므로 인증 하한 개선 실측으로 해석하지 않는다.
2. **재사용:** PR142 `next_smoothing_weight`, PR147 `smooth_snapshot`, PR152
   `Mechanics.add`의 실제 함수 본문을 사용했다. PR147/152의 반복 순서와 checkpoint/
   ledger 원칙은 현 Stage 축에 맞춰 연결했다. 예전 M1 데이터·권한은 전용하지 않았다.
3. **Master 정체:** 위 퇴화 증거와 lambda upper-bound 효과가 확인된다. seed 대비
   projection 중복이나 선로26 무영향은 관측과 맞지 않는다. 유일한 원인은 미확정이다.
4. **Pricing gap 축소:** NOT_MEASURED. 이전 12-column pool의 수치 목적값과 인증 하한
   차이는 각각 4.331553/4.387148/4.360875/4.359289이다. 이는 exact pricing optimum gap이
   아니며, 새 Dual·새 certificate가 없으므로 줄었다고 주장할 수 없다.
5. **3% 가능성:** UNKNOWN. 필요한 LB는 0.5244554202246624, 추가 개선은
   0.13549641154734338이다. Full DW closure도 정확한 formulation ceiling도 미증명이다.
6. **현재 한계:** 실측의 직접 병목은 기존 catalog의 선택적 `point_sha` 필드를 필수로
   가정한 소프트웨어 오류였다. 이후 수정해 저장 벡터 SHA로 복원하고 실제 구형 schema를
   회귀에 포함했다. 수학적 인증상의 남은 병목은 전체 미탐색 정수궤적을 덮는 pricing
   하한의 약함이다. 정식화 자체가 3%를 불가능하게 만든다는 증거는 아직 없다.

## Evidence and scope

`INTEGRATED_CG_TRIAL.json`, `FIRST_ROUND_ANOMALY.json`,
`OFFLINE_ADMISSION_REPAIR_AUDIT.json`, `INTEGRATED_EVIDENCE_MANIFEST.json` and the
native logs in `D:/v42_m_stage_trajectory_hull/runtime/v42_trajectory_hull/integrated_cg01`
separate frozen trial results from post-trial source repair. The old 136.165 second
ledger prefix is unchanged. New gate anchors the 141.403 second ledger and latches
this stopped trial against automatic replay. Lightweight regression passed; no
full regression suite or extra Gurobi optimization was run.

B3 M1/M2: NOT_RUN_NO_FIXED_INPUT. No Production promotion, campaign, Supervisor or
scheduled-task operation occurred. Old Frozen scientific files and PR202 are intact.
