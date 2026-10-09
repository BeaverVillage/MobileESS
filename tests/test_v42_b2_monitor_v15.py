import json
from pathlib import Path
import numpy as np
from v42_pr134_b1.common import sha
from v42_b2_monitor_v15.actual import metric, comparison


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size)


def fixture(tmp_path, *, converged=96, summary=.8, arm='B1'):
    fresh=tmp_path/arm/'FRESH'
    (fresh/'fresh').mkdir(parents=True)
    arrays=fresh/'fresh/OPENDSS_PHASE_ARRAYS.npz'
    np.savez(arrays,branch_names=np.array(['line.L1','transformer.T1']),
             branch_kinds=np.array(['line','transformer']),
             convergence=np.arange(96)<converged,
             phase_current_loading_pu=np.tile([.8,1.3],(96,1)))
    ar=dict(path=str(arrays),sha256=sha(arrays),bytes=arrays.stat().st_size)
    fr=write(fresh/'FRESH_RESULT.json',dict(NormalAmps_current=True,converged=converged==96,
        summary=dict(case=arm,day='2025-05-01',namespace='ACTUAL',convergence_count=converged,
                     OpenDSS_solve_count=converged,rho_max_AC=summary)))
    result=tmp_path/arm/'RESULT.json'
    rr=write(result,dict(identity=dict(arm=arm,day='2025-05-01'),
                       evaluation=dict(Fresh=dict(folder=str(fresh))),files=[ar,fr]))
    return dict(arm=arm,day='2025-05-01',result=str(result),result_SHA=rr['sha256'],status='PASS')


def test_actual_max_is_line_only_and_percent(tmp_path):
    m=metric(fixture(tmp_path))
    assert m['available'] and m['loading_pu']==.8 and m['percent']==80
    assert m['transformer_excluded'] and m['converged_slots']==96


def test_pending_is_absent_not_zero():
    r=comparison({'b1':dict(arm='B1',day='2025-05-01',status='PENDING'),
                  'b2':dict(arm='B2',day='2025-05-01',status='RUNNING')})['rows'][0]
    assert not r['B1']['available'] and not r['B2']['available']
    assert r['difference_pp'] is None


def test_exact_96_converged_slots_required(tmp_path):
    assert metric(fixture(tmp_path,converged=95))['available'] is False


def test_summary_must_agree_with_sealed_arrays(tmp_path):
    m=metric(fixture(tmp_path,summary=.75))
    assert not m['available'] and 'SUMMARY_ARRAY_MISMATCH' in m['error']


def test_result_sha_drift_is_not_displayed(tmp_path):
    row=fixture(tmp_path);Path(row['result']).write_text('{}',encoding='utf-8')
    m=metric(row)
    assert not m['available'] and 'SHA_MISMATCH' in m['error']


def test_array_mutation_after_cached_read_rejected(tmp_path):
    row=fixture(tmp_path);assert metric(row)['available']
    p=tmp_path/'B1/FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz';p.write_bytes(b'mutated')
    m=metric(row)
    assert not m['available'] and 'ARRAY_SHA_MISMATCH' in m['error']


def test_difference_uses_percentage_points(tmp_path):
    one=fixture(tmp_path,arm='B1');two=fixture(tmp_path,arm='B2')
    rows=comparison({'one':one,'two':two})['rows']
    assert rows[0]['difference_pp']==0 and rows[0]['B1']['percent']==80
