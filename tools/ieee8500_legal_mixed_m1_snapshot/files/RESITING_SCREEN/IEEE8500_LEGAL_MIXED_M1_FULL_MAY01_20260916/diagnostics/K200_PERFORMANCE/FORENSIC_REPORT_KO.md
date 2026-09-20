# IEEE8500 B2 K200 성능 forensic 및 current-layout seed 검증

측정 대상은 `legal_mixed_M1`, 2025-05-01, 6 MESS, 24 service PCC, s_DC=s_MESS=1이다. 최초 forensic 동안 production은 수정하지 않고 py-spy `--nonblocking`, 5 Hz, 480초로 외부 계측했다. 이후 사용자의 즉시 중지 요청에 따라 IEEE8500 supervisor/worker만 중지했고, 조건부 수정·재개 승인을 근거로 격리 proof가 PASS한 뒤 B2만 clean namespace에서 다시 시작했다. IEEE123에는 중단·설정 변경을 하지 않았다.

**핵심 원인**

기존 20개 seed 파일을 잘못 복사한 것이 아니다. 현재 B0에서 생성된 20개 seed도 `tpx21459660c0`의 특정 시간·단자에 집중되었다. 새 downstream PCC에서는 이 제한된 모델의 rho를 거의 0으로 낮출 수 있다. 기존 separation은 `loading > reduced_rho + 1e-8`인 모든 선로 상태를 추가한다. 따라서 처음 STAY에서 전 시간대의 거의 모든 양의 loading 상태가 추가됐고, `_local_search`가 이 집합을 이후 후보의 `line_states`로 전달하여 매 후보마다 재구성했다.

격리된 원래 20-state 초기 relaxation 결과: 이전 배치 rho=0.848951511084, 현재 배치 rho=3.97639853e-8. 두 모델 모두 482 variables / 2,530 rows이며 Gurobi 계산 자체는 약 0.004초였다. 이 값은 축소된 초기 모델의 하한이며 AC-feasible production 결과가 아니다.

현재 첫 STAY cache의 닫힌 선로 state 수는 1,175,712개이고, 이후 후보도 같은 집합을 이어받았다. state마다 16개 polygon face를 생성하므로 선로만 약 18,811,392개의 constraint 삽입 경로가 생긴다. 이전 첫 STAY cache는 선로 state 20개였다.

추가 격리 진단에서 원래 20-state 초기해에 대해 full linear evaluation만 한 번 수행했다. 첫 추가 요구는 line 1,175,692 / voltage 79,227 / transformer current 172 / kVA 344였다. 초기 20개와 합하면 정확히 1,175,712개이다. 이때 축소 모델 rho는 약 4e-8이지만 전체 선형 검사 rho는 21.73757이고 certificate는 FAIL이었다. 이는 중간 relaxation이 안전한 해가 아님을 정상적으로 검출한 것이며 최종 feasible 결과로 사용하지 않았다. 거대한 제약을 실제 추가하는 루프는 이 진단에서 실행하지 않았다.

**실측 시간**

|비교|샘플|candidate wall time|
|---|---:|---:|
|이전 첫 K200 전체|201개, cache hits=0 / misses=201|중앙값 1.6343초, 전체 restricted 단계 401.0013초|
|현재 병적 실행|처음 완료된 13개 cache|중앙값 401.2403초, 범위 367.8263–425.8809초|
|current-layout seed, 후보별 독립 검증|5개|중앙값 7.0255초|
|current-layout seed, 대표 후보 간 state 전달 재현|처음 5개|중앙값 6.6639초|

이전 fast run도 최초 K200에서 201개 모두 실제 solve했다. 따라서 이전 속도가 cache hit 때문이었다는 설명은 해당 단계에서는 성립하지 않는다.

|단계|480초 샘플 비율|약 409초 candidate advance로 환산|해석|
|---|---:|---:|---|
|전기 제약 표현식·모델 materialization|82.5%|약 337초|주로 `_add_fixed_line` 및 `_fixed_expression`; 주 병목|
|Gurobi `optimize()`|11.5%|약 47초|restricted P/Q/SoC solve; LP/MIP 내부 세부는 분리하지 않음|
|전체 선형 전기 상태 evaluation|1.33%|약 5.4초|96-slot affine/polygon 검사; OpenDSS가 아님|
|모델 dispose|0.625%|약 2.6초|native model 해제|
|cache serialization/I/O|0.083%|약 0.34초|샘플 추정; 순수 disk 시간과 serialization의 정확한 분리는 불가|
|기타/불완전 stack 및 미측정|3.96%|약 16.2초|44 sampling errors 포함; 이를 다른 단계 시간으로 숨기지 않음|
|candidate 생성·mobility feasibility·traffic lookup|현재 child loop 내 0회|반복 비용 0|K200 후보 평가 전 수행; 현재 실행의 준비 세부 timer는 없어 각각의 정확한 wall time은 미확정|
|OpenDSS replay / native control settling|현재 child loop 내 0회|0초|최종 route 선택 뒤 `exact()`에서 실행|

이는 2,328개 외부 stack sample로 추정한 시간 배분이며 개별 함수의 정확한 stopwatch 결과가 아니다. cache에 저장된 candidate runtime은 직접 측정값이다. cache 완료 간격에서 candidate runtime을 뺀 overhead 중앙값은 약 7.41초이며 dispose·serialization·fsync·진행 callback 등을 포함하므로 전부 disk I/O로 간주하면 안 된다. 이전 cheap screen은 LOCAL_SEARCH 기록상 301.03초/parent이며 child당 반복 시간이 아니다.

**CPU/RAM 경합**

약 483초 자원 관측에서 전체 CPU 평균 42.5%, B2 평균 CPU 약 0.925 core였다. IEEE123의 세 worker는 당시 May-13/14/15 Actual 단계였으며 각각 약 0.90 core를 소비했다. 설정상 3×4라는 이유로 12 solver thread가 모두 포화했다고 볼 수 없다. B2가 single-thread Python 모델 생성에 대부분을 쓰고 있어 Gurobi Threads=4만으로 이 구간이 빨라지지 않는다.

가용 RAM 중앙값은 약 12.11 GiB이나 최저 0.75 GiB까지 내려갔고, 그때 B2 RSS는 약 20.11 GiB였다. 따라서 일시적 RAM 압력은 실제로 있었다. 다만 시스템을 단독 실행한 대조군이 없으므로 IEEE123 경합에 의한 slowdown 비율을 분리해서 주장하지 않는다. Windows psutil의 swap sin/sout=0은 hard page fault 부재 증거가 아니다. B2 I/O 평균은 read/write 각각 약 0.017 MiB/s였다.

**artifact/cache 비교**

경로 약어: `OLD = D:/ChatGPT/Mobile ESS 2/independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913`, `NEW = D:/ChatGPT/Mobile ESS 2/RESITING_SCREEN/IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916`, `BEAM = B2/beam/2025-05-01/B2/B2`.

|항목|previous fast path|current path / 존재 상태(수정 전)|hit·재생성·runtime 영향|
|---|---|---|---|
|candidate cache|OLD/B2/candidate_cache, 2,211개 보존|NEW/B2/candidate_cache, 조사 당시 13~14개 신규|PCC binding, coefficient, screen authority와 namespace identity가 달라 이전 결과 재사용 불가. 이전도 첫 K200은 cold misses 201개|
|route enumeration|OLD/BEAM/s1/B2-ROOT/LOCAL_SEARCH.json|동일 NEW 상대경로는 아직 없음|enumeration 자체는 메모리 생성; 최종 summary는 K 완료 후 저장. candidate-table SHA 동일|
|traffic/path cache|OLD/traffic/shared/traffic/2025-05-01/ROUTE_TABLE.json.gz|동일 NEW 경로 존재|동일 SHA의 frozen table 재사용. 소실 아님|
|mobility feasibility|OLD/BEAM/s1/B2-ROOT/LOCAL_SEARCH.json의 2,157 feasible/52 infeasible 기록|메모리 enumeration 완료, 최종 summary 아직 없음|별도 persistent feasibility cache를 읽는 경로 없음; 후보 table SHA 동일|
|beam/K200 checkpoint|OLD/BEAM/STAGE_1..6.json 존재|NEW/BEAM에 아직 0개|첫 stage 미완료이므로 정상 미생성. 다른 전기 authority의 완료 stage를 이식하면 안 됨|
|incumbent/warm-start|OLD/BEAM/s1/B2-ROOT/SEEDS.json 존재|NEW 동일 경로 미생성|201개 restricted solve 후 생성하는 full-child seed; 누락으로 child당 7분이 된 것이 아님|
|electrical screening|OLD/BEAM/CONGESTION_MAP.json, 초기 20 states|NEW 동일 파일, 초기 20 states|모두 존재. 현재 전기 context로 재생성됐지만 한 병목에 집중된 seed rule이 새 배치에 부적합|
|coefficient cache|OLD의 sibling IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912/coefficients, 96개|NEW/coefficients, 96개|모두 보존. infrastructure 변경으로 새로운 96개 필요; candidate마다 OpenDSS로 재생성하지 않음|
|station travel matrices|OLD의 ROUTE_TABLE.json.gz|NEW의 동일 table|별도 누락된 matrix가 아니라 같은 frozen route authority를 사용|
|service domain|OLD/MESS_24_SERVICE_PCC_COLUMN_BINDING.json|NEW/동일 파일 존재|둘 다 24 services/60 controls. 6은 fleet/선정 station 수이며 이전 full route domain이 6이었다는 증거 없음|
|OpenDSS replay cache|OLD/B2/final_exact/AC_VALIDATION.json|NEW/B2/final_exact는 아직 미생성|K200 child replay cache 자체가 없음. 마지막 선택 뒤 Fresh/exact 수행|
|Gurobi nodefile/MIP-start|OLD/B2의 .mst 0개|NEW/B2의 .mst 0개|restricted 모델은 fresh build. 디스크 MIP-start를 복구하는 코드 경로 없음|

모든 경로·존재 상태·sample 파일의 전체 SHA-256은 `artifact_inventory.json`, cache identity 및 timing은 `cache_audit.json`에 기록했다. 비교 시점 이후 병적 NEW/B2는 `B2_ARCHIVE_RELOCATION.json`의 위치로 이동·보존됐으며 해당 manifest로 역사적 경로를 추적한다.

동일 SHA 증거:

- route table: `3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9`
- traffic forecast: `72f71b609de1301b4911cfabe3a7d02e5567e8c3889c50ac4892bab967246e8c`
- 첫 MESS candidate-table SHA: `3f1ab86a6acde6d85f1ee11f024b998d6f18f8d4d4058b97638d4ffef2c6b809`

cleanup evidence로 발견된 `B3_2ROUND_EXTENSION/INVALIDATED_2ROUND_RUN_MANIFEST.json`은 해당 IEEE123 2-round 하위 디렉터리 삭제 기록이다. 두 IEEE8500 namespace 삭제 증거는 발견하지 못했다. 이는 workspace 소스/manifest 조사 범위의 결론이며 파일시스템 journal 조사로 모든 과거 삭제 부재를 입증한 것은 아니다. 이전 실행의 numerical_repair.py는 현재 worker에 설치되지 않았지만 CERTIFICATE_STALLED 후에만 개입하는 retry이며, 조사한 후보는 모두 retry=false여서 이 slowdown 원인으로 확인되지 않았다.

복원할 수 있다고 검증된 누락 semantics-preserving cache는 발견하지 못했다. 안전한 route/traffic authority는 이미 동일하게 존재하며, 이전 electrical solve/cache/checkpoint는 authority가 달라 그대로 복원할 수 없다.

**수정 proof와 범위**

새 규칙은 현재 96-slot B0 loading에서 상위 32개 서로 다른 native line asset을 고르고, 각 phase/terminal의 최고 2개 slot 및 slot별 최고 line을 초기 seed에 포함한다. 초기 438 states이며 이후 active set 크기를 제한하지 않는다. 기존 full-separation 함수, tolerance=1e-8, K200 후보 domain/순위, objective, resource/SOC, 최종 exact-AC 절차는 변경하지 않는다. `rho>=0.848071657` 또는 다른 rho floor를 모델에 추가하지 않았다.

대표 후보 간 state 전달을 포함한 5개 검증에서:

- 첫 restricted rho: 0.942189089713
- 첫 separation 추가: line 55, voltage 21,325, transformer current 48, kVA 96
- STAY closure: line 499 / voltage 21,325 / current 48 / kVA 96
- 다섯 번째 closure: line 501 / voltage 21,440 / current 48 / kVA 96
- 모든 full linear certificate PASS, 기존 목적값 차이 0, 최대 rho 차이 5.2941e-9
- candidate 중앙값 6.6639초; 아직 전체 K200 또는 최종 AC 완료를 의미하지 않음

`COMPACT_SEED_PROOF.json`과 `PROPAGATED_SEED_PROOF.json`에 후보별 초기 rho·첫 추가·최종 active-set 크기·시간·기존 cache 비교가 있다. 수정은 B2 seed에만 적용했다. 기존 B2의 16개 파일은 hash 재확인 후 `B2_BEFORE_SEED_CORRECTION_1789572235`에 보존했고, B0/B1 및 고정 authority의 SHA 불변을 확인했다. 최초 production 재개 PID는 supervisor 53924 / B2 worker 47600이다. 현재 PID와 상태는 SUPERVISOR_STATUS.json을 확인한다. Actual은 실행하지 않는다.

**Production 재개 후 확인:** 최초 6개 후보가 새 namespace에서 완료됐고, STAY 18.323초 / 후속 후보 5.430–7.622초였다. 선로 state 499–502개이며 모두 full linear certificate PASS였다. 기존 cache에서 대응되는 후보는 원래 목적값과 rho의 동일 tolerance 이내 일치를 재확인했다. `PRODUCTION_SEED_FIX_VERIFICATION.json`에 확인 시점의 전체 완료 후보와 시간 및 비교를 저장했다. 최종 full B2/Fresh 성공을 앞서 선언한 것은 아니며, 그 gate는 원래 절차대로 남아 있다.
