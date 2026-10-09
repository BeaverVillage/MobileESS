"""Authorized modeled-port study: mixed MV AIDC / preferred customer LV STA.

Static geometry precedes AC controllability scoring. The original service IDs,
six MESS units, strict pair signs and common proper-transform contract are fixed.
LV geometry uses original upstream-primary proxies, not measured geography.
No original evidence, Native model or electrical equipment is mutated here.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

from .geometry import pair_sign, read_coords, read_csv, sha256, traffic_xy, transform, write_csv
from .joint_geometry import audit_mapping, bitset_csp


DOCS="docs/ieee8500_v42_single_case"


def score_guided_exchanges(anchors: list[dict], candidates: list[dict], fit: dict,
                           seed: dict, scores: list[dict[int,float]], allowed: list[list[int]],
                           max_exchanges: int=100, pair_evaluation_limit: int=500000) -> dict:
    """Deterministic joint1/2-site score ascent with every direction retained.

    This is an explicitly bounded local method, not a global optimality proof.
    All allowable source candidates are considered; there is no KNN truncation.
    Two-site exchanges can improve allocations that cannot improve one site.
    """
    by_bus={c["bus"]:j for j,c in enumerate(candidates)}
    current=[by_bus[seed[a["location_id"]]["bus"]] for a in anchors]
    if len(scores)!=len(anchors) or len(allowed)!=len(anchors):raise ValueError("One score/domain row per service required")
    if any(j not in allowed[a] or j not in scores[a] for a,j in enumerate(current)):
        raise ValueError("Seed outside scored study domain")
    if any(not math.isfinite(v) for row in scores for v in row.values()):raise ValueError("Finite ex-ante scores required")
    positions=[transform((c["x"],c["y"]),fit) for c in candidates]
    target=[traffic_xy(a) for a in anchors]
    signs={(a,b):tuple(pair_sign(target[a],target[b],k) for k in (0,1))
           for a,b in itertools.permutations(range(len(anchors)),2)}
    rounded=[{j:round(v,12) for j,v in row.items()} for row in scores]
    def compatible(a,j,b,k):
        return candidates[j]["bus"]!=candidates[k]["bus"] and all(
            not sign or sign*(positions[k][axis]-positions[j][axis])>0
            for axis,sign in enumerate(signs[(a,b)]))
    if not all(compatible(a,current[a],b,current[b]) for a,b in itertools.combinations(range(len(anchors)),2)):
        raise ValueError("Seed is not jointly direction-feasible")
    def domain(site,changing):
        lower=[-math.inf,-math.inf];upper=[math.inf,math.inf]
        occupied={candidates[current[a]]["bus"] for a in range(len(anchors)) if a not in changing}
        for other in range(len(anchors)):
            if other in changing:continue
            for axis,sign in enumerate(signs[(other,site)]):
                if sign>0:lower[axis]=max(lower[axis],positions[current[other]][axis])
                elif sign<0:upper[axis]=min(upper[axis],positions[current[other]][axis])
        result=[j for j in allowed[site] if j in rounded[site] and candidates[j]["bus"] not in occupied
                and all(lower[k]<positions[j][k]<upper[k] for k in (0,1))]
        return sorted(result,key=lambda j:(-rounded[site][j],math.dist(target[site],positions[j]),candidates[j]["bus"]))
    def value():return sum(rounded[a][j] for a,j in enumerate(current))
    initial=value();history=[];evaluations=0;bounded=False
    for iteration in range(max_exchanges):
        best=None;gain=0.
        # Joint objective ranks every feasible single replacement globally.
        for a in range(len(anchors)):
            choices=domain(a,{a})
            if not choices:continue
            j=choices[0];delta=rounded[a][j]-rounded[a][current[a]]
            if delta>gain+1e-12:gain=delta;best=[(a,j)]
        if best is None:
            # Exhaustive within declared two-site budget; exact compatibility
            # between the changing pair complements the unchanged-site bounds.
            for a,b in itertools.combinations(range(len(anchors)),2):
                da,db=domain(a,{a,b}),domain(b,{a,b})
                if not da or not db:continue
                old=rounded[a][current[a]]+rounded[b][current[b]]
                for j in da:
                    if rounded[a][j]+rounded[b][db[0]]<=old+gain+1e-12:break
                    for k in db:
                        delta=rounded[a][j]+rounded[b][k]-old
                        if delta<=gain+1e-12:break
                        if evaluations>=pair_evaluation_limit:bounded=True;break
                        evaluations+=1
                        if compatible(a,j,b,k):gain=delta;best=[(a,j),(b,k)];break
                    if bounded:break
                if bounded:break
        if best is None:break
        changes=[]
        for a,j in best:
            changes.append({"location_id":anchors[a]["location_id"],"old_bus":candidates[current[a]]["bus"],
                "new_bus":candidates[j]["bus"],"old_score":rounded[a][current[a]],"new_score":rounded[a][j]})
        for a,j in best:current[a]=j
        history.append({"iteration":iteration,"joint_objective_gain":gain,"joint_objective":value(),"changes":changes})
        if bounded:break
    else:bounded=True
    selected={a["location_id"]:candidates[current[site]] for site,a in enumerate(anchors)}
    audit=audit_mapping(anchors,selected,fit)
    if not all(r["pair_pass"] for r in audit) or len({c["bus"] for c in selected.values()})!=len(anchors):
        raise ValueError("Final joint exact-direction audit rejected score exchange")
    return {"selected":selected,"initial_joint_score":initial,"selected_joint_score":value(),
        "score_increase":value()-initial,"exchanges":history,"two_site_pair_evaluations":evaluations,
        "budget_exhausted":bounded,"one_two_site_local_optimum":not bounded,
        "global_optimality_claim":False,"all_provided_role_candidates_considered":True,"feasible":True}


def load_candidates(root: Path) -> tuple[list[dict],dict]:
    docs=root/DOCS;mvfile=docs/"MV_AIDC_CANDIDATES.csv";lvfile=docs/"LV_STA_CANDIDATES.csv"
    source=read_coords(root/"ieee8500_v42/data/feeder/Buscoords.dss")
    candidates=[]
    for row in read_csv(mvfile):
        if row["electrical_host_eligible"].lower()!="true" or row["source_proximity_guard_pass"].lower()!="true":continue
        bus=row["dss_bus"].lower();point=(float(row["x"]),float(row["y"]))
        if source[bus]!=point:raise ValueError("Original MV source coordinates changed")
        if row["continuous_abc_from_feeder_head"].lower()!="true" or row["phase_nodes"]!="1,2,3":
            raise ValueError("Original MV continuous ABC source path failed")
        if abs(float(row["nominal_kv_ll"])-12.47)>.01247 or float(row["root_distance_ohm"])<1.3819547376654384:
            raise ValueError("Original MV voltage or q05 source guard failed")
        candidates.append({"bus":bus,"candidate_id":"MV:"+bus,"x":point[0],"y":point[1],"mode":"MV_MODELED_PORT",
            "root_distance_ohm":float(row["root_distance_ohm"]),"coordinate_authority":"original_DSS_layout_unknown_CRS",
            "upstream_primary_bus":bus,"original_topology_customer_side":False,"original_transformer_kva":"",
            "original_triplex_normal_amps":"","original_engineering_upper_bound_kva_NOT_allowed_output":"",
            "terminal_240v":"","phase_nodes":row["phase_nodes"],"support_triplex_lines":""})
    for row in read_csv(lvfile):
        if row["topology_customer_side"].lower()!="true":continue
        bus=row["candidate_bus"].lower();primary=row["upstream_primary_bus"].lower()
        point=(float(row["proxy_x"]),float(row["proxy_y"]))
        if source[primary]!=point:raise ValueError("LV proxy is not original upstream-primary coordinate")
        if bus not in source or not row["triplex_path"] or not row["direct_support_lines"]:
            raise ValueError("Original customer-side source connection missing")
        candidates.append({"bus":bus,"candidate_id":"LV:"+bus,"x":point[0],"y":point[1],"mode":"LV_MODELED_PORT_PRIMARY_PROXY",
            "root_distance_ohm":"","coordinate_authority":"upstream_primary_proxy_NOT_surveyed_customer_geography",
            "upstream_primary_bus":primary,"original_topology_customer_side":True,
            "original_transformer_kva":float(row["transformer_primary_kva"]),
            "original_triplex_normal_amps":float(row["triplex_min_normal_amps"]),
            "original_engineering_upper_bound_kva_NOT_allowed_output":float(row["engineering_upper_bound_kva_NOT_allowed_output"]),
            "terminal_240v":row["injection_terminal_240v"],"phase_nodes":"1,2",
            "support_triplex_lines":row["direct_support_lines"],"original_service_transformer":row["upstream_transformer"]})
    candidates=sorted(candidates,key=lambda c:c["candidate_id"])
    mv=sum(c["mode"]=="MV_MODELED_PORT" for c in candidates)
    lv=len(candidates)-mv
    if (mv,lv)!=(606,1177) or len({c["bus"] for c in candidates})!=1783:
        raise ValueError("Expected606 original MV and1177 original loaded customer LV buses")
    return candidates,{"MV":sha256(mvfile),"LV":sha256(lvfile),
        "Buscoords":sha256(root/"ieee8500_v42/data/feeder/Buscoords.dss"),
        "traffic_anchors":sha256(root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json")}


def freeze_geometry_policy(root: Path, output: Path, inputs: dict) -> dict:
    base=json.loads((root/DOCS/"joint_selection_v2/expanded_orientation_v1/PREREGISTRATION.json").read_text())
    # The135-degree priority is prior geometry evidence, fixed before any current
    # score is read. Other angles remain the original deterministic grid.
    schedule=[135.]+[v for v in base["common_orientation_schedule_degrees"] if v!=135.]
    policy={"schema":"JOINT_GEOMETRY_V3_MODELED_PORT_STUDY_PREREGISTRATION",
        "latest_authorization":"simulation-based redesigned interfaces authorized; field measurements unavailable",
        "scope":"single simulated study case only, not a field-approved Production configuration",
        "fixed_services":24,"fixed_AIDC_services":12,"fixed_STA_services":12,"fixed_MESS_units":6,
        "additional_CT_or_STA_or_units_added":False,"source_files_mutated":False,
        "role_domains":{"AIDC":"606 independently verified MV ABC/q05 source guarded original hosts",
                        "STA":"1177 original loaded customer LV buses preferred;606 MV fallback hosts"},
        "candidate_source_sha256":inputs,"candidate_count":1783,
        "MV_source_guards":"original host exclusions, continuous ABC,12.47kV, original638 q05 root-distance guard",
        "LV_source_guards":"original customer-side split-phase bus, original service transformer and triplex support path",
        "LV_continuous_ABC_requirement":"not imposed on split-phase customer terminal; AIDC remains MV ABC",
        "LV_coordinate_authority":"upstream-primary proxy; original schematic X/SX offsets are never survey evidence",
        "direction_result_label":"ASSUMED_PROXY_DIRECTION_PASS if any selected STA uses LV proxy",
        "required_pairs":276,"required_axis_relations":552,"near_pair_tolerance_km":.001,"axis_zero_tolerance_km":.001,
        "common_orientation_schedule_degrees":schedule,"common_source_center":base["common_source_center"],
        "common_target_center":base["common_target_center"],"uniform_scale":base["uniform_scale"],
        "transform":"one proper global rotation, positive uniform scale and common translation; no reflection or per-site offsets",
        "stage_order":["all-LV STA geometry feasibility","mixed LV-preferred/MV fallback geometry feasibility",
                       "separately preregistered ex-ante controllability score selection","actual AC checks at selected modeled ports"],
        "algorithm":"full-domain static bitset CSP with exact complete pairwise arc consistency",
        "branch_order":"MRV then fixed service identity; STA LV-first, then squared geometry distance and lexical candidate ID",
        "per_angle_seconds_limit":12,"per_angle_node_limit":20000,
        "stopping_rule":"first exact-audited witness in declared stage/angle order; no geometry optimality claim",
        "old_pair_dispersion_metrics":"separate source-tree/layout audits, not hard geographic interconnection limits",
        "AC_score_read_before_geometry_preregistration":False,"AC_score_used_for_this_geometry_witness":False,
        "B1_B2_B3_performance_used":False,"Native_calls":0,
        "field_evidence_required_for_simulated_study":False,"field_qualified_or_Production":False,
        "study_case_freeze_authorized_after_modeled_AC_eligibility":True,
        "modeled_equipment_rating_requirement":"separate literature-backed interface/transformer/triplex/PCS bounds; no vehicle-rating substitution",
        "selected_port_actual_AC_validation_required":True,"voltage_current_transformer_reverse_power_and_PQ_constraints_required":True,
        "study_rating_derating_access_and_connection_time_parameters":"root supplies explicit model assumptions; not field certification",
        "bounded_failure_claim":"UNKNOWN family feasibility; never infer global infeasibility from angle or time bounds"}
    path=output/"GEOMETRY_PREREGISTRATION.json"
    normalized=json.loads(json.dumps(policy))
    if path.exists() and json.loads(path.read_text())!=normalized:
        raise ValueError("CurrentV3 geometry preregistration immutable; create explicit new revision")
    if not path.exists():path.write_text(json.dumps(policy,indent=2)+"\n",encoding="utf-8")
    return policy


def common_transform(policy: dict, angle: float) -> dict:
    theta=math.radians(angle);scale=policy["uniform_scale"];u,v=scale*math.cos(theta),scale*math.sin(theta)
    center=policy["common_source_center"];target=policy["common_target_center"]
    return {"u":u,"v":v,"translation_x":target[0]-u*center[0]+v*center[1],
        "translation_y":target[1]-v*center[0]-u*center[1],"rotation_degrees":angle,
        "determinant":u*u+v*v,"uniform_scale":scale}


def export_mapping(output: Path, anchors: list[dict], selected: dict, fit: dict, result: dict) -> None:
    mapping=[]
    for anchor in anchors:
        site=anchor["location_id"];c=selected[site];point=transform((c["x"],c["y"]),fit)
        lv=c["mode"].startswith("LV")
        mapping.append({"location_id":site,"role":anchor["role"],"traffic_node_id":anchor["traffic_node"],
            "candidate_bus":c["bus"],"candidate_id":c["candidate_id"],"mode":c["mode"],
            "source_or_proxy_x":c["x"],"source_or_proxy_y":c["y"],"coordinate_authority":c["coordinate_authority"],
            "common_frame_x_km":point[0],"common_frame_y_km":point[1],"traffic_x_km":anchor["x_east_km"],"traffic_y_km":anchor["y_north_km"],
            "geometry_error_layout_equivalent_km":math.dist(point,traffic_xy(anchor)),
            "upstream_primary_bus":c["upstream_primary_bus"],"customer_terminal_240v":c["terminal_240v"],
            "original_service_transformer":c.get("original_service_transformer",""),"support_triplex_lines":c["support_triplex_lines"],
            "original_transformer_kva":c["original_transformer_kva"],"original_triplex_normal_amps":c["original_triplex_normal_amps"],
            "source_bound_NOT_allowed_output_kva":c["original_engineering_upper_bound_kva_NOT_allowed_output"],
            "modeled_allowed_P_kw":"PENDING_ROOT_MODEL_RATING","modeled_allowed_Q_kvar":"PENDING_ROOT_MODEL_RATING",
            "geometry_direction_status":"ASSUMED_PROXY_DIRECTION_PASS" if lv else "SOURCE_LAYOUT_DIRECTION_PASS",
            "field_geography_certified":False,"field_port_qualified":False,"Production":False,
            "simulation_redesigned_port_authorized":True,"selected_port_actual_AC_pass":"PENDING",
            "is_final_controllability_selection":False,"is_study_case_frozen":False})
    audit=audit_mapping(anchors,selected,fit)
    for row in audit:
        lv=selected[row["location_a"]]["mode"].startswith("LV") or selected[row["location_b"]]["mode"].startswith("LV")
        row["mapping_status"]="ASSUMED_PROXY_DIRECTION_PASS" if lv else "SOURCE_LAYOUT_DIRECTION_PASS"
        row["physical_geographic_direction_certified"]=False
    write_csv(output/"JOINT_SERVICE_MAPPING.csv",mapping);write_csv(output/"RELATIVE_POSITION_AUDIT.csv",audit)
    write_csv(output/"AIDC_MAPPING.csv",[r for r in mapping if r["role"]=="AIDC"])
    write_csv(output/"STA_MAPPING.csv",[r for r in mapping if r["role"]=="STA"])
    errors=[r["geometry_error_layout_equivalent_km"] for r in mapping]
    result.update(all_pair_count=len(audit),all_axis_relations=552,all_pair_pass=all(r["pair_pass"] for r in audit),
        distinct_buses=len({r["candidate_bus"] for r in mapping}),STA_LV_count=sum(r["role"]=="STA" and r["mode"].startswith("LV") for r in mapping),
        mean_geometry_error_layout_equivalent_km=sum(errors)/24,rms_geometry_error_layout_equivalent_km=math.sqrt(sum(e*e for e in errors)/24),
        maximum_geometry_error_layout_equivalent_km=max(errors),witness_sha256=sha256(output/"JOINT_SERVICE_MAPPING.csv"),
        files_sha256={name:sha256(output/name) for name in ("JOINT_SERVICE_MAPPING.csv","AIDC_MAPPING.csv","STA_MAPPING.csv","RELATIVE_POSITION_AUDIT.csv","GEOMETRY_PREREGISTRATION.json")})


def geometry_search(root: Path) -> dict:
    root=root.resolve();output=root/DOCS/"joint_selection_v3/geometry_first"
    output.mkdir(parents=True,exist_ok=True)
    if (output/"GEOMETRY_RESULT.json").exists():
        raise ValueError("CurrentV3 result exists: verify it instead of rerunning a time-bounded selection")
    candidates,inputs=load_candidates(root);policy=freeze_geometry_policy(root,output,inputs)
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    if len(anchors)!=24 or sum(a["role"]=="STA" for a in anchors)!=12:
        raise ValueError("Original24 service identities required")
    if sum(bool(pair_sign(traffic_xy(a),traffic_xy(b),k)) for a,b in itertools.combinations(anchors,2) for k in (0,1))!=552:
        raise ValueError("Expected552 original strict nonexempt axis signs")
    mv=[j for j,c in enumerate(candidates) if c["mode"]=="MV_MODELED_PORT"]
    lv=[j for j,c in enumerate(candidates) if c["mode"].startswith("LV")]
    attempts=[];winner=None;fit=None
    for stage in ("ALL_LV_STA","MIXED_LV_PREFERRED_MV_FALLBACK"):
        allowed=[mv if a["role"]=="AIDC" else lv if stage=="ALL_LV_STA" else list(range(len(candidates))) for a in anchors]
        priority=[{j:(int(a["role"]=="STA" and not candidates[j]["mode"].startswith("LV")),) for j in domain}
                  for a,domain in zip(anchors,allowed)]
        for angle in policy["common_orientation_schedule_degrees"]:
            trial=common_transform(policy,angle)
            answer=bitset_csp(anchors,candidates,trial,policy["per_angle_node_limit"],policy["per_angle_seconds_limit"],allowed,priority)
            record={k:v for k,v in answer.items() if k!="selected"};record.update(stage=stage,angle_degrees=angle)
            attempts.append(record);print(json.dumps(record),flush=True)
            (output/"SEARCH_PROGRESS.json").write_text(json.dumps(attempts,indent=2)+"\n")
            if answer["feasible"]:winner=answer;fit=trial;break
        if winner:break
    result={"schema":"CURRENT_V3_MODELED_PORT_GEOMETRY_RESULT","status":"ASSUMED_PROXY_DIRECTION_PASS" if winner else "UNKNOWN_BOUNDED_MIXED_DOMAIN_SEARCH",
        "geometric_feasibility":bool(winner),"attempts":attempts,"proper_common_transform":fit,
        "candidate_count":1783,"AIDC_domain_count":606,"STA_LV_domain_count":1177,"STA_MV_fallback_domain_count":606,
        "simulation_redesigned_port_authorized":True,"field_evidence_required_for_study":False,
        "field_geography_or_port_certified":False,"Production":False,
        "is_final_controllability_selection":False,"study_case_frozen":False,"selected_port_actual_AC_gate":"PENDING",
        "AC_score_used":False,"B1_B2_B3_performance_used":False,"Native_calls":0,"global_infeasibility_claim":False,
        "preregistration_sha256":sha256(output/"GEOMETRY_PREREGISTRATION.json")}
    if winner:export_mapping(output,anchors,winner["selected"],fit,result)
    (output/"GEOMETRY_RESULT.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


def verify_geometry(root: Path, output: Path | None=None, write_report: bool=True) -> dict:
    """Recalculate current mixed witness directly; no CSP or AC solver called."""
    root=root.resolve();output=output or root/DOCS/"joint_selection_v3/geometry_first"
    policy=json.loads((output/"GEOMETRY_PREREGISTRATION.json").read_text())
    result=json.loads((output/"GEOMETRY_RESULT.json").read_text())
    if not result["geometric_feasibility"]:raise ValueError("No feasible witness to verify")
    candidates,inputs=load_candidates(root)
    if inputs!=policy["candidate_source_sha256"]:raise ValueError("CurrentV3 preregistered input bytes changed")
    by_bus={c["bus"]:c for c in candidates};fit=result["proper_common_transform"]
    mapping=read_csv(output/"JOINT_SERVICE_MAPPING.csv");by_site={r["location_id"]:r for r in mapping}
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    if len(by_site)!=24 or len({r["candidate_bus"] for r in mapping})!=24:
        raise ValueError("Original24 identities and24 distinct buses required")
    if sha256(output/"JOINT_SERVICE_MAPPING.csv")!=result["witness_sha256"]:
        raise ValueError("Current geometry witness bytes changed")
    det=fit["u"]**2+fit["v"]**2
    if det<=0 or abs(math.sqrt(det)-policy["uniform_scale"])>1e-15:
        raise ValueError("Positive uniform global similarity required")
    declared=common_transform(policy,fit["rotation_degrees"])
    if any(abs(fit[k]-declared[k])>1e-9 for k in ("u","v","translation_x","translation_y")):
        raise ValueError("One preregistered common transform required")
    positions={};errors=[];selected={}
    for anchor in anchors:
        site=anchor["location_id"];row=by_site[site];c=by_bus[row["candidate_bus"]]
        if row["traffic_node_id"]!=anchor["traffic_node"] or row["role"]!=anchor["role"]:
            raise ValueError("Original service/traffic identity changed")
        if anchor["role"]=="AIDC" and c["mode"]!="MV_MODELED_PORT":raise ValueError("AIDC outside MV606 domain")
        if (float(row["source_or_proxy_x"]),float(row["source_or_proxy_y"]))!=(c["x"],c["y"]):
            raise ValueError("Original source or upstream-primary proxy altered")
        x=fit["u"]*c["x"]-fit["v"]*c["y"]+fit["translation_x"]
        y=fit["v"]*c["x"]+fit["u"]*c["y"]+fit["translation_y"]
        if max(abs(x-float(row["common_frame_x_km"])),abs(y-float(row["common_frame_y_km"])))>1e-9:
            raise ValueError("Per-site coordinate alteration detected")
        positions[site]=(x,y);selected[site]=c
        errors.append(math.hypot(x-float(anchor["x_east_km"]),y-float(anchor["y_north_km"])))
    direct=[]
    for a,b in itertools.combinations(anchors,2):
        ai,bi=a["location_id"],b["location_id"]
        dx=float(b["x_east_km"])-float(a["x_east_km"]);dy=float(b["y_north_km"])-float(a["y_north_km"])
        for axis,delta in enumerate((dx,dy)):
            expected=0 if math.hypot(dx,dy)<=.001 or abs(delta)<=.001 else 1 if delta>0 else -1
            actual_delta=positions[bi][axis]-positions[ai][axis]
            actual=1 if actual_delta>0 else -1 if actual_delta<0 else 0
            direct.append({"location_a":ai,"location_b":bi,"axis":"X" if axis==0 else "Y",
                "traffic_delta_km":delta,"common_delta_layout_equivalent_km":actual_delta,
                "expected_sign":expected,"actual_sign":actual,"pass":not expected or expected==actual,
                "coordinate_assumption":"LV upstream-primary proxy where applicable; never survey",
                "transform_rotation_degrees":fit["rotation_degrees"]})
    if len(direct)!=552 or not all(r["pass"] for r in direct):raise ValueError("Direct552 sign verification failed")
    write_csv(output/"DIRECT_552_AXIS_VERIFICATION.csv",direct)
    checked={"status":"ASSUMED_PROXY_DIRECTION_PASS","direct_axis_relations":552,"direct_pairs":276,
        "all_axis_pass":True,"strict_nonexempt_signs":sum(bool(r["expected_sign"]) for r in direct),
        "original24_service_traffic_identities_pass":True,"distinct_PCC_buses":24,
        "AIDC_MV_count":12,"STA_LV_count":sum(c["mode"].startswith("LV") for site,c in selected.items() if site.startswith("STA")),
        "one_common_proper_transform":True,"positive_determinant":det,"rotation_degrees":fit["rotation_degrees"],
        "mean_layout_equivalent_error_km":sum(errors)/24,"rms_layout_equivalent_error_km":math.sqrt(sum(e*e for e in errors)/24),
        "maximum_layout_equivalent_error_km":max(errors),"field_geography_certified":False,"Production":False,
        "simulation_redesign_authorized":True,"field_evidence_required_for_simulated_study":False,
        "selected_port_actual_AC_gate":"PENDING","ex_ante_controllability_selection":
            "COMPLETED_LOCAL_SURROGATE_SELECTION_AC_PENDING" if result.get("AC_score_used") else "PENDING_SCORE_INPUT",
        "study_case_frozen":False,"selection_solver_calls":0,"Native_calls":0,
        "input_sha256":inputs,"witness_sha256":sha256(output/"JOINT_SERVICE_MAPPING.csv"),
        "direct_axis_audit_sha256":sha256(output/"DIRECT_552_AXIS_VERIFICATION.csv")}
    (output/"GEOMETRY_VERIFICATION.json").write_text(json.dumps(checked,indent=2)+"\n",encoding="utf-8")
    if not write_report:return checked
    table="| 서비스 | 교통 ID | 후보 bus | 모델 |\n|---|---|---|---|\n"+"".join(
        f"| {r['location_id']} | {r['traffic_node_id']} | {r['candidate_bus']} | {r['mode']} |\n" for r in mapping)
    report=["# 현재 V3: LV 포트 재설계 연구의 공동 기하 witness\n",
        "**12개 STA를 모두 원본 고객측 LV bus에 두고 12개 AIDC MV host를 공동 재선정한 기하 witness를 얻었다.** "
        "원래24 service 및 교통 ID,6 MESS unit을 유지했다. 추가 CT·STA·차량을 만들지 않았다. 이 파일은 "
        "공통 기하 조건의 첫 feasible witness이며, 아직 AC controllability 점수로 고른 최종 연구 시나리오가 아니다.\n",
        f"전체24 지점에 회전 **{fit['rotation_degrees']:.9f}°**, 양의 공통 배율 **{fit['uniform_scale']:.12f}**, "
        f"하나의 평행이동을 적용했다. determinant={det:.12g}>0이다. Reflection,개별 지점 회전·좌표 이동, "
        "공차 변경을 사용하지 않았다. 사전 동결한1m 공차에서66 AIDC–AIDC,144 AIDC–STA,66 STA–STA "
        "쌍의552개 strict 축 관계가 모두 PASS이며,24 PCC bus가 서로 다르다.\n",
        "LV 후보의 좌표는 **상위 primary bus의 원본 좌표를 사용한 proxy**이다. Source의 X/SX 오프셋은 "
        "고객측 위치의 survey가 아니다. 원본DSS CRS·좌표 단위·true east/north도 인증되지 않았다. "
        "따라서 판정은 `ASSUMED_PROXY_DIRECTION_PASS`이며, 실측 지리 방향을 보장하지 않는다. "
        "중복 primary 좌표는 동일 좌표로 처리했고 strict pair 순서를 인위적으로 벌리지 않았다.\n",
        f"위치 residual은 평균 **{checked['mean_layout_equivalent_error_km']:.6f}**, "
        f"RMS **{checked['rms_layout_equivalent_error_km']:.6f}**, 최대 **{checked['maximum_layout_equivalent_error_km']:.6f}** "
        "layout-equivalent km이다. 실제 도로 거리·지리 오차나 거리 최적성을 뜻하지 않는다.\n",
        "후보는606개 독립 source audit MV host와1177개 원본 customer-side LV bus 전체이다. "
        "AIDC에는 원본 host 제외·12.47kV·연속ABC·q05 root guard를 유지했다. Split-phase LV STA에는 "
        "원본 서비스 transformer와triplex 경로 및 customer-side terminal을 확인한다. LV를3상 "
        "ABC terminal로 잘못 취급하지 않는다.\n",
        "현재 사용자는 현장 실측 근거가 없는 조건에서 **시뮬레이션 기반 재설계 포트 연구를 허용했다**. "
        "따라서 field qualification의 부재를 연구 중단 gate로 다시 적용하지 않는다. "
        "연구용 PCS/보호/절연/DC–DC/BMS·정격·derating·접근/접속 시간의 가정을 별도로 공개하고, "
        "원본 CT·triplex·전압·전류·reverse power와 실제 선택 포트의 P/Q AC 제약을 검사해야 한다. "
        "차량450kW/600kVA를 각 LV 포트의 허용 정격으로 옮기지 않는다. 연구 승인과 Production/현장 인증은 다르다.\n",
        "탐색 전에 `GEOMETRY_PREREGISTRATION.json`으로 단계·전체 domain·각도·분기·12초/20000 node 한도를 "
        "동결했다.135°를 먼저 시도한 이유는 이전의 기하 witness이며 AC 성능이 아니다.135°의 "
        "all-LV STA 시도는 시간 한도로UNKNOWN이고, 다음 원래v3 fit 각도에서22 search node로 "
        "all-LV witness를 얻었다. 한도 결과를 전체 transform family infeasible로 바꾸지 않는다. "
        "점수 입력을 읽지 않았고 B0/B1/B2/B3/AC sensitivity로 이 witness를 선택하지 않았다.\n",
        "다음 단계는 별도 사전 동결한 ex-ante controllability 점수·위치별 실제 모델 P/Q 상한으로 "
        "공동 재선정하고, 최종 선택 포트에서 실제 AC를 검사하는 것이다. 현재 geometry_first witness의 "
        "score-selection 및 연구 case freeze 상태는 PENDING이다. Native/full model은 실행하지 않았다.\n",
        "재현: `.runtime/Scripts/python.exe -m ieee8500_v42.joint_geometry_v3 --verify --root .`. "
        "이 명령은 solver를 호출하지 않고 원본 coordinate/proxy/traffic에서552축을 직접 재검산하며 "
        "`DIRECT_552_AXIS_VERIFICATION.csv`와 `GEOMETRY_VERIFICATION.json`을 출력한다.\n",
        f"Witness SHA256: `{checked['witness_sha256']}`.\n",table]
    (output/"GEOMETRY_STUDY_DIAGNOSTIC_KO.md").write_text("\n".join(report),encoding="utf-8")
    return checked


def plot_geometry(root: Path, output: Path | None=None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .plots import label_sites
    root=root.resolve();output=output or root/DOCS/"joint_selection_v3/geometry_first"
    checked=verify_geometry(root,output);rows=read_csv(output/"JOINT_SERVICE_MAPPING.csv")
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    traffic={a["location_id"]:traffic_xy(a) for a in anchors}
    common={r["location_id"]:(float(r["common_frame_x_km"]),float(r["common_frame_y_km"])) for r in rows}
    pts=list(traffic.values())+list(common.values());bounds=[(min(p[k] for p in pts)-3,max(p[k] for p in pts)+3) for k in (0,1)]
    fig,axs=plt.subplots(1,2,figsize=(16,9),sharex=True,sharey=True)
    for panel,locations in enumerate((traffic,common)):
        ax=axs[panel]
        for role,marker,color in (("AIDC","o","#b92532"),("STA","s","#1262ad")):
            p=[locations[a["location_id"]] for a in anchors if a["role"]==role]
            ax.scatter([v[0] for v in p],[v[1] for v in p],s=55,marker=marker,c=color,zorder=4,
                label=f"12 {role}: "+("traffic anchors" if panel==0 else "MV hosts" if role=="AIDC" else "LV primary-coordinate proxies"))
        ax.set_xlim(*bounds[0]);ax.set_ylim(*bounds[1]);ax.set_aspect("equal");ax.grid(alpha=.15)
        ax.set_title("Original traffic east / north anchors" if panel==0 else f"One common {checked['rotation_degrees']:.3f}° proper similarity",fontsize=12)
        ax.set_xlabel("Traffic east (km)" if panel==0 else "Common X (layout equivalent km)")
        ax.legend(loc="lower left",fontsize=8)
    axs[0].set_ylabel("Traffic north / common Y (km / layout equivalent km)")
    fig.suptitle("Modeled LV port study: assumed proxy direction pass\n"
        "12 LV STA + 12 guarded MV AIDC; all276 pairs /552 strict axes pass",fontsize=16)
    fig.text(.5,.025,f"Residual RMS={checked['rms_layout_equivalent_error_km']:.3f} layout equivalent km; original CRS/geographic units unverified.\n"
        "LV locations are upstream-primary proxies. Ex-ante score selection and actual selected-port AC remain pending; Production is not certified.",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.13,1,.90))
    for ax,locations in zip(axs,(traffic,common)):label_sites(ax,anchors,locations)
    for ext in ("png","svg"):fig.savefig(output/f"GEOMETRY_STUDY_WITNESS.{ext}",dpi=180,bbox_inches="tight")
    plt.close(fig)


def freeze_score_policy(root: Path) -> dict:
    """Freeze selection method before consuming candidate-score CSV values."""
    root=root.resolve();docs=root/DOCS;output=docs/"joint_selection_v3/score_selection"
    output.mkdir(parents=True,exist_ok=True);seed=docs/"joint_selection_v3/geometry_first"
    geometry=json.loads((seed/"GEOMETRY_RESULT.json").read_text())
    if not geometry["geometric_feasibility"] or geometry["STA_LV_count"]!=12:
        raise ValueError("All12-LV source geometry witness required before score phase")
    score_policy=docs/"joint_selection_v3/selection_scores/PREREGISTRATION.json"
    hardware=docs/"LV_PORT_SIMULATION_DESIGN.json"
    if not score_policy.exists() or not hardware.exists():raise ValueError("Root score/port model preregistration required")
    policy={"schema":"CURRENT_V3_EX_ANTE_JOINT_SELECTION_METHOD",
        "method_frozen_before_score_CSV_values_observed":True,
        "score_values_consumed_at_freeze":False,"B1_B2_B3_outcomes_used":False,
        "root_score_policy_sha256":sha256(score_policy),"modeled_LV_port_design_sha256":sha256(hardware),
        "geometry_seed_witness_sha256":sha256(seed/"JOINT_SERVICE_MAPPING.csv"),
        "geometry_preregistration_sha256":sha256(seed/"GEOMETRY_PREREGISTRATION.json"),
        "selected_transform":geometry["proper_common_transform"],
        "transform_choice_basis":"previous geometry-only allLV witness; not tuned to AC scores",
        "source_domains":"all606 MV for each AIDC, all1177 LV for each STA; all12LV feasibility already shown",
        "MV_STA_fallback":"not needed in this stage since12LV witnesses exist; no claim other fallback allocations globally inferior",
        "services":24,"AIDC_services":12,"STA_services":12,"MESS_units":6,"additional_CT_or_STA_or_units":0,
        "required_pairs":276,"required_strict_axis_signs":552,"near_pair_and_axis_tolerance_km":.001,
        "score_CSV_schema":"location_id,role,candidate_bus,score,score_source plus root power/relaxation metadata",
        "required_complete_site_candidate_rows":21396,"no_missing_candidate_score_imputation":True,
        "root_score_eligibility":"declared source/modeling relaxation; field availability certification false is metadata, not study hardstop",
        "score_objective":"sum root-supplied site-specific signed development-surrogate scores, rounded12 decimal places",
        "STA_modeled_scoring_ceiling":"P5kW,Q from[-3,0,3]kvar common20line vector, S6kVA, eachhot27A; actual AC check follows",
        "AIDC_score_scope":"root known-original-UID power bound, PF.95 coupled P/Q; uncertified relaxation, no idle/anonymousCC4 power credited",
        "routing_fleet_scope":"root unchanged original6 initial vehicles, safeETA plus600s; heuristic exposure is not simultaneous dispatch guarantee",
        "selection_algorithm":"deterministic full-role-domain1site best-improvement, then2site joint best-improvement",
        "iteration_order":"fixed original service order; original source candidate order; gain ties retain first deterministic candidate",
        "candidate_equal_score_order":"squared common-frame anchor distance then lexical bus; old spacing remains separate audit",
        "maximum_accepted_exchanges":100,"two_site_pair_evaluation_limit":500000,
        "termination":"no improvement=>one/two-site local optimum; declared budget exhaustion=>bounded selection only",
        "global_optimality_or_whole_transform_family_claim":False,"KNN_domain_truncation":False,
        "all_moves_guarded":"original source eligibility, role domains,24 distinct buses, all552 strict directions",
        "geometry_authority":"ASSUMED_PROXY_DIRECTION_PASS: LV upstream-primary proxy, not surveyed customer geography",
        "field_evidence_required_for_simulated_study":False,"simulation_redesigned_ports_authorized":True,
        "physical_AC_and_job_QoS_SOC_access_constraints":"root must verify at final selected study configuration; derivative surrogate cannot certify them",
        "study_freeze_authorized_after_all_modeled_eligibility":True,"Production_certified":False,
        "score_input_binding":"bind completed root scoreCSV/receipt SHA before reading values; reject incomplete/changed policy or inputs",
        "Native_calls":0,"algorithm_module_sha256":sha256(Path(__file__))}
    path=output/"SCORING_PREREGISTRATION.json"
    if path.exists() and json.loads(path.read_text())!=policy:
        raise ValueError("Score selection preregistration immutable: explicit revision needed")
    if not path.exists():path.write_text(json.dumps(policy,indent=2)+"\n",encoding="utf-8")
    return policy


def score_search(root: Path) -> dict:
    """Apply root-frozen complete scores to the preregistered local selector."""
    root=root.resolve();docs=root/DOCS;output=docs/"joint_selection_v3/score_selection"
    policy=freeze_score_policy(root)
    if (output/"SCORE_SELECTION_RESULT.json").exists():
        raise ValueError("Score-selected result exists; do not silently rerun selection")
    input_folder=docs/"joint_selection_v3/selection_scores";scorefile=input_folder/"CANDIDATE_SELECTION_SCORES.csv"
    receipt_path=input_folder/"RECEIPT.json"
    if not scorefile.exists() or not receipt_path.exists():raise ValueError("Complete root candidate-score CSV/receipt not ready")
    receipt=json.loads(receipt_path.read_text())
    if receipt["status"]!="COMPLETE_DEVELOPMENT_SURROGATE_NOT_DISPATCH":raise ValueError("Root score calculation incomplete")
    binding={"candidate_scores_sha256":sha256(scorefile),"root_receipt_sha256":sha256(receipt_path),
        "root_score_policy_sha256":sha256(input_folder/"PREREGISTRATION.json"),
        "modeled_LV_port_design_sha256":sha256(docs/"LV_PORT_SIMULATION_DESIGN.json")}
    if binding["root_score_policy_sha256"]!=policy["root_score_policy_sha256"] or binding["modeled_LV_port_design_sha256"]!=policy["modeled_LV_port_design_sha256"]:
        raise ValueError("Frozen root score/port model policy changed")
    path=output/"SCORE_INPUT_SHA256.json"
    if path.exists() and json.loads(path.read_text())!=binding:raise ValueError("Bound candidate-score input changed")
    if not path.exists():path.write_text(json.dumps(binding,indent=2)+"\n",encoding="utf-8")
    # First reading of score values occurs only after immutable method/input pins.
    candidates,source_inputs=load_candidates(root)
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    by_bus={c["bus"]:j for j,c in enumerate(candidates)};by_site={a["location_id"]:k for k,a in enumerate(anchors)}
    raw=read_csv(scorefile)
    if len(raw)!=21396:raise ValueError("Complete12*606 AIDC+12*1177 STA score rows required")
    scores=[{} for _ in anchors];metadata=[{} for _ in anchors]
    for row in raw:
        site=row["location_id"];a=by_site[site];j=by_bus[row["candidate_bus"].lower()]
        if row["role"]!=anchors[a]["role"] or j in scores[a]:raise ValueError("Score site/role duplication mismatch")
        if (anchors[a]["role"]=="AIDC")!=(candidates[j]["mode"]=="MV_MODELED_PORT"):
            raise ValueError("Root score candidate outside complete role domain")
        if not row["score_source"]:raise ValueError("Root score provenance required")
        scores[a][j]=float(row["score"]);metadata[a][j]=row
    mv=[j for j,c in enumerate(candidates) if c["mode"]=="MV_MODELED_PORT"]
    lv=[j for j,c in enumerate(candidates) if c["mode"].startswith("LV")]
    allowed=[mv if a["role"]=="AIDC" else lv for a in anchors]
    if any(set(row)!=set(domain) for row,domain in zip(scores,allowed)):raise ValueError("Every role candidate score required")
    seed_folder=docs/"joint_selection_v3/geometry_first"
    if sha256(seed_folder/"JOINT_SERVICE_MAPPING.csv")!=policy["geometry_seed_witness_sha256"]:
        raise ValueError("Frozen geometry seed changed")
    seed={r["location_id"]:candidates[by_bus[r["candidate_bus"]]] for r in read_csv(seed_folder/"JOINT_SERVICE_MAPPING.csv")}
    fit=policy["selected_transform"]
    answer=score_guided_exchanges(anchors,candidates,fit,seed,scores,allowed,
        policy["maximum_accepted_exchanges"],policy["two_site_pair_evaluation_limit"])
    result={"schema":"CURRENT_V3_SCORE_SELECTED_MODELED_STUDY_RESULT","status":"SCORE_SELECTED_PROXY_GEOMETRY_PASS_AC_PENDING",
        "geometric_feasibility":True,"proper_common_transform":fit,"AC_score_used":True,
        "score_stage":"root-frozen development surrogate, not actual dispatch or B3 performance",
        "score_input_binding":binding,"source_input_sha256":source_inputs,
        "scoring_preregistration_sha256":sha256(output/"SCORING_PREREGISTRATION.json"),
        "initial_joint_score":answer["initial_joint_score"],"selected_joint_score":answer["selected_joint_score"],
        "score_increase":answer["score_increase"],"exchanges":answer["exchanges"],
        "two_site_pair_evaluations":answer["two_site_pair_evaluations"],"budget_exhausted":answer["budget_exhausted"],
        "one_two_site_local_optimum":answer["one_two_site_local_optimum"],"global_optimality_claim":False,
        "full606_MV_and1177_LV_each_site_scores_used":True,"Native_calls":0,"B1_B2_B3_outcomes_used":False,
        "simulation_port_redesign_authorized":True,"field_evidence_required_for_study":False,
        "Production":False,"study_case_frozen":False,"selected_port_actual_AC_gate":"PENDING"}
    # Inherited geometry contract is preserved byte-for-byte and independently
    # verifiable; current score provenance is a separate immutable preregistration.
    (output/"GEOMETRY_PREREGISTRATION.json").write_bytes((seed_folder/"GEOMETRY_PREREGISTRATION.json").read_bytes())
    export_mapping(output,anchors,answer["selected"],fit,result)
    port=json.loads((docs/"LV_PORT_SIMULATION_DESIGN.json").read_text())
    selected_scores=[]
    for a,anchor in enumerate(anchors):
        c=answer["selected"][anchor["location_id"]];row=metadata[a][by_bus[c["bus"]]]
        selected_scores.append(dict(row,rounded_selection_score=round(float(row["score"]),12),
            original_traffic_node_id=anchor["traffic_node"],coordinate_authority=c["coordinate_authority"],
            study_STA_S_ceiling_kva=port["S_max_kva"] if anchor["role"]=="STA" else "",
            study_STA_hot_current_ceiling_A=port["I_each_hot_max_A"] if anchor["role"]=="STA" else "",
            actual_modeled_port_AC_or_dispatch_certified=False))
    write_csv(output/"SELECTED_CONTROLLABILITY_SCORES.csv",selected_scores)
    # Fill declared model ceilings separately from still-pending AC allowances.
    mapping=read_csv(output/"JOINT_SERVICE_MAPPING.csv")
    for row in mapping:
        a=by_site[row["location_id"]];c=answer["selected"][row["location_id"]];info=metadata[a][by_bus[c["bus"]]]
        row["modeled_allowed_P_kw"]="PENDING_SELECTED_PORT_AC";row["modeled_allowed_Q_kvar"]="PENDING_SELECTED_PORT_AC"
        row["is_final_controllability_selection"]="True_LOCAL_SURROGATE_ONLY"
        row["development_surrogate_score"]=round(float(info["score"]),12);row["score_source"]=info["score_source"]
        row["AIDC_known_only_flexible_P_upper_bound_kw"]=info["flexibility_upper_bound_kw"]
        row["study_port_P_ceiling_kw"]=info["vehicle_port_P_kw"];row["study_port_Q_abs_ceiling_kvar"]=info["vehicle_port_Q_kvar"]
    write_csv(output/"JOINT_SERVICE_MAPPING.csv",mapping)
    write_csv(output/"AIDC_MAPPING.csv",[r for r in mapping if r["role"]=="AIDC"])
    write_csv(output/"STA_MAPPING.csv",[r for r in mapping if r["role"]=="STA"])
    result["witness_sha256"]=sha256(output/"JOINT_SERVICE_MAPPING.csv")
    result["files_sha256"]={name:sha256(output/name) for name in ("JOINT_SERVICE_MAPPING.csv","AIDC_MAPPING.csv","STA_MAPPING.csv",
        "RELATIVE_POSITION_AUDIT.csv","SCORING_PREREGISTRATION.json","SELECTED_CONTROLLABILITY_SCORES.csv")}
    (output/"GEOMETRY_RESULT.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    result["independent_direct_geometry_verification"]=verify_geometry(root,output,write_report=False)
    (output/"SCORE_SELECTION_RESULT.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    table="| 서비스 | traffic | 선택bus | frozen score |\n|---|---|---|---|\n"+"".join(
        f"| {r['location_id']} | {r['traffic_node_id']} | {r['candidate_bus']} | {float(r['development_surrogate_score']):.9g} |\n" for r in mapping)
    report=["# 현재V3: 사전 점수 기반 공동 후보 선택\n",
        "**원본12 AIDC와12 LV STA service ID를 유지하면서 사전 동결된 개발일 controllability surrogate로 공동 후보를 선택했다.** "
        "6 MESS unit과 원본CT/Triplex/정격/자동 제어를 확대하지 않았다. 이 단계는 최종 연구 case의 실제AC·QoS·SOC·배차 "
        "적격성을 대체하지 않으며 Production 인증을 주장하지 않는다.\n",
        f"기하 seed 점수 {answer['initial_joint_score']:.12g}에서 선택 점수 **{answer['selected_joint_score']:.12g}**로 "
        f"{answer['score_increase']:.12g} 증가했다. 허용된 원본606MV/AIDC 및1177LV/STA를 각12서비스에서 모두 읽고 "
        "site-specific score를 사용했다. Source/role guard,24 distinct bus,552 strict 방향을 모든 이동에서 유지했고 "
        "원본 input과 공통 matrix로 직접 재검증했다. 모든STA는LV upstream-primary coordinate proxy이며 "
        "`ASSUMED_PROXY_DIRECTION_PASS`이다.\n",
        f"공통 회전은 geometry-only seed에서 이미 선택한 **{fit['rotation_degrees']:.9f}°**로 유지했다. "
        "점수나B3 성능으로 회전·공차·개별 좌표를 조정하지 않았다. 알고리즘은 전체 role domain의1site "
        "최선 개선 후2site 공동 개선을 반복했다. "
        +("1/2-site local optimum에 도달했다. " if answer['one_two_site_local_optimum'] else "선언한 계산 한도에서 중단한 bounded 결과이다. ")
        +"전체 combinatorial/global transform-family 최적성은 주장하지 않는다.\n",
        "점수 의미는 부모의 `selection_scores/PREREGISTRATION.json`을 그대로 따른다. 개발일4시간×20원본 선로의 "
        "signed 전류반응에 AIDC known-original-UID activeGPU/C1 swing/PF.95 상한, STA5kW/3kvar 공통 Q vector, "
        "6차량/12STA exposure 및 원본 초기 위치 safeETA+600s를 반영한 heuristic이다. AIDC 상한은 "
        "전체QoS/WAN job dispatch를 인증한 실제 flexibility가 아니며, STA exposure는 동시12dock 사용 또는 "
        "실제route 보장이 아니다. anonymousCC4/idle credit, B1/B2/B3 성과나 hidden-day claim을 추가하지 않았다.\n",
        "[저압 연구 포트 설계](../../LV_PORT_SIMULATION_DESIGN.md)의 P±5kW,Q±3kvar,S6kVA,eachhot27A "
        "및 실제|V1−V2|에 따른 current ceiling은 개별/합성 실제AC에서 다시 검사해야 한다. 원본 CT winding·Triplex "
        "모든conductor·전압·reverse power를 유지하고, Q/PCS/DC–DC/BMS·접속 효율/지연 가정을 공개한다. "
        "Field 근거 부재는 사용자 허용 연구를 중단시키지 않는다. Study freeze는 최종 모델 적격성 통과 후 부모가 수행하며 "
        "현재 선택 파일은 AC PENDING이다.\n",
        f"Witness SHA256: `{result['witness_sha256']}`. "
        "선택 방법은 score CSV 값을 보기 전에 `SCORING_PREREGISTRATION.json`으로 동결했고, "
        "입력CSV·root receipt·score policy·hardware model SHA는 `SCORE_INPUT_SHA256.json`에 있다.\n",table]
    (output/"SCORE_SELECTION_REPORT_KO.md").write_text("\n".join(report),encoding="utf-8")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,default=Path("."))
    mode=parser.add_mutually_exclusive_group();mode.add_argument("--verify",action="store_true");mode.add_argument("--plot",action="store_true")
    mode.add_argument("--freeze-score-policy",action="store_true");mode.add_argument("--select-scores",action="store_true")
    args=parser.parse_args()
    if args.plot:plot_geometry(args.root);answer={"status":"PLOTTED_VERIFIED_WITNESS"}
    elif args.freeze_score_policy:answer=freeze_score_policy(args.root)
    elif args.select_scores:answer=score_search(args.root)
    else:answer=verify_geometry(args.root) if args.verify else geometry_search(args.root)
    print(json.dumps({k:v for k,v in answer.items() if k!="attempts"},indent=2))
