# V40M Actual execution authority closure

판정: **V40M_EXTERNAL_AUTHORITY_STILL_MISSING**.

시작 commit: `2434a0e8a870ad7c52c34fdc0e270c6e164aebd8`. Branch: `codex/v40m-actual-authority72-closure`. Worktree: `C:\codex_mobileess_workspace\MobileESS_v40m_authority72_closure`.
최종 연구 commit SHA는 post-commit V40M_FINAL_COMMIT_RECEIPT.json에 기록한다. 그 receipt는 자신의 commit SHA를 내장하지 않는다.

72는 UID 수가 아니라 날짜/B0–B3 case 수다. 원래 122 case / 8,786 UID–case 행을 V40H·V40I 사이에서 정확히 대조했다. 72 blocker는 5,126 UID–case 행과 고유 UID 1,634개다. V40K receipt의 72는 count 확인이며 새 identity 목록으로 해석하지 않았다.
72 case-key SHA256: `f6039f9de579ae7af844f74c87c765b8559f0d916dbab048d7975c3e74dce8a5`.
5,126 UID–case-key SHA256: `4249fd68c1db1fdf06a75205626da157f29c4e1d998987b9cf1dc92a8b837d74`.
과거 44 jobs는 2025-05-01/B1에 해당하고 기존 44-case blockers와의 일치는 0이었다. 숫자로 cohort를 합치지 않았다.

| Classification | Old | New |
|---|---:|---:|
| LEGITIMATE_PRE_DAY_COMPLETE | 50 | 50 |
| ACTUAL_EXECUTION_AUTHORIZED | 0 | 0 |
| AUTHORITY_CONFLICT | 0 | 0 |
| AUTHORITY_MISSING | 72 | 72 |

기존 72건 중 해결 0건. 신규 pre-day-complete 0건, 신규 execution-site 0건, 충돌 0건, 잔여 missing 72건.

50개 root, 최초 1,211,390개 + 확장 경로 metadata 복구 472개 = 1,211,862개 파일, 104,489,345,932 bytes를 목록화했다. 최초 inventory SHA256: `1d49eefcbad7d3fa4dd2ea3fcb9e3af5813abe790a7899837a3a741008a44aaf`. 복구 addendum은 원래 error 경로에 한정된다.
실제 parsed/동일-content 재사용 72,266개; 미파싱 1,139,596개. 최초 inventory 오류 691건 중 잔여 223건, 파싱/읽기 오류 2건은 별도 limitations에 공개했다. 긴 UNC 경로 14,236건을 재검색해 복구했다.
검색 제외는 dependency/VCS/cache, 다른 power benchmark의 job domain, 이전 mobility/electrical solver audit, 비실행기록 형식 등이다. 전체 저장소가 완전히 읽혔다거나 외부 증거가 존재하지 않는다는 주장이 아니다.

| 순서 | Source family | Files | Bytes | Parsed | Not parsed |
|---|---|---:|---:|---:|---:|
| A | Original scheduler/job raw records | 16,773 | 11,309,942,092 | 9,307 | 7,466 |
| B | Execution/start/end raw records | 3 | 21,296,653 | 3 | 0 |
| C | Actual site/partition/node allocation records | 925 | 2,289,570,695 | 193 | 732 |
| D | Authoritative adapter inputs | 827 | 26,330,758 | 332 | 495 |
| E | Archived raw source files | 93 | 743,487,590 | 35 | 58 |
| F | Historical handoff/freeze references | 599,510 | 12,491,095,934 | 31,480 | 568,030 |
| G | Execution logs/manifests | 593,731 | 77,607,622,210 | 30,916 | 562,815 |

원본 Kestrel ZIP 및 member SHA256/정확한 row key를 다시 확인했다. 원래 전체 UID 2,543개의 raw timing·GPU가 frozen observation과 일치한다. 물리 nodelist는 복구 가능하지만 현재 12개 합성 AIDC의 case별 실제 allocation은 아니다. 미해결 5,126행은 PENDING이어서 과거 관측 종료를 현재 case의 실제 admission/end로 바꿀 수 없다. 기존 완료 3,660행은 RUNNING 연속 실행 규약과 실제 timestamp로 재검증했다.

주요 근거: V40M_RAW_UID_EVIDENCE.json, V40M_TYPED_UID_SIGHTINGS.parquet, V40M_SOURCE_ADJUDICATION.json. 72-case JSON/Parquet 원장에는 UID별 실제 관측 시각, 물리 노드, source/member hash, exact row key와 미해결 이유를 기록했다. Parquet의 복합 열은 canonical JSON 문자열이며 scalar case 열은 native 형식이다.

검증: unit 21개 + data regression 21개 = 42개 PASS. V40I/V40J/V40K source·artifact 해시 보존, V40L 내부 접근/수정 없음, 허용 namespace 외 tracked 변경 없음.

31_DAY_ELECTRICAL_REGENERATION = HOLD. B0_B1_B2_B3 = NO. FULL_MAY = NO. 재학습, q/K0/tail/PF/Q-control 변경, optimization 및 certified electrical output 생성은 모두 0/NO.
