# B2 가속 생성기의 원본 소스 권한 연결 V13

B1 May01~31 전체 31/31 PASS를 보존하고 B2를 이어 실행한다. V10의 시작 실패는 원본 Grid 계수 SimpleNamespace를 해시하지 못한 오류였다. V11은 모든 namespace 필드를 해시하고 하위 오류를 보존했다. V12는 FULL 게이트 PASS 이후 실행 중인 B2 워커를 잘못 차단하던 조건을 수정했고 모든 기존 산출물 SHA를 병렬로 재확인했다.

실제 V12 May01 BASELINE은 Native=0 FULL 생성, 원본 transport 검증 및 전체 과학 fingerprint를 통과했다. 총 준비 시간은 367.249237초였다. OPTIMIZED 실행은 생성 시작 전 원본 m_model.py SHA 조회에서 실패했다. 기존 Gateway는 과학 소스 목록만 조회했지만 해당 생성기는 불변 CAMPAIGN_MANIFEST의 implementation.sources에 보관돼 있었다.

V13은 가속 생성기를 별도 소스 버전으로 보존한다. 원본 캠페인의 과학 소스와 구현 소스를 충돌 없이 합친 builder_original_sources를 새 manifest에 봉인하고, 이전의 전체 소스 체인 검증과 실제 파일 SHA 검사를 모두 유지한다. Gateway는 이 봉인된 권한에서 m_model.py, m1.py, mess.py를 조회한다. 세 실제 모듈의 SHA 조회, import 경로 일치 및 변경된 SHA 거부를 실행해 확인했다. 경량 회귀는 256개 PASS다.

통과한 May01 원본 FULL 결과는 입력 SHA, 원본 전체 소스 권한, Native/P2=0, 원본 transport PASS, 두 fingerprint 함수의 정확 AST 동일성을 확인해 비교 기준으로 봉인한다. 결과 파일은 수정하지 않는다. 이 참조는 모델 생성 동치성 비교에만 사용하며 점·bound·시간을 운영 최적화로 전달하지 않는다. May01 OPTIMIZED와 May23 BASELINE/OPTIMIZED를 새 버전에서 실제 생성한다. 비교 시간은 통제된 성능 benchmark가 아니며 과학 내용과 행렬/domain의 정확 동일성을 우선한다.

B2는 worker별 불변 입력, 원본 PCS 계산 재사용 및 중복 Gurobi 모델 복사 제거를 적용한다. 원본 graph/FULL/Compact/C3A 및 원본 verifier를 그대로 사용한다. B1의 AIDC Job/Graph 전용 가속은 B2 고정 AIDC 경로의 실행 대상이 아니다. 실제 운영 모델은 각 날짜·worker에서 새로 생성한다.

운영 정책은 B2 3워커, Threads=1, P2=0, 날짜별 Native 누적 5400초, 인증 Gap 3%다. Windows Scheduler가 Coordinator/Monitor/Watchdog를 소유하며 localhost:8793은 현재 버전과 B2 3슬롯을 보고한다. 실제 FULL 비교 및 각 운영 worker의 가속 생성 receipt와 Native 진입은 별도 증거 파일로 기록한다.
