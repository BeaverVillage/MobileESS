# 고정 v3 AIDC 기하 독립 검토

이 문서는 **종전 고정 v3 AIDC 12곳**을 대상으로 한 검토이다. 이후 사용자가 AIDC 재선정을 허용한 결정과 구분하며, 이 증명으로 새 AIDC/STA 공동 재선정의 가능 여부를 단정하지 않는다. 기존 입력과 결과는 보존한다.

검토 결과는 PASS이다. 이는 기하 조건이 충족됐다는 뜻이 아니라, **종전 고정 12곳에 대한 불가능성 증명과 입력 대응이 독립적으로 확인됐다는 뜻**이다. 최소제곱 정합의 오차 또는 탐색 실패만으로 STOP을 결정하지 않았다. 원본 소수 좌표의 정확한 유리수 연산으로 동서와 남북 각각의 모순을 확인했다.

## 1. 검토 대상과 독립성

새 검토기 `ieee8500_v42/review_geometry.py`는 표준 라이브러리와 파일 SHA 함수만 사용한다. `geometry.py`, 과거 selector, Native 모델 및 OpenDSS를 import하거나 실행하지 않는다. 읽은 파일의 경로와 SHA256, 12곳 대응표, 66쌍 판정, 정확한 분수 증명은 `GEOMETRY_INDEPENDENT_REVIEW.json`에 저장했다. 검토 중 Native 호출과 OpenDSS 호출은 각각 0회이다.

다음을 대조했다.

- 복사된 v3 AIDC CSV, 원래 24곳 전기적 mapping CSV, 24 traffic anchor JSON이 원본 파일 및 `GEOMETRY_INPUT_SHA256.json`과 바이트 단위로 같다.
- AIDC01–12는 TN_01–12, 원 traffic service IDC01–12 및 model IDC_01–12와 연결된다. 서비스·노드 ID와 원본 longitude/latitude가 모두 같다.
- 12개 DSS 버스는 종전 고정 roster와 같고, CSV의 x/y가 원본 `source/Buscoords.dss` 소수 좌표와 정확히 같다.
- `RELATIVE_POSITION_AUDIT.csv`에는 전체 276쌍이 있고 AIDC–AIDC 66쌍은 빠짐·중복이 없다.
- `AIDC_66_DIRECTION_AUDIT.csv`의 각 양끝 AIDC/TN/DSS label, traffic 좌표, 원본 DSS 좌표, 공통 정합 좌표, 차이, 부호, 보존 여부, 예외 여부 및 정합 미승인 flag를 모두 다시 계산했다.

종전 12곳은 AIDC01 `l3234149`, 02 `e182733`, 03 `m1027055`, 04 `m1069411`, 05 `l2688693`, 06 `m1142814`, 07 `m1026690`, 08 `l3123452`, 09 `l2728247`, 10 `l2973833`, 11 `m1047763`, 12 `e192258`이다.

## 2. Traffic 좌표의 출처와 투영

원 `station_selection_v1/prepare_sta.py:7–17`은 48노드 CSV와 24서비스 CSV를 traffic node ID로 join하고, 경위도를 radian으로 바꾼 후 다음 식을 사용한다.

\[
x_i=6371.0088\cos(\overline{\phi}_{24})(\lambda_i-\overline{\lambda}_{24}),\qquad
y_i=6371.0088(\phi_i-\overline{\phi}_{24}).
\]

단위는 km이다. 원본 경위도에서 이 식을 재계산한 최대 차이는 receipt에 기록했으며 1e-8 km 미만이다. 원본 static reference CSV의 SHA도 `audit/melbourne_static_sources.json`에 기록된 hash와 같다. 이 검토는 보관된 로컬 사본을 검증했고 과거 WSL 원격 경로를 새로 읽지는 않았다.

과거 `audit/melbourne_12_anchors.json`과 24곳 JSON의 투영 x/y는 평균을 취하는 집합이 달라 수치가 다르다. 두 좌표계 사이에는 양의 x배율 및 평행이동, y평행이동만 있다. 원 경위도·ID를 대조하고 66쌍의 동서·남북 부호가 전부 같음을 확인했다. 따라서 이 평균 차이가 이번 부호 충돌의 원인이 아니다.

## 3. 허용 변환과 정확한 모순

동결된 허용 변환은 모든 24곳에 공통인 다음 proper similarity이다.

\[
F(g)=sR(\theta)g+t,\qquad s>0,\quad\det R=1.
\]

반사, 위치별 독립 변환, 비선형 왜곡을 허용하지 않는다. Traffic 축차이 및 근거리 판정의 기존 1 m 허용값을 바꾸지 않았다. 고정 66쌍에는 근거리 면제 쌍이 없다.

더 큰 변환 집합 `F(g)=Ag+t`의 각 출력축도 별도로 검토했다. 쌍 `(a,b)`에서 traffic 축차이의 부호를 `σ`, 원본 DSS 차이를 `g_b−g_a`라 하고 `v=σ(g_b−g_a)`라 하면, 방향 보존에는 해당 행벡터 `r`에 대해 `r·v>0`이 필요하다. 양끝의 평행이동은 상쇄된다.

각 축의 아래 세 벡터는 **모든 가중치가 양수**인 조합으로 정확히 0이 된다. 소수 반올림된 표시값을 증명에 사용하지 않고 원 DSS 소수 좌표를 분수로 바꾸어 교차곱으로 가중치를 재구성했다.

| 축 | 증명에 쓰인 쌍 | 정규화 가중치(표시 근사값) |
|---|---|---|
| 동서 | AIDC02–03, AIDC07–11, AIDC11–12 | 0.473931470826512, 0.468108560054286, 0.057959969119202 |
| 남북 | AIDC09–12, AIDC10–12, AIDC11–12 | 0.316803154448240, 0.614225106298878, 0.068971739252882 |

\[
\sum_i w_i v_i=(0,0),\quad w_i>0
\quad\Longrightarrow\quad
\sum_i w_i(r\cdot v_i)=r\cdot(0,0)=0.
\]

모든 `r·v_i>0`이면 왼쪽은 양수가 되어 모순이다. 동서·남북 모두 정확한 가중 벡터합은 `0/1, 0/1`이다. 따라서 어떤 상수 2×2 affine 행렬도 해당 고정 roster의 모든 방향을 보존하지 못하며, 그 부분집합인 공통 proper similarity도 불가능하다. 이는 수치 탐색의 수렴 여부와 무관하다.

생산 검토기의 binary64 가중치와 정확한 원본 소수 좌표 가중치의 최대 차이는 동서 4.05e-15, 남북 1.05e-13 수준이다. 이는 큰 원본 좌표를 부동소수로 뺀 영향이며, 독립 증명의 잔차나 방향 허용오차가 아니다. 정확한 분자·분모와 부호를 receipt에 보존했다.

이 증명은 임의의 비선형 warp를 검토하지 않는다. 물리적 실제 경위도의 불가능성을 주장하지도 않는다. 입력 DSS XY와 지정 traffic 좌표의 대응, 공통 선형 변환, 엄격한 축 부호 조건을 대상으로 한다.

## 4. 66쌍 결과와 좌표 권한

원본 XY 축 그대로의 비교는 동서 63/66, 남북 52/66, 합계 115/132 축에서 traffic 부호와 다르다. 거부된 공통 최소제곱 정합은 동서 2/66, 남북 15/66, 합계 17/132 축 및 17/66쌍에서 다르다. 이 정합을 승인된 좌표계나 새 위치 선택 결과로 사용하지 않았다.

`Buscoords.dss`의 CRS, 거리 단위와 compass 방향은 인증되지 않았다. 따라서 원본 XY의 x/y를 실제 동/북이라고 단정할 수 없다. 특히 원 `AddBusXY.py`는 저압 변압기 secondary를 primary에 `(5,0)`, load bus를 primary에 `(45,40)`을 더해 만든다. 원본 LV 도식 위치는 실제 도로·부지·연결점의 지리적 증거가 아니다. 이번 증명은 원본 입력 좌표에서의 명시된 수학적 계약에만 적용한다.

## 5. 과거 v3 PASS가 부호 충돌을 막지 못한 이유

원 `selection_v3_source_proximity/select_sites.py:44–62`의 hard gate는 normalized proper Procrustes `E_coord≤0.20`, normalized 66거리 `E_pair≤0.20`, two-nearest-neighbor retention≥0.50, 모든 electrical pair거리≥0.9129072401559803 Ω, 원 XY pair거리≥2221.532547954318 및 12개 고유 host이다. 원 `initialize():34–42`의 추가 guard는 root impedance 하위 5%를 제외하여 638개를 606개로 줄인다. 모든 쌍의 x/y 부호 보존 조건은 없다.

원 validation 결과 `E_coord=0.1996973435588948`, `E_pair=0.1293899223332357`, 이웃 보존 22/24는 당시 기준을 만족한다. 거리·정규화 형상·이웃 구조의 평균 오차를 제한해도 축별 개별 부호는 보장되지 않는다. 과거 PASS는 당시 형상 계약의 PASS이고, 새로 요구된 엄격한 66쌍 방향 계약의 인증이 아니다. 과거 알고리즘 오류나 과거 PASS 위조로 해석하지 않는다. AIDC와 STA의 독립 정합도 144개 교차 쌍 방향 보존을 보장하지 않는다.

## 6. 원 bare feeder AC 결과의 해석 범위

`ORIGINAL_FEEDER_REGRESSION.json`은 원 `Master-unbal`과 원 정적 load, 원 regulator/capacitor 설정을 사용한 저장된 실제 OpenDSS 결과이다. 이 검토는 그 파일을 읽었고 새 AC solve를 하지 않았다. AIDC/MESS overlay가 없고 정적 background BG=1.0이므로 **96시점 AIDC queue/facility/May profile을 포함한 완전한 V42 B0가 아니다**.

저장 결과는 control settling 및 수렴을 보고한다. 최소전압은 `sx2748781a.2`의 0.9114118054461826 pu이고, 원 목적함수 의미의 line `rho_max`는 `Line.tpx21459660c0`의 1.7542167831069122이다. 원 feeder만으로도 저압 부족전압과 line 과부하가 있다는 진단 근거가 되지만, 완전한 V42 B0 최종 실패율이나 새 scale의 검증으로 사용하지 않는다.

원 V42 목적함수는 oriented parent terminal의 원 non-neutral phase node 1/2/3 전류를 원 `Line.NormAmps`로 나눈 값이다. 저장된 별도 all-terminal 감사값 1.754216802561661은 terminal 2에서 발생한다. 두 정의를 같은 `min rho`로 섞지 않는다. 모든 terminal·conductor 및 neutral의 안전 감사는 별도 인증 항목이다. 자세한 함수·파일 SHA는 `SOURCE_AUTHORITY.md` 및 `OBJECTIVE_SCOPE_AUDIT.json`에 있다.

## 7. 결정

종전 고정 AIDC roster에 대해 방향 보존이 불가능하다는 STOP은 독립적으로 타당하다. 이후 사용자가 허용한 **새 AIDC 12곳과 STA 12곳 공동 재선정**은 새 입력·새 증명·새 pair audit으로 평가해야 한다. 이 문서와 receipt는 과거 고정 roster의 provenance로 보존하며 새 후보를 미리 배제하지 않는다. LV 물리 포트와 실제 위치 증거, 전기적 연결·열정격·보호·접근·시점 검증, 6 MESS 원 모델 인증 및 완전한 V42 B0는 별도 미완료 조건이다.

재현 명령: `python -B -m ieee8500_v42.review_geometry`. 이 검토의 결과는 `GEOMETRY_INDEPENDENT_REVIEW.json`이다.
