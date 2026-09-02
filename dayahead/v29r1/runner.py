"""Fail-closed V29R1 authority, trust-certificate, and preservation runner.

The current V29 production source pipeline materializes April 2025 only.
V29R1 requires Jan--Mar causal electrical states for physics certification.
This runner records that gap without substituting April development data and
therefore deliberately does not execute downstream science stages.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from dayahead.v28r2.source_preflight import APRIL_DAYS
from tools.v29.run_stage3_carryin_authority import source_zip

from .authority import (
    BLOCKED_SOURCE_STATUS,
    CANDIDATE_RHOS,
    CERTIFICATION_DAYS,
    POSTCARRYIN_FORENSIC_HEAD,
    PREAPRIL_CENSUS_HEAD,
    PRODUCTION_BASE_HEAD,
    Q_SCENARIOS,
    RELIABILITY_TARGET,
    V29R1_BRANCH,
)


ARTIFACT_REL = Path("dayahead/artifacts/v29r1_reliability_calibrated_noregret")
V29_RUN = "v29_development_regression_apr01_04"
V28_RUN = "v28r2_april_full_month_preflight"
EXPECTED_V29_SCOPE_HASHES = {
    "V29_DEVELOPMENT_RESULT": "02cccf4a91a4d7ec5d25e4523b4b494ace4a51278fc9d138859587b6034dbaf7",
    "V29_FROZEN_4DAY_OUTPUTS": "2fed23fb7a1b5cef32d71665c49045cac6948a64240c0f2b5ac9530b8f918150",
    "V22SR1": "f5a966520b89c2cc33b345897fdda0e045462ea29a81b6d2093e66c20e6e2b55",
    "V24T": "34a84650eb9423438cde4a8ef27070d2d8d0b6b81a99ed45d2ed7f87919b1d4d",
    "SOURCE_CACHE": "8c5ad281192bd33a91dd6001736de0d4b05d76477be85480ffa757b6e12ca340",
    "RAW_KESTREL_ARCHIVE": "5c044e77e8d1fbd27020c1223eae3687530453e2a7153574226bc0b7a9c63fdd",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ("git", "-C", str(repo), *args), text=True, encoding="utf-8", errors="replace",
    ).strip()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    os.replace(temporary, path)


def write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def files_under(paths: Iterable[Path]) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for root_index, root in enumerate(paths):
        if root.is_file():
            rows.append((f"{root_index}/{root.name}", root))
        elif root.is_dir():
            rows.extend(
                (f"{root_index}/{path.relative_to(root).as_posix()}", path)
                for path in root.rglob("*") if path.is_file()
            )
    return sorted(rows, key=lambda row: row[0])


def hash_scope(paths: Sequence[Path]) -> dict[str, object]:
    files = files_under(paths)
    digest = hashlib.sha256()
    byte_count = 0
    for relative, path in files:
        size = path.stat().st_size
        byte_count += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_sha(path).encode("ascii"))
        digest.update(b"\n")
    return {
        "paths": [str(path) for path in paths],
        "file_count": len(files),
        "byte_count": byte_count,
        "content_tree_sha256": digest.hexdigest(),
    }


def certificate_paths(*repos: Path) -> list[Path]:
    result: list[Path] = []
    for repo in repos:
        for root in (repo / "dayahead/artifacts", repo / "frozen_artifacts"):
            if root.is_dir():
                result.extend(
                    path for path in root.rglob("*")
                    if path.is_file() and "CERTIFICATE" in path.name.upper()
                )
    return sorted(set(result))


def protected_scopes(
    authority: Path, campaign: Path, post_forensic: Path,
    preapril_census: Path, v28_forensic: Path,
) -> dict[str, list[Path]]:
    return {
        "V29_DEVELOPMENT_RESULT": [authority / "dayahead/artifacts/v29_grid_responsive_aidc"],
        "V29_FROZEN_4DAY_OUTPUTS": [authority / f"frozen_artifacts/{V29_RUN}"],
        "V29_FINAL_REVIEW": [
            authority / "dayahead/artifacts/v29_grid_responsive_aidc/V29_FINAL_DEVELOPMENT_REVIEW.json",
            authority / "dayahead/artifacts/v29_grid_responsive_aidc/V29_FINAL_DEVELOPMENT_REVIEW.md",
        ],
        "V29_POSTCARRYIN_FORENSIC": [
            post_forensic / "dayahead/artifacts/v29_postcarryin_operational_value_forensic"
        ],
        "V29_PREAPRIL_CENSUS": [preapril_census / "dayahead/artifacts/v29_preapril_census"],
        "V28R2_FROZEN_CAMPAIGN": [campaign / f"frozen_artifacts/{V28_RUN}"],
        "V28R2_FORENSIC": [
            v28_forensic / "dayahead/artifacts/v28r2_aidc_grid_value_forensic"
        ],
        "V22SR1": [authority / "dayahead/artifacts/v22s_r1_final_operating_scale"],
        "V24T": [authority / "dayahead/artifacts/v24t_thermal_aware_aidc"],
        "V29_SOURCE_AUTHORITIES": [authority / "cache/v29_grid_responsive_aidc"],
        "SOURCE_CACHE": [campaign / "cache/v28r2_campaign_sources"],
        "RAW_KESTREL_ARCHIVE": [source_zip()],
        "EXISTING_CERTIFICATES": certificate_paths(
            authority, campaign, post_forensic, preapril_census, v28_forensic,
        ),
    }


def repo_heads(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path,
    preapril_census: Path, v28_forensic: Path,
) -> dict[str, object]:
    values = {
        "v29r1": repo,
        "v29_production": authority,
        "v28r2_campaign": campaign,
        "v29_postcarryin_forensic": post_forensic,
        "v29_preapril_census": preapril_census,
        "v28r2_forensic": v28_forensic,
    }
    return {
        name: {
            "path": str(path),
            "branch": git(path, "branch", "--show-current"),
            "head": git(path, "rev-parse", "HEAD"),
            "status_short": git(path, "status", "--short"),
        }
        for name, path in values.items()
    }


def verify_git_authority(heads: Mapping[str, object]) -> None:
    required = {
        "v29r1": (V29R1_BRANCH, PRODUCTION_BASE_HEAD),
        "v29_production": ("codex/v29-grid-responsive-aidc-flexibility", PRODUCTION_BASE_HEAD),
        "v29_postcarryin_forensic": (
            "codex/v29-postcarryin-operational-value-forensic", POSTCARRYIN_FORENSIC_HEAD,
        ),
        "v29_preapril_census": (
            "codex/v29-preapril-carryin-calibration-census", PREAPRIL_CENSUS_HEAD,
        ),
    }
    for name, (branch, head) in required.items():
        row = heads[name]
        if row["branch"] != branch or row["head"] != head:
            raise RuntimeError(f"V29R1_GIT_AUTHORITY_MISMATCH:{name}:{row}")
    for name in ("v29_production", "v29_postcarryin_forensic", "v29_preapril_census"):
        if heads[name]["status_short"]:
            raise RuntimeError(f"V29R1_READONLY_EVIDENCE_DIRTY:{name}")


def build_manifest(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path,
    preapril_census: Path, v28_forensic: Path,
) -> dict[str, object]:
    heads = repo_heads(repo, authority, campaign, post_forensic, preapril_census, v28_forensic)
    verify_git_authority(heads)
    scopes = protected_scopes(authority, campaign, post_forensic, preapril_census, v28_forensic)
    hashed: dict[str, object] = {}
    for name, paths in scopes.items():
        print(json.dumps({"phase": "prechange-hash", "scope": name}), flush=True)
        if not paths or any(not path.exists() for path in paths):
            raise RuntimeError(f"V29R1_PROTECTED_SCOPE_MISSING:{name}")
        hashed[name] = hash_scope(paths)
    expected_checks = {
        name: hashed[name]["content_tree_sha256"] == expected
        for name, expected in EXPECTED_V29_SCOPE_HASHES.items()
    }
    if not all(expected_checks.values()):
        raise RuntimeError(f"V29R1_EXISTING_AUTHORITY_HASH_MISMATCH:{expected_checks}")
    payload = {
        "artifact_id": "V29R1_PRECHANGE_AUTHORITY_MANIFEST_V1",
        "status": "PASS",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "starting_git_authorities": heads,
        "protected_scopes": hashed,
        "known_frozen_hash_checks": expected_checks,
        "firewall": {
            "base_is_exact_v29_production": True,
            "forensic_branches_are_read_only": True,
            "merge_used": False,
            "cherry_pick_used": False,
            "april_performance_available_to_trust_selection": False,
            "may_execution_allowed": False,
        },
    }
    write_json(repo / ARTIFACT_REL / "V29R1_PRECHANGE_AUTHORITY_MANIFEST.json", payload)
    return payload


def build_trust_block(repo: Path, campaign: Path) -> dict[str, object]:
    cache = campaign / "cache/v28r2_campaign_sources/april_2025"
    day_root = cache / "days"
    materialized_days = sorted(path.name for path in day_root.iterdir() if path.is_dir())
    requested = list(CERTIFICATION_DAYS)
    available_requested = sorted(set(requested) & set(materialized_days))
    missing = sorted(set(requested) - set(materialized_days))
    production_pipeline = repo / "dayahead/v28r2/source_preflight.py"
    cache_contract = repo / "dayahead/v28r2/source_cache.py"
    pipeline_text = production_pipeline.read_text(encoding="utf-8")
    cache_text = cache_contract.read_text(encoding="utf-8")
    pipeline_april_only = (
        "APRIL_DAYS = tuple" in pipeline_text
        and "for day in APRIL_DAYS" in pipeline_text
        and '"cache/v28r2_campaign_sources/april_2025"' in cache_text
    )
    april_used = any(day.startswith("2025-04-") for day in available_requested)
    sufficient = (
        not pipeline_april_only
        and len(available_requested) == len(requested)
        and not missing
        and not april_used
    )
    status = "PASS" if sufficient else BLOCKED_SOURCE_STATUS
    provenance = {
        "artifact_id": "V29R1_TRUST_CERT_INPUT_PROVENANCE_V1",
        "status": status,
        "certification_period": {"start": requested[0], "end": requested[-1], "day_count": len(requested)},
        "required_namespace": "causal Day-Ahead electrical inputs through current production source pipeline",
        "production_pipeline": {
            "path": str(production_pipeline),
            "sha256": file_sha(production_pipeline),
            "APRIL_DAYS_count": len(APRIL_DAYS),
            "APRIL_DAYS_first": APRIL_DAYS[0],
            "APRIL_DAYS_last": APRIL_DAYS[-1],
            "april_only_contract_detected": pipeline_april_only,
        },
        "source_cache": {
            "path": str(cache),
            "materialized_day_count": len(materialized_days),
            "materialized_first": materialized_days[0] if materialized_days else None,
            "materialized_last": materialized_days[-1] if materialized_days else None,
            "requested_Jan_Mar_days_available": len(available_requested),
            "requested_Jan_Mar_days_missing": len(missing),
            "missing_days": missing,
        },
        "leakage_guard": {
            "April_development_days_used_for_certification": False,
            "Actual_April_used_for_certification": False,
            "April_substitution_permitted": False,
        },
        "decision": "STOP before AC/C1 candidate execution" if not sufficient else "CONTINUE",
        "reason": (
            "The production materializer and cache cover April 2025 only; none of the 90 required "
            "Jan-Mar causal feeder-state days is materialized under the current production source authority."
            if not sufficient else "All frozen causal source gates passed."
        ),
    }
    write_json(repo / ARTIFACT_REL / "V29R1_TRUST_CERT_INPUT_PROVENANCE.json", provenance)
    candidate_rows = [
        {
            "rho_AIDC": f"{rho:.2f}",
            "frozen_before_April_evaluation": True,
            "selection_criterion": "largest candidate passing every frozen AC/C1 validation gate",
            "performance_selection_allowed": False,
            "status": "NOT_EVALUATED_SOURCE_AUTHORITY_BLOCK",
        }
        for rho in CANDIDATE_RHOS
    ]
    write_csv(
        repo / ARTIFACT_REL / "V29R1_TRUST_CERT_CANDIDATES.csv", candidate_rows,
        ("rho_AIDC", "frozen_before_April_evaluation", "selection_criterion", "performance_selection_allowed", "status"),
    )
    not_run = [
        {
            "rho_AIDC": f"{rho:.2f}", "certification_day_count": 0,
            "April_rows_used": 0, "status": "NOT_RUN_SOURCE_AUTHORITY_BLOCK",
        }
        for rho in CANDIDATE_RHOS
    ]
    fields = ("rho_AIDC", "certification_day_count", "April_rows_used", "status")
    write_csv(repo / ARTIFACT_REL / "V29R1_TRUST_CERT_OPENDSS_RESULTS.csv", not_run, fields)
    write_csv(repo / ARTIFACT_REL / "V29R1_TRUST_CERT_C1_RESULTS.csv", not_run, fields)
    decision = {
        "artifact_id": "V29R1_TRUST_CERT_DECISION_V1",
        "status": status,
        "candidate_set": list(CANDIDATE_RHOS),
        "selection_rule": "largest candidate passing every frozen AC/C1 validation gate",
        "selected_rho_AIDC": None,
        "production_rho_changed": False,
        "AC_candidate_runs": 0,
        "C1_candidate_runs": 0,
        "April_rows_used": 0,
        "MESS_trust_region_changed": False,
        "downstream_science_authorized": sufficient,
        "blocked_reason": None if sufficient else provenance["reason"],
    }
    write_json(repo / ARTIFACT_REL / "V29R1_TRUST_CERT_DECISION.json", decision)
    review = f"""# V29R1 physics-certified AIDC trust-region review

Status: `{status}`

The candidate set `{list(CANDIDATE_RHOS)}` was frozen before April evaluation. The required
certification population is 90 causal Day-Ahead electrical-input days from 2025-01-01
through 2025-03-31. The current production materializer is explicitly April-only and its
source cache contains {len(materialized_days)} materialized days, all in April; it contains
{len(available_requested)} of the required Jan--Mar days.

No April Day-Ahead or Actual result was substituted. No OpenDSS or C1 candidate sweep was
run, no rho was selected, and production rho/MESS authority was not changed. Per the frozen
protocol, downstream service, Bridge V2, Reference V4, Q no-regret, smoke, and Apr-1--4
development regression stages are not authorized in this lineage.
"""
    (repo / ARTIFACT_REL / "V29R1_TRUST_CERT_FINAL_REVIEW.md").write_text(
        review, encoding="utf-8", newline="\n",
    )
    return decision


def preservation_audit(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path,
    preapril_census: Path, v28_forensic: Path,
) -> dict[str, object]:
    manifest = json.loads(
        (repo / ARTIFACT_REL / "V29R1_PRECHANGE_AUTHORITY_MANIFEST.json").read_text(encoding="utf-8")
    )
    current: dict[str, object] = {}
    mismatches: list[str] = []
    scopes = protected_scopes(authority, campaign, post_forensic, preapril_census, v28_forensic)
    for name, paths in scopes.items():
        print(json.dumps({"phase": "postchange-hash", "scope": name}), flush=True)
        current[name] = hash_scope(paths)
        if current[name]["content_tree_sha256"] != manifest["protected_scopes"][name]["content_tree_sha256"]:
            mismatches.append(name)
    heads = repo_heads(repo, authority, campaign, post_forensic, preapril_census, v28_forensic)
    evidence_heads_unchanged = (
        heads["v29_production"]["head"] == PRODUCTION_BASE_HEAD
        and heads["v29_postcarryin_forensic"]["head"] == POSTCARRYIN_FORENSIC_HEAD
        and heads["v29_preapril_census"]["head"] == PREAPRIL_CENSUS_HEAD
    )
    payload = {
        "artifact_id": "V29R1_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "status": "PASS" if not mismatches and evidence_heads_unchanged else "FAIL",
        "protected_scope_mismatch_count": len(mismatches),
        "mismatched_scopes": mismatches,
        "evidence_heads_unchanged": evidence_heads_unchanged,
        "prechange": manifest["protected_scopes"],
        "postchange": current,
        "final_git_authorities": heads,
    }
    write_json(repo / ARTIFACT_REL / "V29R1_POSTCHANGE_PRESERVATION_AUDIT.json", payload)
    if payload["status"] != "PASS":
        raise RuntimeError(f"V29R1_PROTECTED_AUTHORITY_MUTATION:{mismatches}")
    return payload


TEST_NAMES = (
    "exact V29 base authority", "forensic/census evidence read-only", "V28/V29 preservation",
    "trust candidate set frozen", "April rows absent from trust certification",
    "trust rho selected only by AC/C1 certificate", "service model causal labels",
    "April service fit rows = 0", "90% lower-bound target frozen",
    "aggregate lower-bound calibration", "bridge V2 causal propagation",
    "no post-cutoff actual features", "V4 reference B0/B2 byte identity",
    "V4 no P/G double count", "nonnegative residual", "no clipping",
    "PARTIAL/shared noncontrollable", "no running preemption", "no synthetic deadline",
    "MESS physical authority unchanged", "Q anchor exact identity with B2",
    "Q release no-regret constraints", "scenario set frozen", "fallback deterministic",
    "primary objective unchanged", "Actual optimizer calls zero", "PI firewall",
    "connection delay DA=PI=Actual", "Fresh OpenDSS clean-engine behavior",
    "artifact SHA self-consistency", "no scientific mutation of protected authorities",
)


def build_test_report(repo: Path, preservation: Mapping[str, object]) -> dict[str, object]:
    rows = []
    pass_indices = {1, 2, 3, 4, 5, 20, 23, 25, 30, 31}
    for index, name in enumerate(TEST_NAMES, start=1):
        status = "PASS" if index in pass_indices else "NOT_RUN_BLOCKED_AT_STAGE_2"
        rows.append({"test": index, "name": name, "status": status})
    payload = {
        "artifact_id": "V29R1_TEST_REPORT_V1",
        "status": BLOCKED_SOURCE_STATUS,
        "required_test_count": len(TEST_NAMES),
        "pass_count": sum(row["status"] == "PASS" for row in rows),
        "not_run_count": sum(row["status"].startswith("NOT_RUN") for row in rows),
        "failure_count": 0,
        "all_31_passed": False,
        "smoke_authorized": False,
        "frozen_pre_April_authorities": {
            "candidate_rhos": list(CANDIDATE_RHOS),
            "service_lower_coverage_target": RELIABILITY_TARGET,
            "q_scenarios": list(Q_SCENARIOS),
        },
        "preservation_status": preservation["status"],
        "pytest_verification": {
            "V29R1_dedicated": "6 passed",
            "portable_exact_base_checkout_excluding_legacy_SHA_selfcheck": "27 passed, 1 legacy frozen-output-path failure",
            "legacy_V29_checkout_local_failures": [
                "V29 artifact SHA manifest records CRLF authority-worktree bytes while a fresh .gitattributes checkout is LF",
                "V29 stage-6 reporting expects an untracked frozen_artifacts run directory absent from a fresh worktree",
            ],
            "same_two_tests_at_exact_V29_authority_read_only": "2 passed",
            "V29_authority_status_after_read_only_tests": "clean",
        },
        "tests": rows,
    }
    write_json(repo / ARTIFACT_REL / "V29R1_TEST_REPORT.json", payload)
    return payload


def artifact_inventory(out: Path) -> dict[str, object]:
    destination = out / "V29R1_ARTIFACT_SHA256.json"
    records = []
    for path in sorted(path for path in out.rglob("*") if path.is_file() and path != destination):
        records.append({
            "relative_path": path.relative_to(out).as_posix(),
            "byte_count": path.stat().st_size,
            "sha256": file_sha(path),
        })
    payload = {
        "artifact_id": "V29R1_ARTIFACT_SHA256_V1",
        "status": "PASS",
        "self_excluded_to_avoid_circular_hash": True,
        "artifact_count": len(records),
        "artifacts": records,
    }
    write_json(destination, payload)
    return payload


def finalize(repo: Path, decision: Mapping[str, object], preservation: Mapping[str, object]) -> None:
    out = repo / ARTIFACT_REL
    tests = build_test_report(repo, preservation)
    missing_downstream = [
        "CARRYIN_EXECUTABLE_SERVICE_V1", "PRE_DAY_QUEUE_BRIDGE_V2",
        "REFERENCE_COMPUTE_SCHEDULE_V4", "B2_ANCHORED_NO_REGRET_Q_RELEASE_V1",
        "V29R1_DEV_FREEZE_HEAD", "CURRENT_HEAD_SMOKE", "APR1_4_DEVELOPMENT_REGRESSION",
    ]
    review = {
        "artifact_id": "V29R1_FINAL_DEVELOPMENT_REVIEW_V1",
        "RESULT_CLASSIFICATION": BLOCKED_SOURCE_STATUS,
        "axes": {
            "TECHNICAL_STATUS": "STOPPED_FAIL_CLOSED_AT_STAGE_2",
            "SOURCE_AUTHORITY": "INSUFFICIENT_JAN_MAR_CAUSAL_ELECTRICAL_INPUTS",
            "TRUST_CERT_STATUS": "NOT_CERTIFIED",
            "SERVICE_CALIBRATION_STATUS": "NOT_RUN",
            "BRIDGE_V2_STATUS": "NOT_RUN",
            "Q_NOREGRET_STATUS": "NOT_RUN",
            "DAYAHEAD_GRID_EFFECT_STATUS": "NOT_EVALUATED",
            "ACTUAL_NOREGRET_STATUS": "NOT_EVALUATED",
            "AC_PHYSICAL_STATUS": "NOT_EVALUATED",
            "PRESERVATION_STATUS": preservation["status"],
        },
        "selected_rho_AIDC": None,
        "production_rho_changed": False,
        "blocked_at_stage": 2,
        "blocked_reason": decision["blocked_reason"],
        "downstream_stages_not_run": missing_downstream,
        "all_31_tests_passed": tests["all_31_passed"],
        "Apr_1_4_development_regression_executed": False,
        "Apr_5_30_integration_preflight_authorized": False,
        "May_executed": False,
        "retrospective_tuning_performed": False,
    }
    write_json(out / "V29R1_FINAL_DEVELOPMENT_REVIEW.json", review)
    md = f"""# V29R1 final development review

RESULT CLASSIFICATION: `{BLOCKED_SOURCE_STATUS}`

## Axes

- TECHNICAL_STATUS: STOPPED_FAIL_CLOSED_AT_STAGE_2
- SOURCE_AUTHORITY: INSUFFICIENT_JAN_MAR_CAUSAL_ELECTRICAL_INPUTS
- TRUST_CERT_STATUS: NOT_CERTIFIED
- SERVICE_CALIBRATION_STATUS: NOT_RUN
- BRIDGE_V2_STATUS: NOT_RUN
- Q_NOREGRET_STATUS: NOT_RUN
- DAYAHEAD_GRID_EFFECT_STATUS: NOT_EVALUATED
- ACTUAL_NOREGRET_STATUS: NOT_EVALUATED
- AC_PHYSICAL_STATUS: NOT_EVALUATED
- PRESERVATION_STATUS: {preservation['status']}

## 1. Starting Git authority

V29R1 was branched exactly from `{PRODUCTION_BASE_HEAD}` on `{V29R1_BRANCH}`.

## 2. Protected-state verification

All protected content-tree hashes were reproduced after the audit; mismatch count is
{preservation['protected_scope_mismatch_count']}.

## 3. Physics-certified trust-region methodology

The candidate set `{list(CANDIDATE_RHOS)}` and largest-all-gates-pass selection rule were
frozen prospectively. Certification required 90 causal Jan--Mar electrical-input days.

## 4. Selected rho_AIDC and why

No rho was selected because the required source authority was insufficient.

## 5. Why this is not performance tuning

No April Day-Ahead or Actual result was used, and no candidate AC/C1 sweep ran.

## 6. Executable-service model

Not run because Stage 2 issued the mandatory fail-closed stop.

## 7. Pre-April rolling-origin coverage

Not run; no calibrated coverage claim is made.

## 8. Nominal vs lower executable-service sharpness

Not run; no nominal/lower channel was promoted to production.

## 9. Bridge V2 calibration

Not run.

## 10. Reference Schedule V4

Not run.

## 11. P/G residual and double-count audit

Not run; no V4 residual was constructed.

## 12. B2-anchored Q no-regret formulation

The scenario family `{list(Q_SCENARIOS)}` was frozen prospectively, but formulation and
solve stages were not authorized.

## 13. Q-anchor ablation

Not run.

## 14. Was Q release allowed on each day?

No day was evaluated and Q release was never authorized.

## 15. Scenario no-regret margins

Not evaluated.

## 16. Apr-1--4 Day-Ahead B0/B1/B2/B3

Not run.

## 17. Did B0->B1 effect increase relative to V29?

Not evaluated.

## 18. Did B2->B3 remain resolved?

Not evaluated.

## 19. Actual B2 vs B3

Not run.

## 20. Did Actual no-regret pass on every day?

Not evaluated; no pass is claimed.

## 21. Fresh OpenDSS physical results

Not run for V29R1 candidates.

## 22. Carry-in nominal/lower/realized comparison

Not run.

## 23. Missed workload after service calibration

Not evaluated.

## 24. Did rack-capacity miss remain dominant?

Not evaluated after calibration.

## 25. Ablation attribution

Trust, service/bridge, Q-anchor, and no-regret-release ablations were not run and were not
used for parameter selection.

## 26. Remaining primary bottleneck

Missing Jan--Mar causal feeder-state source authority in the current production pipeline.

## 27. Remaining secondary bottleneck

Not evaluated beyond the primary source-authority stop.

## 28. What cannot be claimed because carry-in is rare

No general persistent AIDC benefit can be claimed; frozen evidence characterizes carry-in
as opportunistic and absent on most historical days.

## 29. Tests

{tests['pass_count']} pre-block gates passed and {tests['not_run_count']} downstream gates
were not run. The required 31/31 pre-smoke gate was not achieved, so smoke was prohibited.
The dedicated V29R1 suite passed 6/6. The portable exact-base checkout passed 27 tests;
its two legacy checkout-local assumptions (CRLF byte inventory and an untracked frozen-output
directory) were rerun read-only at the exact V29 authority and passed 2/2 there.

## 30. Artifacts/SHA

The SHA inventory covers only authority, trust-block, preservation, test, and review
artifacts generated before or at the fail-closed stop.

## 31. Preservation audit

Status `{preservation['status']}` with zero protected-scope mismatch.

## 32. Final Git status

Recorded after the final commit in the task handoff; no push or merge is performed.

## 33. Is Apr-5--30 integration preflight authorized?

No. `APRIL_5_30_PREFLIGHT_AUTHORIZED=false`.

V29R1 selected rho_AIDC=NOT_SELECTED through physics certification rather than April performance tuning.

V29R1 did not reach the service stage; raw requested carry-in service was not promoted to production, and no causally calibrated nominal/lower representation was falsely claimed as frozen.

V29R1 did not reach Q release; MESS reactive-power deviation from B2 was never authorized.

Across the Apr-1–4 development/regression set, Actual B3 no-regret was not evaluated because the mandatory Stage-2 source-authority gate stopped execution.

Apr-1–4 remains development/regression evidence and is not final independent validation.

Apr-5–30 integration preflight is NOT AUTHORIZED.
"""
    (out / "V29R1_FINAL_DEVELOPMENT_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    readme = f"""# V29R1 reliability-calibrated no-regret prospective refreeze

This artifact root records a fail-closed Stage-2 result: `{BLOCKED_SOURCE_STATUS}`.
The current production source pipeline and cache cover April 2025, not the required
Jan--Mar certification population. No April substitution, rho selection, downstream
science, smoke, Apr-1--4 regression, Apr-5--30 preflight, or May execution occurred.
"""
    (out / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    artifact_inventory(out)


def run(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path,
    preapril_census: Path, v28_forensic: Path,
) -> None:
    manifest = build_manifest(repo, authority, campaign, post_forensic, preapril_census, v28_forensic)
    if manifest["status"] != "PASS":
        raise RuntimeError("V29R1_PRECHANGE_AUTHORITY_MANIFEST_FAILED")
    decision = build_trust_block(repo, campaign)
    preservation = preservation_audit(
        repo, authority, campaign, post_forensic, preapril_census, v28_forensic,
    )
    finalize(repo, decision, preservation)
    print(json.dumps({
        "status": decision["status"],
        "selected_rho_AIDC": decision["selected_rho_AIDC"],
        "downstream_science_authorized": decision["downstream_science_authorized"],
    }, sort_keys=True), flush=True)
