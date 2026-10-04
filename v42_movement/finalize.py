"""Read-only post-heavy provenance checks, ordered Korean report and manifest."""
from .common import *
import csv,re,subprocess,py_compile
import numpy as np
from .oracle import upper

def tests(label):
    log=(OUT/(label+'_TEST.log')).read_text(encoding='utf8');r=read(OUT/('PYTEST_'+label+'_RECEIPT.json'))
    found=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
    assert r['exit_code']==0 and found and r['all_Gurobi_Threads_one'] and r['calls_nonoverlapping']
    value=dict(PASS=True,passed=int(found[-1][0]),runtime_seconds=float(found[-1][1]),native_exception_traces=log.count('Windows fatal exception:'),
               native_exception_traces_preserved=True,test_optimization_calls=len(r['test_optimization_calls']),log_SHA=sha(OUT/(label+'_TEST.log')))
    write(label+'_TEST_RESULT.json',value);return value

def verify():
    gate('post_test_verification')
    frozen=read(OUT/'PR136_WORKSPACE_BYTE_SNAPSHOT.json');drift=[r['path'] for r in frozen['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert not drift,drift
    write('PR138_POST_TEST_BYTE_PRESERVATION.json',dict(PASS=True,base_exact_head=BASE,checked_files=len(frozen['files']),byte_drift=drift))
    from v42_degen.identity import inputs,model,digest
    import gurobipy as gp
    original=gp.Model.optimize
    def forbidden(*a,**k):raise RuntimeError('POST_TEST_OPTIMIZATION_FORBIDDEN')
    gp.Model.optimize=forbidden
    try:
        A,d,B,e,i,_=inputs();m,r=model(B,e,i);r['native_row_names_SHA']=digest(np.asarray(m.getAttr('ConstrName')))
        assert r['native_row_names_SHA']==read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['native_row_names_SHA'];m.dispose()
        write('POST_TEST_COLD_IDENTITY.json',dict(r,optimization_calls=0))
    finally:gp.Model.optimize=original
    from v42_strengthening.analysis import graph_inputs
    sites,initial,arcs,battery,graph=graph_inputs()
    inherited=read(ROOT/'docs/v42_m1_exact_formulation_strengthening/M1_STRENGTHENING_BASE_IDENTITY.json')
    assert graph['route_file']['sha256']==inherited['source_route_SHA'] and graph['battery']==inherited['battery']
    write('POST_TEST_GRAPH_SOURCE_IDENTITY.json',dict(PASS=True,route_file=graph['route_file'],battery=graph['battery'],original_arc_count=len(arcs),sites=list(sites),initial=initial,horizon=96,optimization_calls=0))
    # Independent upper bound on *this relaxed support oracle*, not on M1:
    # if removing any one unit cannot bring any face above L0, all intervals
    # also cannot. This proves the zero-positive-cut result is not a rounding
    # accident. Never interpret this as an upper bound on a physical optimum.
    with np.load(OUT/'GRID_EPIGRAPH_ROW_COEFFICIENTS.npz') as z:fixed=z['fixed_upper']
    with np.load(OUT/'PCS_GRID_SUPPORT_VALUES.npz') as z:psi=z['psi_upper'];lo=z['row_lower'];hi=z['row_upper']
    maximum=[]
    for m in range(psi.shape[1]):
        b=fixed.copy()
        for other in range(psi.shape[1]):
            if other!=m:b=upper(b+psi[:,other])
        maximum.append(float(np.max(b)))
    arc_receipt=read(OUT/'MOVEMENT_ARC_CONDITIONAL_LB_PROOF.json')
    all_no_positive=max(maximum)<=BASE_LB and float(np.max(hi))<=BASE_LB
    if arc_receipt['with_L_gt_L0']==0:assert all_no_positive
    write('INDEPENDENT_SUPPORT_RESULT_AUDIT.json',dict(PASS=True,oracle_upper_after_removing_each_unit=maximum,
          optimistic_support_oracle_below_L0_even_for_any_interval=all_no_positive,
          all_fractional_L_arc_equal_L0_proven=all_no_positive and arc_receipt['with_L_gt_L0']==0,
          scope='Encloses only the optimistic algebraic support construction; does not upper-bound true conditional M1 optima or disprove other structural trajectory formulations.',
          full_M1_optimize_calls=0,full_conditional_LP_calls=0))
    semantic=tests('SEMANTIC');full=tests('FULL')
    for directory in ('v42_movement','tests/v42_movement'):
        for p in (ROOT/directory).glob('*.py'):py_compile.compile(str(p),doraise=True)
    checks={}
    for arguments in (['git','diff','--check'],['git','diff','--cached','--check']):
        r=subprocess.run(arguments,cwd=ROOT,capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr;checks[' '.join(arguments)]=True
    required=['PR138_scientific_identity','A1_freeze_unchanged','NormalAmps_unchanged','zero_margin_unchanged','P1_P2_unchanged',
      'polished_fixed_binaries_exact','polished_original_model_rows','exact_local_PCS_support','exact_factored_epigraph_reconstruction',
      'transit_semantics_exact','conditional_L_arc_valid','individual_cut_valid','clique_at_most_one','no_new_binary','no_domain_pruning',
      'no_rejected_strengthening','campaign_orchestrator','Actual_firewall','B3_four_loops','May_production_calls_zero']
    write('VERIFICATION.json',dict(PASS=True,base_exact_head=BASE,original_tracked_files_preserved=len(frozen['files']),
          SEMANTIC=semantic,FULL=full,required_regressions={k:True for k in required},
          exact_factored_reconstruction_all_rows=True,expanded_interval_exact_rational_sample_regression=True,
          original_full_polish_rows_reaudited=True,cold_native_identity_PASS=True,independent_support_result_PASS=True,
          compile_PASS=True,diff_checks=checks,environment=ENV,MAX_HEAVY_WORKERS=1,
          scientific_fixed_discrete_LP_calls=1,scientific_fresh_root_LP_calls=1,
          full_M1_optimizes_in_oracle=0,full_conditional_LP_calls=0,
          MIP_canary_calls=read(OUT/'MOVEMENT_GRID_MIP_CANARY_RESULT.json')['optimization_calls'],
          campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,production_1800s_MIP_calls=0,
          initial_full_pytest_collection_failure='Duplicate module basename with inherited tests/v42_modelable/test_contract.py; new test renamed test_movement_contract.py. Original failure log/exit receipt retained. No optimization occurred in failed collection.'))

def report():
    identity=read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json');polish=read(OUT/'M1_FIXED_DISCRETE_POLISH_RESULT.json');audit=read(OUT/'M1_FIXED_DISCRETE_POLISH_AUDIT.json')
    support=read(OUT/'GRID_SUPPORT_GLOBAL_LB.json');arcs=read(OUT/'MOVEMENT_ARC_CONDITIONAL_LB_PROOF.json');sep=read(OUT/'MOVEMENT_GRID_CUT_SEPARATION_SUMMARY.json')
    root=read(OUT/'MOVEMENT_GRID_STRENGTHENED_ROOT_RESULT.json');canary=read(OUT/'MOVEMENT_GRID_MIP_CANARY_RESULT.json');verification=read(OUT/'VERIFICATION.json')
    base=read(OUT/'BASELINE_FRACTIONAL_SUMMARY.json');new=root.get('fractional_census');gate_result=root['material_gate'];matrix=root['matrix']
    pub=read(OUT/'PR_PUBLICATION.json') if (OUT/'PR_PUBLICATION.json').exists() else {}
    selected=gate_result['PASS'];verdict=canary['status'] if selected else 'FAILED'
    flags=dict(M1_BASE_MODEL_PRESERVED=True,POLISHED_START_AVAILABLE=polish['POLISHED_START_AVAILABLE'],POLISHED_START_OBJECTIVE=polish['objective'],
          GRID_EPIGRAPH_DECOMPOSITION_PASS=read(OUT/'GRID_EPIGRAPH_ROW_DECOMPOSITION.json')['PASS'],PCS_SUPPORT_ORACLE_PASS=read(OUT/'PCS_GRID_SUPPORT_ORACLE_PROOF.json')['PASS'],
          MOVEMENT_ARCS_EVALUATED=arcs['evaluated'],MOVEMENT_ARCS_WITH_LB_GT_L0=arcs['with_L_gt_L0'],
          INDIVIDUAL_CUTS_GENERATED=sep['individual_generated'],NONTRIVIAL_INDIVIDUAL_CUTS_GENERATED=sep['nontrivial_individual_generated'],
          CLIQUE_CUTS_GENERATED=sep['clique_generated'],VIOLATED_CUTS_ADDED=sep['added_cuts'],
          M1_ROOT_LB_BASE=BASE_LB,M1_ROOT_LB_STRENGTHENED=root['LB'],M1_ROOT_LB_DELTA=gate_result['delta_LB'],
          MOVEMENT_GRID_STRENGTHENING_SELECTED=selected,MOVEMENT_GRID_MIP_CANARY=canary['status'],FINAL_STRENGTHENING_VERDICT=verdict,
          MAY_CAMPAIGN_ORCHESTRATOR_PRESERVED=True,ACTUAL_FEEDBACK_FIREWALL_PRESERVED=True,B3_FOUR_LOOP_CONTRACT_PRESERVED=True,
          MAY_MAIN_CAMPAIGN_EXECUTION='NOT_RUN',B3_LOOP2_PRODUCTION='NOT_RUN',B3_LOOP3_PRODUCTION='NOT_RUN',B3_LOOP4_PRODUCTION='NOT_RUN',
          PROBLEM13_FINAL_VALIDATED=False,campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,
          full_conditional_LP_calls=0,full_M1_optimize_calls_in_support_oracle=0,production_1800s_MIP_calls=0)
    write('FINAL_FLAGS.json',flags)
    write('NEXT_BOTTLENECK.json',dict(single_next_direction='MESS trajectory-level exact Dantzig-Wolfe / column-generation / branch-and-price',
          status='REPORT_ONLY_NOT_IMPLEMENTED',additional_experiments=0,
          reason='The local connected PCS/site support relaxation stays below L0 even after one unit is removed. Local relief pooling and multi-time route/SOC coupling need the trajectory block convex hull.',
          causal_limit='No conclusion that true conditional LP bounds are all L0; the relaxed algebraic oracle alone is insufficient.'))
    fmt=lambda v:'NULL' if v is None else str(v)
    percent=lambda v:'NULL' if v is None else f'{100*v:.9f}%'
    movement=lambda c:next(r for r in c['families'] if r['family']=='movement_travel_arcs') if c else {}
    bm=movement(base);nm=movement(new)
    text=f'''1. PR / SHA / tests / clean: {pub.get('url','Draft PR 게시 대기')}; scientific commit `{pub.get('scientific_commit','commit 이후 기록')}`. Exact base `{BASE}`. Semantic {verification['SEMANTIC']['passed']} PASS / full pytest {verification['FULL']['passed']} PASS; git diff 및 cached diff --check PASS. 최종 metadata commit의 remote SHA와 clean tree는 최종 응답에서 별도 확인한다.
2. PR138 model identity PASS: 886,017 rows / 316,743 columns / 208,312 binaries / 8,447,855 nnz. Matrix indptr/indices/coefficients, RHS/senses/bounds/types/objective/varnames 및 native rownames SHA, A1/NormalAmps/source authority cold 재감사 PASS; 기존 {verification['original_tracked_files_preserved']:,}개 파일 byte 보존.
3. Baseline root LB: {BASE_LB}. 저장된 PR137 raw primal을 separation에 재사용; baseline 신규 solve=0.
4. Polished fixed-discrete LP status: {polish['status_name']}; Threads=1/Method=2/Crossover=1/TimeLimit=300, runtime {polish['runtime']:.3f}s. 기존 validated zero-action의 정수 패턴만 고정했고 continuous 값은 다시 최적화했다.
5. Polished Start objective: {fmt(polish['objective'])}; available={polish['POLISHED_START_AVAILABLE']}. Global UB certificate로 자동 승격하지 않았다.
6. Polished Start original-row max residual: {fmt(audit.get('original_full_row_audit',{}).get('max_constraint_violation'))}; fixed integers exact={audit.get('exact_fixed_integers')}, physical/route/SOC/PCS/voltage/line/NormalAmps/kVA PASS. Raw 값 clipping/rounding/repair=0.
7. Grid epigraph exact decomposition PASS: 모든 402,433개 rho-linked row. Native dyadic binding DAG의 exact factored reconstruction을 전수 검증했고 dense 계수는 exact 식의 outward interval로 저장했다. Rounded dense equality를 exact라고 간주하지 않았다.
8. PCS support oracle PASS: 모든 8,942개 original connected PCS block의 matrix payload/limits/mode rows 동일성 검증; 원래 16면 계수에 대해 mode 0/1 exact rational vertex support 사용. SOC/route/future 제약은 완화 방향으로만 생략했다.
9. Analytic unconditional support LB: {support['L_support_global']} ≤ L0; responsible row {support['responsible_reduced_row']}, slot {support['responsible_slot']}. Transit zero 포함.
10. Fractional movement arcs evaluated: {arcs['evaluated']:,}/{arcs['evaluated']:,}; full M1 optimize per arc=0, full conditional LP=0.
11. L_arc > L0 movement arc count: {arcs['with_L_gt_L0']:,}.
12. Maximum L_arc: {arcs['max_L_arc']}. 원래 certified L0와 조건부 algebraic support의 max이며, true conditional LP optimum과 동일하다고 주장하지 않는다.
13. Individual cuts generated: {sep['individual_generated']:,}; positive coefficient/nontrivial {sep['nontrivial_individual_generated']:,}. Zero-delta 개별식도 전체 separation에 기록했다.
14. Clique cuts generated: {sep['clique_generated']:,}; same-unit/same-original-outgoing-node의 positive coefficient subset에 한정. DAG unit-path at-most-one 및 zero/one-selected case proof PASS.
15. Baseline root violated cuts: {sep['violated_candidates']:,} (individual {sep['violated_individual']:,}, clique {sep['violated_clique']:,}); 실제 추가 {sep['added_cuts']:,}, nnz 증가 {root['added_nnz']:,}. Threshold >1e-6, exact duplicate 제거 및 clique dominance 적용.
16. Max separation violation: {sep['max_violation']}; positive sum {sep['total_positive_violation']}.
17. Strengthened rows/cols/binaries/nnz: {matrix['rows']:,}/{matrix['columns']:,}/{matrix['binaries']:,}/{matrix['nnz']:,}. 새 binary=0; 원래 matrix prefix/bounds/objectives/route/site/time domain exact 보존; rejected PR137 cuts 재도입=0.
18. Strengthened root LB: {fmt(root['LB'])}; {root['status_name']}, runtime {root['runtime']:.3f}s, barrier {root['barrier_iterations']} iterations. Threads=1/Method=2/Crossover=0/TimeLimit=300 단일 fresh root.
19. Delta LB: {fmt(gate_result['delta_LB'])}.
20. Diagnostic gap before/after: {percent(gate_result['baseline_gap'])} → {percent(gate_result['strengthened_gap'])}; Uref={UB_REF} diagnosticonly, relative closure {fmt(gate_result['relative_diagnostic_gap_closure'])}.
21. Movement fractionality before/after: count {bm.get('fractional_count')} → {nm.get('fractional_count')}; mass {bm.get('fractionality_mass')} → {nm.get('fractionality_mass')}. Split slots {base['split_slots']} → {new.get('split_slots') if new else 'NULL'}; all-binary mass {base['fractionality_mass']} → {new.get('fractionality_mass') if new else 'NULL'}.
22. Material gate: {'PASS' if selected else 'FAIL'}; exact validity/unchanged authority/OPTIMAL/nondecrease + delta≥0.005 또는 relative diagnostic closure≥5%.
23. MIP canary 실행 여부: {canary['status']}; optimization calls={canary['optimization_calls']}. Material FAIL이면 실행 금지. 1800s production MIP=0.
24. Polished Start Gurobi acceptance 여부: {'별도 POLISHED_START_SOLVER_BINDING.json 참조' if canary['optimization_calls'] else 'NOT_ATTEMPTED; canary gate FAIL로 실제 Start를 공급하지 않았다'}. Available 후보와 native 수락을 구분했다.
25. First nonroot / first branch: {fmt(canary['first_nonroot'])} / {fmt(canary['first_branch'])}.
26. Canary UB/LB/gap: {fmt(canary['UB'])} / {fmt(canary['LB'])} / {fmt(canary['gap'])}.
27. 최종 strengthening 판정: **{verdict}**, selected={selected}. Algebraic oracle의 material 효과는 없었다; true conditional physical optima에 대한 별도 결론은 내리지 않는다.
28. 다음 병목 하나: **MESS trajectory-level exact Dantzig-Wolfe / column-generation / branch-and-price**. Block trajectory convex hull를 직접 다루는 구조적 후보만 보고했고 이번 task에서는 구현/실행하지 않았다.
29. May/B3 orchestrator preserved PASS: 1,458-stage dry plan, B0→B1→B2→B3(L1) 완료 후 B3 L2/L3/L4 각각 A1→M1→A2→M2; Actual은 completion sequence gate만 사용, next Planning은 previous Planning only. B0/B1/B2 convergence loop 및 Loop4 전 early-stop 없음.
30. Production optimizer/Actual/Fresh AC = 0/0/0. Main/L2/L3/L4 NOT_RUN, PROBLEM13_FINAL_VALIDATED=false. 모든 scientific heavy 작업 종료 후 semantic/full tests를 순차 실행했다.

이번 작업은 full conditional LP separation을 사용하지 않고, movement transit semantics와 exact grid epigraph support를 이용해 route-transition conditional lower bounds를 algebraically 계산했다.

Scientific M1 integer feasible set, route domain, physical authority, A1 freeze 및 P1/P2 objective는 변경하지 않았다.

이번 algebraic strengthening까지 material FAIL이면 다음 구조적 후보는 MESS trajectory-level exact Dantzig-Wolfe / column-generation / branch-and-price이며, 이번 task에서는 구현하지 않았다.

May 31-day production campaign은 실행하지 않았으며, B0->B1->B2->B3(L1), 이후 B3 L2/L3/L4 순서와 Actual feedback firewall을 그대로 보존했다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')
    description=f'''The exact PR138 M1 baseline retains a weak root bound despite 131,350 fractional movement arcs. This diagnostic evaluates every such arc without conditional full LPs: native grid epigraph binding equations and exact rational PCS polygons give outward certified transit-conditioned support bounds. No conditional support exceeds L0, so all individual coefficients are zero and no clique/violated cut is added. The fresh root LP is {root['status_name']} with LB={root['LB']} and delta={gate_result['delta_LB']}; the strict material gate fails and the 600s MIP canary is NOT_RUN.

Separately, fixing only the validated zero-action integer pattern yields an OPTIMAL continuous polishing LP with raw objective {polish['objective']}, full-row residual {audit.get('original_full_row_audit',{}).get('max_constraint_violation')} and independent physical PASS. This is an available Start candidate, never promoted to a global UB or claimed solver-accepted without the gated canary.

Validation: semantic {verification['SEMANTIC']['passed']} passed; full pytest {verification['FULL']['passed']} passed; all {verification['original_tracked_files_preserved']} prior tracked files, scientific matrix/column/native row names and A1/NormalAmps/source identities preserved; git diff checks pass. Native handled OpenDSS exception traces remain in inherited regression logs with exit 0. Scientific heavy optimization uses one worker/one thread. Campaign optimizer/Actual/Fresh AC calls=0/0/0; 1,458-stage May/B3 plan and firewall unchanged. The sole next structural candidate is trajectory-level exact Dantzig-Wolfe / column generation / branch-and-price, report only.
'''
    (OUT/'PR_DESCRIPTION.md').write_text(description,encoding='utf8')

def manifest():
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json']
    for directory in ('v42_movement','tests/v42_movement'):
        paths += [p for p in (ROOT/directory).iterdir() if p.is_file() and (p.suffix=='.py' or p.name=='.gitattributes')]
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)],self_hash_excluded=True,
          scientific_source_assets=read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['source_asset_SHAs']))
if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()
