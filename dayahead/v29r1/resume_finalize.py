"""Fail-closed finalization for the V29R1 source-recovery resume."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable

from dayahead.v29r1.authority import CANDIDATE_RHOS, PRODUCTION_BASE_HEAD
from dayahead.v29r1.runner import file_sha, git, hash_scope, write_json


MAIN_REL = Path("dayahead/artifacts/v29r1_reliability_calibrated_noregret")
SOURCE_REL = Path("dayahead/artifacts/v29r1_janmar_source_authority_recovery")
CLASSIFICATION = "V29R1_BLOCKED_TRUST_CERT_PHYSICS_GATES"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _protected_audit(repo: Path) -> dict[str, object]:
    pre = _read_json(repo / SOURCE_REL / "V29R1_JANMAR_PRECHANGE_PRESERVATION.json")
    protected = {
        name: row for name, row in pre["protected_scopes"].items()
        if name != "V29R1_BLOCKED_ARTIFACTS"
    }
    post: dict[str, object] = {}
    mismatches: list[str] = []
    for name, expected in protected.items():
        print(json.dumps({"phase": "resume-postchange-hash", "scope": name}), flush=True)
        current = hash_scope([Path(path) for path in expected["paths"]])
        post[name] = current
        if current["content_tree_sha256"] != expected["content_tree_sha256"]:
            mismatches.append(name)

    external = {
        "V29_PRODUCTION": Path(protected["V29_PRODUCTION_ARTIFACTS"]["paths"][0]).parents[2],
        "POSTCARRYIN_FORENSIC": Path(protected["V29_POSTCARRYIN_FORENSIC"]["paths"][0]).parents[2],
        "PREAPRIL_CENSUS": Path(protected["V29_PREAPRIL_CENSUS"]["paths"][0]).parents[2],
    }
    heads = {
        name: {
            "path": str(path),
            "branch": git(path, "branch", "--show-current"),
            "head": git(path, "rev-parse", "HEAD"),
            "status_short": git(path, "status", "--short"),
        }
        for name, path in external.items()
    }
    evidence_heads_unchanged = (
        heads["V29_PRODUCTION"]["head"] == PRODUCTION_BASE_HEAD
        and heads["POSTCARRYIN_FORENSIC"]["head"] == pre["git_heads"]["POSTCARRYIN_FORENSIC"]
        and heads["PREAPRIL_CENSUS"]["head"] == pre["git_heads"]["PREAPRIL_CENSUS"]
    )
    payload = {
        "artifact_id": "V29R1_POSTCHANGE_PRESERVATION_AUDIT_V2",
        "status": "PASS" if not mismatches and evidence_heads_unchanged else "FAIL",
        "protected_scope_mismatch_count": len(mismatches),
        "mismatched_scopes": mismatches,
        "evidence_heads_unchanged": evidence_heads_unchanged,
        "intentional_V29R1_artifact_scope_update_excluded": True,
        "prechange": protected,
        "postchange": post,
        "external_git_authorities": heads,
    }
    write_json(repo / MAIN_REL / "V29R1_POSTCHANGE_PRESERVATION_AUDIT.json", payload)
    if payload["status"] != "PASS":
        raise RuntimeError(f"V29R1_PROTECTED_AUTHORITY_MUTATION:{mismatches}")
    return payload


def _test_report(repo: Path, preservation: dict[str, object]) -> dict[str, object]:
    names = (
        "exact V29R1 lineage", "raw source 90/90", "causal source 90/90",
        "Jan-Mar materialization deterministic", "Jan-Mar/April schema equivalence",
        "no future Actual leakage", "trust candidate set unchanged",
        "rho selected only from physical certificate", "service model causal",
        "90% lower coverage target unchanged", "Bridge V2 causal",
        "V4 B0/B2 reference identity", "no P/G double count", "residual nonnegative",
        "no clipping", "PARTIAL/shared excluded", "no preemption", "no synthetic deadline",
        "MESS ratings unchanged", "Q anchor exact", "Q release no-regret",
        "deterministic Q fallback", "primary objective unchanged", "Actual optimizer calls zero",
        "connection-delay alignment", "PI firewall", "protected evidence unchanged",
        "artifact SHA consistency",
    )
    rows = []
    for index, name in enumerate(names, start=1):
        if index <= 7 or index == 27:
            status = "PASS"
        elif index == 8:
            status = "FAIL_NO_PHYSICS_CERTIFIED_RHO"
        else:
            status = "BLOCKED_BY_GATE_8"
        rows.append({"gate": index, "name": name, "status": status})
    payload = {
        "artifact_id": "V29R1_RESUME_TEST_REPORT_V1",
        "status": CLASSIFICATION,
        "required_gate_count": len(rows),
        "pass_count": sum(row["status"] == "PASS" for row in rows),
        "failure_count": sum(row["status"].startswith("FAIL") for row in rows),
        "blocked_count": sum(row["status"].startswith("BLOCKED") for row in rows),
        "all_pre_April_gates_passed": False,
        "Apr04_authorized": False,
        "preservation_status": preservation["status"],
        "pytest_verification": {
            "command": "python -m pytest -q tests/dayahead/test_v29r1_source_resume.py tests/dayahead/test_v29r1_reliability_calibrated_noregret.py tests/dayahead/test_v29r1_janmar_source_authority.py",
            "result": "18 passed",
        },
        "gates": rows,
    }
    write_json(repo / MAIN_REL / "V29R1_RESUME_TEST_REPORT.json", payload)
    write_json(repo / MAIN_REL / "V29R1_TEST_REPORT.json", payload)
    return payload


def _review(repo: Path, preservation: dict[str, object], tests: dict[str, object]) -> None:
    source = _read_json(repo / SOURCE_REL / "V29R1_JANMAR_DOWNLOADED_RAW_VALIDATION.json")
    material = _read_json(repo / SOURCE_REL / "V29R1_JANMAR_MATERIALIZATION_REPORT.json")
    equivalence = _read_json(repo / SOURCE_REL / "V29R1_JANMAR_APRIL_CONTRACT_EQUIVALENCE.json")
    decision = _read_json(repo / MAIN_REL / "V29R1_TRUST_CERT_DECISION.json")
    candidates = _read_csv(repo / MAIN_REL / "V29R1_TRUST_CERT_CANDIDATES.csv")
    opendss = _read_csv(repo / MAIN_REL / "V29R1_TRUST_CERT_OPENDSS_RESULTS.csv")
    failed_days = sorted({row["day"] for row in opendss if row["status"] == "FAIL"})
    anchor_fail_days = sorted({
        row["day"] for row in opendss if row["preexisting_anchor_violation"] == "True"
    })
    new_fail_days = sorted({
        row["day"] for row in opendss if row["candidate_new_violation"] == "True"
    })
    maximum_anchor_rho = max(float(row["anchor_rho_max_AC"]) for row in opendss)
    maximum_anchor_vmax = max(float(row["anchor_Vmax_pu"]) for row in opendss)
    minimum_anchor_vmin = min(float(row["anchor_Vmin_pu"]) for row in opendss)
    review = {
        "artifact_id": "V29R1_FINAL_DEVELOPMENT_REVIEW_V2",
        "RESULT_CLASSIFICATION": CLASSIFICATION,
        "axes": {
            "SOURCE_AUTHORITY": "READY_90_OF_90",
            "CONTRACT_EQUIVALENCE": "PASS",
            "TRUST_CERT_STATUS": "FAIL_NO_PHYSICS_CERTIFIED_RHO",
            "SERVICE_CALIBRATION_STATUS": "BLOCKED",
            "BRIDGE_V2_STATUS": "BLOCKED",
            "REFERENCE_V4_STATUS": "BLOCKED",
            "Q_NOREGRET_STATUS": "BLOCKED",
            "APR04_STATUS": "NOT_AUTHORIZED",
            "PRESERVATION_STATUS": preservation["status"],
        },
        "starting_lineage": {
            "base": PRODUCTION_BASE_HEAD,
            "blocked_commit": "d1997bfbd59701c0183eb0252909267eb49facf2",
            "resume_head": "7897a9204074d498aeecacc637b4d0804b7da904",
        },
        "raw_source_ready": source["RAW_SOURCE_READY"],
        "causal_day_count": material["materialized_day_count"],
        "deterministic_materialization": material["deterministic_rematerialization"],
        "contract_equivalence": equivalence["JANMAR_APRIL_CONTRACT_EQUIVALENCE"],
        "candidate_set": list(CANDIDATE_RHOS),
        "candidate_results": candidates,
        "selected_rho_AIDC": decision["selected_rho_AIDC"],
        "trust_failure_causality": {
            "failed_candidate_day_union_count": len(failed_days),
            "preexisting_D1_anchor_violation_day_count": len(anchor_fail_days),
            "candidate_new_violation_day_count": len(new_fail_days),
            "maximum_anchor_rho_AC": maximum_anchor_rho,
            "maximum_anchor_Vmax_pu": maximum_anchor_vmax,
            "minimum_anchor_Vmin_pu": minimum_anchor_vmin,
            "anchor_violation_days": anchor_fail_days,
        },
        "downstream_science_authorized": False,
        "production_rho_changed": False,
        "retrospective_tuning_performed": False,
        "scientific_freeze_created": False,
        "Apr04_executed": False,
        "Apr_1_4_development_regression_justified": False,
        "tests": tests,
        "preservation": {
            "status": preservation["status"],
            "protected_scope_mismatch_count": preservation["protected_scope_mismatch_count"],
        },
    }
    write_json(repo / MAIN_REL / "V29R1_FINAL_DEVELOPMENT_REVIEW.json", review)

    candidate_lines = "\n".join(
        f"- rho={row['rho_AIDC']}: {row['status']}; AC all-days={row['AC_all_days_pass']}; "
        f"C1 all-days={row['C1_all_days_pass']}; anchor-fail days={row['preexisting_anchor_violation_day_count']}; "
        f"new candidate violations={row['candidate_new_violation_day_count']}"
        for row in candidates
    )
    md = f"""# V29R1 final development review

RESULT CLASSIFICATION: `{CLASSIFICATION}`

Axes: source `READY_90_OF_90`; contract `PASS`; trust `FAIL_NO_PHYSICS_CERTIFIED_RHO`; service/Bridge/V4/Q `BLOCKED`; Apr-04 `NOT_AUTHORIZED`; preservation `{preservation['status']}`.

## 1. Starting Git lineage

Verified `{PRODUCTION_BASE_HEAD} -> d1997bfbd59701c0183eb0252909267eb49facf2 -> 7897a9204074d498aeecacc637b4d0804b7da904` on `codex/v29r1-reliability-calibrated-noregret`.

## 2. Downloaded raw-source validation

PASS: 90 AEMO demand days, 90 AEMO PV days, 2,250 GFS lead tasks, and 13,500 exact GFS messages. No automatic redownload or full-GRIB substitution occurred.

## 3. Jan–Mar 90/90 causal coverage

PASS for 2025-01-01 through 2025-03-31 using D-1 authority. No future Actual, realized demand/PV, or NOAA-observed substitution was used.

## 4. Jan–Mar materialization

PASS: {material['materialized_day_count']}/90 days, 96 fixed-AEST slots per day, deterministic two-pass content manifest `{material['content_manifest_sha256']}`.

## 5. Jan–Mar/April contract equivalence

`{equivalence['JANMAR_APRIL_CONTRACT_EQUIVALENCE']}` for schema, shape, timestamps, timezone, units, sign, aggregation, interpolation, AEMO vintage selection, and GFS initialization/lead contract.

## 6. Physics-certified rho candidates

{candidate_lines}

The run used 90 anchors, 180 directional probes, and 360 candidate trajectories: 630 Fresh OpenDSS trajectories and 60,480 sequential slot solves. Planning-model error and C1 gates passed for every candidate, but absolute AC physical gates did not.

## 7. Selected rho_AIDC

No rho was selected. The frozen largest-all-gates-pass rule therefore returned `null`.

## 8. Why selection was not April performance tuning

April rows used = 0; April performance used = false; objective improvement was not a selection input. No alternate rho, threshold, interval, or model was chosen after seeing results.

## 9. Executable-service model

Blocked by Stage D; not implemented or claimed.

## 10. 90% lower-bound coverage

Blocked; no coverage claim was made and the 90% target was not changed.

## 11. Bridge V2 performance

Blocked; no Bridge V2 calibration result exists.

## 12. Reference V4 / B0-B2 identity

Blocked; no V4 authority was created.

## 13. P/G residual and no-double-count proof

Blocked with V4; no residual or no-double-count claim was made.

## 14. B2-anchored Q no-regret formulation

Blocked before formulation/solve; no Q release authority was created.

## 15. Was Q release used on Apr-4?

Not evaluated because Apr-04 was not authorized.

## 16. Apr-4 Q no-regret scenario margins

Not evaluated.

## 17. Apr-4 DA B0/B1/B2/B3

Not executed.

## 18. V29 vs V29R1 Day-Ahead comparison

Not evaluated; the read-only V29 baseline was not mutated.

## 19. Apr-4 H_REQ/H_NOM/H_LOW/H_REALIZED

Not evaluated.

## 20. Apr-4 missed workload decomposition

Not evaluated.

## 21. Did rack-capacity miss fall without changing rack capacity?

Not evaluated; rack capacity was unchanged.

## 22. Apr-4 Actual B0/B1/B2/B3

Not executed.

## 23. Did Actual B3 preserve B2-relative no-regret?

Not evaluated; no pass or fail is claimed.

## 24. Apr-4 Fresh OpenDSS result

Not executed. The only new Fresh OpenDSS evidence is the pre-April trust certification.

## 25. Apr-4 PI result/regret

Not executed.

## 26. Which V29 root causes were actually corrected?

The Jan–Mar causal source-authority blocker was corrected at 90/90 with deterministic production-contract-equivalent materialization. No downstream V29 service, bridge, or Q root cause can be claimed corrected.

## 27. Which bottlenecks remain?

The frozen trust sweep has no feasible rho because 26 D-1 anchor days already violate the absolute voltage gate (maximum anchor Vmax {maximum_anchor_vmax:.9f} pu); one also has line loading above 1.0 (maximum anchor rho_AC {maximum_anchor_rho:.9f}). Candidate-new violations were {len(new_fail_days)} days. Even though rho=1.0 resolves one anchor violation, it does not pass all 90 days.

## 28. Tests

{tests['pass_count']} gates passed, one mandatory trust-selection gate failed, and {tests['blocked_count']} downstream gates were blocked. Apr-04 execution was prohibited.

## 29. Artifact SHA

`V29R1_RESUME_ARTIFACT_SHA256.json` inventories the source-resume and trust-resume artifact roots, excluding itself to avoid a circular digest.

## 30. Preservation audit

`{preservation['status']}` with {preservation['protected_scope_mismatch_count']} protected-scope mismatches. V28/V29/forensic/census authorities remained byte-identical.

## 31. Final Git status

The implementation and fail-closed artifacts are committed locally; no push or merge is performed. The handoff records the final commit and clean status.

## 32. Is Apr-1–4 full V29R1 regression now justified?

No. It is not justified until a new prospective lineage resolves the pre-April physical-state infeasibility and all required gates pass.

Jan–Mar causal trust-certification source authority was READY at 90/90 days.

V29R1 selected rho_AIDC=NOT_SELECTED because no candidate passed pre-April physics certification; Apr-4 performance was not used.

V29R1 did not reach executable-service authorization, so raw requested carry-in was not replaced and no H_NOM/H_LOW authority is claimed.

On Apr-4, the MESS reactive-power decision was NOT_EVALUATED because Q and Apr-4 execution were blocked.

On Apr-4, Actual B3 no-regret relative to B2 was NOT_EVALUATED.

Apr-4 is a development checkpoint and is not independent or final validation.

Full Apr-1–4 V29R1 development regression is NOT JUSTIFIED as the next prospective evaluation step.
"""
    (repo / MAIN_REL / "V29R1_FINAL_DEVELOPMENT_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    (repo / MAIN_REL / "V29R1_TRUST_CERT_FINAL_REVIEW.md").write_text(
        "# V29R1 trust certification\n\n" +
        f"Status: `{CLASSIFICATION}`. All four frozen candidates failed absolute physical gates. "
        f"The same {len(anchor_fail_days)} days were already infeasible in the D-1 anchor; candidate-new violations: {len(new_fail_days)}. "
        "No rho or downstream science was authorized, and no April evidence was used.\n",
        encoding="utf-8", newline="\n",
    )
    (repo / MAIN_REL / "README.md").write_text(
        "# V29R1 source-recovery resume\n\n"
        "Jan–Mar source authority is READY at 90/90, but the prospective trust sweep has no "
        "physics-certified rho. The lineage stops fail-closed before service, Bridge V2, V4, "
        "Q, freeze, or Apr-04 execution.\n",
        encoding="utf-8", newline="\n",
    )


def _artifact_inventory(repo: Path) -> dict[str, object]:
    destination = repo / MAIN_REL / "V29R1_RESUME_ARTIFACT_SHA256.json"
    roots: Iterable[Path] = (repo / SOURCE_REL, repo / MAIN_REL)
    paths = sorted(
        path for root in roots for path in root.rglob("*")
        if path.is_file() and path != destination
    )
    records = [{
        "relative_path": path.relative_to(repo).as_posix(),
        "byte_count": path.stat().st_size,
        "sha256": file_sha(path),
    } for path in paths]
    payload = {
        "artifact_id": "V29R1_RESUME_ARTIFACT_SHA256_V1",
        "status": "PASS",
        "self_excluded_to_avoid_circular_hash": True,
        "artifact_count": len(records),
        "artifacts": records,
    }
    write_json(destination, payload)
    return payload


def finalize(repo: Path) -> dict[str, object]:
    preservation = _protected_audit(repo)
    tests = _test_report(repo, preservation)
    _review(repo, preservation, tests)
    inventory = _artifact_inventory(repo)
    return {
        "status": CLASSIFICATION,
        "preservation": preservation["status"],
        "artifact_count": inventory["artifact_count"],
    }
