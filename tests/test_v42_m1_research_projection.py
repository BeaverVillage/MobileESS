"""Pure adversarial exact row projection and immutable admission-view checks."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_m1_research import projection_rows as projection
from v42_m1_research import final_admission as admission


@pytest.fixture
def case(monkeypatch):
    # aux = Pdis-Pch+1/2; fixed=2. Original row:
    # -2rho + aux + 3fixed + Q/4 <= 10.
    A = sparse.csr_matrix([[-2.,0.,0.,.25,1.,3.],
                          [0.,1.,-1.,0.,1.,0.]])
    d = dict(names=np.array(['rho_max','Pch[MESS01,STA01,66]',
                            'Pdis[MESS01,STA01,66]','Q[MESS01,STA01,66]',
                            'response_line_P[66,0]','response_line_correction[66,0]']),
             row_names=np.array(['line_thermal_face','response_line_P_binding']),
             rhs=np.array([10.,.5]),sense=np.array(['<','=']),
             lower=np.array([0.,0.,0.,-10.,-100.,2.]),
             upper=np.array([100.,100.,100.,10.,100.,2.]),
             objective=np.array([1.,0.,0.,0.,0.,0.]),constant=np.array(0.))
    monkeypatch.setattr(projection,'FIXED_ROWS',(0,))
    return SimpleNamespace(A=A,d=d,case_sha='synthetic_projection_case')


def test_fraction_exact_elimination_and_negative_rho_division(case):
    packet=projection.project_rows(case)[0]
    assert packet['exact_projected_coefficients']=={'0':'-2','1':'-1','2':'1','3':'1/4'}
    assert packet['exact_projected_rhs']=='7/2'
    assert packet['exact_native_equality_multipliers']=={'1':'-1'}
    assert packet['exact_fixed_native_bound_equality_multipliers']=={'5':'-3'}
    expression=packet['direct_rho_lower_requirement']
    assert expression['exact_constant']=='-7/4'
    assert expression['exact_physical_coefficients']=={'1':'-1/2','2':'1/2','3':'1/8'}
    checked=projection.verify_projection_packet(case,[packet])
    assert checked['PASS'] and checked['new_cut_or_LB_strengthening'] is False
    assert checked['rows'][0]['slots']==[66]


@pytest.mark.parametrize('pch,pdis,q,rho',[(F(1),F(5),F(2),F(10)),
    (F(1,7),F(2,3),F(-5,8),F(0)),(F(0),F(0),F(0),F(11,16))])
def test_exact_residual_preserved_when_original_equalities_hold(case,pch,pdis,q,rho):
    packet=projection.project_rows(case)[0]
    values=[rho,pch,pdis,q,pdis-pch+F(1,2),F(2)]
    original=sum(F(float(v))*values[j] for j,v in enumerate(case.A.toarray()[0]))-10
    received=sum(F(v)*values[int(j)] for j,v in packet['exact_projected_coefficients'].items())-F(packet['exact_projected_rhs'])
    assert original==received
    assert (original<=0)==(received<=0)


def test_greater_than_source_has_negative_normalization_and_no_false_rho_lb(case):
    case.d['sense'][0]='>'
    packet=projection.project_rows(case)[0]
    assert packet['source_normalization_sign']==-1
    assert packet['direct_rho_lower_requirement'] is None
    assert projection.verify_projection_packet(case,[packet])['PASS']
    packet['source_normalization_sign']=1
    with pytest.raises(ValueError,match='INEQUALITY_SIGN_DRIFT'):
        projection.verify_projection_packet(case,[packet])


@pytest.mark.parametrize('field,key',[
    ('exact_projected_coefficients','1'),('exact_native_equality_multipliers','1'),
    ('exact_fixed_native_bound_equality_multipliers','5')])
def test_exact_coefficient_or_equality_multiplier_mutation_rejected(case,field,key):
    packet=projection.project_rows(case)[0]
    packet[field][key]=str(F(packet[field][key])+F(1,2**100))
    with pytest.raises(ValueError,match='COEFFICIENT_OR_RHS_MISMATCH'):
        projection.verify_projection_packet(case,[packet])


def test_native_inequality_cannot_be_used_as_unrestricted_equality(case):
    packet=projection.project_rows(case)[0]
    packet['exact_native_equality_multipliers']={'0':'1'}
    with pytest.raises(ValueError,match='NOT_NATIVE_EQUALITY'):
        projection.verify_projection_packet(case,[packet])


def test_nonfixed_native_bound_cannot_be_substituted(case):
    packet=projection.project_rows(case)[0]
    case.d['upper'][5]=2.0000000000000004
    with pytest.raises(ValueError,match='FIXED_BOUND_NOT_NATIVE_EQUALITY'):
        projection.verify_projection_packet(case,[packet])


def test_reported_rho_rearrangement_is_recomputed(case):
    packet=projection.project_rows(case)[0]
    packet['direct_rho_lower_requirement']['exact_constant']='7/4'
    with pytest.raises(ValueError,match='RHO_REARRANGEMENT_COEFFICIENT_DRIFT'):
        projection.verify_projection_packet(case,[packet])


def test_unresolved_auxiliary_is_not_claimed_as_pq_only(case):
    case.d['row_names'][1]='unregistered_definition'
    case.d['lower'][5]=0.;case.d['upper'][5]=3.
    packet=projection.project_rows(case)[0]
    assert not packet['PQ_rho_only'] and packet['direct_rho_lower_requirement'] is None
    assert projection.verify_projection_packet(case,[packet])['rows'][0]['PQ_rho_only'] is False


@pytest.mark.parametrize('kind',['empty','duplicate','wrong_row','boolean_row'])
def test_fixed_packet_completeness_empty_duplicate_and_substitution_rejected(case,kind):
    packet=projection.project_rows(case)[0]
    packets=[packet]
    if kind=='empty':packets=[]
    elif kind=='duplicate':packets=[packet,deepcopy(packet)]
    elif kind=='wrong_row':packet['source_row']=1
    else:packet['source_row']=False
    with pytest.raises(ValueError,match='FIXED_ROW_PACKET_COVER_INCOMPLETE_OR_DUPLICATED'):
        projection.verify_projection_packet(case,packets)


@pytest.mark.parametrize('wrong_case',['another_day',None])
def test_projection_packet_requires_same_case_even_if_coefficients_match(case,wrong_case):
    packet=projection.project_rows(case)[0]
    if wrong_case is None:packet.pop('case_sha')
    else:packet['case_sha']=wrong_case
    with pytest.raises(ValueError,match='CASE_IDENTITY_DRIFT'):
        projection.verify_projection_packet(case,[packet])


def test_fixed_row_packet_cannot_omit_or_reorder_a_valid_row(case,monkeypatch):
    case.A=sparse.vstack([case.A,case.A[0]],format='csr')
    case.d['rhs']=np.r_[case.d['rhs'],case.d['rhs'][0]]
    case.d['sense']=np.concatenate([case.d['sense'],np.array(['<'])])
    case.d['row_names']=np.concatenate([case.d['row_names'],np.array(['transformer_kVA'])])
    monkeypatch.setattr(projection,'FIXED_ROWS',(0,2))
    packets=projection.project_rows(case)
    assert projection.verify_projection_packet(case,packets)['PASS']
    for invalid in (packets[:1],list(reversed(packets))):
        with pytest.raises(ValueError,match='FIXED_ROW_PACKET_COVER_INCOMPLETE_OR_DUPLICATED'):
            projection.verify_projection_packet(case,invalid)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_evidence_remap_changes_only_operational_path_and_checks_copy(tmp_path):
    original=tmp_path/'original';view=tmp_path/'view'
    original.mkdir();view.mkdir()
    source=original/'dual.npz';source.write_bytes(b'unchanged exact multiplier bytes')
    target=view/'dual.npz';target.write_bytes(source.read_bytes())
    payload=dict(case_sha='same',ledger=dict(calls=[dict(Runtime=1.)]),
        cover=dict(original_binary_columns=list(range(8)),exact_leaf_rows=[dict(sense='<',rhs=3),dict(sense='>',rhs=4)]),
        leaves=[dict(certificate=dict(dual_evidence=dict(path=str(source),sha256=_digest(source),format='EXACT')))])
    before=deepcopy(payload)
    admission.repoint_evidence(payload,original.resolve(),view.resolve())
    before['leaves'][0]['certificate']['dual_evidence']['path']=str(target)
    assert payload==before
    assert source.read_bytes()==target.read_bytes()
    target.write_bytes(b'changed multiplier')
    with pytest.raises(ValueError,match='COPIED_EVIDENCE_BYTE_DRIFT'):
        admission.repoint_evidence(dict(dual_evidence=dict(path=str(source),sha256=_digest(source))),original.resolve(),view.resolve())


def test_evidence_reference_cannot_escape_original_run(tmp_path):
    original=tmp_path/'original';view=tmp_path/'view';original.mkdir();view.mkdir()
    outside=tmp_path/'outside.npz';outside.write_bytes(b'not an original-run artifact')
    with pytest.raises(ValueError,match='EVIDENCE_OUTSIDE_ORIGINAL_RUN'):
        admission.repoint_evidence(dict(dual_evidence=dict(path=str(outside),sha256=_digest(outside))),original.resolve(),view.resolve())


def _make_final_view_fixture(tmp_path,monkeypatch,*,near_integer=False,inflight=False):
    root=tmp_path/'repo';base=root/'runtime/v42_m1_joint_gap_research';reports=root/'docs'
    original=base/'registered';original.mkdir(parents=True);reports.mkdir()
    monkeypatch.setattr(admission,'ROOT',root)
    monkeypatch.setattr(admission,'REPORTS',reports)
    ledger=dict(inflight={} if inflight else None,case_sha='same',calls=[dict(Native_Runtime=10.)])
    cover=dict(case_sha='same',original_binary_columns=list(range(8)),exact_leaf_rows=[dict(sense='<',rhs=3),dict(sense='>',rhs=4)])
    result=dict(case_sha='same',ledger=deepcopy(ledger),UB=dict(best_validated_global_UB=.6),
                JOINT_DISJUNCTION=dict(cover=cover,row_proof_evidence=dict(path=str(original/'cover.json'),sha256='pending')))
    (original/'cover.json').write_text(json.dumps(cover))
    result['JOINT_DISJUNCTION']['row_proof_evidence']['sha256']=_digest(original/'cover.json')
    (original/'NATIVE_RUNTIME_LEDGER.json').write_text(json.dumps(ledger))
    (original/'RESEARCH_TRACK_RESULTS.json').write_text(json.dumps(result))
    np.savez_compressed(original/'FINAL_VALID_UB_POINT.npz',point=np.array([.6,1e-14]))
    np.savez_compressed(reports/'U2_RAW_POINT.npz',point=np.array([.6,0.]))
    (reports/'FINAL_STRICT_ADMITTED_UB_POINT.npz').write_bytes((reports/'U2_RAW_POINT.npz').read_bytes())
    check=dict(PASS=True,objective=.6,C3A=dict(integer_pattern_exact=True,exact_binary_0_1=True),
               original_full_matrix=dict(integer_pattern_exact=not near_integer,exact_binary_0_1=not near_integer))
    monkeypatch.setattr(admission,'validate_candidate',lambda c,p:check)
    case=SimpleNamespace(case_sha='same')
    return original,reports,case


def test_final_view_preserves_original_checkpoint_ledger_cover_and_uses_exact_gate(tmp_path,monkeypatch):
    original,reports,case=_make_final_view_fixture(tmp_path,monkeypatch)
    before={p.name:p.read_bytes() for p in original.iterdir()}
    view,receipt=admission.create_view(original,case=case)
    assert {p.name:p.read_bytes() for p in original.iterdir()}==before
    assert (view/'NATIVE_RUNTIME_LEDGER.json').read_bytes()==before['NATIVE_RUNTIME_LEDGER.json']
    assert (view/'cover.json').read_bytes()==before['cover.json']
    assert (view/'FINAL_VALID_UB_POINT.npz').read_bytes()==(reports/'U2_RAW_POINT.npz').read_bytes()
    assert (view/'FINAL_VALID_UB_POINT.npz').read_bytes()!=before['FINAL_VALID_UB_POINT.npz']
    adjusted=json.loads((view/'RESEARCH_TRACK_RESULTS.json').read_text())
    old=json.loads(before['RESEARCH_TRACK_RESULTS.json'])
    assert adjusted['ledger']==old['ledger']
    assert adjusted['JOINT_DISJUNCTION']['cover']==old['JOINT_DISJUNCTION']['cover']
    assert adjusted['JOINT_DISJUNCTION']['row_proof_evidence']['path']==str(view/'cover.json')
    assert receipt['additional_Native_optimize_calls']==0 and receipt['repairs']==receipt['rounding']==receipt['clipping']==0


def test_final_view_tolerant_pass_does_not_admit_near_zero_original_arc(tmp_path,monkeypatch):
    original,_,case=_make_final_view_fixture(tmp_path,monkeypatch,near_integer=True)
    before={p.name:p.read_bytes() for p in original.iterdir()}
    with pytest.raises(ValueError,match='RAW_ORIGINAL_INTEGER_PATTERN_NOT_EXACT'):
        admission.create_view(original,case=case)
    assert {p.name:p.read_bytes() for p in original.iterdir()}==before
    assert not (original.parent/(original.name+'_final_strict_admission_view')).exists()


def test_final_view_refuses_inflight_run_before_any_copy(tmp_path,monkeypatch):
    original,_,case=_make_final_view_fixture(tmp_path,monkeypatch,inflight=True)
    with pytest.raises(ValueError,match='REGISTERED_RUN_NOT_FINALIZED'):
        admission.create_view(original,case=case)
    assert not (original.parent/(original.name+'_final_strict_admission_view')).exists()
