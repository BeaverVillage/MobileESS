기존 M0의 registered 실행은 그대로 기다린다. 다음 조건이 모두 충족된 경우에만 수치 실패 handoff를 한다: native production이 60분 정체 기준으로 정상 종료하고, M0 root에 OPTIMAL receipt가 없으며, LP가 7200초 이상 경과하고, 마지막 10개 simplex 기록 모두 Primal Inf > 1e6 및 objective > 원본 rho 상한 1이다.

그때 기존 M0의 원본 로그·in-flight OPEN checkpoint·PID/create_time/명령/cwd를 보존한 뒤 확인된 해당 프로세스만 종료한다. 최종 native status는 알 수 없으므로 operator-aborted로 기록한다. 이 종료를 LP infeasibility, OPTIMAL 또는 native INTERRUPTED로 간주하지 않는다. 모든 도메인과 기존 유효 LB/UB가 유지된다.

프로세스가 종료된 뒤에만 같은 root 도메인을 등록된 Method=1 recovery controller로 인계한다. 중복 동시 root solve와 native tree resume는 없다. 새 attempt의 모델/목적함수는 원본 그대로이고, OPTIMAL LP와 독립 exact LB 인증서가 있어야만 그 node LB를 수용한다. nonoptimal LP가 제공하는 실제 simplex basis는 다음 LP의 warm start로만 쓸 수 있다.
