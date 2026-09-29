# Runtime-vNext14R1 RADDiT crosswalk forensic

Base: V14 Draft PR #86, dbe906d6b211fcbb71d8b4c1c17a33ce492452ea.

결론: STOPPED_LEVEL1_TIMESTAMP_AUTHORITY_UNRESOLVED. NEW_ML_FITS=0.

공유 metadata exact audit에서 1,780,972 embedding 행 모두 historic key가 존재한다. EKEY2의 유일 raw 후보 1,775,514행, 중복 모호 행 5,458개, 유일 후보 holdout/float bitwise 충돌 0개다. 하지만 naive timestamp/export authority가 없어 승인 crosswalk를 생성하지 않았다. Kestrel F0–F2·negative controls·V13 coverage/bias는 NOT_RUN이며 observed count/rate는 null이다. 승인된 V13 연결은 0 / 621,583이다.

읽기 순서: FINAL_REVIEW_KO.md, FINAL_VERDICT.json, EMBEDDING_HISTORIC_KEY_AUDIT.csv, TIMEZONE_AND_UNIT_CANONICALIZATION.md, PUBLIC_CROSSWALK_AUTHORITY_SEARCH.md. 45개 최종 질문과 모든 요청 flag를 포함한다.

계산은 사용자 요청에 맞춰 PyArrow projected metadata와 numeric pandas joins로 수행했다. CSV는 연구 pipeline용 flat typed table이며 workbook/시각화는 만들지 않았다. 미실행 값을 0으로 대체하지 않는다. 원본 벡터는 읽지 않는다. .local의 projection과 negative forensic ledgers는 LOCAL_EVIDENCE_MANIFEST.json에 hash-bound되며 Git에 올리지 않는다. 성공을 가장하는 빈 crosswalk 파일은 없다.

재현: Python 3.11.7, pandas 2.2.3, numpy 2.4.6 및 PyArrow. `embedding_audit.py --replay`는 보존한 shared-metadata projection에서 세 diagnostic ledger의 content SHA256을 새 프로세스로 검증한다. `test_forensic.py`는 작은 합성자료의 collisions, missing/contradicting fields, float exactness를 검증한다. 이전 namespace의 스크립트나 모델은 실행하지 않았다. `prepare.py`는 원래 base HEAD에서만 실행하도록 고정했다. 이미 동결한 결과를 덮어쓰지 말고 재연구는 별도 namespace에서 수행해야 한다.

다음 연구에는 source export와 timestamp/crosswalk 계약이 필요하다. Semantic 정보가 무용하다는 결론은 없다. 모델 학습·April·May·V42/CC4/MESS/optimizer/OpenDSS 실행은 없었다.
