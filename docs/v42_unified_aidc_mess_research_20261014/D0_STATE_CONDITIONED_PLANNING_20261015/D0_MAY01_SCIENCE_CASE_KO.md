# D0 May01 Science/Case

평가 Issue와 시작은 승인 초기 상태의 2025-05-01 00:00, 종료는 2025-05-02 00:00이다. 원본 Source의 UTC+10 시각을 유지하며 96×900초를 평가한다. Epoch 시작은 1746021600이다. 새 계획의 상태 조건은 D0에서 공개된 관측 초기 정보다.

- Science SHA: `a7a9aee9a4673292207709287231d76c5fffb1c71a21401690d7f44d26f7043a`
- Case SHA: `c39c3fd7f35b017a69b96da91f52ba4a4208428ae5abae745f0d61f7911c2d51`
- Source SHA: `781109e77b05f927381a2c09741acfa4935c315546f2a1e2f6fa8191b3fa768b`
- Current A1 Stage Case SHA: `9fa345e5d1a96e6803b66373dde54291b4b9c146777cbe06716b89f075bef2cd`
- Executed Pilot Source Rev1 A1 SHA: `8e0737b9b425c4aa3e88f0cf01908c18de1fb5b899815200a29ef2220f07acb1`
- Initial semantic SHA: `5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573`
- Initial byte SHA: `d8aae451858d7ab8579f087ac9811d04f83a8c10bd7e6fc1b2156e35b2db7003`

원본 초기 파일 6,973,987 bytes를 검증했다. Running324/472GPU와 Pending1300, 사이트·Gang·Elapsed·Episode를 보존했다. 원본 사이트151/296GPU, PR12920/20GPU, PR125153/156GPU 및 활성에서 제외된44를 변경하지 않았다. 이 사이트 배치는 승인된 모델 초기 상태이며 Kestrel 관측 사이트라고 주장하지 않는다.

모든 활성1624UID의 공개 Submit/Status로 D0 Known을 분류했다. 기존 D−1 Unknown78(23Running/55Pending)은 새 Known이다. D−1 Known1649 중103은 이미 완료되어 새 활성 모집단은1624다. 미래 Unknown 개별 UID/실현 완료시간을 Planning에 사용하지 않았다.

기존 내부 Native[24,120)는 새 D0 평가[0,96)에 명시적으로 대응한다. Native24는 D0이며, 0~23은 평가에 사용하지 않는 내부 좌표다. 과거 6시간 실행 영수증을 이 Case의 Gate로 사용하지 않는다. 과거253/886/888의 불일치, Full96/Fresh 및 Prefix NOT_CERTIFIED 결과는 역사 자료로 보존한다.

초기 Running255/285GPU는 양의 Q50 잔여 서비스로 표현하고, Q50가 이미 만료된69/187GPU는 D0 현재 슬롯에서 물리 점유를 유지한다. 이는 실제 완료가 아니다. Actual은 모든324를 실제 완료 이벤트까지 유지한다. 현재 만료 Gang의 Runtime 위험 Target38.06103955552418GPU 중복만 제외했고 미래 위험 계수는 원본 그대로다. Achieved CC4/Runtime Reserve는 결정변수이며 0으로 고정하지 않았다.

Pending1300을 D0 이후 Source 호환 사이트와 96개 시작 슬롯에서 최적화하도록 원본 F2-CRA에 입력했다. 연구 Backlog 기본 창은85500초이고 추가 의도적 지연은0이다. 원본 기다림/Release/Hard Deadline/보호 정보는 별도로 보존한다. 고객 SLA 및 보호 계약 충족을 인증하지 않는다. 확인되지 않은 Checkpoint 권한은 HOLD이며 이 기본 행동 도메인을 과거 무제한 Migration 도메인과 동일시하지 않는다.

원본 CC4 May01 row412를 그대로 재사용했다. 선언된 발행은 Apr30 18:00(UTC08:00), D0보다21600초 전이다. Q50합5503.441472156033GPUh, Q90합24408.063227293504GPUh이다. 초기78은 May01 도착 예측 cohort보다 앞서 제출되어 예측에서 차감하지 않는다. Saved feature71개 및 TRAIN400일의 as-of를 재검증했고 미래 학습 label0이었다. 예측 선택은 회고 연구 계약이다. 실제2025 운영 ingestion 및 checkpoint byte 가용성은 NOT_CERTIFIED다. Scaling/Clipping/Refit은0회다.

IEEE123, AIDC12/GPU780, 설치SVR11/원래RegControl7을 유지한다. 원본 day bundle에서 Source가 승인한 동일 day의 current electrical_certificate/grid_outputs/route_table 세 필드만 명시적으로 병합했다. Route bytes는 동일하며 수량/CC4/Runtime/Rack을 바꾸지 않았다. Source Raw를 덮어쓰지 않았다.

새 A1 Native0 모델은 844,129행/36,931변수/10,920,902NNZ이다. Original P1/P2 layer와 전체 남은 서비스/CDF/Carry, GPU/Rack/WAN/Grid 제약을 유지한다. Source Rev1의25초 Pilot에서 실제 Native26.238000초를 사용했으나 정수 incumbent0으로 FULL 실행 가능성 및 최적성은 NOT_CERTIFIED다. Phase I/전체 Migration Pricing 인증은 미확립이며 기존 인증을 이전하지 않는다.

Pilot 이후 명령의Native좌표·FULL bool·반환예산finite 검증과M단계의stage/anchor·성공한M1registry→A2 전달 검증을보강했다. Rev1 Source13파일과9개Case자료를`A1_PILOT01/EXECUTED_CASE`에Byte-identical 보존했고 원장은수정하지않았다. 현재Source를Native0로다시생성해Matrix SHA `29ddbc898bf954a607bde471014bd93c1e973ece3f661f24624a7b9798a88f34` 및전체domain/objective SHA `5bb3e3a0bbda181fc483215b2878463da712d85c3f37418acf0e2f07b1a3592c`가Rev1과동일함을확인했다. Source/Science/Case는새로구별한다. 현재Source Native호출0이며 Rev1 bound/primal/최적성인증을현재Case로이전하지않는다.

M1/A2/M2와 Actual은 현재 D0 FULL 계획의 Source/Case/Anchor를 확보한 후 진행한다. 과거 A1/A2, MESS UB/LB나 FCFS 진단 계획을 대신 입력하지 않는다. Actual 최종 실행에는 A2/M2가 필요하다.
