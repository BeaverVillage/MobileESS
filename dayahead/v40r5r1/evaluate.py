from pathlib import Path
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dayahead/artifacts/v40r5r1_zero_inflation_gate_correction'
R5 = ROOT / 'dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'
BASE = '5b2f6cea014110788147a3c0e2cf0d0a046c18b1'
SCIENCE = '488ca53a66e4babc4d3bd2ccca3f97dfb3433a0c'
PRE = '9e77df9e3d607c2b1ef3ee9a6f18fe21b653634e'
CAL = '2917efa8a3b56b2bc0b897574009eb96df3cd526'
R4 = 'ff1fec3a7d8f80b3c2af496758747fafc04bad7b'
CLASSIFICATION = 'V40R5R1_ZERO_INFLATION_AWARE_EVALUATION_COMPLETE'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ('V40R5R1_' + name + '.json')).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8', newline='\n')

def allowed(p):
    return p.startswith(('dayahead/v40r5r1/', 'dayahead/artifacts/v40r5r1_zero_inflation_gate_correction/')) or (p.startswith('tests/dayahead/test_v40r5r1_') and p.endswith('.py'))

def snapshot():
    files = {}
    for directory in [ROOT / 'dayahead/v40r5', R5]:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                files[p.relative_to(ROOT).as_posix()] = sha(p)
    changed = git('diff', BASE, '--name-only').splitlines()
    assert all(allowed(p) for p in changed), changed
    return {'inherited_tree': git('rev-parse', BASE + '^{tree}'), 'R5_files_SHA256': files,
            'protected_git_diff': [p for p in changed if not allowed(p)],
            'scope': 'Full inherited Git tree identity plus materialized R5 byte hashes; no May scientific payload query'}

def calculate():
    data = np.load(R5 / 'data.npz')
    ledger = pd.read_parquet(R5 / 'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    y = data['y']
    threshold = read(R5 / 'V40R5_PREREGISTRATION.json')['burst_threshold_GPUh']
    saved = np.load(R5 / 'frozen_pipeline_predictions.npz')
    result = read(R5 / 'fits/PB1/result.json')
    trial = result['selected']['trial']
    candidates = {f"PB1_TRIAL_{r['trial']}_BC0": np.load(R5 / f"fits/PB1/trial_{r['trial']}_q.npy")[:, 1] for r in result['trials']}
    candidates[f'PB1_TRIAL_{trial}_BC1'] = saved['body_BC1'][:, 1]
    rows, feasibility = [], {}
    old = read(R5 / 'V40R5_ZERO_INFLATION_GATE_AUDIT.json')
    for role in ['CALIBRATION', 'EXPOSED_EVALUATION']:
        mask = np.repeat(((ledger.role == role) & ledger.stage_maturity_eligible).to_numpy(), 96) & (y <= threshold)
        yy = y[mask]; positive = yy > 0; zero = yy == 0
        n = len(yy); nz = int(zero.sum()); np_ = int(positive.sum())
        feasibility[role] = {'N': n, 'zero_N': nz, 'positive_N': np_, 'zero_fraction': nz/n,
            'old_overall_min_at_positive_90': .9 + .1*nz/n,
            'old_continuous_contract_incompatible': nz*2 > n,
            'corrected_min_covered_integer': (9*np_+9)//10,
            'corrected_max_covered_integer': 19*np_//20,
            'corrected_empirical_contract_feasible': (9*np_+9)//10 <= 19*np_//20}
        for name, upper in candidates.items():
            q = upper[mask]; e = q[positive] - yy[positive]
            cp = float(np.mean(yy[positive] <= q[positive]))
            co = float(np.mean(yy <= q)); cz = float(np.mean(yy[zero] <= q[zero]))
            assert cp == old['candidates'][name]['roles'][role]['positive_BODY_coverage']
            rows.append({'role': role, 'candidate': name, 'BODY_N': n, 'positive_BODY_N': np_, 'zero_N': nz,
                'positive_Q90_coverage': cp, 'positive_Q90_pinball_GPUh': float(np.maximum(-.9*e, .1*e).mean()),
                'positive_Q90_MAE_GPUh': float(np.abs(e).mean()), 'positive_Q90_WAPE': float(np.abs(e).sum()/yy[positive].sum()),
                'positive_underprediction_GPUh': float(np.maximum(-e,0).sum()), 'positive_overprediction_GPUh': float(np.maximum(e,0).sum()),
                'all_BODY_underprediction_GPUh': float(np.maximum(yy-q,0).sum()), 'all_BODY_overprediction_GPUh': float(np.maximum(q-yy,0).sum()),
                'overall_coverage_DIAGNOSTIC': co, 'zero_only_coverage_DIAGNOSTIC': cz,
                'coverage_identity_abs_error': abs(co-(zero.mean()+(1-zero.mean())*cp)),
                'positive_contract_compatible': .9 <= cp <= .95})
    return pd.DataFrame(rows), feasibility

def main():
    assert git('rev-parse', 'HEAD') == BASE
    for commit in [R4, PRE, CAL, SCIENCE, BASE]:
        assert git('rev-parse', commit) == commit
        git('merge-base', '--is-ancestor', commit, BASE)
    receipt = read(R5 / 'V40R5_FINAL_COMMIT_RECEIPT.json')
    assert receipt['classification'] == 'V40R5_BODY_FORECAST_INSUFFICIENT'
    assert receipt['selected_model'] is None
    assert read(R5/'V40R5_MODEL_SELECTION.json')['selected_model'] is None
    assert git('log', '-1', '--format=%H', '--', str((R5/'V40R5_FINAL_COMMIT_RECEIPT.json').relative_to(ROOT))) == BASE
    start = snapshot(); dump('PROTECTED_SCOPE_START', start)
    dump('START_STATE', {'base': BASE, 'branch': git('branch','--show-current'), 'worktree': str(ROOT),
        'time_UTC': datetime.now(timezone.utc).isoformat(), 'initial_inherited_state_clean': not start['protected_git_diff']})
    dump('R5_REFERENCE_FREEZE', {'scientific_commit': SCIENCE, 'receipt_commit': BASE, 'preregistration_commit': PRE,
        'CAL_freeze_commit': CAL, 'classification': receipt['classification'], 'selected_model': None,
        'optimizer_integration': 'NO', 'production_ready': 'NO', 'frozen_files': start['R5_files_SHA256']})
    dump('GIT_LINEAGE_AUDIT', {'ordered_ancestors': [R4,PRE,CAL,SCIENCE,BASE], 'verified_with_Git': True})
    dump('CORRECTED_EVALUATION_CONTRACT', {'scope': 'Prospective interpretation/evaluation of already frozen R5 predictions',
        'BODY_population': 'actual <= frozen R5 burst threshold; threshold unchanged', 'positive_BODY': 'actual > 0 within BODY',
        'positive_Q90_coverage_bounds': [.9,.95], 'overall_coverage': 'DIAGNOSTIC_ONLY_NO_UPPER_REJECTION',
        'zero_only_coverage': 'DIAGNOSTIC_ONLY', 'model_fits': 0, 'calibration_fits': 0, 'optimizer_selection': False,
        'full_R5_pipeline_reclassification': False})
    rows, feasibility = calculate(); rows.to_csv(OUT/'V40R5R1_BODY_REEVALUATION.csv', index=False)
    dump('ZERO_INFLATION_FEASIBILITY_AUDIT', {'identity': 'C_all = z + (1-z) C_positive', 'populations': feasibility,
        'independent_finding_preserved': 'BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION'})
    signal = bool(rows[rows.candidate.str.endswith('_BC1')].positive_contract_compatible.all())
    dump('INTERPRETATION', {'classification': CLASSIFICATION, 'BODY_EVALUATION_CONTRACT_CORRECTED': 'YES',
        'POSITIVE_BODY_SIGNAL_OBSERVED': 'YES' if signal else 'NO', 'FULL_R5_PIPELINE_SELECTED': 'NO',
        'OPTIMIZER_INTEGRATION': 'NO', 'PRODUCTION_READY': 'NO', 'R5_classification': receipt['classification'],
        'R5_primary_result': receipt['PRIMARY_RESULT'], 'R5_burst_hybrid_envelope_results': 'UNCHANGED',
        'new_model_fits': 0, 'new_calibration_fits': 0, 'May_scientific_reads': 0, 'shadow_scientific_reads': 0,
        'metadata_discovery': 'Git worktree/index paths and existing R5 provenance only; nonzero metadata access',
        'limitation': 'Positive BODY magnitude coverage compatibility alone does not establish full pipeline safety or confirmatory skill'})
    end = snapshot(); dump('PROTECTED_SCOPE_END',end)
    assert start == end
    dump('PROTECTED_SCOPE_DIFF', {'changed_protected_files': [], 'R5_byte_hashes_equal': True, 'PASS': True})
    review = ['# V40R5R1 최종 검토', '', CLASSIFICATION, '',
        'R5의 실패 판정과 전체 파이프라인 미선택을 유지한다. 저장된 예측의 양수 BODY 크기 평가 계약만 교정하였다.',
        '양수 Q90 coverage 90–95%를 평가하고, 전체/0값 coverage는 진단으로 분리했다. 모델·보정 재학습은 0회다.', '',
        '```text\n'+rows.to_string(index=False)+'\n```', '', 'BC1의 양수 BODY 신호는 관찰되지만 optimizer integration=NO, production ready=NO다.',
        'CAL의 기존 전체 coverage 상한은 0값 비율 때문에 구조적으로 모순되었다. 기존 burst·hybrid 실패는 그대로다.',
        '검증 결과는 V40R5R1_TEST_REPORT.json, 커밋 연결은 V40R5R1_FINAL_COMMIT_RECEIPT.json에 기록한다.']
    (OUT/'V40R5R1_FINAL_REVIEW.md').write_text('\n'.join(review)+'\n',encoding='utf-8',newline='\n')
    print(rows[['role','candidate','positive_Q90_coverage','positive_contract_compatible']].to_string(index=False))

def receipt():
    science = git('rev-parse','HEAD')
    assert git('status','--porcelain') == ''
    dump('FINAL_COMMIT_RECEIPT', {'R5_receipt_commit': BASE, 'scientific_commit': science,
        'receipt_commit_resolution': 'git log -1 --format=%H -- dayahead/artifacts/v40r5r1_zero_inflation_gate_correction/V40R5R1_FINAL_COMMIT_RECEIPT.json',
        'classification': CLASSIFICATION, 'tests': read(OUT/'V40R5R1_TEST_REPORT.json'),
        'clean_scientific_commit_verified': True, 'optimizer_integration': 'NO', 'production_ready': 'NO'})

if __name__ == '__main__':
    receipt() if len(sys.argv)>1 and sys.argv[1]=='receipt' else main()
