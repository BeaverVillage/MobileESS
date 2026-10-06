# PR134 supercompact May B1 통합 상태

Phase I 전수 압축·독립 verifier·원본 accepted witness 왕복 및 전체 행·4개 목적 검증 PASS. 운영 포트에서 fixed Actual/Fresh 96/96 수렴과 위반0을 확인했다. 이 테스트 계획은 production 날짜 재사용이나 old warm start가 아니다.

기존 32개 campaign checkpoint를 읽기 전용으로 감사했다. 완료 파일이 없는 경우 또는 정확 source/model/input/objective/validation 호환성을 입증하지 못한 경우는 재사용하지 않는다. 현재 증명된 전체 날짜 재사용은 0이다. 자세한 원인은 ALL_EXISTING_DATE_REUSE_CASES.json과 DATE_REUSE_AUDIT.csv에 있다.

31개 날짜의 원본 R0·현재 frozen Runtime/CC4/C0/C1·grid authority를 동결했다. scientific source는 PR134이며 PR150/151 입력 재구성은 사용하지 않는다. production은 별도의 Scheduler 소유 실행으로 시작한 뒤 실제 PID/생성시각/명령과 서비스 소유 계통을 검증한다. 아직 월 완료를 주장하지 않는다. 각 날짜의 실패·timeout은 기록하고 다음 날짜로 이동한다.
