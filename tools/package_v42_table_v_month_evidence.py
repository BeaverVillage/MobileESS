"""Package only approved public Native0 input evidence; verify every ZIP entry."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / "docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/PR230_REPAIR_20261015"


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def record(path):
    path = Path(path)
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path.resolve()), sha256=sha, bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def add_sources(audit_root, *, compact=False):
    audit_root = Path(audit_root)
    result = {}

    def include(path, name):
        path = Path(path)
        forbidden = {"ACTUAL_INPUT_BUNDLE.JSON", "FULL_A.NPZ", "DATA.PKL", "FULL_MODEL.PKL"}
        if (not path.is_file() or path.is_symlink() or path.name.upper() in forbidden
                or path.suffix.lower() in {".npz", ".pkl", ".pickle", ".parquet"}):
            raise ValueError("NON_PUBLIC_OR_MODEL_ARTIFACT_FORBIDDEN:" + str(path))
        if name in result:
            raise ValueError("ARCHIVE_ENTRY_DUPLICATE:" + name)
        result[name] = path

    for path in sorted((audit_root / "CASES").rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".gz"}:
            raise ValueError("UNEXPECTED_CASE_ARTIFACT_TYPE:" + str(path))
        if compact and path.name in {"D0_NATIVE_PUBLIC_INPUT.json.gz", "D0_PUBLIC_KNOWN_CLASSIFICATION.json.gz"}:
            continue
        include(path, "CASES/" + path.relative_to(audit_root / "CASES").as_posix())
    if not compact:
        for manifest_path in sorted((audit_root / "CASES").glob("*/INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json")):
            manifest = read(manifest_path)
            state = manifest["initial_record"]
            current = record(state["path"])
            if any(current[k] != state[k] for k in ("sha256", "bytes")):
                raise ValueError("PUBLIC_INITIAL_STATE_SHA_DRIFT:" + manifest["day"])
            include(state["path"], "PUBLIC_INITIAL_STATES/" + manifest["day"] + "/" + Path(state["path"]).name)
            receipt = ROOT / "docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC02/INITIAL_STATES" / manifest["day"] / "INITIAL_STATE_RECEIPT.json"
            if receipt.is_file():
                include(receipt, "PUBLIC_INITIAL_STATES/" + manifest["day"] + "/INITIAL_STATE_RECEIPT.json")
    for name in ("MONTH_NATIVE0_AUDIT.json", "INDEPENDENT_INPUT_PROOF.json", "PRODUCTION_PLAN.json",
            "ORIGINAL_EXECUTOR_SNAPSHOT_MATCH.json", "KO.md"):
        include(audit_root / name, "AUDIT/" + name)
    for folder in ("EXECUTOR_SOURCE_BEFORE_SUPERVISOR_REVIEW", "EXECUTOR_SOURCE_DURING_ANCHOR_REVIEW"):
        for path in sorted((audit_root / folder).glob("*")):
            if path.is_file():
                include(path, "SOURCE_SNAPSHOTS/" + folder + "/" + path.name)
    for path in sorted((PREFIX / "DOMAIN_AUDIT01").glob("*")):
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".py"}:
            include(path, "DOMAIN_AUDIT01/" + path.name)
    for name in ("STOP_COMPLETION.json", "AS_OF_PLANNING_NATIVE_LEDGER.json", "AS_OF_K48_NATIVE_LEDGER.json"):
        include(PREFIX / "STOP_AUDIT01" / name, "NATIVE_PRESERVATION/" + name)
    for name in ("audit_v42_table_v_month.py", "rebind_v42_table_v_month.py", "table_v_frozen_context.py",
            "package_v42_table_v_month_evidence.py"):
        include(ROOT / "tools" / name, "REPRODUCE/tools/" + name)
    for name in ("test_v42_table_v_month_native0.py", "test_v42_table_v_executor_rebind.py", "test_v42_table_v_evidence_archive.py"):
        include(ROOT / "tests" / name, "REPRODUCE/tests/" + name)
    return result


def zip_info(name):
    value = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
    value.compress_type = zipfile.ZIP_DEFLATED
    value._compresslevel = 9
    value.external_attr = 0o100644 << 16
    value.create_system = 3
    return value


def verify(archive, manifest):
    manifest = read(manifest) if not isinstance(manifest, dict) else manifest
    current = record(archive)
    if any(current[k] != manifest["archive"][k] for k in ("sha256", "bytes")):
        raise ValueError("ARCHIVE_SHA_OR_BYTES_MISMATCH")
    expected = {r["archive_path"]: r for r in manifest["entries"]}
    with zipfile.ZipFile(archive) as stream:
        if len(stream.infolist()) != len(expected) or set(stream.namelist()) != set(expected):
            raise ValueError("ARCHIVE_ENTRY_MEMBERSHIP_MISMATCH")
        for info in stream.infolist():
            sha, count = hashlib.sha256(), 0
            with stream.open(info) as content:
                while block := content.read(1024 * 1024):
                    sha.update(block)
                    count += len(block)
            row = expected[info.filename]
            if sha.hexdigest() != row["sha256"] or count != row["bytes"]:
                raise ValueError("ARCHIVE_ENTRY_SHA_OR_BYTES_MISMATCH:" + info.filename)
    return dict(PASS=True, entry_count=len(expected), ZIP_SHA256=manifest["archive"]["sha256"],
        ZIP_bytes=manifest["archive"]["bytes"], all_entry_bytes_and_SHA256_verified=True)


def package(audit_root, output, *, compact=False, max_bytes=40_000_000):
    audit_root, output = Path(audit_root).resolve(), Path(output).resolve()
    proof = read(audit_root / "INDEPENDENT_INPUT_PROOF.json")
    if proof.get("status") != "PASS_31_DATES_124_TYPED_INPUT_CASES" or proof.get("case_count") != 124:
        raise ValueError("COMPLETED_124_PUBLIC_INPUT_PROOF_REQUIRED")
    if output.exists():
        raise FileExistsError("EVIDENCE_PACKAGE_APPEND_ONLY_OUTPUT_REQUIRED")
    output.mkdir(parents=True)
    sources = add_sources(audit_root, compact=compact)
    rows = [dict(archive_path=name, source=record(path), sha256=record(path)["sha256"], bytes=path.stat().st_size)
        for name, path in sorted(sources.items())]
    embedded = dict(schema="TABLE_V_MONTH_PUBLIC_EVIDENCE_ENTRY_MANIFEST_V1", scope="PUBLIC_NATIVE0_INPUTS_ONLY",
        dates=proof["dates"], case_count=124, compact=compact, entries=rows,
        future_Actual_files_included=False, sparse_FULL_or_pickle_included=False,
        approved_public_initial_states_included=not compact,
        original_files_modified=False, final_executor_rebind_included=False,
        original_input_status=proof["status"], executor_status="FINAL_REBIND_REMAINS_SEPARATE")
    embedded_bytes = json_bytes(embedded)
    archive = output / "TABLE_V_31_DAY_PUBLIC_NATIVE0_EVIDENCE.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as stream:
        for row in rows:
            path = sources[row["archive_path"]]
            with path.open("rb") as source, stream.open(zip_info(row["archive_path"]), "w") as target:
                while block := source.read(1024 * 1024):
                    target.write(block)
        stream.writestr(zip_info("ARCHIVE_ENTRY_MANIFEST.json"), embedded_bytes)
    entries = rows + [dict(archive_path="ARCHIVE_ENTRY_MANIFEST.json", sha256=digest_bytes(embedded_bytes), bytes=len(embedded_bytes),
        source="GENERATED_EMBEDDED_MANIFEST")]
    manifest = dict(schema="TABLE_V_MONTH_PUBLIC_EVIDENCE_ARCHIVE_VERIFICATION_V1",
        created_utc=datetime.now(timezone.utc).isoformat(), archive=record(archive), entries=entries,
        entry_count=len(entries), uncompressed_bytes=sum(r["bytes"] for r in entries), max_commit_archive_bytes=max_bytes,
        within_requested_size=archive.stat().st_size <= max_bytes, compact=compact,
        independent_input_proof=record(audit_root / "INDEPENDENT_INPUT_PROOF.json"),
        case_count=124, original_files_modified=False, actual_future_files_included=False,
        approved_public_initial_states_included=not compact,
        sparse_FULL_or_pickle_included=False, final_executor_rebind_included=False,
        source_package_tool=record(__file__))
    manifest["verification"] = verify(archive, manifest)
    if any(record(sources[r["archive_path"]]) != r["source"] for r in rows):
        raise ValueError("SOURCE_CHANGED_DURING_EVIDENCE_PACKAGING")
    with (output / "EVIDENCE_ARCHIVE_MANIFEST.json").open("x", encoding="utf-8", newline="\n") as target:
        target.write(json_bytes(manifest).decode())
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.verify:
        if not args.manifest:
            parser.error("--manifest is required for --verify")
        print(json.dumps(verify(args.verify, args.manifest)))
    else:
        if not args.audit_root or not args.output:
            parser.error("--audit-root and --output are required")
        result = package(args.audit_root, args.output, compact=args.compact)
        print(json.dumps(dict(archive=result["archive"], entry_count=result["entry_count"],
            uncompressed_bytes=result["uncompressed_bytes"], within_requested_size=result["within_requested_size"],
            verification=result["verification"])))


if __name__ == "__main__":
    main()
