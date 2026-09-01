"""Historical V15 C0-C2 materializer; disabled in the V16 production path."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .aidc_labels import LabelOrigin, SPLIT_CONTRACT, TargetLineage, dependency_firewall


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _global_stat(members: Sequence[Mapping[str, Any]], column: str, key: str) -> str | None:
    values = [
        member.get("statistics", {}).get(column, {}).get(key)
        for member in members
    ]
    values = [str(value) for value in values if value not in (None, "None")]
    if not values:
        return None
    return min(values) if key == "min" else max(values)


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("freeze_item", "status", "source", "function", "test"))
        writer.writeheader()
        writer.writerows(rows)


def materialize(preflight_path: Path, authority_path: Path, output: Path) -> dict[str, Any]:
    raise RuntimeError("HISTORICAL_V15_MATERIALIZER_DISABLED_UNDER_V16")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    key = preflight["key_sources"]
    kestrel = key["kestrel_jobs"]
    pue = key["nlr_esif_pue_it_power"]
    kestrel_members = kestrel["members"]
    pue_sha = pue["sha256"]
    kestrel_sha = kestrel["sha256"]

    lineages = (
        TargetLineage(
            target="P_NF",
            label_origin=LabelOrigin.OBSERVED_RAW,
            depends_on=("it_power_kw",),
            derivation_rule="source timestamp interpretation pending; observed IT active power then 15-minute aggregation only",
            source_file_sha256=(pue_sha,),
            source_system_id="NLR_ESIF_DATA_CENTER_PUE",
            timestamp_axis_id="ESIF_PUE_TIMESTAMP_TIMEZONE_UNRESOLVED",
            first_timestamp=pue["statistics"]["ts"]["min"],
            last_timestamp=pue["statistics"]["ts"]["max"],
        ),
        TargetLineage(
            target="G_NF",
            label_origin=LabelOrigin.SOURCE_DERIVED,
            depends_on=("start_time", "end_time", "gpus_requested", "partition", "state_simple"),
            derivation_rule="sum source-backed active GPU allocations on the timezone-aware Kestrel operational axis",
            source_file_sha256=(kestrel_sha,),
            source_system_id="NLR_KESTREL_SLURM",
            timestamp_axis_id="KESTREL_TZ_AWARE_MOUNTAIN_TO_FIXED_AEST_15MIN_V1",
            first_timestamp=_global_stat(kestrel_members, "start_time", "min"),
            last_timestamp=_global_stat(kestrel_members, "end_time", "max"),
        ),
        TargetLineage(
            target="W_F",
            label_origin=LabelOrigin.SOURCE_DERIVED,
            depends_on=("submit_time", "start_time", "end_time", "gpus_requested"),
            derivation_rule="development-frozen cohorts from source-backed future job arrivals; no future job ID fabrication",
            source_file_sha256=(kestrel_sha,),
            source_system_id="NLR_KESTREL_SLURM",
            timestamp_axis_id="KESTREL_TZ_AWARE_MOUNTAIN_TO_FIXED_AEST_15MIN_V1",
            first_timestamp=_global_stat(kestrel_members, "submit_time", "min"),
            last_timestamp=_global_stat(kestrel_members, "submit_time", "max"),
        ),
    )
    lineage_audit = dependency_firewall(lineages)
    lineage_payload = {
        "authority_id": "AIDC_LABEL_ORIGIN_PROVENANCE_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": lineage_audit["status"],
        "targets": lineage_audit["targets"],
        "joint_alignment": {
            "status": lineage_audit["status"],
            "failures": lineage_audit["failures"],
            "row_wise_cross_dataset_merge_performed": False,
            "synthetic_temporal_alignment_performed": False,
            "resource_coupling_claim_eligible": lineage_audit["resource_coupling_claim_eligible"],
        },
    }
    _atomic_json(output / "AIDC_LABEL_LINEAGE.json", lineage_payload)
    _atomic_json(output / "AIDC_LABEL_PROVENANCE_AUDIT.json", lineage_audit)
    _atomic_json(
        output / "AIDC_RAW_PREFLIGHT.json",
        {
            "authority_id": "AIDC_RAW_PREFLIGHT_V1",
            "status": preflight["status"],
            "failures": preflight["failures"],
            "scientific_coverage_findings": preflight.get("scientific_coverage_findings", []),
            "raw_root": preflight["raw_root"],
            "read_only_source_root": True,
            "inventory_summary": preflight["inventory_summary"],
            "key_sources": {
                "kestrel": {
                    "path": kestrel["path"],
                    "sha256": kestrel_sha,
                    "rows": kestrel["rows"],
                    "partitions": kestrel["hive_year_month_partitions"],
                },
                "pue_it_power": {
                    "path": pue["path"],
                    "sha256": pue_sha,
                    "rows": pue["rows"],
                    "timestamp_min": pue["statistics"]["ts"]["min"],
                    "timestamp_max": pue["statistics"]["ts"]["max"],
                    "it_power_null_count": pue["statistics"]["it_power_kw"]["null_count"],
                },
                "h100_b200": {
                    "path": key["h100_b200_support"]["path"],
                    "sha256": key["h100_b200_support"]["sha256"],
                    "scientific_role": "PARAMETER_SUPPORT_ONLY_NO_ROWWISE_KESTREL_MERGE",
                },
                "aemo_archive_file_count": key["aemo_archive_file_count"],
                "scats_archive_file_count": key["scats_archive_file_count"],
            },
        },
    )
    _atomic_json(
        output / "AIDC_SPLIT_CONTRACT.json",
        {
            "authority_id": "AIDC_SPLIT_CONTRACT_V1",
            "status": "DEFINED_NOT_ACTIVATED_BLOCKED_BY_C2",
            **SPLIT_CONTRACT,
            "november_or_december_opened_by_training_code": False,
            "final_production_refit_performed": False,
        },
    )

    authority["c0_preimplementation_working_tree_clean"] = True
    authority["c0_preimplementation_parent_sha"] = "94b6d320d524ea6ef76ba324f91cb820e8e48004"
    authority["remote_pr9_sha_at_c0"] = "94b6d320d524ea6ef76ba324f91cb820e8e48004"
    authority["raw_preflight_sha256"] = _sha256(preflight_path)
    authority["c2_status"] = lineage_audit["status"]
    authority["c2_failures"] = lineage_audit["failures"]
    authority["proposed_model_implementation_authorized"] = lineage_audit["status"] == "PASS"
    _atomic_json(authority_path, authority)

    blocked = lineage_audit["status"] != "PASS"
    blocked_status = "NOT_RUN_BLOCKED_BY_C2_LABEL_ALIGNMENT_GATE"
    _atomic_json(
        output / "AIDC_ML_FREEZE_REPORT.json",
        {
            "status": blocked_status if blocked else "READY_FOR_C3_C6",
            "label_gate": lineage_audit,
            "model_training_started": False,
            "november_primary_evaluation_started": False,
            "december_replication_started": False,
            "synthetic_label_created": False,
            "reduced_target_model_selected_by_codex": False,
        },
    )
    for name, scope in (
        ("DAYAHEAD_EQUIVALENCE_REPORT.json", "C7-C9 monolithic/BD equivalence"),
        ("DAYAHEAD_OPENDSS_SMOKE_REPORT.json", "C10 Fresh OpenDSS"),
        ("DAYAHEAD_RESULT_SCHEMA_AUDIT.json", "C11 result schema"),
    ):
        _atomic_json(
            output / name,
            {
                "status": blocked_status,
                "scope": scope,
                "scientific_reason": "C2 P/G/W joint label gate failed; downstream proposed evidence is prohibited before prospective re-freeze",
                "solver_calls": 0,
                "opendss_calls": 0,
            },
        )

    traceability = [
        {"freeze_item": "C0 Branch & Authority Snapshot", "status": "PASS", "source": "dayahead/authority.py", "function": "dayahead.cli.authority_snapshot", "test": "tests/dayahead/test_authority.py"},
        {"freeze_item": "C1 Raw Data Preflight", "status": "PASS_WITH_C2_COVERAGE_FINDING", "source": "dayahead/aidc_preflight.py", "function": "audit", "test": "tests/dayahead/test_preflight.py"},
        {"freeze_item": "C2 AIDC P/G/W Label & Alignment Gate", "status": "FAIL_STOP", "source": "dayahead/aidc_labels.py", "function": "dependency_firewall", "test": "tests/dayahead/test_label_gate.py"},
        {"freeze_item": "C3 Cohort/Split/Causality Freeze", "status": blocked_status, "source": "dayahead/aidc_labels.py; dayahead/input_contract.py", "function": "SPLIT_CONTRACT; issuance_cutoff", "test": "tests/dayahead/test_input_contract.py"},
    ]
    for stage in range(4, 13):
        traceability.append({"freeze_item": f"C{stage}", "status": blocked_status, "source": "", "function": "", "test": ""})
    _write_csv(output / "DAYAHEAD_PRECODE_TO_CODE_TRACEABILITY.csv", traceability)

    report = f"""# CODEX Day-Ahead AIDC Joint Implementation Report

## Outcome

Implementation stopped at the mandatory C2 scientific gate. The source audit is complete enough to establish that the only observed NLR ESIF IT-power series ends at `{pue["statistics"]["ts"]["max"]}`, before the frozen September-October validation and November-December locked evaluation windows. Its supplied README also does not state the timezone semantics of `ts`. P/G/W do not share one proven source-system/time-axis identity. Creating a synthetic P target, row-wise joining independent traces, or silently reducing the model is prohibited.

## Authority and source

- Branch: `codex/dayahead-aidc-joint-v1`
- Parent / PR #9 HEAD: `94b6d320d524ea6ef76ba324f91cb820e8e48004`
- Scientific framework: `V15_DA_AIDC_ICPS`
- Raw root: `{preflight["raw_root"]}` (read-only)
- Full inventory: {preflight["inventory_summary"]["file_count"]} files, {preflight["inventory_summary"]["total_bytes"]} bytes, SHA-256 complete
- Kestrel: {kestrel["rows"]} rows in {kestrel["parquet_member_count"]} Parquet members
- ESIF PUE/IT power: {pue["rows"]} rows, observed span `{pue["statistics"]["ts"]["min"]}` to `{pue["statistics"]["ts"]["max"]}`

## Implemented scope

- Frozen authority IDs and mapping digest contracts
- Fixed-AEST D-1 18:00 cutoff and exact 96-slot axis
- Energy-preserving AEMO 30-to-15 hold, realized 5-to-15 mean, and mobility-energy 5-to-15 sum
- Complete-product latest-vintage selection without per-slot mixing
- Read-only full raw inventory/hash and key Parquet/ZIP metadata audit
- P/G/W label-origin, dependency, source-system, time-axis, and coverage firewall
- Split/seed/calibration contract definition without activating training

## Changed files

- `dayahead/__init__.py`
- `dayahead/authority.py`
- `dayahead/input_contract.py`
- `dayahead/aidc_preflight.py`
- `dayahead/aidc_labels.py`
- `dayahead/cli.py`
- `dayahead/materialize_precode_gate.py`
- `dayahead/finalize_precode_artifacts.py`
- `tests/dayahead/test_authority.py`
- `tests/dayahead/test_input_contract.py`
- `tests/dayahead/test_label_gate.py`
- `tests/dayahead/test_preflight.py`
- `dayahead/artifacts/precode/*` (C0-C2 evidence and blocked downstream reports)

## Scientific invariants preserved

- No historical result bytes were relabelled.
- No synthetic label or future job ID was created.
- No row-wise cross-dataset temporal fabrication was performed.
- No November/December training, tuning, optimization, or evaluation was started.
- No reduced-target model was selected by Codex.
- Solver calls: 0; OpenDSS calls: 0.

## Blocking evidence

- `FAIL_AIDC_P_LABEL`: observed IT-power coverage ends before the frozen validation/evaluation windows, and the supplied PUE README does not resolve the `ts` timezone.
- `FAIL_AIDC_JOINT_LABEL_ALIGNMENT`: P uses NLR ESIF PUE while G/W use NLR Kestrel Slurm, with no source-backed identity proving one synchronized operational target axis.
- Required action: create a prospective scientific re-freeze with a source-backed aligned P/G/W authority, or explicitly approve a reduced-target contract under a new authority ID.

## Known limitations

C4-C12 were intentionally not executed because the frozen handoff requires C2 PASS before the proposed model and downstream optimization evidence. The existing historical rolling-control implementation remains unchanged.
"""
    (output / "CODEX_DAYAHEAD_AIDC_JOINT_IMPLEMENTATION_REPORT.md").write_text(report, encoding="utf-8")
    return lineage_audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = materialize(args.preflight, args.authority, args.output_dir)
    print(json.dumps({"status": result["status"], "failures": result["failures"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
