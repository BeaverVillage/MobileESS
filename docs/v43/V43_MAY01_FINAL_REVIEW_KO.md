# V43 May01 중간 검토

2026-10-16T04:55:30.278644+00:00 기준. 네 비교군 전체 완료가 아니다.

Golden003 B1 A1은 Original FULL/독립 Gap/Fresh96 PASS이고 재실행하지 않는다. B3 A2 인증으로 이전하지 않는다. CSV는 존재하는 새 실행 증거만 집계하고 미실행 칸은 비워 둔다. 차이는 %p이며 Planning과 Actual은 별도다.

Golden 고정 결정 Fresh는 이벤트 Actual과 다르며 원본 receipt의 ACTUAL namespace를 보존한다. 이를 Planning forecast Fresh loading으로 옮기지 않았다. Planning 선형 P1과도 별도 열이다.

- B0: Planning REFERENCE_FRESH_PASS; C0 RUNNING/NOT_RUN; C1 NOT_RUN/NOT_RUN
- B1: Planning A1_GOLDEN003_PASS; C0 PASS/PASS; C1 PASS/PASS
- B2: Planning NOT_RUN; C0 NOT_RUN/NOT_RUN; C1 NOT_RUN/NOT_RUN
- B3: Planning NOT_RUN; C0 NOT_RUN/NOT_RUN; C1 NOT_RUN/NOT_RUN

Source 권한·44 MODEL_ASSUMED·R1 미실행·R2 HOLD·FULL·Global Gap·Actual·Fresh를 분리한다. Forecast causal availability와 delayed TIME actuation은 NOT_CERTIFIED다. May02~31은 실행하지 않는다.
