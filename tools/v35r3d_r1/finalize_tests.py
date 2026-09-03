"""Write the R1 test report and update final-review counters."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ART = REPO / "dayahead" / "artifacts" / "v35r3d_r1_running_residual_accounting"
JUNIT = REPO / "logs" / "v35r3d_r1_running_residual_accounting" / "pytest.xml"


def main() -> int:
    root = ET.parse(JUNIT).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise RuntimeError("V35R3D_R1_JUNIT_MISSING")
    tests = int(suite.attrib.get("tests", 0))
    failed = int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    passed = tests - failed - skipped
    report = {
        "artifact_id": "V35R3D_R1_TEST_REPORT_V1",
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "PASS": failed == 0 and skipped == 0,
        "categories": [
            "LINEAGE", "REUSE", "RUNNING_JOB", "CALIBRATION", "START_ACCOUNTING",
            "CAPACITY", "CRITICAL_WINDOWS", "CAUSALITY", "SCOPE",
        ],
    }
    (ART / "V35R3D_R1_TEST_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    final_path = ART / "V35R3D_R1_FINAL_REVIEW.json"
    final = json.loads(final_path.read_text(encoding="utf-8"))
    final["numbered_report"]["85"] = str(passed)
    final["numbered_report"]["86"] = str(failed)
    final_path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = ART / "V35R3D_R1_FINAL_REVIEW.md"
    md = md_path.read_text(encoding="utf-8")
    md = md.replace("85. PENDING_TEST_RUN", f"85. {passed}")
    md = md.replace("86. PENDING_TEST_RUN", f"86. {failed}")
    md_path.write_text(md, encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
