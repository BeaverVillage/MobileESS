# 설치용량별 원본 Job Reference·Queue 재계산

사용자 추가 지시에 따라 기존 fixed-occupancy 진단은 byte 그대로 보존하고, C0/C1/C2 각각 원본 1649 known UID와 동일 CC4 service의 FCFS Reference·queue·96-slot occupancy·C1/PCC를 다시 계산했다. Actual은 동일한 2498 UID의 submit/GPU/runtime를 private event 환경에 그대로 넣고 causal FCFS를 재실행했다. 각 capacity의 필요한 service와 원본 runtime는 동일하며 더 많은 GPU가 신규 Job을 만들지 않는다.

Reference는 issue부터 시작하며 운영일은 issue+6시간이다. 증가한 capacity는 같은 일을 prefix에서 더 일찍 실행하여 Dday GPU-h를 줄이거나 post-H tail을 당길 수 있다. 따라서 처리 GPU-h는 prefix·96-slot·tail로 나누어 audit하며 전체 required service 보존과 구별한다. C1/C2의 Actual 추가 admission/queue/carryout 역시 설비 효과이며 유연 dispatch 또는 알고리즘 성능 개선이 아니다.

공통 FCFS 초기 RUNNING fallback site는 원본 실측 AIDC 위치가 없는 연구용 placement다. 확장 시 이를 재계산한 것은 가정된 초기 배치를 바꾼 별도 시나리오이며 실제 운영 중 checkpoint migration으로 표현하지 않는다. 원본 Native WINDOW와 새 Reference의 start/site 불일치, 실측 QoS deadline 부재, WAN/restart/full-option adapter 미검증은 남는다. eligible source-mask GPU-h 변화는 인증된 flexible GPU-h 변화가 아니며 certified PCC flexible power 증가와 실행 가능한 비영 96-slot AIDC 효과는 여전히 NOT_CERTIFIED다.

실제 compute service는 completion 순간까지이며 원본 전기 power adapter는 control release 시간까지 GPU 자원을 유지한다. Actual CSV의 physical_occupied GPU-h는 이 최대 15분 release rounding을 포함한다. executed_realized_Dday_GPUh와 reserved rounding을 분리했고 이미 실행된 service +prefix +Dday +terminal remaining으로 원본 실제 GPU-h를 보존했다. 예약 GPU-h 증가를 추가 compute 서비스로 과장하지 않는다.

[2024 Kestrel 4-GPU node 사양](https://www.nrel.gov/docs/gen/fy24/90033.pdf)을 기준으로 C1 AIDC05=150 GPU는 동종4-GPU 서버37.5개이므로 exact homogeneous packing FAIL이다. C0/C2의 정수 가능성은 BOM·PSU·rack·냉각·전기접속 정격 증명이 아니다. 이들 정격은 UNVERIFIED이며 현장 시설 적격성을 승격하지 않았다. [Kestrel QoS 문서](https://nrel.sitefinity.cloud/hpc/system-resource-allocation-unit)의 normal/high는 queue priority이며 실제 사용자 deadline/체크포인트 지원 계약을 증명하지 않는다.
