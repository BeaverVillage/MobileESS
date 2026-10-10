"""Exact envelope admission and cache isolation; no Model or Native entry."""
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from v42_m1_anytime.dual_stabilization import ProvedEnvelope, StageIdentity, DualSearch
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha
from v42_b2_seed_recovery_v18 import certificate_box
from v42_m1_research.check_lb import check_rational_dual_certificate


def fixture():
    A=csr_matrix([[1.,0.],[-2.,1.]])
    d=dict(lower=np.array([0.,-np.inf]),upper=np.array([1.,np.inf]),
           rhs=np.array([.5,0.]),sense=np.array(['=','=']),objective=np.array([1.,0.]),
           constant=np.asarray(0.),types=np.array(['C','C']),names=np.array(['x[0]','helper[0]']),
           row_names=np.array(['fixed_x[0]','helper_binding[0]']))
    identity=StageIdentity('B2_M','2025-05-01','a'*64,'b'*64,'d'*64,'c'*64,matrix_sha(A),_domain_sha(d))
    return SimpleNamespace(A=A,d=d,case_sha=identity.case_sha),identity


def envelope(identity,**overrides):
    options=dict(derive=certificate_box.derive,verify=certificate_box.verify,validate=lambda:None)
    return ProvedEnvelope(identity,**dict(options,**overrides))


def test_actual_select_uses_proved_view_and_original_independent_checker():
    p,i=fixture();before=_domain_sha(p.d);box=envelope(i);calls=[]
    def certify(y):
        calls.append(y)
        return box.check(p.A,p.d,y,checker=check_rational_dual_certificate,case_sha=p.case_sha)
    result=DualSearch(i,finite_box=box).select(p,{}, {'0':'64'},0,certify=certify)
    assert result['status']=='QUALIFIED' and Fraction(result['certificate']['exact_bound'])==Fraction(1,2)
    assert result['Global_LB_published'] is False and calls
    assert (box.derive_calls,box.verify_calls)==(1,1) and box.cache_hits>=1
    assert _domain_sha(p.d)==before and np.isneginf(p.d['lower'][1]) and np.isposinf(p.d['upper'][1])


def test_cache_reuses_once_and_returns_independent_copies():
    p,i=fixture();box=envelope(i);lo,hi,proof=box(p.A,p.d)
    lo[1]=-999.;proof['steps'].clear()
    next_lo,next_hi,next_proof=box(p.A,p.d)
    assert next_lo[1]==0. and next_hi[1]==2. and len(next_proof['steps'])==1
    assert (box.derive_calls,box.verify_calls,box.cache_hits)==(1,1,1)


@pytest.mark.parametrize('field',['matrix_sha','domain_sha'])
def test_wrong_selected_matrix_or_domain_sha_rejected(field):
    p,i=fixture();box=envelope(replace(i,**{field:'0'*64}))
    with pytest.raises(ValueError,match='IDENTITY_DRIFT'):box(p.A,p.d)
    assert box.derive_calls==box.verify_calls==0


def test_source_or_fixed_input_validator_rechecked_on_cache_hit():
    p,i=fixture();valid=[True]
    def validate():
        if not valid[0]:raise PermissionError('AUDITED_SOURCE_OR_FIXED_INPUT_DRIFT')
    box=envelope(i,validate=validate);box(p.A,p.d);valid[0]=False
    with pytest.raises(PermissionError,match='SOURCE_OR_FIXED_INPUT_DRIFT'):box(p.A,p.d)
    assert (box.derive_calls,box.verify_calls)==(1,1)


def test_other_stage_or_day_proof_cannot_be_transplanted():
    p,i=fixture();first=envelope(i);first(p.A,p.d)
    for changed in (replace(i,stage='B3_M1'),replace(i,stage='B3_M2'),replace(i,day='2025-05-02')):
        other=envelope(changed);other._cache=first._cache
        with pytest.raises(ValueError,match='CACHE_OR_STAGE_PROOF_DRIFT'):other(p.A,p.d)


def test_inward_rounded_envelope_rejected_by_original_independent_replay():
    p,i=fixture()
    def bad(A,d):
        lo,hi,proof=certificate_box.derive(A,d)
        proof['steps'][0]['lower']=float(np.nextafter(lo[1],np.inf));lo[1]=proof['steps'][0]['lower']
        return lo,hi,proof
    box=envelope(i,derive=bad)
    with pytest.raises(ValueError,match='INWARD_ROUNDING'):box(p.A,p.d)
    assert box._cache is None


def test_cache_bound_tamper_rejected_without_rederiving():
    p,i=fixture();box=envelope(i);box(p.A,p.d)
    lo=box._cache[0];lo.flags.writeable=True;lo[1]=-1.
    with pytest.raises(ValueError,match='CACHE_OR_STAGE_PROOF_DRIFT'):box(p.A,p.d)
    assert (box.derive_calls,box.verify_calls)==(1,1)


def test_foreign_certificate_case_or_restricted_box_rejected():
    p,i=fixture();box=envelope(i)
    with pytest.raises(ValueError,match='CERTIFICATE_CASE_DRIFT'):
        box.check(p.A,p.d,{},checker=check_rational_dual_certificate,case_sha='0'*64)
    with pytest.raises(ValueError,match='FOREIGN_CERTIFICATE_BOX'):
        box.check(p.A,p.d,{},checker=check_rational_dual_certificate,case_sha=p.case_sha,lower=np.array([.1,0.]))


def test_finite_original_domain_does_not_invoke_envelope_proof():
    p,i=fixture();p.d['lower'][1]=0.;p.d['upper'][1]=2.;i=replace(i,domain_sha=_domain_sha(p.d))
    box=envelope(i,derive=lambda *a:pytest.fail('UNNECESSARY_DERIVE'),verify=lambda *a:pytest.fail('UNNECESSARY_VERIFY'))
    lo,hi,proof=box(p.A,p.d)
    assert np.array_equal(lo,p.d['lower']) and np.array_equal(hi,p.d['upper'])
    assert proof['finite_original_box'] and box.derive_calls==box.verify_calls==0
