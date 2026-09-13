"""Verify archived bytes and recorded stop gates; never import scientific code."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Manifest path escapes snapshot: {relative}")
    return path


def verify():
    manifest = read(HERE / "SOURCE_COPY_MANIFEST.json")
    seen = set()
    for row in manifest["files"]:
        assert row["path"] not in seen, row["path"]
        seen.add(row["path"])
        p = contained(HERE, row["path"])
        assert p.stat().st_size == row["bytes"], row["path"]
        assert digest(p) == row["sha256"], row["path"]
    for row in manifest["coverage"]:
        assert digest(contained(REPO, row["repository_path"])) == row["sha256"], row
    assert len(manifest["coverage"]) == 193
    selection = read(HERE / "may06/BACKGROUND_SELECTION.json")
    assert selection["status"] == "NO_FEASIBLE_B0_ON_USER_GRID"
    assert selection["selected"] is None and selection["B1_B2_B3_runs"] == 0
    screen = read(HERE / "may06/BACKGROUND_SCREEN_TABLE.json")
    assert [r["alpha_BG"] for r in screen] == [0.60, 0.65, 0.70]
    for row in screen:
        assert row["date"] == "2025-05-06" and row["AIDC_scale"] == 1.0
        assert row["B0_max_phase_line_loading"] > 1.0
        assert not row["exact_AC_feasible"]
        assert row["converged_slots"] == row["control_settled_slots"] == 96
        assert all(row[f"{p}_max_phase_line_loading"] is None for p in ("B1", "B2", "B3"))
    for name in ("may06/screen_b0.py", "may06/finalize_report.py"):
        ast.parse((HERE / name).read_text(encoding="utf-8-sig"), filename=name)
    raw = read(HERE / "MAY21_FULL_RAW_FILE_MANIFEST.json")
    index = read(HERE / "MAY21_FULL_RAW_INDEX.json")
    assert len(raw) == index["source_file_count"] == 23709
    assert len({r["path"] for r in raw}) == len(raw)
    assert sum(r["bytes"] for r in raw) == index["source_bytes"]
    may06 = read(HERE / "MAY06_EXTERNAL_ARCHIVE.json")
    assert may06["readback"] == "ALL_MEMBER_SHA256_MATCH"
    assert may06["source_preservation"] == "SHA_SIZE_MTIME_UNCHANGED"
    return {"status": "PASS", "copied_files": len(seen), "code_document_coverage": 193,
            "raw_manifest_files": len(raw), "May06_B0_stop_gate": "PASS",
            "scientific_execution_count": 0}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
