"""Plan or bind deterministic full-month power and mobility source views."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def period(
    repo: Path, period_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], Path]:
    path = repo / "pfr/contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    matches = [row for row in contract["periods"] if row["period_id"] == period_id]
    if len(matches) != 1:
        raise RuntimeError("full-month period is not present exactly once")
    return matches[0], contract, path


def mobility_index(root: Path) -> dict[int, tuple[Path, str | None]]:
    runtime = root / "mobility_runtime"
    rows: dict[int, tuple[Path, str | None]] = {}
    index_path = root / "R12_COMMON_MOBILITY_INDEX.csv"
    hashes: dict[int, str] = {}
    if index_path.is_file():
        cache_authority_path = root / "R12_COMMON_MOBILITY_CACHE_AUTHORITY.json"
        cache_authority = json.loads(cache_authority_path.read_text(encoding="utf-8"))
        if (
            cache_authority.get("status") != "PASS"
            or cache_authority.get("future_actual_target_read") is not False
            or cache_authority.get("index_sha256") != sha256(index_path)
        ):
            raise RuntimeError(f"mobility cache authority/index drift: {root}")
        with index_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                hashes[int(row["issue_step"])] = str(row.get("sha256") or "")
    for path in runtime.glob("issue_*.npz"):
        issue = int(path.name.split("_")[1])
        if issue in rows:
            raise RuntimeError(f"duplicate mobility issue inside {root}: {issue}")
        rows[issue] = (path.resolve(), hashes.get(issue) or None)
    return rows


def source_authorities(root: Path) -> list[dict[str, str]]:
    rows = []
    for path in sorted(root.glob("*.json")):
        upper = path.name.upper()
        if "AUTHORITY" in upper or "MANIFEST" in upper:
            rows.append({"path": str(path), "sha256": sha256(path)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--period-id", required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--generated-mobility-root", type=Path, action="append", default=[])
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    selected_period, contract, contract_path = period(args.repo, args.period_id)
    first = int(selected_period["global_issue_first"])
    last = int(selected_period["global_issue_last"])
    expected = set(range(first, last + 1))
    reused_roots = [Path(value) for value in selected_period["reused_mobility_roots"]]
    generated_roots = list(args.generated_mobility_root)

    dependency_paths = [
        args.repo
        / "performance/post_stage15_runtime_acceleration/package/scripts/PREPARE_W02_POWER_PRICE_SOURCE.py",
        args.repo
        / "performance/post_stage15_runtime_acceleration/package/scripts/PREPARE_W02_MOBILITY_SOURCE.py",
        args.repo
        / "stage7/r12_representative_weeks/materialize_r12_common_mobility_cache.py",
    ]
    frozen_generator_hashes = contract["source_generator_sha256"]
    dependency_checks = {
        str(path): bool(
            path.is_file()
            and frozen_generator_hashes.get(str(path.relative_to(args.repo)).replace("\\", "/"))
            == sha256(path)
        )
        for path in dependency_paths
    }
    dependency_ok = all(dependency_checks.values())
    reused_indexes = {str(root): mobility_index(root) for root in reused_roots}
    expected_reused_ranges = selected_period["reused_mobility_expected_ranges"]
    if len(expected_reused_ranges) != len(reused_roots):
        raise RuntimeError("reused mobility root/range axis mismatch")
    reused_range_checks = {}
    reused_allowed: dict[str, set[int]] = {}
    for root, expected_range in zip(reused_roots, expected_reused_ranges):
        required = set(
            range(int(expected_range["first"]), int(expected_range["last"]) + 1)
        )
        reused_allowed[str(root)] = required
        reused_range_checks[str(root)] = required <= set(reused_indexes[str(root)])
    reused_issues = set().union(*reused_allowed.values())
    reused_scored = expected & reused_issues
    report: dict[str, Any] = {
        "schema_version": "PFR_FULL_MONTH_SOURCE_PLAN_V13_13",
        "status": (
            "READY_TO_MATERIALIZE"
            if dependency_ok and all(reused_range_checks.values())
            else "BLOCKED"
        ),
        "period_id": args.period_id,
        "calendar_start": selected_period["calendar_start"],
        "days": selected_period["days"],
        "global_issue_first": first,
        "global_issue_last": last,
        "scored_issue_count": len(expected),
        "power_generation_starts": selected_period["power_generation_starts"],
        "mobility_generation_chunks": selected_period["mobility_generation_chunks"],
        "reused_mobility_issue_count": len(reused_scored),
        "issues_requiring_generated_source": len(expected - reused_scored),
        "dependency_checks": dependency_checks,
        "reused_source_range_checks": reused_range_checks,
        "contract_sha256": sha256(contract_path),
    }
    plan_path = args.shared_root / "SOURCE_MATERIALIZATION_PLAN.json"
    atomic_write_json(plan_path, report)
    if args.plan_only:
        print(json.dumps({"status": report["status"], "report": str(plan_path)}))
        if not dependency_ok or not all(reused_range_checks.values()):
            raise SystemExit(2)
        return

    power_blocks = []
    for path in sorted((args.shared_root / "power_price").glob("block_*_*_*")):
        if not path.is_dir():
            continue
        authority_path = path / "BLOCK_AUTHORITY.json"
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        if authority.get("status") != "PASS" or authority.get("future_actual_used") is not False:
            raise RuntimeError(f"invalid power block authority: {path}")
        power_blocks.append(
            (
                int(authority["issue_first"]),
                int(authority["issue_last"]),
                path,
                authority_path,
            )
        )
    power_blocks.sort()
    source_last = int(selected_period["source_padding_issue_last"])
    power_coverage = {
        issue
        for block_first, block_last, _, _ in power_blocks
        for issue in range(block_first, block_last + 1)
        if first <= issue <= source_last
    }
    if power_coverage != set(range(first, source_last + 1)):
        raise RuntimeError("full-month power blocks do not exactly cover scored+padding range")
    if any(
        current[0] <= previous[1]
        for previous, current in zip(power_blocks, power_blocks[1:])
    ):
        raise RuntimeError("full-month power blocks overlap")

    all_roots = reused_roots + generated_roots
    indexed = [(root, mobility_index(root)) for root in all_roots]
    generated_root_set = {str(root) for root in generated_roots}
    for root in generated_roots:
        full_authority_path = root / "REP_WEEK_MOBILITY_FULL_AUTHORITY.json"
        full_authority = json.loads(full_authority_path.read_text(encoding="utf-8"))
        if (
            full_authority.get("status") != "PASS"
            or full_authority.get("future_actual_used") is not False
            or int(full_authority.get("source_issue_count", -1)) != 2304
            or int(full_authority.get("scored_issue_count", -1)) != 2304
            or int(full_authority.get("padding_issue_count", -1)) != 0
        ):
            raise RuntimeError(f"generated full-month mobility authority drift: {root}")
    mobility_view = args.shared_root / "mobility/mobility_runtime"
    mobility_view.mkdir(parents=True, exist_ok=True)
    selected_rows = []
    for issue in range(first, last + 1):
        candidates = []
        for root, index in indexed:
            if issue not in index:
                continue
            if str(root) not in generated_root_set and issue not in reused_allowed[str(root)]:
                continue
            candidates.append((root, index[issue]))
        if not candidates:
            raise RuntimeError(f"missing full-month mobility issue {issue}")
        source_root, (source_path, recorded_hash) = candidates[0]
        target = mobility_view / source_path.name
        if target.exists() or target.is_symlink():
            if not target.is_symlink() or target.resolve() != source_path:
                raise RuntimeError(f"mobility view target drift: {target}")
        else:
            target.symlink_to(source_path)
        selected_rows.append(
            {
                "issue": issue,
                "source_root": str(source_root),
                "source_path": str(source_path),
                "recorded_sha256": recorded_hash,
                "view_path": str(target),
            }
        )
    template_source = reused_roots[0] / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    template_target = args.shared_root / "mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    if template_target.exists() or template_target.is_symlink():
        if not template_target.is_symlink() or template_target.resolve() != template_source.resolve():
            raise RuntimeError("mobility template view drift")
    else:
        template_target.symlink_to(template_source.resolve())

    index_path = args.shared_root / "mobility/FULL_MONTH_MOBILITY_VIEW_INDEX.json"
    atomic_write_json(
        index_path,
        {
            "status": "PASS",
            "period_id": args.period_id,
            "issue_first": first,
            "issue_last": last,
            "issue_count": len(selected_rows),
            "future_actual_used": False,
            "rows": selected_rows,
        },
    )
    authority = {
        "schema_version": "PFR_FULL_MONTH_SHARED_EXOGENOUS_AUTHORITY_V13_13",
        "status": "PASS",
        "candidate_id": args.period_id,
        "scored_issue_first": first,
        "scored_issue_last": last,
        "scored_issue_count": len(expected),
        "source_issue_last": source_last,
        "same_source_for_all_methods": True,
        "future_actual_used_by_optimizer": False,
        "period_contract_sha256": sha256(contract_path),
        "mobility_view_index_sha256": sha256(index_path),
        "template_bank_sha256": sha256(template_source),
        "power_block_authorities": [
            {"path": str(authority_path), "sha256": sha256(authority_path)}
            for _, _, _, authority_path in power_blocks
        ],
        "mobility_source_authorities": {
            str(root): source_authorities(root) for root in all_roots
        },
    }
    authority_path = args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
    atomic_write_json(authority_path, authority)
    print(json.dumps({
        "status": "PASS",
        "period_id": args.period_id,
        "issues": len(expected),
        "reused_issues": len(reused_scored),
        "authority": str(authority_path),
    }))


if __name__ == "__main__":
    main()
