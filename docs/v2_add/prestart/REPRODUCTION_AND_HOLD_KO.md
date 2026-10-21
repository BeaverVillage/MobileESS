# V2_add prestart 재현 및 실행 보류

아래 명령은 저장소 V2_add에서 격리 Runtime의 Python으로 실행한다. 원본 V44/V1_add 소스와 Worker는 변경하지 않는다. 이 절차는 새 실험 버전을 생성하지 않는다.

1. `python -m v2_add_preflight.prestart init`
2. `python -m v2_add_preflight.prestart inputs`
3. `python -m v2_add_preflight.prestart_electrical prefix`
4. `python -m v2_add_preflight.prestart_electrical responses`
5. `python -m v2_add_preflight.prestart_native fixture_calls`
6. `python -m v2_add_preflight.prestart_native build`
7. `python -m v2_add_preflight.prestart_aidc` — 실제 인과적 진단이지만 기준 불일치로 인정하지 않는 결과도 보존한다.
8. `python -m v2_add_preflight.prestart_electrical two_peak`
9. `python -m v2_add_preflight.prestart_split_fleet`
10. `python -m v2_add_preflight.prestart_execution plan`
11. `python -m v2_add_preflight.prestart_certify`
12. `python -m v2_add_preflight.prestart_report`
13. `python -m v2_add_preflight.prestart_verify`
14. `python -m v2_add_preflight.prestart_report`
15. `python -m v2_add_preflight.prestart_seal`

기존 AC/Fresh Receipt와 일치하면 배열을 재생성하지 않고 SHA 확인 후 재사용한다. 코드/입력 SHA가 다르면 기존 캐시를 덮지 않고 실패하며 새 증거 태그가 필요하다. `prefix`는 기존 배열 산술 감사이고 `responses`는72개 짧은 고정 상태 AC 교란이다. `two_peak` 및 차량군 분할은 유한 TIME/Fresh witness이며 공식 B0/B1/B2/B3 캠페인이 아니다.

Native0 생성은 원본 이동 블록/Q250/STA 점유와 실제 원본 Route를 구성하지만 IEEE8500 FULL Grid 모델이 아니다. 소형 Fixture도 전체 Stage/K48/Beam/Joint 인증이 아니다. 별도의 Native optimization이나 presolve를 실행하지 않는다. 자원 관측은0.25초 간격이며 자체 RSS4GiB/시스템 여유6GiB/생성900초 보호 기준으로 중단한다. 이 값은 원본 Solver budget 변경이 아니다.

모든 필수 Gate가 인증되지 않아 캠페인 명령은 차단된다. 실행 권한 파일을 이 절차에서 만들지 않는다. 실제 Stage Adapter·독립 FULL·전압/초기 이력·날짜 간 검증을 완료한 후에도 별도 사용자 승인이 있어야 한다. 복구 시 같은 날짜/입력/Scenario/Source/수용 해시·산출물 SHA를 확인하고 미정산 Native ledger를 임의 초기화하지 않는다.
