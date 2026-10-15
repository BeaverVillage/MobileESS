"""Append a verified final source/typed rebind supplement to public evidence."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_v42_table_v_month import DAYS, validate_month_rows, write_new
from tools.package_v42_table_v_month_evidence import (ROOT, PREFIX, digest_bytes,
    json_bytes, read, record, verify, zip_info)


def package(rebind_root, output, *, max_combined_bytes=40_000_000):
    rebind_root, output = Path(rebind_root).resolve(), Path(output).resolve()
    final_path = rebind_root / "FINAL_EXECUTOR_REBIND.json"
    final = read(final_path)
    if (final.get("status") != "PASS_FINAL_SOURCE_NATIVE0_124_CASES"
            or final.get("dates") != list(DAYS) or final.get("case_count") != 124
            or not final.get("all_final_source_bytes_equal") or any(final["operations"].values())
            or final["final_plan_preflight"].get("blockers") != []
            or final["final_plan_preflight"].get("status") != "PASS_NATIVE0_WIRING"):
        raise ValueError("FINAL_124_NATIVE0_TYPED_AND_SOURCE_PASS_REQUIRED")
    validate_month_rows(final["cases"])
    if output.exists():
        raise FileExistsError("FINAL_EVIDENCE_SUPPLEMENT_APPEND_ONLY")
    proof_path = PREFIX / "MONTH_NATIVE0_02/INDEPENDENT_INPUT_PROOF.json"
    proof = read(proof_path)
    if record(final["original_input_audit"]["path"]) != final["original_input_audit"]:
        raise ValueError("ORIGINAL_INPUT_AUDIT_BYTE_DRIFT")
    scientific = proof["frozen_scientific_input_sources"]
    pins = list({r["path"]: r for r in final["pinned_final_source"] + scientific}.values())
    if any(record(r["path"]) != r for r in pins):
        raise ValueError("FINAL_SOURCES_CHANGED_BEFORE_EVIDENCE_PACKAGING")
    main_manifest = PREFIX / "MONTH_EVIDENCE_02/EVIDENCE_ARCHIVE_MANIFEST.json"
    main = read(main_manifest)
    verify(main["archive"]["path"], main)
    sources = {}

    def add(path, name):
        path = Path(path)
        if (not path.is_file() or path.is_symlink() or name in sources
                or path.suffix.lower() not in {".json", ".md", ".py"}
                or path.name.upper() == "ACTUAL_INPUT_BUNDLE.JSON"):
            raise ValueError("ONLY_EXPLICIT_METADATA_AND_PYTHON_SOURCE_ALLOWED:" + name)
        sources[name] = path

    for path in sorted(rebind_root.rglob("*")):
        if path.is_file():
            add(path, "FINAL_REBIND/" + path.relative_to(rebind_root).as_posix())
    add(PREFIX / "DOMAIN_AUDIT01/PRESERVATION_RECHECK_02.json", "PRESERVATION_RECHECK_02.json")
    add(PREFIX / "EXECUTOR_REBIND_FINAL01/SOURCE_DRIFT.json", "PREVIOUS_REBIND_SOURCE_DRIFT.json")
    add(proof_path, "INDEPENDENT_INPUT_PROOF.json")
    source_rows = {r["path"]: r for r in final["pinned_final_source"] + scientific
        if Path(r["path"]).suffix.lower() == ".py"}
    source_rows[str(Path(__file__).resolve())] = record(__file__)
    for path, source in sorted(source_rows.items()):
        path = Path(path)
        name = ("SOURCE/" + path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT)
            else "EXTERNAL_SOURCE/" + source["sha256"] + "/" + path.name)
        add(path, name)
    output.mkdir(parents=True)
    rows = [dict(archive_path=name, source=record(path), sha256=record(path)["sha256"],
        bytes=path.stat().st_size) for name, path in sorted(sources.items())]
    embedded = json_bytes(dict(schema="TABLE_V_FINAL_REBIND_EVIDENCE_ENTRIES_V1", entries=rows,
        case_count=124, independent_input_archive=main["archive"],
        unchanged_scientific_source_records=scientific, final_source_records=final["pinned_final_source"],
        no_future_Actual_or_sparse_model_content=True, physical_or_launch_certificate=False))
    archive = output / "TABLE_V_FINAL_EXECUTOR_NATIVE0_EVIDENCE.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for row in rows:
            stream.writestr(zip_info(row["archive_path"]), sources[row["archive_path"]].read_bytes())
        stream.writestr(zip_info("ARCHIVE_ENTRY_MANIFEST.json"), embedded)
    entries = rows + [dict(archive_path="ARCHIVE_ENTRY_MANIFEST.json", sha256=digest_bytes(embedded),
        bytes=len(embedded), source="GENERATED_EMBEDDED_MANIFEST")]
    manifest = dict(schema="TABLE_V_FINAL_REBIND_ARCHIVE_VERIFICATION_V1",
        created_utc=datetime.now(timezone.utc).isoformat(), archive=record(archive), entries=entries,
        entry_count=len(entries), uncompressed_bytes=sum(r["bytes"] for r in entries),
        independent_public_input_archive=main["archive"], final_typed_rebind=record(final_path),
        combined_archive_bytes=archive.stat().st_size + main["archive"]["bytes"],
        max_combined_archive_bytes=max_combined_bytes, scientific_and_executor_source_bytes_unchanged=True,
        source_package_tool=record(__file__), physical_or_launch_certificate=False)
    manifest["within_requested_size"] = manifest["combined_archive_bytes"] <= max_combined_bytes
    manifest["verification"] = verify(archive, manifest)
    if (any(record(r["path"]) != r for r in pins)
            or any(record(sources[r["archive_path"]]) != r["source"] for r in rows)):
        raise ValueError("FINAL_EVIDENCE_SOURCE_DRIFT_DURING_PACKAGING")
    write_new(output / "EVIDENCE_ARCHIVE_MANIFEST.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebind-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = package(args.rebind_root, args.output)
    print(result["archive"], "entries=" + str(result["entry_count"]),
        "combined_bytes=" + str(result["combined_archive_bytes"]))
    if not result["within_requested_size"]:
        raise SystemExit(2)
