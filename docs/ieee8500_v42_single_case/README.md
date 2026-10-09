# IEEE8500 V42 결과 인덱스

현재 권위: [한국어 중간 보고](FINAL_REVIEW_KO.md), [단일 연구 snapshot](STUDY_CONFIGURATION_DRAFT.json), [운영 미선정/승격 차단](FINAL_SINGLE_SCENARIO.json).

최종 파일 봉인: [SHA256 manifest](ARTIFACT_SHA256_MANIFEST.json), [저장 증거 검증 receipt](ARTIFACT_PACKAGE_VERIFICATION.json). 이는 파일·계약 증거의 무결성 검증이며 물리적 Production PASS가 아니다.

공동 선정 current stage는 `joint_selection_v3/score_selection/`이며 mapping SHA는 바뀌지 않았다. 모든 276쌍/552축은 source/primaryproxy좌표에서 PASS다. 원 지리/하드웨어 실물/continuous control영역은 UNVERIFIED다. 12스케일 모두 원 global voltage 제약 FAIL이며 B1–B3 Native는0회다.

루트 `FINAL_STA_MAPPING`, `RELATIVE_POSITION_AUDIT`, `SCALE_SCREENING`, `LINE_LOADING_REPORT`, `REGCONTROL_TAP_VALIDATION`, `AIDC_CAPACITY_AUDIT`는 현재 공동 배치 결과다. 이전 동일 이름 파일은 `historical_fixed_v3_outputs/`에 byte 보존했다.

루트 `PREREGISTRATION.json`, `GEOMETRY_STATUS`, `DIRECTION_ROOT_CAUSE_AUDIT`, `GEOMETRY_LV_REPORT`와 `diagnostics/`는 **사용자가 AIDC v3 고정을 해제하기 전** 독립 진단이다. `joint_selection_v2/`는 이후 all-MV geometric witness/개발 민감도이며 최종 입지가 아니다. 현재 절차는 v3 `GEOMETRY_PREREGISTRATION`, `SCORING_PREREGISTRATION`, `selection_scores/PREREGISTRATION`, `selected_ac/PREREGISTRATION`, `selected_port_ac/PREREGISTRATION`에 각각 실행 전 동결됐다. 원 기록을 사후 수정한 pre-registration이라고 주장하지 않는다.

루트 `SENSITIVITY_RESULTS.csv`는 BG1 이전 진단이며 현재 .552 전체 후보 응답은 `joint_selection_v3/mv_sensitivity/`와 `lv_sensitivity/`에 있다. Source series Reactor 누락 경로 메타데이터의 사후 정정은 `PATH_METADATA_CORRECTION.json`으로 수치불변을 증명한다. 현재 root 보고 CSV의 lineρ는 전원 방향 parent 단자 활성상 기준이며 둘다단자·CT권선·원모든노드 fullarrays는 selected_ac/bg0p552_gpu1p0/AC_96.npz 및 AC_AXES.json에 있다.

모든 발전·부하·도체·변압기 sourcebyte/962개 V42파일은 보존했다. `COMPARISON_PLAN_BLOCKED.json`은 동일SHA arm요청만 구성한다. 독립 미노출 평가일과 Production은 아직 없으며 `execute_production`은 항상 차단된다.
