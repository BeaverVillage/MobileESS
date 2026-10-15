# 캠페인 진행 JSON 오류 수정 및 B2 준비 병목 감사

## 사용자 최신 지시와 실행 순서

사용자는 B2 모델 준비 병목을 확인하고 B2를 중단한 뒤 B1부터 다시 실행하도록 지시했다. EXECUTION06 B2 M1은 모델·증명 생성 중 Native 0초, inflight 없음, active_stage_context 없음 상태에서 중단했다. B0 성공 결과, B1 실패 결과, B2 부분 Raw·로그와 실행 PID·Source를 보존했다. 중단 전후 PLANNING/K48 원장의 바이트 SHA는 동일하다. EXECUTION07은 새 Native 예산 주기가 아니라 EXECUTION06 원장을 이월하는 연속 실행이며, 순서는 B1 → B2 → B3다. May02–31 Heavy는 승인되지 않았다.

## B1 실패 원인과 수정 범위

EXECUTION06 B1 A1은 FULL 모델 생성 107.84초 후 `LIVE_PROGRESS.json.tmp`를 `LIVE_PROGRESS.json`으로 교체할 때 Windows WinError 5가 발생했다. Solver 호출 전이며 Native 소비는 0초다. 화면용 진행 기록 실패가 모델 생성을 중단시킨 통합 오류다.

`table_v_run.progress`만 전용 `write_progress`에 연결했다. 고유 임시 파일을 사용하고 공유 위반을 짧게 재시도한다. 계속 잠겨 있으면 마지막 완전한 JSON을 유지하며 별도 append-only 경고를 남기고 모델 생성을 계속한다. Raw·인증·예산 원장의 엄격한 `_write`는 변경하지 않았다. JSON 직렬화 오류는 프로그래밍 오류로 계속 드러낸다. 수학적 Source, Case, Policy, Matrix, DW/Pricing, FULL MILP 및 MESS 알고리즘은 변경하지 않았다.

실제 Windows에서 읽기 핸들을 열어 둔 채 교체 오류를 재현하고, 비치명 처리·기존 스냅샷 보존·핸들 해제 후 회복을 확인했다. 단순 FILE_SHARE_DELETE 설정만으로 이 환경의 `os.replace` 성공을 보장할 수 없다는 점도 확인했다. 운영 수정은 그 가정에 의존하지 않는다.

신규 9개 테스트와 기존 회귀를 합쳐 1,123 PASS, 실제 Native 0회, 과거 Native 원장 바이트 보존 PASS다.

## B2 준비 병목의 실제 근거

중단 전 PID 25748의 두 스택에서 각각 `v42_supercompact.presolve.Presolve.row_scan`과 `audit_pivots`의 `rowset` 호출을 확인했다. Solver나 RAM 부족으로 기다리는 상태가 아니었다. 중단 당시 RSS 약 4.35GB, private 약 4.50GB, 관측된 프로세스 Peak RSS 약 5.15GB다. 마지막 진행 기록은 전력망 814,560행 사전 검사 완료, 287,558행의 함의 증명을 표시한다. 이 기록 후에도 정확 Presolve가 계속되어 화면 기록의 나이와 실제 계산 시간이 달라질 수 있다.

동일 최종 수학 Source의 기존 실제 Native0 원본 모델은 1,130,336행 / 344,967열 / 16,432,980 NNZ다. 선택된 C3A·Dense Response 모델은 715,142행 / 354,332열 / 7,903,837 NNZ다. AIDC의 1,555 Job → 229 Class 압축은 B1/B3 A-stage용이며 B2 Reference M-stage의 이 준비 비용을 줄이지 않는다.

`MESS_NATIVE0/CURRENT_M/CURRENT_EXACT_C3A_PROOF.json`의 실측:

- C3A 생산·검증 Wall: 744.643초.
- 독립 verifier Wall: 441.990초.
- 독립 검증 대상 affine definition / tightened bounds: 각각 95,124개.
- 독립 exact fallback: 0회. interval 계산과 Fraction 기반 계수·증명 처리가 주요 후보다.
- 전체 Native0 감사 Wall 1,267.678초에는 이 준비뿐 아니라 두 Pool의 생성·Direct Joint 행렬 읽기 검증도 포함된다. 이 값을 순수 Production 모델 생성시간으로 보고하지 않는다.

현재 PR221 정적 캐시는 반복 Joint에 적용되지만, `TableVMessStages.prepare`가 먼저 호출하는 원본 M 모델·C2/C3A 준비는 현재 Case에서 새로 수행된다. `Presolve.run`은 행/열/NNZ가 수렴할 때까지 `fixed → row_scan → audit_pivots`를 반복하며, `audit_pivots`는 각 pivot/consumer 쌍에서 set union을 다시 만든다. 독립 C3A verifier는 95,124개 bound의 interval 표현을 다시 구성한다.

## 개선 가능성과 이번 적용 경계

1. 현재 Source·원본 Matrix·Domain·Objective·고정 AIDC·물리 계수·발행시각·Case의 정확한 바인딩을 검사한 후, 이전 검증된 전체 준비 결과와 증명을 재사용하는 공통 캐시가 가장 큰 후보다. B3 A2/M2의 변경된 입력에는 무조건 재사용하면 안 된다.
2. 동일 CSR 행·정확한 dyadic ratio·변수 지원 집합을 재사용하고 pivot의 consumer 비용 계산 중 같은 set union을 반복 생성하지 않게 할 수 있다. 행·계수·허용오차를 변경할 필요가 없다.
3. 독립 verifier 안에서만 동일 affine vector와 동일 도달 가능 영역의 interval 계산을 메모이즈할 수 있다. 생산자의 판정을 verifier에 복사해서는 안 되며, 기존 양방향 동치성과 모든 축의 독립 재검증이 필요하다.

위 M-stage 개선은 후보를 확인한 상태다. 전체 준비시간 감소량은 아직 실측하지 않았으며 성능 개선 완료로 보고하지 않는다. B1 재실행을 지연시키거나 동결 Source를 실행 중에 수정하지 않도록 이번 Release에는 화면 저장 오류 수정만 적용한다. M-stage 개선을 적용하려면 별도 안전 경계에서 원본 행렬과 증명·회귀를 검증한 Source로 동결해야 한다. 검증 생략, 허용오차 완화, 물리·QoS 제약 삭제는 하지 않는다.
