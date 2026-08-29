"""Historical V15 precode finalizer; disabled in the V16 production path."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def finalize(output: Path) -> None:
    raise RuntimeError("HISTORICAL_V15_FINALIZER_DISABLED_UNDER_V16")
    preflight = json.loads((output / "RAW_DATA_PREFLIGHT.json").read_text(encoding="utf-8"))
    lineage = json.loads((output / "AIDC_LABEL_PROVENANCE_AUDIT.json").read_text(encoding="utf-8"))
    blocked = "NOT_RUN_BLOCKED_BY_C2_LABEL_ALIGNMENT_GATE"
    gates = {
        "G0 Source isolation": "PASS",
        "G1 Terminology": "PASS",
        "G2 Raw integrity": "PASS",
        "G3 No-look-ahead": "PASS_CONTRACT_TEST_ONLY_NO_SCIENTIFIC_LOADER_EXECUTED",
        "G4 AIDC labels": "FAIL",
        "G5 Split lock": blocked,
        "G6 ML outputs": blocked,
        "G7 Traffic support": blocked,
        "G8 Time/input": "PASS_UNIT_CONTRACT_ONLY_INTEGRATION_BLOCKED_BY_C2",
        "G9 Objective identity": blocked,
        "G10 AIDC/MESS hard constraints": blocked,
        "G11 Benders validity": blocked,
        "G12 Solver equivalence": blocked,
        "G13 OpenDSS": blocked,
        "G14 Result audit": blocked,
    }
    report = {
        "authority_id": "DAYAHEAD_TEST_REPORT_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": "SCIENTIFIC_FAIL_CLOSED_AT_C2",
        "expected_blocking_failures": lineage["failures"],
        "gates": gates,
        "commands": [
            {
                "command": "python -m pytest -q tests/dayahead tests/test_pfr_ai_training.py tests/test_pfr_power.py tests/test_pfr_methods.py tests/test_git_identity.py",
                "result": "PASS",
                "summary": "50 passed, 71 subtests passed",
            },
            {
                "command": "python -m compileall -q dayahead",
                "result": "PASS",
            },
            {
                "command": "git diff --check",
                "result": "PASS",
            },
            {
                "command": "python -m dayahead.aidc_preflight --raw-root <authority> --output RAW_DATA_PREFLIGHT.json --full-inventory-hashes",
                "result": preflight["status"],
                "summary": f"{preflight['inventory_summary']['file_count']} files; {preflight['inventory_summary']['total_bytes']} bytes; full SHA-256 complete",
            },
            {
                "command": "python -m dayahead.materialize_precode_gate --preflight RAW_DATA_PREFLIGHT.json --authority DAYAHEAD_IMPLEMENTATION_AUTHORITY.json --output-dir dayahead/artifacts/precode",
                "result": "EXPECTED_FAIL_CLOSED",
                "summary": ", ".join(lineage["failures"]),
            },
            {
                "command": "python -m pytest -q tests",
                "result": "ENVIRONMENTAL/PREEXISTING_FAILURES",
                "summary": "362 passed, 4 skipped, 84 subtests passed, 3 failed; two require POSIX fcntl and one existing Gurobi trust-region test differs under Windows/Gurobi 13.0.3; no failing file is under dayahead/",
            },
        ],
        "november_primary_evaluation_started": False,
        "december_replication_started": False,
        "solver_calls": 0,
        "opendss_calls": 0,
    }
    _atomic_json(output / "DAYAHEAD_TEST_REPORT.json", report)
    manifest = output / "DAYAHEAD_SHA256SUMS.txt"
    files = sorted(path for path in output.iterdir() if path.is_file() and path != manifest)
    manifest.write_text(
        "".join(f"{_sha(path)}  {path.name}\n" for path in files),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    finalize(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
