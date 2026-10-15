"""Compile real date-bound public A inputs for all May days, Native/AC zero."""
import argparse
import gc
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_integration import release_date_case as compiler
from v42_integration import release_initial_states as io


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(compiler.BASE / "RC02/DATE_CASES/COMPILE01"))
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("DATE_COMPILER_ATTEMPT_ALREADY_EXISTS_NO_OVERWRITE:" + str(output))
    output.mkdir(parents=True)
    import gurobipy as gp
    protected = [io.record(ROOT / path) for path in compiler.SOURCE13]
    own_sources = [io.record(ROOT / path) for path in ("v42_integration/release_date_case.py",
        "tools/prepare_v42_release_date_cases.py", "v42_integration/release_initial_states.py")]
    io.write_json(output / "EXECUTED_SOURCE.json", dict(Source13=protected, additive_compiler=own_sources))
    original_native = {name: getattr(gp.Model, name) for name in ("__init__", "optimize", "presolve", "computeIIS")}
    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append("MODEL_OR_NATIVE_ENTRYPOINT")
        raise RuntimeError("DATE_PUBLIC_INPUT_COMPILER_NATIVE_MODEL_BUILD_AND_SOLVES_FORBIDDEN")
    begun = time.perf_counter()
    rows = []
    try:
        for name in original_native:
            setattr(gp.Model, name, forbidden)
        for index in range(1, 32):
            day = f"2025-05-{index:02d}"
            start = time.perf_counter()
            row = dict(day=day, status="INPUT_UNAVAILABLE", Native_calls=0, native_model_builds=0, AC_solves=0,
                independent_date=True, previous_day_Actual_carry=False)
            try:
                folder = output / day / "CASE"
                context = compiler.compile_date_case(day, output=folder)
                compiler.require_date_case(context["manifest"], stage="A1")
                if context["production_case_verifier"] is not compiler.require_date_case:
                    raise ValueError("EXACT_PRODUCTION_DATE_CASE_VERIFIER_NOT_BOUND")
                audit = context["input_audit"]
                row.update(status="COMPILED_PUBLIC_NATIVE_INPUTS", case_folder=str(folder.resolve()),
                    manifest=io.record(folder / "D0_CASE_MANIFEST.json"), identity=context["manifest"]["identity"],
                    Source13_SHA=context["manifest"]["source_sha"], input_sha=audit["a_input_sha"],
                    running_UIDs=audit["running_UIDs"], pending_UIDs=audit["pending_UIDs"], running_GPU=audit["initial_running_GPU"],
                    native_jobs=len(context["data"][1]), source_legal_windows=True, slots=96,
                    native_internal_slots=[24, 120], original_full_domain="UNMATERIALIZED_COMPLETE_SOURCE_AUTHORIZED_BASIC",
                    unrestricted_migration="HOLD", P2_calls=0, Source13_exact=True,
                    same_day_original_physical_projection=True, lazy_A_M_factories_available=True,
                    lazy_factory_runtime_materialization="NOT_RUN", production_heavy_execution="NOT_RUN",
                    May01_saved_P1_case_exact_preserved=day == "2025-05-01")
                # Resume is verified on representative dates and May31 rather
                # than multiplying every input-generation I/O for no new case.
                if day in ("2025-05-01", "2025-05-02", "2025-05-10", "2025-05-12", "2025-05-31"):
                    reloaded = compiler.load_date_case(day, folder)
                    if reloaded["manifest"] != context["manifest"] or reloaded["input_audit"]["a_input_sha"] != audit["a_input_sha"]:
                        raise ValueError("REPRESENTATIVE_RESUME_RECOMPILE_DRIFT")
                    row["resume_input_byte_verification"] = "PASS"
                    del reloaded
                else:
                    row["resume_input_byte_verification"] = "SAME_IMPLEMENTATION_TESTED_ON_REPRESENTATIVE_DATES"
                del context
                gc.collect()
            except (OSError, ValueError, KeyError, RuntimeError) as error:
                row["missing_or_invalid_input_reasons"] = [str(error)]
            row["compile_and_audit_wall_seconds"] = time.perf_counter() - start
            io.write_json(output / day / "DATE_INPUT_STATUS.json", row)
            rows.append(row)
            print(day, row["status"], row.get("missing_or_invalid_input_reasons", []), flush=True)
    finally:
        for name, method in original_native.items():
            setattr(gp.Model, name, method)
    if attempts:
        raise ValueError("DATE_COMPILER_ENTERED_FORBIDDEN_MODEL_OR_NATIVE_BODY:" + str(attempts))
    if any(io.record(r["path"]) != r for r in protected + own_sources):
        raise ValueError("DATE_COMPILER_EXECUTED_SOURCE_BYTES_CHANGED")
    result = dict(schema="MAY31_INDEPENDENT_D0_PUBLIC_NATIVE_CASE_COMPILATION_V1", dates=rows,
        compiled=sum(r["status"] == "COMPILED_PUBLIC_NATIVE_INPUTS" for r in rows),
        unavailable=sum(r["status"] == "INPUT_UNAVAILABLE" for r in rows), Native_calls=0,
        native_model_builds=0, AC_solves=0, Actual_runs=0, P2_calls=0, forbidden_entry_attempts=attempts,
        original_Source13_bytes_preserved=True, saved_May01_A1_P1_case_unchanged=True,
        no_forecast_refit_or_correction=True, independent_Fresh_AC_still_required=True,
        production_solver_dispatch_certified=False, budget_approval_supplied=False,
        current_controller_and_full96_physical_PASS_transferred=False,
        wall_seconds=time.perf_counter() - begun)
    io.write_json(output / "MAY31_DATE_CASE_COMPILATION.json", result)
    lines = ["# 31일 독립 D0 Native 입력 컴파일", "",
        "Source13와 원본 수학 compiler를 수정하지 않고 공개 D0 초기 상태·동일 날짜 CC4·기존 11-SVR Forecast 계수를 날짜별로 연결했다. 원본 classify_d0_backlog/_compile_d0_known_data가 실제 96슬롯 입력을 생성했다. May01은 성공한 A1 P1의 manifest 전체 객체와 input fingerprint를 그대로 보존했다.", "",
        "| 날짜 | 결과 | Running UID | GPU | Pending UID | Native Job | Resume | 정확한 누락 사유 |", "|---|---|---:|---:|---:|---:|---|---|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(key, "")) for key in ("day", "status", "running_UIDs", "running_GPU", "pending_UIDs", "native_jobs", "resume_input_byte_verification"))
            + " | " + "; ".join(row.get("missing_or_invalid_input_reasons", [])) + " |")
    lines += ["", "Native Model 생성, domain materialization, Optimize/presolve/IIS, Actual 및 AC는 모두 실행하지 않았다. 별도 승인 예산과 단계별 Original FULL 수용을 통과해야 lazy 원본 A/M producer를 실행할 수 있다. 이 결과는 Solver 성공·전기적 실행 가능성·Full96·캠페인 실행 인증이 아니다.", "",
        "API: release_date_case.compile_date_case(day, output=...), load_date_case(day, output), require_date_case(manifest, stage=...). context.production_case_verifier는 임의 callback이 아닌 동일 exact source 함수다. Resume는 별도 임시 폴더에서 입력을 다시 컴파일하고 저장된 artifact와 byte equality를 확인하며 기존 입력을 덮어쓰지 않는다. 후속 stage checkpoint의 FULL/예산 수용은 Production executor가 담당한다.", "",
        "May03~31에 기존 B2 projection JSON이 없어도 동일 날짜 공인 ELECTRICAL_CERTIFICATE.outputs를 사용한 원래 physical-only merge를 생성했다. 계수 byte SHA, 원래 96축·60 controls·153 transformer current rows를 직접 검증했다. 오래된 지역 affine의 전역 비선형 안전성을 주장하지 않으며 Actual 후보 AC와 Fresh AC가 별도 필수다."]
    with (output / "DATE_CASE_COMPILATION_KO.md").open("x", encoding="utf8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    print("SUMMARY", result["compiled"], result["unavailable"], result["wall_seconds"], flush=True)


if __name__ == "__main__":
    main()
