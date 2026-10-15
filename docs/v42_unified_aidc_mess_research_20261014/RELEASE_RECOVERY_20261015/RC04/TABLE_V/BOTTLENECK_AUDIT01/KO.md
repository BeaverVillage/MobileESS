B1 A1 읽기 전용 병목 감사 — 2026-10-15

판정: 측정 구간에서 B1 A1 계산은 정상적으로 CPU를 사용 중입니다. RAM/commit/대상 프로세스 I/O 포화 증거는 없습니다. 결과의 최적성·feasible 여부는 아직 판정하지 않습니다.

8.014초 두 표본에서 PID 67000 CPU는 7.781초, 단일 코어 대비 97.09%였습니다. 16논리코어 전체 대비 6.07%는 승인된 Native Threads=1과 모순되지 않습니다. 프로세스 스레드 객체는50개이지만, 이것이50개 Native 작업 스레드를 사용한다는 뜻은 아닙니다. working set4.06GiB, private5.39GiB, 가용12.48GiB, system commit45.32%였습니다. 대상 read/write는0입니다. pagefault57,884개 증가는 soft/hard 합계이므로 이것만으로 swapping을 주장하지 않습니다. hard fault rate는 별도 측정하지 않았습니다.

관측 마지막 Native inflight wall은547.32초, 승인 cap은5400초입니다. 이 값은 관측 벽시간이며 최종 Gurobi Runtime으로 바꾸어 표시하지 않습니다. 완료 원장 Native0초는 optimize 반환 전이므로 정상입니다. 정확한 잔여 Native·objective·gap은 반환 시 원장/결과에서 확정해야 합니다.

원본 native.build는 OutputFlag=0을 설정합니다. 따라서 Gurobi 로그68바이트, 화면 마지막 NATIVE_BINDINGS 문구가 유지되는 현상은 단독 정지 근거가 아닙니다. 이번 측정에서는 CPU가97% 동작합니다. 실제 presolve/barrier/branch 내부 세부 단계는 현재 로그로 식별할 수 없습니다. 모니터는 읽기 전용으로 inflight와 시작시각을 우선 표시하고, Runtime 확정 전임을 표시할 수 있습니다.

비용 증거: 공통 준비13.350초, 실제 FullFlex 모델 build+첫 binding93.914초입니다. Full 모델은1,699,066행/600,284열/15,446,607비영, 물리 도메인1555개, migration block452,367개입니다. 이후 모델 certificate 저장부터 Native inflight 시작까지2.763초입니다. 이 후속 구간에는 두 번째 binding·resource snapshot·lock이 함께 들어 있으므로 binding 단독 시간으로 주장하지 않습니다. Root 보고 입력 재검증11.78초는 현재 Native 중 재벤치하지 않았습니다.

정적 확인: table_v_a는 native_binding을 계산하고, budget.solve는 같은 모델에 대해 다시 계산합니다. 각 arm의 load_context는 Basic와 FullFlex 공개 descriptor를 재구성하고 저장 파일과 byte 비교합니다. 같은 B3 context 안에서는 materialize_physical closure가 기존 physical/coefficients/template grid를 재사용하지만 arm/process 간 decoded context 캐시는 없습니다. CC4는 frozen Q50/Q90/kernel을 읽으며 fit/refit/scaling/clipping은0입니다. 물리 coefficient는 기존 당일 NPZ를 검증·로드하며 새 AC를 생성하지 않습니다.

후속 개선 후보는 현재 실행을 바꾸지 않는 범위로만 제시합니다. 읽기 전용 모니터의 Native 단계/경과 표시가 우선입니다. 이후 동일 Source·initial·science·case·CC4·physical byte SHA와 정확한 Matrix/Domain/Objective SHA를 유지하는 immutable descriptor/coefficient 캐시를 검토할 수 있습니다. 중복 binding 제거는 해시 이후 모델 변경이 없다는 별도 검증과 독립 admission guard가 필요하며, 절약 시간은 아직 측정하지 않았습니다. B1→B3 A1 재사용은 동일 행렬·도메인·목적과 원본 FULL replay를 통과한 경우에만 허용됩니다.

Source final9개 SHA는 모두 동일합니다. 대상 process 중단·속성변경·Source 수정·Native·Actual·새 모델 build 모두0입니다. probe 자체 CPU0.03125초, wall8.03초(대부분 대기), read 약163KiB였습니다. 타임아웃·Threads·알고리즘·domain은 변경하지 않았습니다. R2 작업은 수행하지 않았습니다.
