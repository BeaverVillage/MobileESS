"""Create the V16.3 final execution contract before May/June access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .authority import sha256_file
from .final_science_protocol_v16_3 import (
    AUTHORITY_COMMIT,
    AUTHORITY_ID,
    BENDERS,
    CASES,
    ELIGIBILITY,
    EVALUATION_PERIODS,
    FRESH_AC,
    GUROBI_PARAMETERS,
    GUROBI_VERSION,
    NO_TUNING_COUNTERS,
    OUTPUT_SCHEMA,
    REFREEZE_MANIFEST_SHA256,
    SCIENTIFIC_AUTHORITY_SHA256,
    STATISTICS,
)
from .run_authority_semantic_g11_v16_2 import _write_json


def execute(repo: Path, output: Path) -> dict[str, object]:
    repo = repo.resolve()
    output = output.resolve()
    authority = repo / "dayahead/artifacts/v16_3/V16_3_SCIENTIFIC_AUTHORITY.json"
    manifest = repo / "dayahead/artifacts/v16_3/V16_3_REFREEZE_MANIFEST.json"
    if sha256_file(authority) != SCIENTIFIC_AUTHORITY_SHA256:
        raise RuntimeError("FINAL_SCIENCE_FAIL_AUTHORITY_SHA_DRIFT")
    if sha256_file(manifest) != REFREEZE_MANIFEST_SHA256:
        raise RuntimeError("FINAL_SCIENCE_FAIL_REFREEZE_MANIFEST_SHA_DRIFT")
    payload = {
        "artifact_id": "V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT",
        "status": "FROZEN_COMMITTED_BEFORE_MAY_JUNE_SCIENTIFIC_ACCESS",
        "authority_id": AUTHORITY_ID,
        "authority_commit": AUTHORITY_COMMIT,
        "authority_sha256": SCIENTIFIC_AUTHORITY_SHA256,
        "refreeze_manifest_sha256": REFREEZE_MANIFEST_SHA256,
        "frozen_parameters": {
            "beta_AIDC": 0.25,
            "rho_valid": 0.10,
            "PUE": 1.30,
            "PF": 0.95,
            "objective": "MINIMUM_MAXIMUM_NORMALIZED_PHASE_LINE_CURRENT_LOADING",
            "control_semantics": "D1_FROZEN_COMMON_NATIVE_CONTROL_STATE",
            "voltage_model": "D1_AC_ANCHORED_AFFINE_VOLTAGE",
            "phase_current_model": "D1_AC_ANCHORED_AFFINE_PHASE_CURRENT_WITH_NONNEGATIVE_EPIGRAPH",
        },
        "evaluation_periods": EVALUATION_PERIODS,
        "eligibility": ELIGIBILITY,
        "cases": CASES,
        "solver": {"name": "Gurobi", "version": GUROBI_VERSION, "parameters": GUROBI_PARAMETERS},
        "benders": BENDERS,
        "fresh_AC": FRESH_AC,
        "output_schema": OUTPUT_SCHEMA,
        "statistical_aggregation": STATISTICS,
        "no_tuning_counters_at_contract_freeze": NO_TUNING_COUNTERS,
        "data_access_at_contract_creation": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "may_result_inspection_count": 0,
            "june_result_inspection_count": 0,
        },
        "protocol_mutation_after_commit_allowed": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    target = output / "V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json"
    _write_json(target, payload)
    return {"path": str(target.resolve()), "sha256": sha256_file(target), "status": payload["status"]}


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--output", type=Path, default=repo / "dayahead/artifacts/v16_3_final")
    print(json.dumps(execute(**vars(parser.parse_args(argv))), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
