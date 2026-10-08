# 완료된 M1 연구 증거 감사

PR167–190의 정확한 HEAD 목록과 완료된 M188/M190 Git blob을 읽었다. 새 audit는 출처 바이트와 과거 주장 범위를 검사하며, 저장된 PASS를 새로운 수학적 증명 PASS로 간주하지 않는다. 과거 solver 코드와 PR190의 scalar support 구현을 import하지 않았고 optimize 호출은 0회다. 미완료 작업공간이나 프로세스에 접근하지 않았다. 모든 새 파일과 Git 객체 읽기·캐시는 독립 D: clone 안에서 수행했다.

## 기준과 하한 authority 구분

과학적 기준은 PR162 C3A `1d922c91eb27056a5ccc79c92ef18146707099ab`다. 완료된 통합 M 기준은 PR188 `4b19e85089171729a3225529a40cb00bf31f43d5`, PR190 참조 HEAD는 `c10e2deb0970b52b308ff71d7b7642b9156cfafe`다. May01 1,499-job anchor를 May12 1,782-job P1-only 입력에 적용하지 않는다.

기존 Global LB **0.5687116104049206**은 PR162 native MILP bound authority를 보존한 값이다. PR190의 `GAP_ROOT_CAUSE_AUDIT.json`은 이 값을 독립 exact ROOT dual certificate로 재분류하지 않았다고 명시한다. native ROOT 목적 **0.568711942993466**과의 차이 약 3.33e-7도 서로 다른 authority 범위 비교이며, 동일 점의 인증 손실 측정이 아니다.

독립 인증을 새로 수행할 때 이 차이를 숨기면 안 된다. 저장된 plain C3A exact dyadic ROOT 인증서는 **0.5671374761409242**다. 두 차량의 4-slot lift를 포함한 PR169 homogeneous exact 인증서는 **0.5687115940355527**로, 기존 native authority보다 약 1.64e-8 낮다. 이 높은 archived exact 값에는 각 232,837개 disjunct의 lift와 multiplier source 및 원본 정수 projection proof가 필요하다. 이번 history audit는 인증서 SHA와 claim을 기록했으며 새 independent replay를 수행했다고 주장하지 않는다.

## 왜 ROOT가 약한가

완료된 저장 ROOT는 node_activity 7,070개와 charge_mode 384개가 fractional이고, continuous route flow 140,502개가 여러 경로로 분산한다. B2 ROOT도 fractional binary 8,019개와 route flow 140,264개가 남았다. 위치·mode·P/Q·SOC 지원을 다양한 차량과 지점으로 재배분할 수 있다.

PR167의 one-slot hull cut 320개는 일부 저장 점의 국소 위반을 제거했지만 certified ΔLB는 0이었다. PR169의 MESS04/MESS03 69–72 joint local hull도 ΔLB=0이다. 전체 두 block 모델은 7,540,822행·3,106,200열·28,679,818 NNZ로 커졌다. fractionality 감소나 특정 local 위반을 전체 전역 gap의 원인 증명으로 확대하지 않았다.

PR188의 단일 mode/location sibling 분기는 전체 정수 영역을 포괄했지만 certified ΔLB=0이었다. 분기 후에도 135,444–140,095개의 fractional route flow와 대체 dispatch가 남았다. 특정 child의 bound를 전체 Global LB로 쓰려면 완전한 domain cover와 각 leaf 인증이 필요하다.

PR182의 더 큰 fleet/time/grid extended formulation 두 후보는 ROOT 종료에 실패했다. TIME_LIMIT의 partial LP objective 0.57689/0.57642를 valid LB로 사용하지 않았다. 원래 모델보다 강한 구조가 있어도 계산 가능한 인증을 못 만들면 개선은 NOT_PROVEN이다.

## B2의 651개 행

B2는 원래 306,040개 열과 모든 원본 행을 보존한 651행·1,302 NNZ 추가다. 완료된 독립 receipt는 exact coefficient/source rational check, 원본 bounds를 통한 outward transport, 잘못된 physics/RHS mutation 2건 거부, 과거 20개 정수 witness 및 best UB replay를 기록한다. 새 연구에서 사용하기 전에는 완료된 source DAG와 원래 정수영역에 대한 독립 validity replay가 필요하다. witness가 통과한다는 사실만으로 모든 정수영역 유효성이 증명되지는 않는다.

B2 native LP 목적 진단값은 **0.5687138902579907**이다. raw multiplier는 wrong-sign 20,566건으로 거부됐다. 별도로 sign-cone projection한 수학적 multiplier의 exact LB는 **0.5659508784310822**이며, binding equality 4,500개 repair 후에도 **0.5667436728775703**이다. 두 인증은 기존 Global LB보다 낮아서 개선이 아니다. raw ObjBound를 인증값으로 승격하지 않았다.

## PR190 scalar와 cutoff의 실패

선택한 scalar grid direction의 요구 D(3/5)는 **0.0130951605623203**, 차량 capacity analytical 상한 합은 **0.0445024823893487**이다. 더 결정적인 음성 증거는 각 차량의 exact private-physics feasible support 하한 합 **0.0342492521133151**이 D를 초과한다는 것이다. 같은 scalar와 독립 차량 capacity 합계로는 차량별 최적 최대 지원량을 완벽히 풀어도 모순이 나오지 않는다. 이 private witness는 coupled grid를 만족하는 전역 rho≤0.60 해가 아니다.

원본 cutoff의 단일 native 결과는 TIME_LIMIT, SolCount=0, NodeCount=1, Runtime 1,180.036초로 **INCONCLUSIVE / NOT_PROVEN**이다. native binary64(0.6)와 exact 3/5의 차이도 별도로 기록됐다. 정수해를 못 찾은 사실과 cutoff infeasibility proof를 구별한다. scalar 코드 전체를 새 v42로 병합하지 않았다.

## UB 증거와 복원 대상

best UB **0.6284141956452488**의 실제 점은 완료된 M188 Git blob `docs/v42_m1_route_mode_benders_20261008/artifacts/BEST_VALID_POINT.npz`다. `C3A_VALID_START.npz`는 더 오래된 **0.6694159238756877** warmstart이며 best UB가 아니다.

PR169는 정적 Q-only 초기 해에서 64–84 슬롯 neighborhood를 통해 mode14개와 node_activity10개를 바꾸어 실제 충·방전과 이동을 사용했고 UB를 0.6339776033797229까지 낮췄다. PR170/171은 0.6324498168172089, 0.6306505800203936을 검증했다. PR183의 최종 0.6284141956452488 개선은 기존 trajectory를 유지하며 `charge_mode[MESS01,0]` 한 bit와 joint dispatch를 바꾼 assignment018에서 나왔다. Pch 최대 변화300kW, Pdis45.673172kW, Q771.407595kvar, SOC71.25kWh는 가족별 최대 절대 변화이며 개별 인과 기여의 분해가 아니다.

PR183의 20개 유효 고정 배정 recourse는 median Runtime 약2.002초였지만 첫 새 master 배정은120초 recourse가 미해결되어 independent separating cut을 못 만들었다. 따라서 알려진 배정의 빠른 LP가 새 배정도 항상 빠름을 보장하지 않는다. restricted-neighborhood bound는 Global LB가 아니다.

PR183와 PR190의 저장 independent best replay는 원본 integer pattern, 96-slot route/SOC/PCS/PQ/mode/connection, frozen AIDC와 673,920개 original grid 행을 통과했다. 이 history audit는 해당 receipt를 읽었으며, 새 MIP start 사용 전의 새 independent original replay는 연구 runner가 수행해야 한다.

현재 과거 native authority 기준 Gap **9.500515051068552%**, M1_ACCEPTED=false를 보존한다. 다음의 단일 우선 병목은 **서로 다른 line/time의 동시 지원 요구를 합계 scalar로 지우지 않고 4대의 전체 96-slot 경로·SOC·mode·P/Q로 포괄하는 계산 가능한 공동 relaxation/cover 인증**이다. 본 문서는 새 연구의 결과나 성공 판정을 선취하지 않는다.
