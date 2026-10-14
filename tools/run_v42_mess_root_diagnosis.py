"""Native0 saved S1 Root/CSR analysis and exact verified fixation specifications."""
import json
from pathlib import Path
import shutil
import sys
from time import perf_counter

import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record,matrix_sha,domain_sha,vector_sha
from v42_integration.mess_scaling import checked
from v42_integration.mess_root_diagnosis import root_diagnosis,fixation_overlay,solver_phase_receipt
from tools.audit_v42_s1_fractionality import original_authority
from v42_m1_research.check_ub import matrix_replay

BASE=ROOT/"docs/v42_unified_aidc_mess_research_20261014"
OUT=BASE/"D0_STATE_CONDITIONED_PLANNING_20261015"
OLD=BASE/"FOLLOWUP/MESS_CONTINUATION_20324_ATTEMPT01"
RUNTIME=ROOT/"runtime/D0_MESS_ROOT_DIAGNOSIS_20261015"


def read(path):return json.loads(Path(path).read_text(encoding="utf8"))


def write_new(path,record):
    if Path(path).exists():raise ValueError("D0_MESS_NEW_REPORT_CANNOT_OVERWRITE_EXISTING_EVIDENCE:"+str(path))
    _write(path,record)


def grid_metadata(domain,certificate):
    gate=read(ROOT/"runtime/v42_unified/MESS_EXACT_COMPRESSION_COMPARE01/SOLVE/PILOT_SOURCE_CONTENT_GATE.json")
    source=gate["response"]["source"]
    if source["sha256"]!=certificate["identity"]["response_sha"] or not gate["grid_authority"]["all_original_transformer_current_rows_required"]:
        raise ValueError("S1_GRID_METADATA_ORIGINAL_ALL_TRANSFORMER_SOURCE_REQUIRED")
    with np.load(checked(source),allow_pickle=False) as z:
        branches=list(map(str,z["branch_names"]));ratings=z["transformer_ratings"].copy();nv=z["voltage_constant"].shape[1]
    template=[]
    for n in range(nv):
        template.extend([(f,"voltage_index:"+str(n),None,None) for f in ("voltage_lower","voltage_upper")])
    for branch,rating in zip(branches,ratings):
        asset,phase=branch.rsplit("::",1) if "::" in branch else (branch,None)
        template.extend([("transformer_current",asset,phase,None)] if branch.lower().startswith("transformer.") else [
            ("line_thermal_face",asset,phase,f) for f in range(16)])
        if not np.isnan(rating):template.extend([("transformer_kVA",asset,phase,f) for f in range(16)])
    family=np.array([r[0] for r in template]);axes={}
    for slot in certificate["slots"]:
        offset=slot["original_row_offset"];n=slot["original_rows"]
        if n!=len(template) or not np.array_equal(domain["row_names"][offset:offset+n],family):
            raise ValueError("S1_ORIGINAL_NATIVE_GRID_INSERTION_METADATA_AXIS_DRIFT")
        axes[slot["slot"]]=offset
    offsets=np.array([axes[t] for t in range(96)])
    def describe(row):
        t=int(np.searchsorted(offsets,row,side="right")-1);local=row-int(offsets[t])
        if t<0 or not 0<=local<len(template):raise ValueError("S1_LITERAL_GRID_ROW_OUTSIDE_CAPTURED_SLOTS")
        f,a,p,facet=template[local]
        return dict(family=f,asset=a,phase=p,facet=facet,slot=t,
            original_captured_row=row,native_insertion_local_row=local)
    receipt=dict(status="PASS",source_response=source,branch_phase_names=len(branches),voltage_columns=nv,
        rows_per_slot=len(template),slots=96,all_original_native_grid_family_rows_matched=True,
        capture_offsets=axes,metadata_from_original_native_constructor_order=True,Native_optimize_calls=0)
    return describe,receipt


def main():
    import psutil
    if psutil.virtual_memory().available<8*1024**3:raise RuntimeError("S1_SAVED_CSR_PRELOAD_8GB_RAM_GATE")
    RUNTIME.mkdir(parents=True,exist_ok=False);OUT.mkdir(parents=True,exist_ok=True)
    began=perf_counter();cp=BASE/"MEASURED_MESS_FULL96/FULL96_COMPRESSION_CERTIFICATE.json";cert=read(cp)
    with np.load(checked(cert["original_full_native_domain"]),allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    A=sparse.load_npz(checked(cert["original_full_native_CSR"])).tocsr()
    if matrix_sha(A)!=cert["captured_original_matrix_sha"] or domain_sha(d)!=cert["original_domain_sha"]:
        raise ValueError("S1_SAVED_ORIGINAL_CSR_DOMAIN_SHA_DRIFT")
    root_path=OLD/"FRACTIONAL_SOURCE_ROOT_RAW.npz";integer_path=OLD/"INTEGER_ORACLE_RAW.npz"
    with np.load(root_path,allow_pickle=False) as z:
        x=z["point"].copy()
        if not np.array_equal(z["names"],d["names"]):raise ValueError("S1_SAVED_ROOT_NAME_AXIS_DRIFT")
    with np.load(integer_path,allow_pickle=False) as z:integer=z["point"].copy()
    continuous=dict(d,types=np.full(len(d["names"]),"C"));root_replay=matrix_replay(A,continuous,x)
    integer_replay=matrix_replay(A,d,integer)
    if not root_replay["PASS"] or not integer_replay["PASS"] or not integer_replay["integer_pattern_exact"]:
        raise ValueError("S1_SAVED_LITERAL_RAW_ORIGINAL_ROW_REPLAY_REJECTED")
    manifest=read(ROOT/"runtime/v42_unified/MESS_EXACT_COMPRESSION_COMPARE01/S1_SELECTION_AND_SOURCE.json")
    if manifest["reduced_case_sha"]!=cert["identity"]["reduced_case_sha"]:raise ValueError("S1_SAVED_CASE_SHA_DRIFT")
    _,arcs,arc_columns,_,physical=original_authority(d,manifest)
    metadata,grid_authority=grid_metadata(d,cert)
    diagnosis=root_diagnosis(A,d,x,arcs=arcs,arc_columns=arc_columns,units=manifest["optimization_units"],
        sites=manifest["charging_sites"],battery=manifest["original_battery"],row_metadata=metadata,integer_point=integer)
    diagnosis.update(source_identity=cert["identity"],source_certificate=file_record(cp),
        saved_Root_raw=file_record(root_path),saved_integer_raw=file_record(integer_path),
        unmodified_Root_original_LP_rows=root_replay,unmodified_integer_original_rows=integer_replay,
        source_original_physical_authority=physical,grid_metadata_authority=grid_authority,
        Native0_load_hash_replay_and_diagnosis_wall_seconds=perf_counter()-began)
    write_new(OUT/"S1_ACTUAL_ROOT_LITERAL_DIAGNOSIS.json",diagnosis)
    oracle=read(BASE/"FOLLOWUP/MESS_S1_INTEGER_ORACLE_CONTINUATION_01.json")
    log=(OLD/"INTEGER_ORACLE_NATIVE_GUROBI.log").read_text(encoding="utf8")
    phases=solver_phase_receipt(log,native_runtime=oracle["Native_Runtime"],build_wall=oracle["build_wall_seconds"])
    phases["literal_historical_log"]=file_record(OLD/"INTEGER_ORACLE_NATIVE_GUROBI.log")
    write_new(OUT/"S1_EXISTING_SOLVER_PHASE_TIMING.json",phases)
    experiments=[];preserved=OUT/"MESS_FIXATION_NATIVE0";preserved.mkdir(exist_ok=False)
    for label in ("S1-A","S1-B","S1-C","S1-D"):
        evaluated,overlay,receipt=fixation_overlay(A,d,integer,experiment=label,source_identity=cert["identity"])
        path=RUNTIME/(label+"_ORIGINAL_DOMAIN_OVERLAY.npz");np.savez_compressed(path,**overlay)
        receipt.update(overlay=file_record(path),source_domain=cert["original_full_native_domain"],
            source_CSR=cert["original_full_native_CSR"],source_scope="HISTORICAL_S1_FIXED_AIDC_ANCHOR_NOT_NEW_D0",
            integer_original_application_proof=file_record(OLD/"S1_INTEGER_ORACLE_ORIGINAL_APPLICATION_RAW_REPLAY.json"),
            pattern="SAME_FULL_VALIDATED_STAY_TWO_ACTIVE_UNITS",proposed_Native_cap_seconds=15.,
            fixture_result_is_not_May01_result=True)
        snapshot=preserved/path.name;shutil.copyfile(path,snapshot);receipt["preserved_overlay"]=file_record(snapshot)
        if receipt["preserved_overlay"]["sha256"]!=receipt["overlay"]["sha256"]:raise ValueError("S1_FIXED_DOMAIN_OVERLAY_SNAPSHOT_BYTE_DRIFT")
        if label=="S1-A":receipt.update(Native_result="EXISTING_OPTIMAL_CONTINUOUS_LP_REUSED",existing_objective=diagnosis["Root_LP_objective"],proposed_Native_cap_seconds=0.)
        _write(RUNTIME/(label+"_SPECIFICATION.json"),receipt)
        write_new(preserved/(label+"_SPECIFICATION.json"),receipt);experiments.append(receipt)
        del evaluated
    record=dict(status="NATIVE0_PREPARED",source_scope="HISTORICAL_ORIGINAL_S1_NOT_NEW_D0",
        source_identity=cert["identity"],experiments=experiments,
        original_S1_UB=oracle["ObjVal"],original_S1_valid_bound=oracle["same_S1_full_domain_ObjBound"],
        original_S1_gap_percent=oracle["MIPGap"]*100,integer_optimum="NOT_CERTIFIED",
        B_C_D_actual_Native_execution="NOT_RUN",Route_vs_Mode_causal_role="NOT_CERTIFIED",
        no_repetition_of_384_Mode_or_384_SOC_cuts=True,Official_UB_algorithm="Adaptive Beam -> 4-MESS Joint MILP -> Original FULL -> Incumbent Registry",
        Official_Global_LB_method="K48",Original_4x24_Global_LB=None,new_D0_MESS_UB=None,new_D0_K48_LB=None,
        Native_budget_proposal=dict(B_C_D_total_caps_seconds=45.,supervisor_return_reserve_seconds=30.,
            proposal_total_with_return_seconds=75.,A1_priority=True,not_automatically_dispatched=True,
            reason="Three separately capped LPs isolate one verified route/mode pattern. Existing root runtime informs caps, but completion is not guaranteed. Do not borrow historical sessions."),
        Native_optimize_calls=0)
    write_new(OUT/"S1_ROUTE_MODE_SOC_EXPERIMENTS.json",record)
    lines=["# S1 실제 Root 및 고정 실험 진단", "", "이 자료는 과거 동일 S1 Source/Case의 진단이다. 새 D0 M1/M2 결과나 원래 4×24 Global LB로 이전하지 않는다.","",
        f"저장된 Root에서 Arc {diagnosis['fractional_route_Arcs']}개, Mode {diagnosis['fractional_Mode']}개가 분수이다. 다중 위치 {diagnosis['multiple_location_vehicle_slots']} 차량·슬롯, 동시 충·방전 {diagnosis['simultaneous_charge_discharge_vehicle_slots']} 차량·슬롯을 원래 계수와 대조했다.","",
        "Pch/Pdis/Q의 Signed 계수·차량별 기여·SOC 재귀식과 Critical Line/Phase/Slot은 S1_ACTUAL_ROOT_LITERAL_DIAGNOSIS.json에 저장했다. 분수해의 관측만으로 Route 또는 Mode가 5.02% gap의 유일하거나 지배적인 원인이라고 증명하지 않는다.","",
        f"원래 CSR는 {A.shape[0]:,}행/{A.nnz:,} NNZ이다. 최소 비영 계수 {diagnosis['sparse_statistics']['min_nonzero_coefficient']:.3g}, 최대 절댓값 {diagnosis['sparse_statistics']['max_abs_coefficient']:.3g}로 넓은 계수 범위를 확인했다. 이는 수치 조건수 측정이나 모델 변경 근거는 아니다.","",
        f"기존 Integer oracle Native {oracle['Native_Runtime']:.3f}초에서 Presolve 표기 {phases['Presolve_reported_seconds']}, Barrier 완료 누적 시각 {phases['Barrier_completion_cumulative_Native_seconds']}, Crossover {phases['Crossover_reported_seconds']}, Root relaxation {phases['Root_relaxation_reported_seconds']}초를 보존했다. Solver 내부 중첩 값은 합산하지 않는다. Root 처리 완료 이후 1 node에서 제한시간으로 종료했다.","",
        "S1-A는 기존 연속 LP를 재사용한다. S1-B는 검증된 STAY Arc를 고정하고 Mode/Power를 연속 완화한다. S1-C는 같은 Raw의 Mode만 고정하고 Route를 완화한다. S1-D는 둘을 함께 고정한다. B/C/D는 원래 행·목적함수를 유지하는 Domain Overlay까지 준비했으며 Native 실행은 NOT_RUN이다.","",
        "고정 LP의 목적값이 상승하더라도 그 패턴에 대한 조건부 결과다. 원래 S1 또는 4×24 Global LB로 사용할 수 없고, 가족별 gap을 더하거나 유일한 원인을 인증할 수 없다. 과거 Mode Hull384와 SOC Hull384는 반복하지 않았다.","",
        "새 수학적 강화 선택은 B/C/D 결과까지 확인한 뒤로 남긴다. 차량 전체 궤적 DW는 연구 후보이며 공식 K48을 대체하지 않는다. 완전한 원래 도메인 Pricing과 독립 Dual Certificate가 없는 Restricted Master 값은 Global LB가 아니다.","",
        "B/C/D 제안 상한은 각 15초(합 45초)와 반환 여유 30초이다. A1이 우선이며 Supervisor가 배분하기 전에는 실행하지 않는다. 현재 예산만으로 세 LP 완료를 보장하지 않는다."]
    path=OUT/"S1_ROOT_BOTTLENECK_DIAGNOSIS_KO.md"
    if path.exists():raise ValueError("S1_NEW_KO_REPORT_ALREADY_EXISTS")
    path.write_text("\n".join(lines)+"\n",encoding="utf8")
    print(json.dumps(dict(status="PASS",Native_optimize_calls=0,fractional_routes=diagnosis["fractional_route_Arcs"],
        fractional_modes=diagnosis["fractional_Mode"],critical_rows=len(diagnosis["critical_rows"]),
        fixed_columns={r["experiment"]:r["fixed_columns"] for r in experiments},output=str(OUT)),indent=2))


if __name__=="__main__":main()
