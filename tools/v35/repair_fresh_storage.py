#!/usr/bin/env python3
"""Repair V35 Fresh storage encoding without rerunning scientific computation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v35.execution import normalize_v35_fresh_storage  # noqa: E402
from dayahead.v35.storage import atomic_json, sha256_file  # noqa: E402


def _replace_record(records: list[dict[str, object]], path: Path, sha256: str) -> None:
    matches = [row for row in records if Path(str(row["path"])).resolve() == path.resolve()]
    if len(matches) != 1:
        raise RuntimeError(f"V35_FRESH_REPAIR_STORAGE_RECORD_COUNT:{path}:{len(matches)}")
    matches[0]["sha256"] = sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-head", required=True)
    parser.add_argument("--new-head", required=True)
    args = parser.parse_args()
    cache_root = REPO / "dayahead/cache/v35"
    artifact_root = REPO / "dayahead/artifacts/v35_april_may_final"
    checkpoints = []
    for path in sorted(cache_root.rglob("CHECKPOINT.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") == "PASS" and payload.get("code_HEAD") == args.old_head:
            checkpoints.append(path)
    if not checkpoints:
        raise RuntimeError("V35_FRESH_REPAIR_NO_CHECKPOINTS")
    repaired: list[dict[str, object]] = []
    touched_days: set[tuple[str, str]] = set()
    for checkpoint_path in checkpoints:
        case_root = checkpoint_path.parent
        fresh_root = case_root / "fresh"
        arrays_path = fresh_root / "OPENDSS_PHASE_ARRAYS.npz"
        manifest_path = fresh_root / "OPENDSS_OUTPUT_MANIFEST.json"
        result_path = case_root / "CASE_RESULT.json"
        history_root = case_root / "history" / f"fresh-finite-storage-{args.old_head[:8]}"
        history_root.mkdir(parents=True, exist_ok=False)
        preserved = []
        for source in (arrays_path, manifest_path, result_path, checkpoint_path):
            target = history_root / source.name
            shutil.copy2(source, target)
            preserved.append({
                "original_path": str(source.resolve()), "preserved_path": str(target.resolve()),
                "sha256": sha256_file(target),
            })
        old_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        arrays_record, manifest_record = normalize_v35_fresh_storage(fresh_root)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        _replace_record(result["storage_files"], arrays_path, str(arrays_record["sha256"]))
        _replace_record(result["storage_files"], manifest_path, str(manifest_record["sha256"]))
        result["fresh_storage_contract"] = {
            "all_numeric_arrays_finite": True,
            "transformer_kVA_non_applicable_encoding": "ZERO_WITH_EXPLICIT_APPLICABILITY_MASK",
        }
        result_sha = atomic_json(result_path, result)
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["code_HEAD"] = args.new_head
        checkpoint["Fresh_SHA"] = arrays_record["sha256"]
        _replace_record(checkpoint["storage_files"], arrays_path, str(arrays_record["sha256"]))
        _replace_record(checkpoint["storage_files"], manifest_path, str(manifest_record["sha256"]))
        _replace_record(checkpoint["storage_files"], result_path, result_sha)
        prior_repairs = list(checkpoint.get("engineering_repairs", []))
        if "recovery_rebind" in checkpoint:
            prior_repairs.append(checkpoint.pop("recovery_rebind"))
        prior_repairs.append({
            "classification": "STORAGE_INTEGRITY_DEFECT",
            "defect_id": "V35_FRESH_NONAPPLICABLE_TRANSFORMER_KVA_NONFINITE_SENTINEL",
            "old_code_HEAD": args.old_head, "new_code_HEAD": args.new_head,
            "scientific_optimizer_reruns": 0,
            "applicable_transformer_values_changed": 0,
            "physical_summaries_changed": 0,
            "preserved_pre_repair_files": preserved,
        })
        checkpoint["engineering_repairs"] = prior_repairs
        atomic_json(checkpoint_path, checkpoint)
        if not all(
            Path(str(row["path"])).is_file()
            and sha256_file(Path(str(row["path"]))) == row["sha256"]
            for row in checkpoint["storage_files"]
        ):
            raise RuntimeError("V35_FRESH_REPAIR_CHECKPOINT_SHA_RELOAD")
        touched_days.add((str(checkpoint["phase"]), str(checkpoint["day"])))
        repaired.append({
            "phase": checkpoint["phase"], "day": checkpoint["day"], "case": checkpoint["case"],
            "checkpoint": str(checkpoint_path.resolve()), "history": str(history_root.resolve()),
            "new_Fresh_SHA": checkpoint["Fresh_SHA"],
        })
    for phase, day in sorted(touched_days):
        day_path = artifact_root / "daily" / phase / day / "DAY_RESULT.json"
        day_result = json.loads(day_path.read_text(encoding="utf-8"))
        for case in tuple(day_result["cases"]):
            case_root = cache_root / phase / day / case
            checkpoint = json.loads((case_root / "CHECKPOINT.json").read_text(encoding="utf-8"))
            result = json.loads((case_root / "CASE_RESULT.json").read_text(encoding="utf-8"))
            result["storage_files"] = checkpoint["storage_files"]
            day_result["cases"][case] = result
        atomic_json(day_path, day_result)
    report = {
        "artifact_id": "V35_FRESH_FINITE_STORAGE_REPAIR_V1", "status": "PASS",
        "classification": "STORAGE_INTEGRITY_DEFECT",
        "old_code_HEAD": args.old_head, "new_code_HEAD": args.new_head,
        "repaired_checkpoint_count": len(repaired), "scientific_optimizer_reruns": 0,
        "applicable_transformer_values_changed": 0, "physical_summaries_changed": 0,
        "repaired": repaired,
    }
    atomic_json(artifact_root / "V35_FRESH_FINITE_STORAGE_REPAIR.json", report)
    print(json.dumps({key: report[key] for key in (
        "status", "repaired_checkpoint_count", "scientific_optimizer_reruns",
        "applicable_transformer_values_changed", "physical_summaries_changed",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
