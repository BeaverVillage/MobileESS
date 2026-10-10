"""Combine historical control records with separately reproduced diagnostics."""
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parent
SOURCES = {}


def receipt(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), sha256=sha, bytes=path.stat().st_size)


def read(path, expected=None):
    actual = receipt(path)
    if expected:
        assert actual == expected
    SOURCES[actual["path"]] = actual
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(name, value):
    with (ROOT/name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def csv_write(name, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with (ROOT/name).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        writer.writerows(rows)


def main():
    base = read(ROOT/"CONTROL_AUDIT_RESULT.json")
    source_sha_ledger = read(ROOT/"CONTROL_SOURCE_SHA_LEDGER.json")
    original_b0_control = next(r for r in source_sha_ledger["sources"] if "DAY_20250501" in r["path"] and r["path"].endswith("RAW_CONTROL_LOG.json"))
    b0 = read(original_b0_control["path"], original_b0_control)
    factorial = read(ROOT/"FACTORIAL_REPLAY_STATUS.json")
    assert factorial["PASS"] is True and factorial["baseline_reproduced_bit_exact"] is True
    full = next(row for row in factorial["variants"] if row["variant"] == "FULL_PQ_REPLAY")
    assert all(full["original_AC_arrays_bit_identity"].values())
    b2_path = ROOT/"factorial/FULL_PQ_REPLAY/OBSERVED_CONTROL_ITERATIONS.json"
    b2 = read(b2_path)
    b1_proof = read(ROOT/"B1_MAY01_EXACT_CONTROL_REPLAY/B1_EXACT_CONTROL_REPLAY_RESULT.json")
    assert b1_proof["PASS"] is True and all(b1_proof["original_B1_arrays_bit_exact"].values())
    b1 = read(b1_proof["observed_controls"]["path"], b1_proof["observed_controls"])
    summaries, slots = [], []
    for arm, controls, evidence in (("B0",b0["slots"],"ORIGINAL_HISTORICAL_RAW_LOG"),
            ("B1",b1,"SEPARATE_EXACT_ORIGINAL_B1_REPLAY"), ("B2",b2,"SEPARATE_EXACT_FULL_PQ_B2_REPLAY")):
        assert len(controls) == 96 and all(row["control_actions_done"] for row in controls)
        for row in controls:
            assert row.get("REGCONTROL_AUTHORITY_SHA",row.get("control_parameters_sha")) == base["common_RegControl_settings_SHA"]
        totals = [row["convergence_iterations"] if arm == "B0" else row["electrical_iterations"] for row in controls]
        control_counts = [row["control_iterations"] for row in controls]
        maxcontrols = [base["arms"][arm]["max_control_iterations_configured"]] if arm == "B0" else sorted({row["configured_max_control_iterations"] for row in controls})
        maxiters = None if arm == "B0" else sorted({row["configured_max_electrical_iterations"] for row in controls})
        assert maxcontrols == [100]
        summaries.append(dict(arm=arm, evidence=evidence, max_control_iterations_observed=max(control_counts),
            max_Solution_Iterations_total_observed=max(totals), ControlActionsDone_true_slots=96,
            configured_MaxControlIterations=100, configured_MaxIterations=maxiters[0] if maxiters and len(maxiters)==1 else "NOT_RECORDED",
            settings_SHA=base["common_RegControl_settings_SHA"], historical_iteration_fields="RECORDED" if arm=="B0" else "ORIGINAL_LOG_UNKNOWN; separate exact replay measured",
            regulator_settings_changed=False, capacitor_settings_changed=False,
            original_AC_arrays_bit_exact=True if arm in ("B1","B2") else "ORIGINAL_ARRAYS_UNCHANGED"))
        for t,row in enumerate(controls):
            slots.append(dict(arm=arm, slot0=t, slot1=t+1, evidence=evidence,
                observed_ControlIterations=row["control_iterations"], observed_Solution_Iterations_total=totals[t],
                ControlActionsDone=row["control_actions_done"], configured_MaxControlIterations=100,
                configured_MaxIterations=row.get("configured_max_electrical_iterations","NOT_RECORDED"),
                settings_SHA=base["common_RegControl_settings_SHA"]))
    manifests = []
    for arm, path in (("B1",Path(r"D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01\dates\B1\2025-05-01\output\OPERATIONS\FRESH\fresh\OPENDSS_OUTPUT_MANIFEST.json")),
            ("B2",Path(r"D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01\output\OPERATIONS\FRESH\fresh\OPENDSS_OUTPUT_MANIFEST.json"))):
        manifest = read(path)
        array_receipt = receipt(path.with_name("OPENDSS_PHASE_ARRAYS.npz"))
        expected = manifest["files"]["OPENDSS_PHASE_ARRAYS.npz"]
        assert array_receipt["sha256"] == expected["sha256"] and array_receipt["bytes"] == expected["bytes"]
        SOURCES[array_receipt["path"]] = array_receipt
        manifests.append(dict(arm=arm, original_phase_manifest=receipt(path), original_phase_array=array_receipt, PASS=True))
    for row in source_sha_ledger["sources"]:
        assert receipt(row["path"]) == row
    for row in b1_proof["original_binding_receipts"] + b1_proof["unchanged_original_sources"] + b1_proof["identical_executed_sources"]:
        assert receipt(row["path"]) == row
    for row in factorial["source_binding_receipts"] + factorial["execution_sources"]:
        assert receipt(row["path"]) == row
    csv_write("CONTROL_MEASURED_ITERATION_SUMMARY.csv",summaries)
    csv_write("CONTROL_MEASURED_ITERATIONS_288_SLOTS.csv",slots)
    supplement = dict(schema="V42_CONTROL_DIAGNOSTIC_SUPPLEMENT_V1", PASS=True,
        common_control_implementation_defect_found=False,
        conclusion_scope="Exact settings, enabled seven RegControls, capacitor state, original Fresh source routing, bit-exact B1/B2 replay, and observed per-slot completion/iteration data. No proof that future days must be voltage-feasible.",
        summary=summaries, individual_RegControl_settings_SHA=base["individual_regulator_settings_SHA"],
        common_RegControl_settings_SHA=base["common_RegControl_settings_SHA"],
        original_voltage_limits=[.95,1.05], original_controls_settings_preserved=True,
        original_model_settings_and_tap_cap_arrays_preserved=True,
        original_phase_manifest_proofs=manifests,
        historical_missing_iteration_values_not_overwritten=True, counts_are_separate_diagnostic_measurements=True,
        iteration_semantics=dict(Solution_Iterations="Total iterations for the most recent solution including control passes; not the per-pass cap counter",
            MostIterationsDone="Maximum number required by any single control pass; not captured by these observe-only hooks",
            configured_MaxIterations=15,
            citation="https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.Iterations",
            second_citation="https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.MostIterationsDone"),
        source_receipts=list(SOURCES.values()), original_source_before_after_SHA_equal=True,
        supplemental_B1_new_AC_solves=96, supplemental_B1_Native_optimizer_calls=0,
        B2_full_pq_diagnostic_receipt=receipt(ROOT/"factorial/FULL_PQ_REPLAY/DIAGNOSTIC_RECEIPT.json"),
        B1_exact_control_replay_receipt=receipt(ROOT/"B1_MAY01_EXACT_CONTROL_REPLAY/B1_EXACT_CONTROL_REPLAY_RESULT.json"),
        supplemental_script=receipt(__file__))
    write("CONTROL_DIAGNOSTIC_SUPPLEMENT.json",supplement)
    report="""# B0/B1/B2 공통 제어 감사 최종 보충 근거

이번 감사 범위에서 공통 제어 구현 오류는 발견되지 않았습니다. 7개 RegControl의 개별·전체 설정 SHA, 활성 상태, 초기 탭, snapshot/static 모드, maxcontroliter=100 및 4개 고정 ON capacitor 상태가 동일합니다. B1/B2 독립 진단 재실행은 기존 전압·전류·탭·capacitor AC 배열 13개를 비트 단위로 재현했습니다. 기존 결과·탭·제어 설정·모델·전압 한계(0.95~1.05 pu)는 보존했습니다.

| Arm | 관측 근거 | 최대 ControlIterations | 최대 Solution.Iterations (합계) | 제어 완료 슬롯 | MaxControlIterations | MaxIterations |
|---|---|---:|---:|---:|---:|---:|
| B0 | 기존 RAW 로그 | 3 | 9 | 96/96 | 100 | 기존 로그 미기록 |
| B1 | 원본 AC 배열 정확 재현 진단 | 3 | 9 | 96/96 | 100 | 15 |
| B2 | 원본 Full P/Q 정확 재현 진단 | 5 | 17 | 96/96 | 100 | 15 |

원래 B1/B2 로그의 반복 횟수는 미기록 상태로 남겨두고, 새 관측치는 별도 진단 자료로 기록했습니다. Solution.Iterations는 제어 반복을 포함한 전체 합계이며, 개별 제어 pass의 한도 카운터와 다릅니다. 따라서 B2 합계 17을 MaxIterations=15 위반으로 해석하지 않습니다. 개별 pass 최대치는 MostIterationsDone API이며 이번 훅에서 별도로 측정하지 않았습니다. [OpenDSSDirect API](https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.Iterations), [MostIterationsDone](https://dss-extensions.org/OpenDSSDirect.py/opendssdirect.html#opendssdirect.Solution.ISolution.ISolution.MostIterationsDone)

B2와 B1의 탭 위치는 672개 관측 중 403개에서 다르고, 최대 차이는 0.025입니다. 모든 capacitor 상태는 동일합니다. 실제 P/Q가 다른 상태에서 활성 RegControl이 자체적으로 움직인 기록이며, 설정 SHA 변경은 없습니다. 자세한 7개 설정은 CONTROL_REGULATOR_SETTINGS_B0_B1_B2.csv, 슬롯별 탭·활성·capacitor 비교는 CONTROL_TAP_DIFFERENCES_B0_B1_B2.csv, 측정 반복 횟수는 CONTROL_MEASURED_ITERATIONS_288_SLOTS.csv에 있습니다.

B2 원본의 19개 과전압은 Actual 실패로 유지합니다. 이 결과는 이후 날짜의 전압 타당성을 보장하지 않으며, 공식 캠페인 결과를 변경하거나 통과로 승격하지 않습니다. B1 추가 진단은 96 AC 슬롯을 실행했고 optimizer/Native 호출은 0회입니다.
"""
    with (ROOT/"CONTROL_FINAL_REPORT.md").open("x",encoding="utf8",newline="\n") as stream:
        stream.write(report)
    write("CONTROL_FINAL_ARTIFACT_SHA_LEDGER.json",dict(schema="V42_CONTROL_FINAL_ARTIFACT_SHA_LEDGER_V1",
        files=[receipt(ROOT/name) for name in ("CONTROL_MEASURED_ITERATION_SUMMARY.csv", "CONTROL_MEASURED_ITERATIONS_288_SLOTS.csv",
            "CONTROL_DIAGNOSTIC_SUPPLEMENT.json", "CONTROL_FINAL_REPORT.md")], original_source_before_after_equal=True))
    print(json.dumps(dict(PASS=True, summary=summaries, original_array_receipts_verified=manifests,
        output=str(ROOT)), ensure_ascii=False))


if __name__ == "__main__":
    main()
