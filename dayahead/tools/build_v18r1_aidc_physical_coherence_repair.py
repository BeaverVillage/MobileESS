from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair"
V18 = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze"
V17_FORENSIC = ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic"
OLD_MANIFEST = V18 / "V18_AIDC_REFREEZE_PRECHANGE_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_prechange_manifest() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "V18R1_PRECHANGE_PRESERVATION_MANIFEST.json"
    previous = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
    v17 = previous["preserved_files"]
    if len(v17) != 369:
        raise RuntimeError("V17_369_BASELINE_MISSING")
    v18 = [file_record(path) for path in sorted(V18.glob("*")) if path.is_file()]
    forensic = [file_record(path) for path in sorted(V17_FORENSIC.rglob("*")) if path.is_file()]
    status = [line for line in git("status", "--porcelain").splitlines() if line]
    task_output_prefix = "?? dayahead/artifacts/v18r1_aidc_physical_coherence_repair/"
    builder_path = "?? dayahead/tools/build_v18r1_aidc_physical_coherence_repair.py"
    preexisting_status = [line for line in status if line != builder_path and line != task_output_prefix]
    manifest = {
        "artifact_id": "V18R1_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"),
        "git_status_at_user_task_start": preexisting_status,
        "worktree_clean_at_user_task_start": not preexisting_status,
        "git_status_when_manifest_written": status,
        "preservation_policy": "V17 369/369, V17 flexibility forensic, and every frozen V18 artifact are byte-preserved",
        "v17_preserved_file_count": len(v17),
        "v17_preserved_files": v17,
        "v17_forensic_file_count": len(forensic),
        "v17_forensic_files": forensic,
        "v18_preserved_file_count": len(v18),
        "v18_preserved_files": v18,
        "firewall_counters_at_start": {
            "B0_B1_B2_B3_calls": 0,
            "OpenDSS_calls": 0,
            "new_grid_science_result_calls": 0,
            "literature_target_builder_reads": 0,
            "result_based_parameter_selection_calls": 0,
        },
    }
    write_json(target, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prechange-only", action="store_true")
    args = parser.parse_args()
    if args.prechange_only:
        build_prechange_manifest()
        return
    raise RuntimeError("FULL_V18R1_BUILDER_NOT_YET_IMPLEMENTED")


if __name__ == "__main__":
    main()
