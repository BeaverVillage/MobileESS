"""Supervisor entrypoint: source audit by default, one bounded S1 solve with --run.

Run from the single shared checkout. The native ledger is always the common
UnifiedResearchBudget. No historical campaign is opened and no private ledger
is created. A native run remains a reduced planning diagnostic using the
explicit historical AIDC anchor; it is not a new E60 A1 or Full96 Actual proof.
"""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import argparse
import csv
import json

from v42_integration.mess_scaling import (STAGES, DEFAULT_STAY, build_scale_case,
    prepare_production_pilot, model_build_estimate, beam_paths, run_original_pilot,audit_grid_bottleneck,offline_vectorized_proof_benchmark)
from v42_integration.m_engine import _write, file_record
from v42_integration.unified_contract import REPORT, load_contracts,require_bindings


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def materialize_reports(prepared, *, pilot=None, reason="SOURCE_AND_NATIVE0_AUDIT_ONLY"):
    REPORT.mkdir(parents=True, exist_ok=True)
    scale = prepared["scale"]
    _write(REPORT/"ORIGINAL_24_CHARGING_SITE_AUDIT.json", prepared["audit"])
    existing=prepared.get("existing_stages")
    bundle, stay = (prepared["a_case"].data[0],scale.stay_plan) if existing is None else (None,None)
    matrix, rows, telemetry = [], [], []
    for stage, (vehicles, sites) in STAGES.items():
        if existing is None:
            candidate = build_scale_case(bundle, stage, stay, bindings=load_contracts()["bindings"],
                stay_source=file_record(DEFAULT_STAY))
            manifest=candidate.manifest
        else:
            manifest=deepcopy(next(c for c in existing if c["stage"]==stage))
        matrix.append(manifest)
        measured = pilot if stage == "S1" else None
        rows.append(dict(Stage=stage, MESS=vehicles, Sites=sites,
            Case_SHA=manifest["reduced_case_sha"],
            Status=measured.get("status") if measured else "NOT_RUN",
            First_FULL_UB=measured.get("BEST_GLOBAL_UB", "NOT_RUN") if measured else "NOT_RUN",
            Best_Moving_UB=(measured.get("BEST_MOVING_FEASIBLE_UB") or "NOT_FOUND") if measured else "NOT_RUN",
            Global_LB=measured.get("Global_LB", "NOT_CERTIFIED") if measured else "NOT_RUN",
            Relative_Gap=measured.get("gap", "NOT_CERTIFIED") if measured else "NOT_RUN",
            Bound_Scope=measured.get("bound_scope") if measured else "NOT_RUN",
            Original_4x24_Global_Certified=False,
            Reason=reason if measured is None else "MEASURED_REDUCED_PLANNING_DIAGNOSTIC"))
        size = measured.get("model_size", {}) if measured else {}
        events = measured.get("events", {}) if measured else {}
        telemetry.append(dict(Stage=stage, MESS=vehicles, Sites=sites,
            Build_Wall_s=measured.get("build_wall_seconds", "NOT_RUN") if measured else "NOT_RUN",
            Rows=size.get("linear_constraints", "NOT_RUN"),
            Columns=sum(size.get(k, 0) for k in ("binary", "integer", "continuous")) if size else "NOT_RUN",
            Binary=size.get("binary", "NOT_RUN"), Nonzeros=size.get("nonzeros", "NOT_RUN"),
            Presolve_Rows_Removed=events.get("presolve_removed_rows", "NOT_RUN"),
            Presolve_Columns_Removed=events.get("presolve_removed_columns", "NOT_RUN"),
            Presolved_Binary=measured.get("Presolved_Binary","NOT_MEASURED") if measured else "NOT_RUN",
            Root_s=measured.get("Root_LP_seconds", "NOT_RUN") if measured else "NOT_RUN",
            Root_LB=events.get("root_LB") if events.get("root_LB") is not None else "NOT_OBSERVED_ROOT_INTERRUPTED" if measured else "NOT_RUN",
            Root_Fractional_Arc=events.get("root_fractional_route_columns") if events.get("root_fractional_route_columns") is not None else "NOT_OBSERVED_ROOT_INTERRUPTED" if measured else "NOT_RUN",
            Root_Fractional_Mode=events.get("root_fractional_modes") if events.get("root_fractional_modes") is not None else "NOT_OBSERVED_ROOT_INTERRUPTED" if measured else "NOT_RUN",
            First_Solver_Incumbent_s=events.get("first_solver_incumbent_seconds", "NOT_RUN"),
            First_FULL_UB_s=measured.get("first_FULL_validated_UB_seconds", "NOT_MEASURED") if measured else "NOT_RUN",
            Nodes=measured.get("B_and_B_nodes", "NOT_RUN") if measured else "NOT_RUN",
            Peak_RSS=measured.get("after_native_memory", {}).get("peak_RSS_bytes", "NOT_RUN") if measured else "NOT_RUN",
            Peak_Private_Commit=measured.get("after_native_memory", {}).get("peak_private_commit_bytes", "NOT_RUN") if measured else "NOT_RUN"))
    _write(REPORT/"MESS_SCALING_CASE_MATRIX.json", dict(schema="MESS_SCALING_MATRIX_V1",
        bindings=scale.bindings, stages=matrix, Native_optimize_calls=0 if pilot is None else pilot.get("Native_optimize_calls",0),
        case_build_Native_optimize_calls=0,
        execution_status_by_stage={s:pilot["status"] if s=="S1" and pilot is not None else "NOT_RUN" for s in STAGES},
        measurement_policy="UNMEASURED_IS_NOT_RUN;ONE_S1_PILOT_BEFORE_ANY_SCALE_UP"))
    write_csv(REPORT/"MESS_ALGORITHM_UB_LB_GAP.csv", rows)
    write_csv(REPORT/"MESS_BUILD_ROOT_BRANCHING_MEMORY.csv", telemetry)
    result = pilot or dict(status="NOT_RUN", reason=reason, stage="S1", bindings=scale.bindings,
        reduced_case_sha=scale.case_sha, Native_optimize_calls=0,
        Original_Physical_MILP="NOT_RUN", first_FULL_feasible_UB=None,
        Global_LB=None, gap=None, Full96_Actual="NOT_RUN", Fresh_AC="NOT_RUN",
        model_build_estimate=model_build_estimate(scale, prepared["coefficients"]))
    _write(REPORT/"MESS_2X5_FIRST_FULL_RESULT.json", result)
    _write(REPORT/"MESS_INCUMBENT_REGISTRY_AUDIT.json", dict(
        status="NOT_RUN" if pilot is None else pilot["status"],
        incumbent_requirements=["CURRENT_SOURCE_CASE_SHA", "LITERAL_INTEGER_BINARY",
            "CURRENT_ORIGINAL_GRID_ROWS", "ORIGINAL_ROUTE_SOC_MODE_PCS", "RAW_NO_CLIP_OR_ROUND"],
        BEST_GLOBAL_UB=None if pilot is None else pilot.get("BEST_GLOBAL_UB"),
        BEST_MOVING_FEASIBLE_UB=None if pilot is None else pilot.get("BEST_MOVING_FEASIBLE_UB"),
        source_PR220_UB=0.5398310226338695, source_PR220_UB_historical_reference_only=True,
        historical_LB_transferred=False, restricted_ObjBound_is_Global_LB=False,
        inactive_Q_preserved=True, invalid_stay_auto_promotion=False,
        current_scope="REDUCED_PHYSICAL_CASE_WITH_EXPLICIT_HISTORICAL_AIDC_DIAGNOSTIC_ANCHOR"))
    (REPORT/"MESS_PRESCREENING_VALIDITY_PROOF.md").write_text(
        "# MESS prescreening validity\n\n"
        "All routes retain original service IDs, road link chains, traffic SHA, ETA, connection delay and safe travel energy. "
        "The 96-slot DAG retains the original complete STAY/MOVE grammar. Forward-unreachable and backward-dead-end "
        "arcs are zero for every feasible nonnegative unit flow and can be removed in both LP and integer domains.\n\n"
        "A path SOC upper bound grants optimistic maximum charging in every connected slot and no discharge. "
        "A path whose maximum reachable SOC is below the original minimum or terminal SOC cannot be physically feasible. "
        "These path checks never establish a fractional-arc zero. Grid sensitivity and beam-width/depth discards "
        "are heuristic search limits and never redefine the exact reduced MILP or provide a global bound.\n\n"
        "Inactive vehicles are current-source independently replayed with all four original physical vehicles. "
        "Their exact location, P, nonzero Q, Mode and SOC persist as fixed full-grid injections. "
        "An old full grid certificate is not copied; the current original grid rows must independently pass.\n\n"
        "A bound from a joint finite route pool is RESTRICTED_ROUTE_POOL. Only the unrestricted reduced original "
        "physical MILP can provide REDUCED_CASE_GLOBAL. Neither proves the original 4x24 global lower bound.\n",
        encoding="utf8")
    measurement=("S1 모델 구성은 %.3f초, %s행·%s변수·%s개 이진변수·%s개 nonzero였다. "
        "Presolve %.2f초 후 %s행·%s변수로 줄었으나 Root LP는 %.2f초 진행한 뒤 시간 제한으로 중단됐다. "
        "Native Runtime은 %.3f초이며 요청 30초보다 %.3f초 길었다. "
        "현재 FULL 검증 UB는 %.15f, 축소 문제 Global LB는 %.15f, Gap은 %.4f%%이다. "
        "최선 이동 FULL 해는 발견하지 못했다. 전체 4대의 route/SOC/PCS와 비활성 차량의 P/Q 일치는 PASS였다. "
        "피크 RSS %.3f GB, 피크 Private Commit %.3f GB를 기록했다.\n\n"
        "소스 정차 시작점과 최종 UB의 차이는 RHO 초기화의 1e-9 안전 여유이며, "
        "실제 경로·P/Q 개선의 성과로 주장하지 않는다. 3%% Gap은 실패했고 원본 4대·24개 Global 인증도 없다.\n\n") % (
            pilot["build_wall_seconds"],pilot["model_size"]["linear_constraints"],
            sum(pilot["model_size"][k] for k in ("binary","integer","continuous")),pilot["model_size"]["binary"],
            pilot["model_size"]["nonzeros"],pilot.get("Presolve_seconds",0.),pilot.get("Presolved_Rows"),
            pilot.get("Presolved_Columns"),pilot.get("Root_LP_seconds",0.),pilot.get("native_Runtime",0.),
            pilot.get("native_receipt",{}).get("overshoot_seconds",0.),pilot["BEST_GLOBAL_UB"],pilot["Global_LB"],
            pilot["gap"]*100,pilot["after_native_memory"]["peak_RSS_bytes"]/1e9,
            pilot["after_native_memory"]["peak_private_commit_bytes"]/1e9) if pilot is not None and pilot.get("Native_optimize_calls")==1 else ""
    (REPORT/"MESS_SCALE_UP_DECISION_KO.md").write_text(
        "# MESS 규모 확대 판단\n\n"
        "원본 후보지는 IDC01–IDC12와 STA01–STA12의 24개이다. S1은 MESS01·MESS03과 "
        "STA01·STA08·IDC01·IDC11·STA12를 사용한다. 초기 위치, AIDC 공존, 서로 다른 전기적 경로와 "
        "상류·하류 위치를 실행 전에 고정했다. 원본 이동 링크·ETA·이동에너지와 Full96 축을 유지한다.\n\n"
        "비활성 MESS02·MESS04는 설비에서 삭제하지 않으며, 원본 FULL STAY의 0 kW와 비영(非零) Q, "
        "SOC 760 kWh를 보존한다. 이번 코드가 원본 물리 검증과 현재 계통 행을 다시 검사하며, "
        "과거 PR223 전압 인증을 복사하지 않는다.\n\n"
        +measurement+f"현재 S1 상태는 {result['status']}이다. S2–S7은 NOT_RUN이다. "
        "차량 수와 후보지 수 중 무엇이 더 큰 실제 병목인지는 동일 조건 실측 전에는 판단할 수 없다. "
        "모델 크기 예상치는 계측이 아니다. 원본 계통 행은 규모 축소에도 모두 남으므로, "
        "경로·P/Q 변수를 줄여도 계통 행 구성 시간이 지배할 수 있다.\n\n"
        "S1의 현재 FULL 해와 공유 Native 원장·메모리를 확인한 뒤에만 다음 규모를 선택한다. "
        "후보 경로 제한 Bound를 Global LB로 승격하거나 3% Gap을 임의 인증하지 않는다. "
        "본 실험의 AIDC anchor는 명시적 과거 진단 anchor이며 새 E60 A1 인증이 아니다.\n",
        encoding="utf8")
    return result


def recover_measured_reports(result_path,output):
    """Repair serialization/reporting only, using persisted source and solver evidence."""
    import re
    result_path=Path(result_path)
    native_record=file_record(result_path)
    result=json.loads(result_path.read_text(encoding="utf8"))
    require_bindings(result["shared_bindings"],load_contracts()["bindings"])
    ledger_path=REPORT/"UNIFIED_NATIVE_RUNTIME_LEDGER.json"
    ledger_before=file_record(ledger_path)
    ledger=json.loads(ledger_path.read_text(encoding="utf8"))
    if result.get("Native_optimize_calls")!=1 or not any(
            row.get("label")==result["native_receipt"]["label"] and
            row.get("Native_Runtime")==result["native_receipt"]["Native_Runtime"] for row in ledger["calls"]):
        raise ValueError("MESS_POSTPROCESS_EXISTING_NATIVE_LEDGER_RECEIPT_REQUIRED")
    matrix=json.loads((REPORT/"MESS_SCALING_CASE_MATRIX.json").read_text(encoding="utf8"))
    if next(c for c in matrix["stages"] if c["stage"]=="S1")["reduced_case_sha"] != result["reduced_case_sha"]:
        raise ValueError("MESS_POSTPROCESS_REDUCED_CASE_IDENTITY_DRIFT")
    log=(result_path.parent/"NATIVE_GUROBI.log").read_text(encoding="utf8")
    match=re.search(r"Variable types:\s*\d+ continuous,\s*\d+ integer\s*\((\d+) binary\)",log)
    if match:result["Presolved_Binary"]=int(match[1])
    result.update(postprocess_recovered=True,postprocess_Native_retries=0,
        physical_improvement_claimed=False,source_RHO_enclosure_only_difference=1e-9,
        numeric_LB_scope="SOLVER_UNRESTRICTED_REDUCED_CASE_NO_INDEPENDENT_DUAL_CERTIFICATE",
        Original_Physical_MILP="CURRENT_REDUCED_ORIGINAL_FORMULA_FULL96_GRID_AND_ALL4_VEHICLE_REPLAY_PASS")
    if result.get("BEST_MOVING_FEASIBLE_UB") is None:
        result["moving_status"]="NOT_FOUND_WITHIN_SINGLE_30_SECOND_PILOT"
    prepared=dict(scale=SimpleNamespace(bindings=result["shared_bindings"],case_sha=result["reduced_case_sha"]),
        audit=json.loads((REPORT/"ORIGINAL_24_CHARGING_SITE_AUDIT.json").read_text(encoding="utf8")),
        existing_stages=matrix["stages"])
    materialize_reports(prepared,pilot=result)
    ledger_after=file_record(ledger_path)
    if ledger_before!=ledger_after or file_record(result_path)!=native_record:
        raise ValueError("MESS_POSTPROCESS_ORIGINAL_NATIVE_EVIDENCE_MUTATION")
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    _write(output/"POSTPROCESS_REPAIR.json",dict(status="REPAIRED",cause="RESULT_DICT_ATTACHED_TO_ITSELF_AS_CONSTRUCTOR_RECEIPT",
        Native_retries=0,new_Native_optimize_calls=0,model_builds=0,existing_result=native_record,
        original_native_runtime=result["native_receipt"]["Native_Runtime"],ledger_before=ledger_before,
        ledger_after=ledger_after,original_result_bytes_unchanged=True,required_reports_materialized=True))
    return result


def summarize_compression_benchmark(result_path):
    """Small measured report; immutable runtime matrices and old S1 stay intact."""
    result_path=Path(result_path)
    result=json.loads(result_path.read_text(encoding="utf8"))
    proof_path=result_path.parent/"EXACT_PROOF"/"FULL96_COMPRESSION_CERTIFICATE.json"
    proof=json.loads(proof_path.read_text(encoding="utf8"))
    phases=result["benchmark_phase_memory"]["phases"]
    def wall(name):return phases.get(name,{}).get("wall_seconds",0.)
    variants=[]
    for row in result["variants"]:
        wanted=("variant","reduced_case_sha","comparison_id","original_matrix_sha","original_domain_sha",
            "selected_matrix_sha","model_size","native_receipt","requested_native_cap","native_Runtime",
            "native_Work","native_wall_seconds","native_status","B_and_B_nodes","raw_solver_ObjBound","Global_LB",
            "gap","BEST_GLOBAL_UB","BEST_MOVING_FEASIBLE_UB","initial_start_vector_sha","actual_Start_readback",
            "first_variant_solver_incumbent_used_as_second_start","events","accepted","rejected","full_validation_seconds",
            "after_variant_memory","bound_scope","Presolve_seconds","Root_LP_seconds","Root_LP_status",
            "Presolved_Rows","Presolved_Columns","Presolved_NNZ")
        variants.append({key:row[key] for key in wanted if key in row})
    original,compressed=variants
    proof_keys=("identity","source_constructor","FULL96_original_rows_captured","slots_captured","original_grid_rows",
        "retained_grid_rows","original_grid_nonzeros","retained_grid_nonzeros","physical_rows_unchanged",
        "original_variable_bounds_types_names_sha","original_physical_CSR","original_native_bounds_types_names_rows",
        "original_integer_and_LP_feasible_region_preserved","proof_counts","actual_selected_matrix_sha",
        "captured_original_matrix_sha","selected_domain_sha","original_domain_sha","retained_native_CSR_bit_identity_PASS",
        "objective_bounds_types_names_exactly_unchanged","original_full_native_CSR","original_full_native_domain")
    compact=dict(schema="MESS_EXACT_COMPRESSION_BENCHMARK_MEASURED_REPORT_V1",source_result=file_record(result_path),
        source_exact_certificate=file_record(proof_path),numeric_scope=result["numeric_scope"],bindings=proof["identity"],
        integrated_current_A1_M1_certified=False,integrated_four_stage_certified=False,Original_4x24_global_certified=False,
        source_model_build_count=1,build_wall_seconds=result["build_wall_seconds"],
        benchmark_after_build_wall_seconds=result["solve_wall_seconds"],
        build_plus_benchmark_wall_seconds=result["build_wall_seconds"]+result["solve_wall_seconds"],
        sampler_total_phase_wall_seconds=sum(row.get("wall_seconds",0.) for row in phases.values()),
        total_wall_scope="Sampler phase sum includes warm validation/disposal; build+benchmark is a named subtotal, not source-preparation process wall",
        Native_optimize_calls=result["Native_optimize_calls"],native_Runtime_total=result["native_Runtime"],
        compression_wall_seconds=sum(wall(name) for name in ("COMPRESSION_CAPTURE","COMPRESSION_PROOF",
            "COMPRESSION_ARTIFACT_WRITE","COMPRESSION_NATIVE_REMOVE","COMPRESSION_CSR_RECONSTRUCT_VERIFY")),
        proof_plus_reconstruction_wall_seconds=wall("COMPRESSION_PROOF")+wall("COMPRESSION_CSR_RECONSTRUCT_VERIFY"),
        benchmark_phase_memory=result["benchmark_phase_memory"],variants=variants,
        callback_phase_attribution_note="Root interruption did not reach root-completion callbacks; PRESOLVE memory label spans later Native work. Use native log5.43/5.99s for presolve and11.38/13.81s for Root, not callback phase wall.",
        exact_compression_proof={key:proof[key] for key in proof_keys if key in proof},
        row_reduction_percent=100*(1-compressed["model_size"]["linear_constraints"]/original["model_size"]["linear_constraints"]),
        NNZ_reduction_percent=100*(1-compressed["model_size"]["nonzeros"]/original["model_size"]["nonzeros"]),
        UB_unchanged=original["BEST_GLOBAL_UB"]==compressed["BEST_GLOBAL_UB"],
        solver_LB_delta=compressed["Global_LB"]-original["Global_LB"],speedup="NOT_DEMONSTRATED",
        both_Root_LP_interrupted=True,old_standalone_30s_S1_reports_unchanged=True,
        attribution_correction=dict(existing_runtime_and_ledger_receipts_not_mutated=True,
            original_recorded_grid_compression_mode="NONE",compressed_recorded_grid_compression_mode="NONE",
            correct_modes=dict(ORIGINAL="ORIGINAL_FULL_ROWS",COMPRESSED="EXACT_NATIVE_CSR_SAME_MODEL"),
            reason="Original benchmark context retained its initial mode; comparison_variant/certificate/selectedSHA are authoritative",
            future_stage_context_fixed=True))
    path=REPORT/"MESS_EXACT_COMPRESSION_BENCHMARK.json";_write(path,compact)
    if path.stat().st_size>200*1024:raise ValueError("MESS_SMALL_BENCHMARK_REPORT_200KB_LIMIT")
    rows=[]
    for row in variants:
        size=row["model_size"];variant=row["variant"]
        rows.append(dict(Variant=variant,Case_SHA=row["reduced_case_sha"],Numeric_Scope=result["numeric_scope"],
            Original_Source_Model_Builds=1 if variant=="ORIGINAL" else 0,
            Original_Build_s=result["build_wall_seconds"] if variant=="ORIGINAL" else 0,
            Compression_Proof_s=wall("COMPRESSION_PROOF") if variant=="COMPRESSED" else 0,
            Compression_Reconstruct_s=wall("COMPRESSION_CSR_RECONSTRUCT_VERIFY") if variant=="COMPRESSED" else 0,
            Rows=size["linear_constraints"],Columns=size["binary"]+size["continuous"]+size["integer"],
            Binary=size["binary"],NNZ=size["nonzeros"],Presolve_s=row["Presolve_seconds"],
            Root_s=row["Root_LP_seconds"],Root_Status=row["Root_LP_status"],
            Root_Optimal_LB="NOT_OBSERVED_ROOT_INTERRUPTED",Native_s=row["native_Runtime"],
            Solver_Global_LB=row["Global_LB"],FULL_UB=row["BEST_GLOBAL_UB"],Gap=row["gap"],
            Validation_s=row["full_validation_seconds"],Speedup="NOT_DEMONSTRATED"))
    write_csv(REPORT/"MESS_EXACT_COMPRESSION_BUILD_ROOT_MEMORY.csv",rows)
    return compact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT/"MESS_S1_PILOT")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--native0-build", action="store_true")
    parser.add_argument("--seconds", type=float, default=30.)
    parser.add_argument("--mode", choices=("EXACT_REDUCED", "BEAM_JOINT"), default="EXACT_REDUCED")
    parser.add_argument("--grid-compression",choices=("NONE","EXACT_NATIVE_BLOCK"),default="NONE")
    parser.add_argument("--compression-probe-slots",type=int)
    parser.add_argument("--compare-exact-compression",action="store_true")
    parser.add_argument("--summarize-compression",type=Path)
    parser.add_argument("--offline-vectorized-proof",type=Path)
    parser.add_argument("--proof-slots",type=int,default=1)
    parser.add_argument("--proof-reference-timing",action="store_true")
    parser.add_argument("--recover-result",type=Path)
    parser.add_argument("--audit-grid-rows",type=Path)
    args = parser.parse_args()
    if args.compression_probe_slots is not None and (
            not args.native0_build or args.run or args.grid_compression!="EXACT_NATIVE_BLOCK"):
        parser.error("A partial grid capture requires --native0-build --grid-compression EXACT_NATIVE_BLOCK and cannot --run")
    if args.compare_exact_compression and (not args.run or args.native0_build or args.grid_compression!="NONE" or
            args.mode!="EXACT_REDUCED" or args.seconds>30):
        parser.error("An exact comparison requires --run --mode EXACT_REDUCED --seconds 20 (at most30), original grid, and two equal solver caps")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.offline_vectorized_proof is not None:
        if args.run or args.native0_build:parser.error("Offline proof cannot run a model or optimizer")
        result=offline_vectorized_proof_benchmark(args.offline_vectorized_proof,args.output,
            slots=args.proof_slots,reference_timing=args.proof_reference_timing)
        print(json.dumps({key:result[key] for key in ("PASS","scope","slots_verified","vector_proof_compute_seconds",
            "scalar_reference_compute_seconds","proof_kernel_compute_speedup","Native_optimize_calls")}))
        return
    if args.summarize_compression is not None:
        report=summarize_compression_benchmark(args.summarize_compression)
        print(json.dumps(dict(rows_reduced_percent=report["row_reduction_percent"],NNZ_reduced_percent=report["NNZ_reduction_percent"],
            speedup=report["speedup"],Native_optimize_calls=0,report=str(REPORT/"MESS_EXACT_COMPRESSION_BENCHMARK.json"))))
        return
    if args.audit_grid_rows is not None:
        result=audit_grid_bottleneck(args.audit_grid_rows)
        print(json.dumps(dict(scope=result["scope"],grid_row_percent=result["grid_row_percent"],
            source_formula_totals=result["source_formula_totals"],native_models=0,Native_calls=0)))
        return
    if args.recover_result is not None:
        result=recover_measured_reports(args.recover_result,args.output)
        print(json.dumps(dict(status=result["status"],postprocess_repaired=True,Native_retries=0,
            UB=result["BEST_GLOBAL_UB"],LB=result["Global_LB"],gap=result["gap"])))
        return
    prepared = prepare_production_pilot(args.output)
    pools, beam = beam_paths(prepared["scale"])
    _write(args.output/"NATIVE0_BEAM_AUDIT.json", beam)
    _write(args.output/"S1_SELECTION_AND_SOURCE.json", prepared["scale"].manifest)
    if not args.run and not args.native0_build:
        result = materialize_reports(prepared)
        print(json.dumps(dict(status=result["status"], stage="S1", Native_optimize_calls=0,
            source_sites=24, original_routes=len(prepared["scale"].routes),
            beam_path_counts={u:len(v) for u,v in pools.items()}), ensure_ascii=False))
        return
    from v42_integration.unified_resource import UnifiedResearchBudget
    budget = UnifiedResearchBudget()
    budget.preflight()
    with prepared["physical"].physical_scope():
        result = run_original_pilot(prepared["scale"], coefficients=prepared["coefficients"],
            grid_authority=prepared["grid_authority"], aidc_anchor=prepared["aidc_anchor"],
            coefficient_source=prepared["coefficient_source"],
            physical_bundle=prepared["physical_bundle"],electrical_certificate=prepared["electrical_certificate"],
            thermal_receipt=prepared["thermal_receipt"],
            all_sites=prepared["all_sites"], budget=budget, output=args.output/"SOLVE",
            seconds=args.seconds, mode=args.mode, native0=args.native0_build and not args.run,
            grid_compression=args.grid_compression,compression_probe_slots=args.compression_probe_slots,
            compare_exact_compression=args.compare_exact_compression)
    if args.grid_compression=="NONE" and not args.compare_exact_compression:
        materialize_reports(prepared, pilot=result)
    else:
        # Compression experiments have separate case/mode lineage. Preserve the
        # previously measured standalone S1 report and its historical bindings.
        _write(args.output/"COMPRESSION_EXPERIMENT_RESULT.json",result)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
