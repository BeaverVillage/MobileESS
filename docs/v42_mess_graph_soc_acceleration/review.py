"""Write the requested 50-answer Korean review from measured evidence."""
from pathlib import Path
import json
import csv

HERE=Path(__file__).resolve().parent


def main():
    profiles=json.loads((HERE/'MESS_BASELINE_MODEL_SIZE.json').read_text())
    native=profiles['native_static_96'];before=native['baseline'];after=native['reduced']
    cold_build=after['model_build_seconds']+native['domain_prescreen_seconds']
    eq=json.loads((HERE/'MESS_OBJECTIVE_EQUIVALENCE.json').read_text())
    original=eq['cases']['canary']
    warm=json.loads((HERE/'MESS_WARM_START_AUDIT.json').read_text())
    reductions=list(csv.DictReader((HERE/'MESS_ELECTRICAL_COLUMN_REDUCTION.csv').open(encoding='utf-8')))
    forced={r['metric']:r for r in reductions if r['case']=='terminal_equality_and_transit_only'}
    answers=[
        ('MESS는 현재 complete-route enumeration인가?', '아니다. source-authorized travel/stay arc의 시간 확장 network-flow MILP이다.'),
        ('현재 formulation은 왜 이미 compact한 편인가?', '전체 일일 경로 조합을 열거하지 않고 arc binary와 flow conservation으로 하나의 경로를 표현한다. 기존에도 forward-unreachable arc/PQ 변수를 만들지 않았다. compact 구조라는 말이 native solve가 쉽다는 뜻은 아니다.'),
        ('stay arc란?', '(site,t)→(site,t+1). 이 binary가 선택된 슬롯에서만 해당 위치의 Pch/Pdis/Q를 사용할 수 있다.'),
        ('travel arc란?', '권한 있는 RouteArc의 (source,depart)→(destination,connect). arrive/connect/전액 이동 에너지/authority hash를 보존한다.'),
        ('전체 96 slots를 한 번에 푸는가?', 'native 엔진은 96슬롯 전체 route/P/Q/SOC를 공동 최적화한다. 이번에는 96슬롯 정적 mobility 모델만 구축했고, native optimize는 gate 때문에 미실행했다.'),
        ('이동과 P/Q/SOC를 같이 결정하는가?', '그렇다. route binary, charge_mode, Pch/Pdis/Q, 전 시간 SOC가 동일 MILP에 있다.'),
        ('forward reachability는 무엇인가?', '각 MESS의 (initial_site,0)에서 실제 arc를 따라 도달 가능한 node 집합이다. 도달 불가능한 source를 가진 arc를 제거한다.'),
        ('기존 대비 무엇이 추가됐는가?', 'backward co-reachability, 양방향 SOC outer hull, node 교집합·arc mapping 검사, fixed point, 안전한 시간별 SOC bounds, 공유 domain, 완전한 물리 warm-start 검증 및 MESS 전용 optimize timer다.'),
        ('backward reachability는 무엇인가?', '모든 허용 (site,H) terminal에서 거꾸로 추적해 terminal에 도달할 수 있는 node/arc를 남기는 검사다.'),
        ('terminal location을 임의로 고정했는가?', 'NO. 모든 기존 site를 terminal 후보로 사용한다. origin 복귀를 강제하지 않는다.'),
        ('forward SOC envelope은 무엇인가?', 'initial SOC부터 stay의 최대 충·방전 변화와 travel의 전액 차감을 전파한 보수적인 SOC 구간이다. 여러 predecessor는 outer hull로 합친다.'),
        ('backward terminal-SOC envelope은 무엇인가?', '모든 terminal의 정확한 terminal SOC에서 역방향으로 stay 변화·travel 차감의 역상을 전파한 필요한 predecessor SOC 구간이다.'),
        ('terminal SOC는 equality인가?', 'YES. E[H]==battery.terminal을 그대로 둔다. native authority는 760 kWh다. ≥로 완화하지 않았다.'),
        ('travel 중 충전 가능한가?', 'NO. 기존 모델처럼 travel action 및 skipped transit/connect 대기 슬롯에는 선택된 stay가 없으므로 Pch/Pdis/Q가 모두 0이다.'),
        ('travel energy는 어떻게 SOC에 반영되는가?', 'departure slot의 E[t+1] balance에서 energy_kwh 전액을 차감한다. connect까지 SOC가 그대로 유지된다. route를 중간 위치로 분해하지 않았다.'),
        ('SOC interval hull이 정확 feasibility certificate인가?', 'NO. 경로 상관관계와 PCS/grid 제약을 완전히 표현하지 않는 필요조건이다.'),
        ('왜 prescreen으로 안전한가?', '모든 물리적 prefix/suffix SOC를 포함하는 outer interval이므로 빈 교집합·빈 arc image에는 feasible trajectory가 없다. 바깥 반올림과 반복 제거의 귀납적 안전성을 사용한다.'),
        ('어떤 arc를 SOC 때문에 제거했는가?', 'bounded 예제에서 초기 SOC 부족 travel, terminal SOC에 닿지 못하는 node/incident stay, 에너지 mapping이 빈 arc를 제거했다. native static에서는 추가 SOC 제거가 0이었다. 이유와 iteration은 CSV/JSON에 모두 기록했다.'),
        ('exact route duplicate 정의는?', 'route_id/source/destination/depart/arrive/connect/energy_kwh/authority_sha256 등 모든 dataclass 필드가 같은 경우다. 숫자 0과 0.0은 같은 값으로 취급한다. 기존 dict.fromkeys와 동일하며 서로 다른 route ID/권한/도착시각은 남긴다.'),
        ('energy가 큰 route를 dominance로 삭제했는가?', 'NO. terminal SOC equality 때문에 더 큰 이동 에너지의 route가 필요할 수 있다. 높은 에너지 route만 살아남는 사례도 검증했다.'),
        ('pruning fixed point를 돌렸는가?', 'YES. 구조 forward/backward, SOC forward/backward·교집합, arc mapping을 deterministic하게 반복한다. native 네 MESS는 제거가 없는 마지막 iteration을 포함해 각각 2회였다.'),
        ('route binary가 몇 % 줄었는가?', 'native PR99 실제 변수 기준 207,928→207,928, 0%. 후보 graph 대비 forward 제거는 기존에도 적용됐다. 강제 transit bounded fixture에서는 7→2, 71.43%다.'),
        ('Pch 변수는 얼마나 줄었는가?', f"native 8,942→8,942, 0. bounded 강제 transit에서는 {forced['Pch']['before']}→{forced['Pch']['after']}다."),
        ('Pdis는?', 'native 8,942→8,942, 0. 강제 transit bounded에서는 6→1이다.'),
        ('Q는?', 'native 8,942→8,942, 0. 강제 transit bounded에서는 6→1이다.'),
        ('PCS rows는?', 'native 143,072→143,072, 0. 강제 transit bounded에서는 96→16이다. 모든 살아남은 stay마다 정확히 16 faces이며 production QConstr는 0이다.'),
        ('charge_mode binaries는?', 'native 384→384, 0. 강제 transit bounded에서는 5→1이다. 모든 가능 경로가 transit인 시간만 생략한다.'),
        ('total rows/columns/nonzeros 감소는?', f"native mobility-only rows 206,336→206,062(274개 감소), columns 235,526→235,526, nonzeros 1,259,442→동일. Gurobi build {before['model_build_seconds']:.3f}→{after['model_build_seconds']:.3f}s지만 최초 domain {native['domain_prescreen_seconds']:.3f}s를 포함한 cold 합계는 {cold_build:.3f}s다. 전체 cold 가속이나 solve 가속을 주장하지 않는다."),
        ('full feasible-route set이 보존됐는가?', '모든 물리적 경로가 살아남는 분석적 안전성 증명과 77개 bounded case의 전체 route/연속 SOC 구간 열거가 PASS다. native의 전체 route 열거/최적화는 수행하지 않았다.'),
        ('objective equivalence는 PASS인가?', 'YES. 77개 bounded 사례에서 infeasible 여부 및 optimal 5단계 목적값을 비교했다. 양쪽 MIPGap=0, 동일 1e-9 수치 tolerance, 목적값 허용차 3e-7이다. native equality를 측정한 것은 아니다.'),
        ('P1 rho는 동일한가?', f"YES. 원본 canary old={original['old']['rho']:.12f}, new={original['new']['rho']:.12f}. 추가 nontrivial route/PQ 사례들도 PASS다."),
        ('P2는?', 'YES. 원본 canary는 양쪽 0이고, 별도 reserve_requirement grid에서 nonzero reserve_shortfall도 비교했다.'),
        ('movement energy/count는?', 'YES. 원본 canary는 0.1 kWh/1회로 동일하다. 모든 bounded 사례에서 일치하며 deterministic tie도 동일하다.'),
        ('grid-benefit Top-K를 사용했는가?', 'NO. rho/전압/거리/낮은 에너지에 따른 site·route 선택이나 sampling은 없다.'),
        ('Dijkstra를 production optimizer에 넣었는가?', 'NO. source route table만 읽고 기존 RouteArc 계약으로 매핑한다. road search나 synthetic shortest path는 없다.'),
        ('M1/M2 static domain을 공유하는가?', 'YES. immutable domain을 명시적으로 두 solve에 전달하며 동일 입력의 single-process LRU도 제공한다. grid/AIDC anchor는 hash에 포함하지 않는다. gated native subprocess backend wiring은 후속 통합 사항이다.'),
        ('M2는 M1 warm start를 사용하는가?', '엔진에서 지원하며 bounded handoff 검증 PASS다. x/charge_mode/Pch/Pdis/Q/SOC 전체를 검증 후 지정한다. 바뀐 grid 변수는 다시 계산한다. native M2는 미실행이다.'),
        ('warm start는 objective를 바꾸는가?', f"NO. 동일 M2 문제의 cold/warm 목적값이 일치했다. start accepted={warm['accepted']}. 한 번의 작은 비교가 speedup 증거는 아니다."),
        ('model build와 optimize timer를 분리했는가?', 'YES. MESS OptimizeBudget은 첫 optimize 직전에 시작하며 모든 lex pass가 한 budget을 나눠 쓴다. data/domain, prescreen/authority 확인, Gurobi build와 per-pass Runtime을 분리 기록한다.'),
        ('future native M1 time limit은?', '1800초 optimize budget. 새 MESS OptimizeBudget 기본값이다.'),
        ('future native M2 time limit은?', '1800초 optimize budget. AIDC timer와 분리했다.'),
        ('target MIP gap은?', '0.005=0.5%. 고정이다. bounded exact equivalence만 gap=0이다. sweep이나 native 관측 후 gap 조정은 없다.'),
        ('presolve는 solve limit에 포함되는가?', 'YES. Gurobi optimize Runtime과 누적 optimize budget에 포함된다. build는 제외한다. 정확한 독립 B&B phase 시간이 관측 불가능하면 null로 남기며 callback 시간을 duration으로 꾸미지 않는다.'),
        ('현재 native M1을 실행했는가?', 'NO. PR99 accepted A1이 없으므로 M1/M2 모두 NOT_RUN_AWAITING_ACCEPTED_A_BLOCK다. 이번 native source-backed mobility-only build에는 가짜 AIDC/grid anchor가 없다. 기존 600초 outer coordinator/supervisor는 보존했으며 실제 native 1800초 실행 전에 timer 통합이 필요하다.'),
        ('MESS의 실제 남은 병목은 무엇인가?', 'native solve 병목은 미측정이다. static 모델에 route binary 207,928개가 남고 최초 domain 계산 비용도 관측됐다. 이것만으로 B&B/grid/root bottleneck을 단정할 수 없다.'),
        ('mobility route combinatorics가 병목인가?', '미확정. route column 비중은 크지만 native B&B branching 증거가 없으므로 route combinatorics 지배를 주장하지 않는다.'),
        ('grid coupling이 병목인가?', '미확정. accepted A1/A2를 넣은 native grid/security 모델과 root/cuts를 실행하지 않았다.'),
        ('MESS Dantzig-Wolfe가 필요한가?', '현재 trigger FALSE(증거 미확보). network-flow MILP를 유지한다. 실제 route/path branching이 지배하면 다음 별도 작업의 후보로만 검토한다.'),
        ('CL-MC-BD가 필요한가?', '현재 trigger FALSE(증거 미확보). 실제 critical-line/security coupling이 지배할 때만 검토한다. 자동 구현하지 않았다.'),
        ('다음 MESS 단계는 정확히 무엇인가?', '진짜 accepted A1/A2 결과를 통합하고 domain 전달·outer supervision을 정렬한 뒤 각 M1/M2 optimize를 1800초/gap0.005로 실행한다. build/presolve/root/B&B·grid/security·P/Q/SOC를 측정한 후에만 다음 exact 기법을 결정한다.'),
    ]
    assert len(answers)==50
    text='# V42 MESS 최종 검토\n\n기준은 PR #99 지정 head다. 기존 AIDC/Runtime/CC4/TS 코드와 증거는 byte 단위로 보존했다. native 수치와 bounded 예제의 효과를 구분한다.\n\n'
    text+='\n\n'.join(f'{i}. **{question}**\n\n   {answer}' for i,(question,answer) in enumerate(answers,1))+'\n'
    (HERE/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')


if __name__=='__main__':main()
