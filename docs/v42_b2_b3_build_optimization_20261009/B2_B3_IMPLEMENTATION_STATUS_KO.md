# B2/B3 모델 생성 개선

V6 효율적 Option/Resource/GPU interval/R1 projection/checkpoint 및 검증된 동일 날짜 input/domain cache를 B3 A1/A2에 연결했습니다. A2의 새 MESS P/Q Grid/FULL/RHS는 다시 생성하며 원본 source globals를 복원합니다.

B2와 B3 M 단계는 원본 PCS 함수의 동일 bytecode/식과 exact float.hex 계수를 유지하면서 빌드 안의 반복 cos/sin 평가를 줄입니다. 원본 FULL/Compact/C3A는 매번 생성합니다. Route input cache는 반복 동일 입력에만 이득이 있으며 첫 build 속도 개선의 근거로 사용하지 않습니다. 추가 sparse assembly 변경은 중복·동치성이 확인되기 전 적용하지 않았습니다.

B2 PR192의 별도 개발 코드와 테스트17개 PASS를 담당 캠페인 대화에 전달했습니다. 최신 사용자 지시대로 해당 대화가 현재 소스와 V7 정식 전환을 담당하며 실행 중 V6 Worker를 교체하지 않습니다. 별도 branch만 남기는 것을 캠페인 반영 완료로 주장하지 않습니다.

단계별 일곱 구성 phase와 scope SHA의 비교 인터페이스를 구현했습니다. 실제 May01/May23 전체 모델 동치성·비교 성능·RSS는 NOT_RUN이고, B1 성능 수치를 B2/B3로 자동 이전하지 않습니다. 실제 Native/FULL/OpenDSS는 0회이며 B3 Production은 미승인입니다.
