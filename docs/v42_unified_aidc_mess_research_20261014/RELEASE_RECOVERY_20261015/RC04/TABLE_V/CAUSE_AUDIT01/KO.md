B1 A1 INFEASIBLE — 공개 Source·domain 원인 감사 및 최소 복원

확정된 실행 사실은 EXECUTION01 B1 A1의 현재 행렬이 Gurobi status3 INFEASIBLE로 끝났다는 것입니다. Native776.268999815초가 소비됐고 rows1,699,066/columns600,284/nonzeros15,446,607입니다. 전체 연구 문제의 불가능성이나 원본 알고리즘 오류로 확대하지 않습니다. 이번에 찾은 compiler 결함이 status3의 단독 원인이라는 증명도 아직 없습니다.

확정된 additive compiler 결함: 원본 ExperimentalQoSProvider receipt는 submit/event/Source release/earliest를 하한으로 하고 reference+budget 및 Source latest/deadline을 상한으로 발급합니다. 원본 experimental_planning은 해당 receipt_slot_domain 전체를 사용합니다. 새 Table V compiler에는 t>=causalReference라는 별도 하한이 추가돼 있었습니다. reference는 Source hard release가 아니므로 이 필터는 원본이 허용한 합법 시작을 삭제합니다.

실제 영향은 Pending992UID/시작3667개였습니다. 비참여711UID와 참여281UID가 포함됩니다. 예 UID8639667은 Source hard4field가 모두null이고 원본 receipt native[24,25]인데 compiler가[25]만 남겼습니다. 원본 E1의 budget0은 추가 지연을 금지하는 상한이며, 원래 receipt가 허용한 reference 이전 시작을 모두 금지하는 별도 하한은 아닙니다.

Root가 DOMAIN_REPAIR02에 원래 Source를 보존한 뒤 해당 추가 비교식만 한 줄에서 제거하도록 승인했습니다. 수정은 그 조건 삭제뿐이며 원본 Source13, QoS 통계·예산·HardRelease·Deadline·Running site/elapsed·ServiceCarry·WAN·도메인 알고리즘은 변경하지 않았습니다. 기존 PREP와 EXECUTION01 입력/Raw/실패 결과를 덮어쓰지 않았습니다.

새 공개 준비 FLEX_PLANNING/PREP_RESTORED01은 PASS입니다. 1555 positive-service UID 모두 compile window가 원래 issued receipt window와 정확히 일치합니다. 992UID/3667시작이 정확히 복원됐고 movable Pending은377→1088입니다. Known1624, E1 checkpoint454/그중Running77은 동일합니다. 새로운 Source SHA는e5ae3eb1184efb64188c553c630746dc5dd11d0299800057e5f53b2a0f9373a5이며 science1c1d99be…/case9c3ad24e…로 별도 봉인됐습니다. 원본 Source13 SHA13개 모두 그대로입니다.

추가 구조 검사에서 Running continuation site/elapsed 축 오류0, raw source-compatible set 차이0, finite service-bound 모순0이었습니다. Q50 expired Running69UID는187GPU의 현재 native24 물리 hold로 그대로 남습니다. Known+CC4 CDF의 보수적96 prefix 용량 필요조건에는 양수 위반0이었습니다. 이 조건은 단순 필요조건이므로 coupled FULL feasible을 증명하지 않습니다. Runtime risk-anchor의 기존 pending reference delta 보정도 유지하며 offset 불변 회귀가 통과합니다.

원본 E1 receipt 이전 시작을 의도적으로 늦은 causal reference 아래에서 제거하지 않는다는 참여/비참여2개 회귀를 추가했습니다. 작은 geometry를 포함해45개 테스트가1.37초에 PASS했습니다. Native·presolve·IIS·대형 model build·Actual·AC·미래 private metadata 읽기 모두0입니다. 새 case의 실제 FULL 판정은 Root의 정확한 Source/Case/Matrix/Domain/Objective 검증과 승인된 stage 잔여 예산 실행에 남습니다. 기존 B1 소비776.269초는 그대로 누적해야 하며 이번 감사에서는 원장을 변경하지 않았습니다.
