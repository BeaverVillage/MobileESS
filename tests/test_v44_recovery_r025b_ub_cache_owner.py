from unittest.mock import patch
import pytest
from v44_recovery_r025b import a2_cache,ub_downstream


def result():
    return dict(policy='R025B_NATIVE60_PHASE1000_UB',UB_feasible_only=True,PASS=True,
        FULL_feasible=True,P2_calls=0,freeze={'fixture':True},allow_downstream=True,
        independent_Global_LB_validated=False,certified_gap=None)


def test_ub_cache_owner_requires_independent_physical_proof_instead_of_gap():
    parent=result()
    with patch.object(ub_downstream,'verify_ub',return_value={'PASS':True}) as verify:
        assert a2_cache.accepted_owner(parent)
        verify.assert_called_once_with(parent)


def test_missing_physical_proof_is_not_silently_accepted():
    with patch.object(ub_downstream,'verify_ub',side_effect=ValueError('bad physical proof')):
        with pytest.raises(ValueError,match='physical proof'):a2_cache.accepted_owner(result())


def test_legacy_certified_cache_and_current_r025_ub_both_remain_compatible():
    assert a2_cache.accepted_owner(dict(independent_Global_LB_validated=True,certified_gap=.004))
    assert not a2_cache.accepted_owner(dict(independent_Global_LB_validated=False,certified_gap=None))
    parent=dict(result(),policy='R025_NATIVE60_PHASE400_UB')
    with patch.object(ub_downstream,'verify_ub',return_value={'PASS':True}):assert a2_cache.accepted_owner(parent)
