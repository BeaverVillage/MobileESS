"""V2 Forecast certificates must reach their strict SVR11 loader unchanged."""
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('schema', [
    'V42_SVR11_ELECTRICAL_CERTIFICATE_V1',
    'V42_SVR11_LDC_INTERVAL_ELECTRICAL_CERTIFICATE_V2'])
def test_svr_certificate_uses_checked_loader_without_legacy_npz_relabel(monkeypatch,schema):
    from v42_pr134_b1.native import original_coefficients_for_day
    from v42_svr11 import model
    certificate=dict(schema=schema,day='2025-05-02',source_SHA='test')
    expected=object()
    def checked(actual,day):
        assert actual is certificate and day=='2025-05-02'
        return expected
    monkeypatch.setattr(model,'load_coefficients',checked)
    original=SimpleNamespace(native_coefficients=lambda c:pytest.fail('V2 reached legacy loader'))
    assert original_coefficients_for_day(original,certificate,'2025-05-02') is expected
    assert 'operating_day' not in certificate


def test_v2_loader_source_rejection_is_not_hidden_by_legacy_fallback(monkeypatch):
    from v42_pr134_b1.native import original_coefficients_for_day
    from v42_svr11 import model
    def reject(*args):
        raise PermissionError('SVR11_COEFFICIENT_EPOCH_DRIFT')
    monkeypatch.setattr(model,'load_coefficients',reject)
    with pytest.raises(PermissionError,match='EPOCH_DRIFT'):
        original_coefficients_for_day(SimpleNamespace(),dict(
            schema='V42_SVR11_LDC_INTERVAL_ELECTRICAL_CERTIFICATE_V2'),'2025-05-02')


def test_new_full_milp_version_keeps_original_1800_builder_admission():
    from v42_common_mess import VERSION
    from v42_b2_build_authority_v13.builder import admitted_native_limit
    from v42_b3_joint.policy import COMMON_MESS_VERSION,native_limit
    request=dict(algorithm_version=VERSION)
    manifest=dict(schema='V42_COMMON_U4_QUALIFICATION_V1',algorithm_version=VERSION,native_M_limit_seconds=1800)
    assert admitted_native_limit(request,manifest)==1800
    assert COMMON_MESS_VERSION==VERSION
    assert native_limit('M1')==native_limit('M2')==1800
    assert native_limit('A1')==native_limit('A2')==5400


def test_unvalidated_full_milp_campaign_cannot_release(tmp_path):
    from v42_svr11.milp_release import validate
    with pytest.raises(PermissionError,match='NOT_REAL_VALIDATED'):
        validate(tmp_path,{})
