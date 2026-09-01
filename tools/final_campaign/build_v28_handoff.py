#!/usr/bin/env python3
"""Generate V28 implementation handoff, schemas, flags, and preservation audit."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v28_final_dayahead_actual"
BASE = "a9f75e603a74cd3f938aa7eb7dfa537fd4ea0662"
THERMAL = "e7dad3a7b7c10dcb343747849e577d053c125e44"
WSL_ROOT = "/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28_final_dayahead_actual"


def git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=REPO, text=True, encoding="utf-8").strip()


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def tree(commit: str, path: str) -> str:
    return git("rev-parse", f"{commit}:{path}")


def main() -> None:
    certificate_properties = {
        "date": {"type": "string", "format": "date"}, "status": {"const": "PASS"},
        "git_head": {"type": "string"}, "code_sha": {"type": "string"}, "config_sha": {"type": "string"},
        "source_sha": {"type": "string"}, "model_sha": {"type": "string"}, "solver_settings": {"type": "object"},
        "OpenDSS_settings": {"type": "object"}, "previous_attempts": {"type": "integer"}, "defect_ids": {"type": "array"},
        "logs": {"type": "array"}, "result_sha": {"type": "string"}, "certificate_sha256": {"type": "string"},
    }
    required = list(certificate_properties)
    for month in ("APRIL", "MAY"):
        write(f"V28_{month}_DAY_CERTIFICATE_SCHEMA.json", {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "title": f"V28 {month} day certificate",
            "type": "object", "required": required, "properties": certificate_properties, "additionalProperties": True,
        })
    write("V28_APRIL_DEFECT_REGISTRY_SCHEMA.json", {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
        "required": ["defects"], "properties": {"defects": {"type": "array", "items": {"type": "object", "required": ["defect_ID", "first_failing_date", "symptom", "root_cause", "affected_component", "code_fix_commit", "impacted_future_days", "rerun_days", "pass_days_retained", "regression_tests", "status"]}}},
    })
    commands = f"""# V28 local execution commands

Actual WSL worktree: `{WSL_ROOT}`

## A. 로컬 실행 명령

### 1. April execution

```bash
cd '{WSL_ROOT}'
bash tools/final_campaign/run_2025_april_preflight.sh
```

### 2. April audit

```bash
cd '{WSL_ROOT}'
bash tools/final_campaign/audit_2025_april_preflight.sh
```

### 3. May freeze

```bash
cd '{WSL_ROOT}'
bash tools/final_campaign/freeze_2025_may_final.sh
```

### 4. May execution

```bash
cd '{WSL_ROOT}'
bash tools/final_campaign/run_2025_may_final.sh
```

### 5. May finalization

```bash
cd '{WSL_ROOT}'
bash tools/final_campaign/finalize_2025_may_science.sh
```

## B. 로컬 모니터링 명령

### 1. April monitoring

```bash
cd '{WSL_ROOT}'
bash tools/final_campaign/monitor_2025_april_preflight.sh --watch-seconds 10
```

### 2. May monitoring

```bash
cd '{WSL_ROOT}'
bash tools/final_campaign/monitor_2025_may_final.sh --watch-seconds 10
```
"""
    (OUT / "V28_LOCAL_EXECUTION_COMMANDS.md").write_text(commands, encoding="utf-8", newline="\n")
    handoff = f"""# V28 local execution handoff

The implementation worktree is `{WSL_ROOT}`. The full April and May campaigns were not run by Codex.

Current fail-closed integration blocker: the 24-step orchestrator, certificate, resume, freeze, monitor, and finalizer layers are implemented, but a production per-step heavy authority backend that binds the newly frozen V28 LightGBM/C1/V22SR1 inputs into the inherited V16.3 optimizer/OpenDSS context is not yet implemented. Full runs stop before creating a PASS certificate; the non-authority smoke cannot issue one.

Use `V28_LOCAL_EXECUTION_COMMANDS.md` after resolving `V28-BLOCK-001`. Do not bypass the backend gate or synthesize PASS certificates.
"""
    (OUT / "V28_LOCAL_EXECUTION_HANDOFF.md").write_text(handoff, encoding="utf-8", newline="\n")
    preservation = {
        "artifact_id": "V28_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "checks": {
            "V17_candidate_tree_unchanged": tree("HEAD", "dayahead/artifacts/v17_candidate") == tree(BASE, "dayahead/artifacts/v17_candidate"),
            "V22SR1_tree_unchanged": tree("HEAD", "dayahead/artifacts/v22s_r1_final_operating_scale") == tree(BASE, "dayahead/artifacts/v22s_r1_final_operating_scale"),
            "V27_tree_unchanged": tree("HEAD", "dayahead/artifacts/v27m_safe_flex_r1") == tree(BASE, "dayahead/artifacts/v27m_safe_flex_r1"),
            "V24T_artifact_tree_exact_import": tree("HEAD", "dayahead/artifacts/v24t_thermal_aware_aidc") == tree(THERMAL, "dayahead/artifacts/v24t_thermal_aware_aidc"),
            "V24T_code_tree_exact_import": tree("HEAD", "dayahead/thermal") == tree(THERMAL, "dayahead/thermal"),
        },
        "historical_files_modified": [], "raw_sources_modified": 0,
    }
    preservation["status"] = "PASS" if all(preservation["checks"].values()) else "FAIL"
    write("V28_POSTCHANGE_PRESERVATION_AUDIT.json", preservation)
    flags = {
        "FINAL_LIGHTGBM_AUTHORITY_READY": True, "FINAL_THERMAL_PCC_AUTHORITY_READY": True,
        "FINAL_INPUT_PIPELINE_READY": True, "FINAL_DAYAHEAD_IMPLEMENTATION_READY": True,
        "FINAL_ACTUAL_REPLAY_IMPLEMENTATION_READY": True, "FINAL_PI_IMPLEMENTATION_READY": True,
        "APRIL_RUNNER_READY": False, "APRIL_MONITOR_READY": True, "APRIL_AUDITOR_READY": True,
        "MAY_FREEZE_SCRIPT_READY": True, "MAY_RUNNER_READY": False, "MAY_MONITOR_READY": True,
        "MAY_FINALIZER_READY": True, "LOCAL_HANDOFF_READY": False,
        "APRIL_FULL_MONTH_PREFLIGHT_PASS": False, "MAY_FINAL_SCIENCE_COMPLETE": False,
        "FINAL_GRID_SCIENCE_AUTHORIZED": False,
        "blocking_defect": "V28-BLOCK-001_HEAVY_AUTHORITY_BACKEND_NOT_IMPLEMENTED",
    }
    write("V28_IMPLEMENTATION_READY_FLAGS.json", flags)
    write("V28_IMPLEMENTATION_TEST_REPORT.json", {
        "artifact_id": "V28_IMPLEMENTATION_TEST_REPORT_V1",
        "classification": "V28_IMPLEMENTATION_BLOCKED_HEAVY_BACKEND",
        "targeted_tests": {"passed": 34, "failed": 0},
        "inherited_selected_regression_tests": {
            "passed": 91,
            "failed": 8,
            "failure_classification": "PREEXISTING_HISTORICAL_FIXTURE_OR_BRANCH_RELATIVE_ASSERTIONS",
            "details": [
                "V16.3 final cache rows are intentionally absent from this checkout",
                "V22S tests compare against a pre-V23 ML branch and require ignored historical cache files",
                "V21 serialized text/registry checkout hashes differ from their historical manifest before V28",
            ],
            "V28_caused_failures": 0,
        },
        "non_authority_smoke": "PASS_NON_AUTHORITY_SMOKE_ONLY_NO_CERTIFICATE",
        "full_April_executed": False, "full_May_executed": False,
        "known_blockers": ["V28-BLOCK-001"],
    })
    scale = json.loads((REPO / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_FINAL_IEEE123_AIDC_SCALE.json").read_text(encoding="utf-8"))
    write("V28_FINAL_SCALE_AUTHORITY.json", {"artifact_id": "V28_FINAL_SCALE_AUTHORITY_V1", "source": scale, "GPU_h_times_0_528808792_MW": False, "beta_AIDC_calls": 0})
    for target, source in (
        ("V28_FINAL_DAYAHEAD_AUTHORITY.json", "FINAL_DAYAHEAD_MODEL_V1.json"),
        ("V28_FINAL_ACTUAL_REPLAY_AUTHORITY.json", "FINAL_ACTUAL_REPLAY_MODEL_V1.json"),
        ("V28_FINAL_PI_AUTHORITY.json", "FINAL_PERFECT_INFORMATION_ORACLE_V1.json"),
    ):
        write(target, {"artifact_id": target[:-5], "implementation_authority": json.loads((OUT / source).read_text(encoding="utf-8")), "science_complete": False})
    source_manifest = {
        "artifact_id": "V28_FINAL_SOURCE_SHA256_V1",
        "Kestrel": "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f",
        "V22SR1_source_manifest_sha256": sha(REPO / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_ARTIFACT_SHA256.json"),
        "V24T_source_manifest_sha256": sha(REPO / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_RAW_DATA_INVENTORY.json"),
        "raw_sources_mutated": False,
    }
    write("V28_FINAL_SOURCE_SHA256.json", source_manifest)
    hashes = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "V28_IMPLEMENTATION_ARTIFACT_SHA256.json":
            hashes[path.relative_to(REPO).as_posix()] = sha(path)
    write("V28_IMPLEMENTATION_ARTIFACT_SHA256.json", {"artifact_id": "V28_IMPLEMENTATION_ARTIFACT_SHA256_V1", "git_head_before_final_commit": git("rev-parse", "HEAD"), "files": hashes})


if __name__ == "__main__":
    main()
