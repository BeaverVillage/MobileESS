"""Seal and read-only verify this blocked research review package.

This checks saved evidence and original source bytes; it starts no AC solver,
Native model, scheduler or campaign. The manifest and verification receipt
are excluded from their own roster to avoid circular hashes.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ieee8500_v42.integration import digest, verify_source_identity

REPORT = ROOT / "docs/ieee8500_v42_single_case"
MANIFEST = REPORT / "ARTIFACT_SHA256_MANIFEST.json"
RECEIPT = REPORT / "ARTIFACT_PACKAGE_VERIFICATION.json"
EXCLUDED = {p.relative_to(ROOT).as_posix() for p in (MANIFEST, RECEIPT)}
PATHS = ("ieee8500_v42", "docs/ieee8500_v42_single_case",
         "tools/ieee8500_v42", "tests/test_ieee8500_v42_*.py", "tests/.gitattributes")
CONFIG_SHA = "8f1ad20d080ecf04609be7a66fe912983dcb6ce8bf5b6afdd740b4bccc6aa1f6"
MAPPING_SHA = "4a70fd13bf08c8512d30f74e48dfafb46fdddd4e112a3aee92a8191f22cad016"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def inventory():
    raw = git("ls-files", "--cached", "--others", "--exclude-standard", "-z",
              "--", *PATHS)
    names = sorted(set(raw.decode("utf-8").strip("\0").split("\0")) - EXCLUDED)
    assert names and all(name for name in names), "EMPTY_OR_INVALID_ROSTER"
    return names


def csv_rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream)


def document_links(allow_pending_outputs=False):
    count = 0
    for name in ("FINAL_REVIEW_KO.md", "README.md", "REPRODUCE_KO.md", "SOURCE_AUTHORITY.md"):
        path = REPORT / name
        for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            linked = (path.parent / target.split("#", 1)[0]).resolve()
            pending = allow_pending_outputs and linked in (MANIFEST, RECEIPT)
            assert linked.is_file() or pending, (name, target)
            count += 1
    return count


def scientific_checks(allow_pending_outputs=False):
    configuration = read(REPORT / "STUDY_CONFIGURATION_DRAFT.json")
    pin = read(REPORT / "STUDY_CONFIGURATION_SHA256.json")
    mapping = REPORT / "joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv"
    assert digest(configuration) == pin["canonical_configuration_sha256"] == CONFIG_SHA
    assert sha(mapping) == pin["mapping_sha256"] == MAPPING_SHA
    assert sha(REPORT / "STUDY_CONFIGURATION_DRAFT.json") == pin["file_sha256"]
    source = verify_source_identity(ROOT, read(REPORT / "V42_SOURCE_SHA_MANIFEST.json"))
    assert source["source_files_verified"] == 962
    final = read(REPORT / "FINAL_SINGLE_SCENARIO.json")
    assert final["selected_operational_scenario"] is None
    assert final["selected_and_frozen_production_configuration"] is None
    assert not final["production_ready"] and final["B1_B2_B3_Native_calls"] == 0
    tests = read(REPORT / "FINAL_LIGHTWEIGHT_TEST_RECEIPT.json")
    assert tests["PASS"] and tests["test_count"] == 76
    assert tests["failures"] == tests["errors"] == tests["skipped"] == 0
    scales = list(csv_rows(REPORT / "SCALE_SCREENING.csv"))
    assert len(scales) == 12 and all(r["AC_constraints_pass"] == "False" for r in scales)
    for name, selected in (
        ("SCALE_SCREENING.csv", "joint_selection_v3/selected_ac/SCALE_SCREENING.csv"),
        ("RELATIVE_POSITION_AUDIT.csv", "joint_selection_v3/score_selection/RELATIVE_POSITION_AUDIT.csv"),
    ):
        assert sha(REPORT / name) == sha(REPORT / selected), name
    directions = list(csv_rows(REPORT / "RELATIVE_POSITION_AUDIT.csv"))
    assert len(directions) == 276
    assert all(r["x_pass"] == r["y_pass"] == r["pair_pass"] == "True" for r in directions)
    assert all(r["physical_geographic_direction_certified"] == "False" for r in directions)
    assert len(list(csv_rows(mapping))) == 24
    assert len(list(csv_rows(REPORT / "FINAL_STA_MAPPING.csv"))) == 12
    assert len(list(csv_rows(REPORT / "AIDC_CAPACITY_AUDIT.csv"))) == 12
    assert sum(1 for _ in csv_rows(REPORT / "REGCONTROL_TAP_VALIDATION.csv")) == 13824

    # The main whole-feeder CSV must exactly reproduce the saved actual AC
    # parent-terminal phase maximum, including each original NormalAmps.
    import numpy as np
    archive = REPORT / "joint_selection_v3/selected_ac/bg0p552_gpu1p0"
    axes = read(archive / "AC_AXES.json")
    groups = {}
    for index, row in enumerate(axes["lines"]):
        if axes["objective_mask"][index]:
            groups.setdefault(row["element"], []).append(index)
    with np.load(archive / "AC_96.npz", allow_pickle=False) as packed:
        amps, ratios = packed["line_amps"], packed["line_rho"]
    rows = iter(csv_rows(REPORT / "LINE_LOADING_REPORT.csv"))
    count = 0
    for slot in range(96):
        for line, indices in groups.items():
            index = max(indices, key=lambda i: ratios[slot, i])
            expected = axes["lines"][index]
            row = next(rows)
            assert row["line"] == line and int(row["slot"]) == slot
            assert int(row["parent_terminal"]) == expected["terminal"]
            assert int(row["binding_local_node"]) == expected["node"]
            assert float(row["NormalAmps"]) == expected["normal_amps"]
            assert float(row["I_A"]) == float(amps[slot, index])
            assert float(row["rho"]) == float(ratios[slot, index])
            count += 1
    assert next(rows, None) is None and count == 355008
    preservation = read(REPORT / "CAMPAIGN_PRESERVATION_CHECK.json")
    assert preservation["PASS"] and preservation["own_external_mutations"] == 0
    assert not preservation["scheduler_snapshot_identical"]
    assert len(preservation["scheduler_registration_diff"]["added"]) == 3

    link_count = document_links(allow_pending_outputs)
    return dict(original_source=source, same_frozen_configuration_sha256=CONFIG_SHA,
                same_mapping_sha256=MAPPING_SHA, contract_tests_PASS=76,
                modeled_direction_pairs_PASS=276, actual_geography="UNVERIFIED",
                scale_cases_global_AC_FAIL=12, main_original_line_day_rows=count,
                primary_document_local_links_checked=link_count,
                original_campaign_authorities_preserved=True,
                independent_external_new_scheduler_registrations_observed=3,
                operational_scenario_selected=False, production_ready=False,
                Native_calls=0, evidence_kind="SAVED_ARTIFACT_AND_BYTE_IDENTITY_VERIFICATION")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", action="store_true", help="Create the initial manifest; refuses replacement.")
    args = parser.parse_args()
    names = inventory()
    changed = git("diff", "HEAD", "--name-only", "-z").decode("utf-8").strip("\0")
    assert not changed or set(changed.split("\0")) <= set(names) | EXCLUDED, "OUTSIDE_NAMESPACE_CHANGE"
    checks = scientific_checks(allow_pending_outputs=args.seal)
    if args.seal:
        assert not MANIFEST.exists(), "MANIFEST_EXISTS_DO_NOT_RESEAL_EXISTING_EVIDENCE"
        entries = {name: {"sha256": sha(ROOT / name), "bytes": (ROOT / name).stat().st_size}
                   for name in names}
        assert all(item["bytes"] < 100_000_000 for item in entries.values()), "OVERSIZED_GIT_ARTIFACT"
        write(MANIFEST, dict(schema="IEEE8500_BLOCKED_RESEARCH_ARTIFACT_SEAL_V1",
            scope="OWN_NEW_NAMESPACES_ONLY_NOT_PRODUCTION_QUALIFICATION",
            excluded_self_referential_files=sorted(EXCLUDED), files=entries,
            canonical_configuration_sha256=CONFIG_SHA, mapping_sha256=MAPPING_SHA))
    manifest = read(MANIFEST)
    assert sorted(manifest["files"]) == names, "ROSTER_DRIFT"
    for name, expected in manifest["files"].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT) and path.is_file(), "INVALID_ARTIFACT_PATH"
        assert path.stat().st_size == expected["bytes"] and sha(path) == expected["sha256"], name
    result = dict(PASS=True, sealed_files_verified=len(names), manifest_sha256=sha(MANIFEST),
                  largest_artifact_bytes=max(r["bytes"] for r in manifest["files"].values()),
                  **checks)
    write(RECEIPT, result)
    assert document_links() == checks["primary_document_local_links_checked"]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
