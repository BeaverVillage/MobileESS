"""Honest closeout at the authorized nonconverged-root stop gate."""
from .common import *
from v42_dw_continuation.audit_helpers import check_segment_chain
from v42_m_stage_root.common import preserve_old
import subprocess
import math

def rows(path):
    with Path(path).open(encoding='utf8-sig',newline='') as f:return list(csv.DictReader(f))

def run():
    result=read(OUT/'DW_CONTINUATION_FINAL_RESULT.json');cp=read(OUT/'DW_CHECKPOINT_LATEST.json')
    assert not result['DW_ROOT_OPTIMAL_CERTIFIED'],'Converged root must advance through B&P; do not close here'
    preserved=preserve_old();budget=check_segment_chain(OUT);assert budget['total']<=1800
    pool=read(OUT/'DW_CONTINUATION_FULL_POOL_AUDIT.json');assert pool['PASS']
    reg=read(OUT/'REGRESSION_RECEIPT.json');assert reg['exit_code']==0
    bench=read(OUT/'HYBRID_PRICING_CLEAN_BENCHMARK.json');selection=read(OUT/'HYBRID_PRICING_SELECTION.json')
    assert len(bench['units'])==4 and not selection['HYBRID_SELECTED'] and bench['total_active_benchmark_wall_seconds']<=600
    certificate=read(OUT/'DW_CONTINUATION_FINAL_CERTIFICATION.json')
    write('ROOT_CG_FINAL_CERTIFICATE.json',dict(ROOT_CG_CONVERGED=False,exact_root_LP_objective=None,
        last_restricted_LP_objective=result['smallest_RMP_upper'],best_certified_LB=result['best_certified_LB'],
        materiality=result['materiality'],root_pool_size=result['retained_columns'],
        CG_rounds=result['discovery_rounds'],pricing_calls=result['new_pricing_calls'],
        historical_development_native=read(OUT/'ROOT1604_RESUME_AUTHORITY.json')['historical_total_native'],
        new_root_development_native=budget['total'],new_root_sum_model_native=result['sum_native_optimize_wall'],
        total_historical_plus_new_root_native=result['cumulative_optimize'],
        build_seconds=result['build_seconds'],elapsed_build_audit_and_optimization=result['elapsed_including_build_audit'],
        stop_reason=result['stop_reason'],last_certification=certificate,
        exact_optimum_claimed=False,existing_numerical_authority=EPS,automatic_extension=False))
    table('ROOT_CG_PROGRESS.csv',cp['restart_state']['rounds'])
    write('ROOT_CG_FULL_POOL_AUDIT.json',pool)
    notrun=dict(status='NOT_RUN_PREREQUISITE',reason='M1_ROOT_NOT_CONVERGED',native_optimization_seconds=0)
    for name in ('BAP_INTEGRATION_AUDIT.json','BAP_DEVELOPMENT_RESULT.json','M1_FRESH_3600_CANARY.json',
        'M1_PHYSICAL_AUDIT.json','A2_PREREQUISITE_AUTHORITY.json','M2_CURRENT_FORMULATION_AUDIT.json',
        'M2_3600_CANARY.json','M2_PHYSICAL_AUDIT.json'):
        write(name,notrun)
    write('M1_FINAL_ALGORITHM_FREEZE.json',dict(M1_ALGORITHM_READY=False,status='NOT_FROZEN',
        reason='M1_ROOT_NOT_CONVERGED',P1='NOT_ACCEPTED',P2_movement_energy='NOT_RUN',
        P2_movement_count='NOT_RUN',development_source_commit=cp['source_commit'],
        PRICING_BACKEND=selection['PRICING_BACKEND'],fresh_canary_launched=False,
        fresh_runtime_uses_development_columns=False))
    for name,fields in [('BAP_NODE_LEDGER.csv',['node','status','native_seconds']),
        ('BAP_GLOBAL_BOUND_LEDGER.csv',['event','global_LB','incumbent','gap']),
        ('M1_FRESH_RUNTIME_LEDGER.csv',['stage','native_seconds','budget_total']),
        ('M2_RUNTIME_LEDGER.csv',['stage','native_seconds','budget_total'])]:table(name,[],fields)
    resource=[]
    for filename in ('FAILED_ATTEMPT_HYBRID_RESOURCE_LEDGER.csv','HYBRID_REMAINING_RESOURCE_LEDGER.csv',
                     'DW_CONTINUATION_RESOURCE_LEDGER.csv'):
        for r in rows(OUT/filename):resource.append(dict(source_ledger=filename,**r))
    table('RESOURCE_LEDGER.csv',resource)
    peaks=dict(min_available_RAM=min(float(r['available_RAM']) for r in resource),
        max_commit_percent=max(float(r['commit_percent']) for r in resource),
        max_tree_RSS=max(float(r.get('total_tree_RSS') or r.get('RSS') or 0) for r in resource),
        max_hard_page_input_pages_per_sec=max(float(r['hard_page_input_pages_per_sec']) for r in resource if r.get('hard_page_input_pages_per_sec')),
        sampled_peaks_only=True)
    authority=read(OUT/'ROOT1604_RESUME_AUTHORITY.json')
    ledgers=[dict(category='A_HISTORICAL_DEVELOPMENT',native_union_seconds=authority['historical_total_native'],
        production_runtime=False),dict(category='B_HYBRID_BENCHMARK',native_union_seconds=None,
        active_wall_seconds=bench['total_active_benchmark_wall_seconds'],production_runtime=False),
        dict(category='C_ROOT_CONTINUATION_DEVELOPMENT',native_union_seconds=budget['total'],
            sum_model_native_seconds=result['sum_native_optimize_wall'],production_runtime=False)]
    for category in ('D_BAP_DEVELOPMENT','E_FRESH_M1_CANARY','F_M2_CANARY'):
        ledgers.append(dict(category=category,status='NOT_RUN_PREREQUISITE',native_union_seconds=0,
            production_runtime=category in ('E_FRESH_M1_CANARY','F_M2_CANARY')))
    table('RUNTIME_CATEGORY_LEDGER.csv',ledgers)
    freeze=read(OUT/'ROOT_EXECUTION_FREEZE.json')
    assert all(sha(ROOT/p)==h for p,h in freeze['sources'].items())
    assert all(sha(OUT/p)==h for p,h in freeze['authorities'].items())
    verification=dict(PASS=True,final_stop_state='M1_ROOT_NOT_CONVERGED',PR152_preserved_files=preserved,
        source_freeze_unchanged=True,root_development_budget=budget,resource_peaks=peaks,
        regression=reg,HYBRID_SELECTED=False,ROOT_CG_CONVERGED=False,M1_ALGORITHM_READY=False,
        BAP_nodes=0,BAP_incumbent=None,BAP_global_LB=None,BAP_gap=None,
        M1_fresh_canary_status='NOT_RUN_PREREQUISITE',M2_canary_status='NOT_RUN_PREREQUISITE',
        full_May_B2_B3_L1_L4_launched=False,backend_changed_during_root=False,
        development_columns_in_fresh_runtime=False,foreign_native=read(OUT/'ROOT_FOREIGN_NATIVE_OBSERVATION.json'))
    write('VERIFICATION.json',verification)
    review=f'''# V42 M-stage exact completion 검토

최종 중단 상태: **M1_ROOT_NOT_CONVERGED**. Root 미수렴이므로 B&P, P2, fresh M1/M2 canary 및 May B2/B3/L1–L4 production은 실행하지 않았다.

| 항목 | 결과 |
|---|---|
| Hybrid global optimum 동등성 | 증명 실패; 네 MESS 모두 점검 |
| Hybrid/Gurobi 속도 | 인증 실패로 INCONCLUSIVE; 20% 개선 주장 없음 |
| 선택 pricing backend | ORIGINAL_GUROBI_EXACT |
| 신규 root Discovery rounds | {result['discovery_rounds']} |
| 신규 RMP / pricing calls | {result['new_RMP_solves']} / {result['new_pricing_calls']} |
| 최종 retained pool | {result['retained_columns']} |
| Exact root LP objective | 미확정 |
| 최저 audited restricted LP upper | {result['smallest_RMP_upper']:.16g} |
| Certified LB | {result['best_certified_LB']:.16g} |
| Exact root CG convergence | false |
| Materiality | {result['materiality']} |
| 신규 root development native interval union | {budget['total']:.6f}초 / 1800초 |
| 신규 root 모델별 native 시간 합계 | {result['sum_native_optimize_wall']:.6f}초 |
| 기존 development native union | {authority['historical_total_native']:.6f}초 |
| 기존 + 신규 development native union | {result['cumulative_optimize']:.6f}초 |
| Root build | {result['build_seconds']:.6f}초 |
| Root build/audit/solve 전체 경과 | {result['elapsed_including_build_audit']:.6f}초 |
| B&P nodes / incumbent / global LB / gap | 0 / 미실행 / 미실행 / 미실행 |
| M1 P1 / P2 movement energy / count | 미수락 / 미실행 / 미실행 |
| M1 development acceptance | false |
| Fresh M1 runtime / status | 0초 / NOT_RUN_PREREQUISITE |
| A2 prerequisite / current M2 formulation | 미평가 / 미평가 |
| M2 runtime / status | 0초 / NOT_RUN_PREREQUISITE |
| 최저 가용 RAM | {peaks['min_available_RAM']/1024**3:.3f} GiB |
| 최고 commit | {peaks['max_commit_percent']:.3f}% |
| 최고 작업 트리 RSS | {peaks['max_tree_RSS']/1024**3:.3f} GiB |
| 회귀검증 | REGRESSION_TESTS.log 및 REGRESSION_RECEIPT.json 참조 |

원래 MESS01 Gurobi pricing은 완료된 log/point를 복구했으며 재실행하지 않았다. Hybrid의 RAW_PI_SIGN_INVALID 검증 실패를 보존하고, 사용자 중단 이후 나머지 세 MESS만 비교했다. Benchmark 두 실행 구간의 active wall 합계는 {bench['total_active_benchmark_wall_seconds']:.6f}초이다. 사용자 중단을 포함한 시간을 단일 continuous wall 성능 결과로 주장하지 않았다. 동등성과 속도 개선이 입증되지 않아 기존 pricing backend의 reject/freeze 결정을 그대로 유지했다.

1800초 신규 root grant는 역사적 예산과 분리했다. 병렬 pricing의 예산은 PR152와 동일한 optimize interval union으로 집계했으며, 모델별 native 합계도 별도 공개한다. Build/audit/wait는 production runtime으로 바꾸어 보고하지 않는다. 중단 사유는 {result['stop_reason']}이다. RMP upper는 fractional restricted-master 상한이며, 정수 M1 incumbent acceptance가 아니다.

PR152의 1,604-column checkpoint는 M1 알고리즘 개발 및 exact root completion에만 사용했으며, 논문용 fresh M1 runtime 측정에는 development checkpoint에서 학습된 column을 주입하지 않았다.

Hybrid DP-LP pricing은 full original pricing problem과 global optimum equivalence가 증명된 경우에만 exact pricing backend로 채택했다. 이번 실행은 증명 실패로 미채택이다.

Root CG는 모든 pricing subproblem의 exact nonnegative reduced-cost certificate가 확보된 경우에만 converged로 판정했다. 이번 실행의 converged 판정은 false이다.

Branch-and-Price는 exact node pricing과 valid global bounds를 유지했으며, 휴리스틱 incumbent만으로 node 또는 M1을 acceptance하지 않았다. 이번 task에서는 root 선행조건 실패로 B&P를 실행하지 않았으므로 실제 B&P 검증 완료를 주장하지 않는다.

최종 M1/M2 production-style canary는 각각 3600초 stage budget을 초과하지 않았으며, 시간 초과 시 자동 완화나 추가 예산 없이 FAIL로 종료했다. 이번 task에서는 canary가 선행조건 실패로 미실행이므로 PASS/FAIL_TIME_LIMIT 실행 결과를 주장하지 않는다.

Commit/Draft PR는 PUBLICATION_RECEIPT.json에 기록한다. PR152/PR154 history를 수정하지 않고 새 child branch에서만 변경했다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(review,encoding='utf8')
    manifest={p.relative_to(ROOT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and
        p.name not in ('SHA256_MANIFEST.json','PUBLICATION_RECEIPT.json') and not p.name.endswith('.tmp')}
    write('SHA256_MANIFEST.json',dict(files=manifest,publication_receipt_excluded_to_avoid_self_reference=True))
    print('FINAL_STOP M1_ROOT_NOT_CONVERGED',result['retained_columns'],budget['total'],flush=True)

if __name__=='__main__':run()
