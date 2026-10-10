# V42 Tap-aware 자율 전압제어 개발 상태

2026-10-11 KST. **전체 31일 캠페인 배포는 보류**되어 있다. 기존 921건 실패를 보존하며 현재 새 제어기의 실제 96슬롯 전압 안전성을 검증 중이다. 회귀 테스트 PASS를 물리 검증 완료로 해석하지 않는다.

| 같은 May01 Actual·MESS 동결 계획 | 전압 위반 셀 | 최대 전압 pu | 최대 원본 선로 부하율 | 판정 |
|---|---:|---:|---:|---|
| STATCOM OFF | 19 | 1.0583754891 | 59.9034723% | FAIL |
| 기존 V1 STA08 단일 장치, 96슬롯 자동 RegControl | 40 | 1.0682074665 | 60.6523928% | FAIL |
| 기존 V1 36개 물리 PCC, 96슬롯 자동 RegControl | 921 | 1.0687059750 | 130.1884727% | FAIL |

위반 셀은 노드·상·슬롯 조합이다. 921건은 모두 과전압이며 저전압은 0건이다. 기존 19건은 36장치 V1에서 모두 해소됐으나 새로운 원격 노드 위반 921건이 발생했다. 단일 STA08 V1은 기존 19건 중 7건 해소·12건 지속·28건 신규이다. 36장치 V1의 원본 변압기 kVA 위반 24상 셀은 8개 고유 reg1a×슬롯 사건에 해당한다. 이 수를 장치 24개의 과부하로 혼동하지 않는다.

기존 V1의 24개 논리 사이트/36개 물리 PCC/27.75 MVAr는 실패 진단 구성이다. 새 평가의 후보 구성은 STA01~12 MESS PCC 및 IDC01~12 AIDC PCC, 정확히 24개·초기 18.75 MVAr다. 별도 IDC MESS PCC 12개는 설치 대상에서 제외하되 원본 전체 노드 전압·선로·변압기 검사는 계속 포함한다. 아직 최종 설계 동결·전체 정책 평가 승인이 없다.

원본 RegControl 7개는 모두 자동 운전하며 설정 SHA는 `3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf`다. Delay=15초, TapDelay=2초, MaxTapChange=16, 탭 범위 0.9~1.1 및 32단을 유지한다. 고정 커패시터 4개 ON, CapControl 0개, 원본 전압 허용범위 0.95~1.05 pu 및 모든 기존 정격을 유지한다. 과거에 별도로 허용됐던 고정탭 진단 기록은 보존되며, 최신 지시 이후 새 고정/비활성화 시험을 수행하지 않는다.

독립 저장자료 감사와 실제 단상 Q 공급/흡수 시험은 Q 부호·kvar/MVAr·상별/3상 총정격·명령/실제값·물리 PCC 중복 주입 오류를 확인하지 못했다. V1은 자기 PCC의 전압만으로 Q를 흡수하여 원격 전압과 탭 상승·상호작용을 제약하지 못했다. 정확한 감지 전압이 저장되지 않은 과거 결과는 UNKNOWN으로 남긴다. 원본 탭 자동제어가 완료됐다는 사실은 STATCOM과의 전체 협조 제어가 안전함을 뜻하지 않는다.

새 제어기는 현재 원격 전압·선로/변압기 상태 및 원본 RegControl의 PT/CT·R/X 보상 감지 전압을 사용한다. 예상 상승 탭이 원격 과전압을 악화시키는 Q 변경을 제한하고, 다른 PCC에 보상을 분담한다. Q Rate Limit·Deadband·Hysteresis·유한 상별 전류/kVA 한계를 적용하며, Q 지령만 되돌릴 수 있다. 탭과 기존 설비 상태를 직접 복원하거나 MILP 결정변수로 추가하지 않는다. Planning과 Actual은 동일 코드·설비를 사용하지만 각자 Source Initial State로 새 엔진과 제어 상태를 만든다.

Original Snapshot STATIC는 각 SolveSnap에서 자동 탭을 정적 반복으로 완료한다. 전기적 계산 반복을 실제 1초 지연과 동일시하지 않는다. 정확한 다음 STATIC 제어 동작 예측과 최종 SolveSnap 누적 탭의 근사 예측을 구분한다. 실시간 지연/과도 안정성은 정적 결과만으로 검증했다고 주장하지 않는다.

최종 배포에는 같은 May01 입력에서 24장치 96슬롯 Fresh AC의 전체 원본 및 추가 노드 전압 위반 0건, 모든 선로·변압기/장치 정격 위반 0건, 원본 제어 및 STATCOM 수렴이 필요하다. 장치 수 1→2→4→24의 결과와 실패는 모두 기록한다. 별도의 Forecast Fresh 및 Planning–Actual 상태 독립성, Forecast 오차를 반영한 상별 보수 여유, 새 B0/B1/B2/B3 실제 Canary를 통과해야 전체 B0→B2(3 worker)→B1→B3 순서를 실행한다.

기설 전압제어 인프라를 가정하며 설비 투자비·설치비와 별도 경제성 분석은 학술 연구 범위 밖이다. 총 설치 MVAr·장치 정격·최대 Q 사용률·전압·원본 선로 부하율·탭 동작·손실을 평가한다.

정지된 Planning 1.048 pu MILP 실험은 재개하지 않는다. 제어기 내부 보수 여유는 원본 0.95~1.05 허용범위의 변경이나 실제 실패의 PASS 재분류가 아니다.

원자료의 Raw AC·전체 제어 trace와 실행 소스 스냅샷은 `D:/v42_dstatcom_development_20261010`에 보존했다. 이 폴더의 `PRESERVED_FAILURE_PUBLICATION_RECEIPTS.json`은 공개한 작은 CSV·JSON·SVG가 원본과 바이트 동일함을 기록한다. 대형 trace를 요약으로 대체하거나 삭제하지 않았다.

근거: [OpenDSS RegControl](https://opendss.epri.com/RegControl.html), [C-API 0.14.5 RegControl 구현](https://raw.githubusercontent.com/dss-extensions/dss_capi/0.14.5/src/Controls/RegControl.pas). 다음 동작 예측은 실행 버전의 Sample/DoPendingAction/AtLeastOneTap 구현을 따른다.
