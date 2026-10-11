import pytest
from v42_svr11 import milp_release


@pytest.mark.parametrize('status,seconds',[
    ('NOT_REPORTED_OR_ROOT_INCOMPLETE',None),
    ('NATIVE_LOG_ROOT_INTERRUPTED',180.),
    ('NATIVE_LOG_REPORTED',210.),
])
def test_root_release_rejects_incomplete_interrupted_or_slow_root(monkeypatch,status,seconds):
    value=dict(PASS=True,source_SHA='source',classification='EXACT_REDUCTION_AND_ROOT180_VALIDATED',
        exact_reduction_proven=True,root180_validated=True,Full_native_calls=1,
        production_results_promoted=0,old_optimization_results_read=0,old_UB_LB_gap_reused=0,
        original_and_LP_and_integer_domains_identical=True,
        full=dict(Root_LP_status=status,Root_LP_seconds=seconds))
    monkeypatch.setattr(milp_release,'_checked',lambda *args:value)
    with pytest.raises(PermissionError,match='COMPLETED_ROOT180_AND_EXACT_REDUCTION_REQUIRED'):
        milp_release._validate_root180(dict(source_SHA='source',representative_root_validation={}))
