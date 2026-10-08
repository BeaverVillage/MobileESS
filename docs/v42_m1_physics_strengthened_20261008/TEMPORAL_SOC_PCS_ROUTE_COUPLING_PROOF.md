# 전체 시간 물리 결합

4대 MESS의 96-slot FULL energy 384행을 C3A energy 행에 exact dyadic arithmetic으로 전달해 계수·RHS·senses 일치를 검증했다. 실제 dt=0.25시간, eta=0.95, Pmax=300 kW, PCS=400 kVA, SOC=440..1,080 kWh, initial=terminal=760 kWh다. 원래 route arc의 energy를 사용하고 PCS 16-face·connected Pch/Pdis·mode·P/Q·grid 행을 모두 유지한다.

이동 arc a=(depart, connect, e)의 f=1이면 원래 DAG의 유일 경로는 이동 구간의 site vertices를 건너뛴다. 원래 connection/PCS 행으로 해당 구간 Pch=Pdis=Q=0이다. 원래 energy 행을 합하면 Econnect−Edepart+e=0이다. f=0일 때도 endpoint bounds를 만족한다. D=Econnect−Edepart+e, U=max(0,uconnect−ldepart+e), L=min(0,lconnect−udepart+e)라 두면 D≤U(1−f), D≥L(1−f)가 정수 일정에서 유효하다. 또한 Edepart≥ldepart+max(0,lconnect+e−ldepart)f, Econnect≤uconnect−max(0,uconnect−udepart+e)f다.

시간별 local-hull EF 복제 대신 모든 실제 travel interval과 전체 96-slot 경로에 대한 원래 변수의 제약을 사용한다. 이번에 실제 위반한 651행은 모두 arrival-SOC reachability다. 넓은 후보 검토를 완전한 trajectory hull이라고 주장하지 않는다. ROOT의 f 값을 정수로 cast하지 않는다. 추가 제약은 정수 projection에 유효하며 분수 f를 배제할 수 있다.

IEEE 계수 전달 오차 delta_j에 대해 RHS를 Σ max(delta_j*l_j,delta_j*u_j)만큼 outward 증가시킨다. 전체 original finite box에서 전달 행이 exact 행보다 강해지지 않음을 검증했다. 독립 verifier는 원래 arc·endpoint bounds로 651행을 재구성하고 잘못된 travel energy와 안전하지 않은 RHS 변조를 거부했다. 기존 witness 20개와 최선 UB를 제거하지 않았다.
