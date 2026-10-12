"""Seal portable research artifacts after final review, without solver imports."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
TREES = ("tools/u4_primal_alns", "docs/v42_b2_u4_primal_alns_600x3")
DOCS = ROOT / TREES[1]
OUTPUT = DOCS / "ARTIFACT_INDEX.json"
BASE = "6ca7624d7eafd45d5b061ff33e262b0de32bfe8d"


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def main():
    assert git("rev-parse", "HEAD").decode().strip() == BASE, "Delivery seal must precede first commit."
    assert not git("diff", "--name-only"), "Inherited tracked files changed."
    paths = set()
    for options in [("--cached",), ("--others", "--exclude-standard")]:
        data = git("ls-files", *options, "-z", "--", *TREES)
        paths.update(p.decode("utf-8") for p in data.split(b"\0") if p)
    paths.discard(OUTPUT.relative_to(ROOT).as_posix())
    files = []
    for name in sorted(paths):
        path = ROOT / name
        assert path.is_file() and "__pycache__" not in path.parts
        data = path.read_bytes()
        files.append({"path": name, "bytes": len(data), "sha256": sha256(data).hexdigest()})
    required = [
        "COMPARISON.json", "FINAL_INDEPENDENT_UB_CERTIFICATE.json",
        "FINAL_POST_EPOCH_INDEPENDENT_CERTIFICATE.json",
        "INDEPENDENT_FINAL_RESULT_RESOURCE_EPOCH_AUDIT.json",
        "INDEPENDENT_NATIVE_RUNTIME_MEMORY_NUMERIC_AUDIT.json",
        "POST_RUN_RESOURCE_SOURCE_AUDIT.json", "RESEARCH_WALL_CLOCK.json",
        "ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json",
        "ORIGINAL_CRITICAL_GRID_POINT_COMPARISON.json", "REPORT_RENDER_RECEIPT.json",
        "REPORT_FINAL_RENDER_QA.json", "FINAL_INDEPENDENT_REPORT_REVIEW.json",
        "INDEPENDENT_SOURCE_RESOURCE_DELIVERY_REVIEW.json",
    ]
    for name in required:
        document = json.loads((DOCS / name).read_text(encoding="utf-8"))
        if name != "COMPARISON.json":
            assert document.get("PASS") is True, name
    report = DOCS / "B2_U4_PRIMAL_ALNS_600X3_FINAL_KO.md"
    rendered = json.loads((DOCS / "REPORT_RENDER_RECEIPT.json").read_text(encoding="utf-8"))
    assert sha256(report.read_bytes()).hexdigest() == rendered["report_sha256"]
    for name in ["REPORT_FINAL_RENDER_QA.json", "FINAL_INDEPENDENT_REPORT_REVIEW.json",
                 "INDEPENDENT_SOURCE_RESOURCE_DELIVERY_REVIEW.json"]:
        review = json.loads((DOCS / name).read_text(encoding="utf-8"))
        report_hash = (review["reviewed_report"]["sha256"]
                       if name == "INDEPENDENT_SOURCE_RESOURCE_DELIVERY_REVIEW.json"
                       else review["report_sha256"])
        assert report_hash == rendered["report_sha256"], name
    description = DOCS / "PR_DESCRIPTION_KO.md"
    assert sha256(description.read_bytes()).hexdigest() == rendered["description_sha256"]
    comparison = json.loads((DOCS / "COMPARISON.json").read_text(encoding="utf-8"))
    assert comparison["best_verified_UB"] == 0.5461621302242249
    assert comparison["existing_Global_LB"] == 0.46498486997548166
    assert comparison["total_actual_Native_seconds"] == 1217.7610006332397
    assert comparison["ACTUAL"] == "ACTUAL_NOT_RUN"
    receipt = {
        "schema": "V42_B2_U4_PRIMAL_ALNS_DELIVERY_ARTIFACT_INDEX_V1",
        "PASS": True,
        "generated_UTC": datetime.now(timezone.utc).isoformat(),
        "base": BASE,
        "branch": git("branch", "--show-current").decode().strip(),
        "files": files,
        "file_count_excluding_this_index": len(files),
        "total_bytes_excluding_this_index": sum(f["bytes"] for f in files),
        "self_reference": "This index excludes itself; its Git blob and commit bind the exact final bytes.",
        "scope": "Only the two new research trees. Existing Source/U4/history/task state is independently protected by the preserved audits. Native0/runtime/Raw/rejected-preparation/source-epoch evidence is retained without rewriting.",
        "Native_optimize_calls": 0,
        "solver_imports": 0,
    }
    OUTPUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"PASS": True, "artifact_count": len(files), "artifact_bytes": receipt["total_bytes_excluding_this_index"],
                      "index": str(OUTPUT), "index_sha256": sha256(OUTPUT.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
