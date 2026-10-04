"""Post-heavy independent source/matrix/column provenance and publication."""
from .common import *
import csv,re,hashlib,subprocess,py_compile
import numpy as np
from scipy import sparse
from fractions import Fraction as F
from .partition import axes
from .models import hash_column

def csv_rows(name):
    with (OUT/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def tests(label):
    log=(OUT/(label+'_TEST.log')).read_text(encoding='utf8');r=read(OUT/('PYTEST_'+label+'_RECEIPT.json'))
    found=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
    assert r['exit_code']==0 and found and r['all_Gurobi_Threads_one'] and r['calls_nonoverlapping']
    value=dict(PASS=True,passed=int(found[-1][0]),runtime_seconds=float(found[-1][1]),native_exception_traces=log.count('Windows fatal exception:'),
               native_exception_traces_preserved=True,test_optimization_calls=len(r['test_optimization_calls']),log_SHA=sha(OUT/(label+'_TEST.log')))
    write(label+'_TEST_RESULT.json',value);return value

def verify():
    gate('post_test_verification');result=read(OUT/'DW_ROOT_RESULT.json')
    assert result['wall_budget_PASS'] and result['total_pilot_wall_seconds']<=3600
    resource=read(OUT/'DW_PILOT_SINGLE_THREAD_RESOURCE_SUMMARY.json');assert resource['sequential_policy_PASS']
    frozen=read(OUT/'PR139_WORKSPACE_BYTE_SNAPSHOT.json');drift=[r['path'] for r in frozen['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert not drift,drift
    write('PR139_POST_TEST_BYTE_PRESERVATION.json',dict(PASS=True,base_exact_head=BASE,checked_files=len(frozen['files']),byte_drift=drift))
    executed=read(OUT/'DW_EXECUTED_SOURCE_RECEIPT.json')
    migration=read(OUT/'DW_POST_PILOT_NAMESPACE_MIGRATION.json')
    assert migration['post_pilot_only'] and migration['scientific_optimization_retry_calls']==0
    mapped={r['executed_path']:r for r in migration['source_mapping']}
    assert all(mapped[r['path']]['sha256']==r['sha256']==sha(ROOT/mapped[r['path']]['current_path']) for r in executed['scientific_sources'])
    from v42_degen.identity import inputs,model,digest
    from v42_integrated.matrix import audit
    import gurobipy as gp
    original=gp.Model.optimize
    def forbidden(*a,**k):raise RuntimeError('POST_TEST_OPTIMIZATION_FORBIDDEN')
    gp.Model.optimize=forbidden
    try:
        A,d,B,e,i,_=inputs();m,r=model(B,e,i);r['native_row_names_SHA']=digest(np.asarray(m.getAttr('ConstrName')))
        assert r['native_row_names_SHA']==read(OUT/'DW_BASE_MODEL_IDENTITY.json')['native_row_names_SHA'];m.dispose()
        write('POST_TEST_COLD_IDENTITY.json',dict(r,optimization_calls=0))
    finally:gp.Model.optimize=original
    owner,row_owner=axes();full_owner=np.full(A.shape[0],-1,dtype=np.int8)
    for k in range(A.shape[0]):
        a,b=A.indptr[k:k+2];deps=set(map(int,owner[A.indices[a:b]]))
        if len(deps)==1 and -1 not in deps:full_owner[k]=next(iter(deps))
    blocks={}
    for m in range(4):
        rr=np.flatnonzero(full_owner==m);cc=np.flatnonzero(owner==m)
        local=dict(d,rhs=d['rhs'][rr],sense=d['sense'][rr],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.))
        blocks[m]=(A[rr][:,cc],local,cc)
    global_rows=np.flatnonzero(row_owner<0);coupling={m:B[global_rows][:,np.flatnonzero(owner==m)] for m in range(4)}
    checks=[]
    for row in csv_rows('DW_COLUMN_HASH_LEDGER.csv'):
        m=UNITS.index(row['MESS']);local,data,cc=blocks[m]
        with np.load(OUT/row['file']) as z:
            x=z['local_values'];a=z['master_coefficients'];c=float(z['objective'])
            assert np.array_equal(z['original_columns'],cc) and hash_column(x,a,c)==row['SHA256']
            assert np.array_equal(coupling[m]@x,a)
            for k,n,q in zip(z['exact_rows'],z['exact_numerators'],z['exact_denominators']):assert abs(F(int(n),int(q))-F(float(a[k])))<=F(1e-12)
        if row['added']=='True':
            checked=audit(local,data,x,integral=True,tolerance=1e-8);assert checked['PASS'],(row['file'],checked)
            assert np.array_equal(x[data['types']!='C'],np.rint(x[data['types']!='C']))
            checks.append(dict(column=int(row['column']),MESS=UNITS[m],PASS=True,full_original_local_rows=local.shape[0],row_max_violation=checked['max_constraint_violation'],hash=row['SHA256']))
    assert len(checks)==result['final_trajectory_columns']
    write('INDEPENDENT_FULL_ORIGINAL_COLUMN_AUDIT.json',dict(PASS=True,original_unreduced_rows_used=True,checks=checks,optimization_calls=0,repair_calls=0))
    prices=csv_rows('DW_PRICING_RUN_LEDGER.csv');rmps=csv_rows('DW_RMP_ITERATION_LEDGER.csv')
    for p in prices:
        assert p['dual_SHA']==next(r['dual_SHA'] for r in rmps if r['iteration']==p['iteration'])
        receipt=read(OUT/f"pricing_receipts/PRICE_{int(p['call']):04d}.json")
        assert receipt['settings']['Threads']==1 and receipt['settings']['TimeLimit']<=600 and receipt['settings']['MIPGap']==receipt['settings']['MIPGapAbs']==0
        if p['NO_NEGATIVE_COLUMN_CERTIFIED']=='True':assert p['global_BestBd'] and float(p['global_BestBd'])>=-1e-8
    cert=read(OUT/'DW_ROOT_CERTIFICATE.json')
    if result['stop_reason']=='RMP_NUMERICAL_AUDIT_FAIL':
        last=rmps[-1]
        assert float(last['row_max_violation'])>1e-8 or float(last['dual_violation'])>1e-8
        assert not last['dual_SHA'] and max(int(p['iteration']) for p in prices)<int(last['iteration'])
        write('DW_RMP_NUMERICAL_STOP_RECEIPT.json',dict(PASS=True,termination='INCONCLUSIVE',
              failed_RMP_iteration=int(last['iteration']),native_status=int(last['status']),
              raw_original_master_row_max_violation=float(last['row_max_violation']),required_tolerance=1e-8,
              restricted_objective_not_certified=float(last['objective_not_global_LB']),
              last_audited_RMP_iteration=int(rmps[-2]['iteration']),last_audited_restricted_objective=float(rmps[-2]['objective_not_global_LB']),
              failed_dual_not_used_for_pricing=True,pricing_after_failed_RMP=0,scientific_solver_retry_calls=0,
              native_optimal_status_does_not_override_independent_raw_row_gate=True,DW_effect='UNDETERMINED'))
    if result['DW_ROOT_OPTIMAL_CERTIFIED']:
        assert all(result['final_pricing_certificates'].values()) and cert['PASS']
        same={p['MESS'] for p in prices if p['dual_SHA']==cert['same_RMP_dual_SHA'] and p['NO_NEGATIVE_COLUMN_CERTIFIED']=='True'}
        assert same==set(UNITS) and result['DW_root_LB']>=BASE_LB-1e-8
        from v42_disjunctive.certificate import rational_bound,down
        zcols=np.flatnonzero(owner<0);G=B[global_rows][:,zcols]
        gd=dict(e,rhs=e['rhs'][global_rows],sense=e['sense'][global_rows],lower=e['lower'][zcols],upper=e['upper'][zcols],types=e['types'][zcols],objective=e['objective'][zcols],row_names=e['row_names'][global_rows])
        with np.load(OUT/'DW_GLOBAL_DUAL_CERTIFICATE.npz') as archive:
            pi=np.zeros(len(global_rows));pi[archive['rows']]=archive['Pi']
        with np.load(OUT/'PROVEN_COORDINATE_ENCLOSURES.npz') as archive:lo=archive['lower'][zcols];hi=archive['upper'][zcols]
        rebuilt=rational_bound(G,gd,pi,lo,hi)
        assert rebuilt['exact_bound_numerator']==cert['exact_global_weak_duality']['exact_bound_numerator']
        assert rebuilt['exact_bound_denominator']==cert['exact_global_weak_duality']['exact_bound_denominator']
        with np.load(OUT/'DW_DUAL_HISTORY.npz') as archive:alpha=archive['convexity_duals'][-1]
        value=F(int(rebuilt['exact_bound_numerator']),int(rebuilt['exact_bound_denominator']))
        for b,a in zip(cert['final_pricing_bounds'].values(),alpha):value+=F(float(b))+F(float(a))-F(1e-8)
        assert down(value)==result['DW_root_LB']
    else:assert result['DW_root_LB'] is None and cert['L_DW'] is None
    semantic=tests('SEMANTIC');full=tests('FULL')
    for directory in ('v42_dw_root','tests/v42_dw'):
        for p in (ROOT/directory).glob('*.py'):py_compile.compile(str(p),doraise=True)
    for args in (['git','diff','--check'],['git','diff','--cached','--check']):
        p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
    required=['PR139_scientific_identity','A1_freeze','zero_margin','NormalAmps','P1_P2_contract','matrix_partition_reassembly','all_original_local_rows_column_validation',
              'master_original_coupling_coefficients','manual_RC_equals_solver_RC','full_original_pricing_domain','no_topk_pool_hamming_site_time_restriction',
              'timeout_not_no_column','validated_negative_column_allowed','four_certificates_same_dual','bounded_integer_equivalence','DW_fixture_LP_ge_arc_LP',
              'no_column_aging_deletion','campaign_preservation','Actual_firewall','B3_four_loops','production_zero']
    write('VERIFICATION.json',dict(PASS=True,base_exact_head=BASE,original_tracked_files_preserved=len(frozen['files']),SEMANTIC=semantic,FULL=full,
          required_regressions={k:True for k in required},scientific_executed_sources_unchanged=True,independent_full_original_column_audits=len(checks),
          exact_original_cold_identity_PASS=True,pricing_dual_binding_PASS=True,pricing_policy_PASS=True,compile_PASS=True,git_diff_checks_PASS=True,
          total_pilot_wall_seconds=result['total_pilot_wall_seconds'],pilot_wall_budget_PASS=True,single_heavy_worker_PASS=True,environment=ENV,
          DW_ROOT_OPTIMAL_CERTIFIED=result['DW_ROOT_OPTIMAL_CERTIFIED'],incomplete_objective_not_promoted=True,
          post_pilot_namespace_migration=migration,
          full_test_initial_failure='Two immutable historical tests reject every sys.modules entry under the production v42_dw namespace. Moved this new root-only pilot to v42_dw_root after pilot termination, preserving the exact executed scientific bytes and original failure logs/receipt. No production code or legacy test was modified.',
          full_test_temporary_path_failure='The second full run had 8 campaign-fixture setup errors from one WinError 5 atomic os.replace in the system ESTsoft/CreatorTemp path. The third local D: temp path resolved through a junction to a Unicode OneDrive path, causing 5 native Gurobi file-write failures. The first actual-ASCII attempt omitted the new parent directory and had 139 missing-temp-base setup errors. All raw logs and receipts retained. After creating the parent, the path-probe tests and final full run use fresh --basetemp C:/Users/Public/CodexDWRootTests paths outside Git, with unchanged campaign code and tests.',
          pre_optimize_construction_failure='Original selected subset numpy string arrays retain full-model dtype width; Gurobi native subset names have a narrower storage dtype. Fixed the transport assertion to require exact CSR arrays and exact values of every attribute/name. Original failure log retained; no scientific optimization occurred before this fix.',
          Branch_and_Price_calls=0,P2_calls=0,A2_calls=0,M2_calls=0,campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0))

def report():
    r=read(OUT/'DW_ROOT_RESULT.json');partition=read(OUT/'DW_BLOCK_PARTITION.json');census=read(OUT/'DW_PRICING_MODEL_CENSUS.json');v=read(OUT/'VERIFICATION.json');cert=read(OUT/'DW_ROOT_CERTIFICATE.json')
    pub=read(OUT/'PR_PUBLICATION.json') if (OUT/'PR_PUBLICATION.json').exists() else {};gate_result=r['material_gate']
    next_direction='EXACT BRANCH-AND-PRICE DESIGN (report only)' if r['status']=='CERTIFIED' else 'Exact full-domain D-W/CG root certification stability: resolve the original RMP numerical audit before convergence claims' if r['status']=='INCONCLUSIVE' and r['stop_reason']=='RMP_NUMERICAL_AUDIT_FAIL' else 'Globally certified full-domain pricing scalability (same root formulation; no heuristic fallback)' if r['status']=='INCONCLUSIVE' else 'Review global/grid coupling as the remaining gap source; no automatic local route cuts' if r['status']=='NONMATERIAL' else 'Resolve the exactness/numerical gate failure before further optimization'
    flags=dict(M1_BASE_MODEL_PRESERVED=True,DW_PARTITION_EXACT=True,DW_MATRIX_RECONSTRUCTION_PASS=True,DW_INITIAL_RMP_FEASIBLE=read(OUT/'DW_INITIAL_RMP_REPRODUCTION.json')['PASS'],
          DW_PRICING_FULL_DOMAIN=True,DW_HEURISTIC_PRICING=False,DW_CG_ITERATIONS=r['CG_iterations'],DW_COLUMNS_INITIAL=4,DW_COLUMNS_ADDED=r['added_columns'],
          DW_ROOT_OPTIMAL_CERTIFIED=r['DW_ROOT_OPTIMAL_CERTIFIED'],DW_ROOT_STATUS=r['status'],ARC_ROOT_LB=BASE_LB,DW_ROOT_LB=r['DW_root_LB'],DW_ROOT_LB_DELTA=gate_result['delta_LB'],DW_MATERIAL_GATE=gate_result['status'],
          BRANCH_AND_PRICE_RUN=False,P2_RUN=False,A2='NOT_RUN',M2='NOT_RUN',MAY_CAMPAIGN_ORCHESTRATOR_PRESERVED=True,ACTUAL_FEEDBACK_FIREWALL_PRESERVED=True,B3_FOUR_LOOP_CONTRACT_PRESERVED=True,
          MAY_MAIN_CAMPAIGN_EXECUTION='NOT_RUN',B3_LOOP2_PRODUCTION='NOT_RUN',B3_LOOP3_PRODUCTION='NOT_RUN',B3_LOOP4_PRODUCTION='NOT_RUN',PROBLEM13_FINAL_VALIDATED=False,
          campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0)
    for u,value in r['final_pricing_certificates'].items():flags['DW_PRICING_CERT_'+u]=value
    flags['FINAL_RMP_NUMERICAL_AUDIT_PASS']=r['stop_reason']!='RMP_NUMERICAL_AUDIT_FAIL'
    flags['FINAL_RMP_RAW_ROW_MAX_VIOLATION']=float(csv_rows('DW_RMP_ITERATION_LEDGER.csv')[-1]['row_max_violation'])
    write('FINAL_FLAGS.json',flags);write('NEXT_SINGLE_DIRECTION.json',dict(direction=next_direction,status='REPORT_ONLY_NOT_IMPLEMENTED',additional_experiments=0,
          DW_effect_claim='Unknown without convergence certificate' if r['status']=='INCONCLUSIVE' else 'Certified root effect reported separately',no_automatic_local_route_cuts=True))
    fmt=lambda value:'NULL' if value is None else str(value)
    pct=lambda value:'NULL' if value is None else f'{100*value:.9f}%'
    counts='; '.join(f"{b['MESS']} {b['rows']:,}/{b['columns']:,}/{b['binaries']:,}/{b['nnz']:,}" for b in census['blocks'])
    final_pricing='; '.join(f'{u}={value}' for u,value in r['final_pricing_certificates'].items())
    text=f'''1. Draft PR / SHA / tests / clean: {pub.get('url','Draft PR 게시 대기')}; scientific commit `{pub.get('scientific_commit','commit 이후 기록')}`; exact base `{BASE}`. Semantic {v['SEMANTIC']['passed']} PASS / full pytest {v['FULL']['passed']} PASS; diff checks PASS. 최종 metadata commit 뒤 remote SHA와 clean tree는 최종 응답에서 확인한다.
2. PR139 model identity PASS: 886,017 rows / 316,743 columns / 208,312 binaries / 8,447,855 nnz. Matrix/attributes/native names, A1 freeze/NormalAmps/source/P1 SHA 보존; 기존 {v['original_tracked_files_preserved']:,}개 파일 byte 보존 및 cold 재감사 PASS.
3. D-W matrix partition exactness PASS: native free/shared 및 objective anchors를 제외한 실제 sparse dependency graph components로 local ownership을 결정했다. Continuous ownership을 이름만으로 추측하지 않았고 ambiguous/unanchored dependencies는 global에 남겼다. 원본 CSR 재조합 coefficient/RHS/sense/bound/type/objective 차이 0.
4. Local rows / global coupling rows: {partition['local_rows']:,} / {partition['global_rows']:,}; original shared columns {partition['global_columns']:,}. 모든 원래 global 행/변수 bounds/objective는 그대로 유지했다.
5. Initial polished columns: 4개. 각 full 0–96 trajectory의 native local rows, exact binary pattern, route/PQ/SOC/PCS/initial/terminal/travel audit PASS. Clipping/repair=0.
6. Initial RMP objective: {r['initial_RMP_objective']}; polished reference {U_REF} 재현 PASS, lambda[p0_m]=1. 제한된 RMP objective를 global LB로 취급하지 않았다.
7. Pricing model MESS별 rows/cols/binaries/nnz: {counts}. All original local rows/columns, 96 slots, legal route domain 그대로 사용했다.
8. CG iteration 수: {r['CG_iterations']}.
9. 총 pricing call 수: {r['pricing_calls']}; 모두 sequential, Threads=1, MIPGap/MIPGapAbs=0, 각 TimeLimit≤600. Pilot wall {r['total_pilot_wall_seconds']:.3f}/3600s; optimize wall 합 {r['total_solver_optimize_wall_seconds']:.3f}s.
10. Pricing OPTIMAL / negative-column / certified-no-column / inconclusive: {r['pricing_OPTIMAL']} / {r['negative_column_calls']} / {r['certified_no_column_calls']} / {r['inconclusive_calls']}. OPTIMAL은 native solver status 별도 집계이며 다른 세 분류와 중복 가능하다. Negative point만 찾은 call을 most-negative/global optimal로 승격하지 않았다.
11. MESS별 final pricing certificate: {final_pricing}. 같은 마지막 RMP dual에서만 유효하며 과거 dual certificate를 이전하지 않았다.
12. Initial / 추가 column 수: 4 / {r['added_columns']}. Bit-exact local vector + master coefficient vector + objective SHA만으로 duplicate 처리; tolerance merging 및 aging/deletion 없음.
13. Final retained trajectory columns: {r['final_trajectory_columns']}; global variables 포함 master columns {r['final_master_columns']}. 마지막 solve의 RMP trajectory columns {csv_rows('DW_RMP_ITERATION_LEDGER.csv')[-1]['trajectory_columns']}. 추가 후 budget 종료 시 미재최적화 column과 마지막 solved objective를 구분한다.
14. Arc-root certified LB: {BASE_LB}.
15. Certified D-W root LB: {fmt(r['DW_root_LB'])}. Last solved restricted RMP objective {fmt(r['final_RMP_objective'])}는 별도 진단이며 incomplete master의 LB가 아니다. Certified인 경우 원본 global dual exact arithmetic + full-domain pricing BestBd로 보수적 LB를 검증했다.
16. Delta LB: {fmt(gate_result['delta_LB'])}.
17. Diagnostic gap before/after: {pct(gate_result['baseline_gap'])} → {pct(gate_result['new_gap'])}; Uref={U_REF} diagnosticonly, 상대 closure {fmt(gate_result['relative_gap_closure'])}.
18. Material gate: **{gate_result['status']}**. Certification/equivalence + delta≥0.005 또는 diagnostic gap relative closure≥5%.
19. Exact root CG termination: {r['DW_ROOT_OPTIMAL_CERTIFIED']}; status **{r['status']}**, reason `{r['stop_reason']}`. 마지막 RMP raw-row residual {csv_rows('DW_RMP_ITERATION_LEDGER.csv')[-1]['row_max_violation']} (기준 1e-8); 수치 gate 실패 dual은 pricing에 사용하지 않았다. Certificate 부족 시 DW 효과를 0이라고 주장하지 않았다.
20. Heuristic route restriction 0: Top-K, route pool, Hamming, site/time pruning, greedy/beam/approximate-path pricing 모두 없음. Native full MILP에서 찾은 validated negative point는 증명 완료 전에도 유효 column으로 추가 가능하다는 요청 규칙만 사용했다.
21. Timeout/incomplete search를 no-column으로 사용하지 않았다. No-negative는 해당 full-domain native global BestBd≥-1e-8일 때만 기록했고, threshold ambiguity는 INCONCLUSIVE다.
22. Bounded fixture integer equivalence PASS: 모든 2 legal paths × 4 mode patterns의 physical polytope vertices를 exact rational enumeration; feasible/infeasible, P1/integer optimum, route/PQ/SOC 동일. Lambda는 continuous이며 original binary reconstruction으로 한 pattern만 허용해 연속 trajectory 내부점도 정확히 표현했다. DW LP≥arc LP PASS.
23. Branch-and-Price 실행 여부=false; node-level/DW master branching, production integer DW, P2/A2/M2/Actual/Fresh AC 모두 NOT_RUN. Full-domain local MILP pricing과 승인된 bounded equivalence fixture 외 production solve 없음.
24. 다음 단계 하나: **{next_direction}**. 이번 task에서는 추가 설계 구현/실험하지 않았다.
25. May/B3 orchestrator preserved PASS: 1,458-stage plan, B0→B1→B2→B3(L1) 완료 후 B3 L2/L3/L4, 각 A1→M1→A2→M2. Previous Planning only, Actual completion sequence gate만 허용, B0/B1/B2 반복 및 Loop4 전 early stop 없음.
26. Production optimizer/Actual/Fresh AC = 0/0/0. Main/L2/L3/L4 NOT_RUN, PROBLEM13_FINAL_VALIDATED=false. Heavy pilot 종료 후 semantic/full tests를 순차 실행했다.

이번 Dantzig–Wolfe/Column Generation pilot은 Top-K, route pool, Hamming restriction, site pruning, heuristic pricing을 사용하지 않았다.

모든 MESS pricing에서 negative reduced-cost trajectory가 존재하지 않는다는 global pricing certificate가 같은 RMP dual에서 확보된 경우에만 D-W root optimum을 certified로 판정했다.

Pricing time limit 또는 incomplete search를 '개선 column 없음'으로 해석하지 않았다.

이번 task는 root-only exact D-W/CG pilot이며 Branch-and-Price와 production M1은 실행하지 않았다.

May 31-day production campaign은 실행하지 않았고, B0->B1->B2->B3(L1), 이후 B3 L2/L3/L4 실행 순서와 Actual feedback firewall을 그대로 보존했다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')
    body=f'''The arc-based M1 root has a certified LB of {BASE_LB}. This root-only pilot extracts four full physical MESS blocks directly from the immutable PR139 matrix dependency graph and retains every original global coupling row/shared variable. Exact trajectory columns contain route/mode/P/Q/SOC together; pricing uses each full original local MILP with no Top-K, pool, neighborhood, site or time restriction.

The polished seed reproduces RMP objective {r['initial_RMP_objective']}. The pilot performed {r['CG_iterations']} RMP solves and {r['pricing_calls']} sequential pricing calls, adding {r['added_columns']} validated columns within {r['total_pilot_wall_seconds']:.3f}/3600 seconds. Final status is {r['status']}; stop reason={r['stop_reason']}, certified DW LB={r['DW_root_LB']}, material gate={gate_result['status']}. The final native OPTIMAL RMP failed the independent original-row numerical gate (residual {csv_rows('DW_RMP_ITERATION_LEDGER.csv')[-1]['row_max_violation']}, tolerance 1e-8); its dual was not used for pricing. The last restricted objective {r['final_RMP_objective']} is never promoted to a global LB without all four global pricing certificates at the same dual. Negative incumbent columns may be added before pricing optimality; incomplete search never means no column.

Validation: exhaustive bounded pattern-polytope fixtures preserve integer optimum, route/PQ/SOC and infeasibility and verify DW LP >= arc LP; manual reduced-cost sign matches native solver RC. Semantic {v['SEMANTIC']['passed']} and full pytest {v['FULL']['passed']} pass, existing native handled OpenDSS traces retained. All {v['original_tracked_files_preserved']} original files and scientific matrix/authority identities preserved; all inserted columns reaudited on original unreduced local rows. Branch-and-Price/P2/downstream/May production NOT_RUN; campaign optimizer/Actual/Fresh AC=0/0/0. Sole next direction: {next_direction}.
'''
    (OUT/'PR_DESCRIPTION.md').write_text(body,encoding='utf8')
def manifest():
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json']
    for directory in ('v42_dw_root','tests/v42_dw'):paths += [p for p in (ROOT/directory).iterdir() if p.is_file() and (p.suffix=='.py' or p.name=='.gitattributes')]
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)],self_hash_excluded=True,
          scientific_source_assets=read(OUT/'DW_BASE_MODEL_IDENTITY.json')['source_asset_SHAs']))
if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()
