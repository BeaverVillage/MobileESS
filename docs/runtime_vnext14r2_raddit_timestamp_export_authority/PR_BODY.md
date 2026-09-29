RADDiT historic의 timezone-aware timestamp와 배포 embedding의 naive timestamp 사이에 source-backed 변환 근거가 없어, 99.6935%의 유일 raw 후보를 승인 mapping으로 승격할 수 없었던 V14R1(#87)을 조사했다.

새 UTC-strip(T1) 진단에서 EKEY2 일치는 0행이며, T0의 유일 후보 1,775,514행과 ambiguous 5,458행은 유지된다. Historic의 **표시 종료일 >= 2024-04-23**은 배포 부분집합 1,780,972행과 전체 행 membership이 정확히 일치한다(제외 776,912행). 그러나 실제 timezone stripping/export 코드·실행 manifest를 찾지 못했으므로 `STOPPED_TIMESTAMP_EXPORT_AUTHORITY_UNRESOLVED`, provenance `PARTIAL`, Level1 `FALSE`로 동결한다. 일치율을 출처 근거로 대체하지 않았다.

- 21개 commit, 43개 source/doc blob, notebook 저장 출력 59개, 46개 LFS 경로 및 공식 공개 자료를 조사했다. 원본 exporter·vector transform과 생성 당시 모델/환경 revision은 미해결이다.
- V42 submission/Arrival 인터페이스를 정적으로 재검사했다. 필요한 8개 semantic 입력 중 partition/qos 2개만 있으며 누락 입력 6개를 기록했다.
- 4개 회귀 테스트, 원본 timezone-aware 종료일을 이용한 독립 membership 검증, fresh-process 및 shuffled/canonical-order replay가 통과했다. V6–V14R1 과학 파일 1,417개, delivery manifest 10개, 기존 local evidence 20개 해시와 raw 파일 23,601개의 size/mtime를 재검증했다.
- Level2 F0–F2, negative controls, V13 support/bias는 `NOT_RUN`이며 미측정 수치는 null이다. `NEW_ML_FITS=0`; April 평가·May payload 개봉·모델 다운로드·vector decode·V42/CC4/MESS/optimizer/OpenDSS 실행 또는 변경은 없다.

모든 변경은 `docs/runtime_vnext14r2_raddit_timestamp_export_authority/`에 한정한다. 50문항 한국어 검토, 상세 CSV/JSON, source/local/delivery manifests와 검증 코드를 포함하며 큰 진단 ledger와 logs는 `.local`에 보존했다. 이 결론은 semantic 정보의 무용성을 뜻하지 않는다. 다음 단계에는 원본 timestamp/export 계약·실행 기록·동일 embedding 표현을 재현할 근거가 필요하다.
