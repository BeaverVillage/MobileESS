"""Joint 24-location static geometry screening, independent of V42 Native.

All 276 pair signs are hard constraints. No AIDC is fixed in this authorized
revision. Proper global orientation is preregistered; no reflection or individual
rotation. Geometric feasibility never certifies an electrical connection port.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import time
import warnings
from collections import deque
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .geometry import POLICY as OLD_TOLERANCE, pair_sign, read_csv, sha256, traffic_xy, transform, write_csv


def dense_rank(values: list[float]) -> list[int]:
    """Dense integer ranks preserve exact strict input-coordinate order.

    MILP rows use integer rank separation >= 1, avoiding an invented minimum
    spatial separation or a numerically weak strict floating-point inequality.
    Equal source coordinates remain equal ranks and cannot satisfy a strict sign.
    """
    rank={value:i for i,value in enumerate(sorted(set(values)))}
    return [rank[value] for value in values]


def candidate_data(root: Path) -> tuple[list[dict],dict]:
    # Prefer newly independently verified source host inventory when available.
    verified=root/"docs/ieee8500_v42_single_case/MV_AIDC_CANDIDATES.csv"
    fallback=root/"ieee8500_v42/data/joint_selection_v2/MV_GUARDED_CANDIDATES.csv"
    prereg=root/"docs/ieee8500_v42_single_case/joint_selection_v2/PREREGISTRATION.json"
    if prereg.exists():
        pinned=json.loads(prereg.read_text())["candidate_authority"]
        source=Path(pinned["path"])
        if sha256(source)!=pinned["sha256"]:
            raise ValueError("Preregistered candidate source bytes changed")
    else:
        source=verified if verified.exists() else fallback
    rows=read_csv(source);result=[]
    for row in rows:
        bus=row.get("bus",row.get("dss_bus",row.get("ieee8500_bus",row.get("candidate_bus","")))).lower()
        x=row.get("x",row.get("source_x",row.get("bus_x","")))
        y=row.get("y",row.get("source_y",row.get("bus_y","")))
        rootdistance=row.get("primary_upstream_impedance_ohm",row.get("root_distance_ohm",row.get("electrical_root_distance_ohm","")))
        if not bus or x=="" or y=="" or rootdistance=="":
            raise ValueError(f"Missing source host identity/coordinates/root distance in {source}")
        if float(rootdistance)<1.3819547376654384:
            continue
        if row.get("source_proximity_excluded","False").lower()=="true":continue
        if source==verified:
            # Accept only independently confirmed electrical eligibility, if the
            # inventory includes its explicit eligibility field.
            eligibility=row.get("electrical_host_eligible",row.get("electrical_eligible","True"))
            if str(eligibility).lower() not in ("true","pass","1"):continue
        result.append({"bus":bus,"x":float(x),"y":float(y),"root_distance_ohm":float(rootdistance),
                       "electrical_authority":"independent_source_inventory" if source==verified else "historical_guarded_v3_pool_pending_independent_check",
                       "source_record":row})
    result=sorted(result,key=lambda row:row["bus"])
    if len({row["bus"] for row in result})!=len(result):raise ValueError("Duplicate MV host identity")
    return result,{"path":str(source),"sha256":sha256(source),"candidate_count":len(result),
                   "independently_verified_inventory":source==verified}


def freeze_policy(root: Path, output: Path, authority: dict) -> dict:
    old=json.loads((root/"docs/ieee8500_v42_single_case/GEOMETRY_STATUS.json").read_text())
    fit=old["common_similarity"]
    policy={"schema":"JOINT_GEOMETRY_V2_PREREGISTRATION",
        "authorization":"latest user authorizes joint 12 AIDC + 12 STA electrical reselection",
        "AIDC_sites_fixed":False,"service_and_traffic_identities_fixed":True,"services":24,
        "required_pairs":276,"traffic_pair_distance_tolerance_km":OLD_TOLERANCE["traffic_pair_distance_tolerance_km"],
        "traffic_axis_zero_tolerance_km":OLD_TOLERANCE["traffic_axis_zero_tolerance_km"],
        "transform":fit,"transform_policy":"one frozen proper similarity from v3 diagnostic orientation; all candidates/sites share it unchanged",
        "orientation_search":"one preregistered orientation only; no global-class infeasibility claim",
        "strict_inequality_implementation":"integer dense rank difference >= 1, equal-coordinate ties share rank",
        "hard_source_guards":["original v3 host eligibility and exclusions","original continuous ABC path and 12.47kV",
                              "original 638-pool q05 root distance >= 1.3819547376654384 ohm","24 distinct PCC buses"],
        "old_pair_spacing":{"electrical_ohm":0.9129072401559803,"source_xy_unknown_units":2221.532547954318,
            "role":"dispersion audit/tie-break, not a source-verified physical connection rating or hard safety spacing",
            "reason":"latest scope retains valid source/physical guards; original XY units are unknown and pair thresholds were statistical design choices"},
        "LV_candidates":1177,"approved_LV_ports":0,
        "STA_mode":"existing MV host fallback geometry only; all access/device/protection gates stay unresolved",
        "screening_domains":[50,100,"all"],"domain_expansion_is_predefined":True,
        "objective":"geometry-first sum squared common-frame anchor distance, rounded 1e-6 km2; lexical bus rank tiny tie-break",
        "outcome_performance_used":False,"B1_B2_B3_used":False,
        "first_feasible_screening_result_accepted_for_physical_review":True,
        "solver":"independent SciPy/HiGHS static binary assignment only; never V42 Native or a physical solver",
        "solver_time_limit_seconds_per_domain":45,"solver_threads":1,"solver_random_seed":0,
        "infeasible_or_time_limited_truncated_domain":"UNKNOWN broader feasibility, not global infeasibility",
        "production_configuration_frozen":False,"production_freeze_requires_user_approval_and_all_physical_gates":True,
        "candidate_authority":authority}
    path=output/"PREREGISTRATION.json"
    if path.exists() and json.loads(path.read_text())!=policy:
        raise ValueError("Existing v2 preregistration differs; create an explicit new revision instead of overwriting")
    path.write_text(json.dumps(policy,indent=2)+"\n",encoding="utf-8")
    return policy


def solve_assignment(anchors: list[dict], candidates: list[dict], fit: dict,
                     domain_size: int | None, time_limit: float=45) -> dict:
    """Finite static assignment MILP with all pair signs and bus uniqueness."""
    positions=[transform((c["x"],c["y"]),fit) for c in candidates]
    ranks=[dense_rank([p[k] for p in positions]) for k in (0,1)]
    target=[traffic_xy(a) for a in anchors]
    domains=[]
    for point in target:
        ordered=sorted(range(len(candidates)),key=lambda j:(math.dist(point,positions[j]),candidates[j]["bus"]))
        domains.append(ordered if domain_size is None else ordered[:domain_size])
    entries=[(site,j) for site,domain in enumerate(domains) for j in domain]
    variable={(site,j):index for index,(site,j) in enumerate(entries)}
    by_site=[[(j,variable[(site,j)]) for j in domain] for site,domain in enumerate(domains)]
    by_bus=[[] for _ in candidates]
    costs=[]
    for index,(site,j) in enumerate(entries):
        by_bus[j].append(index)
        costs.append(round(math.dist(target[site],positions[j])**2,6)+j*1e-12)
    rowindices=[];colindices=[];values=[];low=[];high=[]
    def add_row(items,lower,upper):
        index=len(low);low.append(lower);high.append(upper)
        for column,value in items:
            if value:
                rowindices.append(index);colindices.append(column);values.append(float(value))
    for site in by_site:add_row([(index,1) for _,index in site],1,1)
    for bus in by_bus:
        if bus:add_row([(index,1) for index in bus],0,1)
    signs=0
    for a,b in itertools.combinations(range(len(anchors)),2):
        for axis in (0,1):
            sign=pair_sign(target[a],target[b],axis)
            if not sign:continue
            # sign * (rank_b-rank_a) >= 1 is equivalent to the required
            # strict selected coordinate order, including coordinate ties.
            add_row([(index,-sign*ranks[axis][j]) for j,index in by_site[a]]+
                    [(index,sign*ranks[axis][j]) for j,index in by_site[b]],1,np.inf)
            signs+=1
    matrix=coo_matrix((values,(rowindices,colindices)),shape=(len(low),len(entries))).tocsc()
    before=time.monotonic()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore",message="Unrecognized options detected")
        solved=milp(np.array(costs),integrality=np.ones(len(entries)),bounds=Bounds(0,1),
            constraints=LinearConstraint(matrix,np.array(low),np.array(high)),
            options={"time_limit":float(time_limit),"mip_rel_gap":0.,"threads":1,"random_seed":0})
    result={"domain_size":"all" if domain_size is None else domain_size,"variables":len(entries),
            "rows":len(low),"hard_axis_signs":signs,"elapsed_seconds":time.monotonic()-before,
            "solver_status":int(solved.status),"solver_message":str(solved.message),
            "mip_gap":float(solved.mip_gap) if getattr(solved,"mip_gap",None) is not None else None,
            "objective_value":float(solved.fun) if solved.fun is not None else None,
            "selected":{},"feasible":False,"global_infeasibility_claim":False}
    if solved.x is not None:
        selected={}
        for site,sitevars in enumerate(by_site):
            picks=[j for j,index in sitevars if solved.x[index]>.5]
            if len(picks)!=1:break
            selected[anchors[site]["location_id"]]=candidates[picks[0]]
        if len(selected)==len(anchors):
            audit=audit_mapping(anchors,selected,fit)
            if all(row["pair_pass"] for row in audit) and len({c["bus"] for c in selected.values()})==len(anchors):
                result.update(feasible=True,selected=selected)
            else:
                result["postsolve_rejected"]="exact all-pair sign / distinct-bus audit"
    return result


def audit_mapping(anchors: list[dict], selected: dict, fit: dict) -> list[dict]:
    result=[]
    for a,b in itertools.combinations(anchors,2):
        ai,bi=a["location_id"],b["location_id"]
        ta,tb=traffic_xy(a),traffic_xy(b)
        ga=transform((selected[ai]["x"],selected[ai]["y"]),fit)
        gb=transform((selected[bi]["x"],selected[bi]["y"]),fit)
        expected=[pair_sign(ta,tb,k) for k in (0,1)]
        delta=[gb[k]-ga[k] for k in (0,1)]
        actual=[1 if d>0 else -1 if d<0 else 0 for d in delta]
        passed=[not e or e==s for e,s in zip(expected,actual)]
        result.append({"location_a":ai,"location_b":bi,"role_pair":"-".join(sorted([a["role"],b["role"]])),
            "traffic_node_a":a["traffic_node"],"traffic_node_b":b["traffic_node"],
            "candidate_bus_a":selected[ai]["bus"],"candidate_bus_b":selected[bi]["bus"],
            "traffic_dx_km":tb[0]-ta[0],"traffic_dy_km":tb[1]-ta[1],
            "expected_x_sign":expected[0],"expected_y_sign":expected[1],
            "common_frame_dx_km":delta[0],"common_frame_dy_km":delta[1],
            "actual_x_sign":actual[0],"actual_y_sign":actual[1],
            "x_pass":passed[0],"y_pass":passed[1],"pair_pass":all(passed),
            "source_xy_distance_unknown_units":math.dist((selected[ai]["x"],selected[ai]["y"]),(selected[bi]["x"],selected[bi]["y"])),
            "traffic_distance_km":math.dist(ta,tb),"common_frame_distance_km":math.dist(ga,gb),
            "mapping_status":"GEOMETRY_FEASIBLE_UNQUALIFIED_DESIGN_FINAL_HOLD"})
    return result


def bitset_csp(anchors: list[dict], candidates: list[dict], fit: dict,
               node_limit: int=5000, seconds_limit: float=5,
               allowed_domains: list[list[int]] | None=None,
               candidate_priorities: list[dict[int,tuple]] | None=None) -> dict:
    """Full-domain deterministic CSP with exact pairwise arc consistency.

    Compatibility is represented by integer bitsets of source coordinate
    quadrants. No KNN truncation or invented geographic spacing is imposed.
    Bounded search returns UNKNOWN, never a global mathematical conclusion.
    """
    start=time.monotonic();points=[transform((c["x"],c["y"]),fit) for c in candidates]
    n=len(candidates);full=(1<<n)-1;targets=[traffic_xy(a) for a in anchors]
    less=[];greater=[];equal=[]
    for axis in (0,1):
        groups={}
        for j,p in enumerate(points):groups.setdefault(p[axis],0);groups[p[axis]]|=1<<j
        low={};high={};prefix=0
        for value in sorted(groups):
            low[value]=prefix;high[value]=full^(prefix|groups[value]);prefix|=groups[value]
        less.append([low[p[axis]] for p in points]);greater.append([high[p[axis]] for p in points])
        equal.append([groups[p[axis]] for p in points])
    compatibility={}
    signs={}
    for a,b in itertools.permutations(range(len(anchors)),2):
        sx,sy=pair_sign(targets[a],targets[b],0),pair_sign(targets[a],targets[b],1)
        signs[(a,b)]=(sx,sy)
        if (sx,sy) not in compatibility:
            x=greater[0] if sx>0 else less[0] if sx<0 else [full]*n
            y=greater[1] if sy>0 else less[1] if sy<0 else [full]*n
            # Distinct buses remain mandatory even if near-axis signs are exempt.
            compatibility[(sx,sy)]=[(x[j]&y[j])&~(1<<j) for j in range(n)]
    allowed=allowed_domains or [list(range(n)) for _ in anchors]
    preferences=[]
    for site,(target,domain) in enumerate(zip(targets,allowed)):
        key=lambda j:(math.dist(target,points[j]),candidates[j]["bus"])
        if candidate_priorities is not None:
            key=lambda j:tuple(candidate_priorities[site][j])+(math.dist(target,points[j]),candidates[j]["bus"])
        preferences.append(sorted(domain,key=key))
    nodes=0;revisions=0;bounded=False
    def check_budget():
        nonlocal bounded
        if nodes>=node_limit or time.monotonic()-start>seconds_limit:
            bounded=True;raise TimeoutError
    def consistent(domains: list[int], changed: int | None=None) -> bool:
        nonlocal revisions
        queue=deque(signs if changed is None else [(a,changed) for a in range(len(anchors)) if a!=changed])
        pending=set(queue)
        while queue:
            check_budget();a,b=queue.popleft();pending.remove((a,b));support=compatibility[signs[(a,b)]]
            revised=0;bits=domains[a]
            while bits:
                bit=bits&-bits;j=bit.bit_length()-1;bits^=bit
                if support[j]&domains[b]:revised|=bit
            if revised!=domains[a]:
                revisions+=1;domains[a]=revised
                if not revised:return False
                for c in range(len(anchors)):
                    edge=(c,a)
                    if c!=a and c!=b and edge not in pending:
                        queue.append(edge);pending.add(edge)
        return True
    answer=None
    def search(domains: list[int]) -> bool:
        nonlocal nodes,answer
        check_budget();nodes+=1
        unresolved=[a for a,d in enumerate(domains) if d.bit_count()>1]
        if not unresolved:
            answer=[d.bit_length()-1 for d in domains];return True
        site=min(unresolved,key=lambda a:(domains[a].bit_count(),a))
        for j in preferences[site]:
            if not domains[site]&(1<<j):continue
            child=domains[:];child[site]=1<<j
            if consistent(child,site) and search(child):return True
        return False
    try:
        domains=[sum(1<<j for j in domain) for domain in allowed]
        if consistent(domains):search(domains)
    except TimeoutError:pass
    selected={anchors[a]["location_id"]:candidates[j] for a,j in enumerate(answer)} if answer is not None else {}
    rows=audit_mapping(anchors,selected,fit) if selected else []
    feasible=bool(selected) and all(r["pair_pass"] for r in rows)
    return {"feasible":feasible,"selected":selected,"search_nodes":nodes,"arc_revisions":revisions,
            "elapsed_seconds":time.monotonic()-start,"budget_exhausted":bounded,
            "status":"FEASIBLE" if feasible else "UNKNOWN_BOUNDED_SEARCH" if bounded else "INFEASIBLE_FROZEN_ORIENTATION_DOMAIN",
            "global_infeasibility_claim":False,"full_candidate_count":n}


def expanded_search(root: Path) -> dict:
    """New preregistered orientation revision; never overwrite first v2 search."""
    root=root.resolve();docs=root/"docs/ieee8500_v42_single_case"
    output=docs/"joint_selection_v2/expanded_orientation_v1";output.mkdir(parents=True,exist_ok=True)
    source=docs/"MV_AIDC_CANDIDATES.csv"
    if not source.exists():raise ValueError("Independent source MV inventory required")
    raw=read_csv(source);candidates=[]
    for r in raw:
        if r["electrical_host_eligible"].lower()!="true" or r["source_proximity_guard_pass"].lower()!="true":continue
        if float(r["nominal_kv_ll"])!=12.47 or r["phase_nodes"] not in ("1;2;3","1,2,3","ABC","[1, 2, 3]","1.2.3"):
            raise ValueError("Source verified candidate is not 12.47kV ABC")
        candidates.append({"bus":r["dss_bus"].lower(),"x":float(r["x"]),"y":float(r["y"]),
            "root_distance_ohm":float(r["root_distance_ohm"]),"electrical_authority":"independent_source_inventory"})
    candidates=sorted(candidates,key=lambda c:c["bus"])
    if len(candidates)!=606:raise ValueError("Expected independently verified 606 guarded MV hosts")
    original=json.loads((docs/"GEOMETRY_STATUS.json").read_text())["common_similarity"]
    angles=[original["rotation_degrees"],0.,90.,180.,270.]+[float(a) for a in range(0,360,15) if a not in (0,90,180,270)]
    registry=read_csv(root/"ieee8500_v42/data/geometry/ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv")
    oldaidc=[r for r in registry if r["location_role"]=="AIDC"]
    center=(sum(float(r["bus_x"]) for r in oldaidc)/12,sum(float(r["bus_y"]) for r in oldaidc)/12)
    target_center=transform(center,original)
    policy={"schema":"JOINT_GEOMETRY_V2_EXPANDED_ORIENTATION_V1","AIDC_electrical_hosts_reselectable":True,
        "service_identities_and_traffic_nodes_fixed":True,"candidate_source_sha256":sha256(source),"candidate_count":606,
        "hard_guards":"original host exclusions, independently verified ABC/12.47kV and original q05 root guard",
        "old_pair_spacing_role":"dispersion audit/tie-break only; not hard physical safety constraints",
        "old_electrical_spacing_ohm":.9129072401559803,"old_source_xy_spacing_unknown_units":2221.532547954318,
        "rationale":"original statistical dispersion design metrics are not original interconnection ratings or geographic safety distances",
        "required_pairs":276,"required_axis_signs":552,"near_axis_and_pair_tolerances_km":.001,
        "common_orientation_schedule_degrees":angles,"uniform_scale":original["scale_km_per_unknown_native_unit"],
        "common_source_center":center,"common_target_center":target_center,
        "transform_policy":"one common proper rotation, same positive uniform scale/translation for every site; no reflection/per-site rotation",
        "candidate_domain":"all606; no truncation","static_algorithm":"deterministic bitset CSP with complete pairwise arc consistency",
        "branch_order":"MRV then service identity; candidate squared common-frame distance then lexical bus",
        "per_angle_node_limit":5000,"per_angle_seconds_limit":5,
        "stopping_rule":"first exact-audited geometric feasible allocation in preregistered angle order",
        "not_found_claim":"UNKNOWN allowed-transform family; bounded orientations or time cannot prove global impossibility",
        "B0_B1_B2_B3_or_AC_sensitivity_used_for_geometry":False,
        "LV_qualified_port_count":0,"STA_choice":"MV fallback candidate, all physical port/protection/access gates unresolved",
        "final_production_freeze":False,"final_freeze_requires_all_physical_gates":True,
        "latest_user_authorizes_single_scenario_freeze_after_all_eligibility_gates":True}
    prereg=output/"PREREGISTRATION.json"
    if prereg.exists() and json.loads(prereg.read_text())!=json.loads(json.dumps(policy)):
        raise ValueError("Expanded preregistration is immutable")
    prereg.write_text(json.dumps(policy,indent=2)+"\n")
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    attempts=[];winner=None;fit=None
    for angle in angles:
        radians=math.radians(angle);scale=policy["uniform_scale"]
        u,v=scale*math.cos(radians),scale*math.sin(radians)
        trial_fit={"u":u,"v":v,"translation_x":target_center[0]-u*center[0]+v*center[1],
                   "translation_y":target_center[1]-v*center[0]-u*center[1],
                   "determinant":u*u+v*v,"rotation_degrees":angle,"uniform_scale":scale}
        answer=bitset_csp(anchors,candidates,trial_fit,policy["per_angle_node_limit"],policy["per_angle_seconds_limit"])
        record={k:v for k,v in answer.items() if k!="selected"};record["angle_degrees"]=angle
        attempts.append(record);print(json.dumps(record),flush=True)
        (output/"SEARCH_PROGRESS.json").write_text(json.dumps(attempts,indent=2)+"\n")
        if answer["feasible"]:winner=answer;fit=trial_fit;break
    result={"status":"GEOMETRY_FEASIBLE_UNQUALIFIED_DESIGN_FINAL_HOLD" if winner else "UNKNOWN_BOUNDED_ORIENTATION_SEARCH",
            "geometric_feasibility":bool(winner),"attempts":attempts,"production_configuration_frozen":False,
            "is_final_selection":False,"physical_ports_qualified":False,"global_infeasibility_claim":False,
            "preregistration_sha256":sha256(prereg),"proper_common_transform":fit,"all_candidates":606}
    if winner:
        selected=winner["selected"];audit=audit_mapping(anchors,selected,fit)
        mapping=[]
        for a in anchors:
            site=a["location_id"];c=selected[site];p=transform((c["x"],c["y"]),fit)
            mapping.append({"location_id":site,"role":a["role"],"traffic_node_id":a["traffic_node"],
                "candidate_bus":c["bus"],"source_x":c["x"],"source_y":c["y"],"common_frame_x_km":p[0],"common_frame_y_km":p[1],
                "traffic_x_km":a["x_east_km"],"traffic_y_km":a["y_north_km"],"geometry_error_km":math.dist(p,traffic_xy(a)),
                "root_distance_ohm":c["root_distance_ohm"],"mode":"MV_3PH_AIDC" if a["role"]=="AIDC" else "MV_FALLBACK_STA",
                "source_electrical_host_eligible":True,"physical_port_protection_access_gate":"UNRESOLVED",
                "is_final_selection":False,"status":result["status"]})
        write_csv(output/"JOINT_SERVICE_MAPPING.csv",mapping);write_csv(output/"RELATIVE_POSITION_AUDIT.csv",audit)
        write_csv(output/"AIDC_MAPPING.csv",[r for r in mapping if r["role"]=="AIDC"])
        write_csv(output/"STA_MAPPING.csv",[r for r in mapping if r["role"]=="STA"])
        result.update(all_pair_count=276,all_pair_pass=all(r["pair_pass"] for r in audit),
                      distinct_bus_count=len({c["bus"] for c in selected.values()}),mean_geometry_error_km=sum(r["geometry_error_km"] for r in mapping)/24)
    (output/"GEOMETRY_RESULT.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


def mixed_diagnostic_search(root: Path) -> dict:
    """Explicitly unqualified mixed-domain geometry witness, not production."""
    root=root.resolve();docs=root/"docs/ieee8500_v42_single_case"
    output=docs/"joint_selection_v2/mixed_domain_diagnostic_v1";output.mkdir(parents=True,exist_ok=True)
    mvfile=docs/"MV_AIDC_CANDIDATES.csv";lvfile=docs/"LV_STA_CANDIDATES.csv"
    mv=read_csv(mvfile);lv=read_csv(lvfile)
    candidates=[]
    for r in mv:
        if r["electrical_host_eligible"].lower()!="true" or r["source_proximity_guard_pass"].lower()!="true":continue
        candidates.append({"bus":r["dss_bus"].lower(),"x":float(r["x"]),"y":float(r["y"]),
            "root_distance_ohm":float(r["root_distance_ohm"]),"mode":"MV_3PH", "coordinate_authority":"original_layout_unknown_CRS",
            "electrical_authority":"independently_verified_MV_ABC_root_guard","physical_port_qualified":False})
    for r in lv:
        if r["topology_customer_side"].lower()!="true":continue
        candidates.append({"bus":r["candidate_bus"],"x":float(r["proxy_x"]),"y":float(r["proxy_y"]),
            "root_distance_ohm":"","mode":"LV_SPLIT_PHASE_UNQUALIFIED_PROXY",
            "coordinate_authority":"upstream_primary_proxy_NOT_actual_customer_geography",
            "electrical_authority":"original_service_transformer_triplex_customer_side",
            "upstream_primary_bus":r["upstream_primary_bus"],"support_triplex_lines":r["direct_support_lines"],
            "engineering_upper_bound_kva_NOT_allowed_output":r["engineering_upper_bound_kva_NOT_allowed_output"],
            "physical_port_qualified":False})
    candidates=sorted(candidates,key=lambda c:c["bus"])
    aidc_domain=[j for j,c in enumerate(candidates) if c["mode"]=="MV_3PH"]
    if len(aidc_domain)!=606 or len(candidates)!=1783:raise ValueError("Mixed domain must be606 MV+1177 LV")
    base=json.loads((docs/"joint_selection_v2/expanded_orientation_v1/PREREGISTRATION.json").read_text())
    policy={"schema":"JOINT_GEOMETRY_MIXED_DOMAIN_DIAGNOSTIC_V1","diagnostic_only":True,
        "source_sha256":{"MV":sha256(mvfile),"LV":sha256(lvfile)},"role_domains":{"AIDC":"606 verified MV ABC/root guarded hosts","STA":"1177 LV customer primary-coordinate proxies +606 MVfallback"},
        "candidate_count":1783,"LV_actual_customer_geography_verified":False,"LV_proxy_uncertainty":"no surveyed customer location; schematic source X/SX offsets never treated as survey",
        "approved_MV_ports":0,"approved_LV_ports":0,"device_authorization":False,
        "required_pairs":276,"near_axis_and_pair_tolerances_km":.001,
        "common_orientation_schedule_degrees":base["common_orientation_schedule_degrees"],
        "common_source_center":base["common_source_center"],"common_target_center":base["common_target_center"],"uniform_scale":base["uniform_scale"],
        "transform_policy":"exactly one global proper rotation/positive scale/translation; no per-site change or reflection",
        "strict_orders":"full276 pairs; duplicated LV parent coordinates share ranks and cannot satisfy strict relations at two sites",
        "algorithm":"full-domain bitset CSP/complete arc consistency, queue deduplicated",
        "branch_order":"MRV then location identity; common-frame distance then lexical source bus",
        "per_angle_node_limit":5000,"per_angle_seconds_limit":5,"stopping_rule":"first exact-audited geometric witness only",
        "AC_or_B3_performance_used":False,"old_spacing_metrics":"dispersion audit only, not hard source connection ratings",
        "production_configuration_frozen":False,"final_freeze_requires_all_physical_eligibility_gates":True,
        "latest_user_authorizes_single_final_freeze_after_eligibility":True,
        "bounded_not_found_claim":"UNKNOWN; never global impossibility"}
    prereg=output/"PREREGISTRATION.json"
    if prereg.exists() and json.loads(prereg.read_text())!=policy:raise ValueError("Mixed diagnostic preregistration immutable")
    prereg.write_text(json.dumps(policy,indent=2)+"\n")
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    allowed=[aidc_domain if a["role"]=="AIDC" else list(range(len(candidates))) for a in anchors]
    center=policy["common_source_center"];target=policy["common_target_center"];scale=policy["uniform_scale"]
    attempts=[];winner=None;fit=None
    for angle in policy["common_orientation_schedule_degrees"]:
        theta=math.radians(angle);u,v=scale*math.cos(theta),scale*math.sin(theta)
        tf={"u":u,"v":v,"translation_x":target[0]-u*center[0]+v*center[1],"translation_y":target[1]-v*center[0]-u*center[1],
            "rotation_degrees":angle,"determinant":u*u+v*v,"uniform_scale":scale}
        answer=bitset_csp(anchors,candidates,tf,5000,5,allowed)
        record={k:v for k,v in answer.items() if k!="selected"};record["angle_degrees"]=angle
        attempts.append(record);print(json.dumps(record),flush=True)
        (output/"SEARCH_PROGRESS.json").write_text(json.dumps(attempts,indent=2)+"\n")
        if answer["feasible"]:winner=answer;fit=tf;break
    result={"status":"GEOMETRY_WITNESS_ONLY_PHYSICAL_GATES_UNRESOLVED" if winner else "UNKNOWN_BOUNDED_MIXED_DOMAIN_SEARCH",
        "diagnostic_only":True,"geometric_feasibility":bool(winner),"attempts":attempts,"candidate_count":1783,
        "proper_common_transform":fit,"preregistration_sha256":sha256(prereg),
        "production_configuration_frozen":False,"is_final_selection":False,"all_ports_qualified":False,"global_infeasibility_claim":False}
    if winner:
        selected=winner["selected"];audit=audit_mapping(anchors,selected,fit);mapping=[]
        for a in anchors:
            site=a["location_id"];c=selected[site];p=transform((c["x"],c["y"]),fit)
            mapping.append({"location_id":site,"role":a["role"],"traffic_node_id":a["traffic_node"],"candidate_bus":c["bus"],
                "mode":c["mode"],"coordinate_authority":c["coordinate_authority"],"source_or_primary_proxy_x":c["x"],"source_or_primary_proxy_y":c["y"],
                "common_frame_x_km":p[0],"common_frame_y_km":p[1],"traffic_x_km":a["x_east_km"],"traffic_y_km":a["y_north_km"],
                "geometry_error_km":math.dist(p,traffic_xy(a)),"source_electrical_host_eligible":True,
                "support_triplex_lines":c.get("support_triplex_lines",""),"upstream_primary_bus":c.get("upstream_primary_bus",""),
                "physical_ports_protection_access_gate":"UNRESOLVED","allowed_P_kw":"","allowed_Q_kvar":"",
                "is_final_selection":False,"diagnostic_only":True})
        write_csv(output/"JOINT_SERVICE_MAPPING.csv",mapping);write_csv(output/"RELATIVE_POSITION_AUDIT.csv",audit)
        write_csv(output/"AIDC_MAPPING.csv",[r for r in mapping if r["role"]=="AIDC"]);write_csv(output/"STA_MAPPING.csv",[r for r in mapping if r["role"]=="STA"])
        result.update(all_pair_count=276,all_pair_pass=all(r["pair_pass"] for r in audit),distinct_bus_count=len({c["bus"] for c in selected.values()}),
            STA_LV_proxy_count=sum(r["role"]=="STA" and r["mode"].startswith("LV") for r in mapping),
            mean_geometry_error_km=sum(r["geometry_error_km"] for r in mapping)/24)
    (output/"GEOMETRY_RESULT.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


def verify_witness(root: Path) -> dict:
    """Verify frozen mapping from original inputs; export audits, no solver."""
    from .geometry import read_coords
    root=root.resolve();docs=root/"docs/ieee8500_v42_single_case"
    folder=docs/"joint_selection_v2/expanded_orientation_v1"
    result=json.loads((folder/"GEOMETRY_RESULT.json").read_text())
    if not result["geometric_feasibility"]:raise ValueError("No current geometric witness")
    fit=result["proper_common_transform"]
    policy=json.loads((folder/"PREREGISTRATION.json").read_text())
    if sha256(docs/"MV_AIDC_CANDIDATES.csv")!=policy["candidate_source_sha256"]:
        raise ValueError("Preregistered independently verified candidate bytes changed")
    rows=read_csv(folder/"JOINT_SERVICE_MAPPING.csv");by_id={r["location_id"]:r for r in rows}
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    source=read_coords(root/"ieee8500_v42/data/feeder/Buscoords.dss")
    eligible={r["dss_bus"]:r for r in read_csv(docs/"MV_AIDC_CANDIDATES.csv")}
    if len(by_id)!=24 or len({r["candidate_bus"] for r in rows})!=24:raise ValueError("24 distinct identities/buses required")
    positions={};errors=[]
    for anchor in anchors:
        site=anchor["location_id"];row=by_id[site];bus=row["candidate_bus"]
        if row["traffic_node_id"]!=anchor["traffic_node"] or row["role"]!=anchor["role"]:
            raise ValueError("Traffic/service identity changed")
        if bus not in eligible:raise ValueError("Bus outside independently verified source pool")
        authority=eligible[bus]
        if authority["electrical_host_eligible"].lower()!="true" or authority["source_proximity_guard_pass"].lower()!="true":
            raise ValueError("Source host guard failed")
        if authority["continuous_abc_from_feeder_head"].lower()!="true" or authority["phase_nodes"]!="1,2,3":
            raise ValueError("Original continuous ABC source path failed")
        if abs(float(authority["nominal_kv_ll"])-12.47)>.01247:
            raise ValueError("Original nominal MV host voltage failed")
        if float(authority["root_distance_ohm"])<1.3819547376654384:raise ValueError("Original root guard failed")
        original=source[bus]
        if original!=(float(row["source_x"]),float(row["source_y"])):raise ValueError("Original source XY altered")
        x=fit["u"]*original[0]-fit["v"]*original[1]+fit["translation_x"]
        y=fit["v"]*original[0]+fit["u"]*original[1]+fit["translation_y"]
        if max(abs(x-float(row["common_frame_x_km"])),abs(y-float(row["common_frame_y_km"])))>1e-9:
            raise ValueError("Per-site coordinate transform or matrix inconsistency")
        positions[site]=(x,y)
        errors.append(math.hypot(x-float(anchor["x_east_km"]),y-float(anchor["y_north_km"])))
    determinant=fit["u"]**2+fit["v"]**2
    if determinant<=0 or abs(determinant-fit["determinant"])>1e-15:raise ValueError("Transform not proper similarity")
    exact=[];strict_sign_count=0
    for a,b in itertools.combinations(anchors,2):
        ai,bi=a["location_id"],b["location_id"]
        traffic_delta=(float(b["x_east_km"])-float(a["x_east_km"]),float(b["y_north_km"])-float(a["y_north_km"]))
        common_delta=(positions[bi][0]-positions[ai][0],positions[bi][1]-positions[ai][1])
        near=math.hypot(*traffic_delta)<=.001
        for axis in (0,1):
            expected=0 if near or abs(traffic_delta[axis])<=.001 else (1 if traffic_delta[axis]>0 else -1)
            strict_sign_count+=int(expected!=0)
            actual=1 if common_delta[axis]>0 else -1 if common_delta[axis]<0 else 0
            exact.append(not expected or expected==actual)
    if len(exact)!=552 or not all(exact):raise ValueError("Exact 276-pair sign failure")
    # Reconstruct only static source-tree metrics. These are historical design
    # audits, not hard geographic/physical limits and not a selection rerun.
    from .mv_candidates import build_candidates
    original_candidates=build_candidates(root)
    dispersion=[]
    for a,b in itertools.combinations(anchors,2):
        ai,bi=a["location_id"],b["location_id"]
        dispersion.append({"location_a":ai,"location_b":bi,"role_pair":"-".join(sorted([a["role"],b["role"]])),
            "candidate_bus_a":by_id[ai]["candidate_bus"],"candidate_bus_b":by_id[bi]["candidate_bus"],
            **original_candidates.pair_metrics(by_id[ai]["candidate_bus"],by_id[bi]["candidate_bus"]),
            "old_electrical_threshold_ohm":.9129072401559803,
            "old_xy_threshold_unknown_units":2221.532547954318,
            "hard_geometry_failure":False,"used_to_select_this_witness":False})
    write_csv(folder/"OLD_PAIR_DISPERSION_AUDIT.csv",dispersion)
    dispersion_summary={}
    for role in ("AIDC-AIDC","AIDC-STA","STA-STA"):
        group=[r for r in dispersion if r["role_pair"]==role]
        dispersion_summary[role]={"pairs":len(group),
            "old_electrical_threshold_failures":sum(not r["original_electrical_dispersion_gate_pass"] for r in group),
            "old_xy_threshold_failures":sum(not r["original_xy_dispersion_gate_pass"] for r in group),
            "minimum_electrical_distance_ohm":min(r["electrical_tree_distance_ohm"] for r in group),
            "minimum_source_xy_distance_unknown_units":min(r["source_xy_distance_unknown_units"] for r in group)}
    checked={"status":"PASS_GEOMETRY_ONLY_NOT_PHYSICAL_OR_PRODUCTION","method":"direct original-source matrix calculation; no selection solver called",
        "all_pair_count":276,"axis_relations":552,"all_axis_signs_pass":all(exact),"distinct_buses":24,
        "strict_nonexempt_axis_relations":strict_sign_count,
        "original_source_xy_unchanged":True,"service_traffic_identity_unchanged":True,"source_eligible_ABC_root_guard_pass":True,
        "common_rotation_degrees":fit["rotation_degrees"],"positive_determinant":determinant,
        "mean_geometry_error_km":sum(errors)/24,"rms_geometry_error_km":math.sqrt(sum(e*e for e in errors)/24),
        "maximum_geometry_error_km":max(errors),"minimum_geometry_error_km":min(errors),
        "distance_error_interpretation":"source-layout equivalent km only; not surveyed geographic distance or road travel distance",
        "physical_port_qualification":False,"final_scenario_frozen":False,
        "old_pair_dispersion_audit":dispersion_summary,
        "input_sha256":{str(path.relative_to(root)):sha256(path) for path in
            (root/"ieee8500_v42/data/feeder/Buscoords.dss",root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json",
             docs/"MV_AIDC_CANDIDATES.csv",docs/"ORIGINAL_FEEDER_INVENTORY.json",root/"ieee8500_v42/data/mv_candidates/SOURCE_MANIFEST.json")},
        "witness_sha256":sha256(folder/"JOINT_SERVICE_MAPPING.csv"),
        "files_sha256":{name:sha256(folder/name) for name in ("JOINT_SERVICE_MAPPING.csv","AIDC_MAPPING.csv","STA_MAPPING.csv","RELATIVE_POSITION_AUDIT.csv","PREREGISTRATION.json","OLD_PAIR_DISPERSION_AUDIT.csv")}}
    (folder/"WITNESS_VERIFICATION.json").write_text(json.dumps(checked,indent=2)+"\n")
    report=["# IEEE8500 공동 AIDC–STA 방향 적격성 진단\n",
        "**공동 전기적 위치를 재선정하면 276쌍의 방향 보존이 가능한 기하 witness를 얻는다.** "
        "AIDC 12곳과 STA 12곳의 서비스 ID 및 교통 ID는 유지했고, 전기적 후보 버스는 현재 사용자 지시에 따라 공동으로 변경했다. "
        "과거 고정 v3 앵커의 불가능성 진단은 옛 fixed-anchor 계약에 대한 결과이며, 현재 공동 재선정 문제의 불가능성을 뜻하지 않는다.\n",
        f"하나의 공통 135° proper 회전과 양의 균일 배율 {fit['uniform_scale']:.12f}를 전체 24개에 적용했다. "
        f"determinant={determinant:.12g}>0이며, reflection 또는 개별 회전·이동을 사용하지 않았다. "
        "사전 동결한 1 m 근접/축 공차를 바꾸지 않고 66 AIDC–AIDC, 144 AIDC–STA, 66 STA–STA 쌍, "
        "총 552개 축 관계를 직접 검증했다. 모두 PASS이고 24개 전기적 버스는 서로 다르다.\n",
        "이 결과는 **기하 조건의 첫 feasible witness**이다. 전체 제어 가능성 또는 최종 controllability 점수로 고른 운영 시나리오가 아니다. "
        "후보들은 원본 v3 host 제외 규칙, 원본 q05 root-distance guard, 실제 12.47 kV·연속 ABC 경로를 만족하는 606개 "
        "원본 MV 호스트에서 선택했다. STA는 현재 witness에서 모두 MV fallback 후보이며 LV 포트를 승인하거나 활성화하지 않았다.\n",
        f"공통 frame과 교통 anchor의 위치 오차는 평균 **{checked['mean_geometry_error_km']:.6f}**, "
        f"RMS **{checked['rms_geometry_error_km']:.6f}**, 최대 **{checked['maximum_geometry_error_km']:.6f}** km 상당값이다. "
        "방향을 정확히 보존하는 것과 거리·형상이 작게 왜곡되는 것은 별도 조건이다. 이 witness는 방향 적격성을 증명하지만 "
        "거리 최적성이나 높은 형상 품질을 주장하지 않는다. 숫자는 원본 layout를 공통 배율로 옮긴 equivalent km이며, "
        "원본 DSS의 CRS·단위·true east/north가 인증되지 않았으므로 실제 지리 거리나 SCATS 주행 거리로 해석하지 않는다.\n",
        "원래 v3의 0.912907 Ω / 2221.533 unknown-unit pair spacing은 통계적 분산 설계 기준이므로 새 계약에서는 "
        "별도 audit/tie-break 지표로 보존한다. 이 첫 witness의 분기는 거리·버스 사전순만 사용했으며, 기존 spacing 지표로 고르지 않았다. "
        "원본 정적 전기 tree에서 276쌍의 전기 거리·공유 경로·원본 좌표 거리와 옛 threshold PASS/FAIL을 "
        "`OLD_PAIR_DISPERSION_AUDIT.csv`에 재계산했다. 원본 접속 정격 또는 물리적 안전 이격으로 잘못 취급하지 않는다. "
        "전압·선로·변압기·GPU/랙·Workload/QoS·MESS SOC 및 위치별 P/Q·접속 장치/보호/접근 제약은 "
        "이 기하 탐색으로 통과한 것이 아니다.\n",
        "**최종 Production freeze는 수행하지 않았다.** 원본 MV bus의 전기적 host eligibility와 실제 포트 승인·설비·보호·접근·시간 "
        "근거는 다르다. 현재 모든 후보의 물리적 포트 정격은 미입증이며, 이를 vehicle 450 kW / 600 kVA 정격으로 대체하지 않는다. "
        "최신 사용자는 모든 적격성을 만족한 단일 시나리오의 동결을 이미 허용했으므로 별도의 이전 승인 조건을 현재 gate로 추가하지 않았다. "
        "현재 동결을 막는 원인은 아직 해결되지 않은 물리적 적격성이다.\n",
        "탐색은 Native/Gurobi/전력망 최적화가 아닌 정적 bitset CSP였다. 606개 전체를 포함하고 모든 pair의 부호를 "
        "공통 frame의 strict rank 순서로 검사했다. 각도 순서·정적 분기 기준·5초/5000 node 한도를 시행 전에 기록했다. "
        "시간 한도에 도달한 앞선 각도들은 UNKNOWN이며 전체 변환군의 infeasible로 바꾸지 않았다. "
        "B0/B3·민감도/성능을 이용해 각도나 버스를 고르지 않았다. 큐 중복 제거는 동일 제약의 계산 개선이며 "
        "변경 전 search 결과도 별도 파일로 보존했다.\n",
        "`verify_witness(Path(root))`는 solver를 호출하지 않고 원본 DSS 좌표와 원본 교통 anchor에서 "
        "24개 identity, source guard, 한 공통 변환 및 276쌍 방향을 재검산한다. "
        "재현 명령은 `.runtime/Scripts/python.exe -m ieee8500_v42.joint_geometry --verify --root .`이다. "
        "그 결과와 RMS/최대 오차, 입력·witness SHA는 `WITNESS_VERIFICATION.json`에 있다. "
        "부모의 독립 source audit는 별도 구현으로 다시 검사한다.\n",
        f"현재 witness SHA256: `{checked['witness_sha256']}`.\n",
        "옛 분산 기준의 실패 수는 AIDC–AIDC / AIDC–STA / STA–STA 각각 다음과 같다: "
        +"; ".join(f"{role}: 전기 {values['old_electrical_threshold_failures']}/{values['pairs']}, "
                  f"좌표 {values['old_xy_threshold_failures']}/{values['pairs']}" for role,values in dispersion_summary.items())+". "
        "이는 현재 하드 방향 조건의 실패나 미입증 실제 포트의 허용을 뜻하지 않는다.\n",
        "| 서비스 | 교통 ID | 전기적 후보 bus | 모드 |\n|---|---|---|---|\n"
        +"".join(f"| {row['location_id']} | {row['traffic_node_id']} | {row['candidate_bus']} | {row['mode']} |\n" for row in rows)]
    (folder/"JOINT_GEOMETRY_DIAGNOSTIC_KO.md").write_text("\n".join(report),encoding="utf-8")
    return checked


def plot_witness(root: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .plots import label_sites
    root=root.resolve();folder=root/"docs/ieee8500_v42_single_case/joint_selection_v2/expanded_orientation_v1"
    checked=verify_witness(root);mapping=read_csv(folder/"JOINT_SERVICE_MAPPING.csv")
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    traffic={a["location_id"]:traffic_xy(a) for a in anchors}
    positions={r["location_id"]:(float(r["common_frame_x_km"]),float(r["common_frame_y_km"])) for r in mapping}
    colors={"AIDC":"#b92532","STA":"#1262ad"}
    allpoints=list(traffic.values())+list(positions.values())
    bounds=[(min(p[k] for p in allpoints)-3,max(p[k] for p in allpoints)+3) for k in (0,1)]
    fig,axs=plt.subplots(1,2,figsize=(16,9),sharex=True,sharey=True)
    for panel,locations in enumerate((traffic,positions)):
        ax=axs[panel]
        for role,marker in (("AIDC","o"),("STA","s")):
            points=[locations[a["location_id"]] for a in anchors if a["role"]==role]
            ax.scatter([p[0] for p in points],[p[1] for p in points],c=colors[role],marker=marker,s=55,
                       label=f"{role} identities ({len(points)})",zorder=4)
        ax.set_xlim(*bounds[0]);ax.set_ylim(*bounds[1]);ax.set_aspect("equal");ax.grid(alpha=.15)
        ax.set_title("Original traffic east / north anchors" if panel==0 else "One 135° proper similarity: MV geometry witness",fontsize=12)
        ax.set_xlabel("Traffic east (km)" if panel==0 else "Common-frame X (layout equivalent km)")
        ax.legend(loc="lower left",fontsize=9);label_sites(ax,anchors,locations)
    axs[0].set_ylabel("Traffic north / common-frame Y (km / layout equivalent km)")
    fig.suptitle("Direction-feasible joint geometry witness — physical ports unqualified\n"
                 "All 276 pairs / 552 axis relations pass; 24 distinct source-eligible MV buses",fontsize=16)
    fig.text(.5,.025,f"Geometry residual RMS={checked['rms_geometry_error_km']:.3f}, mean={checked['mean_geometry_error_km']:.3f}, max={checked['maximum_geometry_error_km']:.3f} layout equivalent km.\n"
             "Direction pass does not certify distance shape, geography, AC feasibility, actual ports, controllability, or a final operating scenario.",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.13,1,.90))
    for extension in ("png","svg"):fig.savefig(folder/f"JOINT_GEOMETRY_WITNESS.{extension}",dpi=180,bbox_inches="tight")
    plt.close(fig)


def run(root: Path, time_limit: float=45) -> dict:
    root=root.resolve();output=root/"docs/ieee8500_v42_single_case/joint_selection_v2"
    output.mkdir(parents=True,exist_ok=True)
    candidates,authority=candidate_data(root)
    policy=freeze_policy(root,output,authority)
    if time_limit!=policy["solver_time_limit_seconds_per_domain"]:
        raise ValueError("Solver limit must match preregistration")
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    if len(anchors)!=24:raise ValueError("Exactly 24 immutable service identities required")
    fit=policy["transform"];attempts=[];winner=None
    for size in (50,100,None):
        answer=solve_assignment(anchors,candidates,fit,size,time_limit)
        attempts.append({k:v for k,v in answer.items() if k!="selected"})
        (output/"SEARCH_PROGRESS.json").write_text(json.dumps(attempts,indent=2)+"\n")
        print(json.dumps(attempts[-1]),flush=True)
        if answer["feasible"]:winner=answer;break
    result={"status":"GEOMETRY_FEASIBLE_UNQUALIFIED_DESIGN_FINAL_HOLD" if winner else "UNKNOWN_NO_FEASIBLE_RESULT_IN_FROZEN_ORIENTATION_SEARCH",
            "geometric_feasibility":bool(winner),"candidate_count":len(candidates),"attempts":attempts,
            "production_configuration_frozen":False,"is_final_selection":False,
            "physical_connection_ports_approved":False,"approved_LV_ports":0,
            "proper_common_transform":fit,"preregistration_sha256":sha256(output/"PREREGISTRATION.json"),
            "candidate_authority":authority,"global_infeasibility_claim":False,
            "pair_spacing_role":"separate dispersion audit, not hard source physical constraints"}
    if winner:
        selected=winner["selected"]
        audit=audit_mapping(anchors,selected,fit)
        write_csv(output/"RELATIVE_POSITION_AUDIT.csv",audit)
        mapping=[]
        for a in anchors:
            site=a["location_id"];c=selected[site];point=transform((c["x"],c["y"]),fit)
            mapping.append({"location_id":site,"role":a["role"],"traffic_node_id":a["traffic_node"],
                "candidate_bus":c["bus"],"source_x":c["x"],"source_y":c["y"],
                "common_frame_x_km":point[0],"common_frame_y_km":point[1],
                "traffic_x_km":a["x_east_km"],"traffic_y_km":a["y_north_km"],
                "geometric_residual_km":math.dist(point,traffic_xy(a)),"root_distance_ohm":c["root_distance_ohm"],
                "source_electrical_authority":c["electrical_authority"],
                "electrical_mode":"MV_3PH_CANDIDATE" if a["role"]=="AIDC" else "MV_FALLBACK_CANDIDATE",
                "LV_reselection_status":"NOT_QUALIFIED_NO_PORT" if a["role"]=="STA" else "NOT_APPLICABLE",
                "physical_ports_access_protection_gate":"UNRESOLVED_NOT_APPROVED",
                "is_final_selection":False,"status":result["status"]})
        write_csv(output/"JOINT_SERVICE_MAPPING.csv",mapping)
        write_csv(output/"AIDC_MAPPING.csv",[r for r in mapping if r["role"]=="AIDC"])
        write_csv(output/"STA_MAPPING.csv",[r for r in mapping if r["role"]=="STA"])
        result["all_pair_count"]=len(audit);result["all_pair_pass"]=all(r["pair_pass"] for r in audit)
        result["unique_bus_count"]=len({r["candidate_bus"] for r in mapping})
        result["mean_geometric_residual_km"]=sum(r["geometric_residual_km"] for r in mapping)/24
    (output/"GEOMETRY_RESULT.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path("."))
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--expanded",action="store_true");mode.add_argument("--mixed",action="store_true")
    mode.add_argument("--verify",action="store_true");args=parser.parse_args()
    result=verify_witness(args.root) if args.verify else mixed_diagnostic_search(args.root) if args.mixed else expanded_search(args.root) if args.expanded else run(args.root)
    print(json.dumps({k:v for k,v in result.items() if k not in ("attempts","proper_common_transform")},indent=2))
