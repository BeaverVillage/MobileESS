#!/usr/bin/env python3
"""Fail-closed validator for the C -> B Stage-7 zero-burn-in handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_IDS = [
    "W02_2025-01-13", "W07_2025-02-17", "W10_2025-03-10",
    "W17_2025-04-28", "W18_2025-05-05", "W25_2025-06-23",
    "W26_2025-06-30", "W32_2025-08-11", "W38_2025-09-22",
    "W41_2025-10-13", "W44_2025-11-03", "W51_2025-12-22",
]
HEX = set("0123456789abcdef")


def load(path: Path) -> dict:
    def reject(token: str) -> None:
        raise ValueError(f"non-RFC8259 numeric token: {token}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha(value: object) -> bool:
    text = str(value).lower()
    return len(text) == 64 and all(char in HEX for char in text)


def verify_manifest(root: Path) -> list[str]:
    errors: list[str] = []
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(None, 1)
        path = root / rel.strip().lstrip("*")
        if not path.is_file():
            errors.append(f"SHA target missing: {path.relative_to(root)}")
        elif sha256(path) != expected:
            errors.append(f"SHA mismatch: {path.relative_to(root)}")
    return errors


def validate(root: Path) -> dict:
    errors: list[str] = []
    required = [
        "C_7_FINAL_STATUS.json",
        "C_7_CURRENT_AUTHORITY.json",
        "C_TO_B_8_ORCHESTRATION_INPUT_MANIFEST.json",
        "SUPERSESSION_LINEAGE.json",
        "SHA256SUMS.txt",
    ]
    for rel in required:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")
    if errors:
        return {"status": "FAIL_CLOSED", "errors": errors}

    manifest = load(root / "C_TO_B_8_ORCHESTRATION_INPUT_MANIFEST.json")
    final = load(root / "C_7_FINAL_STATUS.json")
    if manifest.get("schema_version") != "mobileess.b.8.representative_week_zero_burnin_manifest.v2":
        errors.append("manifest schema mismatch")
    if manifest.get("controller_burn_in_steps") != 0:
        errors.append("controller_burn_in_steps != 0")
    if manifest.get("selection_window_pre_history_steps") != 576:
        errors.append("selection_window_pre_history_steps != 576")
    if manifest.get("initialization_mode") != "DETERMINISTIC_CANONICAL_COLD_START":
        errors.append("initialization mode mismatch")
    if manifest.get("stage7_evaluation_steps_executed") != 0:
        errors.append("Stage-7 evaluation must not be executed")
    if manifest.get("supersession_marker") != "SUPERSEDED_BY_STAGE7_ZERO_BURNIN_CANONICAL_INITIALIZATION":
        errors.append("supersession marker mismatch")
    source_shas = manifest.get("source_authority_shas", {})
    if not source_shas or not all(is_sha(value) for value in source_shas.values()):
        errors.append("source authority SHA set missing or malformed")

    episodes = manifest.get("representative_week_episodes")
    if not isinstance(episodes, list) or len(episodes) != 12:
        errors.append("representative_week_episodes must contain exactly 12 entries")
        episodes = [] if not isinstance(episodes, list) else episodes
    ids = [entry.get("candidate_id") for entry in episodes]
    if ids != EXPECTED_IDS:
        errors.append("representative-week identity/order mismatch")
    outputs: set[str] = set()
    checkpoints: set[str] = set()
    for entry in episodes:
        candidate = str(entry.get("candidate_id", ""))
        if entry.get("controller_burn_in_steps") != 0:
            errors.append(f"{candidate}: controller burn-in != 0")
        if entry.get("selection_window_pre_history_steps") != 576:
            errors.append(f"{candidate}: selection pre-history != 576")
        if entry.get("future_actual_used") is not False:
            errors.append(f"{candidate}: future actual flag is not false")
        if entry.get("future_plans_persisted") is not False:
            errors.append(f"{candidate}: future plan persistence is not false")
        if entry.get("method_independent_initial_state") is not True:
            errors.append(f"{candidate}: method-independent state flag is not true")
        rel = Path(str(entry.get("initializer_path", "")))
        state_path = root / rel
        if not state_path.is_file():
            errors.append(f"{candidate}: initializer file missing")
        elif sha256(state_path) != entry.get("initializer_file_sha256"):
            errors.append(f"{candidate}: initializer file SHA mismatch")
        if not is_sha(entry.get("initializer_state_sha256")):
            errors.append(f"{candidate}: malformed initializer state SHA")
        output = str(entry.get("output_namespace", ""))
        checkpoint = str(entry.get("checkpoint_namespace", ""))
        if not output or output in outputs:
            errors.append(f"{candidate}: output namespace missing/duplicate")
        if not checkpoint or checkpoint in checkpoints:
            errors.append(f"{candidate}: checkpoint namespace missing/duplicate")
        outputs.add(output)
        checkpoints.add(checkpoint)
    if final.get("status") != "15_STAGE_STEP_7_FINAL_PASS":
        errors.append("C Stage-7 final status is not PASS")
    errors.extend(verify_manifest(root))
    return {
        "schema_version": "mobileess.b.8.zero_burnin_validation.v2",
        "status": "PASS" if not errors else "FAIL_CLOSED",
        "candidate_count": len(episodes),
        "controller_burn_in_steps": manifest.get("controller_burn_in_steps"),
        "selection_window_pre_history_steps": manifest.get("selection_window_pre_history_steps"),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff_root", type=Path)
    args = parser.parse_args()
    result = validate(args.handoff_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
