원래 Adaptive Beam → 4-MESS Joint MILP → Original FULL Validation → Incumbent Registry를 보존했다. PR220/221/222/227의 원본 계통·경로·384 Charge Mode·SOC·P/Q 구조와 역사적 Moving UB를 변경하지 않았다.

15. 원래 PR221 INITIAL_1001 동일 4대·24노드·96슬롯 Direct Joint를 정확히 압축했다(PASS). 변수137,635와 이진416은 그대로이며715,600행→685,819행,7,008,176NNZ→6,961,847NNZ다. 기존 보수적 Box만 사용한 첫 시도는 삭제0행이었다. 보존된 Connection 부등식과 Helper 등식에서 외향 반올림한 유효 Bound를 증명한 뒤29,781 Grid 행을 삭제했다. Solver 변수 Bound는 변경하지 않았다. 같은 제한 Pool의 Integer/LP 가능영역·목적·Raw Lift·MIP Start 동등성과 Original FULL 포함성을 분리했다. 제한 Pool이 전체 Original Domain과 같다는 주장은 없다.

16. 계산 성능 개선은 확인하지 못했다(NOT_CERTIFIED). 원본 Native19.089초/측정 Joint Wall22.887초, 압축 Native20.229초/Joint Wall24.085초에 압축·증명·캐시 비용9.243초가 추가됐다. 원본은 같은 Pool에서 Presolve 후 Optimal, 압축은 TimeLimit에 도달했다. 정확한 수학적 동등성은 같은 Presolve/Branch 경로를 보장하지 않는다. 전체 새 Beam 생성·반복 Wall은 NOT_RUN이며 기본 설정에 채택하지 않는다.

17. 새 FULL UB 개선은0이다. 양쪽 모두0.5398310226338695이며 실제 Native Capture의 Original FULL 계통·경로·SOC·PCS·Mode Replay가 PASS다. 기존 검증 Moving Incumbent는 보호하고 Registry 수정은0이다. PR221 Benchmark Start는 PR220 원시 벡터와 bit-identical하지 않으나 같은 목적과3-MOVE 경로를 보존하며 차이 최대6.384e-10인 연속 좌표도 수정 없이 각각 Replay했다.

18. 별도 실험용 Diversity Admission은 네 차량에 동일 Pool Budget을 적용하고STAY/검증 Incumbent를 고정하며 목적지·이동시각·Single/Multiple MOVE를 균형 있게 입장시킨다. 기존 Signed Multi-Critical P/Q·SOC·PCS·여행 서비스 손실·Rebound Score의 네 차량 결합을 사용한다. Fixture 회귀는 PASS이며 실제 새4×24 Signed Search와 동일 예산 Solver 비교는 NOT_RUN이다. 충분한 실제 충전소 탐색 또는 더 좋은 UB를 주장하지 않는다.

19. S1 연속 LP 진단과 정수 Oracle은 별개다. 최신 상태는S1_ROOT_FRACTIONALITY.json에 기록한다. 원래30초 S1 MIP는 Root가 중단되어 분수 Route/Mode 개수를 관측하지 못했다. 이번 실제 S1 LP는13.254초에 Optimal, 수치 목적0.6090630116056528이다. 원본 행 잔차4.894e-13 및 Bound 잔차0에서 분수 Arc4,307개/Mode192개, 복수 위치 점유187개 차량·슬롯, 동시 충방전192개 차량·슬롯을 실제 관측했다. 위치+이동중 점유 질량과 SOC Balance는 보존되지만, 분수 차량의 여러 노드 전력 운전은 정수 물리 실행이 아니다. 같은 S1 정수 가능 UB0.6412659669740282와의 차이0.03220295536837536을 정수 최적 Gap으로 부르지 않는다.

20. K48보다 높은 인증 Global LB는 얻지 못했다. 기존0.46498486997548166을 원래 동일 Case에서만 보존한다. PR227 Lagrangian/다기간 Route-SOC 무개선 이력을 보존했다. 새 Aggregate Mode Hull 후보는 정수 단일 위치와 Binary Mode에서ΣPch≤Pmax·Mode 및ΣPdis≤Pmax·(1−Mode)를 증명하며, 원래 Pmax300kW에서 역사적 실제4×24 Root109개 및 실제 S1 Root35개 강한 위반을 진단했다. 처음 사용한 약한600kW 진단97건도 수정 이력으로 보존하고 원래 Pmax라고 부르지 않는다. S1 원본960 Flow/2 Terminal/1,866 Connection/1,866 Mode 행의 정확한 계수와 DAG를 독립 검증한 후384 유효 Cut을 제한된 S1 LP에만 추가했다. 12.309초에 Optimal 목적0.6090630116727263, 증가6.707e-11로 수치 잡음이며 실질 개선0이다. 총 충방전이 모든 슬롯에서300kW 이하라 Mode만 다시 선택하면 모든 Cut을 만족하는 같은 목적의 새 LP Witness가 존재함을 모든 원본 행과 함께 확인했다. 저장 Raw·Route/P/Q/SOC는 수정하지 않았다. 분수 Mode의 현재 값 위반만으로 LB 개선이 따라오지 않는 원인을 규명했다. 이 Cut을 운영 모델에 채택하지 않으며4×24 강화 Global LB는 NOT_RUN이다.

21. 원본 제한 Pool ObjBound0.539831 및 압축 제한 ObjBound0.289400은 모두 Global LB가 아니다. S1 축소 Bound를4×24 Global LB로 이전하지 않는다. 원래 같은 Case의 Global Gap13.864737209%를 유지한다.

동결 가능: 검증 Incumbent 보존, 동일 Pool의 Integer/LP 삭제 증명, 정확한 Raw Lift/Native Readback/FULL Replay, Source/Case/Physical/Pool SHA 기반 오염 거부. 압축·Diversity·Mode Hull은 실험용 기본 비활성이다. 계산 성능·새 Beam UB·강화 Global LB·S1 정수 Oracle은 미검증 상태이며 May 캠페인 확대 근거로 쓰지 않는다.
