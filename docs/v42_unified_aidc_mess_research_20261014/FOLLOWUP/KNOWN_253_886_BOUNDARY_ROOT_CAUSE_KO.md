# PR223 원본 Known 253/886 경계 원인 재조사

승인 초기 상태를 원본 `load_dday_state`로 검증하여 재사용했다. semantic SHA와 파일 byte SHA는 서로 다른 검증 대상이며 같을 필요가 없다.

RUNNING 324 / 472GPU, PENDING 1300를 보존했다. PR129 20건, PR125 153건/156GPU, 제외 44건을 변경하지 않았다.
완료 이력 178건 전체를 보존했다. A1 비영(非零) Q50 명령 밖의 Known RUNNING 48건/163GPU도 물리 점유로 유지한다.

253건은 단일 시작 시각 불일치로 해석할 수 없다. issue RUNNING 103건/133GPU의 start=0은 남은 서비스 연속 실행이다. 실제 과거 episode start, source elapsed, Dday elapsed, site, GPU, Q50, segment를 원본 파일에서 재검증하여 typed certificate를 만들었다. 이 103건의 관측된 6시간 연속 GPU 서비스는 798GPUh이며 Pending prefix가 실행되었다는 증거로 사용하지 않는다.

나머지 150건/150GPU는 issue PENDING이었으나 승인 Dday에서는 RUNNING이다. source 관측 시작은 최적 시작보다 108건 먼저, 42건 늦다. site는 40건 일치, 110건 다르다. 이는 승인된 관측/모델 경계와 issue 최적 계획의 차이이며 기존 초기 상태를 잘못 만들어서 생긴 253건으로 묶지 않는다.

과거 Pending 886건/886GPU는 issue에도 Pending이다. 714건의 명목 구간은 Dday 전에 끝나고 172건은 명목상 Dday에 걸치지만, 승인 Dday에는 모두 Pending이다. 명목 forecast를 실제 실행/완료로 바꾸거나 Dday로 자동 retime할 수 없다.

원본 Actual driver는 과거 시작 명령에 `PRE_DDAY_START_COMMAND_NOT_REPLAYED` reference fallback을 사용했다. 저장된 Full96의 물리 성공과 무누락 결과는 해당 원본 Case에서 보존한다. 최종 Full96 계획은 A2이므로 A1 계획과 A2 계획을 각각 검증한다. 이 결과는 새 current-event 통합이나 원본 최적 prefix 실행의 인증으로 이전하지 않는다.

원본 6시간 optimized Pending prefix의 실행 receipt를 찾지 못했고 기존 승인 플래그도 Apr30 replay=False이다. 새 prefix를 만들거나 실행했다는 주장은 하지 않는다. 경로 B는 승인 observed boundary와 source-verified continuation을 연결하는 최소 adapter다. 이미 Running인 물리 episode와 완료 이력을 유지하며 원본 계획을 보존한다.

886건의 원본 QoS 허용 시작 구간을 UID별로 CSV에 보존했다. 과거 명령을 새 시작으로 바꾸려면 원본 계약상 유효한 현재 구간이 있거나 구체적인 연구 corrective 정책과 receipt가 먼저 필요하다. 조용한 reference queue 치환이나 Known 권리 확대는 하지 않는다. 잔여 불일치가 해결되기 전 실제 May01 replay는 HOLD/NOT_RUN이다.

| Stage | 분류 | UID | GPU | 원본 prefix 명목 GPUh | 원본 prefix 예약 GPUh | 관측 과거 GPUh | 첫 가능한 차이(epoch) |
|---|---|---:|---:|---:|---:|---:|---:|
| A1 | FUTURE_PENDING_COMMAND | 359 | 359 | 0.000000 | 0.000000 | 0.000000 | None |
| A1 | ISSUE_PENDING_SOURCE_STARTED_AFTER_OPTIMIZED | 42 | 42 | 178.005450 | 178.500000 | 98.909444 | 1746000000.0 |
| A1 | ISSUE_PENDING_SOURCE_STARTED_BEFORE_OPTIMIZED | 108 | 108 | 141.000000 | 141.000000 | 475.712778 | 1746000331.0 |
| A1 | ISSUE_RUNNING_OBSERVED_PRIOR_COMPLETION | 1 | 1 | 0.222029 | 0.250000 | 4.204722 | 1746000000.0 |
| A1 | PENDING_PRE_DDAY_COMMAND_NOMINAL_ACTIVE | 172 | 172 | 608.000000 | 608.000000 | 0.000000 | 1746000900.0 |
| A1 | PENDING_PRE_DDAY_COMMAND_NOMINAL_FINISHED | 714 | 714 | 417.797040 | 535.500000 | 0.000000 | 1746000000.0 |
| A1 | VERIFIED_ISSUE_RUNNING_CONTINUATION | 103 | 133 | 765.593221 | 766.500000 | 798.000000 | None |
| A1 | ZERO_NOMINAL_PRIOR_COMPLETED | 102 | 171 | 0.000000 | 0.000000 | 466.884722 | None |
| A1 | ZERO_NOMINAL_RUNNING_PHYSICAL_HOLD | 48 | 163 | 0.000000 | 0.000000 | 978.000000 | None |
| A2 | FUTURE_PENDING_COMMAND | 357 | 357 | 0.000000 | 0.000000 | 0.000000 | None |
| A2 | ISSUE_PENDING_SOURCE_STARTED_AFTER_OPTIMIZED | 82 | 82 | 342.255450 | 342.750000 | 294.795278 | 1746000000.0 |
| A2 | ISSUE_PENDING_SOURCE_STARTED_BEFORE_OPTIMIZED | 68 | 68 | 92.500000 | 92.500000 | 279.826944 | 1746000331.0 |
| A2 | ISSUE_RUNNING_OBSERVED_PRIOR_COMPLETION | 1 | 1 | 0.222029 | 0.250000 | 4.204722 | 1746000000.0 |
| A2 | PENDING_PRE_DDAY_COMMAND_NOMINAL_ACTIVE | 176 | 176 | 690.750000 | 690.750000 | 0.000000 | 1746000900.0 |
| A2 | PENDING_PRE_DDAY_COMMAND_NOMINAL_FINISHED | 712 | 712 | 416.626740 | 534.000000 | 0.000000 | 1746000000.0 |
| A2 | VERIFIED_ISSUE_RUNNING_CONTINUATION | 103 | 133 | 765.593221 | 766.500000 | 798.000000 | None |
| A2 | ZERO_NOMINAL_PRIOR_COMPLETED | 102 | 171 | 0.000000 | 0.000000 | 466.884722 | None |
| A2 | ZERO_NOMINAL_RUNNING_PHYSICAL_HOLD | 48 | 163 | 0.000000 | 0.000000 | 978.000000 | None |

첫 가능한 차이는 실행 prefix가 없어 확정 실패 시점이 아니다. Dday 관측 비교 시점은 모든 행에서 1746021600이며, 인증된 연속 실행에는 차이 시점을 기재하지 않았다.

A1/A2 최종 명령 차이: 1202 UID. Native/Actual/Fresh 새 호출은 모두 0이다.
