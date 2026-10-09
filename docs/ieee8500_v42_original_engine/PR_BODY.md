IEEE123 2025년 5월 B2/B3 캠페인을 보호하기 위해 모든 IEEE8500 실제 실행을 `HOLD_WAITING_FOR_USER_APPROVAL`로 차단합니다. 캠페인 완료 후에도 별도 사용자 실행 승인이 필요하며 자동 재개는 없습니다. 실제 IEEE8500 프로세스는 점검 시 발견되지 않았고, IEEE123 프로세스 종료·수정은 0회입니다.

별도 worktree에서 PR #198 V19 및 의존 소스와 PR #191 B3/V6 소스를 복사하고 Authority를 기록했습니다. 원본 모델·Pricing/RMP·독립 검증기의 차량 차원과 96/97슬롯 입출력을 매개변수화하고, 원본 함수 호출 경로 및 전체 IEEE8500 Grid Adapter 메타데이터 계약을 준비했습니다. NativeBudget/Gap/min rho_max 정책은 바꾸지 않았습니다. PR #199 물리 구성·Job·P5·DSS·B0 결과는 보존합니다.

Validation: stdlib/AST/shape-only Mock 고유 18개 PASS. 4대 입력/DTO/계획 저장 형식은 원본 Mock과 동일하며, 6대 형상과 기존 차량 열 보존을 확인했습니다. Gurobi/OpenDSS/scientific import, 실제 모델 생성, AC, Native optimize, 초기해 벤치마크, Worker/Coordinator 시작은 모두 0회입니다. 복사한 원본 V19 benchmark의 기존 trailing whitespace 1곳은 Source bytes 보존을 위해 유지했습니다.

이 PR은 실행 가능성이나 성능 인증이 아닙니다. 전체 계수 생성, thermal Authority/A/M Builder 통합, 전체 의존성 closure/SourceRegistry SHA 갱신, 실제 4대 행렬 동일성 및 6대 FULL/Compact/C3A 인증은 미완료 또는 실행 보류입니다. 보류를 해제하지 않고 이식 준비만 검토하는 Draft입니다.
