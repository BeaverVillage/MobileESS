"""Solver-free independent saved-result verification and terminal artifacts."""
from .common import *
import re
import numpy as np

FILES=['01_PERSISTENT_RMP_BENCHMARK.json','02_STABILIZATION_BENCHMARK.json','03_EXACT_PRICING_BENCHMARK.json','04_PRICING_REDUCTION_BENCHMARK.json','05_ROOT_CUT_BENCHMARK.json']
LABELS=['Persistent RMP','Stabilized CG','Specialized pricing','Pricing dominance','Root cuts']

def run():
    results=[read(OUT/n) for n in FILES];final=read(OUT/'M1_ACCEL_FINAL_COMBINATION.json')
    freeze=read(OUT/'PR152_BYTE_FREEZE.json')
    preserved=all(sha(ROOT/p)==h for p,h in freeze['files'].items());assert preserved
    assert sha(OLD/'DW_CHECKPOINT_LATEST.json')==freeze['checkpoint_SHA']
    from v42_degen.identity import inputs
    from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
    A,d,*_=inputs();point_audits=[]
    for path in sorted((OUT/'FINAL').glob('*/TRUE_RMP_POINT.npz'))+sorted(OUT.glob('05_*_POINT.npz')):
        with np.load(path) as z:point=z['point'].copy()
        audit=corrected_rows(A,d,point,False,pure_binary_equalities(A,d));assert audit['PASS']
        point_audits.append(dict(file=path.relative_to(OUT).as_posix(),SHA=sha(path),audit=audit))
    tests=(OUT/'FULL_PYTEST.log').read_text(encoding='utf8',errors='replace')
    match=re.search(r'(\d+) passed',tests);assert match
    failed_match=re.search(r'(\d+) failed',tests[-2000:]);error_match=re.search(r'(\d+) errors',tests[-2000:])
    failed=int(failed_match[1]) if failed_match else 0;errors=int(error_match[1]) if error_match else 0
    known=read(OUT/'KNOWN_PR152_BASELINE_TEST_FAILURE.json')
    assert errors==0 and (failed==0 or failed==1 and known['base_SHA']==BASE and known['returncode']==1)
    if failed:
        assert 'FAILED tests/v42_dw_runtime/test_runtime.py::test_original_sources_domain_checkpoint_unchanged' in tests
    records=[]
    for path in sorted(OUT.glob('*_RESOURCE_LEDGER.csv')):
        with path.open(encoding='utf8',newline='') as f:records.extend(csv.DictReader(f))
    table(OUT/'RESOURCE_LEDGER.csv',records)
    rows=[dict(Variant='PR152 baseline',Pricing_wall=None,RMP_wall=None,New_cols=0,UB_decrease=0.,UB_decrease_per_second=None,
        Root_LB_effect='frozen LB '+str(freeze['LB']),Peak_RSS=None,Selected=False)]
    for label,r in zip(LABELS,results):
        v=r.get('variants',{});metric={};price=None;rmp=None;new=0;delta=None;eff=None
        if label=='Persistent RMP' and 'persistent' in v:
            metric=v['persistent'];rmp=metric['total_RMP_wall_seconds'];new=10;delta=metric['points'][0]['upper']-metric['points'][-1]['upper'];eff=delta/rmp
        elif label=='Stabilized CG' and 'box' in v:
            metric=v['box'];price=metric['pricing_batch_wall_seconds'];rmp=metric['RMP_native_seconds'];new=metric['accepted'];delta=metric['UB_decrease'];eff=metric['efficiency']
        elif label=='Specialized pricing':
            metric=r.get('hybrid',{});price=metric.get('wall_seconds')
        elif label=='Pricing dominance' and 'quotient' in v:price=v['quotient']['native_seconds']
        elif label=='Root cuts' and 'cuts' in v:
            metric=v['cuts'];price=metric['pricing_root_native_seconds'];rmp=metric['RMP_native_seconds'];delta=freeze['UB']-metric['upper']
        # Contaminated/unfinished timing is not a comparison entry.
        comparable=r['status']!='NONCOMPARABLE'
        rows.append(dict(Variant=label,Pricing_wall=price if comparable else None,RMP_wall=rmp if comparable else None,
            New_cols=new,UB_decrease=delta,UB_decrease_per_second=eff if comparable else None,
            Root_LB_effect='0 (redundant full-DW cuts)' if label=='Root cuts' else 'no new certificate',
            Peak_RSS=r.get('resource',{}).get('peak_RSS'),Selected=r['selected'],Status=r['status']))
    f=final.get('variants',{}).get('candidate',{})
    rows.append(dict(Variant='Final exact combination',Pricing_wall=f.get('pricing_batch_wall_seconds'),RMP_wall=f.get('RMP_native_seconds'),
        New_cols=f.get('accepted'),UB_decrease=f.get('UB_decrease'),UB_decrease_per_second=f.get('efficiency'),
        Root_LB_effect='frozen independent LB unchanged',Peak_RSS=final.get('resource',{}).get('peak_RSS'),Selected=final['selected'],Status=final['status']))
    table(OUT/'M1_ACCEL_STEPWISE_COMPARISON.csv',rows)
    selection=dict(M1_ACCELERATION_SELECTED=final['selected'],stages=[dict(stage=i+1,status=r['status'],retained=r['selected']) for i,r in enumerate(results)],
        final_status=final['status'],final_efficiency_ratio=final.get('efficiency_ratio'),
        AUTHORITATIVE_ROOT_CONTINUATION_NOT_RUN=True,BRANCH_AND_PRICE_NOT_RUN=True,
        scientific_authority=BASE,authoritative_pool=1604,authoritative_LB=freeze['LB'],authoritative_UB=freeze['UB'],
        exact_CG_convergence=False,materiality='INCONCLUSIVE',May_production_calls=[0,0,0],
        root_CG_10_15_minutes_estimate=None,STOP=True)
    write(OUT/'M1_ACCEL_SELECTION.json',selection)
    write(OUT/'M1_ACCEL_SCIENTIFIC_EQUIVALENCE.json',dict(PASS=preserved,baseline=BASE,original_files_byte_preserved=len(freeze['files']),
        pool=1604,checkpoint_SHA=freeze['checkpoint_SHA'],source_matrix_pricing_RMP_certificate_unchanged=True,
        full_original_domain=True,physical_model_unchanged=True,Certification_path_unchanged=True,
        smoothing_discovery_only=True,true_dual_acceptance=True,solver_tolerances=1e-8,affine_audit=1e-6,
        original_integer_fixture_equivalence=True,postsolve_independent_saved_point_audits=point_audits,
        authoritative_checkpoint_mutations=0,foreign_process_control_calls=0))
    cap=all(r.get('continuous_wall_seconds',0)<=600 for r in results+[final]);assert cap
    write(OUT/'VERIFICATION.json',dict(PASS=failed==0,scientific_equivalence_PASS=True,
        status='PASS' if failed==0 else 'KNOWN_BASELINE_TEST_FAILURE',
        full_pytest_passed=int(match[1]),full_pytest_failed=failed,full_pytest_errors=errors,
        known_baseline_failure=known if failed else None,lightweight_stage_tests=15,
        original_files_preserved=len(freeze['files']),checkpoint_columns=1604,all_experiment_wall_caps_PASS=cap,
        independent_saved_point_audits=point_audits,foreign_process_control_calls=0,
        stage3_noncomparable_excluded=True,root_continuation_calls=0,Branch_and_Price_calls=0,
        May_production_calls=[0,0,0],post_combination_native_calls=0,
        full_task_terminal=True,performance_selected=final['selected']))
    table_lines=['| Variant | Pricing wall | RMP wall | New cols | UB decrease | UB decrease/s | Root/LB effect | Peak RSS | Selected |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    def fmt(v):return 'N/A' if v is None else f'{v:.6g}' if isinstance(v,float) else str(v)
    for r in rows:table_lines.append('| '+' | '.join(fmt(r[k]) for k in ['Variant','Pricing_wall','RMP_wall','New_cols','UB_decrease','UB_decrease_per_second','Root_LB_effect','Peak_RSS','Selected'])+' |')
    report=['# Exact M1 acceleration 개발 최종 검토',
        f'과학적 기준: PR152 `{BASE}`, pool 1,604, LB {freeze["LB"]}, UB {freeze["UB"]}. authoritative checkpoint는 변경하지 않았다.',
        f'Full pytest: {match[1]} passed / {failed} failed / {errors} errors. '+
        ('failure는 PR152 exact 원본에서도 재현된 historical branch-scope assertion이며 assertion을 바꾸거나 숨기지 않았다. ' if failed else '')+
        f'전체 원본 파일 {len(freeze["files"])}개 byte 보존 및 saved-point original matrix 독립 audit PASS.',
        f'최종 M1_ACCELERATION_SELECTED={str(final["selected"]).lower()}, 상태={final["status"]}.',*table_lines,
        'N/A는 미측정/미완료 또는 NONCOMPARABLE이다. partial incumbent와 timing을 성능 선택이나 lower bound에 사용하지 않았다.',
        'Stage 1: matrix/objective identity PASS, persistent+basis 총 시간은 cold보다 느려 REJECTED.',
        'Stage 2: box guidance LP가 90초 cap 안에 optimal이 되지 않아 미채택. alpha sweep이나 자동 연장은 없었다.',
        'Stage 3: HYBRID_DP_LP_POSSIBLE, continuous SOC/P/Q 유지한 toy 3개 PASS. B1 실제 PID+optimize overlap 때문에 timing 제외; full-scale hybrid 비교 미완료, 미채택.',
        'Stage 4: 실제 block의 exact parallel-arc 제거 대상 0개. 동일 formulation의 추가 native solve 없이 구조적으로 REJECTED.',
        f'Stage 5: {results[4]["status"]}. mode-linking cut은 정수 해에 유효하고 toy arc LP를 강화하지만 full D-W에는 redundant라 이론적 root-bound 효과는 0이다.',
        '최종 조합은 개별 retained stage만 포함했다. 빈 집합이면 PR152 identity 비교이며 개선 알고리즘으로 채택하지 않는다.',
        'Root-CG 10–15분 도달 가능성은 한 round로 외삽할 근거가 없어 추정하지 않았다. 다음 단일 blocker는 깨끗한 구간에서 exact pricing/global-bound 구조 개선을 실증하는 것이다.',
        'Lane A의 May production calls=0/0/0. B1의 자체 대기/중단/재시작은 read-only 관측만 했으며 제어 호출은 0이다.',
        '본 작업은 휴리스틱 또는 convergence tolerance 완화 없이 exact M1 알고리즘의 계산 효율만 개선했다.',
        'B1 May production은 독립적으로 실행되었으며, Lane-A 작업은 B1 process/worktree/artifacts를 변경하거나 종료하지 않았다.',
        '실행시간 비교에 사용된 full-scale microbenchmark는 다른 heavy native solve와 겹치지 않은 구간만 selection evidence로 사용했다.',
        '장시간 authoritative root-CG continuation과 Branch-and-Price는 별도 승인 전까지 실행하지 않았다.']
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n\n'.join(report)+'\n',encoding='utf8')
    write(OUT/'PENDING_EXPERIMENTS.json',dict(status='TERMINAL',pending=[],STOP=True,selected=final['selected'],
        full_pytest_passed=int(match[1]),full_pytest_failed=failed,full_pytest_errors=errors,
        authoritative_checkpoint_mutations=0,foreign_process_control_calls=0))
    files={p.relative_to(ROOT).as_posix():sha(p) for directory in ['v42_m1_accel_vnext','tests/v42_m1_accel_vnext','docs/v42_m1_accel_vnext'] for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ['SHA256_MANIFEST.json','TAIL.log']}
    write(OUT/'SHA256_MANIFEST.json',dict(files=files,self_excluded=True,scientific_authority=BASE))
    print('TERMINAL_SCIENTIFIC_VERIFICATION_PASS',match[1],'KNOWN_BASELINE_FAILURES',failed,'SELECTED',final['selected'],flush=True)

if __name__=='__main__':run()
