# B2 가속 생성기의 원본 소스 권한 연결 V13

B1 May01~31 전체 31/31 PASS를 보존하고 B2를 이어 실행한다. V10의 시작 실패는 원본 Grid 계수 SimpleNamespace를 해시하지 못한 오류였다. V11은 모든 namespace 필드를 해시하고 하위 오류를 보존했다. V12는 FULL 게이트 PASS 이후 실행 중인 B2 워커를 잘못 차단하던 조건을 수정했고 모든 기존 산출물 SHA를 병렬로 재확인했다.

실제 V12 May01 BASELINE은 Native=0 FULL 생성, 원본 transport 검증 및 전체 과학 fingerprint를 통과했다. 총 준비 시간은 367.249237초였다. OPTIMIZED 실행은 생성 시작 전 원본 m_model.py SHA 조회에서 실패했다. 기존 Gateway는 과학 소스 목록만 조회했지만 해당 생성기는 불변 CAMPAIGN_MANIFEST의 implementation.sources에 보관돼 있었다.

V13은 가속 생성기를 별도 소스 버전으로 보존한다. 원본 캠페인의 과학 소스와 구현 소스를 충돌 없이 합친 builder_original_sources를 새 manifest에 봉인하고, 이전의 전체 소스 체인 검증과 실제 파일 SHA 검사를 모두 유지한다. Gateway는 이 봉인된 권한에서 m_model.py, m1.py, mess.py를 조회한다. 세 실제 모듈의 SHA 조회, import 경로 일치 및 변경된 SHA 거부를 실행해 확인했다. 경량 회귀는 256개 PASS다.

통과한 May01 원본 FULL 결과는 입력 SHA, 원본 전체 소스 권한, Native/P2=0, 원본 transport PASS, 두 fingerprint 함수의 정확 AST 동일성을 확인해 비교 기준으로 봉인한다. 결과 파일은 수정하지 않는다. 이 참조는 모델 생성 동치성 비교에만 사용하며 점·bound·시간을 운영 최적화로 전달하지 않는다. May01 OPTIMIZED와 May23 BASELINE/OPTIMIZED를 새 버전에서 실제 생성한다. 비교 시간은 통제된 성능 benchmark가 아니며 과학 내용과 행렬/domain의 정확 동일성을 우선한다.

B2는 worker별 불변 입력, 원본 PCS 계산 재사용 및 중복 Gurobi 모델 복사 제거를 적용한다. 원본 graph/FULL/Compact/C3A 및 원본 verifier를 그대로 사용한다. B1의 AIDC Job/Graph 전용 가속은 B2 고정 AIDC 경로의 실행 대상이 아니다. 실제 운영 모델은 각 날짜·worker에서 새로 생성한다.

운영 정책은 B2 3워커, Threads=1, P2=0, 날짜별 Native 누적 5400초, 인증 Gap 3%다. Windows Scheduler가 Coordinator/Monitor/Watchdog를 소유하며 localhost:8793은 현재 버전과 B2 3슬롯을 보고한다. 실제 FULL 비교 및 각 운영 worker의 가속 생성 receipt와 Native 진입은 별도 증거 파일로 기록한다.

실제 FULL 비교 4건은 모두 PASS다. May01 및 May23의 원본/가속 fingerprint가 정확히 동일하다. 관측 준비 시간은 May01 367.249237→363.204403초, May23 305.911398→164.958962초이며, 통제된 benchmark가 아니므로 일정한 가속률을 주장하지 않는다. PRODUCTION_B2_START_PROOF.json은 B1 31개 PASS 행의 완전 보존, 원본 결과 SHA, 각 운영 worker의 실제 가속 생성 receipt, AST 복사 제거 증명, 원본 FULL/Compact/C3A 검증 및 Native 진입을 확인한다. B2 May01/02/03 PID 29088/97556/82468은 Coordinator 92644의 실제 자식이다. 월 전체 B2 종료 결과는 이 시작 증명의 범위가 아니다.

현재 모니터는 읽기 전용 v42_b2_monitor_v15이며 동일한 localhost:8793 및 기존 소유 Monitor Scheduler 작업을 사용한다. 상단 캠페인 요약, 나란히 표시하는 3개 worker의 날짜/단계/독립 인증 Gap/Native 시간/Heartbeat, 날짜별 B1·B2 Actual 최대선로 부하율 비교표로 구성한다. 사용자의 후속 지시에 따라 FULL 모델 검증 안내, 비교표, fingerprint JSON은 화면에서 제거했다. 검증 원본은 캠페인 기록에 남는다. MONITOR_V15_ACTIVATION.json은 교체 전후 Coordinator와 3개 Native worker의 동일 프로세스 및 생존을 확인하고 Native worker kill=0을 기록한다.

Actual 지표는 봉인된 RESULT/FRESH_RESULT/OPENDSS_PHASE_ARRAYS SHA를 확인한 뒤, 실제 96개 AC 슬롯의 phase_current_loading_pu[:, branch_kinds == 'line'] 최대값을 사용한다. 원본 Fresh AC 요약의 rho_max_AC와 수치 일치 및 96/96 수렴을 확인하고 변압기를 제외한다. 저장된 입력/물리 정책의 NormalAmps 기준을 바꾸거나 OpenDSS를 새로 실행하지 않는다. B1 31일 전부 실제 배열과 일치한다. B2 평가 전 또는 96슬롯 수렴 미확인 값은 0 대신 —로 표시하며, 차이는 B2−B1의 퍼센트포인트다. 배포 시점의 비교 결과는 ACTUAL_COMPARISON_V15.json에 보관한다.

Native 시간은 완료 호출 ledger와 실행 중인 호출을 포함한 Solver callback 보고를 구분한다. callback의 완료 누적 Runtime이 ledger와 동일할 때만 현재 호출을 포함한 보고값을 보여준다. Wall 경과를 Native 시간으로 추정하거나 solver MIPGap/BestBd를 독립 Global 인증으로 승격하지 않는다.

검증: V13 경량 회귀 256 PASS, V15 지표 검증 7 PASS, 실제 31일 비교 배열 확인 PASS, 오프라인 DOM 검증 PASS(3worker/31행/미평가 —/%p/열린 세부사항 유지/연결 지연/시작 대기/불필요한 검증 패널 제거), 실제 HTTP HTML/API 일치 PASS. 최초 읽기 약 1.5초, 동일 프로세스 후속 API 계산 약 0.13초였다. 브라우저 도구의 저장 권한 확인 기능 오류로 직접 렌더링 화면 검사는 차단됐다. 브라우저 보안 경로를 우회하지 않았으며, DOM 검증을 실제 브라우저 시각 검사로 주장하지 않는다.
