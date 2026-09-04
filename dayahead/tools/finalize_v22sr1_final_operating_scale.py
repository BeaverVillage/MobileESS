"""Run final V22S-R1 tests, preservation audit, and artifact hashing."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(name: str, payload: object) -> None:
    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    completed = subprocess.run(
        ["python", "-m", "unittest", "tests.test_v22sr1_final_operating_scale", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    combined = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(combined)
    test_count = combined.count(" ... ok")
    if test_count != 25:
        raise AssertionError(f"Expected 25 passing tests, found {test_count}")
    write_json(
        "V22SR1_TEST_REPORT.json",
        {
            "artifact_id": "V22SR1_TEST_REPORT_V1",
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "command": "python -m unittest tests.test_v22sr1_final_operating_scale -v",
            "tests_run": test_count,
            "passed": test_count,
            "failed": 0,
            "result": "PASS",
            "T01_T25_complete": True,
        },
    )

    manifest = json.loads((OUT / "V22SR1_PRECHANGE_MANIFEST.json").read_text(encoding="utf-8"))
    changed = []
    missing = []
    for record in manifest["protected_files"]:
        path = ROOT / record["path"]
        if not path.is_file():
            missing.append(record["path"])
        elif sha256(path) != record["sha256"]:
            changed.append(record["path"])
    if changed or missing:
        raise RuntimeError({"changed": changed, "missing": missing})
    write_json(
        "V22SR1_POSTCHANGE_PRESERVATION_AUDIT.json",
        {
            "artifact_id": "V22SR1_POSTCHANGE_PRESERVATION_AUDIT_V1",
            "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "prechange_manifest_sha256": sha256(OUT / "V22SR1_PRECHANGE_MANIFEST.json"),
            "protected_file_count": manifest["protected_file_count"],
            "changed_file_count": 0,
            "missing_file_count": 0,
            "V17_through_V22S_SHA_unchanged": True,
            "ML_code_changed_files": 0,
            "result": "PASS",
        },
    )

    readme = """# V22S-R1 final operating-load scale artifacts

이 디렉터리는 `MELBOURNE_INFORMED_EQUIVALENT_12SITE_OPERATING_LOAD_CASE`의 출처 재검증, 사전등록 산술, 형상 정규화, unique-host 분모, IEEE123 등가 PCC scale, site weight 및 interface sizing을 보존한다.

이 case는 실제 2025년 4월 Melbourne 계량부하 전수조사가 아니다. 허용 표현은 **Melbourne-informed equivalent AIDC operating-load scale**이다.

재현:

```text
python dayahead/tools/build_v22sr1_final_operating_scale.py
python dayahead/tools/finalize_v22sr1_final_operating_scale.py
```

ML, forecast, GPU-h, B0–B3, OpenDSS, grid science는 호출하지 않는다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    required = {
        "V22SR1_PRECHANGE_MANIFEST.json",
        "V22SR1_SCALING_METHOD_FREEZE.json",
        "V22SR1_SOURCE_REVERIFICATION.json",
        "V22SR1_12SITE_PRIMARY_IT_EQUIVALENT_CAPACITY.csv",
        "V22SR1_CAPACITY_CONVERSION_AUDIT.json",
        "V22SR1_LOAD_UTILISATION_AUTHORITY.json",
        "V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY.json",
        "V22SR1_PRIMARY_OPERATING_IT_PROFILE.csv",
        "V22SR1_MATCHED_UNIQUE_HOST_2025_AUTHORITY.json",
        "V22SR1_HOST_DOUBLE_COUNT_AUDIT.json",
        "V22SR1_PRIMARY_MELBOURNE_PENETRATION.json",
        "V22SR1_FINAL_IEEE123_AIDC_SCALE.json",
        "V22SR1_PRIMARY_SITE_WEIGHTS.csv",
        "V22SR1_SITE_PCC_PEAKS.csv",
        "V22SR1_UTILISATION_SENSITIVITY.json",
        "V22SR1_CAPACITY_EVIDENCE_ENVELOPE.json",
        "V22SR1_PCC_INTERFACE_ENGINEERING_CONTRACT.json",
        "V22SR1_PCC_INTERFACE_SIZING.csv",
        "V22SR1_SCALE_LINEAGE_AND_DEPRECATION.json",
        "V22SR1_READY_FLAGS.json",
        "V22SR1_FINAL_REVIEW.md",
        "V22SR1_FINAL_REVIEW.json",
    }
    missing_required = sorted(name for name in required if not (OUT / name).is_file())
    if missing_required:
        raise RuntimeError(f"Missing required artifacts: {missing_required}")
    files = sorted(
        path for path in OUT.iterdir() if path.is_file() and path.name != "V22SR1_ARTIFACT_SHA256.json"
    )
    write_json(
        "V22SR1_ARTIFACT_SHA256.json",
        {
            "artifact_id": "V22SR1_ARTIFACT_SHA256_V1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "note": "This manifest excludes itself because a recursive self-hash is undefined.",
            "branch": git("branch", "--show-current"),
            "content_HEAD_before_final_commit": git("rev-parse", "HEAD"),
            "artifact_count_excluding_self": len(files),
            "artifacts": [
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for path in files
            ],
        },
    )
    print(
        json.dumps(
            {
                "tests": test_count,
                "protected": manifest["protected_file_count"],
                "artifact_count_excluding_self": len(files),
                "artifact_manifest_sha256": sha256(OUT / "V22SR1_ARTIFACT_SHA256.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
