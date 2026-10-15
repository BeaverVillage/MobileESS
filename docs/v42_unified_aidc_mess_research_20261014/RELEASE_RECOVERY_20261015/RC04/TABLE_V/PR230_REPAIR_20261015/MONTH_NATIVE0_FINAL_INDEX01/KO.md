# May01–31 Native0 최종 입력·소스 검증

31일 × B0/B1/B2/B3 = 124 Case 모두 최종 생산 소스에 대한 검증을 통과했다. 실제 날짜별 compiler가 생성한 31개 독립 Initial State·Case·Typed Input SHA를 유지하고, 저장 공개자료를 원래 typed dataclass로 복원하여 BASIC/FULL_FLEX input_fingerprint의 정확 일치를 재확인한 뒤 실제 describe_case를 124회 호출했다. 원본 loader fallback은 0건이다.

최종 executor 소스 31개와 과학·원본 소스 42개의 SHA/bytes가 모두 일치하고, 저장 공개입력 342개도 불변이다. Native/모델 빌드/Geometry materialization/Actual/AC/미래 실현정보 parsing은 모두 0회다. 원본 provenance byte hashing은 미래 Actual 값의 parsing·사용과 구분했다. May02·May10·May12도 독립 초기상태와 당일 SourceCase·CC4를 사용한다.

원본 MONTH_NATIVE0_02의 aggregate NOT_CERTIFIED는 감사 도중 executor 파일이 수정된 당시의 기록으로 보존한다. 독립 입력 검증은 INDEPENDENT_INPUT_PROOF.json에 PASS로 분리했고, 최종 재바인딩은 EXECUTOR_REBIND_FINAL02/FINAL_EXECUTOR_REBIND.json의 PASS_FINAL_SOURCE_NATIVE0_124_CASES로 완료했다. FINAL01은 마지막 source-byte 재검사 실패를 SOURCE_DRIFT.json으로 보존했다.

May01 E1 독립 감사에서는 992개 PENDING UID의 3,667개 시작 슬롯 복원과 69개 만료 RUNNING의 187 GPU 현재 점유 보존을 확인했다. 실제 matrix geometry 독립 재계산, FULL 정수해·DW pricing 하한·Actual96/Fresh96 결과의 인증은 이 감사 범위에 포함되지 않는다.

과거 immutable raw 56개·원장 및 중단 snapshot 9개·원본 domain input 19개의 현재 SHA/bytes를 다시 확인했다. 역사적 Native 원장은 1,965.3929998874664초·inflight=None로 불변이다. 최신 사용자 승인의 fresh B1 cycle은 새 authorization_id·새 ledger로 시작하고 이 과거 사용량을 carry하지 않는다. 같은 fresh cycle의 재시작 누적은 보존한다.

계획은 PREPARED_ONLY·automatic_start=False이며 wiring blockers=[]이다. 현재 Release SHA·명시적 실행승인·날짜별 예산·May01 네 Arm Full96·대표 canary 증거에 관한 launch blockers는 유지한다. 이 입력·메타데이터 감사가 Heavy 실행을 개시하거나 May31 실행을 승인하지 않는다.

공개 입력 ZIP은 38,153,151 bytes/464 entries, 최종 typed·소스 보충 ZIP은 631,848 bytes/102 entries이며 합계 38,784,999 bytes로 40,000,000 bytes 미만이다. 두 ZIP 모두 각 entry의 bytes/SHA256를 전부 readback 검증했다. 보충 ZIP에는 최종 executor·과학 Python 소스 snapshot도 포함하고, 대형 DATA.pkl·Sparse FULL·원본 future Actual raw 내용은 포함하지 않았다.

- 공개 입력 ZIP SHA256: `e4a190d8eea1fab5e475f6926b29c9708f488ae40ccd0dc42206b48c72b5c177`
- 최종 소스 보충 ZIP SHA256: `2ab73a19b4182b74651910d147bd6edf92988ddb949c556cd8d0cb2f018df32f`
- 최종 124 Case JSON SHA256: `1b7a26d3b408c2833b2a7faf83ebab7afbb8e53d6c47728779e3730df8968602`

RESULT.json이 각 원본 증거·archive manifest·준비계획·실행보류 사유를 연결한다. 재현 도구의 Native0·보존·ZIP 관련 14개 회귀도 통과했다.

최종 재바인딩 재현 명령(새 output 경로 필요):

```powershell
python tools/rebind_v42_table_v_month.py --audit-root <MONTH_NATIVE0_02> --output <NEW_REBIND_OUTPUT>
```

두 ZIP은 같은 검증 도구로 검사할 수 있다.

```powershell
python tools/package_v42_table_v_month_evidence.py --verify <ZIP> --manifest <EVIDENCE_ARCHIVE_MANIFEST.json>
```
