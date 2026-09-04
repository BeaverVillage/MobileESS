"""Freeze the combined V19/V20 state before V21 integration work."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v21_pre_science_integration"
START_HEAD = "586431f2d014adf2750441be30eb95481908ac03"
GROUPS = {
    "v17_candidate": ROOT / "dayahead" / "artifacts" / "v17_candidate",
    "v17_flexibility_forensic": ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic",
    "v18": ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze",
    "v18r1": ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair",
    "v18r2": ROOT / "dayahead" / "artifacts" / "v18r2_aidc_forecast_magnitude_refreeze",
    "v19": ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp",
    "v20": ROOT / "dayahead" / "artifacts" / "v20_independent_authorities",
}
EXPECTED_COUNTS = {
    "v17_candidate": 369,
    "v17_flexibility_forensic": 8,
    "v18": 17,
    "v18r1": 19,
    "v18r2": 21,
    "v19": 27,
    "v20": 39,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


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


def main() -> None:
    if git("rev-parse", "HEAD") != START_HEAD:
        raise RuntimeError("V21_PRECHANGE_HEAD_MISMATCH")
    if git("status", "--porcelain"):
        # The generator itself is the only allowed untracked file at first run.
        status = git("status", "--porcelain").splitlines()
        allowed = ["?? dayahead/tools/build_v21_prechange_manifest.py"]
        if status != allowed:
            raise RuntimeError(f"V21_PRECHANGE_DIRTY:{status}")
    inventory = {name: records(path) for name, path in GROUPS.items()}
    counts = {name: len(value) for name, value in inventory.items()}
    if counts != EXPECTED_COUNTS:
        raise RuntimeError(f"V21_PRESERVATION_COUNT_MISMATCH:{counts}")
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_id": "V21_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "branch": git("branch", "--show-current"),
        "head_before_manifest": START_HEAD,
        "parents": {
            "V19": "e5acb57f25df7d9e89bae61faa24cf9d07fa6245",
            "V20": "d8a1b25ad9add4d148a1b49c4c335b9e11e690f7",
        },
        "preservation_groups": inventory,
        "preserved_artifact_counts": counts,
        "preservation_count_gate": True,
        "firewall_counters_at_start": {
            "result_based_retuning": 0,
            "April_target_reads": 0,
            "beta_AIDC_scaling_calls": 0,
            "facility_scale_calls_on_GPU_h": 0,
            "B0_B1_B2_B3_science_calls": 0,
            "OpenDSS_calls": 0,
            "AC_science_calls": 0,
        },
    }
    target = OUT / "V21_PRECHANGE_PRESERVATION_MANIFEST.json"
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(target)
    print(sha256(target))


if __name__ == "__main__":
    main()
