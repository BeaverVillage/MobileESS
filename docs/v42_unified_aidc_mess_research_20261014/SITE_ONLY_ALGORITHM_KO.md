> PR 기준: 실제 SMOKE02는 2시간/8슬롯, Known86 신규시작·실행 SHA 동일, Unknown0이다. 마지막 Source 회귀79 PASS 뒤 Supervisor가 기본 사이트의 queue reason 표시를 정리했으며 최종 통합 회귀는 UNIFIED_REGRESSION_RESULTS.json을 따른다. 새4시간/Full96/FreshAC는 중단으로 NOT_RUN이다.

# 현재 Dday Known 규칙과 Unknown 사이트 선택

활성 연구는 May01 IEEE123 B1의 C0 기본 사이트와 C1 signed sensitivity 사이트 선택이다. 새 Known MILP, Time-shift, Runtime Repair, Migration, 과거 Known 명령 Actual 실행은 HOLD다. 이전 60분 QoS 및 outer-box 자료는 비활성 확장 진단으로 보존한다.

`run_dday_known_site_only_canary(output, slots=8, shared_manifest=None)`는 원본 strict Source/Provider/receipt를 보존한다. 현재 관측 Running/Pending와 공개 Q50만으로 `DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL` 기준 Known 진단 baseline을 한 번 만든다. 원본 submit/UID 순서로 Known을 먼저 scan하고, 앞 작업이 막힌 경우 뒤의 합법 Known은 원본 B1과 같이 실행할 수 있다. Known 사이트는 source 현재 사이트 또는 공개 source reference 사이트로 고정하며, 정보가 없는 경우의 deterministic source-compatible fallback은 연구 모델 가정이다. 실제 서비스는 원본 private simulator가 실행하고 완료를 현재 관측으로 알린다. Q50 만료로 Running을 해제하지 않는다. 새 A1 최적성이나 Kestrel 실제 배치를 주장하지 않는다.

과거 PR223 Known A1의 선택 작업과 명령은 historical receipt에만 남긴다. 원본 P/Q 및 signed AUTO causal-prefix secant + LDC 계통 행은 numeric linearization anchor다. 현 Known baseline과 과거 anchor를 같은 Planning 계획으로 재라벨하지 않는다. strict source execution bindings와 최신 controller study bindings는 별도로 기록한다.

C0/C1은 동일한 Source actual runtime bank, 시작 상태, current Known rule, FCFS reference, forecast, strict Provider를 독립 복사한다. Unknown은 공개 reference/release/representation/hard window를 통과한 현재 15분 tick에서만 후보를 만들며 추가 의도 지연은 0이다. C0는 reference 사이트, C1은 `PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1` 공개 연구 권한으로 source-compatible 최대 12사이트를 비교한다. 이 권한은 원본 `can_prestart_place`나 QoS receipt를 변경하지 않는다.

모든 후보는 whole GPU gang/rack, Running 점유, firm Known/Unknown 예약 및 원본 현재 voltage/current/transformer 제한을 통과해야 한다. C1은 현재 모든 선로·상 행의 예상 최대 부하율을 최소화한다. 미래 계통/CC4 forecast는 사이트 선택에 사용하지 않고, CC4 익명 수요는 hard GPU가 아니다. Q50/Q90가 실제 runtime 상한이 아니므로 각 Unknown의 GPU 예약을 연구 horizon 끝까지 보수적으로 유지해 Known firm booking을 검사한다. 실제 완료 관측 이후 원래 control release로 해제하며, 여러 Unknown의 겹친 overrun도 함께 보호한다. 막힘 원인은 `UNKNOWN_UNBOUNDED_RUNTIME_KNOWN_FIRM_BOOKING` 및 UID/구간 conflict로 기록한다.

Known에도 원본 current grid guard를 적용한다. 두 variant의 Known UID/실행 사이트/실제 start/누적 compute/완료·release의 SHA가 다르면 `KNOWN_EXECUTION_FAIRNESS_FAIL`이며 비교 개선을 인증하지 않는다. 원인이 capacity/grid/QoS/원본 hard window인지 현재 GPU/PCC P/Q 및 event witness를 보존한다. Actual prefix max line loading은 source signed affine slot-average 진단이며, original11SVR Fresh AC와 Full96 인증은 Supervisor가 별도로 실행해야 한다.

검증: 최신 계약 아래 cheap fixture 77개 PASS (2.55초). 실제 event fixture에서 Unknown은 합법 reference +90분에 실행하고, Q50 900초보다 긴 실제 1800초 서비스를 보존했다. Known 실제 start/completion은 C0/C1 동일하며 실제 변경 사이트 compute는 0.5 GPUh였다. 두 Unknown의 Q50 종료 후 미래 Known 예약을 함께 침범하는 반례를 차단했다. 이 수치는 named fixture이며 실제 May01 결과가 아니다. Agent A는 새 Source factory/Actual/Native/AC를 실행하지 않았고, 실제 8-slot smoke는 Supervisor가 실행한다.