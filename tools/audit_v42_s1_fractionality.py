"""Inspect the saved real S1 LP and prove aggregate mode cuts from raw rows."""
from collections import Counter, defaultdict
from fractions import Fraction
import gzip
import json
from pathlib import Path
import sys

import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record,vector_sha,matrix_sha,domain_sha
from v42_integration.mess_scaling import checked
from v42_integration.mess_mode_hull import aggregate_mode_hull_diagnostic
from v42_integration.unified_contract import digest

OUT=ROOT/"docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP"
BASE=ROOT/"runtime/v42_unified/MESS_EXACT_COMPRESSION_COMPARE01"
PROOF=BASE/"SOLVE/COMPRESSION_BENCHMARK/EXACT_PROOF"
TARGET=ROOT/"runtime/FOLLOWUP_S1_MODE_HULL"


def read(p):return json.loads(Path(p).read_text(encoding="utf8"))


def original_authority(d, manifest):
    """Compare original physical stored coefficients with exact named equations."""
    A=sparse.load_npz(PROOF/"ORIGINAL_PHYSICAL_CSR.npz").tocsr()
    names=list(map(str,d["names"]));lookup={n:j for j,n in enumerate(names)}
    p=manifest["original_battery"]["p_limit"]
    sites=manifest["charging_sites"];H=96
    table=json.loads(gzip.decompress(checked(manifest["original_route_source"]).read_bytes()))
    route=[]
    for i in manifest["original_route_record_indices"]:
        r=table["routes"][i]
        a=(r["origin_service_id"],r["departure_slot_15"],r["destination_service_id"],
            r["departure_slot_15"]+r["connection_ready_slots_15min"],r["energy_safe_kwh"])
        if a not in route:route.append(a)
    arcs=[(s,t,s,t+1,0.) for s in sites for t in range(H)]+route
    stay={(s,t):sites.index(s)*H+t for s in sites for t in range(H)}
    arc={u:{int(n.split(",")[-1][:-1]):j for j,n in enumerate(names) if n.startswith("arc["+u+",")}
         for u in manifest["optimization_units"]}
    if any(not (0<=a[1]<a[3]<=H) for a in arcs):raise ValueError("S1_SOURCE_NOT_STRICT_TIME_DAG")
    def terms(i):
        a,b=A.indptr[i:i+2]
        return {int(j):Fraction(float(v)) for j,v in zip(A.indices[a:b],A.data[a:b]) if v}
    def pattern(t,r):return (tuple(sorted(t.items())),Fraction(float(r)))
    expected_flow=Counter();expected_terminal=Counter()
    for u,cols in arc.items():
        for k,j in cols.items():
            if d["types"][j]!="B" or d["lower"][j]!=0 or d["upper"][j]!=1:
                raise ValueError("S1_ORIGINAL_ARC_BINARY_UNIT_BOX_DRIFT")
        for s in sites:
            for t in range(H):
                co=defaultdict(Fraction)
                for k,j in cols.items():
                    a=arcs[k]
                    if a[:2]==(s,t):co[j]+=1
                    if a[2:4]==(s,t):co[j]-=1
                expected_flow[pattern({j:v for j,v in co.items() if v},int(t==0 and s==manifest["original_initial_sites"][u]))]+=1
        expected_terminal[pattern({j:Fraction(1) for k,j in cols.items() if arcs[k][3]==H},1.)]+=1
    actual_flow=Counter();actual_terminal=Counter();mode_rows={};connection_rows={};energy_rows=[]
    for i,name in enumerate(map(str,d["row_names"][:A.shape[0]])):
        family=name.split("[",1)[0];co=terms(i)
        if family in ("flow","terminal_location"):
            if d["sense"][i]!="=":raise ValueError("S1_ORIGINAL_DAG_EQUALITY_SENSE_DRIFT")
            (actual_flow if family=="flow" else actual_terminal)[pattern(co,d["rhs"][i])]+=1
        elif family in ("connected_Pch","connected_Pdis","no_simultaneous_charge","no_simultaneous_discharge"):
            power="Pch" if family in ("connected_Pch","no_simultaneous_charge") else "Pdis"
            pivots=[j for j in co if names[j].startswith(power+"[")]
            if len(pivots)!=1:raise ValueError("S1_PHYSICAL_POWER_PIVOT_DRIFT")
            j=pivots[0];u,s,t=names[j].split("[",1)[1][:-1].split(",");t=int(t)
            if family.startswith("connected_"):
                other=arc[u][stay[s,t]];wanted={j:Fraction(1),other:-Fraction(p)};rhs=0.
                connection_rows[power,u,s,t]=i
            else:
                other=lookup[f"charge_mode[{u},{t}]"]
                wanted={j:Fraction(1),other:Fraction(-p if power=="Pch" else p)}
                rhs=0. if power=="Pch" else p;mode_rows[power,u,s,t]=i
            if co!=wanted or d["sense"][i]!="<" or d["rhs"][i]!=rhs:
                raise ValueError("S1_ORIGINAL_CONNECTION_MODE_LITERAL_ROW_DRIFT")
        elif family=="energy_balance":energy_rows.append(i)
    if actual_flow!=expected_flow or actual_terminal!=expected_terminal:
        raise ValueError("S1_ORIGINAL_SINGLE_PATH_FLOW_OR_TERMINAL_ROW_DRIFT")
    powers={}
    for j,n in enumerate(names):
        if n.startswith(("Pch[","Pdis[")):
            f,args=n.split("[",1);u,s,t=args[:-1].split(",");powers[f,u,s,int(t)]=j
            if d["lower"][j]!=0 or d["upper"][j]!=p:raise ValueError("S1_ORIGINAL_POWER_BOX_DRIFT")
    if set(powers)!=set(connection_rows) or set(powers)!=set(mode_rows):
        raise ValueError("S1_ORIGINAL_ALL_POWER_MODE_CONNECTION_COVER_DRIFT")
    return A,arcs,arc,energy_rows,dict(status="PASS",PASS=True,Native_optimize_calls=0,
        original_single_integer_path_theorem_verified=True,original_mode_and_connection_rows_exact=True,
        physical_CSR=file_record(PROOF/"ORIGINAL_PHYSICAL_CSR.npz"),route_source=manifest["original_route_source"],
        physical_matrix_sha=matrix_sha(A),source_domain_sha=domain_sha(d),
        flow_rows=sum(actual_flow.values()),terminal_rows=sum(actual_terminal.values()),
        connection_rows=len(connection_rows),mode_rows=len(mode_rows), power_limit_kW=p,
        all_original_integer_routes_preserved=True,route_pool_restriction_added=False,
        proof="Nonnegative binary unit flow on a strict time DAG with one source and one terminal is a single complete path. At most one site STAY is connected at a slot. Literal retained P connection/mode rows then prove the aggregate mode hull for every Original S1 integer point.")


def main():
    manifest=read(BASE/"S1_SELECTION_AND_SOURCE.json")
    source=read(PROOF/"FULL96_COMPRESSION_CERTIFICATE.json")
    if manifest["reduced_case_sha"]!=source["identity"]["reduced_case_sha"]:
        raise ValueError("S1_SOURCE_CASE_SHA_DRIFT")
    with np.load(checked(source["original_full_native_domain"]),allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    with np.load(ROOT/"runtime/FOLLOWUP_S1_LP_30S/LP_POINT.npz",allow_pickle=False) as z:
        x=z["point"].copy();names=z["names"].copy()
    if not np.array_equal(names,d["names"]):raise ValueError("S1_RAW_LP_SOURCE_NAME_AXIS_DRIFT")
    A,arcs,arc,energy,authority=original_authority(d,manifest)
    separation=aggregate_mode_hull_diagnostic(d,manifest["original_battery"]["p_limit"],x)
    separation.update(source_identity=source["identity"],point_sha=vector_sha(x),
        LP_point=file_record(ROOT/"runtime/FOLLOWUP_S1_LP_30S/LP_POINT.npz"),
        actual_source_row_authority_independently_verified=True,source_integer_validity=authority,
        robust_max_violation_kW=max(r["raw_violation"] for r in separation["candidate_rows"]))
    _write(OUT/"S1_AGGREGATE_MODE_HULL_SEPARATION.json",separation)
    _write(OUT/"S1_MODE_HULL_VALIDITY_GATE.json",authority)
    selected=[r for r in separation["candidate_rows"] if r["robustly_violated"]]
    rr=[];cc=[];vv=[]
    for i,row in enumerate(selected):
        for col,value in row["terms"].items():rr.append(i);cc.append(int(col));vv.append(float(Fraction(value)))
    C=sparse.csr_matrix((vv,(rr,cc)),shape=(len(selected),len(x)))
    TARGET.mkdir(parents=True,exist_ok=True);sparse.save_npz(TARGET/"CUTS_A.npz",C)
    np.savez_compressed(TARGET/"CUTS_DATA.npz",rhs=np.array([float(Fraction(r["rhs"])) for r in selected]),
        sense=np.full(len(selected),"<"),row_names=np.array([r["name"] for r in selected]))
    _write(TARGET/"CUTS_AUTHORITY.json",dict(status="PASS",source_identity=source["identity"],
        selected_count=len(selected),integer_validity=authority,point_sha=vector_sha(x),
        cut_matrix_sha=matrix_sha(C),all_coefficients_exact_stored_binary64=True,
        Original_4x24_LB_transfer=False,Native_optimize_calls=0))
    rr=[];cc=[];vv=[]
    for i,row in enumerate(separation["candidate_rows"]):
        for col,value in row["terms"].items():rr.append(i);cc.append(int(col));vv.append(float(Fraction(value)))
    all_C=sparse.csr_matrix((vv,(rr,cc)),shape=(separation["candidate_count"],len(x)))
    sparse.save_npz(TARGET/"ALL_CUTS_A.npz",all_C)
    np.savez_compressed(TARGET/"ALL_CUTS_DATA.npz",rhs=np.array([float(Fraction(r["rhs"])) for r in separation["candidate_rows"]]),
        sense=np.full(separation["candidate_count"],"<"),row_names=np.array([r["name"] for r in separation["candidate_rows"]]))
    _write(TARGET/"ALL_CUTS_AUTHORITY.json",dict(status="PASS",source_identity=source["identity"],
        selected_count=separation["candidate_count"],observed_root_violated=len(selected),integer_validity=authority,
        point_sha=vector_sha(x),cut_matrix_sha=matrix_sha(all_C),all_coefficients_exact_stored_binary64=True,
        Original_4x24_LB_transfer=False,Native_optimize_calls=0))
    lookup={str(n):j for j,n in enumerate(d["names"])};ticks=[]
    for u,cols in arc.items():
        for t in range(96):
            at=[(arcs[k][0],float(x[j])) for k,j in cols.items() if k<len(manifest["charging_sites"])*96 and arcs[k][1]==t]
            transit=sum(float(x[j]) for k,j in cols.items() if k>=len(manifest["charging_sites"])*96 and arcs[k][1]<=t<arcs[k][3])
            ch=sum(float(x[j]) for j,n in enumerate(d["names"]) if str(n).startswith("Pch["+u+",") and str(n).endswith(","+str(t)+"]"))
            dis=sum(float(x[j]) for j,n in enumerate(d["names"]) if str(n).startswith("Pdis["+u+",") and str(n).endswith(","+str(t)+"]"))
            ticks.append(dict(unit=u,slot=t,fractional_connected_sites=[s for s,v in at if v>1e-8],
                connection_mass=sum(v for s,v in at), transit_mass=transit,
                location_plus_transit_mass=sum(v for s,v in at)+transit,
                charge_kW=ch,discharge_kW=dis,simultaneous_charge_discharge=ch>1e-8 and dis>1e-8,
                mode=float(x[lookup[f"charge_mode[{u},{t}]"]]),
                SOC_kWh=float(x[lookup[f"SOC[{u},{t}]"]])))
    energy_residual=np.asarray(A[energy]@x[:A.shape[1]]).ravel()-d["rhs"][energy]
    mechanism=dict(status="DIAGNOSTIC_ONLY",actual_root_point_observed=True,source_identity=source["identity"],
        point_sha=vector_sha(x),LP_point=file_record(ROOT/"runtime/FOLLOWUP_S1_LP_30S/LP_POINT.npz"),
        units=manifest["optimization_units"],slots=96,candidate_nodes=5,
        simultaneous_multiple_location_vehicle_slots=sum(len(r["fractional_connected_sites"])>1 for r in ticks),
        simultaneous_charge_discharge_vehicle_slots=sum(r["simultaneous_charge_discharge"] for r in ticks),
        max_location_plus_transit_mass_residual=max(abs(r["location_plus_transit_mass"]-1.) for r in ticks),
        actual_SOC_balance_max_residual=float(abs(energy_residual).max()),
        actual_SOC_min_kWh=min(r["SOC_kWh"] for r in ticks),actual_SOC_max_kWh=max(r["SOC_kWh"] for r in ticks),
        aggregate_mode_cut_violations=len(selected),max_cut_violation_kW=separation["robust_max_violation_kW"],
        rebound_mechanism="Fractional per-site charge/discharge and route occupancy can offset signed line relief/recharge cost at several nodes. Observed powers and SOC are retained; this is not a physical integer execution.",
        integer_oracle="NOT_CERTIFIED",Original_4x24_Global_LB=None,vehicle_slots=ticks)
    _write(OUT/"S1_ROOT_MECHANISM_ANALYSIS.json",mechanism)
    root=read(OUT/"S1_ROOT_FRACTIONALITY.json");root["root_mechanism_analysis"]=file_record(OUT/"S1_ROOT_MECHANISM_ANALYSIS.json")
    root["mode_hull_separation"]=file_record(OUT/"S1_AGGREGATE_MODE_HULL_SEPARATION.json")
    _write(OUT/"S1_ROOT_FRACTIONALITY.json",root)
    print(json.dumps({k:mechanism[k] for k in ("status","simultaneous_multiple_location_vehicle_slots",
        "simultaneous_charge_discharge_vehicle_slots","actual_SOC_balance_max_residual","aggregate_mode_cut_violations","max_cut_violation_kW")}))


if __name__=="__main__":main()
