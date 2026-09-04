from pathlib import Path

from dayahead.authority import AUTHORITY_IDS, FROZEN_DIGESTS, authority_fingerprint


def test_frozen_authority_ids_are_exact() -> None:
    assert AUTHORITY_IDS["scientific_framework_id"] == "V16_1_DA_AIDC_ICPS_BOUNDARYSEP"
    assert AUTHORITY_IDS["objective_authority"] == "MAX_NORMALIZED_LINE_CURRENT_OBJECTIVE_V1"
    assert AUTHORITY_IDS["aidc_quantile_calibration"] == "NONE_V1"
    assert AUTHORITY_IDS["reference_compute_schedule"] == "REFERENCE_COMPUTE_SCHEDULE_V3"


def test_frozen_digests_and_fingerprint_are_valid() -> None:
    for digest in FROZEN_DIGESTS:
        digest.validate()
    assert len(authority_fingerprint()) == 64
