#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import py_compile
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "driver_r25r_stage1_resume136.py": "f41c9019301a68b23a43d6521fe37e69a868c115cd57806f2e97ba23f8a1a4e0",
    "R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz": "4c2e39b4f136f36a6d3c13f61acb93a7f32b256cfc75d06404cef8fe9ddf312d",
}
FROZEN_BUNDLE_MEMBERS = {
    "CHECKSUMS.sha256": "2b586ebe307298d132aab2d96389e9ef8e97fba05082c9d892e3729c01974e0d",
    "main.py": "911abe18479524b8e48cc058c4a6ed3b8ab9ce673d4de78780a71ca3b7f0a5cd",
    "r25m_b6_exact_path_decomposition.py": "cab1b8cef906b08eaaa75d5e044fcb34ffc45183b24c5c4d8cfddb3508c58795",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    checks = []
    for relative, expected in FROZEN.items():
        actual = sha(ROOT / relative)
        checks.append({"check": f"frozen:{relative}", "pass": actual == expected, "actual": actual})
    with tarfile.open(ROOT / "R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz", "r:gz") as archive:
        members = {member.name.removeprefix("./"): member for member in archive.getmembers()}
        for relative, expected in FROZEN_BUNDLE_MEMBERS.items():
            member = members.get(relative)
            payload = archive.extractfile(member).read() if member is not None else b""
            actual = hashlib.sha256(payload).hexdigest()
            checks.append({"check": f"frozen_bundle_member:{relative}", "pass": actual == expected, "actual": actual})
    for path in sorted((ROOT / "r26").glob("*.py")) + [ROOT / "driver_r25s_stage1_resume_latest.py", ROOT / "driver_r25t_stage1_resume_latest.py"]:
        try:
            py_compile.compile(str(path), doraise=True)
            checks.append({"check": f"compile:{path.name}", "pass": True})
        except Exception as exc:
            checks.append({"check": f"compile:{path.name}", "pass": False, "error": repr(exc)})
    for relative in (
        "r26/config/r26_contract.json",
        "r26/config/event_config.schema.json",
        "r26/config/event_config.example.json",
        "r26/config/smoke_54.example.json",
        "r26/config/experiment_matrix.json",
        "r26/R26_RUNTIME_DIAGNOSIS_ISSUE149.json",
    ):
        try:
            json.loads((ROOT / relative).read_text(encoding="utf-8"))
            checks.append({"check": f"json:{relative}", "pass": True})
        except Exception as exc:
            checks.append({"check": f"json:{relative}", "pass": False, "error": repr(exc)})
    unit = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    checks.append(
        {
            "check": "r26_unit_and_integration_tests",
            "pass": unit.returncode == 0,
            "stdout_tail": unit.stdout[-2000:],
            "stderr_tail": unit.stderr[-4000:],
        }
    )
    result = {
        "schema_version": "r26.static_validation.v1",
        "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
        "long_solver_run_performed": False,
        "real_opendss_smoke_performed": False,
        "frozen_r25r_unchanged": all(
            row["pass"] for row in checks if row["check"].startswith(("frozen:", "frozen_bundle_member:"))
        ),
        "checks": checks,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
