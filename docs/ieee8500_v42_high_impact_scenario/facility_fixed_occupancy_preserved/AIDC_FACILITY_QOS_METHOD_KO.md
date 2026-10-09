# AIDC 설치 규모·Job 서비스·유연성의 분리

C0=780, C1=1170, C2=1560 GPU는 각 사이트의 원본 설치 수에 정확히 1/1.5/2를 곱한 연구 설계다. 정수 GPU와 사이트 합계는 검증했다. 12곳의 버스와 원본 logical single-gang compatibility envelope는 유지했다. 기존 4개 logical pool/site는 합산 가능한 실물 rack이 아니다. 확장 설비의 서버·전원·rack·냉각·접속변압기 정격은 UNVERIFIED다.

Planning 1649개 원본 UID/arrival/GPU/service와 원본 grid-blind reference·CC4 served/backlog를 세 후보에 동일하게 사용했다. Actual 2498개 원본 UID의 frozen causal queue 점유율도 동일하다. 확장은 idle IT를 늘리고 원본 C1을 새 설치범위에서 재계산하며 Job 수나 service GPU-h를 늘리지 않는다. PCC−IT는 원본 C1의 냉각과 기타 시설 전력 합계이고 실측 냉각 정격이 아니다.

[2024 Kestrel 사양](https://www.nrel.gov/docs/gen/fy24/90033.pdf)은 4 GPU/node를 설명한다. C0/C2는 4-GPU 단위 정수 분할이 가능하지만 C1의 AIDC05=150은 37.5 node여서 정확한 동종 4-GPU 설비는 실패한다. GPU SKU·혼합 서버·부분 탑재 증거가 없으므로 1172개 GPU를 1170으로 이름 바꾸거나 서버를 임의 추가하지 않는다. 이 산술 사례가 다른 시설의 현장 전기·냉각 적격성을 증명하지 않는다.

[Kestrel QoS 문서](https://nrel.sitefinity.cloud/hpc/system-resource-allocation-unit)의 normal/high는 scheduling priority와 charge factor이다. [원본 데이터 메타데이터](https://data.openei.org/submissions/8643)의 queue wait/runtime는 실제 사용자 deadline·application checkpoint/restart 계약을 제공하지 않는다. 원본 코드도 wait quantile을 Empirical historical additional-delay budget; not SLA or user tolerance로 명시한다. 20/30/40% flexible share를 신규 실측 계약으로 만들지 않았다.

기존 B0와 Native reference는 site 1290개, start 1024개가 다르며 admitted B0 start 1024개가 원본 WINDOW 밖이다. source-mask upper bound는 이 reference에 투영한 완화이며 동시에 제거한 일을 다른 시점/사이트에서 수행하는 실제 schedule이 아니다. WAN 1 active transfer, 80 GB/GPU payload와 destination capacity, checkpoint/restart, deadline, post-H tail을 묶는 adapter가 검증되지 않았다. SOURCE_B0_REPLAY_ONLY는 96-slot 원본 occupancy·service·backlog와 zero action을 재현한다. 원본 B0의 Native QoS window 적격성을 새로 인증하거나 nonzero control을 증명하지 않는다. 따라서 nonzero AIDC 96-slot 실행 가능 제어는 FAIL_NOT_CERTIFIED이며 certified 감소는 0 kW다.
