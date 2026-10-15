# PR230 AIDC 현재 사이트 선택 진단

사용자 STOP에 따라 추가 Sourcefactory/Actual/AC/Native 및 기능 개발 없이 기존 SMOKE02 결과만 정리했다. 실험은 May01 IEEE123 B1의 현재 관측 Dday Known deterministic priority/backfill 규칙과 C0 기본/C1 current signed sensitivity 사이트 선택이다. 기존 Known A1 명령은 Actual에서 실행하지 않았으며 원본 P/Q는 역사적 numeric linearization anchor로만 사용했다. Source strict Provider와 최신 study case identity는 별도로 기록했다.

실제 8슬롯에서 C0/C1 Known 신규 실행 86건과 전체 Known 실제 실행 SHA가 동일했다. capacity 위반과 Unknown 의도 지연은 0이다. 두 비교군의 slot-average signed 예상 최대 선로 부하율은 0.5201161496609195로 같다. Unknown 신규 실행 및 변경 사이트 실제 GPUh는 모두 0이므로 사이트 선택의 개선 효과와 연구 성능은 검증되지 않았다. Full96와 original11SVR Fresh AC 인증은 실행하지 않았다.

C1 실제 decision 781건 중 566건은 원본 reference/release 이전, 215건은 합법 현재 event에서 사이트 후보가 모두 막혔다. 2580개 site 후보의 사유는 현재 GPU 용량 379건, runtime upper bound가 검증되지 않은 비선점 Unknown의 미래 firm Known 보호 2201건이다. 후자는 물리적 실행 불가능성의 증명이 아니라 보수적 예약 보호다. baseline 1245개 Known command의 source hard-invalid flag는 0이며, 독립 source hard/release/representation/compatibility/GPU 감사도 위반 0을 확인했다. CC4 익명 forecast를 GPU 점유로 사용하지 않았다.

C1 controller P95는 0.0937660999916261초, 최대 0.24020290000771638초이다. C0 P95는 0.008645399997476488초, 최대 0.11838149999675807초이다. 전체 wall 230.391113100006초에 Source 준비, controller/event 처리와 결과 직렬화가 포함된다. 두 Actual phase wall은 각각 81.36598879999656초와 105.20666870000423초이다. 이 값은 최적화나 개선률, 생산 시스템 SLA를 증명하지 않는다.

SMOKE02의 GPU-capacity 거부 379개 후보에서는 예약 검사를 생략했는데도 이전 후보의 last_conflict를 witness로 복사할 수 있었다. 따라서 해당 필드의 per-site 충돌 귀속은 인증하지 않는다. 실제 current GPU guard/실행 결과에는 영향이 없다. C0 61개 최종 reason이 나중에 skip한 다른 사이트의 PREPLACE_SOURCE_AUTHORITY로 표시됐지만, 독립 확인상 실제 source reference site는 모두 compatible이며 원본 site 후보도 정확히 한 번 검사했다. 사이트 선택 누락이 아니라 최종 reason 표시 문제다. 과거 실행 source/hash 및 출력은 수정하지 않았다.

PR source는 SMOKE02 실행 코드를 기준으로 두 표시 수정을 유지한다: 현재 예약 검사를 하지 않은 후보의 이전 conflict를 제거하고, C0 최종 queue reason을 실제 source-site 후보의 guard에서 가져온다. 예약·사이트·실행 판단은 바꾸지 않았다. 최종 통합 Native0 회귀 451개가 통과했다. SMOKE02 재실행 및 새 Sourcefactory/Actual/AC/Native 실험은 0회다.

중단 직전의 미검증 firm-legality helper/reference-authority probe/hard-invalid exclusion과 개발 중이던 확장 final-reason 변경은 PR source에서 분리했다. Supervisor의 최소 C0 source-site 표시 수정은 위 최종 회귀로 별도 확인했다. 전체 최신 Source/tests/CLI byte-copy, SHA manifest와 복구 patch를 runtime/v42_unified/PR_PAUSED_RESEARCH_SNAPSHOT/AIDC_UNVERIFIED_POST_SMOKE에 보존했다. 이 prototype들을 검증된 기능으로 주장하지 않는다.

JSON/CSV는 기존 실측 artifact의 요약이다. runtime_sha는 예측 provider 식별자이며 driver-only private Actual bank의 per-variant digest가 별도로 보고된 상태는 아니다. 동일 immutable Environment의 독립 deepcopy 경로와 실제 Known fairness는 감사했다.

PR 최종 표시 정리: Supervisor가 C0의 최종 queue reason을 마지막 skipped 사이트 대신 실제 source-site 후보의 guard에서 가져오도록 수정했다. 기존 실측 출력은 유지한다. 예약/사이트/실행 판단은 변경하지 않으며, 이를 확인하는 기존 GPU 거부 회귀를 강화했다. Source·시험 최종 SHA와 결과는 FINAL_CODE_SCIENCE_RESULT_FREEZE.json 및 UNIFIED_REGRESSION_RESULTS.json을 따른다.
