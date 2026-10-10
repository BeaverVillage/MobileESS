# 최신 검증 결과

[SVR7_FINAL_REVIEW_KO.md](SVR7_FINAL_REVIEW_KO.md)가 현재 결론이다. **SVR4와 SVR7은 모두 B2 May03의 새 Bus82 과전압 2건으로 FAIL이며 월간 확대·새 Gurobi 캠페인은 HOLD다.** 기존 네 설비는 유지했고 BUS79/BUS108/BUS50을 추가한 정확한 일곱 설비를 동결·비교했다.

필수7파일은 이 디렉터리에 있으며 [124행 비교표](SVR4_VS_SVR7_CANARY_COMPARISON.csv)는 미실행과 원계획 부재를 분리한다. 전체23.7MB 탭 CSV와 동일 바이트 gzip,270행 제어기 요약,15개 주요 TIME 궤적의 원본 NPZ, Source·입력·설비 동결·시간 지연 및 실패 분석 증거도 포함한다. 세 구성 비교의 최대선로부하율은 모든 양단·상 기준이고 원본 Raw terminal-1 값은 별도로 유지했다.

[계통도](IEEE123_SVR7_INSTALLATION_TOPOLOGY.svg)는 literal native 연결과 원본7·기존SVR4·신규SVR3·36개 물리 PCC를 표시한다. [May03 원인·한계 보고서](supporting_audits/SVR7_CE30_MAY03_UPSTREAM_FAILURE_AUDIT_03/MAY03_UPSTREAM_FAILURE_REPORT_KO.md)는 새 상류 위반과 감지 범위, 시간·상별 상호작용을 설명한다. 저장되지 않은 원본 LDC 보상 감지 전압 및 terminal P/Q는 UNKNOWN이다.

[재현 범위](REPLAY_SCOPE_AND_REPRODUCTION_KO.md), `hardware_freeze`, `source_and_admission`, `execution_journal`, `reproduction_tools` 및 `supporting_audits`를 참조한다. `.py.txt` 도구는 실행 당시 원본 바이트를 보존했다. 외부 개발 폴더에서 `.py`로 복원해 사용하며 원본 Windows 경로·입력 영수증이 필요하다. 오류가 있었던 원본 dispatcher와 종료 기록만 수정한 미실행 v2를 구분했다.

`FINAL_V42_VOLTAGE_CONTROL_REVIEW_KO.md`와 `DSTATCOM_RETIREMENT_AUDIT.json`은 앞선 개발 시작 시점의 역사적 기록이다. CapControl 진단 계획 및 NOT_RUN 표기는 그 시점에 해당하며 현재 평가에 적용하지 않는다. 같은 원본 바이트를 `historical_initial_review`에도 보존했다. 현재 D-STATCOM 제거·compiled0 증거는 `DSTATCOM_RETIREMENT_FINAL_SVR7_AUDIT.json`이다. 이전 D-STATCOM 코드·921건 실패 및 CapControl 진단도 보존했다.

현재 Source는 `ce30af2a74d9d2b6a2f2a33fee7a690927752f940f94bd466218075ba34cbf04`이고1,225개 실행 파일을 정확히 유지한다. 문서·단위시험 및 외부 실행 도구는 별도 SHA로 기록한다. AC-only PASS는 신규 SVR 계통에서 계획을 재최적화한 Planning/Actual E2E PASS가 아니다. 연구는 기설 공통 전압제어 인프라를 가정하며 투자비·설치비·경제성은 제외한다.
