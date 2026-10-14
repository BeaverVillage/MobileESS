# Multi-period Route–SOC Support 포함관계 증명

차량별 FULL 사영을 포함하는 전체96-slot 정수 물리 X_m을 사용한다. 중요한 창 W의 원본 signed thermal response로 S_W(x_m)=Σ_{t∈W} c_tᵀy_t를 만들고, X_m 전체에서 max S_W를 푼다. 시간창 밖 물리, 이동 ETA/energy, 모든 SOC 및 terminal, PCS, mode, 접속, charging rebound 경로도 그대로 남는다. 차를 부분 ESS로 분할하거나 경로를 제한하지 않는다.

최대화의 Numerical global upper bound β와 E_max=Σmax((c−ĉ)_j l_j,(c−ĉ)_j u_j)를 exact 계산하면 U=β+E_max≥max_Xm S_W이다. 따라서 임의 FULL integer projection은 S_W≤U를 만족한다. Incumbent maximizing Objective는 상한으로 쓰지 않는다. Solver B&B numerical contract는 exact 정수 trace와 구분한다.

원본→Compact alias x=offset+Tz를 정확한 Fraction으로 대입한다. ĉ_cut−c_cut의 원래 proved Compact box support upper error를 RHS에 더하고 binary64 RHS를 +∞ 방향으로 반올림한다. 따라서 native cut은 원래 유효 부등식의 바깥 relaxation이다. 모든 K48 행/목적/Bounds를 unchanged prefix로 두고 이 cut만 추가하면 FULL integer projection⊆strengthened relaxation⊆K48 relaxation이다. Integer support가 source의 어떤 FULL 해라도 제거하면 기각한다.

현재 Root는 PR214 BASE 원시 점을 변조 없이 Original 물리 좌표로 복원했다. 응답 helper 값 전부를 저장한 FULL 전력 가능해라고 주장하지 않는다. ORIGINAL_ROOT_POINT는 mapped_columns의 물리/rho 값만 권위이며 다른 helper 좌표는 미복원0이다. Window29–32와27–34를 critical dual31/line.l10 phaseA 및 signed contribution/mode/route/SOC 패턴으로 선정했다. 실제 important support solve 두 개만 실행했고, 일반 단일-slot SOC 행을 복제하지 않았다.

두 인증 상한은 실제 Root support보다 컸다. 따라서 실제 위반 cut0, 채택 cut0, strengthened model/LP NOT_RUN이다. 잠재 포함관계 정리와 실제 강화 효과를 구분하며 신규 cut 또는 Global LB를 발명하지 않는다. 다른 방향/시간창의 hull 효과는 미측정이다.

PR222의 등록된 검증 Moving incumbent 전부(1개)를 실제 current FULL validator로 재검증하고 각 support inequality에 exact 대입했다. 이 witness 검사는 보편적 정수 유효성 증명의 대체가 아니다. 작은4-slot fixture는 두 ETA2 route와16mode pattern, 합32개의 정수 분기를 전수 열거하고 각 연속 power/SOC polytope를 SciPy LP로 검사했다. 각 route는 원래 형태의 flow/connection/mode/energy/terminal physics를 갖는다. Universal gross-power upper4는 한 차량 경로와 mode의 포함관계로 증명되며 LP mixture39/8가 위반함을 exact 확인했다. Fixture는 actual May01 cut 효과나 scientific constants 변경이 아니다.
