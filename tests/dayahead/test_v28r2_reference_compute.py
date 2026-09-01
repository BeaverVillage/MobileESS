import json
from pathlib import Path

import numpy as np

from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.reference_compute import (
    FullNodeDistributionAdapter, build_reference_schedule, case_rack_capacity_nodeh_per_slot,
)


def test_adapter_mass_and_reference_schedule_determinism():
    probability = np.ones((7, 96, len(COHORT_IDS)), dtype=float)
    probability /= probability.sum(axis=(1, 2))[:, None, None]
    adapter = FullNodeDistributionAdapter(probability)
    arrivals = adapter.materialize(321.125, 4)
    assert abs(arrivals.sum() - 321.125) <= 1e-9
    racks = ("AIDC01_LP01", "AIDC01_LP02")
    capacities = case_rack_capacity_nodeh_per_slot(racks, {racks[0]: 0.4, racks[1]: 0.6})
    first = build_reference_schedule(arrivals, cohort_ids=COHORT_IDS, rack_ids=racks, rack_capacity_nodeh_per_slot=capacities)
    second = build_reference_schedule(arrivals.copy(), cohort_ids=COHORT_IDS, rack_ids=racks, rack_capacity_nodeh_per_slot=capacities.copy())
    assert first.canonical_bytes() == second.canonical_bytes()
    assert np.all(first.backlog_nodeh >= 0)
    assert np.all(first.p_f_ref_kw >= 0)
    assert np.all(first.g_f_ref_gpu >= 0)


def test_reference_authority_b0_b2_bytes_are_identical():
    path = Path(__file__).resolve().parents[2] / "dayahead/artifacts/v28r2_heavy_backend/V28R2_REFERENCE_SCHEDULE_DETERMINISM_TEST.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["bytes_identical"] is True
        assert payload["B0_reference_schedule_sha256"] == payload["B2_reference_schedule_sha256"]


def test_reference_builder_has_no_actual_grid_or_mess_inputs():
    import inspect

    parameters = set(inspect.signature(build_reference_schedule).parameters)
    assert parameters == {"arrivals_nodeh", "cohort_ids", "rack_ids", "rack_capacity_nodeh_per_slot"}
