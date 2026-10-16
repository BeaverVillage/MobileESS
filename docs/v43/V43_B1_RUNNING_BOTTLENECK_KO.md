B1 C0 실행 중 병목 관측

worker Source782861149, PID47716/creation1792131950.6340928, 시작2026-10-16 06:25:51UTC. Source는 수정하지 않는다. 준비완료35회귀/현재Case 수학동치/driver compile PASS 후 새Actual을 실행했다. B2와C1은시작하지않는다. 전체40분Wall상한/공식Stop/원장정산/부분관측증거보존이설정됐다.

5초비차단py-spy 표본1: 성공238/실패9, current_guard68, probe64, 분기측정1, Inventory3. 표본2(후반): 성공233/실패15, current_guard137, probe129, native apply60, public_future65, service_integral36, SolveSnap15, 분기측정2, Inventory1. 중첩표본은서로겹치며전체Wall비중이아니다. 각Raw/요약JSON은attempt에보존했다.

남은비용은현재후보의원본과거SolveSnap 재생내 native background분배와Unknown별미래서비스·예약프로파일/점수재계산이다. 원본dayahead/v40e/mapping.py allocate는Source고정분배비율에Fraction을적용하고매번bus/phase별ledger보존식을재합산한다. 이정적배경배분은같은관측시각·Source·targets에대해후보마다반복된다. C0는대체사이트를고르지않는데도96슬롯look-ahead 프로파일과점수를계산한다. 반복분기측정/Inventory는현재표본에서작은비중이다.

현재실행을유지하며전체측정과독립Fresh96을먼저보존한다.40분도달또는실제오류시공식중단/정산후개선한다. 이후가능한개선은Source/adapter/관측배경P·Q가정확히같은원본분배결과의캐시, 그리고C0의사용되지않는look-ahead비용을독립동등성검증으로제거하는것이다. 구현·성능효과는아직인증하지않았다. 완전DSS상태복제를주장하거나물리검사/대역을완화하지않는다.
