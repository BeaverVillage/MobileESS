"""Copy saved Source36 evidence into new documentation; execute no science or ops."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\MobileESS_v42_autonomous")
DOC = REPO / "docs/v42_autonomous_may_20261010"
TOP = DOC / "SOURCE36"
DEST = TOP / "DEPLOYMENT"
ROOT = Path(r"D:\v42_may_restart_20261010_02")
OPS = ROOT / "autonomous"
AUDIT = Path(r"D:\v42_source36_deployment_independent_audit_20261010_01")
INDEP = Path(r"D:\v42_source36_independent_review_20261010_01")


def record(path):
    data = Path(path).read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def verify_inventory(folder):
    path = folder / "SHA_INVENTORY.json"
    inv = read(path)
    for relative, expected in inv["files"].items():
        actual = record(folder / relative)
        assert actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"], relative
    return record(path)


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def json_new(path, obj):
    write_new(path, (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


preserved_folders = [DOC / "SOURCE35", TOP / "RMP_PRIMAL_REVIEW", TOP / "ACTUAL_SOURCE35_RMP_DIAGNOSIS"]
preserved_before = {str(p): verify_inventory(p) for p in preserved_folders}
assert not DEST.exists() and not (TOP / "README.md").exists() and not (TOP / "SHA_INVENTORY.json").exists()

audit = read(AUDIT / "SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_03.json")
assert audit["PASS"] is True and audit["source_start_end_identical"] is True
assert audit["scientific_HEAD"] == "68b8903c1184a958c16dd7976044716bdff091c6"
assert audit["execution_SHA"] == "4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39"
assert audit["execution_source_count"] == 99 and audit["original_source_count"] == 1007
assert audit["frozen_unique_source_asset_count"] == 1111
assert len(audit["new_queue_rows"]) == 9 and len(audit["superseded_unstarted_Source35_rows"]) == 6
assert record(AUDIT / "SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_03.json")["sha256"] == "c54c2ff1ac458be01e1972e298b9da836fda4b8c79dfc6700c7408e48c41a3c4"

original_helpers = {
    "build_v36_validation_template.py": "3c7499660720a9cb1304ba5f446896565bb8d0d66b16170096db93c0bc9fdd82",
    "freeze_sparse_v36.py": "dcb9eb24777d82a8fa46ef31bc474c3d6db0a5f79983fbb35dfe78fa2c4104ba",
    "smoke_sparse_v36.py": "a563fbbbf91c385b021b94f4711560f343a0b6bf93d3714deb5d37ff74f07269",
    "prepare_verified_v36_zero_start_retries.py": "028534cb8dd97f9f555975b955939b5bc4bb758cc99f4de3447989300b87ef76",
}
for name, sha in original_helpers.items():
    assert record(OPS / name)["sha256"] == sha
prepared = read(OPS / "V36_ZERO_START_RETRY_PREPARATION.json")
prepared02 = read(OPS / "V36_ZERO_START_RETRY_PREPARATION_02.json")
validation02 = read(OPS / "V36_VERIFIED_REPAIR_VALIDATION_02.json")
deployment = read(OPS / "V36_ZERO_START_RETRY_DEPLOYMENT.json")
assert prepared["PASS"] and prepared02["PASS"] and deployment["PASS"]
assert prepared02["original27_request_proofs_and_manifest_bytes_unchanged"] is True
assert prepared02["admissions_rerun_by_metadata_finalizer"] is False
assert prepared02["new_Native_calls_or_models_by_metadata_finalizer"] == 0
assert "RMP_Method" not in validation02
assert tuple(validation02[k] for k in ("original_RMP_budget_entry_Method", "eligible_current_complete_start_RMP_Native_Method", "cold_ineligible_or_nonfeasible_RMP_fallback_Method")) == (1, 0, 1)
assert prepared["requests_by_day_and_slot"] == prepared02["requests_by_day_and_slot"] == audit["all27_saved_request_records"]
assert record(OPS / "V36_ZERO_START_RETRY_PREPARATION.json")["sha256"] == "35e43065bcfe3fc5012bac3109c555a4f571a11583b0aa2972613c9d0b989814"
assert record(OPS / "V36_ZERO_START_RETRY_DEPLOYMENT.json")["sha256"] == "6a6320699efe7452243e1625b8b41b29c1a7adc445a92f2567607a2233f84536"
hourly_path = OPS / "CODEX_HOURLY_AUTOMATION_VERIFICATION_20261010T003628.json"
hourly = read(hourly_path)
assert record(hourly_path)["sha256"] == "2bbc3b36b74aff16b01e9748bc8627feb22e249d223d5a7632ff3933c7a7e851"
assert hourly["PASS"] and hourly["toml"]["status"] == hourly["database"]["status"] == "ACTIVE"
assert hourly["actual_scheduled_run_observed"] is False and hourly["recent_run_records"] == []
assert "prompt" not in hourly and "prompt" not in hourly["toml"]

copies = []


def copy_saved(source, relative, scope):
    source = Path(source)
    data = source.read_bytes()
    before = record(source)
    assert hashlib.sha256(data).hexdigest() == before["sha256"] and len(data) == before["bytes"]
    target = DEST / relative
    write_new(target, data)
    copied = record(target)
    assert copied["sha256"] == before["sha256"] and copied["bytes"] == before["bytes"]
    copies.append({"source": before, "copy": copied, "relative": relative, "scope": scope})


for path in sorted(AUDIT.iterdir()):
    if path.is_file():
        copy_saved(path, "independent_actual_deployment/" + path.name,
                   "Saved read-only audit, raw producer evidence and timestamped queue/lease/current-worker Native-prefix snapshots; not a current runtime claim.")
for name in original_helpers:
    copy_saved(OPS / name, "executed_helpers/" + name, "Original executed helper bytes preserved; not rerun by packaging.")
for name in ["finalize_v36_validation_metadata_02.py", "prepare_verified_v36_zero_start_retries_02.py"]:
    copy_saved(OPS / name, "additive_metadata02_helpers/" + name, "Additive metadata-only finalizer and enqueue-only02 helper used by Root.")
copy_saved(OPS / "build_v36_validation_template_02_historical_candidate.py",
           "historical_metadata_candidate/build_v36_validation_template_02_historical_candidate.py",
           "96d9 historical corrected candidate was not executed; original3c7499 executed builder bytes remain intact.")
copy_saved(INDEP / "SOURCE36_OPS_HELPERS_ADDITIVE_METADATA_STATIC_READONLY_REVIEW.json",
           "metadata02_static_review/SOURCE36_OPS_HELPERS_ADDITIVE_METADATA_STATIC_READONLY_REVIEW.json",
           "Independent static original/additive helper and conditional-method metadata review.")
for name in ["V36_VALIDATION_BINDING_TEMPLATE.json", "V36_VERIFIED_REPAIR_VALIDATION.json", "V36_ZERO_START_RETRY_PREPARATION.json"]:
    copy_saved(OPS / name, "historical_original_metadata/" + name, "Original generated metadata/proofs retained byte-for-byte, including the inherited ambiguous RMP_Method1 scalar.")
for name in ["V36_VERIFIED_REPAIR_VALIDATION_02.json", "V36_ZERO_START_RETRY_PREPARATION_02.json", "V36_SPARSE_IMMUTABLE_FREEZE.json", "V36_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json", "V36_ZERO_START_RETRY_DEPLOYMENT.json"]:
    copy_saved(OPS / name, "actual_ops/" + name, "Saved actual Source36 metadata/freeze/import smoke/preparation/deployment proof; final scientific PASS not claimed.")
copy_saved(ROOT / "B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json", "actual_ops/B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json", "Exact actual Source36 source/input/attempt/reset authority manifest.")
copy_saved(ROOT / "USER_ZERO_START_RETRY_AUTHORIZATION.json", "actual_ops/USER_ZERO_START_RETRY_AUTHORIZATION.json", "Existing explicit zero-start authorization; history preserved, previous attempt budgets/checkpoints not carried.")
copy_saved(hourly_path, "hourly_configuration/" + hourly_path.name, "ACTIVE saved configuration verification only; no scheduled run observed. Prompt hash only, no full prompt copied.")
request_count = 0
for day, slots in sorted(prepared["requests_by_day_and_slot"].items()):
    for slot, expected in sorted(slots.items()):
        path = Path(expected["path"])
        assert record(path) == expected
        request = read(path)
        assert request["previous_attempts"] == [] and request["restart_from_zero"] is True
        copy_saved(path, f"admitted_requests/{day}/slot{slot}/request.json", "Saved sealed fresh request; Native0 admission is not solver execution or final scientific PASS.")
        request_count += 1
assert request_count == 27
copy_saved(Path(__file__), "preserve_source36_deployment_docs.py", "Documentation-only packaging script; imports no science and performs no ops/helper/admission execution.")

json_new(DEST / "PROVENANCE_SHA_INDEX.json", {
    "schema": "V42_SOURCE36_DEPLOYMENT_SAVED_BYTE_COPY_PROVENANCE_V1", "PASS": True,
    "UTC": datetime.now(timezone.utc).isoformat(), "copies": copies,
    "all_saved_copies_source_and_target_SHA_bytes_equal": True,
    "saved_snapshots_are_not_current_runtime_claims": True,
    "Native_or_model_or_admission_or_ops_execution_by_packager": 0,
    "production_source_runtime_queue_lease_process_Git_mutations_by_packager": 0,
    "full_automation_prompt_copied": False,
})

deployment_readme = """# Source36 saved actual deployment evidence

Root completed nine verified READY enqueue operations at 2026-10-10T00:35:01.334918+00:00 after the actual 27 fresh Native/model-denied request admissions and sparse freeze/import smoke. These saved requests have Native initial0, a full5400 budget, previous_attempts[] and the existing explicit zero-start authorization. First-three priority is1000; the other six priority is100. Exactly six unstarted Source35 READY entries were superseded. The three active Source35 workers, supervisor, request bytes and completed ordered Native ledger prefixes were preserved. The repair lease de36f19fd14e4710af54525dfb15b48c was released at00:35:41.149133+00:00. READY enqueue and admission do not establish an actual Source36 solver start, speedup, GlobalLB improvement or final date PASS.

The independent read-only audit03 passed at00:39:24.304426+00:00, binding scientific commit68b8903c1184a958c16dd7976044716bdff091c6, all1111 immutable source/asset files, original1007, execution99 SHA4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39, all27 request records, nine queues, six safe supersessions, live worker/supervisor identities and prefix continuity. Its PASS is evidence/deployment integrity qualification. It did not construct models, optimize, execute helpers/admissions or mutate any production state. The queue, lease, supervisor and Native files here are its timestamped saved snapshots; Native Runtime can continue to evolve after them.

The first generated validation retained an inherited scalar RMP_Method1. Original template, validation, preparation and all four executed helper bytes stay intact. The briefly corrected96d9 builder candidate is preserved as unexecuted history; the original executed builder is exact3c749966. Additive finalize02 produced new validation02 and preparation02 after Root confirmed original preparation exit0. The correction removes the ambiguous scalar and explicitly records original budget admissionMethod1, eligible exact complete current P/D NativeMethod0 and cold/ineligible/nonfeasible fallbackMethod1. All27 request/factory/CLI proof bytes and the source manifest remain unchanged; admissions were not rerun and no new models or Native calls were made. Enqueue-only02 consumed the corrected records. Carried older computational/pending descriptions retain their historical qualification scope; the explicit current Source36 conditional policy governs this deployment.

Two preliminary independent audit failures are preserved with their runners and tracebacks. Attempt01 used the wrong external independent receipt folder, Source35 instead of Source36, and failed FileNotFound before its review. Attempt02 assumed active queue status onlyWORKER_ENTERED, while the preserved healthy workers had validNATIVE_PROGRESS_VERIFIED status. Audit03 accepts and verifies that existing status with exact identities and ordered prefixes. These are read-only audit harness defects, not production/scientific failures. Their falsePASS fields are retained unchanged and are not erased by audit03PASS.

The saved hourly verification is ACTIVE in the TOML/database and explicitly reports no actual scheduled run, with empty recent run records. Only its1187-byte verification JSON and promptSHA are copied; the full automation prompt is absent. Manual configuration verification is not a scheduled inspection. Current first-three final GlobalGap<=.03 plus original FULL/Actual/Fresh PASS remains pending.

PROVENANCE_SHA_INDEX maps every raw copy to its original path/SHA/size. SHA_INVENTORY covers this package except itself. The packager imports no scientific modules, performs no Native/model/helper/admission/queue/process/Git actions, and leaves the existing Source35 and Source36 review/diagnosis seals unchanged.
"""
write_new(DEST / "README.md", deployment_readme.encode("utf-8"))
for entry in copies:
    assert record(entry["source"]["path"]) == entry["source"]
preserved_after = {str(p): verify_inventory(p) for p in preserved_folders}
assert preserved_before == preserved_after
json_new(DEST / "FINAL_PACKAGING_OBSERVATION.json", {
    "schema": "V42_SOURCE36_DEPLOYMENT_DOCUMENTATION_ONLY_FINAL_OBSERVATION_V1",
    "PASS": True, "UTC": datetime.now(timezone.utc).isoformat(),
    "independent_actual_deployment_audit": record(AUDIT / "SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_03.json"),
    "saved_raw_copies": len(copies), "saved_fresh_request_copies": request_count,
    "saved_raw_source_records_unchanged_start_end": True,
    "existing_doc_subpackage_inventory_records_before": preserved_before,
    "existing_doc_subpackage_inventory_records_after": preserved_after,
    "existing_doc_subpackages_verified_and_byte_unchanged": True,
    "hourly_configuration": record(hourly_path), "hourly_ACTIVE": True,
    "actual_scheduled_run_observed": False, "full_automation_prompt_copied": False,
    "Native_optimize_calls": 0, "real_Native_model_constructions": 0,
    "science_modules_imported": False, "ops_or_admissions_executed": False,
    "production_source_runtime_queue_lease_process_Git_changes": 0,
    "actual_Source36_Native_performance_or_Global_Gap_Actual_Fresh_final_PASS_claimed": False,
})
files = {p.relative_to(DEST).as_posix(): record(p) for p in sorted(DEST.rglob("*")) if p.is_file()}
json_new(DEST / "SHA_INVENTORY.json", {
    "schema": "V42_SOURCE36_DEPLOYMENT_DOCUMENTATION_SHA_INVENTORY_V1", "PASS": True,
    "UTC": datetime.now(timezone.utc).isoformat(), "files": files,
})
assert verify_inventory(DEST)["sha256"] == record(DEST / "SHA_INVENTORY.json")["sha256"]

top_readme = """# Source36 current-start RMP computational candidate and saved deployment

Scientific commit68b8903c1184a958c16dd7976044716bdff091c6 binds original1007 sources and execution99 SHA4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39. The sparse immutable checkout contains1111 source/asset paths. Only rmp_presolve.py execution bytes change from Source35; F1 computational pricing, fullLP/strictPDHG, worker and other98 execution modules remain byte-identical.

Original RMP budget admission remainsMethod1. At its sole unchanged30-second Native call, sealed complete same-current P/D with both original and Native-scaled row/bound violations within literal original1e-9 permits Method0. Cold, ineligible and finite nonfeasible starts retainMethod1. Presolve0, installedwarm2, original precision, Threads1, objective/physics/domain/matrix/row/Pi transport and independent full checker remain unchanged. Total5400 is preserved. This is a computational candidate; neither a Native objective nor a start proves a GlobalLB or finalGap.

- RMP_PRIMAL_REVIEW retains owner369 and independent369 Native/model-denied selected tests, raw available XML/logs, focused122+1 expectation-harness failure, final136 focused cases, source bytes, static reviews and unexecuted metadata candidate. Unchanged cache120 is historical carried evidence, not a new run.
- ACTUAL_SOURCE35_RMP_DIAGNOSIS retains actual saved first-two RMP observations per day for the three Source35 workers: Method1/warm2/Presolve0, unchanged30 caps, status11/Sol0 and no usable Pi. It is historical Native-prefix/source evidence, not a fresh Case/checker replay or Source36 performance proof.
- DEPLOYMENT retains actual27 sealed fresh request admissions, nine READY enqueue at00:35:01.334918UTC, six unstarted Source35 supersessions, three active worker/supervisor/request/Native-prefix preservation, released lease and independent audit03PASS. Original ambiguous RMP_Method metadata and helpers are preserved; additive validation/preparation02 explicitly clarify original admission1, eligibleNative0 and fallback1 without rerunning admissions or changing the manifest. Both preliminary read-only audit harness failures remain intact.

The saved hourly configuration verification is ACTIVE with no actual scheduled run observed; the full prompt is not copied. All actual Source36 Native performance, GlobalLB improvement, finalGlobalGap<=.03 and original FULL/Actual/Fresh scientific PASS remain pending at these saved evidence times. Test/admission/deployment/documentation PASS fields have only their stated integrity scope. No scientific/runtime/queue/lease/process/Git changes are made by documentation packaging.

Each subpackage retains raw-byte provenance and its own SHA inventory. Existing review/diagnosis and Source35 seals remain unchanged. The top SHA_INVENTORY.json covers every Source36 documentation file except itself.
"""
write_new(TOP / "README.md", top_readme.encode("utf-8"))
top_files = {p.relative_to(TOP).as_posix(): record(p) for p in sorted(TOP.rglob("*")) if p.is_file()}
json_new(TOP / "SHA_INVENTORY.json", {
    "schema": "V42_SOURCE36_ALL_DOCUMENTATION_SHA_INVENTORY_V1", "PASS": True,
    "UTC": datetime.now(timezone.utc).isoformat(), "files": top_files,
})
verify_inventory(TOP)
assert preserved_before == {str(p): verify_inventory(p) for p in preserved_folders}
print(json.dumps({"PASS": True, "raw_copies": len(copies), "deployment_files": len(files) + 1,
                  "top_files": len(top_files) + 1, "deployment_inventory": record(DEST / "SHA_INVENTORY.json"),
                  "top_inventory": record(TOP / "SHA_INVENTORY.json")}, ensure_ascii=False))
