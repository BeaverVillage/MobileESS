# 네 슬롯 국소 궤적 hull의 집합과 증명

원본의 `arc` 순서, 도달 가능 시간 DAG, 실제 저장된 PCS16 면과 energy_balance 계수를 읽는다. 출발/도착/연결 시간이 다른 route를 합치거나 travel energy를 바꾸지 않는다. 69를 가로지르는 첫 arc에서 시작해 73 이상에 도달하는 마지막 arc까지 경로를 모두 열거한다. 경계에서 이미 이동 중인 route와 73 이후에 연결되는 route도 빠짐없이 포함한다. 이동 에너지는 원본대로 **출발 슬롯에 한 번** 차감한다. 69 이전에 출발한 에너지는 이전 구간의 원본 모델/인터페이스에 속하며 이 창에서 다시 차감하지 않는다.

이 국소 정수 집합은 자유 경계 SOC69/SOC73와 원래 SOC bounds를 가진 네 슬롯의 물리 disjunction이다. 전체 96슬롯 이전/이후 SOC·grid 확장 가능성까지 열거한 global projection은 아니다. 원래 C3A의 전체 이전/이후 제약은 강화 LP에서 모두 남긴다. 따라서 이 국소 집합의 exact hull이 모든 global integer projection을 포함한다는 타당성과, 이것이 완전한 global hull이라는 주장은 구별한다. 관측 LP의 SOC값을 경계에 고정하지 않는다.

각 mobility 경로에서 연결된 슬롯의 mode 비트를 전부 열거한다. 미연결 슬롯은 Pch=Pdis=Q=0이며 mode 비트가 SOC·flow와 독립인 이진 cube다. 이 cube를 [0,1]로 정확히 convexify해 묶어도 어떤 정수 mode 상태도 사라지지 않는다. mobility 경로 149,817개 × 16 mode word = 정수 궤적 2,397,072개이며, cube factoring 뒤 disjunction은 232,837개다.

한 disjunct에는 경로·연결 site·mode가 고정된다. private E는 경계와 모든 P/SOC 변화 사건에 두며 무변화 transit 사이의 E는 alias다. 연결 슬롯의 private p≥0, Q는 실제 저장 PCS16의 charge 또는 discharge half-polytope에 속한다. 상태 변화는 원본 binary64의 정확한 유리수 계수로 `E_after-E_before-alpha*p=0` 또는 `E_after-E_before+route_energy=0`이다. 모든 사건 E의 [440,1080] bounds를 적용한다. 이동 비용 합이 capacity 폭 640 이하인지 유리수로 확인했으므로 p=Q=0, 충분한 자유 E69가 모든 disjunct의 비어 있지 않은 증인이다.

각 disjunct d에 λ_d≥0와 동차화한 private E/p/Q를 만들고 Σλ=1로 둔다. SOC bounds는 440λ≤E≤1080λ, PCS는 a*p+b*Q≤cap*λ, power는 p≤300λ이며 변화식도 동차화한다. λ>0이면 나누어 원래 disjunct의 점을 얻는다. λ=0이면 E=p=Q=0임을 유계 SOC/half-PCS에서 알 수 있어 recession 오염이 없다. 따라서 합계 좌표가 정확히 그 유한 합집합의 convex hull이다. 반대로 임의의 convex combination은 λ와 scaled private 좌표로 확장된다.

arc/Pch/Pdis/Q/mode/SOC69..73 전체를 원본 C3A 좌표의 저장된 inverse certificate로 연결한다. 원래 행 삭제는 없다. 새 private 변수의 finite box는 λ≤1과 원래 물리 bound에 의해 이미 함의되며 exact bounded-Lagrangian 인증에 쓰인다.

생성기는 Fraction polygon clipping으로 원본 half-PCS의 활성 면을 고른다. `verify_hull.py`는 생성기나 DFS를 import하지 않는다. backward DP 경로 수와 개별 경로의 유효성·유일성을 결합해 열거의 완전성을 확인하고, plane pair 교점 열거로 원본 16면과 retained 면의 꼭짓점 집합이 정확히 같음을 검사한다. 모든 native sparse row/column/bound 및 SOC/flow/PQ 연결을 원본 권위에서 다시 구성한다. 실제 저장 계수는 모두 binary64로 정확히 표현 가능하며 반올림해 hull을 바꾸지 않는다. semantic mutation을 거부하고 파일 해시는 그대로인지 확인한다.

저장 PR167 점의 hull 밖 여부는 native infeasibility 판정만으로 증명하지 않는다. `MESS04_69_72_COMMON_MODE_SEPARATION.json`의 exact rational 비음수 row 조합은 슬롯71에서 방전-mode 질량을 0.2982020917827489 초과 요구함을 증명한다. 이 separator는 네 슬롯 모든 integer 경로에 유효하지만 한 슬롯에서도 성립한다. 따라서 temporal SOC 불가능성이나 네 슬롯 길이의 필요성을 증명했다고 표현하지 않는다.

하한 인증은 원래 행 sense에 맞도록 저장 dual의 부호를 잘라 `r=c-Aᵀπ`를 exact dyadic 정수로 계산한다. `cᵀx+c0≥πᵀrhs+c0+rᵀx`는 모든 feasible point에 유효하다. 기존 인증은 각 변수의 finite box에서 `rᵀx`를 최소화한다. 별도 `homogeneous_bound_certificate.py`는 private E/p/Q의 perspective bounds와 unit별 λ simplex를 그대로 인증 domain에 사용한다. disjunct k의 residual 비용은 `rλ+Σ_E min(440rE,1080rE)+Σ_p min(0,300rp)−Σ_Q400|rQ|`다. transit u는 `0≤u≤Σ_offλ`이므로 음수 ru가 있는 경우 해당 off disjunct 비용에 `min(0,ru)`를 더한다. λ 합1에서 block의 최소 비용은 이 disjunct 비용 중 최소값이다. 원래 C3A 변수는 기존 finite box correction을 한 번만 더한다.

이 인증 최소화에서는 SOC 변화식·PCS 등 일부 coupling을 생략해 domain을 넓힌다. 따라서 보수적인 하한이며 실제 모델에서 행이나 physics를 삭제한 것이 아니다. native optimize나 별도 LP를 호출하지 않는다. exact components의 유리수 합과 마지막 float의 아래 방향 rounding을 검증하고, 사용한 dual 배열 및 hull matrix/data/verifier SHA를 저장한다. 이 인증이 이전 LB보다 약하면 기존 valid LB를 유지한다.
