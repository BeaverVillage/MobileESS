# V41 운영 선택과 실행 중단 근거

요청에 따라 runtime은 Rolling Q90 Track-P L2, 미래 작업량은 H4 R85_B2, H24는 OFF로 명세를 고정했다. 이는 새로운 V41 운영 인터페이스 선택이며 S5R1/R6R1 FAIL 판정을 바꾸지 않는다. 아직 예측 생성이나 최적화 연결은 실행하지 않았다.

현재 B1/A0는 V40H producer가 V40G joint optimizer를 호출하고 A1은 V40H feedback을 사용한다. 주목적은 무차원 rho_max이며 하위 목적은 migration 수, 기준 스케줄 GPU-slot 대칭 편차, 동률 해소다. GPUh 서비스 부족 벌점 계수는 없다. 과거 V28R2 backlog도 벌점이 아니라 기준값과의 강제 등식이다.

따라서 사용자 지시문 17번의 “If NO semantically valid existing coefficient exists: STOP BEFORE MAY CAMPAIGN”을 적용했다. 새 계수, 0 계수, migration 계수, 임의 단위 변환을 대입하지 않았다. 기존 승인 계수의 파일·변수·값·단위 또는 별도의 명시적 과학적 목적함수 결정이 있어야 재개할 수 있다.

extreme raw reserve forecasts are saturated before optimization by causally historical and physically actionable capacity limits. 이는 예측 정확도 개선 주장이 아니며, raw와 actionable을 분리 저장하는 명세다.

V40M의 미해결 Actual 사례 72개는 과거 증거로 보존한다. V41 runtime 적용 후 같은 사례 수라고 단정하지 않는다. 실행 권한 부여 자체가 누락된 Actual 실행 위치 근거를 생성하지 않는다.
