# V43 PR189 원본 수치 재현

현재 공식 경로는 사용자 추가 지시에 따라 PR189 원본 연구 Case의 계산 재현이다. D-1 18:00 AEST(08:00 UTC), 내부 0~120, 평가 24~119, 900초 슬롯을 유지한다. GFS06Z, 원본 C1/전기계수, NATIVE_INPUT/WINDOWS, Known snapshot, Runtime ML Q50, CC4 Q50/Q90 및 GPU/Rack/WAN/계통 제약을 그대로 사용한다. D0/E1/FLEX30 정식화는 가져오지 않는다.

PR189 exact base는 625bbcb8b9a54a00c1660c26d96f7737c2f75457이며 공식 AIDC producer는 v42_may_campaign_native90.a_stage.run이다. 실제 May01의 11개 실행 소스·정책 파일 SHA가 원본과 일치한다. NATIVE_INPUT SHA 365824518d8b3d380b6e2cc72a78d19d27ce8d39d304acdc8ffc5b5806b342fc, WINDOWS SHA 5aec44479490ea00c0532f87229850507623b3d365fcdfbd6b105208dc8317a8이다. Known 1,649개 제출 cutoff와 양의 서비스 1,499 UID/117 Class를 유지한다.

두 평가를 구분한다.

| 평가 | 상태 | 진행 조건 |
|---|---|---|
| PR189_NUMERICAL_REPRODUCTION | Golden003 PASS | 새로운 FULL feasible UB, 독립 Global LB, Gap<=0.5%, 원본 행/정수/물리 및 Fresh AC96 |
| FORECAST_CAUSAL_AVAILABILITY | NOT_CERTIFIED | 보존된 GFS06Z 공개시각 증거에 따른 제한사항 |

CAUSAL_PASS는 False다. GFS06Z 공개시각 증거는 보존하되 재조사하지 않으며, 이 제한만으로 수치 재현이나 후속 통합을 HOLD하지 않는다. 개별 미래 Unknown UID, 실제 도착, 실제 Runtime/Completion 정보는 계속 Planning에서 차단한다.

Golden001은 공식 중지됐고 Native 호출 0회/0초/inflight 없음, Wall 132.525초로 정산됐다. 원본 Raw와 중지 원장은 변경하지 않는다. GFS00Z 수집 결과와 전기 Case 준비 코드·오류 증거는 역사적 진단 자료로 보존했고, 공식 실행 경로에서는 중단했다. 새로운 다운로드나 C1/B0/전기계수 재생성은 하지 않는다.

Golden002는 별도 출력·새 Native=0 원장으로 시작했다. 공유 Native 예산은 원본 A-stage 5,400초이며 Phase I에 별도 900초 제한을 추가하지 않는다. Worker1/Threads1이다. 원본 May01 완전 물리 Domain 캐시를 요청했으나 원본 검증기가 생산자 파일의 전체 경로까지 비교하여 거부했다. 3개 생산자 소스의 SHA/bytes는 같지만 V43 worktree 경로가 다르다. Golden002는 완전 Domain을 재구성하고 실제 Build Wall을 별도로 기록한다. 살아 있는 worker나 원본 검증기는 변경하지 않는다. 과거 point/UB/LB/Native 소비는 읽지 않는다. Fast Active Domain, SUM/Hybrid, Row Generation, Full Pricing, Integer Restoration과 FULL replay를 보존한다.

Historical 비교값은 Phase I Native 63.820초, 전체 B1 Native 97.472초, UB 0.6718471055537026, LB 0.6715871456570585다. 과거 준비 Wall 1,098.747초는 Native와 구분한다. 신규 값은 실제 실행 원장으로 보고한다.

성공 후 Unknown 기본 배치·민감도 Pending pre-site, C0/C1 Actual96, Seedless K48/Adaptive Beam–4-MESS Joint, May01 B0/B1/B2/B3/Fresh AC96, 5월 전체 순서로 계속한다. M-stage의 과거 초기 FULL MILP seed 병목을 되살리지 않는다. 새 MESS Case의 LB/UB는 독립 재계산한다.

Golden002는 2026-10-16 03:06:58 UTC compact 행렬 구성 중 progress.json의 Windows sharing error32로 자연 종료됐다. Native 0회/0초, inflight 없음, 모델 준비 Wall 1698.715초, 전체 Wall 1711.479초다. 원본 Raw/Source/실패 원장은 보존됐다. V43 상태 writer에 원본 PR189의 unique temp/경로별 lock/sharing retry를 복원했다.

Native0 독립 캐시 검증은 139.245초에 PASS했다. UID1499/Class117, STAY133609/Migration624473721 전체 내용과 Source/Input/Resource/Graph 의미 및 캐시 SHA를 원본 검증기로 대조했다. 이는 Local Domain 인증이며 새 FULL 모델, UB/LB 또는 Global Gap 인증이 아니다. Golden002 FAIL에 필요한 복구 Golden003만 별도 Source Freeze/새 원장으로 실행한다. 완료된 Domain을 재생성하거나 기존 최적화해·UB/LB·Native 소비를 재사용하지 않는다.

복구 Golden003은 2026-10-16 03:17:24 UTC(12:17:24 KST), PID39084, source commit1d62fa7286db40697b88a0ea07f4f85aacab280c로 시작했다. GOLDEN_SOURCE_FREEZE_ATTEMPT003.json과 GOLDEN003_LAUNCH_GATE.json을 따른다. 반드시 인증된 경로 독립 Local Domain 캐시를 사용하며 재사용 오류를 Domain 재생성으로 숨기지 않는다. 새로운 FULL 모델·원본 행/정수 검사·UB/LB/Gap·FreshAC96은 아직 실행 중/미확정이다.

## Golden003 확정 결과

2026-10-16 12:41:28 KST에 Gate A PASS로 종료했다. Phase I Native49.1469996초, 전체 B1 Native70.7589989초/130호출이다. 새 FULL feasible UB0.6718471055537026, 독립 Global LB0.6715871456570585, Global Gap0.03869331199%로 0.5% 기준을 충족했다. 원본 행렬 SHA c7a37d49be76737d62ae62ac4efeb566ff892065c7d4dc8ca2fa8332b0f9e42d, 원본 행/정수/물리 Replay가 PASS했다. 과거 값은 복사하지 않았으며 새 solve 결과가 수치적으로 일치했다.

Build Wall930.082초, 전체 Wall1443.884초(24분03.884초)다. 계측된 Integer physical validation5.619초와 Fresh backend0.986초는 별도다. 모든 validation/source audit/persistence를 완전히 분리한 단일 타이머는 없으므로 잔여 Wall을 Validation으로 임의 분류하지 않는다.

Fresh AC96은 96/96 수렴, 전압·선로·변압기 위반0, 최대 선로·상 부하율0.6768261627, Vmin0.978150/Vmax1.048663이다. 이는 원본 fixed replay이고 Unknown event Actual/Prefix의 Gate B 인증은 아직 아니다. FORECAST_CAUSAL_AVAILABILITY=NOT_CERTIFIED, CAUSAL_PASS=False를 유지한다. Golden004를 실행하지 않고 봉인한 새 B1 계획을 Unknown C0/Strict C1 Actual 통합에 사용한다.
