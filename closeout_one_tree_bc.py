"""Independent no-solve original-domain and evidence closeout."""
import json,csv,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
import numpy as np
from v42_degen.identity import inputs
from v42_rowgen.core import row_digest,security_axis
from v42_one_tree_bc.audit import Validator
from v42_one_tree_bc.core import Separator
from v42_one_tree_bc.files import ROOT,OUT,write,sha

BASE='a6045405b254703285a9d8469105746e3fc1b904'
def read(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def csvrows(n):
    with (OUT/n).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def run():
    a=read('M1_ONE_TREE_BC_BASELINE_600S.json');b=read('M1_ONE_TREE_BC_CHALLENGER_600S.json')
    comparison=read('M1_ONE_TREE_BC_COMPARISON.json');selection=read('M1_ONE_TREE_BC_SELECTION.json')
    freeze=read('M1_ONE_TREE_BC_INPUT_FREEZE.json');execution=read('M1_ONE_TREE_BC_EXECUTION_FREEZE.json')
    supervisor=read('M1_ONE_TREE_BC_SUPERVISOR_RESULT.json');fixtures=read('M1_ONE_TREE_BC_FIXTURE_RESULTS.json')
    source_pass=all(sha(ROOT/p)==h for p,h in freeze['source_files'].items())
    assert source_pass
    A,d,B,e,identity,_=inputs();validator=Validator(A,d)
    audits={}
    for r in (a,b):
        with np.load(OUT/f"{r['arm']}_FINAL_VALID_POINT.npz") as z:x=z['point'].copy()
        check=validator(x);assert check['PASS'] and check['objective']==r['final_valid_UB']
        assert check['exhaustive_grid']['checked_rows']==len(security_axis(d))
        audits[r['arm']]=check
    registry=csvrows('M1_ONE_TREE_BC_ROW_REGISTRY.csv')
    grid=set(map(int,security_axis(e)));seen=set();family=Counter()
    for row in registry:
        i=int(row['original_row_id']);assert i in grid and i not in seen
        seen.add(i)
        assert row_digest(B,e,i)==row['original_row_SHA']
        assert str(e['row_names'][i])==row['row_name']
        family[row['family']]+=1
    assert dict(family)==b['rows_by_family']
    assert len(registry)==b['MIPNODE_unique_rows']+b['MIPSOL_unique_rows']
    assert b['final_active_original_rows']==287552+len(registry)
    ledger=csvrows('M1_ONE_TREE_BC_CALLBACK_LEDGER.csv')
    integer=[r for r in ledger if r['callback_type']=='MIPSOL']
    complete_integer=all(int(r['checked_rows'])==598465 and
        (int(r['violations'])==0 or int(r['added'])==int(r['violations'])) and not r['error'] for r in integer)
    assert len(integer)==b['callback_counts'].get('MIPSOL_separations',0)
    assert sum(int(r['violations'])>0 for r in integer)==b['invalid_incumbents_rejected']
    valid_objectives=[float(r['full_objective']) for r in integer if r['valid_full_original']=='True']
    assert all(not r['full_objective'] for r in integer if r['valid_full_original']!='True')
    assert sum(int(r['lazy_resubmissions'] or 0) for r in ledger)==b['lazy_resubmissions']
    assert all(int(r['new_unique_rows'])<=256 for r in ledger if r['callback_type']=='MIPNODE')
    # History byte audit is read-only. Historical source SHA is checked against
    # its original worktree if Git's earlier text conversion differed on checkout.
    prior=ROOT/'docs/v42_m1_exact_grid_rowgen_20261006'
    manifest=json.loads((prior/'SHA256_MANIFEST.json').read_text())
    history_artifacts={p:sha(prior/p)==h for p,h in manifest['artifacts'].items()}
    original_root=Path('C:/v42_m1_exact_grid_rowgen_20261006')
    preserved=[]
    history_sources={p:sha(ROOT/p)==h for p,h in manifest['source_worktree_SHA'].items()}
    for kind,entries,checks,current_root,original_base in (
        ('artifact',manifest['artifacts'],history_artifacts,prior,original_root/'docs/v42_m1_exact_grid_rowgen_20261006'),
        ('source',manifest['source_worktree_SHA'],history_sources,ROOT,original_root)):
        for p,h in entries.items():
            original=original_base/p;assert sha(original)==h
            if not checks[p]:
                raw=original.read_bytes();current=(current_root/p).read_bytes()
                assert raw.replace(b'\r\n',b'\n')==current.replace(b'\r\n',b'\n'),p
                target=OUT/'history/PR158_ORIGINAL_WORKTREE_BYTES'/kind/p
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                assert sha(target)==h
                preserved.append(dict(kind=kind,path=p,manifest_SHA=h,checkout_SHA=sha(current_root/p),
                    preserved_copy=str(target.relative_to(OUT)),normalized_text_identical=True))
    write('PR158_BYTE_PRESERVATION_RECEIPT.json',dict(PASS=True,
        original_manifest_artifacts=len(history_artifacts),original_manifest_sources=len(history_sources),
        original_worktree_all_manifest_hashes_PASS=True,checkout_byte_mismatches=preserved,
        inherited_Git_files_not_edited=True,
        reason='Earlier Git text normalization stored LF before -text rules; original worktree evidence bytes are preserved separately, without rewriting inherited Git history.'))
    with np.load(prior/'B_ROWGEN_ITER_002_RAW.npz') as z:historical_candidate=z['point'].copy()
    historical_bad=Separator(B,e).evaluate(historical_candidate)
    historical_families=dict(Counter(str(e['row_names'][i]).split('[')[0] for i in historical_bad['violated']))
    assert len(historical_bad['violated'])==3941 and historical_families=={'voltage_upper':3941}
    write('PR158_INVALID_CANDIDATE_NO_SOLVE_REAUDIT.json',dict(PASS=True,
        native_solves=0,objective=float(e['objective']@historical_candidate+float(e['constant'])),
        scanned_rows=historical_bad['checked_rows'],violations=3941,families=historical_families,
        rejected_as_UB=True,meaning='Offline exact sparse evaluator regression on frozen PR158 point; not a claim that the paired challenger produced this same candidate.'))
    tracked_changes=subprocess.check_output(['git','diff',BASE,'--name-only'],cwd=ROOT,text=True).splitlines()
    history_modified=[p for p in tracked_changes if p.startswith(('docs/v42_m1_exact_grid_rowgen_20261006/',
        'docs/v42_m1_conservative_early_bap_20261006/','v42_rowgen/'))]
    assert not history_modified
    native_log_calls={r['arm']:(OUT/f"{r['arm']}.log").read_text().count('Optimize a model with') for r in (a,b)}
    assert all(v==1 for v in native_log_calls.values()) and a['optimize_calls']==b['optimize_calls']==1
    regression=ET.parse(OUT/'REGRESSION.xml').getroot()
    suites=list(regression) if regression.tag=='testsuites' else [regression]
    reg={k:sum(int(s.attrib.get(k,'0')) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert reg['failures']==reg['errors']==0
    gap=lambda u,l:max(0.,u-l)/abs(u)
    for r in (a,b):
        assert abs(r['final_global_gap']-gap(r['final_valid_UB'],r['final_valid_LB']))<=1e-15
        assert r['final_valid_LB']<=r['final_valid_UB']+1e-8
    if a['gap_reduction_per_wall_second']==b['gap_reduction_per_wall_second']==0:
        assert selection['ONE_TREE_BC_SELECTED'] is False
    budget=supervisor['continuous_wall']<=600 and comparison['continuous_wall']<=600 and not supervisor['time_deadline_kill']
    assert budget
    independent=dict(PASS=all(c['PASS'] for c in audits.values()),new_native_solves=0,
        full_original_final_valid_points=audits,
        original_unreduced_grid_rows_scanned=len(security_axis(d)),
        callback_reduced_deferred_rows_scanned=598465,
        registry_unique_original_rows_PASS=True,registered_row_payload_hashes_checked=len(registry),
        original_row_SHA_and_name_PASS=True,
        every_MIPSOL_full_grid_scan_PASS=all(int(r['checked_rows'])==598465 for r in integer),
        every_violated_integer_row_submitted_PASS=complete_integer,
        no_rejected_candidate_objective_used_as_UB=True,
        authorized_lazy_resubmissions=b['lazy_resubmissions'],
        native_log_optimize_calls=native_log_calls,immutable_benchmark_source_PASS=source_pass,
        PR158_original_evidence_hashes_checked=len(history_artifacts),PR158_history_bytes_PASS=True,
        PR157_PR158_no_tracked_history_changes=True,
        lower_bound_semantics='Original explicit full-domain master relaxation plus original valid rows; no RMP/restricted-column authority.',
        previous_original_floor_provenance=freeze['floor_provenance'])
    write('M1_ONE_TREE_BC_INDEPENDENT_AUDIT.json',independent)
    verification=dict(PASS=bool(fixtures['PASS'] and independent['PASS'] and budget and complete_integer and all(r['scientific_certification_PASS'] for r in (a,b))),
        regression=reg,fixture_assignments=fixtures['exhaustive_assignments'],
        feasible_assignments=sum(c['feasible'] for c in fixtures['fixtures']),
        infeasible_assignments=sum(c['infeasible'] for c in fixtures['fixtures']),
        fractional_MIPNODE_test_PASS=fixtures['fractional_MIPNODE_original_cut_test']['PASS'],
        fullscale_optimize_calls=2,challenger_optimize_calls=1,
        every_MIPSOL_grid_rows=598465,complete_integer_lazy_submissions_PASS=complete_integer,
        immutable_benchmark_source_PASS=source_pass,
        benchmark_source_commit=execution['source_commit'],
        history_preserved=True,continuous_supervised_wall=supervisor['continuous_wall'],
        selected=selection['ONE_TREE_BC_SELECTED'],final_state=selection['final_state'],
        production_canary=False,P2=False,M2=False,B2_B3=False,STOP=True)
    write('VERIFICATION.json',verification)
    write('M1_ONE_TREE_BC_FIELD_SCOPE.json',dict(PASS=True,
        raw_native_bound_field_in_arm_JSON='Despite its field name raw_native_bound, the frozen benchmark stored native ObjBound nudged downward1e-8 and nextafter(-inf). This is a safety-adjusted bound, not verbatim raw native ObjBound. Original arm JSON and native logs are retained unchanged.',
        log_reported_raw_best_bound=dict(A_MONOLITHIC='2.529539575959e-01',B_ONE_TREE='0.000000000000e+00'),
        deferred_reduced_original_grid_rows=598465,
        final_unreduced_original_grid_rows=673920,
        fullscale_MIPNODE_user_cut_policy_exercised=False,
        fractional_fixture_MIPNODE_policy_exercised=True,
        root_gitattributes_change='Only adds byte-preservation rules for new one-tree files; inherited scientific sources and PR157/PR158 evidence are unchanged.',
        history_checkout_normalization_receipt='PR158_BYTE_PRESERVATION_RECEIPT.json'))
    census=read('M1_ONE_TREE_BC_INITIAL_MODEL_CENSUS.json')
    def f(v):return '—' if v is None else f'{v:.9f}' if isinstance(v,float) else str(v)
    def gib(v):return '—' if v is None else f'{v/2**30:.3f} GiB'
    rows=[
        ('1. Exactness','12개 / 1,536 정수 조합: 49 feasible·1,487 infeasible 일치; fractional-node·sense·재거부 PASS', '회귀63개 PASS'),
        ('2. 원래 모델','886,017 rows / 316,743 cols / 208,312 binary / 8,447,855 nnz','동일 변수·objective·domain'),
        ('3. 초기 모델','전체 모델','287,552 rows / 316,743 cols / 208,312 binary / 2,784,047 nnz'),
        ('4. Deferred rows','0','598,465; auxiliary81,216 유지'),
        ('5. Callback 횟수',a['callback_count'],b['callback_count']),
        ('6. MIPNODE 고유 추가 행',0,b['MIPNODE_unique_rows']),
        ('7. MIPSOL 고유 추가 행',0,b['MIPSOL_unique_rows']),
        ('8. Family 추가 행','—',json.dumps(b['rows_by_family'],ensure_ascii=False)),
        ('9. 최종 고유 원래 행',a['final_active_original_rows'],b['final_active_original_rows']),
        ('10. 거부된 invalid integer 후보',0,b['invalid_incumbents_rejected']),
        ('11. 첫 native / 검증 완료 incumbent 초',f"{f(a['first_solver_incumbent'])} / {f(a['first_native_valid_incumbent'])}",f"{f(b['first_solver_incumbent'])} / {f(b['first_native_valid_incumbent'])}"),
        ('12–13. Valid UB 시작 → 종료',f"{f(a['initial_valid_UB'])} → {f(a['final_valid_UB'])}",f"{f(b['initial_valid_UB'])} → {f(b['final_valid_UB'])}"),
        ('14–15. Valid global LB 시작 → 종료',f"{f(a['initial_valid_LB'])} → {f(a['final_valid_LB'])}",f"{f(b['initial_valid_LB'])} → {f(b['final_valid_LB'])}"),
        ('16–17. Valid gap 시작 → 종료',f"{a['initial_global_gap']*100:.6f}% → {a['final_global_gap']*100:.6f}%",f"{b['initial_global_gap']*100:.6f}% → {b['final_global_gap']*100:.6f}%"),
        ('18. Gap 감소 / wall초',f(a['gap_reduction_per_wall_second']),f(b['gap_reduction_per_wall_second'])),
        ('19. Node / LP iter / work',f"{a['nodes']} / {a['LP_iterations']} / {a['work']}",f"{b['nodes']} / {b['LP_iterations']} / {b['work']}"),
        ('20. Build / native / wall초',f"{a['build_wall']:.3f} / {a['native_runtime']:.3f} / {a['wall_runtime']:.3f}",f"{b['build_wall']:.3f} / {b['native_runtime']:.3f} / {b['wall_runtime']:.3f}"),
        ('21. RSS / process commit / min RAM',f"{gib(a['peak_RSS'])} / {gib(a['peak_process_commit'])} / {gib(a['minimum_available_RAM'])}",f"{gib(b['peak_RSS'])} / {gib(b['peak_process_commit'])} / {gib(b['minimum_available_RAM'])}"),
        ('22. Selected','—',selection['ONE_TREE_BC_SELECTED']),
        ('23. Benchmark source commit',execution['source_commit'],'Draft PR는 별도 PR_RECEIPT.json 및 최종 응답에 기록')]
    text=f"""# M1 one-tree exact grid branch-and-cut 최종 검토

최종 상태: **{selection['final_state']}**. ONE_TREE_BC_SELECTED={str(selection['ONE_TREE_BC_SELECTED']).lower()}.
고정 source commit: `{execution['source_commit']}`; parent PR158 `{BASE}`.
합산 연속 wall: {supervisor['continuous_wall']:.3f}초 (상한600초), sequential, native optimize 각1회.

| 항목 | A original monolithic | B one-tree |
|---|---|---|
"""
    for k,x,y in rows:text+=f'| {k} | {x} | {y} |\n'
    text+=f"""
실제 MIPNODE separation={b['callback_counts'].get('MIPNODE_separations',0)},
MIPSOL exhaustive separation={b['callback_counts'].get('MIPSOL_separations',0)}.
고유 registry 중복 없음; 중복 등록 회피={b['callback_counts'].get('duplicate_rows_avoided',0)},
사용자 허용 lazy 재거부 cbLazy 재제출={b['lazy_resubmissions']},
usercut→lazy 승격={b['callback_counts'].get('usercut_to_lazy_promotions',0)}.
각 MIPSOL의 모든598,465행 검사와 모든 위반 행 제출을 ledger로 독립 감사했다.
최종 독립 point 감사는 중복 제거 전의 전체 grid673,920행까지 추가로 검사했다.
Full-scale에서는 optimal fractional MIPNODE separation이 관측되지 않아
그 가속 정책의 실제 성능은 측정되지 않았다. MIPNODE fixture는 별도로 PASS했다.
`final_active_original_rows`는 초기 행과 고유 제출 행 합계이며,
Gurobi 내부 cut-pool 잔존 행 수를 주장하지 않는다. 애플리케이션 cut deletion은 없다.
원래 full-grid/비-grid/정수 route/SOC/PCS/mode/objective 최종 검증 PASS.

Valid UB는 검증 통과 native point 또는 동일하게 검증된 기존 원래 시작점만 사용했다.
LB는 기존 원래 full-domain certificate floor와 본 원래 변수-domain native tree LB의
최댓값이며 RMP/restricted-column LB는 읽거나 사용하지 않았다. 작은1e-8 하향 조정은
기존 native numerical authority이며 새로운 exact-rational native bound 증명이라고
주장하지 않는다. 시작 incumbent는 비교 시작 시점0초에 이미 유효하므로,
표의 first native valid 시간은 실제 native callback 후보의 감사 완료 시각이다.
RSS/commit/RAM은1초 관찰치의 극값이며 연속 native 메모리 최대치라고 주장하지 않는다.
Native status A={a['native_status']}, B={b['native_status']}; gap<=.005 수렴을 달성했다고
주장하지 않는다. Errors A={a['errors']}, B={b['errors']}.
Arm JSON의 `raw_native_bound` 필드는 실제로1e-8 하향 safety bound이다.
원시 native bound는 보존된 로그에서 A≈0.2529539575959, B=0으로 확인된다.
필드 의미 교정은 M1_ONE_TREE_BC_FIELD_SCOPE.json에 기록했으며 raw 결과는 보존했다.

선정은 사전 등록된 valid-gap-progress 기준만 사용했다. 양쪽 감소가0이면 false이고,
메모리·행 개수·cut 개수·invalid objective만으로 성공을 판단하지 않았다.
추가 policy 비교, production3600초 canary, P2/M2/B2/B3는 실행하지 않고 STOP했다.
PR157/PR158 기존 evidence와 scientific source를 변경하지 않았다.

본 방법은 원래 V42 M1 grid constraints 자체를 callback에서 동적으로 추가하는 exact branch-and-cut이며, heuristic feasible-set restriction이 아니다.

모든 integer incumbent는 598,465개 deferred grid-security rows에 대한 exhaustive separation을 통과한 경우에만 valid UB로 인정했다.

MIPNODE critical/multi-row selection은 계산 가속에만 사용하며, MIPSOL exhaustive separation과 최종 scientific feasibility를 대체하지 않았다.

PR158의 outer-loop row generation과 달리 한 번의 native B&B tree를 유지하며 grid rows를 추가하는 구조를 시험했다.
"""
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')
    manifest_files()
    print(json.dumps(dict(state=selection['final_state'],verification=verification,
        native_calls=0,registry_rows=len(registry)),ensure_ascii=False,indent=2))
def manifest_files():
    sources=['.gitattributes','benchmark_one_tree_bc.py','prepare_one_tree_bc.py',
        'run_one_tree_comparison.py','verify_one_tree_bc.py','closeout_one_tree_bc.py',
        'tests/test_v42_one_tree_bc.py']+[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'v42_one_tree_bc').glob('*.py')]
    write('SHA256_MANIFEST.json',dict(artifacts={str(p.relative_to(OUT)).replace('\\','/'):sha(p)
        for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'},
        source_files={p:sha(ROOT/p) for p in sources},base_PR158=BASE,
        native_fullscale_comparisons=1,fullscale_optimize_calls=2,
        benchmark_source_commit=read('M1_ONE_TREE_BC_EXECUTION_FREEZE.json')['source_commit']))
if __name__=='__main__':run()
