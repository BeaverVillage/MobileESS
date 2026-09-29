# Runtime-vNext12 causal regime runtime

완료된 연구 결과: TOTAL 안전 게이트 통과 후보 없음, Stage B에서 종료.

한국어 설명은 [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md), 기계 판정은 [FINAL_VERDICT.json](FINAL_VERDICT.json).
지정된5개 arm/C0와 grouped ablation만 평가했다. V6–V11·V42·CC4·MESS·전기 kernel은 수정하지 않았다.
원시 May 자료와 신규 April 평가를 열지 않았다. 최종 provider는 생성되지 않았다.

재현에는 SOURCE_MANIFEST에 고정한 V9 .local/PREAPRIL_SOURCE.parquet와 fold1~5 TRAIN/CAL/VALID parquet가 필요하다. 대용량 job별 feature와 중간 예측은 .local에 저장하며 Git에서는 제외한다.
모델 학습·감사는 기존 runtime_vnext_exact_environment를 사용한다. 그림만 별도 기존 aidc_publication_plot_env를 사용했으며 PLOT_ENVIRONMENT.json에 버전을 기록했다.
실행 순서는 FINAL_REVIEW_KO.md 끝에 있으며, 과학 결과를 덮어쓰지 않도록 재현은 별도 복사본에서 수행한다.
