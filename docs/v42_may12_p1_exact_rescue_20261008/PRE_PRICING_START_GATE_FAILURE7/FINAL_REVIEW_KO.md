# May12 P1-only 최종 검토

최종 판정: **MAY12_RESOURCE_PENDING**. P1-only accepted=False. 기존 4목적 A1_ACCEPTED는 변경하지 않았다. P2와 downstream은 실행하지 않았다.

이전 실행은 Phi=0 이후 P1과 130개 클래스 가격화까지 완료됐다. 실패는 P1 점을 새 elastic master에 연결하면서 80개 artificial weight 차이를 거부한 Python witness 검증기였다. 실제 저장 데이터 회귀는 수정 전 실패했고 수정 후 통과했다. 새 P1에서는 artificial-free original point 포함성을 검증한다. 양수 Phi의 frozen-weight 규칙과 scientific tolerance는 유지했다.

Phase-I trajectory: 0.03623444192091598 → 0.016419620449477194 → 0.0046485901268879595 → 0. 기존 활성화 round3, STAY96/migration96. Original dyadic row replay 및 original Planning grid replay PASS=True; full130 zero-dual pricing PASS. Raw native Phi=0과 재구성 artificial Phi(약6.44e-13)를 구분했다. 신규 Phase-I native solve0회. 이 인증은 연속 Phase-I feasibility이며 정수 schedule 인증은 P1 결과에 따로 기록한다.

P1 restricted LP는 0.6607295534700348 → 0.6588875397405124로 감소했다. S0 full130 pricing은 STAY208,957개와 migration50,756,904개를 포함하는 원본 후보 영역의 완전 oracle를 인증했다. Global exact LB=1379175058609872829341611/2417851639229258349412352 (0.5704134348993862), validated integer UB=None, gap=None. 음수 블록129개(STAY 포함129/Migration 포함38)는 concrete column 개수가 아니다. 한 번의 P1 support graph 활성화로 S1을 만들었고 exact original 3,184,901행/1,141,597열 inclusion에서 목적값 동일성을 검증했다. S1 latest pricing은 76/130이다. P1 전체 영역 optimal pricing closure PASS=False. 완전 S0 하한은 유효하며, 미완료 S1 bound와 restricted ObjBound는 global bound로 사용하지 않았다. 원본 모든 global rows와 130개 full STAY/migration oracle의 finite-bound exact certificate/roundoff transport를 사용했다.

Original continuous Phase-I Planning grid replay는 PASS지만, P1 integer physical replay PASS=False이고 schedule metrics=None다. 정수 최적화는 NOT_RUN이며 정수해를 만들었다고 주장하지 않는다. Migration을0으로 고정하거나 이동/시간 후보를 삭제하지 않았다. P1-only Freeze와 acceptance는 false다.

신규 native 205회, Runtime=35.178002s/3600s, Work=37.555673. 기존 native285회/233.892997s/Work327.445620은 그대로 보존했다. 신규 native/build/pricing/검증을 포함한 run wall=3346.877s. 복구 audit 이후 task wall=8935.714s, practical60분 기준=False. 모델 build/검증은 native예산과 구분했으며 실제 per-call Runtime/Work/model sizes/factor-memory/presolve는 RESOURCE_AND_RUNTIME_AUDIT.json과 native 원시 로그에 있다. RAM limits 및 RAM-triggered stops는 없다. Threads1, sequential native. 과거 작업의 예산은 수정하지 않았다.

다른 세 날짜: May17은 기존 four-objective A1 및 practical60분 accepted. May19은 기존 scientific A1 accepted이나 과거 certificate 재사용이어서 fresh end-to-end practicality 인증은 없다. May10은 PR184 고정 개선실험 후에도 UB60/globalLB2로 INCONCLUSIVE다. 그 결과와 PR184 HEAD1444d1614258be3e6ff24c56dfc078d69e8ced9a는 보존했다.

성능 측정과 병목: PERFORMANCE_COMPARISON.csv는 과거와 이번의 실제 측정 범위를 구분한다. 이번 복구는 historical solve 재사용 및 batch ledger refresh 동치성을 채택했다. 제한된 단일 native 설정을 사용했으며 broad sweep이나 automatic follow-up은 없다. P1 LP/master/pricing/정수 단계별 소요시간은 P1_TRAJECTORY.json과 NATIVE_CALLS에 기록된다. 실제 병목은 이 비용표로 판단하며 과거 PR164의 다른 모델 병목을 이번 수치에 전용하지 않는다.

실제 S0 master: 754,043 rows / 71,377 cols / 13,356,317nnz, presolved19,509/32,106/207,709, factor0.03GB. 실제 S1 master: 915,801 rows / 116,985 cols / 13,738,297nnz, presolved56,808/55,389/466,910, factor0.1GB. Peak native RSS=4354105344bytes. Source epochs1–7의 실행 당시 모든 Python bytes 및 실제 native207회의 model/raw/source receipts PASS이며 각 source commit은 NEW_NATIVE_CALLS.json에 기록했다. 최신 broad tests389 PASS(1368 deselected), epoch7 focused22 PASS 및 post-run 회계/acceptance13 PASS를 보존했다. 원본 input11files와47grid arrays identity PASS. 신규 static cache/RAW 대형 binary는 D:에 보존했고 Git에는 재현 가능한 source와 SHA256 receipts 및 증거를 commit했다.

RESOURCE_PENDING의 실제 근거는 `v42_group_branching.continue_z0`와 worker의 실행이다. 이전의 read-only 분석 PID를 잘못 막은 gate 기록, gate 수정, 의도적인 between-solve 구현 경계 비용도 모두 보존하고 wall 합계에 포함했다. 다른 M1/May10 프로세스에는 signal이나 쓰기를 하지 않았다. 가장 최근 관측에는 M1 `phase_b`와 worker2개가 실행 중이었다. RAM 수치에 의한 판단이나 종료는 없었다. Native 잔여예산=3564.821998s이며, 예산 소진이나 infeasibility로 판정하지 않는다.

남은 문제 및 다음 한 가지 권고: 별도로 승인된 실행에서 실제 native 경합이 끝난 뒤, 검증된 S1 activation checkpoint와 pricing cache를 재사용하여 잔여54개 oracle를 완료하고, actual matrix 검증을 통과한 STAY batch activation 경로로 P1 인증을 이어간다. 이번 작업은 자동 재개 없이 종료한다.

Exception/미완료 사유: BudgetStop('MAY12_RESOURCE_PENDING_OTHER_NATIVE_WORKERS'). 최종 local/remote/PR HEAD equality와 clean tree는 별도 Git delivery receipt에 기록한다.
