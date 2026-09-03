"""Convert pytest JUnit output into the required test and final-review artifacts."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ART = REPO / "dayahead" / "artifacts" / "v35r3d_kestrel_runtime_authority_closure"
JUNIT = REPO / "logs" / "v35r3d_kestrel_runtime_authority_closure" / "pytest.xml"


def main() -> int:
    root = ET.parse(JUNIT).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise RuntimeError("V35R3D_JUNIT_SUITE_MISSING")
    tests = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    failed = failures + errors
    passed = tests - failed - skipped
    report = {
        "artifact_id": "V35R3D_TEST_REPORT_V1",
        "command": f"{sys.executable} -m pytest tests/v35r3d -q --junitxml={JUNIT}",
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failures": failures,
        "errors": errors,
        "PASS": failed == 0 and skipped == 0,
        "categories": [
            "ENVIRONMENT", "LINEAGE", "DATA", "FEATURE_FIREWALL", "BENCHMARK",
            "ADAPTER", "CALIBRATION", "RUNNING_JOBS", "SCHEDULER", "SCOPE",
        ],
    }
    (ART / "V35R3D_TEST_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    final_path = ART / "V35R3D_FINAL_REVIEW.json"
    final = json.loads(final_path.read_text(encoding="utf-8"))
    final["numbered_report"]["86"] = str(passed)
    final["numbered_report"]["87"] = str(failed)
    final_path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = (ART / "V35R3D_FINAL_REVIEW.md").read_text(encoding="utf-8")
    md = md.replace("86. PENDING_TEST_RUN", f"86. {passed}")
    md = md.replace("87. PENDING_TEST_RUN", f"87. {failed}")
    (ART / "V35R3D_FINAL_REVIEW.md").write_text(md, encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
