"""FORECAST_BUNDLE_V2 schema validation helpers."""

from __future__ import annotations


REQUIRED_KEYS = {
    "schema_version",
    "conditional_mean_authority",
    "Q50_authority",
    "Q90_authority",
    "mean_and_Q50_distinct",
    "GPU_h_facility_scale_multiplication_calls",
}


def validate_bundle(bundle: dict[str, object]) -> list[str]:
    """Return human-readable schema/coherence failures."""

    failures = [f"missing:{key}" for key in sorted(REQUIRED_KEYS - set(bundle))]
    if bundle.get("schema_version") != "FORECAST_BUNDLE_V2":
        failures.append("wrong_schema_version")
    if bundle.get("mean_and_Q50_distinct") is not True:
        failures.append("mean_Q50_not_distinct")
    if bundle.get("GPU_h_facility_scale_multiplication_calls") != 0:
        failures.append("GPU_h_scaled_by_facility_authority")
    return failures
