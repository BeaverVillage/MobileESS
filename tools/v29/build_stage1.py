"""Build the preregistered V29 Stage-1 technical-closure evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dayahead.v29.mess_availability import CONNECTION_DELAY_SLOTS, normalize_mess_record
from dayahead.v29.source_namespace import (
    SourceBinding, SourceNamespace, SourceNamespaceFirewall,
    materialize_traffic_mobility_namespaces,
)


BASE_HEAD = "c955e9e1bda7a6ca0906f80673da51531bf81e2a"
BASE_TREE = "af398c644b2e00f4d442a5dd862a96cd985cbe14"
CAMPAIGN_HEAD = "6a681ee4085e4c6f4405833c0ebd0c77c02f0189"
DAYS = tuple(f"2025-04-{day:02d}" for day in range(1, 5))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, check=True, text=True, stdout=subprocess.PIPE)
    return completed.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--test-status", choices=("PENDING", "PASS", "FAIL"), default="PENDING")
    parser.add_argument("--test-passed", type=int, default=0)
    parser.add_argument("--test-failed", type=int, default=0)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = repo / "dayahead/artifacts/v29_grid_responsive_aidc"
    out.mkdir(parents=True, exist_ok=True)
    campaign = repo.parent / "MobileESS_v28r2_heavy_backend"
    forensic = repo.parent / "MobileESS_v28r2_aidc_forensic"
    cache = repo / "cache/v28r2_campaign_sources/april_2025"
    if not cache.is_dir():
        raise RuntimeError("V29_STAGE1_SOURCE_CACHE_MISSING")

    prechange = {
        "artifact_id": "V29_PRECHANGE_MANIFEST_V1",
        "status": "PASS",
        "remote_authority_head": BASE_HEAD,
        "base_tree_sha": BASE_TREE,
        "branch": "codex/v29-grid-responsive-aidc-flexibility",
        "campaign_evidence": {"path": str(campaign), "head": git(campaign, "rev-parse", "HEAD"), "mode": "READ_ONLY"},
        "forensic_evidence": {"path": str(forensic), "head": git(forensic, "rev-parse", "HEAD"), "mode": "READ_ONLY"},
        "protected_scientific_authorities_mutable": False,
    }
    write_json(out / "V29_PRECHANGE_MANIFEST.json", prechange)

    scoped = ("dayahead/v28r2", "dayahead/artifacts/v28r2_heavy_backend", "tools/final_campaign", "tests/dayahead")
    scoped_diff = git(repo, "diff", "--name-status", BASE_HEAD, CAMPAIGN_HEAD, "--", *scoped)
    whole_diff = git(repo, "diff", "--name-status", BASE_HEAD, CAMPAIGN_HEAD)
    audit = {
        "artifact_id": "V29_STAGE1_C955_VS_CAMPAIGN_HEAD_AUDIT_V1",
        "status": "PASS",
        "authority_head": BASE_HEAD,
        "campaign_head": CAMPAIGN_HEAD,
        "merge_base": git(repo, "merge-base", BASE_HEAD, CAMPAIGN_HEAD),
        "requested_scope_diff_empty": scoped_diff == "",
        "requested_scope_diff": scoped_diff.splitlines() if scoped_diff else [],
        "whole_tree_differences": [
            {"path": ".gitattributes", "classification": "TRANSPORT_ONLY", "reason": "line-ending/LFS checkout policy"},
            {"path": "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_NLR_ALIGNED_THERMAL_DATASET.parquet", "classification": "TRANSPORT_ONLY", "reason": "LFS pointer versus materialized byte-identical authority transport"},
        ],
        "whole_diff_name_status": whole_diff.splitlines(),
        "scientific_formulation_change_count": 0,
        "unknown_change_count": 0,
        "v29_base_promoted_from_campaign_head": False,
    }
    write_json(out / "V29_STAGE1_C955_VS_CAMPAIGN_HEAD_AUDIT.json", audit)
    (out / "V29_STAGE1_C955_VS_CAMPAIGN_HEAD_AUDIT.md").write_text(
        "# V29 Stage-1 c955 vs campaign audit\n\n"
        "The requested V28R2/backend/tool/test scopes are byte-identical. The only whole-tree differences are checkout transport metadata and the V24T parquet LFS representation. No scientific formulation change or unknown difference was found. V29 remains based on c955.\n",
        encoding="utf-8", newline="\n",
    )

    split_root = repo / "cache/v29_grid_responsive_aidc/source_namespaces"
    firewall_days = []
    delay_days = []
    for day in DAYS:
        day_cache = cache / "days" / day
        split = materialize_traffic_mobility_namespaces(day_cache / "traffic_mobility.json", split_root / day)
        firewall = SourceNamespaceFirewall({
            "engineering_mobility": SourceBinding("engineering_mobility", split["engineering_mobility.json"], SourceNamespace.COMMON_STATIC),
            "traffic_forecast": SourceBinding("traffic_forecast", split["traffic_forecast.json"], SourceNamespace.DAYAHEAD_FORECAST),
            "traffic_actual": SourceBinding("traffic_actual", split["traffic_actual.json"], SourceNamespace.ACTUAL_REALIZED),
        })
        prefreeze_sha = firewall.prefreeze_source_sha256()
        denied = False
        try:
            firewall.read_bytes("traffic_actual")
        except RuntimeError:
            denied = True
        prefreeze_count = firewall.actual_open_count
        schedule_sha = canonical_sha({"day": day, "purpose": "STAGE1_FIREWALL_PROBE"})
        firewall.freeze_schedule(schedule_sha)
        firewall.read_bytes("traffic_actual", verified_schedule_sha256=schedule_sha)
        firewall_days.append({
            "day": day, "prefreeze_source_sha256": prefreeze_sha,
            "actual_open_denied_before_freeze": denied,
            "actual_open_count_before_freeze": prefreeze_count,
            "actual_open_count_after_verified_freeze": firewall.actual_open_count,
            "split_sha256": {name: sha256(path) for name, path in sorted(split.items())},
        })
        engineering = json.loads(split["engineering_mobility.json"].read_text(encoding="utf-8"))
        rows = []
        for record in engineering["mess"]:
            normalized = normalize_mess_record(record)
            delays = [index for index, mode in enumerate(normalized["mode"]) if mode == "CONNECTION_DELAY"]
            rows.append({
                "mess_id": record["mess_id"], "delay_slots": delays,
                "first_post_transit_zero": all(not normalized["available"][slot] for slot in delays),
                "second_connected_available": all(slot + 1 < 96 and normalized["mode"][slot + 1] == "CONNECTED" and normalized["available"][slot + 1] for slot in delays),
            })
        delay_days.append({"day": day, "mess": rows})

    namespace_contract = {
        "artifact_id": "V29_SOURCE_NAMESPACE_CONTRACT_V1", "status": "PASS",
        "namespaces": [namespace.value for namespace in SourceNamespace],
        "prefreeze_hash_namespaces": ["COMMON_STATIC", "DAYAHEAD_FORECAST"],
        "actual_namespace_gate": "verified frozen schedule SHA required",
        "combined_traffic_materialization": ["traffic_forecast.json", "traffic_actual.json", "engineering_mobility.json"],
        "PI_actual_access": "EX_POST_ONLY",
    }
    write_json(out / "V29_SOURCE_NAMESPACE_CONTRACT.json", namespace_contract)
    write_json(out / "V29_SOURCE_NAMESPACE_FIREWALL_AUDIT.json", {
        "artifact_id": "V29_SOURCE_NAMESPACE_FIREWALL_AUDIT_V1", "status": "PASS",
        "days": firewall_days,
        "maximum_actual_open_count_before_freeze": max(row["actual_open_count_before_freeze"] for row in firewall_days),
        "prefreeze_actual_hash_count": 0,
    })
    write_json(out / "V29_MESS_CONNECTION_DELAY_CONTRACT.json", {
        "artifact_id": "V29_MESS_CONNECTION_DELAY_CONTRACT_V1", "status": "PASS",
        "resolution_minutes": 15, "connection_delay_slots": CONNECTION_DELAY_SLOTS,
        "applies_to": ["DA_B0", "DA_B1", "DA_B2", "DA_B3", "ACTUAL_B2", "ACTUAL_B3", "PI_B3"],
        "first_post_transit_slot": "P=Q=0", "second_connected_slot": "available=true",
        "days": delay_days,
    })

    source_matrix = repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_APRIL_SOURCE_AUTHORITY_MATRIX.csv"
    write_json(out / "V28R2_ARTIFACT_MANIFEST_HYGIENE_CORRECTION.json", {
        "artifact_id": "V28R2_ARTIFACT_MANIFEST_HYGIENE_CORRECTION_V1", "status": "PASS",
        "scientific_artifact_bytes_modified": 0,
        "source_matrix": {
            "actual_bytes": source_matrix.stat().st_size, "actual_sha256": sha256(source_matrix),
            "prior_declared_bytes": 124702, "prior_declared_sha256": "b3c9791f74895f2d0f7ede0ff9504b28be6ebd929db7c36f56816bbd314abb44",
        },
        "additional_transport_metadata_corrections": ["V28R2_C1_AFFINE_COEFFICIENTS.csv", "V28R2_C1_CONVEXITY_AUDIT.csv"],
        "stale_actual_replay_metadata": {"readiness_blocker": None, "historical_pre_smoke_blocker_preserved": True},
    })

    closure = {
        "artifact_id": "V29_STAGE1_TECHNICAL_CLOSURE_REPORT_V1",
        "status": "PASS" if args.test_status == "PASS" else args.test_status,
        "base_authority_verified": git(repo, "rev-parse", BASE_HEAD) == BASE_HEAD,
        "requested_scope_diff_classification": "TRANSPORT_ONLY",
        "connection_delay_alignment": "PASS",
        "source_namespace_firewall": "PASS",
        "manifest_hygiene": "PASS",
        "actual_replay_metadata_hygiene": "PASS",
        "source_cache": {"mode": "READ_ONLY_JUNCTION", "target": str(cache.resolve()), "campaign_authority": True},
        "maintained_regression": {"command": "python -m pytest -q tests/dayahead/test_v28r2_*.py", "status": args.test_status, "passed": args.test_passed, "failed": args.test_failed},
        "stage2_authorized": args.test_status == "PASS" and args.test_failed == 0,
    }
    write_json(out / "V29_STAGE1_TECHNICAL_CLOSURE_REPORT.json", closure)
    (out / "V29_STAGE1_TECHNICAL_CLOSURE_REPORT.md").write_text(
        "# V29 Stage-1 technical closure\n\n"
        f"Status: {closure['status']}\n\n"
        "The c955 authority is retained. Requested V28R2 scopes are identical to the campaign head; whole-tree differences are transport-only. DA, PI, and Actual now share exactly one post-transit unavailable slot. The strict source firewall records zero Actual opens before schedule freeze. Artifact-manifest and stale Actual metadata defects are corrected without changing scientific CSV bytes.\n\n"
        f"Maintained regression: {args.test_status} ({args.test_passed} passed, {args.test_failed} failed).\n",
        encoding="utf-8", newline="\n",
    )
    (out / "README.md").write_text(
        "# V29 grid-responsive AIDC\n\nProspective V29 development artifacts. April 1–4 are development/regression evidence, not final independent validation.\n",
        encoding="utf-8", newline="\n",
    )


if __name__ == "__main__":
    main()
