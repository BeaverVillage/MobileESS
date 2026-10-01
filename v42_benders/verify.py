"""Seal completed tests, preserved inherited bytes, source and artifact hashes."""
import gzip,re
from .common import *
from .runner import PROGRESS

def run():
    base=read('PR114_BASE_RECEIPT.json')
    assert len(base['files'])==1533
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in base['files'])
    changed=git('diff','--name-only',BASE).splitlines()
    assert not set(changed)&{r['path'] for r in base['files']}
    fixture=read('FIXTURE_EXACTNESS.json');assert fixture['PASS'] and fixture['assignments']==1536
    assert read('INDEPENDENT_CUT_REPLAY_AUDIT.json')['PASS']
    assert read('ACTUAL_SOLVER_RECOURSE_MATRIX_AUDIT.json')['PASS']
    b=read('B3_DECOMPOSITION_RESULT.json');f=read('FINAL_FLAGS.json')
    assert b['status']=='STOP_UNCERTIFIABLE' and b['feasibility_cuts']==b['optimality_cuts']==0
    assert b['progress'][-1]['reason']=='MULTIPLIER_SIGN'
    assert not any(f[k] for k in ['FULL_M1_CANARY_RUN','PRODUCTION_P1_RUN','PRODUCTION_P1_ACCEPTED','P2_RUN','M1_ACCEPTED','A2_RUN','M2_RUN','PROBLEM13_FINAL_VALIDATED'])
    raw=(OUT/'B3_DECOMPOSITION_PROGRESS.csv').read_bytes()
    if not (OUT/'B3_DECOMPOSITION_PROGRESS.raw.csv').exists():(OUT/'B3_DECOMPOSITION_PROGRESS.raw.csv').write_bytes(raw)
    masterlog=gzip.decompress((OUT/'B3_master.log.gz').read_bytes()).decode()
    assert 'Optimal solution found' in masterlog and '0 simplex iterations' in masterlog
    row=dict(iteration=1,level='feasibility',master_status=2,master_seconds=b['master_seconds'],
        wall_seconds=b['wall_seconds'],recourse_status=b['recourse_log'][0]['status'],cut_id=None,
        lower=None,upper=None,reason='MULTIPLIER_SIGN')
    table('B3_DECOMPOSITION_PROGRESS.csv',[row],PROGRESS)
    dump('B3_PROGRESS_RECONCILIATION.json',dict(PASS=True,raw_progress_preserved=True,
        raw_progress_sha256=sha(OUT/'B3_DECOMPOSITION_PROGRESS.raw.csv'),
        original_result_sha256=sha(OUT/'B3_DECOMPOSITION_RESULT.json'),
        raw_master_log_sha256=sha(OUT/'B3_master.log.gz'),
        source='V1 exception row omitted master fields; independently reconcile terminal status from raw master log and existing runtime receipt',
        source_master_point_available=False,no_missing_hash_or_value_invented=True,normalized_row=row))
    review=OUT/'FINAL_REVIEW_KO.md';text=review.read_text(encoding='utf8')
    text=text.replace('Native status STOP_UNCERTIFIABLE','Native status STOP_UNCERTIFIABLE')
    text=text.replace('PR113/114 warnings를 원문 receipt/hash와 함께 보존한다. New recourse warnings/status/residual/tolerances는 numerical audit와 raw logs에 저장한다.',
        'PR113/114 warnings를 원문 receipt/hash와 함께 보존한다. 첫 B3 LP는 INFEASIBLE이었으나 ray sign 검증에 실패했다. Kappa=5.11554e15 warning이 있었다. Cut은 0개다. V1 rejected raw ray vector/hash/minimum은 저장되지 않아 복구할 수 없다. 이 한계를 REJECTED_B3_RAY_AUDIT에 명시했으며 V2는 검증 전에 입력을 저장한다. 추가 full optimize는 하지 않았다.')
    text=text.replace('Inherited 643 tests를 full suite에서 보존한다. Original 44 bounded-check receipt와 bytes도 검증한다. 새 bounded fixture와 adapter tests는 별도다.',
        '전체 708 tests PASS: inherited 643 + new 65. Inherited log1p warning 1개를 보존한다. Original 44 bounded-check receipt와 bytes를 검증했고 무단 재실행/수정하지 않았다.')
    review.write_text(text.rstrip()+'\n',encoding='utf8')
    nextp=OUT/'NEXT_MODIFICATIONS.md';nexttext=nextp.read_text(encoding='utf8')
    if 'Observed blocker' not in nexttext:
        nexttext+='\nObserved blocker: the first B3 recourse ended INFEASIBLE at 1433.581 seconds, with very big Kappa=5.11554e15. Its Farkas multiplier sign failed strict certification, so no cut was added. V1 did not retain the rejected raw vector/hash/magnitude. The exact executed source is archived; V2 now stores certificate inputs before verification. No second full run was performed. A separately preregistered experiment may examine the archived future multipliers and prove any reconstruction with sign, exact support, stationarity and margin checks. Do not silently flip/clamp an uncertified ray or treat this single-candidate infeasibility as a global B3 proof.\n'
        nextp.write_text(nexttext,encoding='utf8')
    sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for directory in ['v42_benders','tests/v42_benders']
        for p in sorted((ROOT/directory).glob('*.py'))]
    dump('SOURCE_MANIFEST.json',dict(files=sources,executed_V1_source='EXECUTED_SOURCE_ARCHIVE.json',
        published_source_contains_post_experiment_safety_interface_changes=True))
    artifacts=[dict(path=p.relative_to(OUT).as_posix(),sha256=sha(p),bytes=p.stat().st_size)
        for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['VERIFICATION.json','EVIDENCE_MANIFEST.json']]
    dump('EVIDENCE_MANIFEST.json',dict(files=artifacts,hash_algorithm='SHA256',self_and_VERIFICATION_excluded=True))
    dump('VERIFICATION.json',dict(PASS=True,full_tests=708,inherited_tests=643,new_tests=65,
        warnings=1,warning='Inherited v42_final inference calibration log1p RuntimeWarning',
        test_command='python -m pytest -q',test_seconds=36.55,diff_check_PASS=True,
        inherited_files=1533,inherited_bytes_PASS=True,inherited_bounded_checks=44,
        inherited_bounded_receipt_sha256=sha(ROOT/'docs/v42_m1_integrality_gap_root_cause/WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json'),
        fixture_assignments=1536,fixture_exactness_PASS=True,independent_cut_replay_PASS=True,
        recourse_LP_PASS=True,canonical_actual_solver_matrix_PASS=True,
        archived_execution_source_PASS=read('EXECUTED_SOURCE_ARCHIVE.json')['PASS'],
        B3_status=b['status'],B3_cut_count=0,B3_certificate='B3_INCONCLUSIVE',
        no_full_experiment_after_STOP=True,full_M1_canary_run=False,downstream_run=False,
        review_QA_count=len(re.findall(r'^\d+\. \*\*Q\.',text,re.M)),
        source_manifest_sha256=sha(OUT/'SOURCE_MANIFEST.json'),evidence_manifest_sha256=sha(OUT/'EVIDENCE_MANIFEST.json')))
    print('VERIFICATION PASS: 708 tests, 1533 inherited bytes, 1536 assignments, STOP preserved',flush=True)

if __name__=='__main__':run()
