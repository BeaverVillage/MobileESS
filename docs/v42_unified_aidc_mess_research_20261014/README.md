# V42 PR 검토 스냅샷

사용자 요청으로 개발과 실제 실험을 중단했다. 기존 Draft PR #230을 업데이트하며 새 브랜치나 PR을 생성하지 않는다.

현재 읽을 자료:

- [최종 검토와 25개 질문 답변](FINAL_UNIFIED_REVIEW_KO.md)
- [최종 검증 범위](UNIFIED_VALIDATION_GATE.json)
- [AIDC 실측 요약](AIDC_SITE_ONLY_PR_SUMMARY_KO.md)
- [AIDC 수치·Source/Case 이력](AIDC_SITE_ONLY_SMOKE_SUMMARY.json)
- [MESS 동일 모델 압축 실측](MESS_EXACT_COMPRESSION_BENCHMARK.json)
- [동일 Full96 CSR 증명 kernel 실측](MESS_EXACT_VECTORIZED_PROOF_BENCHMARK.json)
- [회귀 결과](UNIFIED_REGRESSION_RESULTS.json)
- [공유 원장](UNIFIED_NATIVE_RUNTIME_LEDGER.json)

AIDC는 May01 B1·MESS OFF·현재 D-day Known 기준 규칙에서 C0/C1을 2시간 재생했다. Unknown 189 UID를 관측하고 165 UID를 판단했다. Known 신규 시작 86개와 전체 실행 SHA는 동일했지만 Unknown 신규 시작/변경 GPUh는 0이다. C1의 합법 이벤트 215번에서 검사한 2,580개 사이트는 현재 GPU 379건과 미래 Known 확정 예약/검증 Runtime 상한 부재 2,201건으로 거부됐다. 계통 점수까지 도달한 후보가 없어 사이트 선택 효과나 affine false-negative를 검증했다고 주장할 수 없다. signed 선로부하율은 양쪽 0.5201161496609195이고 현재 실험의 Fresh AC는 NOT_RUN이다.

MESS S1 원본 Full96은 7,711변수·836,244제약이다. 계통행 814,560개는 모든 슬롯에 전압·선로·변압기 행을 생성하기 때문이다. 원본 CSR/영역에서 정확한 중복·동일 LHS·outward box 증명으로 제약을 357,707개(57.22% 감소), NNZ를 10,083,750개(56.65% 감소)로 줄였다. 원래 전체 행과 4대 차량 물리 replay를 검사했다. 원본/압축 Solver는 각각 20초 제한을 사용했으며 둘 다 Root LP가 중단됐다. Solver 속도 개선은 미입증이다. 같은 저장 CSR의 proof kernel 1-pass만 147.347초에서 18.566초로 줄었으며 이 7.936배를 전체 pipeline이나 Solver 개선으로 해석하지 않는다.

기존 11 SVR·7 RegControl·LDC·정격·한계를 유지한다. 과거 PR230 P/Q의 별도 Fresh16 PASS는 현재 AIDC 결과로 이전하지 않는다. 기존 U60·Runtime Repair·Migration·Known Native 및 seed 자료는 역사/비활성 자료다. 새 Known Heavy, 4단계 Heavy, S2~S7은 HOLD다.

대형 CSR·Actual 상세 JSON·원본 Source archive는 로컬에 보존했다. PR에는 요약, 작은 Full96 증명 메타데이터, SHA manifest와 복구 패치를 포함한다. 원본 Source가 필요한 전체 재생을 PR clone만으로 재현할 수 있다고 주장하지 않는다. [로컬 증거 목록](PR_LOCAL_EVIDENCE_MANIFEST.json)이 실제 파일 SHA를 기록한다. 미측정 후속 개발은 [보존 기록](PR_STOP_SNAPSHOT_AUDIT.json)의 압축 복구 패치로 남긴다.
