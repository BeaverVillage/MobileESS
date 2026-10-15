"""Saved Original S1 root diagnostics and restricted fixation LP overlays.

No solver call, repaired Raw, new cut, operational Beam change or K48 change.
Fixation experiments explain one verified pattern, never a global lower bound.
"""
from collections import Counter,defaultdict
import re

import numpy as np

from .m_engine import matrix_sha,domain_sha,vector_sha


def solver_phase_receipt(log_text, *, native_runtime, build_wall=None):
    """Keep cumulative timestamps distinct from exclusive measured durations."""
    def numbers(pattern):return [float(v) for v in re.findall(pattern,log_text)]
    return dict(Native_Runtime=native_runtime,build_wall_seconds=build_wall,
        Presolve_reported_seconds=numbers(r"Presolve time: ([\d.]+)s"),
        Barrier_completion_cumulative_Native_seconds=numbers(r"Barrier (?:performed [^\n]*? in |solved model in [^\n]*? and )([\d.]+) seconds"),
        Crossover_reported_seconds=numbers(r"Crossover time: ([\d.]+) seconds"),
        Root_relaxation_reported_seconds=numbers(r"Root relaxation: objective .*?, .*? iterations, ([\d.]+) seconds"),
        Root_simplex_logged=bool(re.search(r"Root simplex log",log_text)),
        explored_nodes=[int(v) for v in re.findall(r"Explored (\d+) nodes",log_text)],
        timing_accounting="Presolve/Barrier/Crossover/Root are nested solver observations. Cumulative Barrier timestamp is not an exclusive duration. Do not sum them with Native_Runtime.",
        exclusive_Root_barrier_duration=None,exclusive_B_and_B_duration=None,
        Peak_RAM_this_historical_run="NOT_CAPTURED_IN_THIS_LOG",Native_optimize_calls=0)


def fixation_overlay(A,domain,integer_point,*,experiment,source_identity):
    """Relax all integrality, fixing only the selected original integer family."""
    if experiment not in ("S1-A","S1-B","S1-C","S1-D"):raise ValueError("S1_FIXATION_EXPERIMENT_REQUIRED")
    from v42_m1_research.check_ub import matrix_replay
    point=np.asarray(integer_point,dtype=float);replay=matrix_replay(A,domain,point)
    if not replay["PASS"] or not replay["integer_pattern_exact"] or not replay["exact_binary_0_1"]:
        raise ValueError("S1_FIXATION_UNMODIFIED_ORIGINAL_FULL_INTEGER_PATTERN_REQUIRED")
    names=list(map(str,domain["names"]))
    families={"S1-A":(),"S1-B":("arc",),"S1-C":("charge_mode",),"S1-D":("arc","charge_mode")}[experiment]
    ids=np.array([j for j,n in enumerate(names) if n.split("[",1)[0] in families],dtype=np.int64)
    if families and any(not any(n.startswith(f+"[") for n in names) for f in families):
        raise ValueError("S1_FIXATION_ALL_REQUESTED_ORIGINAL_FAMILIES_REQUIRED")
    d=dict(domain);d["lower"]=domain["lower"].copy();d["upper"]=domain["upper"].copy()
    d["types"]=np.full(len(names),"C");d["lower"][ids]=point[ids];d["upper"][ids]=point[ids]
    packet=dict(indices=ids,values=point[ids].copy())
    receipt=dict(status="NATIVE0_PREPARED",experiment=experiment,source_identity=dict(source_identity),
        original_matrix_sha=matrix_sha(A),original_domain_sha=domain_sha(domain),
        evaluated_domain_sha=domain_sha(d),unchanged_original_matrix_rows_objective=True,
        fixed_original_families=list(families),fixed_columns=len(ids),all_other_integrality_relaxed=True,
        integer_pattern_vector_sha=vector_sha(point),pattern_original_full_row_replay=replay,
        Raw_modified=False,restricted_fixed_pattern_LP=bool(families),
        can_publish_original_S1_Global_LB=False,can_publish_original_4x24_Global_LB=False,
        comparison="Pattern-specific mechanism diagnostic only; an objective rise does not prove this family uniquely dominates the full gap.",
        Native_optimize_calls=0,Native_result="NOT_RUN")
    return d,packet,receipt


def root_diagnosis(A,domain,point,*,arcs,arc_columns,units,sites,battery,
                   row_metadata=None,integer_point=None,critical_limit=64,tolerance=1e-7):
    """Couple the actual saved route/node/mode/PQ/SOC point to literal rows."""
    x=np.asarray(point,dtype=float)
    if x.shape!=(A.shape[1],) or not np.isfinite(x).all():raise ValueError("S1_ACTUAL_ROOT_RAW_AXIS_REQUIRED")
    names=list(map(str,domain["names"]));lookup={n:j for j,n in enumerate(names)}
    rho=[j for j,n in enumerate(names) if n=="rho_max"]
    if len(rho)!=1:raise ValueError("S1_ORIGINAL_RHO_AXIS_REQUIRED")
    rho=rho[0];row_names=list(map(str,domain["row_names"]));rows=A.tocsr()
    thermal=np.array([i for i,n in enumerate(row_names) if n.split("[",1)[0]=="line_thermal_face"],dtype=int)
    if not len(thermal):raise ValueError("S1_ORIGINAL_THERMAL_ROWS_REQUIRED")
    activity=np.asarray(rows@x).ravel()-domain["rhs"]
    scale=-np.asarray(rows[thermal,rho].toarray()).ravel()
    if np.any(scale<=0):raise ValueError("S1_ORIGINAL_SIGNED_MINIMAX_THERMAL_RHO_REQUIRED")
    loading=x[rho]+activity[thermal]/scale
    slots=[];fractional_routes=0;fractional_modes=0
    horizon=max(int(n.split(",")[-1][:-1]) for n in names if n.startswith("SOC["))
    for u in units:
        fractional_routes+=sum(abs(x[j]-round(x[j]))>tolerance for j in arc_columns[u].values())
        for t in range(horizon):
            node={s:0. for s in sites};transit=travel=0.
            for k,j in arc_columns[u].items():
                a=arcs[k];weight=float(x[j])
                if a[0]==a[2] and a[3]==a[1]+1:
                    if a[1]==t:node[a[0]]+=weight
                elif a[1]<=t<a[3]:transit+=weight
                if a[1]==t and a[0]!=a[2]:
                    energy=float(a[-1]) if isinstance(a[-1],(float,int)) else float(a[-1].energy_kwh)
                    travel+=weight*energy
            mode=float(x[lookup[f"charge_mode[{u},{t}]"]]);fractional_modes+=abs(mode-round(mode))>tolerance
            power={f:{s:float(x[lookup[f"{f}[{u},{s},{t}]"]]) if f"{f}[{u},{s},{t}]" in lookup else 0. for s in sites}
                   for f in ("Pch","Pdis","Q")}
            C,D=sum(power["Pch"].values()),sum(power["Pdis"].values())
            E=float(x[lookup[f"SOC[{u},{t}]"]]);En=float(x[lookup[f"SOC[{u},{t+1}]"]])
            residual=En-E-battery["dt_hours"]*(battery["eta_charge"]*C-D/battery["eta_discharge"])+travel
            slots.append(dict(unit=u,slot=t,node_STAY_weights=node,transit_weight=transit,
                location_plus_transit_mass=sum(node.values())+transit,Mode=mode,Pch_by_site=power["Pch"],
                Pdis_by_site=power["Pdis"],Q_by_site=power["Q"],sum_Pch=C,sum_Pdis=D,sum_Q=sum(power["Q"].values()),
                SOC_before=E,SOC_after=En,travel_energy_weighted=travel,SOC_balance_residual=residual,
                SOC_lower_slack=E-battery["minimum"],SOC_upper_slack=battery["maximum"]-E,
                multiple_connected_locations=sum(w>tolerance for w in node.values())>1,
                simultaneous_charge_discharge=C>tolerance and D>tolerance,
                mixed_Q_signs=min(power["Q"].values())<-tolerance and max(power["Q"].values())>tolerance))
    critical=[];seen=set()
    for pos in np.argsort(-loading,kind="stable"):
        i=int(thermal[pos]);meta=row_metadata(i) if row_metadata else dict(name=row_names[i],slot=None)
        key=(meta.get("slot"),meta.get("asset",i),meta.get("phase"))
        if key in seen:continue
        seen.add(key);a,b=rows.indptr[i:i+2];terms=[];contributions=defaultdict(float)
        for j,w in zip(rows.indices[a:b],rows.data[a:b]):
            name=names[j];family=name.split("[",1)[0]
            if family in ("Pch","Pdis","Q"):
                u,s,t=name.split("[",1)[1][:-1].split(",");value=float(w*x[j]/scale[pos])
                contributions[u,family]+=value
                terms.append(dict(column=int(j),name=name,literal_coefficient=float(w),Raw_value=float(x[j]),normalized_contribution=value))
        entry=dict(original_row=i,metadata=meta,normalized_loading=float(loading[pos]),
            slack_to_Raw_rho=float(x[rho]-loading[pos]),signed_P_Q_terms=terms,
            per_unit_family_contribution={"/".join(k):v for k,v in contributions.items()})
        if integer_point is not None:
            entry["same_integer_pattern_loading"]=float(integer_point[rho]+(rows.getrow(i)@integer_point-domain["rhs"][i]).item()/scale[pos])
        critical.append(entry)
        if len(critical)>=critical_limit:break
    absolute=np.abs(rows.data);positive=absolute[absolute>0]
    counts=Counter(n.split("[",1)[0] for n in row_names)
    degree=np.diff(rows.indptr)
    return dict(status="DIAGNOSTIC_ONLY",scope="HISTORICAL_ORIGINAL_S1_ONLY_NOT_NEW_D0",
        source_matrix_sha=matrix_sha(rows),source_domain_sha=domain_sha(domain),root_point_sha=vector_sha(x),
        Root_LP_objective=float(domain["objective"]@x+domain["constant"]),
        fractional_route_Arcs=int(fractional_routes),fractional_Mode=int(fractional_modes),
        multiple_location_vehicle_slots=sum(s["multiple_connected_locations"] for s in slots),
        simultaneous_charge_discharge_vehicle_slots=sum(s["simultaneous_charge_discharge"] for s in slots),
        mixed_Q_sign_vehicle_slots=sum(s["mixed_Q_signs"] for s in slots),
        maximum_location_transit_mass_residual=max(abs(s["location_plus_transit_mass"]-1.) for s in slots),
        maximum_SOC_recurrence_residual=max(abs(s["SOC_balance_residual"]) for s in slots),
        vehicle_slot_coupling=slots,critical_rows=critical,
        total_thermal_rows=len(thermal),maximum_normalized_thermal_loading=float(loading.max()),
        near_Root_bound_thermal_faces=int(np.count_nonzero(loading>=x[rho]-tolerance)),
        row_family_counts=dict(counts),sparse_statistics=dict(rows=rows.shape[0],columns=rows.shape[1],NNZ=rows.nnz,
            min_nonzero_coefficient=float(positive.min()),max_abs_coefficient=float(positive.max()),
            coefficient_dynamic_range=float(positive.max()/positive.min()),
            coefficients_below_1e_10=int(np.count_nonzero(positive<1e-10)),max_row_NNZ=int(degree.max()),
            median_row_NNZ=float(np.median(degree)),matrix_condition_number="NOT_MEASURED"),
        Route_vs_Mode_dominant_gap_cause="NOT_CERTIFIED_FIXATION_EXPERIMENTS_NOT_RUN",
        fractionality_is_not_a_causal_gap_decomposition=True,Original_4x24_Global_LB=None,
        official_Global_LB_method="K48",Native_optimize_calls=0,Raw_modified=False)
