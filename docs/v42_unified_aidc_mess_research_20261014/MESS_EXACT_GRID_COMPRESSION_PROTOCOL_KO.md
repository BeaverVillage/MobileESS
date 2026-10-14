> PR 중단 스냅샷 안내: 아래 초기 진행 기록은 역사 자료이며 현재 실행 상태가 아니다. 현재 결과는 [최종 검토](FINAL_UNIFIED_REVIEW_KO.md), [AIDC 실측](AIDC_SITE_ONLY_PR_SUMMARY_KO.md), [MESS 압축 실측](MESS_EXACT_COMPRESSION_BENCHMARK.json), [벡터화 실측](MESS_EXACT_VECTORIZED_PROOF_BENCHMARK.json)을 따른다. 60분/Runtime Repair/Migration·새 Known Heavy·4단계 Heavy는 중단되어 있다.

# S1 원본 계통 행의 exact 압축 구현과 검증 절차

현재 실행 우선순위는 S1의 836,244행 중 계통 814,560행(97.407%)의 원인을 밝히고, 원본 정수 실행가능영역과 물리를 유지하는 행 압축을 검증하는 것이다. S2–S7과 A1→M1→A2→M2 추가 Heavy는 보류한다. 과거 S1의 Native 30.241초, Build 79.336초, Presolve 8.39초, 중단된 Root LP 17.57초, UB/LB는 그 당시 case의 관측이며 새 case 전후 성능 비교의 baseline으로 바꾸지 않는다.

## 구현된 opt-in 경로

`run_original_pilot(..., grid_compression="EXACT_NATIVE_BLOCK")`은 원본 `v42_native.grid.add_grid`를 그대로 호출한다. forwarding model이 한 슬롯의 원본 행을 Gurobi에 생성한 뒤 실제 CSR/RHS/sense를 읽고, 증명된 행만 삭제한다. 비활성 MESS의 원본 P/Q와 전체 24개 site injection, 96슬롯, 모든 transformer current/kVA 및 thermal face 축은 원본과 같다. 기본값 `NONE`의 기존 pilot은 바뀌지 않는다.

이 버전은 원본 행의 생성 작업을 모두 수행한다. 슬롯별 readback·증명·삭제의 추가 시간이 있으며 generation 속도 개선은 주장하지 않는다. 한 슬롯의 미압축 행과 이전 슬롯의 유지 행을 함께 보관하므로 원본 814,560개 native 행 전체를 동시에 보관할 필요는 없다. 실제 메모리·Presolve·Root·Native Runtime의 차이는 동일 case의 순차 실측 전까지 NOT_RUN이다.

## 포함 관계의 증명

원본을 F={x: l≤x≤u, physical(x), 각 원본 계통행}이라 하고 압축을 C={x: 동일 l/u, 동일 physical, 유지 계통행}이라 한다. 유지행은 원본행의 부분집합이므로 F⊆C이다.

삭제행은 다음 두 가지 증거만 허용한다.

1. **동일 LHS**: native의 nonzero column ID와 저장된 IEEE float 계수가 정확히 같은 부등식만 묶는다. `<`와 `>` sense를 섞지 않는다. `<`는 최소 RHS, `>`는 최대 RHS 행을 대표로 유지한다. 같은 RHS는 exact duplicate, 느슨한 RHS는 dominance이다. 대표도 box로 만족됨이 증명되어 삭제된 경우 그 box 증명을 함께 사용한다. Equality 행은 삭제하지 않는다.
2. **원본 bound box**: 저장된 native 계수를 exact dyadic 수로 해석한다. 각 곱과 누적 합을 +∞ 방향 nextafter로 둘러싼 상계가 native RHS 이하이면 원본 l/u를 만족하는 모든 x가 그 행을 만족한다. 필요한 maximizing endpoint가 무한이면 그 행을 유지한다. 정확히 zero인 계수만 zero로 취급하며 epsilon 삭제는 없다. Constant-only 행도 만족 여부를 같은 원칙으로 검사한다.

따라서 모든 삭제행이 C에서 함의되고 C⊆F이다. F=C는 LP 영역에서도 성립하므로 원본 binary/integer 영역에도 성립한다. PCS16, Mode, SOC, route flow, ETA/에너지, 변수 bounds/types, objective는 바뀌지 않는다. Noncanonical CSR는 float duplicate summation으로 계수를 바꿀 수 있으므로 fail closed한다.

## 실제 1슬롯 Native0 관측

`MESS_NATIVE0_CSR_PROBE01`은 현재 common science de43b37c… / case 1ea2b1ca…에 명시적 과거 AIDC anchor 83f506e6…를 사용한 부분 capture이다. 새 Known A1 인증으로 취급하지 않는다.

| 항목 | 관측 |
|---|---:|
| 원본 slot0 계통 행 / NNZ | 8,485 / 54,185 |
| 유지 slot0 계통 행 / NNZ | 2,276 / 15,907 |
| Exact duplicate 삭제 | 31 |
| Outward box 삭제 | 6,057 |
| Constant box 삭제 | 121 |
| 물리 행 / 전체 변수 | 21,684 / 7,711 |
| 부분 모델 Build | 7.691초 |
| 계통 capture·증명·삭제 | 2.534초 |
| Optimize / Presolve 호출 | 0 / 0 |

실제 Gurobi CSR와 원본 row attributes/proof arrays는 `SOLVE/EXACT_GRID_CAPTURE/SLOT_000.*`에 저장되었다. 첫 prototype은 native bound/type/name 축의 hash만 기록했고 그 실제 배열 파일은 저장하지 않았다. 이 한계를 숨기지 않는다. 이후 builder는 실제 domain 배열과 물리 CSR도 원본 상태에서 저장하도록 수정했다. 최종 shared native cost는 이 capture로 증가하지 않았다.

첫 슬롯은 초기 위치 때문에 여러 P/Q 변수가 구조적으로 존재하지 않는다. 따라서 source-formula에서 모든 선택 site에 변수가 있다고 둔 이전 audit와 constant/duplicate 개수가 다르다. 어느 결과도 전체 96슬롯의 실측 압축율로 외삽하지 않는다. FULL96 원본행 capture, 정수 feasible certificate, UB/LB, 성능 개선은 모두 아직 NOT_RUN이다.

## 모든 candidate의 원본 FULL 검증

전체 capture가 완료되면 `original_problem()`은 보관한 원본 물리 CSR와 각 슬롯의 원본 native CSR/RHS/sense를 합친다. 실제 압축 모델의 CSR와 유지행의 byte identity 및 행 RHS/sense/name을 확인한다. 최적화는 압축 모델에서 수행하더라도 `case.original_A/original_d`는 삭제 전 원본이다. 모든 raw candidate는 기존 strict_full의 원본행·bound·integer·objective 검사와 원본 4대 차량 PCS/Mode/SOC/routes replay를 통과해야 UB registry에 입장한다. Clip/round, 과거 인증 복사, restricted LB 승격은 없다. 부분 1슬롯 capture는 solve와 FULL 인증을 금지한다.

## Supervisor의 다음 순차 비교

Known A1이 실제 FULL로 끝난 후에는 그 결과의 content anchor, 고정 MESS plan, current common bindings, source response/electrical/thermal bytes를 두 variant에 동일하게 사용한다. 과거 S1 anchor/timing과 새 A1 case를 전후 결과로 섞지 않는다.

권장 비교는 원본 S1을 공유 원장/RAM gate 아래 한 번만 생성하고, 실제 전체 CSR와 l/u/types/names/objective/row axes를 immutable artifact로 남기는 것이다. 원본 Native 20–30초와 raw FULL replay를 별도 label로 기록한다. 그 **동일한 모델**에서 위 exact 증명의 삭제행을 제거하고 fresh reset 후 압축 Native 20–30초를 별도 label로 기록한다. 각 mode의 Build/증명 overhead/Presolve/Root/UB/LB/NNZ/RSS/Private Commit을 따로 보고하고, 이전 solve의 LB를 두 번째 solver의 관측으로 복사하지 않는다. 전/후 모두 전체 원본행과 4대 물리 replay를 사용한다.

실행 전 최소 8GB available RAM 및 canonical shared budget의 잔여/worker admission을 확인한다. 이번 static 구현은 자동 solver retry, 새 ledger 또는 추가 Heavy를 시작하지 않는다. source-generation 단계에서 직접 행을 생략하는 후속 최적화는 실제 native CSR와의 exact 검증이 먼저이며, source projection의 last-bit 차이를 무시해 같은 계수라고 가정하지 않는다.

같은 모델 비교용 helper는 `compress_existing_native_grid_model(model, coefficients, authority, output=..., identity=stage_bindings, grid_first=21684)`이다. 실제 original native matrix/domain을 한 번 캡처하고, 96슬롯의 source family order 및 모든 proof를 확인한 후 행을 제거한다. 이 helper는 Optimize/reset을 호출하지 않는다. 반환된 `original_A/original_d`로 두 번째 raw candidate의 FULL 검증을 해야 한다. 원본과 압축 bound/UB는 별도 solver 관측으로 기록한다. 기존 FULL validator 호환을 위해 전체 original CSR를 메모리에서 재구성하는 구현이며 streaming replay로 표현하지 않는다. 원본 CSR 재구성 및 유지행 CSR 비교의 임시 메모리도 실제 FULL96 계측 대상이다.

## 최종 Native0 확인

최종 `MESS_NATIVE0_CSR_PROBE02`는 실제 native bounds/types/names/physical CSR 배열을 immutable NPZ로 저장했다. 저장된 original slot0 CSR와 domain으로 삭제 proof를 다시 계산하여 PASS였고, PROBE01의 native matrix/domain hash를 정확히 재현했다. 최종 22개 semantic test는 5.01초에 PASS했다. 두 번째 부분 Build는 8.014초였고 행/NNZ 및 삭제 개수는 위 표와 같다. 이 Build 수치는 전체 96슬롯 Build가 아니며 이전 79.336초와의 속도 개선률을 계산하지 않는다. `MESS_NATIVE0_EXACT_GRID_COMPRESSION_VALIDATION.json`에 최종 현재 binding과 실제 파일 SHA를 기록했다. PROBE02도 Optimize/Presolve 호출은 0이고 FULL96 성능·UB/LB 인증은 NOT_RUN이다.

## 동일 모델 20초 + 20초 benchmark 실행 adapter

새 opt-in은 `run_original_pilot(..., seconds=20, compare_exact_compression=True)`이다. CLI는 다음과 같다.

```powershell
python -m tools.run_v42_mess_scaling_pilot --run --mode EXACT_REDUCED --seconds 20 --compare-exact-compression --output runtime/v42_unified/MESS_EXACT_COMPRESSION_COMPARE01
```

한 번 생성한 원본 S1 모델에서 ORIGINAL 20초를 실행한다. 실제 original CSR/domain의 hash를 고정하고 96슬롯 proof/capture/removal/reconstruction을 수행한 뒤 `model.reset(1)`로 이전 solution/search/MIP starts를 지운다. COMPRESSED도 원본 CURRENT_SOURCE_STAY START 또는 모두 UNDEFINED를 동일하게 사용한다. 첫 solve의 개선 incumbent를 두 번째 START로 전달하지 않는다. 두 cap은 같으며 공유 잔여 budget에 처음부터 40초가 없으면 입장하지 않는다. 각 Native 직전과 압축 직전 최소 8GB available RAM 및 canonical preflight를 확인한다.

두 canonical label은 `MESS:S1:COMPRESSION_BENCH:ORIGINAL`과 `MESS:S1:COMPRESSION_BENCH:COMPRESSED`이다. ledger stage_context에는 같은 original numeric matrix/domain/case SHA, 각 selected SHA, 동일 start SHA, comparison ID와 실제 equivalence certificate의 파일 SHA를 포함한다. 각 variant는 별도 log, raw packets, 원본 ALL행 및 full4 replay, incumbent bank, 자체 UB/LB/Gap을 갖는다. 두 번째 LB는 두 번째 solver에서 새로 관측한 값만 사용한다. 최종 registry는 둘 중 더 좋은 현재-case FULL 해와 이동 FULL 해를 최종 원본행 replay 후 보관하지만, 이 사후 보관은 두 번째 solver START에 전달되지 않는다.

Build는 한 번의 원본 build이고 압축 proof/capture/artifact-write/native-remove/CSR-reconstruction은 별도 wall phase이다. Presolve/Root 시간은 native log가 authoritative하며 callback-phase wall attribution 및 0.25초 sampled RSS/private peak는 보조 관측이다. OS cumulative process peak를 각 phase의 독립 peak처럼 표현하지 않는다. 실제 전후 성능은 아직 NOT_RUN이다.

현재 B1 A1은 FULL을 얻지 못했으므로 위 standalone CLI의 양쪽 anchor는 모두 명시적 HISTORICAL_DIAGNOSTIC_AIDC_ANCHOR이며, 최신 shared source case/bindings를 동일하게 사용한다. 이 결과를 새로운 Known A1 또는 A1→M1 통합 PASS로 부르지 않는다. 과거 S1 timing/UB/LB는 이번 두 solver에 전송하지 않는다. 기존 mandatory S1 measured reports는 그대로 보관하고 새 benchmark 결과는 새 실행 디렉터리에 기록한다.

최종 24개 Native0 test는 4.86초에 PASS했다. 이 중 benchmark transport 테스트는 mock-only이고 실제 모델/Optimize를 생성하지 않는다. 동일 START, 두 reset, 별도 labels/equal caps, 두 번째 fresh bound 및 최초 solve의 더 좋은 FULL 해의 사후 보관을 검사했다.

Start의 실제 `getAttr("Start")` readback vector가 지정 vector와 bit-exact인지 두 variant 모두 검사하고 `NumStart`, expected/actual Start SHA 및 policy를 variant receipt와 canonical stage_context에 저장한다. CURRENT_SOURCE_STAY가 현재 FULL을 통과하지 못한 경우 root가 명시적으로 승인한 no-start 비교를 사용하며 두 variant를 모두 UNDEFINED로 맞춘다. 마지막 Native0 테스트 실행은 24 PASS / 6.76초였다. 실제 benchmark Native는 아직 실행하지 않았다.


최종 benchmark control-flow regression은 두 번째 solver bound가 첫 번째의 더 좋은 same-case FULL UB를 넘을 때 top-level bound를 거부하는 경우도 검사한다. 마지막 Native0 테스트는 25 PASS / 6.62초였다. 최종 summary는 numeric_scope를 그대로 기록하고 current A1–M1 및 four-stage integration certified를 false로 표시한다. 큰 original/full CSR와 슬롯 proof 배열은 gitignored `runtime/` 아래에 두고 작은 결과/receipt만 연구 보고서에 연결한다.
