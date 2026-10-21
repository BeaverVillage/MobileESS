# V2_add — P5 및 Planning/Actual 의미 감사

P5는 B0 실행 전에 `PHYSICAL_CONFIGURATION_FREEZE.json`으로 고정했다. Source1.04pu, 원본 RegControl12개 Vreg123.5V, CAPBank3 초기OFF, 원본 CapControl9개 및 나머지 원본 제어 속성을 사용한다. Scale별 재조정은 없다. 각 Case receipt는 동일한 설정 SHA를 기록한다.

이번 실행은 PR197/199의 static automatic settling 계약이다. 매15분 입력을 주입하고 native Tap/Cap을 수렴시킨 뒤 상태를 다음 슬롯에 전달한다. Planning과 Actual은 독립 초기 상태에서 시작하며 Actual은 앞24슬롯부터 실행한다. Fresh는 새로운 context로 같은 전체 순서를 재생한다. Tap/Cap 궤적의 동일성을 따로 비교했다.

OpenDSS clock은 각 시퀀스의 상대15분 인덱스다. 실제 전력·날씨 입력은 원본 AEST 시간축에 묶여 있으며 Actual0은 D-1 18:00, Actual24/Planning0은 May01 00:00이다. 원본9 CapControl은 모두 `type=kvar`와 voltage override이며 시각 기반 on/off 스케줄이 아니다. 부하/연구 PV 시간값은 외부 동결 배열로 직접 지정한다. 이 상대 clock을 실제 현장 TIME 제어의 인과적 지연 시뮬레이션으로 해석하지 않는다.

V44 IEEE123의 Planning7/Actual43·SVR12·TIME 자동제어를 복사하지 않았다. 특히 원래 지연/히스테리시스의 초 단위 실제 동작과 통신/작동 지연 인증은 이 static 분석의 범위가 아니다. 물리 설정 차이를 숨기지 않으며, 실제 TIME 계약을 IEEE8500 최종 알고리즘 검증에 연결하는 것은 G4 잔여 작업이다. G4 미완료는 이 독립 P5 B0 연구의 G2 실행을 차단하지 않는다.

기존 IEEE123/V44 결과와의 숫자 차이는 계통·설치 하드웨어·전압제어 계약 차이도 포함한다. 이번 B0/Pilot 비교 내부에서는 같은 P5와 원본 정격을 사용했다.
