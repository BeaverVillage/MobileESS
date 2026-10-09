# 135° 공동 배치의 원본 기반 독립 방향 검토

저장된 새 공동 배치는 **원 24 traffic ID, 24개 고유 원 MV 버스, 276쌍·552개 비면제 축 부호 조건을 만족한다.** 원 경위도에서 traffic 투영, 원 DSS XY에서 단일 변환 좌표, pair CSV의 수치값을 독립 재계산한 최대 차이는 모두 0.0이다. 요청된 1e-12 수치 재현 한계 이내이다. 그러나 **거리·형상에 충실한 배치 또는 최종 물리적 위치 승인으로 판정하지 않는다.**

새 `ieee8500_v42/review_joint_geometry.py`는 geometry/search producer와 해당 `verify_witness` helper를 import하거나 실행하지 않는다. 독립 MV source validator와 파일 SHA 함수만 공유한다. 저장된 witness를 원 자료와 직접 비교했으며 선택 탐색, Native, OpenDSS 호출은 모두 0회이다. receipt는 `JOINT_GEOMETRY_INDEPENDENT_REVIEW.json`이다.

## 원본 좌표·ID·후보 자격

원 `v01_reduced48_nodes_v2.csv`와 `final_service_nodes_24.csv`를 traffic node ID로 join하고 원 source receipt SHA를 검증했다. 원 24곳의 longitude/latitude에서 원 24평균 equiangular 식을 직접 계산했다. AIDC01–12와 STA01–12 및 각 TN ID가 변경되지 않았고, 재계산한 traffic x/y와 mapping CSV의 차이는 0.0 km이다.

`JOINT_SERVICE_MAPPING.csv`의 24개 `source_x/source_y`를 원 `source/Buscoords.dss` 소수 문자열에서 만든 정확한 유리수와 대조했다. 현재 사본의 Buscoords SHA도 원본과 같다. 24개 service ID와 버스는 각각 모두 고유하다. 모든 버스는 원 606개 guarded MV 후보에 속한다. 독립 MV 검증기가 실제 원 inventory의 conductor identity ABC 경로, 12.47 kV, 원 source/substation/regulator 제외, 원 Reactor를 포함한 source 연결성 및 원 q05 guard를 재확인했다. 원 638개 root 거리 재계산 차이는 0.0 Ω이고 선택 24개 mapping의 root 거리도 정확히 같다.

## 단일 proper 변환과 엄격한 방향 증명

전체 24곳에 같은 행렬과 같은 평행이동을 사용한다.

\[
F(g)=\begin{bmatrix}u&-v\\v&u\end{bmatrix}g+t,
\quad u=-0.0008232807688911385,\quad v=0.0008232807688911386.
\]

행렬은 동일한 두 축 배율, 직교 열벡터 및 양의 determinant `1.3555824488519687e-6`를 갖는다. 양의 균일 scale은 `0.0011642948290067979`이고 기록된 회전은 135°이다. Scale·source center·target center 및 공통 translation을 preregistration과 대조했다. 지점별 회전·배율·reflection·이동은 없다. 원 XY에서 각 공통 좌표를 재계산한 최대 차이는 0.0 km이다.

276 canonical pair의 552 축을 부동소수 결과만으로 승인하지 않았다. 원 DSS 소수 좌표 차이 `(dx,dy)`와 저장된 `u,v` 소수 literal을 분수로 바꾸어 각 출력 축의 부호를 정확히 계산했다. 별도로 이상적인 135° 회전에서 양의 `scale/sqrt(2)`를 제외한 두 식 `−(dx+dy)`, `dx−dy`의 정확한 유리수 부호도 검사했다. 두 독립 수학적 계산과 CSV의 common-frame 부호가 원 traffic 부호와 모두 같다.

AIDC–AIDC 66쌍, STA–STA 66쌍, 교차 144쌍을 빠짐·중복 없이 확인했다. 원 1 m axis/near-pair 허용값을 유지하며 이번 552개는 모두 면제되지 않는 엄격한 부호 조건이다. Pair의 양끝 traffic ID와 버스 label, x/y delta, expected/actual sign, pass flag, source·traffic·common-frame 거리를 직접 대조했다. 저장된 pair 수치의 최대 재계산 차이는 0.0이다. 모든 pair별 정확한 부호 결과는 receipt에 있다.

## 방향 PASS의 범위와 형상 감사

이번 witness는 최신 범위의 **엄격한 모든 방향 조건**을 만족한다. 절대 위치 오차는 24곳 RMS 9.91407421717946 km, 평균 9.410440355917315 km, 최대 14.020839602316915 km이다. km는 공통 비교 프레임 단위이며 원 DSS의 CRS·물리 거리·compass 인증이 아니다.

과거 v3 AIDC 12곳에 사용했던 normalized proper-Procrustes `E_coord`와 normalized pair-distance `E_pair`도 독립 계산했다. 현재 AIDC 12곳은 `E_coord=0.6515576850396261`, `E_pair=0.4507495171263371`로 각각 **과거 0.20 기준을 만족하지 않는다.** 원 electrical/XY dispersion 기준의 pair별 pass/fail도 receipt에 보존한다. 이들은 최신 hard 방향 조건과 구분된 역사적 설계 감사값이다. 따라서 이번 결과를 과거 형상 기준까지 통과한 배치, 원 traffic 거리 복제 또는 거리 충실한 매핑이라고 표현하면 안 된다.

최신 공동 선택의 hard guard와 역사적 dispersion 감사 범위는 새 preregistration에 기록돼 있다. 이 검토는 범위를 조용히 바꾸거나 역사적 fail을 physical safety limit 완화로 해석하지 않는다. 최적성·전 계통 성능·원 Native 모델 solve 결과도 주장하지 않는다.

## 미승인 물리 조건과 결정

AIDC 12곳은 MV 3상 후보, STA 12곳은 MV fallback 후보이다. 선택된 LV STA는 0곳이다. 모든 mapping row는 `physical_port_protection_access_gate=UNRESOLVED`, `is_final_selection=False`이고 package도 `physical_ports_qualified=False`, `production_configuration_frozen=False`이다. 이 표기가 타당함을 확인했다.

결론은 **새 135° 공동 배치의 원 source 자격과 방향 witness 검증 PASS**이다. 종전 고정 AIDC의 불가능성은 새 후보 집합에 적용하지 않는다. 이번 기하 PASS는 장비·실제 접속·보호·접근·연결시간·6대 이동·최종 AC/Native 검증을 완료하지 않으며 최종 freeze가 아니다.

재현: `python -B -m ieee8500_v42.review_joint_geometry`. 원 배치·preregistration·source 파일을 수정하거나 선택 탐색을 재실행하지 않는다.
