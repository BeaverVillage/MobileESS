# IEEE8500 V42 원본 엔진 이식 준비 — 실행 보류

현재 모든 IEEE8500 실제 실행 상태는 **HOLD_WAITING_FOR_USER_APPROVAL**이다. IEEE123 2025년 5월 B2/B3 캠페인의 완료만으로 해제되지 않는다. 이후 사용자의 별도 실행 승인이 필요하며, 자동 재개·Worker·Coordinator·예약 작업을 만들지 않았다.

이 작업은 별도 `codex/ieee8500-v42-original-engine` worktree에서만 수정했다. 기존 IEEE123 캠페인의 worktree, 입력, 로그, 프로세스, 스케줄러는 수정하거나 중단하지 않았다. 프로세스 점검 시 확인된 Python 프로세스는 IEEE123 관련 7개였고, IEEE8500 실행 프로세스는 발견되지 않았다. 종료 요청을 보낸 프로세스는 0개다. 이 기록은 관측 시점의 명령행 점검이며 캠페인 전체의 완료 판정은 아니다.

| 항목 | 현재 상태 | 증거와 한계 |
|---|---|---|
| PR #199 C2 물리 구성 및 B0 | REUSED | 원본 파일과 SHA 보존. Planning rho=0.810230773, Actual rho=0.848320702. 재계산하지 않음 |
| PR #198 V19와 필요한 이전 seed 모듈 | COMPLETED_SOURCE_COPY | 지정 head의 코드만 복사. import/초기해 실행 없음 |
| PR #191 B3/V6 연결 코드 | COMPLETED_SOURCE_COPY | 지정 head의 코드 복사. B3 자체 기존 실행 차단 유지 |
| 원본 알고리즘 호출 경로 | STATIC_PREPARED | 원본 모듈·함수 이름과 AST 위치 확인. 실제 호출 0회 |
| MESS 4→6 입력/DTO/결과 배열 | PREPARED_MOCK_CHECKED | 원본 4대 Mock 입력·DTO·계획 저장 결과 동일. 6대 형상/기존 4대 열 보존 확인 |
| Pricing/RMP/독립 LB 차량 차원 | PREPARED_STATIC_ONLY | 차량 블록/convexity 행/dual 차원/두 시각 count-cover 차원 일반화. 실제 행렬/하한 인증 미실행 |
| Grid Adapter | PARTIAL_IMPLEMENTATION | 전체 원본 설비 및 신규 STA/PCS 축, 96슬롯 입력/정책/anchor SHA 계약. 실제 전체 계수 생성·thermal authority scope·A/M builder 통합 미완료 |
| 실제 4대 Matrix/RHS/Bounds/정수영역/목적함수 동일성 | HOLD_WAITING_FOR_USER_APPROVAL | Mock 동일성을 실제 수학적 동일성으로 주장하지 않음 |
| 6대 FULL→Compact→C3A 인증 | HOLD_WAITING_FOR_USER_APPROVAL | 모델 생성 및 인증 미실행 |
| IEEE8500 B0/B1/B2/B3·AC·Native·초기해·Worker | HOLD_WAITING_FOR_USER_APPROVAL | 이번 보류 작업에서 실제 호출/시작 0회 |

`ieee8500_v42_original.hold`는 환경변수, 가변 플래그, 승인 파일, 시간 경과로 열리지 않는 차단이다. 새 호출 경로, 전체 계수 공급, 현재 B0/고부하 AC 생성자 및 직접 MV DSS 진단 진입점은 차단을 먼저 확인한다. IEEE123 실행 진입점에는 이 IEEE8500 차단을 연결하지 않았다. 과거 데이터 안에 보존된 실행 스크립트를 새로 실행하지 않았다.

원본 소스 Authority는 PR198 `b34feffdcf11e076378f63e2aab05d9ea2f2014b`, PR191 `40b6f94dcd80e470f93c73b7479fdd2d9d91c3f2`, PR189 `625bbcb8b9a54a00c1660c26d96f7737c2f75457`, PR199 `23c3643681e38c8b3cf16f2d02686a78c4570cc7`로 기록했다. 원본 Git blob SHA256와 준비 worktree 파일 SHA256를 분리했다. 변경한 원본 인터페이스 파일은 후속 회귀 검증 대상이며, 기존 인증 SHA를 그대로 유효하다고 주장하지 않는다. 전체 의존성 closure와 원본 SourceRegistry의 새 준비 코드 SHA 연결은 미완료다.

변경한 차량 차원은 입력 loader, A-stage의 zero-MESS 출력 형상, M-stage 96/97슬롯 직렬화, B3 Authority/MESSDecision, 물리 replay 입력 형상, block 분해/RMP convexity/dual, 두 시각 count-cover다. `A1–M1–A2–M2`의 네 단계, CC4 시간당 네 슬롯, 원본 네 capacitor 검증, 과거 4대 fixture는 차량 수 일반화와 구분한다. Adaptive의 탐색 휴리스틱 상수, NativeBudget, Gap, PCS16, 원본 경로·SOC·P/Q 식과 목적함수는 바꾸지 않았다.

Grid Adapter는 원본 제어 ID `IDC01…IDC12`, `STA01…STA12`를 유지한다. 기존 1,783개 후보의 87축 민감도를 전체 IEEE8500 제약 계수로 대체하지 않는다. 계수 공급에는 전체 node/branch 축, 원본 3,703개 선로와 1,190개 변압기의 활성·비활성 구분, 별도 12개 STA 변압기, 36개 PCS 상별 전류 축과 입력/정책/anchor SHA를 요구한다. PCS current 축은 line rho 목적에 포함하지 않는 별도 transformer형 제약 축으로 정의했으며 실제 native thermal authority 통합은 검증 전이다. Metadata Mock 통과는 물리적 적격성이나 AC 통과가 아니다.

PR #199의 Job·배경부하·GPU·입지·교통·설비·P5·원본 DSS와 결과는 수정하지 않았다. PR #199의 zero-action/고정 MESS snapshot은 B0 비교 기록으로 보존하며, 새 A-stage에서 AIDC 유연성을 0으로 고정하는 제약으로 이식하지 않았다. 원본 Job와 QoS/C1/Reference의 source contract 연결, 일부 역사적 verifier의 고정 Job 수/IEEE123 authority, 24개 서비스 중 AIDC의 MESS 포트 권한은 후속 정적 통합 검토 사항이다.

경량 검증은 표준 라이브러리와 AST로만 수행했다. 18개 고유 테스트 PASS, Gurobi/OpenDSS/NumPy/SciPy import 0. 전체 17개 검사 후 추가한 kVA 누락 검사는 영향받은 metadata suite 6개만 실행했다. 실제 원본 모델이나 행렬을 만들지 않았고, 기존 수백 개 회귀 테스트를 실행하지 않았다. 테스트 fixture를 연구 Workload나 AC 결과로 사용하지 않는다.

별도 실행 승인 전에는 B1/B2/B3 성능, 이동경로, rebound, 비영 AIDC 유연전력, 독립 UB/LB 또는 Global Gap을 새 결과로 보고할 수 없다. 계통 통합 완료나 Production 준비 완료도 선언하지 않는다.
