# Runtime-vNext7 forensic delivery

먼저 `FINAL_REVIEW_KO.md`와 `FINAL_VERDICT.json`을 읽는다. 연구를 재현할 때 학습 명령은 없다.

Python 3.11+, pandas/numpy/pyarrow 사용. `common7.py`의 로컬 source 경로를 환경에 맞춰 설정하고 **빈 새 output 디렉터리**에서 순서대로 `prepare_forensic.py`, `authority_sources.py`, `duplicate_forensic.py`, `classify_authority.py`, `supplemental_forensic.py`, `descriptive_audit.py`, `build_reports.py`를 실행한다. 기존 frozen 산출물을 덮어쓰지 않는다. 검색 receipt/경로 목록은 원래 환경의 수동 검색 증거이며 출처를 보존한 채 복사하거나 새 검색으로 다시 기록해야 한다. 분류 스크립트는 결과 성능을 입력으로 읽지 않는다.

`verify_delivery.py`는 모델을 학습하지 않고 계보, cutoff, frozen hashes, 분류 completeness와 보존 범위를 검증한다. `.local`은 입력 cache로 Git에 넣지 않는다. `COHORT_CATEGORY_SUPPORT.csv.gz`는 완전한 범주별 지원도 CSV다. 역할 이름 TRAIN/DEV/CAL은 기술 통계 기간의 이름이며 이번에 fit/calibration을 실행했다는 의미가 아니다.

데이터 전체·비공개 요청 로그를 저장소에 새로 올리지 않았다. 기존 공개 익명값을 포함한 필요한 중복 감사 추출·집계만 새 namespace에 저장했다. 후보별 runtime CV/상관·MI/비율이 비어 있는 이유는 strict authority gate이며 누락을 0으로 대체하지 않는다.
