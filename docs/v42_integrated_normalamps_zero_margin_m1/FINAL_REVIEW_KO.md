# V42 통합 결과

1. Draft PR: [#133](https://github.com/BeaverVillage/MobileESS/pull/133). 검증 코드/evidence commit: cfb1411eafb761d4e9168e621fccc84b7e4a83fd; 문서 전달 commit을 포함한 최종 SHA는 PR 현재 head 및 최종 채팅 보고 기준이다. 전체 pytest **1527 PASS, 기존 경고 1개**; semantic tests **29 PASS**. 최초 push 직후 clean tree를 확인했으며 최종 전달 commit 후 다시 확인한다.
2. 기준: PR132 `ac2819cbc7b4e86fce07b4b0ed62e0647e9c473a`; M1 참고: PR131 `a16af252538774b2b2034a8722c31c0ffe5874a9`. PR132에서 분기하여 필요한 기능만 통합했으며 전체 merge/cherry-pick은 수행하지 않았다. 기존 PR131 duplicate 작업은 local commit `724dffea6ee4bf276d361b31ee3cf9b2588a7168`에 보존했다.
3. 설명되지 않은 accepted feature 누락 없음. 통합/보존 검사 PASS는 코드 검증 범위다. 새 A1 수락과 새 M1의 전체 규모 검증은 완료되지 않았다.
4. Planning voltage margin **0**, 전압 제약 **0.95–1.05 pu 유지**. 공통 Planning mapping과 새 A1/M1 builder에 적용했다.
5. **44 transformer / 120 phase**, compiled NormalAmps authority SHA `0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51`. kVA 및 line 제약은 독립 유지했다. 새 A1에서 종전 MESS 위치 누락분 72 phase/time current rows를 포함했다. 새 M1 전체 binding은 A1 gate 때문에 미생성이다.
6. A1 원본 재생성 완료: 96 step, 1499 jobs; rows **9,133,426**, cols **7,449,002**, binaries **2,223,230**, nnz **53,767,578**. solve는 **NATIVE_OUT_OF_MEMORY / Gurobi 10001**, 로그 runtime **518.37 s**. 유효 objective/UB/LB 없음. **A1_ACCEPTED=false**, freeze 미수락. infeasible임을 증명한 결과가 아니다.
7. 새 M1 rows/cols/binaries/nnz: **NOT_RUN / null**. 새 A1 미수락으로 M1을 구성하지 않았다.
8. 새 duplicate 제거 수/reduced matrix: **NOT_RUN / null**. PR131의 75,455개를 새 모델의 값으로 사용하지 않았다.
9. 새 full/reduced root LP objective 및 차이: **NOT_RUN / null**.
10. M1 Start **NOT_EVALUATED, reused=false**. 별도의 A1 과거 numeric proposal은 새 full matrix row/bound 검증에서 거절했고 Start나 고정값으로 적용하지 않았다.
11. M1 root barrier 완료 시간: **null / NOT_RUN**.
12. M1 crossover 완료 시간: **null / NOT_RUN**.
13. M1 root processing 완료 시간: **null / NOT_RUN**.
14. M1 first branch 시간: **null / NOT_RUN**.
15. M1 종료 status: **NOT_RUN — A1_GATE_FAILED**. M1 optimization call **0**.
16. NEW M1 UB: **null**.
17. NEW M1 LB: **null**.
18. NEW M1 gap: **null**.
19. **M1_ACCEPTED=false**. V42_INTEGRATION_PASS는 코드/보존/pytest 범위의 PASS이며 scientific acceptance를 의미하지 않는다.
20. 확인된 병목 하나: **A1 native memory exhaustion**. 다음 방향 하나: 동일 전체 horizon과 동일 물리 제약의 A1을 메모리 여유가 더 큰 host에서 검증한다. 이번 작업에서 실행하지 않았다.

## 실행 및 증거 한계

초기 A1에 M1 전용 Method=2를 적용했던 시도는 중단하고 입력·부분 로그·자원 기록을 보존했다. 이후 A1은 inherited automatic Method=-1, Threads=4로 실행했다. 이 terminal solve의 native memory 오류 이후 추가 heavy 재시도는 하지 않았다. 사후 예외 보고 개선은 실행 source와 구분한 SHA receipt에 기록했다.

terminal log는 Solution count 0, Best objective/bound/gap 없음이다. 로그의 반올림된 root objective 및 일시적인 heuristic proposal은 유효 A1 certificate로 승격하지 않았다. 종료 순간의 정확한 peak RAM이나 allocator 실패의 세부 원인은 관측되지 않았다. 일부 pytest/scalar fixture 검증은 A1과 겹쳐 실행되었다. 독립 작업 존재를 STOP 조건으로 삼지 않았으며, 실제 native Out of memory가 중단 근거다. 성능 향상이나 wall-time 인과 주장은 하지 않는다.

최종 pytest는 1527 PASS, exit 0이다. OpenDSS backend import 중 Windows native exception trace 0xe0465043가 출력되었지만 실행은 계속되어 전체 테스트가 완료됐다. 원인 추정이나 로그 삭제 없이 두 최종 로그에 보존했다.

PR132 April/May B0 physical evidence 및 Runtime/CC4/capacity 계보는 보존 감사에 포함했다. checkout의 LF/CRLF transport 문제와 수정 이력은 보존했고, 과학적 변경으로 숨기지 않았다. 상속 파일 변경은 FILE_LEVEL_INTEGRATION_AUDIT.csv의 11개 명시적 변경으로 제한했다. 새 M1의 duplicate/LP/Start/MIP/certificate 산출물은 NOT_RUN/null이며 CSV는 header만 보존한다.

기존 PR126/PR131의 UB/LB/gap은 새 NormalAmps + zero-margin M1 certificate에 재사용하지 않았다.

A2/M2/Actual/Fresh AC는 실행하지 않았다.
