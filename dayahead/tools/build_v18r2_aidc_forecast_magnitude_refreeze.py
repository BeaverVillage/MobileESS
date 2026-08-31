from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v18r2_aidc_forecast_magnitude_refreeze"
V17 = ROOT / "dayahead" / "artifacts" / "v17_candidate"
V17_FORENSIC = ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic"
V18 = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze"
V18R1 = ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair"
TASK_START_HEAD = "7f0b9e71b4e2120377b4cc44daa7763b03d30b3f"
TASK_START_STATUS = [
    "?? dayahead/artifacts/v18r1_aidc_physical_coherence_repair/V18R1_KESTREL_CAPACITY_TIMELINE_AUTHORITY.tar",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def records(directory: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_prechange_manifest() -> None:
    groups = {
        "v17_candidate": records(V17),
        "v17_forensic": records(V17_FORENSIC),
        "v18": records(V18),
        "v18r1": records(V18R1),
    }
    manifest = {
        "artifact_id": "V18R2_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "branch_at_task_start": "codex/dayahead-aidc-joint-v1",
        "head_at_task_start": TASK_START_HEAD,
        "actual_branch_when_manifest_written": git("branch", "--show-current"),
        "actual_head_when_manifest_written": git("rev-parse", "HEAD"),
        "git_status_at_task_start": TASK_START_STATUS,
        "preexisting_untracked_file_policy": "PRESERVE_BYTE_EXACT; DO_NOT_ADD_DELETE_MODIFY_OR_COMMIT",
        "preservation_groups": groups,
        "counts": {name: len(items) for name, items in groups.items()},
        "firewall_counters_at_start": {
            "B0_B1_B2_B3_calls": 0,
            "OpenDSS_calls": 0,
            "grid_science_calls": 0,
            "literature_target_reads": 0,
            "objective_reads_for_model_selection": 0,
            "workload_multiplier_fit_to_share": 0,
            "C_MODEL_mutations": 0,
        },
    }
    write_json(OUT / "V18R2_PRECHANGE_PRESERVATION_MANIFEST.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prechange-only", action="store_true")
    args = parser.parse_args()
    if args.prechange_only:
        build_prechange_manifest()
        return
    raise SystemExit("full V18R2 build is not implemented yet")


if __name__ == "__main__":
    main()
