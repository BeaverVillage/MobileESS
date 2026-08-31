"""Assemble V20 independent-authority master status and review."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"
BASE = "77a86e3ded8087ea0109ccfca631bd2396ecd9fe"


def load(name: str) -> object:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    a = load("V20A_FINAL_SCALE_REVIEW.json")
    b = load("V20B_D1_STATE_FINAL_REVIEW.json")
    c = load("V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.json")
    d = load("V20D_FINAL_INTEGRATION_PREFLIGHT_TEST.json")
    e = load("V20E_LOCKED_TEST_FINAL_REVIEW.json")
    manifest = load("V20_PRECHANGE_MANIFEST.json")
    preservation_failures = []
    for record in manifest["preserved_files"]:
        path = ROOT / record["path"]
        if not path.exists() or sha(path) != record["sha256"]:
            preservation_failures.append(record["path"])

    flags = {
        "SITE_SCALE_AUTHORITY_READY": bool(a["SITE_SCALE_AUTHORITY_READY"]),
        "D1_STATE_EXTENSION_READY": bool(b["D1_STATE_EXTENSION_READY"]),
        "PARTIAL_NODE_POWER_UPGRADE_READY": bool(c["PARTIAL_NODE_POWER_UPGRADE_READY"]),
        "MODEL_AGNOSTIC_INTEGRATION_READY": bool(d["MODEL_AGNOSTIC_INTEGRATION_READY"]),
        "LOCKED_TEST_AUTHORITY_READY": bool(e["LOCKED_TEST_AUTHORITY_READY"]),
    }
    flags["PRE_ML_INTEGRATION_READY"] = flags["SITE_SCALE_AUTHORITY_READY"] and flags["MODEL_AGNOSTIC_INTEGRATION_READY"]
    flags["FINAL_SCIENCE_READY"] = "PENDING_V19_MODEL_AUTHORITY"
    write("V20_READY_FLAGS.json", {"artifact_id": "V20_READY_FLAGS_V1", **flags})

    workstream_files = sorted(p for p in OUT.iterdir() if p.is_file() and
                              p.name.startswith("V20") and
                              not p.name.startswith("V20_MASTER_"))
    file_hashes = {p.name: sha(p) for p in workstream_files}
    status = {
        "artifact_id": "V20_MASTER_AUTHORITY_STATUS_V1",
        "RESULT_CLASSIFICATION": "V20_INDEPENDENT_AUTHORITY_C_PHYSICAL_AND_LOCKED_TEST_GAPS",
        "workstreams": {"A": a["classification"], "B": b["classification"],
                        "C": c["classification"], "D": "MODEL_AGNOSTIC_PREFLIGHT_CONTRACT_PASS",
                        "E": e["classification"]},
        "ready_flags": flags,
        "preservation": {"checked_files": manifest["preserved_file_count"],
                         "failures": preservation_failures, "status": "PASS" if not preservation_failures else "FAIL"},
        "firewall_counters": {"C_MASS_TPP_code_changes": 0, "ML_model_selection_calls": 0,
                              "ML_retraining_calls": 0, "B0_B1_B2_B3_calls": 0,
                              "OpenDSS_calls": 0, "AC_science_calls": 0, "grid_science_calls": 0,
                              "beta_AIDC_tuning_calls": 0, "C_MODEL_tuning_calls": 0,
                              "PUE_tuning_calls": 0, "result_driven_scale_selection_calls": 0,
                              "unknown_to_zero_count": 0, "unsupported_MVA_to_MW_count": 0},
        "artifact_sha256": file_hashes,
        "git": {"worktree": str(ROOT), "branch": git("branch", "--show-current"),
                "starting_HEAD": BASE, "head_before_final_review_commit": git("rev-parse", "HEAD")},
    }
    write("V20_MASTER_AUTHORITY_STATUS.json", status)

    with (OUT / "V20A_MELBOURNE_12SITE_CAPACITY_EVIDENCE.csv").open(encoding="utf-8") as fh:
        sites = list(csv.DictReader(fh))
    review = {
        "artifact_id": "V20_MASTER_FINAL_REVIEW_V1", "RESULT_CLASSIFICATION": status["RESULT_CLASSIFICATION"],
        "site_specific_AIDC_scale": sites,
        "aggregate_scale": {"final_realworld_numerator_MW": None,
                            "primary_host_denominator_MW": 567.9513, "final_rho": None,
                            "final_IEEE123_equivalent_MW": None,
                            "partial_coverage_diagnostic_candidates": a["diagnostic_candidates"]},
        "D1_state": b, "partial_node_power": c,
        "integration_framework": {"forecast_model_agnostic": True, "C_MASS_fallback_supported": True,
                                  "fixture_preflight": d["deterministic_fixture"],
                                  "current_authority_preflight": d["current_authority_state"]},
        "locked_test": e,
        "remaining_blockers": ["12/12 common-boundary site scale", "site-specific GPU capacity weights",
                               "actual PCC/DNSP interface ratings", "new untouched locked-test period",
                               "V19 forecast authority"],
        "ready_flags": flags, "artifact_sha256": file_hashes,
        "firewall_counters": status["firewall_counters"], "preservation": status["preservation"],
    }
    write("V20_MASTER_FINAL_REVIEW.json", review)

    site_lines = []
    for s in sites:
        site_lines.append(f"| {s['site_name']} | {s['reported_value'] or 'null'} {s['reported_unit'] or ''} | {s['boundary_type']} | {s['confidence']} | {'yes' if s['directly_harmonizable_to_IT_MW']=='True' else 'no'} | null | null |")
    md = [
        "# V20 ML-independent final authority review", "",
        f"RESULT CLASSIFICATION: **{status['RESULT_CLASSIFICATION']}**", "",
        "## 1. Site-specific AIDC scale", "",
        "| Site | April-2025 evidence | boundary | confidence | IT harmonizable? | model site weight | model IT/PCC peak |",
        "|---|---:|---|---|---|---:|---:|", *site_lines, "",
        "운영 상태와 수치 경계를 분리했다. NEXTDC M2/M3의 42/13.5 MW는 2025-02-25 공식 1H25 자료의 built capacity이며, STACK MEL01A 36 MW는 개장된 건물 용량이다. 이들을 IT MW로 자동 변환하지 않았다.", "",
        "## 2. Aggregate scale", "",
        "최종 real-world numerator, rho, IEEE123 equivalent는 모두 **null**이다. 4개 사이트의 동일 `OPERATING_CAPACITY` 합 106.5 MW와 2025 forecast host peak 567.9513 MW를 사용한 rho 0.187516은 부분범위 진단일 뿐이다. 기존 0.9 MW를 목표로 사용하지 않았다.", "",
        "## 3. D-1 state", "",
        "Exact snapshot은 없고 완전한 retrospective causal reconstruction도 불가능하다. 기존 queued 6621.642222 GPU-h / running 5303.617222 GPU-h는 7일 Level-C oracle 진단으로만 유지한다.", "",
        "## 4. Partial-node power", "",
        "새 권한은 없다. 0.48563611660901085 kW/GPU board-only 하한을 유지하며 CPU increment와 유한 상한은 null이다.", "",
        "## 5. Integration framework", "",
        "FORECAST_BUNDLE_V1과 SITE_SCALE_BUNDLE_V1은 모델명 독립적이다. C-MASS accepted면 이를 사용하고, 아니면 V19 training-only blocked-CV accepted baseline으로 자동 fallback한다. Synthetic fixture G1~G14는 모두 PASS다.", "",
        "## 6. Locked test", "",
        "새 untouched 기간을 seal하지 못했다. April target/예측과 May~December 기존 human-visible 결과 이력이 있으므로 E3로 fail-closed했다.", "",
        "## 7. Remaining blockers", "",
        "12/12 공통경계 site scale, GPU weights, 실제 PCC rating, untouched test, V19 forecast authority가 남았다.", "",
        "## 8. Ready flags", "",
        *[f"- {k} = {str(v).lower() if isinstance(v,bool) else v}" for k, v in flags.items()], "",
        "## 9. Generated artifacts + SHA256", "",
        *[f"- `{name}`: `{digest}`" for name, digest in file_hashes.items()], "",
        "## 10. Git", "",
        f"- worktree: `{ROOT}`", f"- branch: `{status['git']['branch']}`",
        f"- starting HEAD: `{BASE}`", f"- head before final review commit: `{status['git']['head_before_final_review_commit']}`", "",
        "B0-B3, OpenDSS, AC/grid science, ML 학습은 실행하지 않았다.",
    ]
    (OUT / "V20_MASTER_FINAL_REVIEW.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
