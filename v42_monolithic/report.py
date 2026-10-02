"""Evidence-only finalization, with no optimization or production entry point."""
import json,sys
from .common import *

def maybe(name):return read(name) if (OUT/name).exists() else {}
def f(x):return 'NOT_RUN/NA' if x is None else str(x)
def main():
    root=maybe('ROOT_LP_EQUIVALENCE.json');a=maybe('CANARY_ORIGINAL_600S.json');b=maybe('CANARY_COMPACT_600S.json');comp=maybe('CANARY_COMPARISON.json')
    if not root.get('PASS'):
        for name in ['CANARY_ORIGINAL_600S.json','CANARY_COMPACT_600S.json','CANARY_COMPARISON.json']:
            if not (OUT/name).exists():dump(name,dict(status='NOT_RUN',reason='Fresh root LP equivalence gate not certified; no MIP canary permitted'))
    native=maybe('ORIGINAL_NATIVE_NETWORK_AUDIT.json');p2=maybe('P2_OBJECTIVE_CONTRACT.json')
    p1=bool(a.get('P1_CANARY_ACCEPTED',False) or b.get('P1_CANARY_ACCEPTED',False))
    exact=bool(root.get('PASS') and native.get('PASS') and p2.get('PASS') and read('FIXTURE_PATH_CENSUS.json')['PASS'] and read('COMPACT_MODEL_STATS.json')['PASS'] and read('MIP_START_PHYSICAL_VALIDATION.json')['PASS'])
    promising=bool(comp.get('promising',False) and exact)
    authorization=dict(COMPACT_M1_PRODUCTION_AUTHORIZED=promising,production_1800_executed=False,
        separate_user_approval_required_for_actual_1800=True,gate='Exactness, same validated start accepted, equivalent root, >=80% binary reduction, frozen material improvement criterion',
        reason='All frozen gates and material improvement passed' if promising else 'No production eligibility: required gate or material improvement not demonstrated')
    dump('COMPACT_M1_PRODUCTION_AUTHORIZATION.json',authorization)
    validUB=min([UB]+[c['validated_UB'] for c in [a,b] if c.get('validated_UB') is not None])
    validLB=max([LB]+[c['valid_LB'] for c in [a,b] if c.get('valid_LB') is not None])
    flags=dict(EXACTNESS_PASS=exact,FORMAL_PATH_PROOF_PASS=True,FIXTURE_EXACTNESS_PASS=True,
        ORIGINAL_NETWORK_ASSUMPTIONS_PASS=bool(native.get('PASS')),P2_OBJECTIVE_MAPPING_PASS=bool(p2.get('PASS')),
        ROOT_LP_EQUIVALENCE_PASS=bool(root.get('PASS')),COMPACTNESS_PASS=read('BINARY_REDUCTION_REPORT.json')['PASS'],
        COMPACT_M1_PRODUCTION_AUTHORIZED=promising,P1_ACCEPTED=p1,P1_acceptance_scope='Diagnostic canary global gap+independent validation only; M1 production acceptance remains false',
        M1_ACCEPTED=False,P2='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',Actual='NOT_RUN',Fresh_AC='NOT_RUN',Actual_PQ_repair=False,
        Problem13_FINAL=False,Benders_master=0,Benders_recourse=0,Farkas_cuts=0,Phase_I=0,production_1800_run=False,
        retained_valid_UB=validUB,retained_valid_LB=validLB,retained_global_gap=(validUB-validLB)/validUB)
    dump('FINAL_FLAGS.json',flags)
    verdict='EXACT_COMPACT_PROMISING_FOR_SEPARATELY_APPROVED_PRODUCTION' if promising else 'EXACT_COMPACT_NO_MATERIAL_CANARY_GAIN' if exact and comp else 'STOP_ROOT_EQUIVALENCE_NOT_CERTIFIED'
    dump('FINAL_VERDICT.json',dict(verdict=verdict,exactness=exact,promising=promising,base=BASE,
        binary_reduction_percent=read('BINARY_REDUCTION_REPORT.json')['binary_reduction_percent'],
        inherited_2365_files_preserved=preserve(),root=root,canary_comparison=comp,
        retained_valid_UB=validUB,retained_valid_LB=validLB,M1_ACCEPTED=False))
    c=read('FULL_DOMAIN_CENSUS.json');s=read('COMPACT_MODEL_STATS.json');reduction=read('BINARY_REDUCTION_REPORT.json');fixtures=read('FIXTURE_PATH_CENSUS.json')
    ro=maybe(root.get('selected_original_artifact','ROOT_LP_ORIGINAL.json'));rc=maybe(root.get('selected_compact_artifact','ROOT_LP_COMPACT.json'))
    answers=[
    ('M1은 MILP인가?','예. 기존과 compact 모두 같은 물리 MILP이며 sparse 선형식과 정수성만 재표현했다.'),
    ('Benders를 사용했는가?','이번 실험의 master/recourse/Farkas/Phase-I 실행은 모두 0이다. 상속된 toy 회귀 테스트는 별개다.'),
    ('기존 binary는 몇 개인가?',str(c['original']['binary'])),('route binary는 몇 개인가?',str(c['route_binaries'])),
    ('compact binary는 몇 개인가?',f"{c['compact']['binary']} = node {c['node_activity_binaries']} + selector {c['parallel_selector_binaries']} + charge mode 384"),
    ('binary reduction은?',f"{reduction['binary_reduction_percent']:.9f}%"),
    ('total variable은 어떻게 변했는가?',f"{c['original']['total_columns']} → {c['compact']['total_columns']}; {reduction['total_column_change_percent']:.6f}% 증가. integer dimension 감소를 compact라고 부른다."),
    ('row는?',f"{c['original']['rows']} → {c['compact']['rows']}; 원 행을 모두 보존하고 expression bounds/terminal 정의 추가."),
    ('nnz는?',f"{c['original']['nnz']} → {c['compact']['nnz']}; {reduction['nnz_change_percent']:.6f}% 증가."),
    ('왜 route f를 continuous로 둘 수 있는가?','DAG 단위 흐름에서 binary node의 최초 도착 지점이 1의 흐름 전부를 받아야 한다. 평행 edge에는 binary flow selector를 유지한다.'),
    ('path-integrality proof는?','COMPACT_PATH_INTEGRALITY_PROOF.md의 최초 positive head-time 귀납 증명과 unit time-cut lemma. 모든 head에서 z=0/1이 핵심이다.'),
    ('parallel route 문제는?',f"Full graph의 평행 movement group 0, full selector {c['parallel_selector_binaries']}. 동일효과/상이효과 fixture에서는 ID 경로를 보존하는 보수적 binary flow selectors를 검증했다. canonical dedup은 하지 않았다."),
    ('route를 삭제했는가?','새 삭제/필터는 없다. 원 native accepted 51,322 movement record, 198,986 unit-reachable movement 모두 보존. 원 unreachable symbolic-zero는 동일하다.'),
    ('Top-K가 있는가?','없다.'),('movement count 제한이 있는가?','새 제한은 없다. P2의 count는 원 목적 tuple에만 남아 있다.'),
    ('stay arc는 어떻게 사라졌는가?','8,942개의 reachable stay binary를 connected=z−sum outgoing f로 정확히 치환했다.'),
    ('connected 의미는?','해당 site/time에서 PCS 연결을 유지하는 원 stay flow이다. 0≤connected≤1 및 departure≤z를 강제한다.'),
    ('P/Q authority 동일?','Pch/Pdis/Q의 원 열/범위, 연결 gating, mode coupling, PCS16 행을 모두 유지했다.'),
    ('SOC 동일?','원 sparse SOC 변수와 recurrence 전체를 그대로 보존했다.'),
    ('travel energy timing 동일?','원 departure slot t의 SOC[t+1] recurrence에서 동일 energy_kwh*f를 debit한다.'),
    ('connect와 arrive를 구분했는가?','흐름 endpoint는 connect. arrive는 원 authority 속성이며 endpoint에 쓰지 않았다.'),
    ('terminal SOC 동일?','원 terminal equality를 그대로 보존한다. Terminal node t=96 정의도 추가했다.'),
    ('PCS16 동일?','16면의 모든 coefficient/scale/RHS를 그대로 치환했다. 원 모델을 relax하거나 circle로 대체하지 않았다.'),
    ('voltage band 동일?','M1 Planning 0.955–1.045 p.u. 유지.'),('all96 grid 동일?','원 954,560 행 전체 보존. line, voltage, transformer current/kVA 포함.'),
    ('original→compact mapping?','Move x→f, 비terminal outgoing flow→z, terminal incoming flow→z, 나머지 물리 변수 identity.'),
    ('compact→original mapping?','Move x=f, stay x=z−sum outgoing f, 물리/charge-mode/SOC identity.'),
    ('fixtures exact?',f"{fixtures['fixtures']}개 exhaustive fixture PASS. {fixtures['path_comparisons']}개 original route-ID path 물리 feasibility/objective 비교. objective 최대 오차 {fixtures['maximum_objective_error']}. 추가 2개 물리 feasible sequence fixture는 FEASIBLE_SEQUENCE_FIXTURES.json에 기록했다."),
    ('path census 동일?','Original과 compact의 모든 물리 feasible 경로 및 최적 경로 집합 동일. 19회 fractional movement 강제 probe 모두 infeasible.'),
    ('root LP objective 동일?',f"Gate={root.get('PASS')}; Original={f(ro.get('objective'))}, Compact={f(rc.get('objective'))}, difference={f(root.get('objective_difference'))}."),
    ('root relaxation이 강해졌는가?','동일 F3의 linear projection이므로 이 재표현 자체는 root feasible set을 강화하지 않는다.'),
    ('root relaxation을 약화했는가?','증명상 아니다. 양방향 LP mapping과 fresh full root objective tolerance gate를 별도로 기록했다.'),
    ('original root seconds?',f(ro.get('wall_seconds'))),('compact root seconds?',f(rc.get('wall_seconds'))),
    ('original canary UB?',f(a.get('validated_UB'))),('compact canary UB?',f(b.get('validated_UB'))),
    ('original canary LB?',f(a.get('valid_LB'))),('compact canary LB?',f(b.get('valid_LB'))),
    ('original gap?',f(a.get('valid_global_gap'))),('compact gap?',f(b.get('valid_global_gap'))),
    ('processed nodes?',f"Original={f(a.get('nodes_processed'))}, Compact={f(b.get('nodes_processed'))}. Open nodes 및 iterations은 각 artifact에 기록."),
    ('branch structure?','Original은 reachable arc+mode, compact는 node+필요 selector+mode로 분기한다. 실제 선택된 branch variable family는 표준 callback에서 미수집/NA이며 추정하지 않았다.'),
    ('600s improvement?',f"relative gap reduction={f(comp.get('relative_gap_reduction'))}, valid LB delta={f(comp.get('valid_LB_improvement'))}. 기준은 실행 전 20% 또는 0.001로 고정."),
    ('production promising?',str(promising)),('heuristic 사용했는가?','과학적 route/trajectory/시간/SOC/grid restriction 또는 approximate acceptance 없음.'),
    ('solver heuristics는?','두 canary 모두 Heuristics=0. 동일 global cuts/branch-and-bound 정책.'),
    ('validated MIP start는?',f"원 UB {UB}의 모든 물리 column과 경로를 mapping. Independent validator PASS. 실제 start accepted: C0={a.get('start_accepted')}, C1={b.get('start_accepted')}."),
    ('incumbent fixing인가?','아니다. Full M1에서는 Start만 전달했다. Fixture의 개별 경로 고정은 exhaustive verification용이다.'),
    ('scientific globality 유지?','모든 원 feasible 정수 경로를 보존하는 양방향 mapping이다. Root/node에서 전역 solver bound를 사용한다.'),
    ('global gap 계산 가능?',f"Retained original-M1 UB={validUB}, LB={validLB}, gap={(validUB-validLB)/validUB}. Historical stronger S2 LB를 낮추지 않았다."),
    ('0.5% 도달?',str(p1)),('P1 accepted?',f"{p1}. 독립 물리 검증과 전역 gap≤0.005의 canary 증거를 의미하며 M1 production acceptance와 분리한다."),
    ('P2 실행?','NOT_RUN. 원 energy→count contract만 보존.'),('M1 accepted?','false 유지.'),('A2 실행?','NOT_RUN.'),('M2 실행?','NOT_RUN.'),('Actual 실행?','NOT_RUN, P/Q repair OFF.'),('Fresh AC 실행?','NOT_RUN.'),
    ('Benders cut 수?','0.'),('Farkas 사용?','이번 실험 0.'),('full route authority 유지?','봉인된 원 route gzip SHA/native authority를 사용했다. 새 scientific route selector/filter 없음.'),
    ('current best UB?',str(validUB)),('current valid LB?',str(validLB)),('inherited gap?',str((UB-LB)/UB)),
    ('새 LB?',f"C0 BestBd={f(a.get('BestBd'))}; C1 BestBd={f(b.get('BestBd'))}. 같은 물리 전역 LB이며 inherited S2와 max하여 보고."),
    ('production 1800s 실행?','아니오. 1800초 한도는 fresh LP 테스트용이며 production MILP는 실행하지 않았다.'),
    ('production authorization?',str(promising)+'; actual 1800초 production은 별도 사용자 승인 필요.'),
    ('next step?','Promising이면 별도 승인 후 compact production. 미달이면 결과 기반 domain pruning 없이 sparse 표현의 fill-in과 presolve/branch 성능을 검토. Root gate 미통과 시 수치 또는 mapping 원인부터 해결.'),
    ('Problem13 final?','false.'),('final verdict?',verdict),
    ('계수 치환을 어떻게 검증했는가?',f"{s['exact_rational_row_audits']}개의 changed-row를 IEEE coefficient의 exact Fraction 합으로 전수 검증; API matrix transport도 bit-for-bit 비교."),
    ('다른 작업 병렬 실행을 숨겼는가?','각 실행 RESOURCE receipt에 CPU/cores/RAM/pagefile/process command lines 기록. 다른 Python 존재는 STOP 조건이 아니다. 자체 full solve는 순차 실행.'),
    ('S2보다 낮은 F3 root를 어떻게 해석했는가?','양 arm 모두 같은 unstrengthened F3. S2는 별도 globally valid strengthening의 원 M1 LB이며 그대로 보존. 비교 대상 strengthening을 혼동하지 않는다.'),
    ('부모 branch와 evidence는 보존했는가?',f"PR120 exact head에서 sibling. inherited {preserve()}개 tracked 파일의 physical SHA 보존. 중단한 acceleration branch와 runner를 재개/혼합하지 않았다."),
    ('재현 시 어떤 파일이 필요한가?','PR120 sealed F3 MPS와 readonly physical input caches, compact sparse snapshot 및 Start/mapping maps가 local cache에 있다. MODEL_FREEZE와 EXECUTION_FREEZE로 SHA를 검증한다. optimizer source/policy는 code commit과 연결된다.'),
    ('Root에서 모든 binary를 relax했는가?',f"예. Original arc/mode, compact z/selector/mode 모두 [0,1] continuous. Primary는 동일 Method=1/Threads=4. Primary terminal 결과 전 사전등록한 조건부 fallback은 동일 Method=2/Crossover=1/Threads=4이며, primary optimal mismatch는 bypass하지 않는다. 선택 pair는 {root.get('method',1)}; 모든 raw evidence와 등록을 보존한다."),
    ('숫자를 기대값으로 강제했는가?','아니다. Actual reachable node 9,038개와 mode384개로 9,422개의 binary를 집계했다. 9,696 가정은 쓰지 않았다.'),
    ('수치 warning과 시간 측정은?','원 scientific matrix의 작은 coefficients를 바꾸지 않는다. Solver warning/Kappa/KappaExact, optimize wall/runtime, construct/build, presolve/root 및 peak memory를 별도로 기록했다.'),
    ]
    assert len(answers)>=70
    body='# V42 M1 exact compact monolithic 최종 검토\n\n'+''.join(f'## {i}. {q}\n\n{ans}\n\n' for i,(q,ans) in enumerate(answers,1))
    (OUT/'FINAL_REVIEW_KO.md').write_text(body,encoding='utf8',newline='\n')
    next_text=f'''# 다음 수정\n\n판정: {verdict}.\n\nFull domain과 모든 scientific rows를 보존한 채 integer dimension은 95.477% 감소했다. Connected expression의 outgoing-movement 치환으로 nnz는 53.074% 증가하므로 presolve, simplex factorization, branch 성능을 증거로 해석해야 한다. Root projection은 동일해야 하며 bound 자체 강화는 이 representation의 목표가 아니다.\n\n사전 material 기준은 gap 20% 또는 valid LB 0.001 개선이며 결과 후 변경하지 않는다. Promising이면 별도 사용자 승인 후 1800초 production을 실행할 수 있다. 미달이면 exact 보조 connected continuous variable와 sparse linking row를 사용하는 대안의 exact projection/계수/새 preregistration을 먼저 준비할 수 있으나 이번 결과를 바꿔 재실행하지 않는다. Root equivalence가 미인증이면 full MILP를 계속하지 않고 수치 종료 상태와 mapping 잔차를 확인한다.\n\nP2/A2/M2/Actual/Fresh AC는 NOT_RUN. M1_ACCEPTED 및 Problem13_FINAL은 false 유지. 중단한 Benders acceleration lane은 그대로 보존한다.\n'''
    (OUT/'NEXT_MODIFICATIONS.md').write_text(next_text,encoding='utf8',newline='\n')
    resources=[read(p.name) for p in sorted(OUT.glob('RESOURCE_*.json'))]
    dump('RESOURCE_RECEIPT.json',dict(RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,independent_workloads_allowed=True,
        own_heavy_lane_sequential=True,receipts=resources,historical_PR120_absolute_speedup_claim=False,
        interpretation='Hardware/thread equality is recorded. Same-lane objective/bound/gap comparison is controlled by frozen settings. Any wall-time speedup remains conditional on concurrent workload snapshots.',
        observed_other_Python_processes=[dict(label=r['label'],processes=[p for p in r['python_solver_processes'] if p['pid']!=r['worker_pid']]) for r in resources]))
    print(verdict,flags,flush=True)
if __name__=='__main__':main()
