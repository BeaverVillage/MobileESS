## 결과

V14의 positional ID 비교를 반복하지 않고, RADDiT 배포 embedding과 historic trace의 공유 metadata를 exact fingerprint로 검사했다. Embedding 1,780,972행 모두 EKEY2 raw key가 존재하며, 유일 1:1 후보는 1,775,514행(99.693538%), ambiguous는 5,458행이다. 유일 후보의 start-time holdout 및 runtime/power float64 bitwise 충돌은 0이고, 새 프로세스에서 ledger content hash가 재현됐다.

최종 상태는 `STOPPED_LEVEL1_TIMESTAMP_AUTHORITY_UNRESOLVED`이다. Historic는 명시적 -06:00, embedding은 naive timestamp이므로 raw 표현의 일치를 source-backed UTC physical identity로 승격하지 않았다. 21개 Git commits, 3개 branch, 42개 고유 source/document blobs, LFS/deleted history, 공개 issue/PR/fork 및 공식 관련 연구 기록에서 누락 776,912행의 filter와 timezone/encrypted export 경로를 입증하지 못했다. 이 제한은 자료가 어디에도 존재하지 않는다는 주장이 아니다.

고유 후보의 인접 순서 역전은 636,834건이고 전체 역전 쌍은 66,906,351개다. 순서로 중복을 임의 배정하지 않았다. Kestrel F0–F2, negative controls 및 V13 fold/tail coverage·selection bias는 Level1 gate에 따라 `NOT_RUN`이며 관측값은 null이다. **새 physical fingerprint에서 0-match가 관측됐다는 결과가 아니다.** 승인된 V13 end-to-end 연결은 0 / 621,583이다.

현재 V42 제출 계약에는 semantic 입력 8개 중 6개가 없고, 공개 Linq embedding 예제와 배포 encrypted representation의 동일성도 미입증이다. 다음 semantic ML 권한은 FALSE. Semantic 정보의 무용성이나 Runtime 예측 불가능성을 주장하지 않는다.

## 검증과 보존

- `NEW_ML_FITS=0`, 새 모델 inference·SVD·kNN·calibration·remaining·queue·provider 미실행. April 평가와 May payload 개봉 없음. V42/CC4/MESS/optimizer/OpenDSS 변경·실행 없음.
- 기존 V6–V14 tracked 1,373개와 delivery manifest 9개 보존. Raw 파일 23,601개 size/mtime 및 V14 local evidence 9개 SHA256 재검증.
- 합성 collision/null/holdout/float exactness 테스트 6개 통과, fresh-process replay 통과, 모집단 합계 검증과 변경 범위·whitespace 검사 통과.
- 필수 산출물, 45문항 한국어 검토, source/local/delivery manifests 포함. Projection·negative forensic ledger·소스·로그 등 local 파일 11개는 `.local`에 hash-bound 보존하며 벡터 payload를 decode하지 않았다. 가짜 성공 crosswalk는 생성하지 않았다.

Base: V14 Draft PR #86 (`dbe906d6b211fcbb71d8b4c1c17a33ce492452ea`). 추가 학습 대신 source-authority 중단 조건을 적용한 forensic 결과다.
