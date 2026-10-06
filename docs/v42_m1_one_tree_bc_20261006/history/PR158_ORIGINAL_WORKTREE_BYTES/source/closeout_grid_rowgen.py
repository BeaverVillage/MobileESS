"""Independent saved-point/row-axis/history audit; zero native optimization."""
from pathlib import Path
from collections import Counter
from fractions import Fraction as F
import json,subprocess,xml.etree.ElementTree as ET
import numpy as np
from v42_degen.identity import inputs,signature
from v42_rowgen.core import *
from audit_grid_rowgen import ROOT,OUT,write,sha
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def trim(r):return {k:v for k,v in r.items() if k!='violated'}
def run():
    A,d,B,e,identity,freeze=inputs()
    experiment=read(OUT/'M1_ROWGEN_600S_MICROBENCHMARK.json');selection=read(OUT/'M1_DECOMPOSITION_SELECTION.json')
    frozen=read(OUT/'MICROBENCHMARK_INPUT_FREEZE.json')
    assert signature(B,e)==frozen['signature'] and identity==frozen['scientific_identity']
    assert all(sha(ROOT/n)==h for n,h in frozen['source_worktree_SHA'].items())
    fixture=read(OUT/'ROW_GENERATION_EXACTNESS.json');assert fixture['PASS'] and fixture['assignments']==1536
    assert sum(v['feasible'] for v in fixture['fixtures'])==49
    assert sum(v['infeasible'] for v in fixture['fixtures'])==1487
    assert len(binding_proof(B,e))==81216
    from v42_dw_root.partition import axes
    from v42_dw_resume.audit import corrected_rows,pure_binary_equalities,prototypes
    owner,rowowner=axes()
    with np.load(ROOT/'docs/v42_m1_exact_dw_cg_root_pilot/DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,rowowner,native);route_mask=pure_binary_equalities(A,d);audits=[]
    for arm in experiment['arms']:
        label=arm['arm']
        with np.load(OUT/f'{label}_FINAL_VALID_POINT.npz') as z:x=z['point']
        raw=corrected_rows(A,d,x,True,route_mask);grid=separate(A,d,x,security_axis(d))
        physical=[b.validate(x[b.columns],True) for b in blocks]
        assert raw['PASS'] and grid['PASS'] and all(v['PASS'] for v in physical)
        assert abs(float(d['objective']@x+float(d['constant']))-arm['final_valid_UB'])<=1e-10
        sf=families(d['row_names']);probes=[]
        for f in sorted(SECURITY):
            ix=np.flatnonzero(sf==f)
            if len(ix):probes.extend(map(int,ix[np.unique(np.linspace(0,len(ix)-1,min(64,len(ix)),dtype=int))]))
        zeros=security_axis(d)[np.diff(A.indptr)[security_axis(d)]==0]
        for i in probes+list(map(int,zeros)):assert exact_residual(A,d,x,i)<=F(TOL)
        replay=[]
        if label=='B_ROWGEN':
            rows=OriginalRows(B,e)
            for iteration in arm['iterations']:
                index=iteration['iteration'];rawfile=OUT/f'{label}_ITER_{index:03d}_RAW.npz'
                if not rawfile.exists():assert iteration.get('candidate') is None;continue
                with np.load(rawfile) as z:p=z['point']
                pending=rows.pending(p);axisfile=OUT/f'{label}_ITER_{index:03d}_GENERATED_AXES.npz'
                if axisfile.exists():
                    with np.load(axisfile) as z:added=z['original_rows']
                    assert np.array_equal(added,pending['violated']) and len(added)==iteration['added']
                    rows.add(added)
                else:assert not len(pending['violated'])
                replay.append(dict(iteration=index,checked_omitted=pending['checked_rows'],all_violated_original_axes_PASS=True,added=iteration['added']))
            assert len(rows.axis)==arm['final_rows']
        audits.append(dict(arm=label,PASS=True,full_grid=trim(grid),full_matrix=raw,physical=physical,
                           rational_scalar_probes=len(probes)+len(zeros),iteration_replay=replay))
    base='611af1ba474e8f457d79e79590ed30aa529262a3'
    changes=subprocess.check_output(['git','diff',base,'--name-only'],cwd=ROOT,text=True).splitlines()
    allowed=lambda p:p.startswith(('docs/v42_m1_exact_grid_rowgen_20261006/','v42_rowgen/')) or p in ['audit_grid_rowgen.py','verify_grid_rowgen.py','benchmark_grid_rowgen.py','run_grid_comparison.py','closeout_grid_rowgen.py','tests/test_v42_grid_rowgen.py']
    assert all(allowed(p) for p in changes),changes
    manifest=read(ROOT/'docs/v42_m1_conservative_early_bap_20261006/SHA256_MANIFEST.json')
    checkout_normalization=[]
    for p,h in manifest['files'].items():
        previous=Path(r'C:\v42_m1_dual_early_bap_20261006')/'docs/v42_m1_conservative_early_bap_20261006'/p
        current=ROOT/'docs/v42_m1_conservative_early_bap_20261006'/p
        assert sha(previous)==h
        if sha(current)!=h:
            assert current.read_bytes().replace(b'\r\n',b'\n')==previous.read_bytes().replace(b'\r\n',b'\n')
            archive=OUT/'history/PR157_ORIGINAL_WORKTREE_BYTES'/p;archive.parent.mkdir(parents=True,exist_ok=True)
            archive.write_bytes(previous.read_bytes());assert sha(archive)==h
            checkout_normalization.append(dict(file=p,original_worktree_SHA=h,checkout_SHA=sha(current),
                difference='Git checkout CRLF/LF only; inherited blobs untouched',original_byte_archive=archive.relative_to(OUT).as_posix()))
    write('PR157_BYTE_PRESERVATION_RECEIPT.json',dict(original_worktree_manifest_files_PASS=len(manifest['files']),
        original_worktree_unchanged=True,inherited_Git_blobs_unchanged=True,new_checkout_newline_only_differences=checkout_normalization,
        original_exact_byte_archives_PASS=len(checkout_normalization),scientific_matrix_and_binary_payload_drift=0))
    history=read(OUT/'history/HISTORY_SOURCE_RECEIPT.json')
    for r in history:assert sha(Path(r['original_path']))==sha(OUT/'history'/r['copy'])==r['SHA']
    calls=read(OUT/'NATIVE_CALL_LEDGER.json');a,b=experiment['arms']
    last=b['iterations'][-1]
    candidate_converged=bool(last.get('final_candidate_grid',False) and last['added']==0)
    with np.load(OUT/f"B_ROWGEN_ITER_{last['iteration']:03d}_RAW.npz") as z:lastpoint=z['point']
    rejection=separate(B,e,lastpoint,security_axis(e))
    rowfamilies=families(e['row_names']);residual=B@lastpoint-e['rhs']
    violation=np.maximum(0,np.where(e['sense']=='=',abs(residual),np.where(e['sense']=='<',residual,-residual)))
    reject_families=[]
    for f in sorted(SECURITY):
        ix=np.flatnonzero(rowfamilies==f)
        reject_families.append(dict(family=f,violated_rows=int(np.count_nonzero(rowfamilies[rejection['violated']]==f)),
            max_violation=float(np.max(violation[ix],initial=0))))
    write('CANDIDATE_REJECTION_FAMILY_AUDIT.json',dict(PASS=True,candidate_is_original_feasible=rejection['PASS'],
        native_candidate_objective=float(e['objective']@lastpoint+float(e['constant'])),
        original_grid_violations=len(rejection['violated']),families=reject_families,native_candidate_not_used_as_valid_UB=True))
    write('M1_ROWGEN_CANDIDATE_TERMINATION_AUDIT.json',dict(row_generation_converged=candidate_converged,
        last_candidate_new_violated_rows=last['added'],last_candidate_full_grid_PASS=candidate_converged,
        final_certified_best_UB_grid_PASS=True,final_best_UB_origin='previously validated original integer Start; no new UB improvement',
        stop_reason='BOUNDED_DEVELOPMENT_WALL_END_NOT_SCIENTIFIC_CONVERGENCE',
        rows_added_after_last_solve_not_yet_resolved=last['added'],additional_native_solves=0))
    rawselection=OUT/'M1_DECOMPOSITION_SELECTION_BENCHMARK_RAW.json'
    if not rawselection.exists():rawselection.write_bytes((OUT/'M1_DECOMPOSITION_SELECTION.json').read_bytes())
    selection.update(exhaustive_final_separation_scope='certified best UB (original-feasible inherited Start), not terminal row-generation candidate',
        row_generation_candidate_converged=candidate_converged,last_candidate_original_grid_violations=last['added'],
        benchmark_raw_selection_SHA=sha(rawselection),additional_native_solves_after_budget=0)
    write('M1_DECOMPOSITION_SELECTION.json',selection)
    assert len(calls)==a['master_solves']+b['master_solves']
    assert all(v['arm']=='A_BASELINE' for v in calls[:a['master_solves']])
    assert all(v['arm']=='B_ROWGEN' for v in calls[a['master_solves']:])
    for arm in (a,b):
        native_bounds=[float(np.nextafter(v['raw_native_bound']-TOL,-np.inf)) for v in calls if v['arm']==arm['arm'] and v['raw_native_bound'] is not None]
        reconstructed=max([arm['starting_valid_LB']]+native_bounds)
        assert abs(reconstructed-arm['final_valid_LB'])<=1e-12
    assert experiment['within_budget'] and experiment['total_continuous_wall']<=600
    tests=ET.parse(OUT/'FINAL_TEST_RESULTS.xml').getroot();suites=[tests] if tests.tag=='testsuite' else list(tests)
    stats={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert stats['failures']==stats['errors']==stats['skipped']==0
    write('INDEPENDENT_SAVED_EVIDENCE_AUDIT.json',dict(PASS=True,new_native_optimization_calls=0,arms=audits,
        inherited_Git_files_unchanged=True,PR157_evidence_bytes_preserved=len(manifest['files']),V16_bytes_preserved=len(history),
        scientific_signature_PASS=True,frozen_source_PASS=True,sequential_native_calls=True,native_call_count=len(calls)))
    write('VERIFICATION.json',dict(PASS=True,regression=stats,assignments=1536,feasible=49,infeasible=1487,
        full_final_separation_PASS=True,all_generated_original_rows_PASS=True,independent_native_calls=0,
        final_best_UB_full_grid_PASS=True,row_generation_candidate_converged=candidate_converged,
        history_preserved=True,benchmark_wall_cap_PASS=True,selected=selection['NEW_M1_DECOMPOSITION_SELECTED'],
        P1_accepted=selection['P1_accepted'],production_canary=False,P2=False,full_May_M_campaign=False,B2_B3=False))
    variable=read(OUT/'CURRENT_M1_VARIABLE_PARTITION.json');rowpart=read(OUT/'CURRENT_M1_ROW_PARTITION.json');census=read(OUT/'ROW_GENERATION_INITIAL_MASTER_CENSUS.json')
    categories=Counter()
    for v in variable['families']:categories[v['category']]+=v['columns']
    report=['# Exact grid row-generation 개발 결과','',f"최종 상태: **{selection['final_state']}**. NEW_M1_DECOMPOSITION_SELECTED={str(selection['NEW_M1_DECOMPOSITION_SELECTED']).lower()}.",'',
        '분류: DIRECT_EXACT_ROW_GENERATION_POSSIBLE. 모든 P/Q/SOC/route/mode/rho는 master에 남는다. Grid-only Benders는 직접 affine 평가가 가능해 불필요·미실행이며 giant recourse는 재도입하지 않았다.',
        f'기존 PR157 original worktree100개 evidence의 manifest SHA는 그대로 PASS다. 새 checkout의{len(checkout_normalization)}개 text evidence는 inherited Git blob의 CRLF/LF 정규화 차이만 있었으며, 원래 byte를 별도 history/PR157_ORIGINAL_WORKTREE_BYTES에 보존했다. 기존 baseline 파일을 수정하지 않았다.',
        '', 'V16.3 May02 Standard BD29→CL-MC-BD7 iterations,71.488→38.376초, 동일 monolithic optimum. Monolithic 자체4.82초였으므로 전체 M1 가속으로 일반화하지 않았다. V42 PR115–1201000–1400초 recourse/Kappa/인증 문제와 PR124 binary감소만으로 runtime 개선을 입증하지 못한 결론을 보존했다. PR157 D-W/Early B&P 원래 증거100개와 모든 inherited Git files는 보존했다.',
        '', '| Variable category | Columns |','|---|---:|']
    report.extend(f'| {cat} | {n:,} |' for cat,n in sorted(categories.items()))
    report+=['','| Original row family | Rows | nnz |','|---|---:|---:|']
    report.extend(f"| {r['family']} | {r['rows']:,} | {r['nnz']:,} |" for r in rowpart['families'])
    report+=['','Security grid rows598,465개, affine definition/grid auxiliary81,216개. Native+1 pivot과 acyclic P/Q→injection→response를 확인했다. 제거한 auxiliary0개/0%: sparse factoring을 유지했다.',
        '', '| Model | Rows | Columns | Binary | Continuous | nnz |','|---|---:|---:|---:|---:|---:|',
        '| Current original | 886,017 | 316,743 | 208,312 | 108,431 | 8,447,855 |','| Initial master | 287,552 | 316,743 | 208,312 | 108,431 | 2,784,047 |',
        '',f"초기 rows감소{100*census['row_reduction_fraction']:.3f}%, nnz감소{100*census['nnz_reduction_fraction']:.3f}%. CSR예상104,918,332→34,558,776byte는 native RSS/factorization 예측이 아니다.",
        '',f"Exactness:12 physical fixtures,1536 exhaustive binary assignments(49 feasible/1487 infeasible) status/optimum 일치. 모든 original row coefficient/sign identity와 <=/>=/=, constant/cancellation/threshold exact-rational fallback, omitted violation 및 final separation 제거 반례 PASS. 회귀{stats['tests']}개 PASS. 독립 최종 감사 native solve0회.",
        '',f"동일 frozen current hard May01 M1을 sequential A→B로 비교했다. 두 arm을 합친 연속 wall{experiment['total_continuous_wall']:.6f}초,600초 이내. 각 arm의 최대280초에 build/row insertion을 포함했다. Paper runtime은 측정하지 않았다.",
        '', '| Metric | A original monolithic | B exact row generation |','|---|---:|---:|']
    metrics=[('Initial valid UB','starting_valid_UB'),('Final valid UB','final_valid_UB'),('Initial valid LB','starting_valid_LB'),('Final valid LB','final_valid_LB'),('Initial relative gap','starting_gap'),('Final relative gap','final_global_gap'),('Gap reduction / wall sec','gap_reduction_per_wall_second'),('First valid existing integer time','first_valid_integer_incumbent_time'),('First new valid integer sec','first_new_valid_integer_incumbent_time'),('First native valid integer sec','first_native_valid_integer_time'),('Master solves','master_solves'),('Row-generation iterations','row_generation_iterations'),('Rows added','rows_added'),('Final active rows','final_rows'),('Native sec','native_runtime'),('Build-inclusive wall sec','wall_runtime'),('Peak process RSS bytes','peak_RSS'),('Peak process commit bytes','peak_process_commit'),('Peak system commit bytes','peak_system_commit'),('Min free RAM bytes','min_free_RAM')]
    for label,key in metrics:report.append(f"| {label} | {a[key]} | {b[key]} |")
    report+=['', '| Memory | A | B |','|---|---:|---:|']
    for label,key in [('Peak RSS','peak_RSS'),('Peak process commit','peak_process_commit'),('Peak system commit','peak_system_commit'),('Min free RAM','min_free_RAM')]:
        report.append(f"| {label} | {a[key]/2**30:.3f} GiB | {b[key]/2**30:.3f} GiB |")
    report+=['',f"RSS감소{100*(1-b['peak_RSS']/a['peak_RSS']):.3f}%, process commit감소{100*(1-b['peak_process_commit']/a['peak_process_commit']):.3f}%. Native bound는 A0.25295395759592587/B0.5635117196342438로 B가 더 높지만, 둘 다 이미 유효한 시작 floor0.5687115725336208보다 낮아 certified global LB를 개선하지 못했다. 마지막 후보의3,941개 위반은 모두 voltage_upper이며 최대 squared-row violation0.12322020406937549다. 두 제한 solve의 node count는 모두1로, 메모리 감소가 더 빠른 B&B를 가능하게 했다는 증거는 없다."]
    report+=['',f"Rows-added-per-iteration:{b['rows_added_per_iteration']}. 마지막 rowgen native 후보 objective0.6548888653197326은 original grid3,941행을 위반해 valid UB로 수락하지 않았다. 그 행들을 모두 추가했지만 wall 예산 종료로 추가 solve를 하지 않았다. Row generation의 scientific convergence={candidate_converged}. 최종 best UB는 양쪽 모두 원래 검증된 Start이며 full unreduced original grid exhaustive separation PASS다. 이는 마지막 개발 후보의 convergence PASS를 의미하지 않는다.",
        '',f"초기 full-domain UB/LB는 동일 과학 모델의 검증된 PR1570.6694159238756877/0.5687115725336208다. Native relaxation-subset bound만 기존1e-8 outward safety로 추가 사용했다. 선택 rate gate={selection['rate_improvement_gate']}, matched stronger-bound gate={selection['matched_strong_bound_gate']}; P1accepted={selection['P1_accepted']}, global gap.005 유지.",
        '', 'RAM/commit은 read-only 관찰이다. 순차 두 모델은 같은 process/environment를 사용하므로 allocator/cache retention이 RSS에 영향을 줄 수 있다. Memory만으로 선택하거나 production speedup을 주장하지 않았다. RAM/commit/paging 기반 stop/wait/kill/parameter 정책은 없다. Benchmark의 등록된 wall deadline만 자기 child 종료 권한을 가진다.',
        '', 'Critical gamma threshold와 PR124 compact challenger는 미시험. 3600초 canary, full May M campaign, P2, B2/B3는 실행하지 않았다.',
        '',f"Benchmark source commit:{frozen['source_commit']}. 최종 commit/Draft PR은 대화 답변에 기록한다.",'',
        '아래 문장은 알고리즘의 성공적 scientific 종료/수락 조건이다. 이번 bounded 개발 STOP은 그 종료 조건을 달성했다는 주장이 아니다.',
        '본 알고리즘은 일부 grid row로 시작하더라도 종료 전에 모든 원래',
        'grid constraint를 exhaustive separation으로 검사하고 모든 violation을',
        '제거하므로 heuristic feasible-set restriction이 아니다.','',
        'Critical-line/multi-row 선택은 계산 순서 가속에만 사용하며,',
        '최종 scientific feasibility와 optimality certificate를 대체하지 않는다.']
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(report)+'\n',encoding='utf8')
    sources=['audit_grid_rowgen.py','verify_grid_rowgen.py','benchmark_grid_rowgen.py','run_grid_comparison.py','closeout_grid_rowgen.py','v42_rowgen/core.py','v42_rowgen/native.py','v42_rowgen/__init__.py','tests/test_v42_grid_rowgen.py']
    artifacts={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'}
    write('SHA256_MANIFEST.json',dict(artifacts=artifacts,source_worktree_SHA={n:sha(ROOT/n) for n in sources},base_PR157=base,
        benchmark_source_commit=frozen['source_commit'],native_fullscale_comparisons=1))
    print('INDEPENDENT_CLOSEOUT_PASS',selection['final_state'],'artifacts',len(artifacts),'tests',stats['tests'])
if __name__=='__main__':run()
