# 재현 범위와 실행 진입점

직접 기준은 PR183 `3100039d19a22ec407713f36a9e978b2e96533a8`이며 과학적 기준은 PR162 C3A다. 이번 receipt는 별도 D: worktree와 원래 검증된 D: scientific inputs를 사용한다. `D_DRIVE_EXECUTION_AUDIT.json`에 실제 경로가 있다. 새 입력을 만들거나 원래 `.npz`를 편집하지 않는다. `artifacts/source_authority/ROUTE_TABLE.json.gz`는 SHA `3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9`인 원본의 D: copy다. 원래 DATA 안의 archived C: provenance 문자열은 실제 입력 읽기 경로가 아니다.

모든 Python 진입 전에 외부 작업공간의 `tmp/activate.ps1`을 실행한다. 동봉한 `ACTIVATE_D.ps1`이 그 정확한 사본이다. Temp/cache/log/checkpoint와 새 scientific output은 D: 작업공간에 둔다. 설치된 Python·library·license의 C: 경로는 예외다. Git metadata는 별도 worktree를 구성한 D: Git common directory를 공유한다. Python I/O guard는 새 작업공간 밖 쓰기와 C: scientific input 읽기를 거부한다.

읽기 전용/검증 모듈의 순서는 `initial_audit`, `structure`, `fixtures`, `verify`, `cumulative`, `grid`, `exact_cut.tests()`, `report.main()`, `final_audit`, `report.package()`다. `initial_audit`는 최초 시작 시 HEAD가 PR183 exact base인지 확인하는 bootstrap audit이므로 publication commit 이후 기존 감사 결과를 재사용한다. 기존 `(z,f)` 증거는 외부 작업공간에 보존하며 해당 audit의 모든 SHA를 최종 검토에서 다시 검사한다. Fixture에는 명시적으로 구분한 작은 HiGHS LP 100회가 있다. 이는 full-scale Gurobi ROOT가 아니다.

`root`는 proof gate·사전등록·자원 격리 확인을 모두 통과해야 최대 한 번의 B2 ROOT를 호출하는 별도 진입점이다. 이번 실행은 외부 A-stage worker와 겹쳐 optimize 이전에 RESOURCE_PENDING으로 종료됐다. 새 ROOT Runtime/Work와 presolve size는 `null`, 소비한 native 예산은 0이다. 수학적으로 동일한 B1과 H2 ROOT는 실행하지 않는다. B2 ROOT용 once-token도 생성하지 않았다.

Canary와 production은 실행하지 않았고 이 PR에서 사용 가능한 production solver로 승인하지 않았다. ROOT의 certified ΔLB≥0.001·원본 동치성·실용 시간 gate를 통과한 뒤에만 다음 단계를 구현·실행한다. 현재 후속 실행을 자동 예약하지 않는다.

완료된 `(z,f)` 작업에서 늦게 생성된 battery feasibility certificate, exact payload, multiplier는 `artifacts/PREVIOUS_ZF_COMPLETED_CERTIFICATE/`에 byte-identical 사본으로 동봉했다. `PREVIOUS_CERTIFICATE_COPY_RECEIPT.json`이 원래 경로와 사본 SHA를 연결한다. 원래 certificate 내부의 provenance 경로는 수정하지 않았다. 이 별도 수학적 증명이 있어도 이전 native status는 TIME_LIMIT(9) 그대로이며, 새 ROOT 실행이나 새 global LB 갱신을 뜻하지 않는다.

`SHA256_MANIFEST.json`은 새 source와 evidence bytes를 기록한다. Manifest 자체와 publication 이후 외부 `GIT_COMPLETION.json`은 자기 참조를 피하기 위해 제외한다. Publication completion에는 실제 HEAD·Draft PR·remote equality·clean tree를 기록한다.
