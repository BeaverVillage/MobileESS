Known과 CC4는 과거 같은 A1 결과의 96×12 행렬로 함께 고려되었다. Q50 Nominal은 미도착 수요의 예상 점유이며 실제 Job 예약이 아니다. 저장된 과거 A1의 Achieved CC4/Runtime Reserve는 모두 0 GPU-slot이고, 부족량은 각각 75,649 및 17,330 GPU-slot이다. 이를 확보된 여유로 해석하지 않았다.

새 CurrentEvent 제어기는 Unknown 입장 시 현재 Running/Committed GPU와 모든 선로/상 signed loading을 사용한다. 미래 Known 예약과 불확실한 Runtime의 잠재적 겹침만으로 입장을 차단하지 않는다. 실제 시작 이벤트의 GPU 충돌에서만 PENDING Known을 다른 사이트로 평가한다. 원래 Planning 명령은 보존하고 Actual corrective 명령을 따로 저장한다. 원본 권한과 데이터 준비 증거가 없으면 Queue한다. 전송은 원본 bytes/s WAN 단위와 15분 전송 계약을 사용하고, 준비가 끝난 뒤 현재 GPU 및 계통을 다시 검사한다.

명명 Native0 Fixture에서 Unknown 실행, 실제 Known 충돌과 corrective pre-placement, 대체 사이트/데이터 권한/WAN 부족 시 Queue, Running 보호, QoS 준비 예산, Forecast 1회 차감과 실제 GPU 분리, Runtime overrun, 실제 Completion 즉시 GPU 해제 및 다음 합법적 15분 이벤트 backfill을 검증했다. Backfill은 선택한 각 후보 사이트의 미래 확정 예약을 검사하며 검증된 비선점 Runtime 상한이 없으면 안전 대기한다. 조건부 잔여 Runtime은 NOT_CERTIFIED로 남기고 미래 실제 완료시각을 읽지 않는다.

Fixture는 실제 C1 재계산 클래스와 OriginalGridPacket의 같은 평가 경로를 사용하지만 수치계수는 명명 합성 Fixture이다. 실제 May01 개선 또는 Fresh AC PASS를 의미하지 않는다. C0/C1/C2 Fixture 최대 선로부하율은 비교 CSV에 있고 실제 May01 값은 NOT_RUN이다.

AIDC_ORIGINAL_COEFFICIENT_FIXTURE.json은 별도의 Native0 수치 계약 검증이다. 원본 IEEE123 11-SVR 계수, C1 모델, 12 AIDC/780 GPU 및 원본 D-day 관측 점유를 사용해 현재 합성 1-GPU 제출의 모든 사이트 후보와 선로/상/변압기 행을 검사했다. 후보가 전압·전류·GPU 제약에 실패하면 그대로 거부한다. 이는 실제 Unknown 입장이나 같은 Case Planning–Actual 실행 인증은 아니다.

기존 Source18R_V5 A1은 FULL-feasible Planning 증거가 있으나, 같은 원본 D-day 아티팩트가 존재해도 Apr30→D-day prefix 실행이 검증되지 않았고 과거 명령과 관측 Running/사이트/시작이 불일치한다. 따라서 역사적 Actual handoff 역시 NOT_CERTIFIED다. 최신 E60 A1 시도 1–3은 SAME_CASE_A1_NOT_CERTIFIED다. 진단 FCFS를 Planning으로 승격하거나 명령을 현재로 이동하지 않았다.

60분은 참여 Batch 연구 정책이며 고객 SLA가 아니다. 본 기본 제어의 의도적 Time-shifting과 Checkpoint Migration은 NOT_RUN/HOLD이다. 새로운 A1 Heavy solve는 하지 않았다. May01 실제 Canary, Full96, 11-SVR Fresh AC, A1–M1–A2–M2 실제 통합은 같은 Case와 검증된 초기 상태의 handoff가 복구될 때까지 인증할 수 없다.
