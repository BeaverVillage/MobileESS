"""Finish requested diagnostics from saved readbacks; never repair science inputs."""
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, reference, write_json, write_parquet
from dayahead.v40d_actual.preflight import verify_protected


def link(path, text):
    return f"[{text}](<{Path(path).resolve().as_posix()}>)"


def main():
    root = REPO / "dayahead/artifacts/v40d_actual_realized_replay"
    out = root / "power_scale_parity/2025-05-01"
    service_root = root / "service_equivalence/2025-05-01"
    power = read(out / "V40D_POWER_SCALE_PARITY_AUDIT.json")
    service = read(service_root / "V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json")
    adapter = read(power["feeder_asset_refs"]["runtime_adapter"]["path"])
    multiplicity = {}
    members = {}
    for row in adapter["loads"]:
        for phase in row["phases"]:
            key = (row["bus"].lower(), int(phase))
            multiplicity[key] = multiplicity.get(key, 0) + 1
            members.setdefault(key, []).append(row["load_name"])
    duplicates = [{"bus": bus, "phase": "ABC"[phase-1], "application_count": count, "load_objects": members[bus, phase]}
                  for (bus, phase), count in sorted(multiplicity.items()) if count != 1]
    audits = []
    for namespace, model_namespace in (("Fresh", "Planning"), ("Actual", "Actual")):
        with np.load(out / model_namespace / "INDEPENDENT_BUS_PHASE_BACKGROUND_PV.npz") as z:
            buses = list(z["bus_ids"])
            p = z["background_P_kw"]; q = z["background_Q_kvar"]; pv = z["PV_P_kw"]
        dup_p = np.zeros(96); dup_q = np.zeros(96)
        for (bus, phase), count in multiplicity.items():
            dup_p += (count - 1) * p[:, buses.index(bus), phase-1]
            dup_q += (count - 1) * q[:, buses.index(bus), phase-1]
        for case in ("B0", "B1", "B2", "B3"):
            f = pd.read_parquet(out / namespace / case / "OPENDSS_COMPONENTS_96.parquet")
            expected_p = p.sum(axis=(1, 2))
            expected_q = q.sum(axis=(1, 2))
            rp = f.background_P_kw.to_numpy(); rq = f.background_Q_kvar.to_numpy()
            errors = {"P_duplication_explanation_max_error_kw": float(np.max(abs(rp - expected_p - dup_p))),
                      "Q_duplication_explanation_max_error_kvar": float(np.max(abs(rq - expected_q - dup_q)))}
            assert max(errors.values()) < 1e-8
            net_intended = expected_p - pv.sum(axis=(1, 2)) + f.AIDC_P_kw + f.MESS_P_kw
            rows = pd.DataFrame({"slot": range(96), "intended_background_P_kw": expected_p,
                                 "OpenDSS_background_P_kw": rp, "background_P_excess_kw": rp - expected_p,
                                 "predicted_shared_phase_duplicate_P_kw": dup_p,
                                 "intended_background_Q_kvar": expected_q, "OpenDSS_background_Q_kvar": rq,
                                 "background_Q_excess_kvar": rq - expected_q,
                                 "predicted_shared_phase_duplicate_Q_kvar": dup_q,
                                 "intended_net_P_kw": net_intended, "OpenDSS_net_P_kw": f.P_net_kw,
                                 "net_P_input_conservation_error_kw": f.P_net_kw - net_intended})
            write_parquet(out / namespace / case / "BACKGROUND_DUPLICATION_AND_NET_CONSERVATION.parquet", rows)
            rows.to_csv(out / namespace / case / "BACKGROUND_DUPLICATION_AND_NET_CONSERVATION.csv", index=False, encoding="utf-8-sig", float_format="%.17g")
            audits.append({"namespace": namespace, "case": case, **errors,
                           "duplicated_background_P_max_kw": float((rp - expected_p).max()),
                           "duplicated_background_Q_max_kvar": float((rq - expected_q).max()),
                           "duplicated_background_energy_kWh": float((rp - expected_p).sum() * .25),
                           "intended_background_max_kw": float(expected_p.max()), "OpenDSS_background_max_kw": float(rp.max())})
    power["background_mapping_defect"] = {"classification": "IMPLEMENTATION_DEFECT", "shared_bus_phase_rows": duplicates,
                                         "case_audits": audits, "source": reference(REPO / "dayahead/v28r2/opendss_mapping.py"),
                                         "function": "apply_trajectory_slot", "mechanism": "The inverse mapping sums aggregated bus-phase background into every load sharing each phase. Bus 65/76 phase contributions are applied twice.",
                                         "corrective_science_or_frozen_artifact_change_performed": False}
    mapping = pd.read_parquet(out / "AIDC_SPATIAL_BINDING.parquet")
    key_fields = ["PCC_bus", "phase_connection", "load_object_name", "OpenDSS_bus_name", "site_ordering_index", "mapping_source_SHA", "service_mapping_source_SHA"]
    checks = []
    for (case, site), group in mapping.groupby(["case", "AIDC_site_id"]):
        assert set(group.namespace) == {"Planning", "Fresh", "Actual"}
        assert all(group[k].nunique() == 1 for k in key_fields)
        checks.append({"case": case, "site": site, "Planning_Fresh_Actual_exact_equal": True})
    spatial = {"AIDC_SPATIAL_BINDING_FORENSIC": "PASS", "site_count": 12, "sites_times_cases": len(checks),
               "site_order_change_count": 0, "site_bus_change_count": 0, "phase_change_count": 0,
               "AIDC_PQ_readback_exact_mismatch_count": 0,
               "same_exogenous_checks": power["same_exogenous_pair_audits"],
               "same_job_runtime_B0_B1_exact": service["same_realized_runtime_each_job"],
               "PENDING_start_plus_runtime_identity_failure_count": sum(c["PENDING_end_exact_identity_failure_count"] for c in service["cases"]),
               "historical_absolute_end_combined_with_shifted_start_count": 0,
               "mapping_checks": checks, "mapping_table": reference(out / "AIDC_SPATIAL_BINDING.parquet"),
               "input_delta_table": reference(out / "B0_B1_ALL_OPENDSS_INPUT_DIFFERENCES.parquet"),
               "site_PQ_delta_table": reference(out / "B0_B1_AIDC_SITE_DELTA_PQ.parquet"),
               "power_scale_audit_PASS": False, "scientific_performance_interpretation_authorized": False}
    write_json(out / "V40D_AIDC_SPATIAL_BINDING_FORENSIC.json", spatial)
    power["AIDC_SPATIAL_BINDING_FORENSIC"] = "PASS"
    power["overall_forensic_classification"] = "A. IMPLEMENTATION_DEFECT"
    power["service_axis_classification"] = "C. HORIZON_BOUNDARY_REDISTRIBUTION"
    power["D_GENUINE_OUT_OF_SAMPLE_AIDC_DEGRADATION_conclusion"] = "NOT_AUTHORIZED_NOT_ESTABLISHED"
    power["PV_REQUESTED_698_APPLIED_BOUNDARY_MATCH"] = "FAIL"
    power["PV_NOMINAL_698_FROZEN_ALLOCATION_PARITY"] = "PASS"
    power["NATIVE_GENERATOR_BIT_EXACT_READBACK"] = "FAIL"
    power["NATIVE_GENERATOR_READBACK_MAX_ERROR_KW_KVAR"] = max(c["component_setpoint_max_error_kw_kvar"] for c in power["cases"])
    power["SOURCE_TERMINAL_POWER_vs_SETPOINT_POWER_note"] = "Component net is setpoint conservation. Source terminal power also includes network losses, capacitor injections and native voltage-dependent load behavior; those are not omitted from OpenDSS."
    write_json(out / "V40D_POWER_SCALE_PARITY_AUDIT.json", power)
    write_json(root / "V40D_POWER_SCALE_PARITY_AUDIT.json", power)
    gate = {"overall_forensic_classification": "A. IMPLEMENTATION_DEFECT", "POWER_SCALE_PARITY": "FAIL", "BACKGROUND_SCALE_PARITY": "FAIL",
            "ACTUAL_SERVICE_EQUIVALENCE": "PASS", "service_axis_classification": "C. HORIZON_BOUNDARY_REDISTRIBUTION",
            "AIDC_SPATIAL_BINDING_FORENSIC": "PASS", "scientific_performance_interpretation_authorized": False,
            "FULL_CAMPAIGN_AUTHORIZED": False, "UNASSIGNED_spillover_blocked_cases": 44,
            "SMOKE_execution_checks_do_not_override_this_science_gate": True,
            "audit": reference(out / "V40D_POWER_SCALE_PARITY_AUDIT.json")}
    write_json(root / "CURRENT_SCIENCE_INTERPRETATION_GATE.json", gate)
    case = {(r["namespace"], r["case"]): r for r in power["cases"]}
    s = {r["case"]: r for r in service["cases"]}
    rows = [
        ["alpha_grid", "0.7481417265421424", "동일·1회", "동일·1회", "PASS"],
        ["PV nominal / 적용 후 unit-profile kW", "698.000002861 / 522.202927267", "동일", "동일", "동결 경로 PASS; 적용 후 698 요구 FAIL"],
        ["regional demand source / unit", "AEMO D-1 forecast / MW", "같은 forecast / MW", "AEMO observed / MW", "PASS"],
        ["regional PV source / unit", "AEMO D-1 forecast / MW", "같은 forecast / MW", "AEMO measurement / MW", "PASS"],
        ["gross-background formula", "G (아래 정의)", "G + bus 65/76 중복", "G + bus 65/76 중복", "FAIL"],
        ["background total max kW", "2353.029588", "2610.787295", "2618.612461 (계약값 2358.887607)", "FAIL"],
        ["PV actual May-01 max kW", "320.738595", "320.738595", "327.947863", "PASS: 시간 프로파일 차이"],
        ["AIDC max aggregate IT kW", "406.775994", "406.775994", "B0/B2 312.567481; B1/B3 357.480842", "PASS: 같은 변환식"],
        ["C1 application count / extra 1.30", "1 / 0", "1 / 0", "1 / 0", "PASS"],
        ["MESS P unit / rating", "kW / 550", "동일", "동일", "PASS"],
        ["MESS Q unit / S rating", "kvar / 700 kVA", "동일", "동일", "PASS"],
        ["MESS battery / initial energy", "1200 / 760 kWh", "동일", "동일", "PASS"],
    ]
    table = ["| Quantity | Planning | Fresh | Actual | PASS/FAIL |", "|---|---|---|---|---|"] + ["| " + " | ".join(r) + " |" for r in rows]
    metric_names = [("작업 수", "job_count"), ("전체 realized runtime 합 (s)", "sum_realized_runtime_seconds"),
                    ("전체 service GPU-h", "full_population_service_GPU_hours"), ("pre-D00 실행 GPU-h", "pre_D00_GPU_hours"),
                    ("D-day 실행 GPU-h (초 단위)", "Dday_GPU_hours"), ("D-day GPU-slot-h (전력 계산용)", "Dday_GPU_slot_hours"),
                    ("post-H remaining GPU-h", "postH_GPU_hours"), ("H까지 완료 작업", "completed_jobs_by_H"), ("H 미완료 작업", "unfinished_jobs_at_H"),
                    ("H backlog GPU-h (remaining의 부분집합)", "backlog_GPU_hours_at_H"), ("D-day IT energy kWh", "Dday_IT_energy_kWh"),
                    ("D-day PCC energy kWh", "Dday_PCC_energy_kWh"), ("평균 시작 지연 s (아래 분모)", "actual_start_delay_mean_seconds_assigned_pending_including_postH"),
                    ("최대 시작 지연 s", "actual_start_delay_max_seconds_assigned_pending_including_postH"),
                    ("시작 지연 집계 작업 수", "actual_start_delay_denominator"), ("D00 경계 통과 작업", "crosses_D00_job_count"),
                    ("H 경계 통과 작업", "crosses_H_job_count"), ("경계 통과 unique 작업", "boundary_crossing_unique_job_count")]
    service_table = ["| Quantity | B0 | B1 |", "|---|---:|---:|"]
    for title, k in metric_names:
        service_table.append(f"| {title} | {s['B0'][k]:,.6f} | {s['B1'][k]:,.6f} |")
    text = [
        "# May-01 Power / Service / Spatial Forensic",
        "전체 판정은 **A. IMPLEMENTATION_DEFECT**이다. 별도 서비스 보존 판정은 **PASS / C. HORIZON_BOUNDARY_REDISTRIBUTION**이다. 현재 rho를 D. GENUINE_OUT_OF_SAMPLE_AIDC_DEGRADATION으로 해석하지 않는다. FULL_CAMPAIGN_AUTHORIZED=False이며 UNASSIGNED spillover 44 cases도 계속 차단한다.",
        "배경 부하 생성은 독립 계산과 P/Q/PV 모두 error=0이다. 그러나 OpenDSS load 매핑에서 bus 65와 76의 A/B/C를 각각 두 번 합산한다. s65a/b/c, s76a/b/c의 겹치는 phase에 대해 이미 합산한 bus-phase 값을 다시 각 load에 넣기 때문이다. Actual 추가 배경 P 최대 259.724854 kW, Fresh 최대 258.875387 kW. 아래 96-slot 표는 이 초과량이 해당 6개 bus-phase의 중복량과 일치함을 P/Q 각각 검증한다.",
        link(REPO / "dayahead/v28r2/opendss_mapping.py", "결함 위치: apply_trajectory_slot") + "; " + link(out / "Actual/B0/BACKGROUND_DUPLICATION_AND_NET_CONSERVATION.csv", "Actual B0 96-slot 중복/순입력 보존") + ".",
        "Fresh·Actual 각각 4 cases를 원래 frozen 입력으로 다시 실행했다. 모든 8개 결과의 전압·전류·손실·native control 배열이 기존 결과와 bit-exact 일치했다. 따라서 관찰기가 만든 오차가 아니라 기존 결과에 포함된 결함이다. 원래 Planning/Fresh/Actual artifact는 변경하지 않았다.",
        "\n".join(table),
        "G = alpha_grid × [operational_MW × 3490 / 7100.2615 + rooftop_PV_MW / 4021.226 × 698.000002861023]. 지역 gross demand는 operational + rooftop PV이며, 두 지역량은 각자의 frozen engineering normalization으로 feeder에 투영된다. PV는 gross에 가산한 뒤 한 번 차감한다. PV_DOUBLE_COUNTING=NO. alpha 누락/중복은 없고, 발견된 중복은 bus-phase→load 배경 부하 매핑이다.",
        "698 kW는 원래 PV spatial allocation의 alpha 적용 전 값이다(파일의 float 합 698.000002861023). 동결 계약은 PV에도 alpha를 적용하여 unit-profile 가용전력은 522.202927266866 kW이다. 698을 적용 후 경계 값으로 읽으면 요청 조건과 불일치하므로 strict PV gate는 FAIL로 보존했다. 세 namespace의 nominal PV 기준과 적용 경로 자체는 같다. 별도 PV inverter nameplate로 해석하지 않았다.",
        "입력 setpoint↔native generator getter에는 최대 1.1368683772161603e-13 kW/kvar의 부동소수점 차이도 존재한다. 사용자 exact gate를 임의의 tolerance로 바꾸지 않고 FAIL을 기록했다. AIDC load P/Q readback은 전 site/slot에서 exact 일치한다. 모든 readback component 합의 net 보존은 exact이지만, **의도한 background 합과 readback 사이의 물리적 보존은 FAIL**이다.",
        "전류/전압 해석을 수행하는 Planning은 coefficient model이며 별도 OpenDSS namespace가 아니다. 표의 Planning background는 그 frozen 입력 합성 계약을 독립 복원한 값이다. Fresh의 component 입력은 accepted DA trajectory를 OpenDSS에서 readback한 값이다. Planning AC anchor도 동일 매핑 결함을 포함했는지에 대한 과거 생성 경로 전체 재감사는 이 보고서의 확정 주장에 포함하지 않는다.",
        "## Service-equivalence / horizon boundary",
        "\n".join(service_table),
        "전체 realized runtime은 두 case 모두 75,775,583 s, 전체 service 35,639.253611 GPU-h이다. 요청 GPU·job_uid·job별 runtime은 exact 일치한다. pre-D00에는 RUNNING의 issue 이전 관측 이력도 포함해 전체 runtime과 같은 분모를 사용했다. UNASSIGNED post-H 작업 508개(B0)는 execution start/end를 만들지 않고 backlog로 계상한다. backlog는 post-H remaining의 부분집합이므로 두 값을 더하지 않는다.",
        "Delta_Dday_GPU_h=+3310.2741666666666; Delta_postH_GPU_h=-3310.2741666666666; Delta_pre_D00_GPU_h=0. 전체 서비스 보존 오차는 job별 0 s이다. GPU 슬롯 점유량 차이 3332.5 GPU-h와 실제 서비스 차이의 22.2258333333334 GPU-h는 15분 점유 집계와 초 단위 실행의 차이다.",
        "시작 지연 평균은 실행을 복원한 assigned PENDING 전체 기준: B0 887개, B1 1395개(일부 H 이후 시작 포함). H 이전 시작 작업만의 평균/최대는 B0 1.014656/900 s(887개), B1 559.854015/21600 s(1233개)이다. 모든 executed PENDING(B0 887, B1 1395)의 actual_end=actual_start+realized_runtime은 slot 표현에서 exact 일치했다. historical absolute end를 shifted start와 조합한 실패는 0이다.",
        link(service_root / "B0_B1_PAIRED_JOB_LEDGER.csv", "1,649 jobs B0/B1 paired ledger") + "; " + link(service_root / "V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json", "전체 4-case 서비스 감사") + ".",
        "## AIDC spatial binding / input delta",
        "AIDC01–12의 index 0–11, load.idc_idc01–12, idc_idc01_pcc–12_pcc.1.2.3, A/B/C 및 mapping source SHA는 Planning/Fresh/Actual 모두 일치한다. 12×96×8 AIDC P/Q readback 모두 exact 일치한다. C1=1회, 추가 1.30=0, 기존 202.750769230769 MW facility scale를 운영 전력으로 사용한 경로=0이다.",
        "B0/B1 background P/Q·PV·weather·topology·ratings·regulator/capacitor 96 slots는 exact identical이다. 전체 OpenDSS input difference 중 AIDC P/Q 외 nonzero row=0이다. B2/B3는 AIDC+MESS 외 nonzero row=0이다. 이 비교의 성공은 공통 background 중복 결함을 상쇄하거나 승인하지 않는다.",
        link(out / "AIDC_SPATIAL_BINDING.csv", "Planning/Fresh/Actual site별 매핑 표") + "; " + link(out / "B0_B1_ALL_OPENDSS_INPUT_DIFFERENCES.parquet", "전체 element input delta") + "; " + link(out / "B0_B1_AIDC_SITE_DELTA_PQ.parquet", "AIDC site×slot delta P/Q") + ".",
        "POWER_SCALE_PARITY=FAIL; BACKGROUND_SCALE_PARITY=FAIL; PV_SCALE_PARITY=strict FAIL(위 boundary 구분); AIDC_SCALE_PARITY=PASS; MESS_SCALE_PARITY=PASS; PV_DOUBLE_COUNTING=NO. 전체 판정 A, 서비스 축 C이며 D는 미확정이다. 원본 과학 코드/동결 결과 수정, 목적함수 재최적화, full campaign은 실행하지 않았다.",
    ]
    report = root / "V40D_POWER_SERVICE_SPATIAL_FORENSIC_REPORT.md"
    report.write_text("\n\n".join(text) + "\n", encoding="utf-8")
    final_guard = verify_protected(REPO, root)
    assert final_guard["status"] == "PASS"
    write_json(out / "FINAL_PROTECTED_RECHECK.json", final_guard)
    print({"report": str(report), "overall": "A. IMPLEMENTATION_DEFECT", "service": "C. HORIZON_BOUNDARY_REDISTRIBUTION", "protected": final_guard["changed_count"], "duplicates": duplicates, "duplication": audits[:2]}, flush=True)


if __name__ == "__main__":
    main()
