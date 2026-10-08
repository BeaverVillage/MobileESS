# May12 P1-only 최종 검토

최종 판정: **MAY12_P1_ONLY_ACCEPTED**. P1-only accepted=True. 기존 4목적 A1_ACCEPTED는 변경하지 않았다. P2와 downstream은 실행하지 않았다.

이전 실행은 Phi=0 이후 P1과 130개 클래스 가격화까지 완료됐다. 실패는 P1 점을 새 elastic master에 연결하면서 80개 artificial weight 차이를 거부한 Python witness 검증기였다. 실제 저장 데이터 회귀는 수정 전 실패했고 수정 후 통과했다. 새 P1에서는 artificial-free original point 포함성을 검증한다. 양수 Phi의 frozen-weight 규칙과 scientific tolerance는 유지했다.

Phase-I trajectory: 0.03623444192091598 → 0.016419620449477194 → 0.0046485901268879595 → 0. 기존 활성화 round3, STAY96/migration96. Original dyadic row replay 및 original Planning grid replay PASS=True; full130 zero-dual pricing PASS. Raw native Phi=0과 재구성 artificial Phi(약6.44e-13)를 구분했다. 신규 Phase-I native solve0회. 이 인증은 연속 Phase-I feasibility이며 정수 schedule 인증은 P1 결과에 따로 기록한다.

P1 restricted LP는 0.6607295534700348 → 0.6588875397405124로 감소했다. S0와 S1은 각130개 full pricing을 완료했다. STAY208,957개와 migration50,756,904개를 포함하는 원본 후보 영역의 완전 oracle를 인증했다. Global LP LB는 S0의0.5704134348993862 → S1의0.6588875395606518로 개선됐다. 최종 exact LB=5934731355288829/9007199254740992, validated integer UB=742301704257481/1125899906842624 (0.6592963546281192), global gap=0.0006200778520881811 (0.0620077852%). 음수 블록129개(STAY 포함129/Migration 포함38)는 concrete column 개수가 아니다. 한 번의 P1 support graph 활성화로 S1을 만들었고 exact original 3,184,901행/1,141,597열 inclusion에서 목적값 동일성을 검증했다. S1 pricing은130/130이고 모든minimum-RC lower bound는0, negative block0개이며 P1 전체 영역 pricing closure PASS=True. Restricted ObjBound를 global bound로 사용하지 않았다. 원본 모든 global rows와 130개 full STAY/migration oracle의 finite-bound exact certificate/roundoff transport를 사용했다.

Original continuous Phase-I 및 P1 integer physical replay PASS=True. 원본1,782개 job의 GPU/rack/gang/WAN/서비스/carryout/Runtime/deadline/CC4 및 전압/thermal/transformer 제약 검증을 통과했다. 저장된 원본 정수 모델 전체3,184,901행/1,141,597열을 별도로 유리수 재생했고 scientific1e-6 tolerance 내 PASS, integrality residual0, 인공변수0이었다. Schedule metrics={'migration_count': 0, 'shift_magnitude': 68003, 'prestart_relocation': 1237}는 P2 후속 목적을 최적화하지 않고 평가한 값이다. Migration count0은 이번 해의 결과이며 migration 변수를0으로 고정하지 않았다. P1-only Freeze와 acceptance는 PASS, 기존 A1_ACCEPTED는 false다.

Native integer status는11(INTERRUPTED)이며 원본 물리 검증과 독립 global gap 목표가 충족돼 callback이 종료한 것이다. Solver의 완전 OPTIMAL 상태를 주장하지 않는다. Integer solve173.380000s / Work142.950591, node1, native MIPGap0.062007758%다. 인증에는 restricted native bound 대신 full-domain exact LB와 실제 integer UB를 사용했다. 종료 사유는 RAM이나 예산 소진이 아니다.

신규 native 261회, Runtime=208.870002s/3600s, Work=180.850507. 기존 native285회/233.892997s/Work327.445620은 그대로 보존했다. 신규 native/build/pricing/검증을 포함한 run wall=4009.185s. 복구 audit 이후 task wall=10458.223s, practical60분 기준=False. 모델 build/검증은 native예산과 구분했으며 실제 per-call Runtime/Work/model sizes/factor-memory/presolve는 RESOURCE_AND_RUNTIME_AUDIT.json과 native 원시 로그에 있다. RAM limits 및 RAM-triggered stops는 없다. Threads1, sequential native. 과거 작업의 예산은 수정하지 않았다.

다른 세 날짜: May17은 기존 four-objective A1 및 practical60분 accepted. May19은 기존 scientific A1 accepted이나 과거 certificate 재사용이어서 fresh end-to-end practicality 인증은 없다. May10은 PR184 고정 개선실험 후에도 UB60/globalLB2로 INCONCLUSIVE다. 그 결과와 PR184 HEAD1444d1614258be3e6ff24c56dfc078d69e8ced9a는 보존했다.

성능 측정과 병목: PERFORMANCE_COMPARISON.csv는 과거와 이번의 실제 측정 범위를 구분한다. 이번 복구는 historical solve 재사용 및 batch ledger refresh 동치성을 채택했다. 제한된 단일 native 설정을 사용했으며 broad sweep이나 automatic follow-up은 없다. P1 LP/master/pricing/정수 단계별 소요시간은 P1_TRAJECTORY.json과 NATIVE_CALLS에 기록된다. 실제 병목은 이 비용표로 판단하며 과거 PR164의 다른 모델 병목을 이번 수치에 전용하지 않는다.

실제 S0 master: 754,043 rows / 71,377 cols / 13,356,317nnz, presolved19,509/32,106/207,709, factor0.03GB. 실제 S1 master: 915,801 rows / 116,985 cols / 13,738,297nnz, presolved56,808/55,389/466,910, factor0.1GB. Integer 모델3,184,901rows / 1,141,597cols / 19,561,231nnz, original integer columns420,619, 첫presolve471,241/564,812/3,977,008, root barrier factor652,000nnz/24MB(0.024GB). Peak native RSS=6815764480bytes. Source epochs1–8의 실행 당시 모든 Python bytes 및 실제 native261회의 model/raw/source receipts PASS이며 각 source commit은 NEW_NATIVE_CALLS.json에 기록했다. Runtime이0으로 반올림된6회도 실제 optimize 호출 횟수에 포함했다. 최종 integer 실행sourceHEAD7b4a0d0292e1b289e7b1775a08ae152cc5d5331f. 최신 broad tests389 PASS(1368 deselected), epoch7 focused22 PASS 및 post-run 회계/acceptance/JSON동일성16 PASS를 보존했다. 원본 input11files와47grid arrays identity PASS. 신규 static cache/RAW 대형 binary는 D:에 보존했고 Git에는 재현 가능한 source와 SHA256 receipts 및 증거를 commit했다.

중간 RESOURCE_PENDING의 실제 근거는 M1 `experiment`/`continue_z0`와 worker였다. 사용자가 M 단계 종료를 알린 뒤 read-only PID 확인에서 native가 없는 것을 검증하고, 동일한 누적 예산으로 재개했다. 이전의 read-only 분석 PID를 잘못 막은 gate 기록, gate 수정, 의도적인 between-solve 구현 경계 비용도 모두 보존하고 wall 합계에 포함했다. 다른 M1/May10 프로세스에는 signal이나 쓰기를 하지 않았다. Native 잔여예산=3391.129998s. 마지막 성공 재개wall662.307797s(11.04분)와 전체 누적run wall 및 전체task wall을 구분한다. Scientific PASS와 전체task60분 실용성FAIL을 동시에 기록한다.

Independent post-run schedule 비교의 첫 실패는 JSON key 문자열화 및 tuple→array 자료형 차이였다. Native receipt의 기존 common.clean과 동일한 표현으로 비교하도록 수정했고, 실제 scheduling 결정과 수치값이 달라지면 거부하는 regression을 추가했다. 실패 로그/증거도 보존했다. 재검증은 point를 수정하지 않고 full row/integer/physical/동일 schedule/exact gap을 모두 확인했으며 optimize call0이다.

남은 문제 및 다음 한 가지 권고: P1-only Freeze를 기존 P2 인증서 필수 downstream에 연결하는 명시적인 interface adapter를 별도 연구 계약으로 검증한다. 이번에는 해당 pipeline을 수정하거나 실행하지 않았다. 전체task60분 실용성은 실패했으므로 이번 scientific acceptance를 fresh end-to-end 성능PASS로 해석하지 않는다. 자동 후속 실행 없이 종료한다.

Exception/미완료 사유: 없음. 최종 local/remote/PR HEAD equality와 clean tree는 별도 Git delivery receipt에 기록한다.
