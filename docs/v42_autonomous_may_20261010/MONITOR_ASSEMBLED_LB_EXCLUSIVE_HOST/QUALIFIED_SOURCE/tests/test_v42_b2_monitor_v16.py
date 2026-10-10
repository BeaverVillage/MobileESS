import json
from pathlib import Path
from fractions import Fraction
import pytest
from v42_pr134_b1.common import sha
from v42_b2_monitor_v16.certificates import bounds, enrich


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')
    return path


def setup(tmp_path, ub='4/5', lb='3/5'):
    output=tmp_path/'output'
    write(output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha='case',day='2025-05-01',arm='B2'))
    point=output/'point.npz';point.write_bytes(b'current-worker-point')
    u=dict(PASS=True,case_sha='case',exact_Global_UB=ub,point_path=str(point),
           point_file_sha256=sha(point),strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
           original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha='case'))
    l=dict(PASS=True,case_sha='case',status='EXACT_STORED_RATIONAL_BOUND_CERTIFIED',
           native_objective_used=False,native_BestBd_used=False,exact_bound=lb)
    return output,u,l


def worker(tmp_path,output):
    request=write(tmp_path/'request.json',dict(output=str(output),result=str(tmp_path/'RESULT.json')))
    write(tmp_path/'NATIVE_RUNTIME_LEDGER.json',dict(inflight=dict(track='M_SEED')))
    return dict(day='2025-05-01',request=str(request),UB=None,independent_Global_LB=None,
                global_gap_display=dict(available=False,value=None))


def test_current_seed_has_explicit_reasons_and_no_invented_zero(tmp_path):
    output,_,_=setup(tmp_path)
    w=enrich(worker(tmp_path,output))
    assert w['bound_status']['phase_label']=='초기 정수해 탐색'
    assert '정수해 탐색' in w['bound_status']['UB_reason']
    assert w['UB'] is None and w['independent_Global_LB'] is None
    assert not w['global_gap_display']['available']
    assert not w['bound_status']['solver_bounds_available']


def test_ub_is_available_before_next_progress_callback(tmp_path):
    output,u,_=setup(tmp_path)
    write(output/'INITIAL_STRICT_UB_CERTIFICATE.json',u)
    w=enrich(worker(tmp_path,output))
    assert w['UB']==.8 and w['independent_Global_LB'] is None
    assert not w['global_gap_display']['available']
    assert w['bound_status']['UB_certificate']['sha256']==sha(output/'INITIAL_STRICT_UB_CERTIFICATE.json')


def test_pair_and_rational_gap(tmp_path):
    output,u,l=setup(tmp_path)
    write(output/'INITIAL_STRICT_UB_CERTIFICATE.json',u)
    write(output/'INITIAL_EXACT_LB_CERTIFICATE.json',l)
    w=enrich(worker(tmp_path,output))
    assert w['UB']>=.8 and w['independent_Global_LB']<=.6
    assert w['Certified_Gap']==.25 and w['global_gap_display']['available']


def test_current_frontier_is_bound_to_both_certificate_shas(tmp_path):
    output,u,l=setup(tmp_path)
    up=write(output/'u.json',u);lp=write(output/'l.json',l)
    write(output/'frontier/CURRENT_CERTIFIED_STATE.json',dict(case_sha='case',
        UB_certificate_path=str(up),UB_certificate_sha256=sha(up),exact_UB='4/5',
        LB_certificate_path=str(lp),LB_certificate_sha256=sha(lp),exact_LB='3/5',exact_gap='1/4'))
    assert bounds(output,'2025-05-01')['Gap']==.25
    u['exact_Global_UB']='3/4';write(up,u)
    with pytest.raises(ValueError,match='SHA_MISMATCH'):bounds(output,'2025-05-01')


def test_foreign_day_and_case_are_rejected(tmp_path):
    output,u,_=setup(tmp_path)
    assert bounds(output,'2025-05-02')=={}
    u['case_sha']='other';write(output/'INITIAL_STRICT_UB_CERTIFICATE.json',u)
    with pytest.raises(ValueError,match='CASE_MISMATCH'):bounds(output,'2025-05-01')


def test_failed_candidate_and_native_bestbd_never_become_certificates(tmp_path):
    output,u,_=setup(tmp_path);u['PASS']=False
    write(output/'SAME_DAY_STATIONARY_CANDIDATE.json',u)
    w=worker(tmp_path,output);w['progress']=dict(Native_BestBd=.7,MIPGap=.01,Native_ObjVal=.8)
    value=enrich(w)
    assert value['UB'] is None and value['independent_Global_LB'] is None
    assert value['global_gap_display']['value'] is None


def test_ub_point_mutation_detected_after_cached_read(tmp_path):
    output,u,_=setup(tmp_path);write(output/'INITIAL_STRICT_UB_CERTIFICATE.json',u)
    assert bounds(output,'2025-05-01')['UB']['value']>=.8
    Path(u['point_path']).write_bytes(b'mutated')
    with pytest.raises(ValueError,match='POINT_SHA_MISMATCH'):bounds(output,'2025-05-01')


def test_inconsistent_exact_bracket_is_not_clamped(tmp_path):
    output,u,l=setup(tmp_path,ub='1',lb='1000000000000000001/1000000000000000000')
    write(output/'INITIAL_STRICT_UB_CERTIFICATE.json',u);write(output/'INITIAL_EXACT_LB_CERTIFICATE.json',l)
    value=enrich(worker(tmp_path,output))
    assert 'BRACKET_INVALID' in value['bound_status']['certificate_error']
    assert value['UB'] is None and value['independent_Global_LB'] is None
    assert not value['global_gap_display']['available']


def test_certificate_path_cannot_escape_current_worker(tmp_path):
    output,u,l=setup(tmp_path)
    up=write(tmp_path/'other-worker/u.json',u);lp=write(output/'l.json',l)
    write(output/'frontier/CURRENT_CERTIFIED_STATE.json',dict(case_sha='case',
        UB_certificate_path=str(up),UB_certificate_sha256=sha(up),exact_UB='4/5',
        LB_certificate_path=str(lp),LB_certificate_sha256=sha(lp),exact_LB='3/5',exact_gap='1/4'))
    with pytest.raises(ValueError,match='OUTSIDE_CURRENT_WORKER'):bounds(output,'2025-05-01')
