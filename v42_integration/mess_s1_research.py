"""S1-only original-domain SOC/route hull separation; no solver or beam change.

The SOC disjunction differs from the previously ineffective aggregate Mode
hull. Source coefficients come from literal retained energy rows. A candidate
is investigated only after actual same-case root violation and integer proof.
"""
from collections import defaultdict
from fractions import Fraction as F

import numpy as np
from scipy import sparse

from .m_engine import matrix_sha,domain_sha,vector_sha

PROOF=(
    "For an Original integer unit, C>0 implies one connected STAY arc and "
    "binary charge_mode=1. Hence D=0 and every departure travel debit T=0. "
    "The retained energy equality then gives E_next=E+alpha*C<=Emax. If C=0, "
    "E+alpha*C<=Emax is the original SOC box. For beta*D+T<=E-Emin: C=0 "
    "uses E_next=E-beta*D-T>=Emin; C>0 gives D=T=0 and uses E>=Emin. "
    "No route, mode, power, travel or terminal SOC restriction is added to the "
    "Original integer domain; the retained continuous LP can be strengthened."
)


def soc_route_hull_rows(physical_matrix, domain, point, *, source_integer_authority):
    required=("PASS","original_single_integer_path_theorem_verified",
              "original_mode_and_connection_rows_exact","all_original_integer_routes_preserved")
    if any(source_integer_authority.get(k) is not True for k in required) or source_integer_authority.get("route_pool_restriction_added") is not False:
        raise ValueError("S1_SOC_HULL_ORIGINAL_INTEGER_ROUTE_MODE_AUTHORITY_REQUIRED")
    if source_integer_authority.get("physical_matrix_sha")!=matrix_sha(physical_matrix) or source_integer_authority.get("source_domain_sha")!=domain_sha(domain):
        raise ValueError("S1_SOC_HULL_LITERAL_SOURCE_MATRIX_DOMAIN_DRIFT")
    A=physical_matrix.tocsr();names=list(map(str,domain["names"]));x=np.asarray(point,dtype=float)
    if x.shape!=(len(names),) or not np.isfinite(x).all():raise ValueError("S1_SOC_HULL_ACTUAL_RAW_ROOT_POINT_REQUIRED")
    rows=[];units=defaultdict(set);lookup={name:j for j,name in enumerate(names)}
    for i,label in enumerate(map(str,domain["row_names"][:A.shape[0]])):
        if label.split("[",1)[0]!="energy_balance":continue
        a,b=A.indptr[i:i+2];terms={int(j):F(float(v)) for j,v in zip(A.indices[a:b],A.data[a:b]) if v}
        soc=[(j,w) for j,w in terms.items() if names[j].startswith("SOC[")]
        before=[j for j,w in soc if w==-1];after=[j for j,w in soc if w==1]
        if len(soc)!=2 or len(before)!=1 or len(after)!=1 or domain["sense"][i]!="=" or domain["rhs"][i]!=0:
            raise ValueError("S1_SOC_HULL_ORIGINAL_ENERGY_RECURRENCE_REQUIRED")
        u,t=names[before[0]].split("[",1)[1][:-1].split(",");t=int(t)
        mode=lookup.get(f"charge_mode[{u},{t}]")
        if mode is None or domain["types"][mode]!="B" or domain["lower"][mode]!=0 or domain["upper"][mode]!=1:
            raise ValueError("S1_SOC_HULL_LITERAL_BINARY_MODE_UNIT_BOX_REQUIRED")
        if names[after[0]]!=f"SOC[{u},{t+1}]" or t in units[u]:raise ValueError("S1_SOC_HULL_SOC_AXIS_OR_DUPLICATE_ROW_DRIFT")
        units[u].add(t)
        charge={j:-w for j,w in terms.items() if names[j].startswith("Pch[")}
        discharge={j:w for j,w in terms.items() if names[j].startswith("Pdis[")}
        travel={j:w for j,w in terms.items() if names[j].startswith("arc[")}
        if any(names[j].split("[",1)[1][:-1].split(",")[0]!=u or
               int(names[j].split("[",1)[1][:-1].split(",")[-1])!=t for j in (*charge,*discharge)) or (
                any(names[j].split("[",1)[1][:-1].split(",")[0]!=u for j in travel)):
            raise ValueError("S1_SOC_HULL_LITERAL_UNIT_SLOT_POWER_TRAVEL_AXIS_REQUIRED")
        if not charge or not discharge or any(w<=0 for w in (*charge.values(),*discharge.values(),*travel.values())) or (
                set(terms)!=set(charge)|set(discharge)|set(travel)|set(before)|set(after)):
            raise ValueError("S1_SOC_HULL_ORIGINAL_CHARGE_DISCHARGE_TRAVEL_SIGN_DRIFT")
        lo=F(float(domain["lower"][before[0]]));hi=F(float(domain["upper"][before[0]]))
        if (domain["lower"][after[0]]!=float(lo) or domain["upper"][after[0]]!=float(hi)):
            raise ValueError("S1_SOC_HULL_ORIGINAL_SOC_BOX_DRIFT")
        for family,coeff,rhs in (
            ("CHARGE_SOC_HEADROOM",{before[0]:F(1),**charge},hi),
            ("DISCHARGE_TRAVEL_SOC_AVAILABILITY",{before[0]:F(-1),**discharge,**travel},-lo)):
            exact=sum((w*F(float(x[j])) for j,w in coeff.items()),F(0))-rhs
            rows.append(dict(name=f"{family}[{u},{t}]",unit=u,slot=t,family=family,
                terms={str(j):str(w) for j,w in coeff.items()},rhs=str(rhs),sense="<",
                original_energy_row=i,exact_raw_root_violation=str(exact),raw_root_violation=float(exact),
                robustly_violated=exact>F(1,10**7),native_coefficients_are_literal_original_coefficients=True))
    if not units or any(slots!=set(range(96)) for slots in units.values()):
        raise ValueError("S1_SOC_HULL_FULL96_ENERGY_ROWS_REQUIRED")
    return dict(status="DIAGNOSTIC_ONLY",method="ORIGINAL_ROUTE_MODE_SOC_DISJUNCTIVE_INTEGER_HULL",
        scope="S1_REDUCED_ORIGINAL_FULL_ROUTE_DOMAIN_ONLY",integer_validity_theorem=PROOF,
        original_integer_domain_preserved=True,root_point_sha=vector_sha(x),candidate_rows=rows,
        candidate_count=len(rows),robustly_violated_count=sum(r["robustly_violated"] for r in rows),
        maximum_raw_root_violation=max(r["raw_root_violation"] for r in rows),
        repeated_aggregate_mode_hull_experiment=False,original_4x24_Global_LB=None,
        new_certified_S1_LB=None,Native_optimize_calls=0)


def cut_packet(diagnostic, columns, *, violated_only=True):
    chosen=[r for r in diagnostic["candidate_rows"] if not violated_only or r["robustly_violated"]]
    rr=[];cc=[];vv=[]
    for i,r in enumerate(chosen):
        for j,w in r["terms"].items():
            value=float(F(w))
            if F(value)!=F(w):raise ValueError("S1_SOC_HULL_NONLITERAL_NATIVE_COEFFICIENT")
            rr.append(i);cc.append(int(j));vv.append(value)
    A=sparse.csr_matrix((np.asarray(vv,dtype=float),(rr,cc)),shape=(len(chosen),columns))
    rhs=np.asarray([float(F(r["rhs"])) for r in chosen])
    if any(F(float(v))!=F(r["rhs"]) for v,r in zip(rhs,chosen)):raise ValueError("S1_SOC_HULL_NONLITERAL_NATIVE_RHS")
    return A,dict(rhs=rhs,sense=np.full(len(chosen),"<"),row_names=np.array([r["name"] for r in chosen]))


def full_vehicle_dw_plan(domain, source_identity, units):
    """Describe a full schedule hull; route-only flow columns add no strength."""
    names=list(map(str,domain["names"]));blocks={}
    required=("arc","SOC","charge_mode","Pch","Pdis","Q")
    for u in units:
        counts={family:sum(n.startswith(f"{family}[{u},") for n in names) for family in required}
        if any(counts[f]==0 for f in required) or counts["SOC"]!=97 or counts["charge_mode"]!=96:
            raise ValueError("MESS_DW_FULL96_JOINT_ROUTE_SOC_BINARY_MODE_P_Q_BLOCK_REQUIRED")
        mode=[j for j,n in enumerate(names) if n.startswith(f"charge_mode[{u},")]
        if any(domain["types"][j]!="B" for j in mode):raise ValueError("MESS_DW_ORIGINAL_BINARY_MODE_DOMAIN_REQUIRED")
        blocks[u]=dict(variable_family_counts=counts,required_schedule_hull=list(required),
            constraints="Original strict route DAG + SOC travel/rebound/terminal + binary Mode + connection + PCS16 + literal original power/Q domains")
    return dict(status="NOT_RUN",method="FULL_VEHICLE_SCHEDULE_DANTZIG_WOLFE",
        source_identity=dict(source_identity),source_domain_sha=domain_sha(domain),units=list(units),blocks=blocks,
        route_only_columns_strengthen_original_network_flow=False,
        pricing_domain="ALL_ORIGINAL_SINGLE_VEHICLE_FULL96_JOINT_ROUTE_SOC_BINARY_MODE_P_Q_SCHEDULES",
        grid_master="ALL_ORIGINAL_SIGNED_IEEE123_P_Q_GRID_ROWS_AND_OBJECTIVE;FIXED_INACTIVE_Q_UNCHANGED",
        pricing_requirements="Each unit needs a globally valid minimum reduced-cost lower bound under the same master dual, independently verified original full pricing domain and outward dual feasibility; finite or restricted Beam pricing cannot certify it.",
        complete_pricing_executed=False,restricted_master_objective_is_Global_LB=False,
        new_S1_Global_LB=None,Original_4x24_Global_LB=None,Native_optimize_calls=0)


def dw_pricing_scope_gate(plan, receipts, *, requested_scope):
    """Reject incomplete/restricted future pricing before any LB publication.

    This checks scope only. It deliberately cannot certify a numerical bound:
    the actual pricing and independently verified outward dual proof are not
    implemented or executed in this continuation.
    """
    if requested_scope!="S1_REDUCED_ORIGINAL_FULL_DOMAIN":raise ValueError("MESS_DW_REDUCED_S1_BOUND_CANNOT_TRANSFER_TO_ORIGINAL_4X24_OR_CURRENT_C1")
    if set(receipts)!=set(plan["units"]):raise ValueError("MESS_DW_ALL_ACTIVE_ORIGINAL_UNIT_PRICING_REQUIRED")
    expected=set(next(iter(plan["blocks"].values()))["required_schedule_hull"])
    for u,r in receipts.items():
        if r.get("source_identity")!=plan["source_identity"] or r.get("source_domain_sha")!=plan["source_domain_sha"]:
            raise ValueError("MESS_DW_PRICING_SOURCE_CASE_ORIGINAL_DOMAIN_DRIFT")
        if set(r.get("joint_schedule_variable_families",[]))!=expected:
            raise ValueError("MESS_DW_ROUTE_ONLY_OR_PARTIAL_SCHEDULE_PRICING_CANNOT_CERTIFY_INTEGER_HULL")
        if r.get("all_original_routes_preserved") is not True or r.get("finite_Beam_pool_restriction") is not False:
            raise ValueError("MESS_DW_RESTRICTED_PRICING_CANNOT_CERTIFY_GLOBAL_LB")
    return dict(status="SCOPE_ONLY_NOT_BOUND_CERTIFICATE",same_S1_scope_admitted=True,
        independent_outward_dual_pricing_proof="NOT_IMPLEMENTED_NOT_RUN",can_publish_numeric_Global_LB=False,
        reduced_S1_Global_LB=None,Original_4x24_Global_LB=None,Native_optimize_calls=0)
