V43 Corrective Actual 및 Current AC 개선 준비 — 실제 실행 인증 전

기존 Golden003, Strict B1 C0/C1, 실행 중인 B0 Attempt002의 Source와 Raw는 변경하지 않았다. 별도 v43_corrective namespace만 추가했다. May01 네 Arm 및 두 R1 정책이 최종 범위이며 May02~31은 금지다.

확인한 결함과 수정 범위:

- 미래 Known의 last_pending_start_seconds가 모든 Unknown의 전역 시작 하한이 되는 결함을 제거했다. FIFO 처리 순서와 사이트별 미래 Known 예약은 유지한다. 독립 Native0 Reference 비교에서 849 UID 모두 기존보다 이른 Reference 시작을 얻었다. 실제 START/Compute 효과는 아직 인증하지 않았다.
- Known이 시작할 때 자기 자신의 동결 예약을 중복 점유로 세는 결함을 별도 CorrectiveReservations에서 수정했다. 같은 UID만 제외하고 다른 UID의 예약과 GPU 용량은 유지한다. 실패한 회귀 XML도 보존했다.
- Unknown Pending은 매 관측 상태/15분 경계에서 재평가한다. 관측된 RUNNING의 공개 경과 compute와 Q50만으로 Overrun을 기록한다. 미래 Runtime/Completion, 새 RUNNING Migration, Known Pre-site, 의도적 Actual Time-shifting은 허용하지 않는다.
- R1은 고정 Seed와 도착 시 UID 해시로 선택한다. 전체 UID 목록을 미리 읽어 30%를 맞추지 않는다. Source 동의와 데이터 준비는 R1_ASSUMED이며 SOURCE_VERIFIED가 아니다.

입력 번들에는 Unknown의 QoS/Partition/요청 Walltime/보호 분류가 빠져 있었다. 원본 archive에서 id, submit_time, gpus_requested, qos, partition, wallclock_req만 선택해 동일 source_member/source_row/UID/Submit/GPU를 대조했다. 849개는 normal753/standby92/high4이다. 기존 V42 May01의 normal/standby 이외 보호 분류를 재사용하며 기록된 요청 버전의 역사적 검증을 주장하지 않는다. Known 속성과 Q50 예측은 변경하지 않는다. R1 참여자 선택은 이 입력 준비 단계에서 수행하지 않았다.

기존 Strict C0의 전압 거부 3,485회는 577개 고유 Unknown UID에 해당한다. 최초 정책 차단으로 CAUSAL_REFERENCE_NOT_READY를 기록한 UID는 693개다. GPU retained 거부는 3 UID, NO_CAPACITY 거부는 4 UID다. 상세 UID 표와 Reference 앞당김은 별도 CSV/JSON으로 보존했다. Signed와 독립 AC의 실제 상·전압 대조는 B0 공식 종료 후 공유 lock을 확보해 수행한다. 증거/원인 검토 전 affine hard gate는 기본적으로 유지한다.

PR189의 빠른 B0는 가벼운 사건 큐와 한 엔진에서의 순차 96슬롯 AC를 사용한다. 설치된 NewContext는 새 context 생성이고 Circuit JSON은 객체/기본 회로 속성의 직렬화다. 완전한 제어 큐·solver 상태 복제의 동등성은 아직 인증되지 않았다.

따라서 우선 보수적 Cached Prefix 구현을 준비했다. 후보마다 과거 SolveSnap 순서는 그대로 실행하지만, Source/C1/MESS/관측 Prefix가 정확히 같은 이미 검증된 과거 슬롯은 중복 분기 측정·Inventory 검사를 생략한다. 과거 탭/Cap 상태와 수렴을 대조하며 현재 후보는 항상 전체 물리 측정·Inventory 검사를 받는다. Fresh는 별도의 원본 전체 순차 측정 경로를 사용한다. 반복된 전체 Prefix JSON 복사 대신 단일 Prefix 인증과 후보 receipt를 저장한다.

Native0 fixture 및 기존 경계 회귀 55개가 PASS했다. 이는 실제 DSS 동등성 또는 새 Actual96/Fresh96 인증이 아니다. 실제 관측 Prefix의 원본/개선본 shadow 대조, 짝지은 짧은 이벤트 Canary의 UID·사이트·시각·GPU 대조, 실제 시간·호출 수 비교를 통과해야 production FAST 경로를 허용한다. 전체 Actual을 기존 느린 FULL_PREFIX/SHADOW 모드로 새 실행하는 경로는 차단했다.

현재 검증 상태: 실제 Prefix 동등성 NOT_RUN, 새 R1 실제 Canary NOT_RUN, 새 R1 Actual96/Fresh96 NOT_RUN, M1/A2/M2 NOT_RUN. B0 Attempt002는 자연 완료까지 유지하고 정산 후 실제 동등성 검증과 병목 개선, 이어 B2/B3 M-stage를 진행한다. 성능 개선이나 Unknown 서비스 회복을 아직 수치로 주장하지 않는다.
