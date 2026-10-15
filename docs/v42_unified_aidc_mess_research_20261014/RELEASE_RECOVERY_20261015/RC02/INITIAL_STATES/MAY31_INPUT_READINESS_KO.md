# 2025년 5월 독립 D0 초기 상태 재구성

원본 May01 initializer 전체 객체·semantic SHA 재현을 먼저 통과했다. 이후 날짜는 해당 날짜 원본 이벤트의 00:00 UTC+10 이하 Prefix와 같은 PR125/PR129/FCFS 규칙으로 각각 생성했다. 전날 Actual Carry와 미래 Completion·Unknown UID는 사용하지 않았다.

| 날짜 | 상태 | Running UID | Running GPU | Pending UID | 이전 완료 UID | 정확한 누락 사유 |
|---|---|---:|---:|---:|---:|---|
| 2025-05-01 | INPUT_READY | 324 | 472 | 1300 | 178 |  |
| 2025-05-02 | INPUT_READY | 204 | 435 | 1235 | 141 |  |
| 2025-05-03 | INPUT_READY | 274 | 472 | 995 | 419 |  |
| 2025-05-04 | INPUT_READY | 268 | 464 | 492 | 310 |  |
| 2025-05-05 | INPUT_READY | 382 | 514 | 472 | 262 |  |
| 2025-05-06 | INPUT_READY | 288 | 396 | 554 | 148 |  |
| 2025-05-07 | INPUT_READY | 396 | 515 | 5849 | 176 |  |
| 2025-05-08 | INPUT_READY | 249 | 520 | 3902 | 952 |  |
| 2025-05-09 | INPUT_READY | 345 | 395 | 2958 | 96 |  |
| 2025-05-10 | INPUT_READY | 281 | 364 | 2706 | 1055 |  |
| 2025-05-11 | INPUT_READY | 271 | 382 | 2054 | 1329 |  |
| 2025-05-12 | INPUT_READY | 164 | 339 | 1659 | 165 |  |
| 2025-05-13 | INPUT_READY | 272 | 438 | 1200 | 212 |  |
| 2025-05-14 | INPUT_READY | 340 | 485 | 1392 | 368 |  |
| 2025-05-15 | INPUT_READY | 347 | 477 | 1196 | 1791 |  |
| 2025-05-16 | INPUT_READY | 294 | 443 | 1048 | 223 |  |
| 2025-05-17 | INPUT_READY | 183 | 291 | 21 | 2170 |  |
| 2025-05-18 | INPUT_READY | 128 | 486 | 1145 | 3 |  |
| 2025-05-19 | INPUT_READY | 133 | 498 | 1007 | 95 |  |
| 2025-05-20 | INPUT_READY | 185 | 524 | 789 | 122 |  |
| 2025-05-21 | INPUT_READY | 117 | 509 | 549 | 74 |  |
| 2025-05-22 | INPUT_READY | 119 | 492 | 563 | 41 |  |
| 2025-05-23 | INPUT_READY | 159 | 499 | 313 | 123 |  |
| 2025-05-24 | INPUT_READY | 61 | 444 | 303 | 30 |  |
| 2025-05-25 | INPUT_READY | 75 | 463 | 274 | 77 |  |
| 2025-05-26 | INPUT_READY | 113 | 514 | 155 | 60 |  |
| 2025-05-27 | INPUT_READY | 68 | 461 | 94 | 64 |  |
| 2025-05-28 | INPUT_READY | 62 | 443 | 74 | 124 |  |
| 2025-05-29 | INPUT_READY | 79 | 458 | 46 | 82 |  |
| 2025-05-30 | INPUT_READY | 137 | 286 | 7 | 88 |  |
| 2025-05-31 | INPUT_READY | 139 | 317 | 36 | 56 |  |

Source SHA, 초기 상태 byte/semantic SHA, CC4 Forecast SHA·예측 행·issue time은 날짜별 INITIAL_STATE_RECEIPT.json과 통합 JSON에 저장했다. 새 초기 상태는 lossless gzip이며 어댑터 load_initial_state로 검증 후 읽는다. May01 공인 파일은 그대로 참조한다.

12 AIDC Site는 관측된 Kestrel 위치가 아니라 기존 승인된 연구 배치 모델이다. Request version history와 historical ingestion 시각은 원래 계약대로 미확인이다. 원본의 UNCONFIRMED QoS·누락 hard window를 새 SLA로 채우지 않았다. Raw QoS/partition/requested walltime은 별도 공개 Request ledger에 보존하고 정책 권한으로 승격하지 않았다.

이 결과는 Initial State/CC4/Raw 준비 증거다. 날짜별 D0 Planning Case Compiler, P1-only 전체 단계, Actual96/Fresh AC, 추가 Native 예산 및 Campaign Gate 통과를 대신하지 않는다. Native Optimize와 P2 호출은 모두 0회다.
