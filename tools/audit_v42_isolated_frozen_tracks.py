"""Read-only PR223 M2 preservation and separate D0 A1 Native0 regeneration.

No production-source edit, optimization, presolve, IIS, controller or new MESS
algorithm. Regeneration writes only the explicitly isolated runtime directory.
"""
import argparse
from contextlib import contextmanager
from hashlib import sha256
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from time import perf_counter

import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record,vector_sha
from v42_integration.a_engine import digest

BASE=ROOT/"docs/v42_unified_aidc_mess_research_20261014"
OUT=BASE/"ISOLATED_UNKNOWN_C0_C1_20261015"
D0=BASE/"D0_STATE_CONDITIONED_PLANNING_20261015"
ORIGINAL=Path("D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3")
RUNTIME=ROOT/"runtime/ISOLATED_FROZEN_TRACKS"
REFERENCE="89b4ee6b63ca7847dd6f2cbd2720052f66949d39"
LEDGER=BASE/"UNIFIED_NATIVE_RUNTIME_LEDGER.json"


def read(path):
    path=Path(path);raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)


def write_new(path,document):
    if Path(path).exists():raise ValueError("ISOLATED_FROZEN_AUDIT_EVIDENCE_EXISTS:"+str(path))
    _write(path,document)


def pinned(path,sha):
    r=file_record(path)
    if r["sha256"]!=sha:raise ValueError("ISOLATED_ORIGINAL_BYTE_SHA_DRIFT:"+str(path))
    return r


@contextmanager
def prohibit_native():
    import gurobipy as gp
    methods={name:getattr(gp.Model,name) for name in ("optimize","presolve","computeIIS")};attempts=[]
    def forbidden(*args,**kwargs):
        attempts.append("FORBIDDEN_NATIVE_CALL");raise RuntimeError("ISOLATED_FROZEN_TRACKS_NATIVE0_ONLY")
    try:
        for name in methods:setattr(gp.Model,name,forbidden)
        yield attempts
    finally:
        for name,original in methods.items():setattr(gp.Model,name,original)


def phase_review(text):
    def nums(pattern):return [float(v) for v in re.findall(pattern,text)]
    return dict(Presolve_seconds=nums(r"Presolve time: ([\d.]+)s"),
        Root_Barrier_completion_cumulative_Native_seconds=nums(r"Barrier (?:performed [^\n]*? in |solved model in [^\n]*? and )([\d.]+) seconds"),
        interrupted_Root_relaxation_reported_seconds=nums(r"Root relaxation: time limit, .*? iterations, ([\d.]+) seconds"),
        Root_relaxation_completed=bool(re.search(r"Root relaxation: objective",text)),
        B_and_B_nodes=[int(v) for v in re.findall(r"Explored (\d+) nodes",text)],
        exclusive_barrier_duration=None,crossover="NOT_REACHED_IN_LOG",integer_solution_count=0,
        time_limit_is_infeasibility_proof=False,nested_solver_times_must_not_be_added=True,
        direct_infeasibility_log_evidence=bool(re.search(r"Model is infeasible|Infeasible model",text)),
        last_barrier_line=next((line.strip() for line in reversed(text.splitlines()) if re.match(r"\s+19\s+",line)),None))


def literal_box_contradictions(A,lower,upper,rhs,sense):
    """Necessary box checks with outward products and conservative sum error.

    Rows with nonfinite arithmetic remain unknown. Absence of a box-only
    contradiction proves neither LP nor MILP feasibility.
    """
    A=A.tocsr();lo=np.asarray(lower,dtype=float).copy();hi=np.asarray(upper,dtype=float).copy()
    lo[lo<=-1e99]=-np.inf;hi[hi>=1e99]=np.inf
    count=np.diff(A.indptr);eps=np.finfo(float).eps
    def bound(maximum):
        chosen=np.where(A.data>=0,hi[A.indices] if maximum else lo[A.indices],lo[A.indices] if maximum else hi[A.indices])
        with np.errstate(invalid="ignore",over="ignore"):
            product=A.data*chosen;product[A.data==0]=0.
            product=np.nextafter(product,np.inf if maximum else -np.inf)
            C=sparse.csr_matrix((product,A.indices,A.indptr),shape=A.shape)
            total=np.asarray(C.sum(axis=1)).ravel()
            C.data=np.abs(product);magnitude=np.asarray(C.sum(axis=1)).ravel()
            gamma=2.*count*eps/(1.-2.*count*eps)
            error=np.nextafter(gamma*np.nextafter(magnitude/(1.-count*eps),np.inf),np.inf)
            result=np.nextafter(total+error if maximum else total-error,np.inf if maximum else -np.inf)
        result[~np.isfinite(result)]=np.inf if maximum else -np.inf
        result[count==0]=0.
        return result
    minimum=bound(False);maximum=bound(True);b=np.asarray(rhs)
    bad=np.flatnonzero(((sense=="<")&(minimum>b))|((sense==">")&(maximum<b))|
        ((sense=="=")&((minimum>b)|(maximum<b))))
    return dict(variable_bound_contradictions=np.flatnonzero(lo>hi).tolist(),
        box_only_contradiction_rows=bad[:100].tolist(),box_only_contradiction_count=len(bad),
        no_box_contradiction_is_not_feasibility_proof=True,
        checked_rows=A.shape[0],nonfinite_enclosure_rows=int(np.count_nonzero(~np.isfinite(minimum)|~np.isfinite(maximum))))


def mess_audit():
    from v42_integration.coordinator import _full_m
    from v42_integration.mess_actual import consume_frozen_mess
    from v42_integration.mess_scaling import validate_stay_physics
    from v42_native.mess import Battery
    plan_path=ORIGINAL/"M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json"
    plan_record=pinned(plan_path,"72be8ee7c73024643bcce927eb2373c40872bc06fb9e9c9da98b6b6b84cb8656")
    repo=ROOT/"docs/v42_common_am_qos_integration/receipts/DDAY_V5_FINAL/DDAY_V5_B3_FINAL_ATTEMPT01/B3"
    repo_plan=pinned(repo/"M2/COMMON_M_PR222/FULL_MESS_PHYSICAL_ANCHOR.json",plan_record["sha256"])
    result=read(ORIGINAL/"M2/COMMON_M_PR222/M_STAGE_RESULT.json") if (ORIGINAL/"M2/COMMON_M_PR222/M_STAGE_RESULT.json").exists() else read(repo/"M2/COMMON_M_PR222/M_STAGE_RESULT.json.gz")
    plan=read(plan_path)
    if _full_m(result)!=plan:raise ValueError("PR223_M2_PHYSICAL_PLAN_RESULT_DRIFT")
    freeze_record=pinned(ORIGINAL/"PLANNING_FREEZE.json","098565139dbac38a11add42a6a3cfcd7c1ebafbd4a8e2461a58f6b9f39691ca3")
    freeze=read(freeze_record["path"])
    if freeze["MESS_plan"]!=plan or freeze["mess_anchor"]!=plan["plan_sha"]:raise ValueError("PR223_PLANNING_FREEZE_M2_MESS_DRIFT")
    replay=read(repo/"M2/COMMON_M_PR222/BEST_GLOBAL_INCUMBENT.REPLAY.json")
    original=read(repo/"MESS_ACTUAL_EXECUTION_RECEIPT.json")
    if not replay["PASS"] or replay["point_vector_sha256"]!=plan["point_vector_sha256"]:raise ValueError("PR223_M2_ORIGINAL_FULL_POINT_PRECONDITION")
    actual=consume_frozen_mess(plan,day_begin_seconds=freeze["actual_gate"]["day_begin_epoch_seconds"],original_full_validated=True)
    if any(actual[k]!=original[k] for k in ("plan_sha","commands","routes","moves")):
        raise ValueError("PR223_M2_LITERAL_EXECUTION_ARRAY_OR_CLOCK_DRIFT")
    native_path=Path("D:/v42_may_joint_repair_campaign_20261013/inputs/B2/2025-05-01/NATIVE_INPUT.json")
    native_record=pinned(native_path,"6b8de8c47cd6655dced630ed3fdf232fb1d96ad58a7c65d7c6533fae3d81f90a")
    native=read(native_path);route=read(repo/"M2/INPUT_AND_SOURCE_IDENTITY.json")["route_table"]
    pinned(route["path"],route["sha256"]);table=read(route["path"])
    physical=validate_stay_physics(plan,tuple(table["service_ids"]),[],Battery(**native["battery"]),native["initial_MESS_sites"])
    raw_record=pinned(replay["point_path"],replay["point_file_sha256"])
    with np.load(raw_record["path"],allow_pickle=False) as z:raw=z["point"].copy()
    if vector_sha(raw)!=plan["point_vector_sha256"]:raise ValueError("PR223_M2_RAW_POINT_VECTOR_DRIFT")
    sites=sorted(plan["P_by_site"]);units=sorted(plan["SOC"]);idc=[f"IDC{k:02d}" for k in range(1,13)]
    arrays=dict(service_sites=np.array(sites),P_by_site=np.array([plan["P_by_site"][s] for s in sites]).T,
        Q_by_site=np.array([plan["Q_by_site"][s] for s in sites]).T,
        aidc_sites=np.array([f"AIDC{k:02d}" for k in range(1,13)]),aidc_MESS_service_sites=np.array(idc),
        aidc_MESS_P=np.array([plan["P_by_site"][s] for s in idc]).T,
        aidc_MESS_Q=np.array([plan["Q_by_site"][s] for s in idc]).T,
        units=np.array(units),unit_P=np.array([plan["P_kW"][u] for u in units]),
        unit_Q=np.array([plan["Q_kvar"][u] for u in units]),SOC=np.array([plan["SOC"][u] for u in units]),
        Mode=np.array([plan["Mode"][u] for u in units]),routes=np.array([plan["routes"][u] for u in units]))
    array_path=RUNTIME/"MESS_FIXED_M2_ARRAYS.npz"
    if not array_path.exists():np.savez_compressed(array_path,**arrays)
    with np.load(array_path,allow_pickle=False) as z:
        if set(z.files)!=set(arrays) or any(not np.array_equal(z[k],v) for k,v in arrays.items()):
            raise ValueError("PR223_M2_FROZEN_CONSUMER_ARRAY_DRIFT")
    protected=["v42_integration/m_engine.py","v42_integration/m_candidates.py","v42_integration/mess_scaling.py",
        "v42_integration/mess_actual.py","v42_native/mess.py","v42_native/mess_domain.py",
        "v42_m1_research/check_ub.py","v42_common_mess","tools/time_decomposed_lb"]
    code_unchanged=subprocess.run(["git","diff","--quiet",REFERENCE,"--",*protected],cwd=ROOT).returncode==0
    if not code_unchanged:raise ValueError("ISOLATED_OFFICIAL_MESS_K48_CODE_DRIFT")
    preserved_arrays=OUT/"MESS_FIXED_M2_SOURCE_ARRAYS.npz"
    if not preserved_arrays.exists():shutil.copyfile(array_path,preserved_arrays)
    if file_record(preserved_arrays)["sha256"]!=file_record(array_path)["sha256"]:
        raise ValueError("PR223_PRESERVED_FIXED_MESS_ARRAY_BYTES_DRIFT")
    axes={f:{u:len(plan[f][u]) for u in sorted(plan[f])} for f in ("P_kW","Q_kvar","Mode","SOC_kWh","routes")}
    fingerprints={f:digest(plan[f]) for f in ("routes","P_by_site","Q_by_site","SOC","Mode","connection_site")}
    preservation=dict(status="PASS",scope="PR223_B3_M2_FIXED_VERIFIED_PLAN_ONLY_NOT_NEW_D0_OPTIMIZATION",
        plan=plan_record,repo_identical_plan=repo_plan,semantic_plan_sha=plan["plan_sha"],
        planning_freeze=freeze_record,source_native_input=native_record,route_source=route,
        plan_axes=axes,literal_field_fingerprints=fingerprints,all_96_frozen_commands_equal_to_PR223_execution=True,
        independent_current_original_route_SOC_PCS_Mode_STAY_replay=physical,
        original_FULL_certificate=file_record(repo/"M2/COMMON_M_PR222/BEST_GLOBAL_INCUMBENT.REPLAY.json"),
        original_Raw_point=raw_record,original_Raw_vector_sha_verified=True,
        Original_FULL_matrix_replay_this_audit="REUSED_PINNED_PR223_RECEIPT_NOT_RERUN",
        fixed_arrays=file_record(RUNTIME/"MESS_FIXED_M2_ARRAYS.npz"),
        preserved_fixed_arrays=file_record(preserved_arrays),
        AIDC_IDC_MESS_P_Q_arrays_zero=True,all_24_sites_including_nonzero_station_injections_preserved=True,
        C0_C1_fixed_plan_must_use_same_fingerprints=True,
        official_UB_algorithm="Adaptive Beam -> 4-MESS Joint MILP -> Original FULL -> Incumbent Registry",
        official_Global_LB_algorithm="K48 -> Certified same-case Global LB",official_algorithms_modified=False,
        code_baseline=REFERENCE,official_code_git_diff_empty=code_unchanged,
        new_Beam_K48_S1_DW_compression_native_experiments=0,Native_optimize_calls=0,
        old_S1_gap_and_original4x24_gap_not_combined=True,new_D0_M1_A2_M2="NOT_RUN",
        source_note="12 mapped IDC injections are zero, but four initial STA sites retain their literal P/Q. This is a fixed historical MESS condition, not zero MESS.")
    write_new(OUT/"MESS_OFFICIAL_ALGORITHM_PRESERVATION.json",preservation)
    return preservation


def metadata():
    pilot=read(D0/"A1_PILOT01/PILOT_RESULT.json");log_path=D0/"A1_PILOT01/SOLVE/NATIVE_SOLVER.log"
    result=read(D0/"A1_PILOT01/SOLVE/A_RESULT.json");phases=phase_review(log_path.read_text(encoding="utf8"))
    reference=read(D0/"FINAL_NATIVE0/EXACT_P1_MATRIX_DOMAIN_EQUIVALENCE.json")
    snapshot=read(D0/"FINAL_NATIVE0/D0_SOURCE_FREEZE.json")
    unchanged=[]
    for record in snapshot["files"]:
        actual=file_record(record["path"])
        if any(actual[k]!=record[k] for k in ("sha256","bytes")):raise ValueError("D0_FROZEN_SOURCE13_DRIFT")
        unchanged.append(actual)
    record=dict(status="METADATA_PASS_NATIVE0_REGENERATION_PENDING_ADMISSION",source_files=unchanged,
        pilot_result=file_record(D0/"A1_PILOT01/PILOT_RESULT.json"),pilot_log=file_record(log_path),
        latest_native0_reference=file_record(D0/"FINAL_NATIVE0/EXACT_P1_MATRIX_DOMAIN_EQUIVALENCE.json"),
        current_expected_binding=reference["current_binding"],current_expected_identity=reference["current_identity"],
        pilot_identity=pilot["identity"],pilot_stage_case_sha=pilot["stage_case_sha"],
        pilot_Native_Runtime=pilot["Native_used_seconds"],pilot_SolCount=0,pilot_not_infeasibility_proof=True,
        old_pilot_bound=0.08280107490283846,old_pilot_bound_transferred=False,
        phase_analysis=phases,prior_numerical_policy=result["numerical_policy"],
        direct_source_or_constraint_failure_evidence="NO_DIRECT_PROOF_FOUND_IN_SAVED_LOG;GLOBAL_FEASIBILITY_UNRESOLVED",
        strategy_review=dict(status="REVIEW_ONLY_NOT_EXECUTED",model_changes=False,
            keep_one_worker_one_thread=True,keep_original_P1_then_P2_then_M1_A2_M2=True,
            keep_all_source_physical_domains_objective_service_QoS_GPU_Power_CDF_Carry=True,
            proposed_first_run_Native_cap_seconds=120.,proposed_return_reserve_seconds=30.,
            minimum_cumulative_ceiling_without_overshoot_buffer_seconds=468.680999994278,
            minimum_additional_ceiling_without_overshoot_buffer_seconds=108.680999994278,
            recommended_cumulative_Native_ceiling_seconds=480.,recommended_additional_ceiling_seconds=120.,
            overshoot_buffer_beyond_120s_call_and_30s_return_seconds=11.319000005722046,
            current_25s_pilot_adapter_is_not_silently_extended=True,
            reason="25s requested/26.238s actual stopped before Root LP completion; an uninterrupted120s same-math P1 trial is a budget proposal, not a feasibility guarantee. Feasibility-focused MIPFocus1 can be reviewed after approval instead of the old bound-focused3; do not silently alter frozen policy.",
            actual_new_D0_A1_Native="HOLD_PENDING_ADDITIONAL_USER_BUDGET"),
        Native_calls=0)
    write_new(OUT/"D0_A1_EXISTING_PILOT_METADATA_REVIEW.json",record)
    return record


def regenerate():
    import psutil
    from v42_integration.d0_case import build_planning_inputs,require_case
    from v42_integration.d0_a_planning import build_d0_native_model
    from v42_integration.d0_resource import native_binding
    if psutil.virtual_memory().available<8*1024**3:raise RuntimeError("ISOLATED_D0_A1_NATIVE0_8GB_RAM_GATE")
    before=file_record(LEDGER);reference=read(D0/"FINAL_NATIVE0/EXACT_P1_MATRIX_DOMAIN_EQUIVALENCE.json")
    output=RUNTIME/"D0_A1_NATIVE0_AUDIT01";output.mkdir(parents=True,exist_ok=False)
    resources=dict(available_RAM_bytes=psutil.virtual_memory().available,Native_calls=0)
    _write(output/"RESOURCE_BEFORE.json",resources)
    began=perf_counter();built=None
    with prohibit_native() as attempts:
        try:
            context=build_planning_inputs(output=output/"CASE");case=context["make_a_case"]("A1",folder=output/"MODEL")
            require_case(context["manifest"])
            if psutil.virtual_memory().available<8*1024**3:raise RuntimeError("ISOLATED_D0_A1_PREMODEL_8GB_RAM_GATE")
            built=build_d0_native_model(case,build_admission=dict(status="PASS",operation="D0_A_NATIVE0_BUILD",case_sha=case.case_sha,concurrent_heavy_solver=False))
            import gurobipy as gp
            model=built[0];model.Params.Threads=1;model.setObjective(dict(built[2])["rho"],gp.GRB.MINIMIZE);model.update()
            binding=native_binding(model)
            if binding!=reference["current_binding"] or context["manifest"]["identity"]!=reference["current_identity"]:
                raise ValueError("ISOLATED_D0_A1_MATRIX_DOMAIN_CASE_IDENTITY_DRIFT")
            obj=np.asarray(model.getAttr("Obj"),dtype=float);names=list(model.getAttr("VarName"))
            nonzero=np.flatnonzero(obj)
            if len(nonzero)!=1 or names[int(nonzero[0])]!="rho_max" or obj[nonzero[0]]!=1. or model.ObjCon!=0.:
                raise ValueError("ISOLATED_D0_A1_EXACT_ORIGINAL_MIN_RHO_OBJECTIVE_DRIFT")
            objective=dict(coefficients_vector_sha=vector_sha(obj),constant=float(model.ObjCon),sense=int(model.ModelSense),
                nonzero_name="rho_max",nonzero_coefficient=1.)
            objective["objective_sha"]=digest(objective)
            box=literal_box_contradictions(model.getA().tocsr(),np.asarray(model.getAttr("LB")),np.asarray(model.getAttr("UB")),
                np.asarray(model.getAttr("RHS")),np.asarray(model.getAttr("Sense")))
            box["finite_row_enclosures"]=box["checked_rows"]-box["nonfinite_enclosure_rows"]
            if attempts or file_record(LEDGER)!=before:raise ValueError("ISOLATED_D0_A1_NATIVE0_LEDGER_OR_GUARD_CHANGED")
            require_case(context["manifest"])
            source_records=read(OUT/"D0_A1_EXISTING_PILOT_METADATA_REVIEW.json")["source_files"]
            for original in source_records:
                current=file_record(original["path"])
                if any(current[k]!=original[k] for k in ("sha256","bytes")):
                    raise ValueError("D0_FROZEN_SOURCE13_POSTBUILD_DRIFT")
            proof=dict(status="PASS",scope="IDENTICAL_FROZEN_D0_A1_P1_MATH_NATIVE0_ONLY_NOT_FULL_FEASIBLE",
                source_case_identity=context["manifest"]["identity"],stage_case_sha=case.case_sha,
                exact_source13_preservation=source_records,all_13_source_files_rehashed_after_build_unchanged=True,
                baseline_native0_equivalence=file_record(D0/"FINAL_NATIVE0/EXACT_P1_MATRIX_DOMAIN_EQUIVALENCE.json"),
                actual_native_binding=binding,objective=objective,necessary_box_check=box,
                complete_model_receipt=built[-1],blocked_Native_attempts=attempts,Native_calls=0,
                original_output_paths_not_written=True,canonical_Native_ledger_unchanged=True,
                ledger_before=before,ledger_after=file_record(LEDGER),wall_seconds=perf_counter()-began,
                FULL_primal="NOT_RUN",integer_feasibility="NOT_CERTIFIED",optimization="NOT_RUN",
                old_pilot_point_or_bound_transferred=False)
            write_new(OUT/"D0_A1_NATIVE0_REGENERATION_PROOF.json",proof)
            _write(output/"PROOF.json",proof)
            return proof
        finally:
            if built is not None:built[0].dispose()


def write_review():
    meta=read(OUT/"D0_A1_EXISTING_PILOT_METADATA_REVIEW.json")
    proof_path=OUT/"D0_A1_NATIVE0_REGENERATION_PROOF.json";proof=read(proof_path) if proof_path.exists() else None
    phase=meta["phase_analysis"]
    text=["# D0 A1 별도 트랙 병목 검토", "", "Unknown C0/C1 진단과 독립된 기존 D0 A1 모델이다. PR223 M2 고정 운전을 새 D0 공동 최적화 결과로 이전하지 않는다.","",
        "기존 Pilot는 요청25초, 실제 Native26.238초, SolCount0, TIME_LIMIT이다. INFEASIBLE 판정이나 모순 제약의 증명이 아니다. P1이 미인증이므로 P2와 신규 M1/A2/M2도 NOT_RUN이다.","",
        f"원래 모델은844,129행 /36,931변수 /10,920,902 NNZ이다. Presolve 표기{phase['Presolve_seconds']}초, Barrier 완료 누적 Native 시각{phase['Root_Barrier_completion_cumulative_Native_seconds']}, 중단 Root relaxation 표기{phase['interrupted_Root_relaxation_reported_seconds']}초를 보존했다. Barrier는19회에서 제한시간으로 중단되어 Root LP가 끝나지 않았다. 세 시간을 더하지 않는다.","",
        "마지막 Barrier의 primal residual은1.55e-6, dual residual은3.33e-8, complementarity는1.36e-5였다. 이는 수렴 중단 관측이며 모델의 구조적 infeasibility 증명이 아니다. 원래 numerical policy의 Method2/ScaleFlag2/NumericFocus3와1 Thread를 보존했다.","",
        (f"새 별도 runtime Native0 재생성 PASS: Matrix {proof['actual_native_binding']['matrix_sha']}, Domain {proof['actual_native_binding']['domain_sha']}, Objective {proof['objective']['objective_sha']}. optimize/presolve/IIS는 전역 차단했고 호출0이다. Case/Science와 Source13개 및 기존 FINAL_NATIVE0 모델 바인딩이 같다. 원래 출력과 Native 원장은 수정하지 않았다." if proof else "새 Native0 재생성은 공유 RAM 창을 기다리는 상태다. 기존 FINAL_NATIVE0 증거를 변경하지 않았고 metadata와 원래 Pilot 로그만 감사했다."),"",
        (f"정적 bounds-only 필요조건 검사: 변수 bound 모순{len(proof['necessary_box_check']['variable_bound_contradictions'])}개, row box 모순{proof['necessary_box_check']['box_only_contradiction_count']}개. 유한한 row 구간은{proof['necessary_box_check']['finite_row_enclosures']:,}행이며 나머지{proof['necessary_box_check']['nonfinite_enclosure_rows']:,}행은 무한 bounds 때문에 결론을 내리지 못했다. 모순을 찾지 못했다는 사실은 LP/MILP feasibility의 증명이 아니다." if proof else "정적 bounds 모순 검사는 Native0 재생성 후 수행한다."),"",
        "다음 최적화는 추가 승인 전 HOLD다. 잔여41.319초에서30초 반환 여유를 빼면11.319초로, 이전 Presolve12.97초보다 짧다. 첫 제안은 모델·행·도메인·목적함수를 바꾸지 않는120초 P1 trial이다.120초와30초 반환 여유만 계산한 최소 총 한도는468.681초(108.681초 추가)다. 기존 Pilot의1.238초 overshoot도 고려해 총 한도480초(120초 추가)를 권고한다. 이 경우30초 반환 여유 외11.319초 buffer가 남는다. 이는 첫 정수해나 최적성의 성공 보장이 아니며 P2/M1/A2/M2 예산은 포함하지 않는다.","",
        "현재25초 Pilot adapter는 동결했다.120초 trial은 추가 예산과 별도 Supervisor admission이 승인된 뒤에만 준비하며 이번에 상한을 변경하거나 실행하지 않았다.","",
        "정수해 확보를 우선하려면 기존 bound-focused MIPFocus3 대신 feasibility-focused1을 승인된 별도 Solver 전략으로 검토할 수 있다. 이번에는 변경·실행하지 않았다. FeasibilityTol/원래 물리 계약/서비스·QoS/GPU·전력/CDF·Carry와 P1→P2→M1/A2/M2 순서는 유지한다. FCFS나 축소 도메인으로 PASS를 만들지 않는다."]
    (OUT/"D0_A1_SOLVER_BOTTLENECK_REVIEW_KO.md").write_text("\n".join(text)+"\n",encoding="utf8")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--native0-build",action="store_true");args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);RUNTIME.mkdir(parents=True,exist_ok=True)
    before=file_record(LEDGER)
    with prohibit_native() as attempts:
        if not args.native0_build:mess_audit();metadata()
        if attempts:raise ValueError("ISOLATED_METADATA_FORBIDDEN_NATIVE_ATTEMPT")
    if args.native0_build:regenerate()
    if file_record(LEDGER)!=before:raise ValueError("ISOLATED_FROZEN_CANONICAL_LEDGER_CHANGED")
    write_review()
    print(json.dumps(dict(status="PASS",Native_calls=0,operation="NATIVE0_REGENERATION" if args.native0_build else "FROZEN_METADATA_ONLY",output=str(OUT)),indent=2))


if __name__=="__main__":main()
