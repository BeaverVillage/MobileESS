from types import SimpleNamespace
import pytest
from v42_a_stage_acceptance.schedule_audit import original_schedule_metrics

def test_original_references_and_checkpoint_count_are_independent_of_affine_claim():
    jobs={'a':SimpleNamespace(reference_start=10,reference_site='A'),
          'b':SimpleNamespace(reference_start=20,reference_site='B')}
    schedule={'a':dict(start=12,initial_site='B',checkpoint=-1),
              'b':dict(start=19,initial_site='B',checkpoint=7)}
    metrics,residuals=original_schedule_metrics(jobs,schedule,dict(migration_count=1,shift_magnitude=3,prestart_relocation=1))
    assert metrics==dict(migration_count=1,shift_magnitude=3,prestart_relocation=1)
    assert max(residuals.values())==0
    with pytest.raises(ValueError,match='OBJECTIVES_MISMATCH'):
        original_schedule_metrics(jobs,schedule,dict(migration_count=1,shift_magnitude=2,prestart_relocation=1))

def test_missing_original_job_prevents_acceptance():
    with pytest.raises(ValueError,match='JOB_POPULATION_CHANGED'):
        original_schedule_metrics({'a':object()}, {}, {})
