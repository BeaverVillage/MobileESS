# Source Epoch 2와 기존 Canary 보존

첫 Source Epoch의 May01/May02 B2 Canary는 원본 FULL Planning 가능해를 반환했지만 Actual 전압 위반으로 실패했다. May01은 19건, May02는 104건이다. Fresh 96슬롯 모두 수렴했으며 결과·Native Ledger·Raw Phase 배열·RegControl 기록을 기존 경로에 보존한다. 실패한 결과를 공식 비교값이나 새 Epoch의 성공으로 재분류하지 않는다.

원본 FULL 검증을 통과한 점의 변경하지 않은 연속 P/Q 좌표에 아주 작은 부동소수점 Bounds 잔차가 있었다. 기존 route_witness는 새 경로 구성과 무관한 모든 연속 좌표에 정확 Bounds 검사를 적용해 실제 경로가 열린 Neighborhood를 닫혔다고 잘못 판단했다. Epoch 2는 route_witness가 변경한 원본 경로 좌표만 검사한다. 원본 FULL 검증, 물리 허용 오차, Literal Integrality, P/Q·SOC 값은 그대로다. 반올림이나 클리핑을 추가하지 않았다.

Native 최적화 호출이 독립 Receipt 대신 None을 반환하는 기존 DateBudget 경로에서는 정확히 하나의 새 완료 Ledger 행만 사용한다. Component·Stage·Label·TimeLimit·실측 Runtime 증가량이 맞지 않거나 미완료 호출이 있으면 사용하지 않는다. 이전 Epoch 비용과 실패 기록은 새 Manifest의 prior_attempts에 원본 SHA Receipt로 연결한다. 기존 실행이 살아 있거나 Runtime을 확인할 수 없는 중단이 있으면 새 Epoch 배포를 차단한다.

보고서는 바깥 공통 Source SHA와 B3 내부 과학 Source SHA를 구분하고 원본 Raw Receipt를 검증한다. 실패한 Actual 선로부하율은 진단값으로 남기며 공식 B1 대비 비교에서는 제외한다. 이전 시도 비용과 현 Epoch 비용을 별도로 집계한다. 새 Fresh 결과에는 Raw Phase 배열 SHA Receipt를 추가한다.

May01 전압·7개 공통 RegControl·P/Q Factorial 감사를 완료할 때까지 공식 전체 캠페인 배포를 차단한다. 감사 파일 SHA와 본문 판정, 보존한 May01 결과 SHA 및 Source SHA를 함께 검증한다. 상태 Wrapper만 PASS로 바꿔 결함 판정을 덮을 수 없다. Canary 전용 실행은 별도의 선택 날짜·Arm을 재실행하며 공식 Campaign Manifest를 발행하지 않는다. 따라서 다른 날짜의 Canary를 진행하면서 감사에 따른 배포 보류를 유지할 수 있다.

통합 회귀 검사 304개가 통과했고 최종 감사 Admission 보강 후 관련 검사 7개가 다시 통과했다. 두 Arm의 실제 물리 Canary와 31일 완료 여부는 이 구현 Gate와 별개로 기록한다. 기존 탭 설정, 커패시터 상태, 전압 범위와 물리 모델은 변경하지 않았다.
