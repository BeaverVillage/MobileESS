"""Deterministic V39D synthetic logical-Rack compatibility refreeze.

The Rack rows are non-additive compatibility envelopes.  V39C site capacity
remains the sole aggregate GPU-capacity authority; the retained 48 logical
Rack identities answer only whether one indivisible gang can be hosted.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from dayahead.v38.authority import (
    CapacityAuthority,
    RackPool,
    canonical_sha256,
    load_capacity_authority,
)
from dayahead.v39c.freeze import atomic_json, sha256_file

from .contracts import (
    CAPACITY_CANONICAL_SHA256,
    CAPACITY_FILE_SHA256,
    EXPECTED_GPU_CAPACITY,
    RACK_AUTHORITY_PATH,
    RACK_FREEZE_CERTIFICATE_PATH,
    V39C_ARTIFACT_ROOT,
    V39C_PREMAY_GANG_AUDIT_PATH,
)


CLASSIFICATION = "POSTHOC_ENGINEERING_RACK_AUTHORITY_REFREEZE"
SEMANTICS = "SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_CAPACITY"
ROOT_CAUSE = "LEGACY_LOGICAL_RACK_AUTHORITY_INCONSISTENT_WITH_V39C_SITE_CAPACITY"
REQUIRED_GANG_PROBES = (1, 2, 4, 8, 16, 32, 60)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def _site_capacity(repo: Path) -> tuple[dict[str, int], dict[str, Any]]:
    path = repo / V39C_ARTIFACT_ROOT / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    if sha256_file(path) != CAPACITY_FILE_SHA256:
        raise RuntimeError("V39D_V39C_CAPACITY_FILE_SHA_DRIFT")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["canonical_SHA256"] != CAPACITY_CANONICAL_SHA256:
        raise RuntimeError("V39D_V39C_CAPACITY_CANONICAL_SHA_DRIFT")
    capacity = {
        str(row["AIDC"]): int(row["synthetic_H100_equivalent_GPU_capacity"])
        for row in payload["site_table"]
    }
    if capacity != EXPECTED_GPU_CAPACITY or sum(capacity.values()) != 624:
        raise RuntimeError("V39D_V39C_CAPACITY_VECTOR_DRIFT")
    return capacity, payload


def _legacy_rows(repo: Path) -> tuple[CapacityAuthority, dict[str, list[RackPool]]]:
    authority = load_capacity_authority(repo)
    by_site: dict[str, list[RackPool]] = {site: [] for site in EXPECTED_GPU_CAPACITY}
    for pool in authority.rack_pools:
        by_site[pool.aidc_id].append(pool)
    if len(authority.rack_pools) != 48 or any(len(rows) != 4 for rows in by_site.values()):
        raise RuntimeError("V39D_LEGACY_RACK_IDENTITY_AXIS")
    return authority, by_site


def _effective(
    site_capacity: Mapping[str, int], pools: list[Mapping[str, Any]], site: str,
) -> int:
    # Compatibility envelopes are non-additive.  The aggregate physical bound
    # is the unchanged V39C site authority, never the sum of Rack envelopes.
    if not any(int(row["compatibility_GPU_limit"]) >= 1 for row in pools):
        return 0
    return min(
        int(site_capacity[site]),
        max(int(row["compatibility_GPU_limit"]) for row in pools),
    )


def construct_authority(repo: Path, rule_source_commit: str) -> dict[str, Any]:
    """Construct the authority without reading any May/runtime result."""

    site_capacity, _capacity_payload = _site_capacity(repo)
    legacy, legacy_by_site = _legacy_rows(repo)
    premay_path = repo / V39C_PREMAY_GANG_AUDIT_PATH
    premay = json.loads(premay_path.read_text(encoding="utf-8"))
    if premay.get("May_result_reads") != 0 or premay.get("status") != "PASS":
        raise RuntimeError("V39D_PREMAY_GANG_AUTHORITY_INVALID")
    observed = tuple(sorted(
        int(value) for value in premay["observed_requested_GPU_sizes"]
        if 0 < int(value) <= max(site_capacity.values())
    ))

    pools: list[dict[str, Any]] = []
    per_site: list[dict[str, Any]] = []
    for site in sorted(site_capacity):
        cap = int(site_capacity[site])
        site_pools = []
        for legacy_pool in sorted(legacy_by_site[site], key=lambda row: row.rack_pool_id):
            row = {
                "aidc_id": site,
                "rack_pool_id": legacy_pool.rack_pool_id,
                "compatibility_GPU_limit": cap,
                "legacy_deliverable_GPU_capacity": legacy_pool.historical_gpu_capacity,
                "aggregate_capacity_contribution_GPU": 0,
                "semantics": "NON_ADDITIVE_SINGLE_GANG_COMPATIBILITY_ENVELOPE",
            }
            pools.append(row)
            site_pools.append(row)
        effective = _effective(site_capacity, site_pools, site)
        host_counts = {
            str(gang): sum(
                int(row["compatibility_GPU_limit"]) >= gang for row in site_pools
            )
            for gang in REQUIRED_GANG_PROBES
        }
        supported_observed = [gang for gang in observed if cap >= gang]
        if effective != cap or any(
            not any(int(row["compatibility_GPU_limit"]) >= gang for row in site_pools)
            for gang in supported_observed
        ):
            raise RuntimeError(f"V39D_RACK_COMPATIBILITY_CONSTRUCTION:{site}")
        per_site.append({
            "AIDC": site,
            "frozen_site_GPU_capacity": cap,
            "logical_Rack_pool_count": len(site_pools),
            "effective_Rack_deliverability": effective,
            "difference_from_site_capacity_GPU": effective - cap,
            "host_count_by_required_gang_GPU": host_counts,
            "site_contract_32GPU_positions": cap // 32,
            "effective_32GPU_host_positions": min(cap // 32, host_counts["32"]),
            "site_can_host_60GPU": cap >= 60,
            "logical_Rack_compatibility_supports_60GPU": host_counts["60"] > 0,
            "preMay_observed_gang_sizes_not_exceeding_site_capacity": supported_observed,
        })

    payload: dict[str, Any] = {
        "artifact_id": "V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY_V1",
        "status": "PASS",
        "classification": CLASSIFICATION,
        "semantics": SEMANTICS,
        "root_cause_repaired": ROOT_CAUSE,
        "rack_rule_source_commit": rule_source_commit,
        "measured_physical_Rack_census_claim": False,
        "modeled_AIDC_sites": True,
        "logical_Rack_pool_count": len(pools),
        "legacy_logical_Rack_pool_identity_preserved": True,
        "aggregate_capacity_authority": "FROZEN_V39C_SITE_GPU_CAPACITY_ONLY",
        "logical_Rack_limits_are_additive_capacity": False,
        "gang_splitting_allowed": False,
        "construction_rule": (
            "retain each legacy logical Rack ID; set its non-additive single-gang "
            "compatibility envelope to its unchanged V39C AIDC site capacity"
        ),
        "frozen_V39C_site_capacity": site_capacity,
        "frozen_V39C_site_capacity_total": sum(site_capacity.values()),
        "effective_Rack_deliverability_by_AIDC": {
            row["AIDC"]: row["effective_Rack_deliverability"] for row in per_site
        },
        "effective_Rack_deliverability_total": sum(
            row["effective_Rack_deliverability"] for row in per_site
        ),
        "required_gang_compatibility_probes_GPU": list(REQUIRED_GANG_PROBES),
        "preMay_gang_authority_source": V39C_PREMAY_GANG_AUDIT_PATH.as_posix(),
        "preMay_gang_authority_SHA256": sha256_file(premay_path),
        "preMay_used_for_numeric_Rack_sizing": False,
        "preMay_used_for_postconstruction_compatibility_verification": True,
        "legacy_Rack_authority_source_SHA256": legacy.source_sha256,
        "site_capacity_authority_file_SHA256": CAPACITY_FILE_SHA256,
        "site_capacity_authority_canonical_SHA256": CAPACITY_CANONICAL_SHA256,
        "numeric_Rack_construction_May_result_reads": 0,
        "numeric_Rack_construction_RW_RSP_PASS_FAIL_reads": 0,
        "numeric_Rack_construction_Fresh_grid_reads": 0,
        "numeric_Rack_construction_migration_result_reads": 0,
        "rack_mutation_count": 0,
        "MAY_STARTED": "NO",
        "logical_Rack_pools": pools,
        "per_AIDC_consistency": per_site,
    }
    payload["rack_canonical_SHA256"] = canonical_sha256(payload)
    if payload["effective_Rack_deliverability_total"] != 624:
        raise RuntimeError("V39D_RACK_TOTAL_NOT_624")
    if sum(row["effective_32GPU_host_positions"] for row in per_site) != 19:
        raise RuntimeError("V39D_RACK_32GPU_POSITION_DRIFT")
    return payload


def freeze(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    rule_source_commit = _git(repo, "rev-parse", "HEAD")
    payload = construct_authority(repo, rule_source_commit)
    atomic_json(repo / RACK_AUTHORITY_PATH, payload)
    return {
        "rack_rule_source_commit": rule_source_commit,
        "rack_authority_SHA256": sha256_file(repo / RACK_AUTHORITY_PATH),
        "rack_canonical_SHA256": payload["rack_canonical_SHA256"],
        "path": RACK_AUTHORITY_PATH.as_posix(),
    }


def seal(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    path = repo / RACK_AUTHORITY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = dict(payload)
    recorded = canonical.pop("rack_canonical_SHA256")
    if canonical_sha256(canonical) != recorded:
        raise RuntimeError("V39D_RACK_CANONICAL_SHA_DRIFT")
    relative = RACK_AUTHORITY_PATH.as_posix()
    if _git(repo, "status", "--short", "--", relative):
        raise RuntimeError("V39D_RACK_AUTHORITY_MUST_BE_COMMITTED_BEFORE_SEAL")
    freeze_commit = _git(repo, "log", "-1", "--format=%H", "--", relative)
    certificate: dict[str, Any] = {
        "artifact_id": "V39D_RACK_FREEZE_CERTIFICATE_V1",
        "status": "PASS",
        "classification": CLASSIFICATION,
        "semantics": SEMANTICS,
        "rack_rule_source_commit": payload["rack_rule_source_commit"],
        "rack_freeze_commit": freeze_commit,
        "rack_authority_path": relative,
        "rack_authority_SHA256": sha256_file(path),
        "rack_canonical_SHA256": recorded,
        "capacity_SHA_before": CAPACITY_FILE_SHA256,
        "capacity_SHA_after": sha256_file(
            repo / V39C_ARTIFACT_ROOT / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
        ),
        "rack_mutation_count": 0,
        "numeric_Rack_construction_May_result_reads": 0,
        "MAY_STARTED": "NO",
    }
    certificate["certificate_canonical_SHA256"] = canonical_sha256(certificate)
    atomic_json(repo / RACK_FREEZE_CERTIFICATE_PATH, certificate)
    return certificate


def load_v39d_rack_authority(repo: Path) -> tuple[CapacityAuthority, dict[str, Any]]:
    repo = repo.resolve()
    authority_path = repo / RACK_AUTHORITY_PATH
    certificate_path = repo / RACK_FREEZE_CERTIFICATE_PATH
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    authority_canonical = dict(authority)
    authority_recorded = authority_canonical.pop("rack_canonical_SHA256")
    certificate_canonical = dict(certificate)
    certificate_recorded = certificate_canonical.pop("certificate_canonical_SHA256")
    if canonical_sha256(authority_canonical) != authority_recorded:
        raise RuntimeError("V39D_RACK_CANONICAL_SHA_DRIFT")
    if canonical_sha256(certificate_canonical) != certificate_recorded:
        raise RuntimeError("V39D_RACK_CERTIFICATE_CANONICAL_SHA_DRIFT")
    if sha256_file(authority_path) != certificate["rack_authority_SHA256"]:
        raise RuntimeError("V39D_RACK_AUTHORITY_FILE_SHA_DRIFT")
    if authority_recorded != certificate["rack_canonical_SHA256"]:
        raise RuntimeError("V39D_RACK_AUTHORITY_CERTIFICATE_SHA_MISMATCH")
    if certificate["capacity_SHA_before"] != certificate["capacity_SHA_after"]:
        raise RuntimeError("V39D_SITE_CAPACITY_CHANGED_DURING_RACK_REFREEZE")
    for relative in (RACK_AUTHORITY_PATH.as_posix(), RACK_FREEZE_CERTIFICATE_PATH.as_posix()):
        if _git(repo, "status", "--short", "--", relative):
            raise RuntimeError(f"V39D_UNCOMMITTED_RACK_FREEZE:{relative}")
    actual_freeze_commit = _git(
        repo, "log", "-1", "--format=%H", "--", RACK_AUTHORITY_PATH.as_posix()
    )
    if actual_freeze_commit != certificate["rack_freeze_commit"]:
        raise RuntimeError("V39D_RACK_FREEZE_COMMIT_DRIFT")

    capacity, _payload = _site_capacity(repo)
    pools = tuple(
        RackPool(
            str(row["aidc_id"]),
            str(row["rack_pool_id"]),
            float(row["compatibility_GPU_limit"]),
        )
        for row in authority["logical_Rack_pools"]
    )
    historical = load_capacity_authority(repo)
    adapted = CapacityAuthority(
        site_capacity=capacity,
        historical_site_capacity=historical.historical_site_capacity,
        rack_pools=pools,
        source_sha256=certificate["rack_authority_SHA256"],
    )
    return adapted, {"authority": authority, "certificate": certificate}


__all__ = [
    "CLASSIFICATION",
    "ROOT_CAUSE",
    "SEMANTICS",
    "construct_authority",
    "freeze",
    "load_v39d_rack_authority",
    "seal",
]
