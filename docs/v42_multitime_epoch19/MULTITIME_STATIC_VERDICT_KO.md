# Multi-Time 정적 판정: MULTITIME_LB_UNPROVEN

후보 한 종류 **Multi-Time Route–SOC–Grid Energy Deliverability Inequality**만 검토했다. 원본 정수 운전계획에 유효하지만 **현재 분수 LP 제약이 이미 함의**하므로 기각한다. 비중복성은 성립하지 않는다. 현재 완료된 Root LP 최적점·유효한 분수 Primal Point가 없어 실제 위반, Root 최적 LB 상승 및 MILP Gap 개선은 증명하지 못했다. `LB_IMPROVEMENT_UNPROVEN` / **`MULTITIME_LB_UNPROVEN`**으로 조기 종료했다. 이 판정은 검토한 비음수 에너지가격의 가산 support 후보에 한정한다. 다른 구조의 모든 Multi-Time 강화를 기각하는 일반 정리는 아니다. 추가 행·열·Binary·NNZ는 모두 **0**이고 모든 Native 호출·Runtime·Full 모델 재생성·파라미터 탐색은 **0**이다.

## 현재 선로와 시간구간

Source18r B2 May01의 실제 저장 Forecast/FULL 계수로 **branch3 `line.sw1::A`, 슬롯72–79([72,80)), 2시간**을 선정했다. 현재 고정 AIDC 입력에서 선로 face peak는 **0.659762706994**, 보수적4대 MESS 외접 제어범위를 적용한 구간 평균 필요 pressure는 **0.365035293772**다. 이것은 현재 계수로 정한 정적 검토 대상이며 LP 최적해의 critical line이라는 증명은 아니다.

새 U4의 저장 점·SHA 및 원본 FULL/96슬롯 물리 replay를 확인하고 같은 Dense80개 보존 face를 직접 평가했다. 선택 구간 실제 U4 peak **0.650839453452**(슬롯76), 슬롯별 peak 평균 **0.637805597992**, U4 전체 rho **0.676053450465**다. 이 정수 가능점은 LP 분수점·LP 위반 증거가 아니다. 과거 다른 Source의 LP/dual/점/시작값은 읽지 않았다.

FULL의 선택 구간128face/480NNZ는 C3A/Dense에서80face/296NNZ로 줄어도 실제 보존 계수가 같다. 정확한 보조변수 역대입 후 thermal relief의 raw control 지지는2,304NNZ다. 32개 구간 에너지 행에는19,264NNZ(이동에너지17,664회)가 있고, 전체96슬롯 이동 항은198,986개다. 이들을 새 조밀 행으로 복사하지 않았다.

## 후보와 일반 증명

실제 저장 face의 민감도를 정확 유리수로 전개하고 선택 구간의 가중 relief를 R로 둔다. 구간 밖 thermal weight는0으로 두되 충전·이동·종단SOC의 효과는 전체96슬롯에 포함한다. 차량별 전체 에너지 E는 다음과 같다.

`E = sum_t(d*Pdis - c*Pch) + sum_route(travel_kWh * route_flow) = SOC[0] - SOC[96] = 0`.

c,d는 새로 효율을 곱해 반올림하지 않고 원본 행에 저장된0.25시간/효율 계수다. 실제 c=4278419646001971/18014398509481984, d=4740631186705785/18014398509481984이며 d>=c다. 초기·종단SOC는760이다. 실제 이동에너지는 출발 다음 SOC시점에 원래대로 차감되고, 이동 중에는 원본이 허용하지 않은 충·방전·Q를 추가하지 않는다. 종단 위치는 원본에서 허용된 모든 site이며 원점 복귀를 강제하지 않는다.

비음수 정확 에너지 가격 lambda에 대해 stay별 h는 저장 PCS16·connected power bounds·Mode가 허용하는 `thermal relief - lambda*(d*Pdis-c*Pch)`의 상계다. travel reward는 `-lambda*travel_kWh`다. 모든 원본96슬롯 경로의 가산 reward 최대값 H를 Bellman 상계로 두면 후보는 **`R <= sum_vehicle H`**다. 원본 선로 face와 결합하면 rho에 대한 하나의 deliverability 하한으로 표현할 수 있다. 모든 site에서 충전 후 복귀·Q 공급/흡수·구간 밖 Rebound 충전을 허용한다. 단순 SOC 합산만 새 제약으로 주장하지 않았다.

독립 증명은 정수 경로보다 더 넓은 **원본 분수 LP 전체**에 이 식이 성립함을 보였다. 각 stay에서 공통 충·방전량 k=min(Pch,Pdis)를 취소하면 netP/Q와 PCS조건을 보존하고 priced objective가 `lambda*(d-c)*k`만큼 증가한다. 따라서 이 방향에서는 동시충방전을 허용한 local fractional support도 integer-mode support보다 커질 수 없다. connected bounds/PCS16은 stayflow에 동차이므로 각 제어 reward는 h*stayflow 이하이다. 모든 비음수 fractional unit DAG flow는 경로 분해 또는 `reward_arc <= H(tail)-H(head)`의 telescoping으로 경로 상계를 만족한다. 마지막으로 원래96개 SOC 등식·종단 조건이 에너지 합을0으로 만든다. 즉 **기존 Flow + PCS/connected + SOC가 이미 후보를 함의**한다. Convex Hull의 분수점도 제거하지 않는다.

현재 저장 계수와 증명 전제 **3,186개 PASS**(768개 정확 C=-D folding,16PCS faces,32구간 SOC행,8SOC끝점,전체384에너지/9216flow bridge 등)다. 일반 정확 유리수 fixture는472검사와4변조 거부 PASS, 작은5경로/51,301유한 제어계획/4,081종단에너지 가능계획 및 분수 혼합을 확인했다. 이는96슬롯 일반 증명을 대체하지 않는다. 구간 밖 충전 누락·음수lambda의 수치 반례를 확인했고, d<c로 뒤집은 저장 에너지 계수는 증명 전제 위반으로 거부했다. 실제96슬롯 모든 경로 조합을 생성하거나 Full DP 값을 계산할 필요는 없어 생성하지 않았다.

## 과거 연구와 관계 및 비용

PR109~111/137/167/169/182/185~187의 정확 head·코드·결과를 먼저 감사했다. local Mode/PCS 강화를 다시 만드는 대신 실제 현재 thermal 방향과 전체96슬롯 이동·Rebound를 함께 검사했다. 그러나 DAG marginal/에너지 가격 상계의 LP 중복성이 드러나 PR111/137의 비물질 결과와 일치했다. PR167 local hull, PR169 대규모 조합, PR182 거대EF는 복제하지 않았다. PR185~187의651개 archived arrival-SOC 행도 추가하지 않았다. 과거 LB 숫자를 현재 실적으로 사용하지 않았다.

후보를 scalar rho 하한으로 사영하면 이론상 행1/NNZ1/열0/Binary0이 가능하지만 이미 LP가 함의하므로 **실제 생성·삽입0**이다. 구간/전체 에너지·route항을 새 조밀 행으로 반복해 규모를 키우지 않았다. 유효성만으로 LB나 Gap 효과를 PASS하지 않았다. Source18r ObjBound0.289400491085는 **미완료 Root의 solver bound**이며 완료 LP 최적값이 아니다.

## 시간·Source·증거

정적 판정은 선행 동결 commit 시각(14:48:44 UTC)에서 원본 closure JSON의 관측 LastWriteTimeUtc(15:02:32.334891 UTC)까지의 보수적 시간상한 **828.33초(13.81분)** 내에 끝났다. 이 상한은 worktree/준비시간을 포함하며 전체 조사 wall의 정확한 계측값은 아니다. 30분 목표를 넘겨 연구를 확대하지 않았다. 선택 CSR 조사 wall24.668초, 일반 fixture wall1.894초는 CPU/정적 wall이며 **Native Runtime은0초**다.

기준 Draft PR207 동결 commit: `497609b46faa14ea7e32a9483a333ab32fd264ef`.
Model Source SHA: `146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8`.
Case SHA: `34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292`.
정적 분석 Source SHA: `ae93dd39409e681a4a0bc71ef87a975855665b9fcdebf260e5e9bd087c19b69a`. 계산 방법과 모든 분석 코드·원본 파일 SHA는 `evidence/MULTITIME_STATIC_EVIDENCE_INDEX.json`, 각 current/history/fixture receipt에 있다.



| 원본 파일 |SHA256|
|---|---|
|FULL_A.npz|81ae1a542115e192051e250b627c61bfcea94e62f43a815b91bc11ef54d9ebb4|
|FULL_DATA.npz|8df044d563d4e6c744e3528ed594bbce33d8302fabf8ea2aacfbb7357a76198f|
|COEFFICIENTS.npz|b3370e37a375d6b358ba0695feeb5bad26da4d043447669f5d2d3024ad20eba8|
|NATIVE_INPUT.json|00c6045617e0da3c58c72d4ab9ab64ef9657c1a8f28c49ba187b468e7dddd4e0|
|B2_FIXED_AIDC.json|c96faf6a3a1264d55ef7c6cf1e783f0ce9c355a9ad63e14501ce1ab38aa3936c|
|FRESH_U4/RAW_00.npz|afd2399ba4b2ef83ab92ae2c76c5790afa435651749e1477f8832e7a089bb367|
|FRESH_U4/RAW_00.REPLAY.json|af9ae81121190099aa67eaadf6d51a13415877244526c19764f7ebc7f118f030|

Source18r·PR207·기존 Native ledger·Source17·원본 입력은 변경하지 않았다. StageBudget/A1/A2/NativeStopRequested/공용 중단 정책도 변경하지 않았다. Threads1/Worker 수를 유지하고 새 Heavy Solver·공식 캠페인 재시작 없이, 다음 단계에서 기존 Source18r 로그 기반 Barrier 병목만 분석한다. 캠페인 HOLD를 유지한다.
