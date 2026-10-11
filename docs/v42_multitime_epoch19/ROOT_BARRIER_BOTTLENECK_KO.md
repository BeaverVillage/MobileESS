# Root Barrier 병목 진단 — Native0, Threads1 유지

Source18r은 Exact 정수·LP 사영 검증과 Dense 압축을 통과했지만, 승인됐던 단 한 번의 Full C3A MILP Root는 600초 제한에서 **ROOT_INCOMPLETE**다. 현재 우선순위는 Root LP 완료이며, ObjBound0.289400491085와 Gap57.1927%만으로 LP가 약한 것이 주원인이라고 판정하지 않는다. 기존 로그·저장 CSR·계수·메모리 receipt만 분석했다. 이번 작업의 **Optimize/LP/MILP/Presolve/Full 모델 재생성/새 Full-size 제약 삽입/파라미터 탐색은 모두0**이다.

사용자의 메모리 정정에 따라 **Threads=1과 현재 Worker 수를 유지**한다. Threads4 권고를 철회한다. 2Workers×4Threads 및2Workers×2Threads, Worker/Threads 자동 증가, 가상메모리 증설·과도한 페이징은 허용하지 않는다. StageBudget/A1/A2/NativeStopRequested/사용자A/공용 중단 정책을 수정하지 않았다. 공식 5월 캠페인 HOLD 및 비활성 Supervisor/예약을 유지한다.

## 600초 로그의 실제 상태

| 항목 | 동결 Source18r 실측 |
|---|---:|
| Gurobi 입력 Rows / Columns / NNZ |715,596 /354,277 /7,911,369|
| 입력 Binary |9,322|
| MIP Presolve |70.78초|
| MIP Presolved Rows / Columns / NNZ |610,100 /354,177 /7,998,268|
| 내부 Root LP Rows / Columns / NNZ |555,551 /397,098 /7,903,205|
| Ordering |2.59초|
| Barrier Dense columns |4,536|
| `AA' NZ` |1.040e+07 — 로그 반올림값|
| `Factor NZ` |4.897e+07 — 로그 반올림값|
| `Factor Ops` |7.065e+10 — 로그 반올림값|
| Factor memory |로그의 대략800MB 추정; 실제 할당 bytes는UNKNOWN|
| Factor iteration time |로그의 대략2초 추정; 실제 Factorization 전용 시간은UNKNOWN|
| Barrier 반복 |56회, 출력 행은Iter0~56의57개|
| API Native Runtime |601.896999835968초, effective TimeLimit600|
| 로그 Barrier summary |56iterations in601.63seconds; 전용 Barrier wall로 재분류하지 않음|
| Root relaxation |time limit,0simplex iterations,528.89초 — 미완료 경과시간|
| Crossover |진입 없음, 완료시간없음|
| Root 완료시간 /180초 목표 |없음 /미달성|
| 원본 FULL 검증 U4 UB |0.6760534504652341|
| Solver ObjBound /Gap |0.28940049108548904 /57.1926611888%|

Gurobi 내부 변환에서 열이 늘었으므로 입력 CSR과 내부 Root LP의 축은 같다거나 4,536개 Dense column이 특정 입력 변수라고 주장할 수 없다. 저장된 Native Presolved CSR·변수명 mapping은 없으므로 **내부 Root의 실제 대형 행·열 목록과 특정 변수별 Factor 기여는UNKNOWN**이다. 추가 Native export를 실행하지 않았다.

## 56회 Barrier 수렴

전체57개 출력 행을 [CSV](evidence/SOURCE18R_BARRIER_ALL_ITERATIONS.csv)에 저장했다. 다음 수치는 로그 표시값이며 원본 FULL primal/dual certificate가 아니다. Time은 반올림된 누적 Native log clock이다.

| Iter |Time(s)|Primal display|Dual display|Primal residual|Dual residual|Complementarity|
|---:|---:|---:|---:|---:|---:|---:|
|0|117|1.32421979e+03|-6.16259961e+11|6.77e+07|0|1.72e+08|
|13|180|0.682630379|-8.53444525e+07|5.41e+02|9.06e-11|9.54e+02|
|24|219|0.667038127|-15.3700103|1.17e-05|1.99e-13|1.09e-04|
|30|307|0.566804292|0.0246695404|3.45e-07|1.37e-12|3.68e-06|
|40|440|0.540015399|0.496570515|4.34e-08|1.01e-11|2.95e-07|
|47|552|0.535646657|0.531535211|8.16e-09|6.41e-11|2.99e-08|
|51|578|0.534851602|0.534589362|1.52e-09|2.38e-10|5.94e-09|
|52|584|0.534786157|0.534717560|1.86e-09|2.88e-10|3.88e-09|
|53|588|0.534712036|0.535388670|1.85e-09|2.42e-10|1.65e-09|
|54|592|0.534683848|0.535544589|1.16e-09|2.70e-10|8.66e-10|
|55|597|0.534676683|0.535563995|1.16e-09|2.68e-10|5.23e-10|
|56|602|0.534667631|0.535551572|1.16e-09|2.58e-10|3.05e-10|

180초에는 아직 큰 Primal residual과 음수 Dual objective가 남아 있다. Iter24 이후에는 feasible region 접근이 느려졌고, Iter54~56에서는 Primal residual 표시값이1.16e-9로 정체한 동안 Complementarity가8.66e-10→3.05e-10으로 줄었다. Iter53~56의 Dual 표시값이 Primal보다 높다. 이 불일치와 미완료 상태 때문에 마지막0.53555를 원본 LP 최적 LB로 쓰거나 API ObjBound를 대체하지 않는다.

출력 clock에서 유도한 Iter0→24의 평균 transition은102/24=4.25초,24→47은333/23=14.48초,47→56은50/9=5.56초다. 이는 표시 간격이고 선형계 풀이·refinement·callback·기타 처리의 전용 profiling이 아니다. 117초 첫 출력에는 Presolve/Ordering 등 선행 시간이 포함된다. 601.63와528.89를 서로 더하지 않는다.

관찰은 큰 Root 행렬·높은 Factor 비용·중반의 느린 잔차 수렴·종반 Primal 잔차 정체다. **Factorization이 전체시간 몇%인지, 수치 conditioning과 구조 fill 중 무엇이 지배적인지, LP 약성이 얼마인지의 인과적 분해는UNKNOWN**이다. 조건수·pivot/refinement 횟수·Factor별 실제 메모리·동기화된 시스템 peak trace는 저장되지 않았다. Root 미완료를 우선 병목으로 판정한다.

## 전체 프로세스와 시스템 메모리

| 측정 | Bytes |GiB 또는 로그 단위|
|---|---:|---:|
| 프로세스 lifetime Peak RSS |6,404,554,752|5.965GiB|
| 프로세스 lifetime Peak Private Commit |9,086,836,736|8.463GiB|
| Full Native 반환시 RSS |5,281,120,256|4.918GiB|
| Full Native 반환시 Private Commit |6,511,312,896|6.064GiB|
| 시스템 RAM total |34,049,220,608|31.711GiB|
| 반환시 Available RAM |9,548,398,592|8.893GiB|
| 반환시 Commit total /limit |48,362,708,992 /68,408,958,976|45.041 /63.711GiB|
| 반환시 Commit 여유 |20,046,249,984|18.670GiB|
| Gurobi MaxMemUsed |별도 Solver 속성|3.263167186GB|

Gurobi MaxMemUsed는 Python·CSR·복원 proof·저장 기준 모델을 포함한 전체 메모리가 아니다. Peak RSS/Private Commit은 프로세스 전체 수명 상한으로 Restore/Native0/Init/U4/Full이 모두 기여할 수 있다. Full600 전용 peak라고 단정하지 않는다. Available RAM/Commit은 반환시 시스템 snapshot으로 동시 최악치가 아니다. 시스템 Commit_peak==Commit_limit은 과거 전역 high-water이며 이 Root가 commit을 소진했다는 증거가 아니다.

사용자가 보고한 현재2Workers에서 RAM약90%는 별도 운영 제약으로 존중한다. Source18r 단일 프로세스의 반환시 RAM사용71.96%나 이후 유휴 snapshot과 같은 시점·PID 조건으로 묶지 않는다. 두 Worker에 peak값을 단순 두 배 해 실제 동시 메모리로 보고하지 않는다. **실제 동시 Peak RSS/Private Commit/Available RAM/Commit 여유 없이는 추가 병렬성의 안전을 증명할 수 없다.** 과거1Worker×Threads4 예상·권고도 현재 적용 대상으로 삼지 않는다.

`v42_common_mess/model.py`의 override 이후 Threads1 재설정, `engine.full_milp_parameters`, `native_readback.ROOT_PARAMETERS`, 실행 전 ProbeBudget 제한을 확인했다. Native0/Initialization/Fresh U4/Full 실제 readback은 모두Threads1이다. PR131의 Threads4·NumericFocus1·1e-8 tolerance·다른 Source/행렬·별도 relaxed LP74/129초 결과는 현재 동일조건 비교가 아니다. 당시 MIP Original Root208.621초/Compact300초 미완료 및 부분 중단까지 기록하고 현재 성능·메모리 근거로 전용하지 않았다. 현재 Threads2/4 적용 가능성은 승인되지 않으며 권고 철회 상태다.

## 입력 CSR의 큰 연결과 Dense Response

두 저장 CSR을 한 번에 하나씩 읽고 degree/coefficient 통계만 계산했다. Full 모델을 만들지 않고 A*A'나 Factor 행렬도 형성하지 않았다.

| 입력 변수 family |Columns|NNZ|최대 column degree|
|---|---:|---:|---:|
|global rho_max|1|333,689|333,689|
|injection_P|2,263|2,533,401|1,150|
|injection_Q|2,237|2,514,887|1,150|
|response_voltage_shared|14,890|14,890|1|
|Q|8,942|122,765|1,010|
|route_flow|207,736|927,098|15|

입력 최대 row degree는602이며 에너지 행384개/217,630NNZ에 실제 이동에너지 항이 모여 있다. response_line_P/Q/correction 정의행은각25,152개, 최대degree49이고 각각1,210,659/1,210,862/1,207,844NNZ다. 전력 주입 변수들이 시간별 계통 응답을 크게 연결한다. 전역 rho는96슬롯 thermal faces를 함께 잇는다. 이 구조는 fill 조사 우선 대상이지만 실제 Native ordering/dense-column 처리 결과와 동일시하지 않는다.

Dense14,890개 변수는 모두 같은 시간의 단일 정의등식에 coefficient+1로 연결되고, 상·하한을 variable bounds로 가진다. 다른 consumer inequality 연결0, objective0이다. 입력에서는 시간을 새로 가로질러 연결하지 않는다. C3A 대비 행−14,890/열+14,890/NNZ−698,341(**8.11%**)이며 input row-degree-square proxy도32,765,107만큼 감소했다. 그러나 helper가 Native presolve에서 어떻게 치환됐는지와4536densecol에 들어가는지는UNKNOWN이다. Source18r 내부RootNNZ7,903,205만으로 Dense의 Factor gain을 증명할 수 없다. 과거 다른 Source의 Root 시간을 이 Source의 성능으로 사용하지 않았다.

## 시간별 rho Epigraph — Exact 증명, 효과 미검증

현재 실제 rho는C,[0,1],objective1이고 모든333,689개 행렬 연결은 thermal `g_i(x)-rho<=b_i`의 coefficient−1이다. 모든96슬롯이 포함된다. 시간별 연속tau_t∈[0,1],objective0을 두고 해당 행을 `g_i(x)-tau_t<=b_i`, 링크를 `tau_t-rho<=0`으로 바꾸는 후보를 정적으로 검토했다.

Forward: 원본 가능점에서 tau_t=rho로 확장하면 모든 행이 성립한다. Reverse: tau_t<=rho이므로 `g_i(x)-rho<=g_i(x)-tau_t<=b_i`; tau를 버리면 원본 모든 행·범위·정수조건이 성립한다. 계수/RHS/bounds/objective를 그대로 복사하므로 **정수·LP 사영과 LP 최적값은 정확히 같다**. LB 강화를 주장하는 후보가 아니다. 실제 현재 coefficient/domain certificate 및 독립16검사와 exact rational 작은fixture PASS다.

가정한 비용은 **연속열+96,행+96,NNZ+192,Binary+0**; 715,692rows/354,373cols/9,322binary/7,911,561NNZ다. global rho degree333,689→96, tau degree2,516~3,545다. 실제 생성·삽입은0이다.

rho만의 uncoalesced row-pair proxy는55,674,007,516→581,040,157로 작아진다. 이것은 실제AA'NNZ/FactorNZ가 아니다. 다른 공통열에 의한 중복, Native presolve, ordering, Dense column 처리를 제외한 값이다. 작은2슬롯×3face 반례에서는 raw normal graph edges15→13인데 link-first elimination factor entries21→33으로 오히려 늘었다. 따라서 **fanout 감소만으로 fill·RAM 비증가를 보장하지 않는다**. Native가 helpers를 없애 원래 전역 연결을 복구할 수도 있다. 실제 FactorNZ/Ops·process peakRSS/private·시스템 여유·Root 시간 효과는UNKNOWN/UNPROVEN이며 Production 채택하지 않는다.

## Exact Scaling — 수치 후보의 조건과 한계

실제 Dense 계수는1.0000053701775258e-13~392.3141121612922, 비율3.92312e15다. 로그RHS range는2e-25~2e3이며 large matrix coefficient range 경고가 있다. 저장 계수27,597개는1e-12이하,117,128개는1e-12초과1e-10이하다. 작은 값이 실제 저장됐다는 사실은 삭제 근거가 아니다. 행 내부 계수 비율과 모델 전체 범위도 다르므로 전역 범위만 conditioning 측정치로 쓰지 않는다.

Native0 scalar 검사에서 양의2^k row scaling은 모든7,911,369계수/RHS의 bit-exact roundtrip을 통과했다. row-max normalization은계수범위1.00000537e-13~1.999235로 줄이지만125,564개 row를 downscale해 같은 absolute FeasibilityTol에서 원본 단위 허용오차를 넓힐 위험이 있다. 따라서 적용하지 않는다. Upscaling-only98,503rows는 이 문제를 피하지만 전체 최소·최대범위는 그대로라 전역 range 개선을 주장하지 않는다.

Continuous finite-bound column의2^k 치환 scalar 검사도 coefficient/finitebounds/objective exact roundtrip을 통과하고 정수·Binary열은 그대로다. 가상 계수범위2.63348038e-11~1024지만 실제 scaled CSR·Native 모델은 만들지 않았다. 열 치환 `x=2^k*z`에서는 새 변수의 bound 허용오차delta_z가 원본 단위에서2^k*delta_z가 되어 k>0이면 넓어질 수도 있다. 행·열의 NNZ/구조 graph는 같으므로 구조 fill 감소 증명이 아니다. combined scaling의 이득도 측정하지 않았다.

향후 구현에서는 `x=2^k*z`, 양의 row factor, 모든 저장 coefficient/RHS/objective/finitebound의 정확 유리수 일치와 역복원, integer exponent0, overflow/subnormal rounding/0 발생 금지 및 실제 Native readback을 모두 요구한다. 원본 FULL 단위의 strict replay를 유지해야 한다. 현재 FeasibilityTol1e-9/OptimalityTol1e-9/IntFeasTol1e-8,NumericFocus3,ScaleFlag2를 변경하지 않았다. 작은 coefficient0처리·tolerance완화·threshold pruning도0이다. 수치 conditioning/잔차/메모리/시간 개선은UNKNOWN이다.

## 우선 조치와 향후 단 한 개 후보

추가 Native 없이 결정할 조치는 **현재 병렬성·HOLD·동결 증거를 유지하고, Tightening 추가를 끝내며, 정확한 rho 시간분할의 구조 certificate를 후속 검토 후보 하나로 남기는 것**이다. 큰 Full 모델/AA' 재생성 대신 저장 incidence와 tiny exact proof를 사용했다. 현재 후보의 실제 메모리 비증가가 증명되지 않았으므로 적용·실행 승인은 없다.

실제 후속 실험이 별도 승인된다면 후보는 **Dense 이후 시간별rho Epigraph 한 종류**만이다. 먼저 별도 successor의 작은fixture와 coefficient-preserving producer/verifier·original FULL 정수/LP mapping·Native CSR readback을 통과시키고, baseline과 successor를 동시에 보유하지 않는 메모리 설계 및 전체 프로세스/시스템 headroom 기준을 검토해야 한다. 새 tolerance/scaling/Threads 변경을 같은 실험에 섞지 않는다. 조건 충족 후에만 **추가 Worker 생성 없이, 한 Worker·Threads1에서 Full Root 최대600초 정확히1회**, sweep/중복0의 예산을 별도 승인 대상으로 제시한다. 실제 PeakRSS/PrivateCommit과시스템 AvailableRAM/Commit을 기록해 비증가 여부를 판단해야 한다. 현재 작업에서는 준비 모델·Solver 호출·예약 모두0이고, 승인 전Heavy실행을 하지 않는다.

## Source와 원본 파일 SHA

Baseline PR207 frozen commit: `497609b46faa14ea7e32a9483a333ab32fd264ef`.
Execution commit: `85168a00256f4427c9895aa2ffb8623b6158ebef`.
Model Source SHA: `146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8`.
Case SHA: `34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292`.
정적 Root 분석 Source SHA: `9db84e89551b2f1abab70ad0403f4711eaad4db780471925326e50e7027d6414`.

| 원본 파일 |SHA256|
|---|---|
|FULL_ROOT_ONCE/NATIVE_GUROBI.log|ae2dc49ed51950186f58bf3487d76134543881fe00ad9ff279dd5cbba83d78ed|
|FULL_ROOT_ONCE/RESULT.json|28fea4d2a4f0d54226e670ba42db7d6d945eb99f77b03416f76bd44c7158116c|
|C3A_A.npz|4cdb1df77ecc5ac71a91c56f8bba15b3d9c194eedd8fb653b52d442c0d929d80|
|C3A_DATA.npz|98ae638d6de001003e20e6bab829f87d743b47f267e6d68adc59bcdcd3a67b04|
|DENSE_RESPONSE_A.npz|e9e0c8a4f042f4014a6068662077e186fb6aa611e9ec2f51d83c886c197c523c|
|DENSE_RESPONSE_DATA.npz|48cf0469e934c1ef63147afda89c67b7ecf91092ad903089baeca8d7a5fdb5a8|

분석 코드·복사 증거 SHA는 [Root evidence index](evidence/ROOT_BARRIER_EVIDENCE_INDEX.json), 원본 coefficient·Readback·메모리·PR131 SHA는 각 첨부 receipt에 있다. Log parser wall0.00457초, saved CSR 단계 wall3.980+3.069초 등은 정적 CPU/wall이며 **이번 Native 호출/Runtime은0회/0초**다. 작은 exact fixture·fill 반례도 Solver를 호출하지 않았다. Figure 생성 대신 전체 CSV/표를 제공했다. Source18r·PR207의 실험 결과·Native ledger·원본 과학 증거는 변경하지 않았다.
