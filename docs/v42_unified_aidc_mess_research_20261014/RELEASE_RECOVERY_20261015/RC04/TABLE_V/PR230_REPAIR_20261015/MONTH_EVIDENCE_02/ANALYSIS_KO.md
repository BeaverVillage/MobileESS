# May01–31 Table V 독립 공개입력 검증 및 보존 분석

2025-05-01부터 2025-05-31까지 실제 날짜별 compiler와 E1/FLEX30 compiler를 호출한 31일 × 4 Arm = 124 Case 입력 검증이 모두 통과했다. 실패·누락은 0건이며, 31개 Initial State SHA·Case SHA·Typed Input SHA가 각각 독립적임을 확인했다. 같은 날 네 Arm은 동일한 초기상태와 Case를 공유한다.

B0=Reference/OFF, B1=Full E1·FLEX30·R1/OFF, B2=Reference/ON, B3=Full E1·FLEX30·R1/ON을 유지했다. D0 이후 96슬롯(900초), 원본 GPU/Rack/WAN/서비스·Carry 권한과 R2 HOLD·P2 0회·Worker 1·Threads 1이 보존됐다.

원본 감사 aggregate의 NOT_CERTIFIED_NATIVE0_MONTH는 감사 도중 검토 후 executor 코드가 갱신된 데 따른 Source Pin 불일치다. 124개 입력 검증은 모두 PASS이며, 이를 독립적으로 구분한 INDEPENDENT_INPUT_PROOF.json은 PASS_31_DATES_124_TYPED_INPUT_CASES다. 최종 executor 소스 재바인딩은 별도 산출물로 검증한다.

## May02·May10·May12 독립성

### 2025-05-02

- 공개 Known UID: 1439; 양수 잔여서비스 UID: 1369
- Initial State SHA: `3d71c5f78d5b1fe69e4915786b4861a8d568475e2fe94cedbb4bc72108d707f9`
- 원본 일별 Native Template SHA: `c064dd4fa0529411f62160f295551276cd9775713e335c97f1757056cc64f50f`
- Case SHA: `fb9e8bbe0f2b9faa96ceff0d9c8f1f156676cd77951a9a34852a7dff114aa73b`
- Typed Input SHA: `e0f896470c285926a08e86e2f2df63b84a43f8ec227cf01d65f0f28b74695830`
- CC4 Forecast Receipt SHA: `f9557f95ef2a60640b34c429104621b1095fd9e262e81e009dc06bce4d4a0f14`

### 2025-05-10

- 공개 Known UID: 2987; 양수 잔여서비스 UID: 2714
- Initial State SHA: `cd881e103900579f6a9b4391558b984b4fe376a9d8aa3d16b53bb51cb4767352`
- 원본 일별 Native Template SHA: `665ab55a22c7cd251fcc5b2ec34a995ef06db195dd39477759bcce2722ef00b1`
- Case SHA: `78350d072f7cbc0857be1c3a3181b0ce88da5f5f4a42f43e4f031ca5a7580eed`
- Typed Input SHA: `891565ba997879bef141a79ee72805af225f2788cc0ff1136229f5ed8b36b9a5`
- CC4 Forecast Receipt SHA: `f650ddf1766bef3d16f0343af1e6e503bf0a0340cc7eedea6db94a5edf651358`

### 2025-05-12

- 공개 Known UID: 1823; 양수 잔여서비스 UID: 1678
- Initial State SHA: `a4ca2d7d467da55b930e8f2c92bc1480f35c0e50ac01417c8d146a5b47e9944c`
- 원본 일별 Native Template SHA: `0ba29bfa2526b7bef772ffc1a824eab7c2f3df087cad5408c1e9509b9fc1a1e1`
- Case SHA: `6b14239e937b00c6932a4404fcaac8931d965274b31f2b3de7163d2c7c21ecd3`
- Typed Input SHA: `fc24323c4b5d79e5c6c316d2ae0ff85b8feb3496dac18636fcd462f0f571809b`
- CC4 Forecast Receipt SHA: `5db2c0ce62d51edbc63a76d1d39736d1b05c4045ca1d83fdff8000bb61f89747`

## Native0 및 원본 보존

이 입력/메타데이터 감사의 Native·모델 빌드·Geometry materialization·Actual·AC·미래 실현정보 parsing은 모두 0회다. 원본 receipt 검증 과정의 ACTUAL bundle·원시 archive byte hashing은 provenance SHA 확인에만 사용됐고, 미래 Actual 파일 parsing·값 사용과 구별했다. C1의 승인된 forecast-weather 입력만 원래 경로로 읽었다.

May01 별도 E1 감사는 원본 typed issuer 1,624개 receipt를 재발급·독립 산술 비교하여 992 PENDING UID의 3,667개 시작 슬롯 복원을 확인했다. 69개 Q50 만료 RUNNING의 187 GPU 현재 슬롯 점유와 전체 STAY 서비스·Carry도 보존됐다. 실제 Matrix/Domain geometry 독립 인증·FULL 정수해·DW Global LB·Gap 인증과는 범위를 구별했다.

기존 immutable Raw 56개, Stop Snapshot 9개, 원본 Domain Input 19개의 SHA/bytes 보존을 재확인했다. 기존 B1의 역사적 Native 원장은 1,965.3929998874664초로 그대로이며 inflight=None·P2=0이다.

최신 사용자 승인에 따른 fresh B1 accounting cycle은 별개다. 새 authorization_id·새 ledger를 0초에서 시작하고, 기존 1,965.393초를 carry하지 않는다. 같은 fresh cycle의 중단·재시작은 누적한다. 원본 원장과 STOP_COMPLETION에 남은 과거 잔여예산 수치는 역사적 승인 범위의 기록으로 보존하며, 새 cycle의 잔여예산으로 해석하지 않는다. 이 감사가 실제 Heavy 실행을 개시하지 않는다.

## Commit용 압축 증거

최종 ZIP은 38,153,151 bytes로 40,000,000 bytes 미만이다. 464개 entry의 압축 해제 후 bytes·SHA256를 전부 readback 검증했다. 원본 공개자료 총 970,551,805 bytes를 포함하며, 31일 공개 INPUTS·approved Initial State·Readiness Receipt·124 Case 감사·입력 독립성 증명·E1 Domain 감사·Native 보존 원장·재현 도구를 담았다.

- ZIP SHA256: `e4a190d8eea1fab5e475f6926b29c9708f488ae40ccd0dc42206b48c72b5c177`
- ZIP: `TABLE_V_31_DAY_PUBLIC_NATIVE0_EVIDENCE.zip`
- 검증 manifest: `EVIDENCE_ARCHIVE_MANIFEST.json`

원본 future Actual bundle, Parquet 원시 trace, Sparse FULL 행렬, pickle은 포함하지 않았다. 원본 파일은 변경·삭제하지 않았다. 최종 Source 재바인딩 결과는 이 입력 증거 ZIP과 별도로 보관한다.

검증 명령:

```powershell
python tools/package_v42_table_v_month_evidence.py --verify <ZIP> --manifest <EVIDENCE_ARCHIVE_MANIFEST.json>
```

입력 검증은 실제 FULL-feasible Planning, DW Pricing 하한, 정수 UB, Actual96/Fresh96 완료 또는 May31 Heavy 실행 승인을 뜻하지 않는다.
