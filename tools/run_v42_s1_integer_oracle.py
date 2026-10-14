"""Supervisor-only bounded exact Original S1 integer oracle, not 4x24 runtime."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record,matrix_sha,domain_sha,vector_sha,APPROVED_JOINT_PARAMETERS
from v42_integration.mess_scaling import checked
from v42_integration.unified_resource import UnifiedResearchBudget
from tools.audit_v42_s1_fractionality import original_authority


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--solve",action="store_true");p.add_argument("--cap",type=float,default=40.)
    p.add_argument("--attempt",type=int,default=1);args=p.parse_args()
    if not 0.<args.cap<=40.:p.error("S1 oracle cap must be positive and at most40seconds")
    runtime=ROOT/f"runtime/MESS_CONTINUATION_20324/S1_INTEGER_ORACLE_ATTEMPT{args.attempt:02d}"
    runtime.mkdir(parents=True,exist_ok=False)
    certificate=ROOT/"docs/v42_unified_aidc_mess_research_20261014/MEASURED_MESS_FULL96/FULL96_COMPRESSION_CERTIFICATE.json"
    cert=json.loads(certificate.read_text(encoding="utf8"))
    if not cert["PASS"] or not cert["FULL96_original_rows_captured"] or cert["slots_captured"]!=96:
        raise ValueError("S1_ORIGINAL_FULL96_CAPTURE_REQUIRED")
    base=ROOT/"runtime/v42_unified/MESS_EXACT_COMPRESSION_COMPARE01"
    manifest=json.loads((base/"S1_SELECTION_AND_SOURCE.json").read_text(encoding="utf8"))
    if (manifest["stage"]!="S1" or len(manifest["optimization_units"])!=2 or len(manifest["charging_sites"])!=5 or
            manifest["reduced_case_sha"]!=cert["identity"]["reduced_case_sha"]):raise ValueError("S1_ORIGINAL_2X5_SAME_SOURCE_DOMAIN_REQUIRED")
    with np.load(checked(cert["original_full_native_domain"]),allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    if domain_sha(d)!=cert["original_domain_sha"]:raise ValueError("S1_ORIGINAL_DOMAIN_SHA_DRIFT")
    _,_,_,_,physical=original_authority(d,manifest)
    warm_path=base/"SOLVE/COMPRESSION_BENCHMARK/ORIGINAL/IDENTICAL_SOURCE_STAY_START.npz"
    with np.load(warm_path,allow_pickle=False) as z:start=z["point"].copy()
    budget=UnifiedResearchBudget();admission=budget.preflight()
    specification=dict(status="PASS",source_certificate=file_record(certificate),source_identity=cert["identity"],
        physical=physical,MESS_count=2,nodes=5,slots=96,original_integer_types_preserved=True,
        complete_original_S1_route_domain=True,restricted_Beam_pool_used=False,aggregate_Mode_Hull_repeated=False,
        source_scope="HISTORICAL_S1_FIXED_AIDC_ANCHOR_DIAGNOSTIC_NOT_CURRENT_C1",cap_seconds=args.cap,
        workers=1,threads=1,return_reserve_seconds=30.,resource_admission=admission,
        Original_4x24_operational_algorithm_replaced=False,Original_4x24_Global_LB=None,Native_optimize_calls=0)
    _write(runtime/"SPECIFICATION.json",specification)
    if not args.solve:print(json.dumps(dict(status="PASS",Native_optimize_calls=0,runtime=str(runtime),specification=specification),ensure_ascii=False));return
    if budget.remaining(reserve=30.)<args.cap:raise RuntimeError("S1_ORACLE_CANONICAL_RETURN_BUDGET_GATE")
    import psutil
    if psutil.virtual_memory().available<8*1024**3:raise RuntimeError("S1_ORACLE_PRELOAD_8GB_RAM_GATE")
    began=perf_counter();A=sparse.load_npz(checked(cert["original_full_native_CSR"])).tocsr()
    if matrix_sha(A)!=cert["captured_original_matrix_sha"]:raise ValueError("S1_ORIGINAL_FULL_MATRIX_SHA_DRIFT")
    from v42_m1_research.check_ub import matrix_replay
    start_replay=matrix_replay(A,d,start)
    if not start_replay["PASS"] or not start_replay["integer_pattern_exact"] or not start_replay["exact_binary_0_1"]:
        raise ValueError("S1_ORACLE_UNMODIFIED_SAME_CASE_INTEGER_STAY_START_REJECTED")
    if psutil.virtual_memory().available<8*1024**3:raise RuntimeError("S1_ORACLE_PREMODEL_8GB_RAM_GATE")
    import gurobipy as gp
    model=gp.Model("ORIGINAL_S1_ONLY_FULL_ROUTE_INTEGER_DIAGNOSTIC")
    try:
        params=dict(APPROVED_JOINT_PARAMETERS,MIPGap=0.,MIPGapAbs=1e-10,LogFile=str(runtime/"NATIVE.log"))
        for name,value in params.items():setattr(model.Params,name,value)
        x=model.addMVar(A.shape[1],lb=d["lower"],ub=d["upper"],vtype=d["types"],obj=d["objective"])
        x.VarName=d["names"].tolist();x.Start=start;model.ObjCon=float(d["constant"]);model.ModelSense=gp.GRB.MINIMIZE
        rows=model.addMConstr(A,x,d["sense"],d["rhs"]);rows.ConstrName=d["row_names"].tolist();model.update()
        if (matrix_sha(model.getA().tocsr())!=matrix_sha(A) or not np.array_equal(np.asarray(model.getAttr("RHS")),d["rhs"]) or
            not np.array_equal(np.asarray(model.getAttr("Sense")),d["sense"]) or not np.array_equal(x.LB,d["lower"]) or
            not np.array_equal(x.UB,d["upper"]) or not np.array_equal(x.VType,d["types"]) or
            not np.array_equal(x.Obj,d["objective"]) or not np.array_equal(x.Start,start)):
            raise ValueError("S1_ORACLE_ORIGINAL_NATIVE_INTEGER_DOMAIN_READBACK_DRIFT")
        _write(runtime/"NATIVE0_READBACK.json",dict(status="PASS",Native_optimize_calls=0,matrix_sha=matrix_sha(A),
            domain_sha=domain_sha(d),start_sha=vector_sha(start),variables=A.shape[1],rows=A.shape[0],NNZ=A.nnz,
            binaries=int(np.count_nonzero(d["types"]=="B"))))
        budget.stage_context=dict(scale_stage="S1",planning_stage="M1",reduced_case_sha=cert["identity"]["reduced_case_sha"],
            captured_bindings=cert["identity"],source_certificate=file_record(certificate),
            original_source_matrix_sha=matrix_sha(A),original_source_domain_sha=domain_sha(d),
            experiment="BOUNDED_S1_FULL_ORIGINAL_INTEGER_ORACLE_ONLY",Original_4x24_bound_transfer=False)
        build_wall=perf_counter()-began
        call=budget.solve(model,label="MESS:S1:BOUNDED_INTEGER_ORACLE_CONTINUATION",cap=args.cap)
        result=dict(status="NOT_CERTIFIED",scope="S1_2X5_ORIGINAL_FULL_ROUTE_INTEGER_ONLY",
            source_identity=cert["identity"],specification=file_record(runtime/"SPECIFICATION.json"),
            build_wall_seconds=build_wall,Native_call=call,Native_Runtime=float(model.Runtime),
            native_status=int(model.Status),SolCount=int(model.SolCount),NodeCount=float(model.NodeCount),
            same_S1_full_domain_ObjBound=float(model.ObjBound),cap_seconds=args.cap,
            Original_4x24_Global_LB=None,original_4x24_bound_transfer=False,
            integer_optimum=None,historical_S1_STAY_UB=float(d["objective"]@start+d["constant"]),
            Raw_repair=False,aggregate_Mode_Hull_repeated=False)
        if model.SolCount:
            point=np.asarray(x.X,dtype=np.float64);np.savez_compressed(runtime/"INTEGER_RAW.npz",point=point)
            replay=matrix_replay(A,d,point)
            literal=np.all(point[d["types"]!="C"]==np.rint(point[d["types"]!="C"]))
            result.update(ObjVal=float(model.ObjVal),MIPGap=float(model.MIPGap),Raw=file_record(runtime/"INTEGER_RAW.npz"),
                original_grid_physical_row_replay=replay,literal_integer_gate=bool(literal),
                accepted_integer_UB=float(model.ObjVal) if replay["PASS"] and literal else None,
                optimum_status="NUMERICAL_S1_INTEGER_OPTIMAL" if model.Status==gp.GRB.OPTIMAL and replay["PASS"] and literal else "NOT_CERTIFIED")
            if model.Status==gp.GRB.OPTIMAL and replay["PASS"] and literal:result["integer_optimum"]=float(model.ObjVal)
        _write(runtime/"RESULT.json",result)
        report=ROOT/"docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP"/f"MESS_S1_INTEGER_ORACLE_CONTINUATION_{args.attempt:02d}.json"
        if report.exists():raise ValueError("S1_ORACLE_CANNOT_OVERWRITE_HISTORICAL_REPORT")
        _write(report,result)
        print(json.dumps({k:result.get(k) for k in ("status","native_status","SolCount","ObjVal","same_S1_full_domain_ObjBound","MIPGap","optimum_status","Native_Runtime")},indent=2))
    finally:model.dispose()


if __name__=="__main__":main()
