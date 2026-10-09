"""Read-only provenance of selected modeled-port actions; never reselects.

The root-frozen scores already include original local AC-linear margins. Nominal
5kW/3kvar port ceilings are not all-host/all-time actions or dispatch certificates.
"""
import argparse
import itertools
import json
import math
from pathlib import Path

from .geometry import read_csv, sha256, write_csv
from .joint_geometry_v3 import DOCS, verify_geometry


def run(root: Path) -> dict:
    root=root.resolve();docs=root/DOCS;folder=docs/"joint_selection_v3/score_selection"
    policy=json.loads((folder/"SCORING_PREREGISTRATION.json").read_text())
    binding=json.loads((folder/"SCORE_INPUT_SHA256.json").read_text())
    sourcefolder=docs/"joint_selection_v3/selection_scores"
    # Keep the pre-selection receipt pin immutable. A later topology-only
    # metadata correction must verify its exact archived original bytes and
    # the restricted amendment chain; arbitrary receipt changes are rejected.
    current_receipt=sourcefolder/"RECEIPT.json"
    if sha256(current_receipt)==binding["root_receipt_sha256"]:
        receipt_binding={"status":"PASS_UNCHANGED_ORIGINAL_RECEIPT_PIN",
            "root_receipt_sha256":binding["root_receipt_sha256"]}
    else:
        from .archive_path_pin_chain import verify_chain
        receipt_binding=verify_chain(root)
    sourcepolicy=sourcefolder/"PREREGISTRATION.json"
    if sha256(sourcepolicy)!=binding["root_score_policy_sha256"] or sha256(sourcepolicy)!=policy["root_score_policy_sha256"]:
        raise ValueError("Root action-source policy changed from before-score pin")
    authoritative=json.loads(sourcepolicy.read_text())
    actionfile=sourcefolder/"STA_SCORE_MOBILITY_AND_Q.csv"
    if not actionfile.exists():raise ValueError("Root all-host local-action provenance not ready")
    rootactions=read_csv(actionfile);mapping=read_csv(folder/"JOINT_SERVICE_MAPPING.csv")
    selected={(r["location_id"],r["candidate_bus"]):r for r in mapping if r["role"]=="STA"}
    scores={(r["location_id"],r["candidate_bus"]):r for r in read_csv(folder/"SELECTED_CONTROLLABILITY_SCORES.csv")}
    slots=authoritative["slots"];actions=[]
    for row in rootactions:
        key=(row["location_id"],row["candidate_bus"])
        if key not in selected:continue
        p=float(row["P_design_choice_kw"]);q=float(row["Q_design_choice_kvar"])
        if p<0 or p>5 or abs(q)>3 or math.hypot(p,q)>6:
            raise ValueError("Root selected action outside nominal study interface ceiling")
        predicted=float(row["potential_score_before_mobility"])
        weighted=predicted*float(row["initial_fleet_reachable_fraction"])*float(row["fleet_exposure_factor"])
        if abs(weighted-float(row["weighted_score"]))>1e-12:raise ValueError("Root mobility/exposure weight mismatch")
        actions.append(dict(row,nominal_P_ceiling_kw=5.,nominal_Q_abs_ceiling_kvar=3.,nominal_S_ceiling_kva=6.,
            nominal_hot_current_ceiling_A=27.,actual_nonlinear_selected_port_AC_certified=False,
            simultaneous_vehicle_dispatch_certified=False,field_port_or_geography_certified=False,
            action_authority="original local AC-linear voltage/CT/Triplex intervals, not blanket nominal power",
            original_service_transformer=selected[key]["original_service_transformer"],
            original_transformer_kva=selected[key]["original_transformer_kva"],
            original_triplex_normal_amps=selected[key]["original_triplex_normal_amps"]))
    if len(actions)!=48 or len({(r["location_id"],int(r["slot"])) for r in actions})!=48:
        raise ValueError("Exact12STA*4time selected action coverage required")
    for site,bus in selected:
        group=[r for r in actions if (r["location_id"],r["candidate_bus"])==(site,bus)]
        if {int(r["slot"]) for r in group}!=set(slots):raise ValueError("Original score time-axis coverage mismatch")
        actual=sum(float(r["weighted_score"]) for r in group)/len(slots)
        if abs(actual-float(scores[(site,bus)]["score"]))>1e-12:raise ValueError("Selected action score does not reproduce root CSV")
    actions=sorted(actions,key=lambda r:(r["location_id"],int(r["slot"])))
    write_csv(folder/"SELECTED_STA_SCORE_ACTIONS.csv",actions)
    original_text=policy["STA_modeled_scoring_ceiling"]
    explanation={"status":"AUTHORITATIVE_PRE_SCORE_ROOT_LOCAL_BOUNDS_VERIFIED",
        "original_receipt_and_metadata_amendment_binding":receipt_binding,
        "no_selection_rerun":True,"mapping_scores_algorithm_and_preregistration_unchanged":True,
        "root_policy_sha256_pinned_before_score_values":binding["root_score_policy_sha256"],
        "selection_method_nominal_ceiling_description":original_text,
        "nominal_ceiling_description_interpretation":"hardware ceiling only; not action at every host/time or actual allowed output",
        "authoritative_STA_action":authoritative["STA_action"],"authoritative_STA_actions":authoritative["STA_actions"],
        "local_bound_certification":authoritative["local_bound_certification"],
        "selected_action_rows":48,"all_selected_root_scores_reproduced":True,
        "maximum_selected_P_kw":max(float(r["P_design_choice_kw"]) for r in actions),
        "maximum_selected_abs_Q_kvar":max(abs(float(r["Q_design_choice_kvar"])) for r in actions),
        "zero_action_rows":sum(float(r["P_design_choice_kw"])==0 and float(r["Q_design_choice_kvar"])==0 for r in actions),
        "source_action_csv_sha256":sha256(actionfile),"selected_action_csv_sha256":sha256(folder/"SELECTED_STA_SCORE_ACTIONS.csv"),
        "witness_sha256":sha256(folder/"JOINT_SERVICE_MAPPING.csv"),
        "actual_AC_or_dispatch_feasibility_claim":False,"Production":False,"Native_calls":0}
    (folder/"SCORING_SOURCE_BINDING_CLARIFICATION.json").write_text(json.dumps(explanation,indent=2)+"\n",encoding="utf-8")
    verify_geometry(root,folder,write_report=False)
    # Historical dispersion metrics stay visible, separate from current hard
    # direction guards. The old scalar ABC tree is not extended into split-phase
    # service paths by inventing an impedance convention.
    from .mv_candidates import build_candidates
    candidate_set=build_candidates(root)
    mv={r["dss_bus"]:r for r in read_csv(docs/"MV_AIDC_CANDIDATES.csv")}
    guarded=[]
    for row in mapping:
        if row["role"]!="AIDC":continue
        authority=mv[row["candidate_bus"]]
        if authority["electrical_host_eligible"].lower()!="true" or authority["source_proximity_guard_pass"].lower()!="true":
            raise ValueError("Selected AIDC source guard failed")
        guarded.append(dict(location_id=row["location_id"],traffic_node_id=row["traffic_node_id"],
            selected_bus=row["candidate_bus"],nominal_kv_ll=authority["nominal_kv_ll"],phase_nodes=authority["phase_nodes"],
            continuous_abc_from_feeder_head=authority["continuous_abc_from_feeder_head"],
            source_substation_regulator_exclusion_pass=authority["source_substation_regulator_exclusion_pass"],
            root_distance_ohm=authority["root_distance_ohm"],original_q05_guard_ohm=authority["root_distance_q05_guard_ohm"],
            source_proximity_guard_pass=authority["source_proximity_guard_pass"],electrical_host_eligible=authority["electrical_host_eligible"],
            field_port_qualified=False,simulation_port_design_authorized=True,
            root_score_known_UID_flexibility_is_certified=False,selected_actual_AC_or_job_dispatch_certified=False))
    write_csv(folder/"AIDC_SOURCE_GUARD_AUDIT.csv",guarded)
    dispersion=[]
    for a,b in itertools.combinations(mapping,2):
        pa=(float(a["source_or_proxy_x"]),float(a["source_or_proxy_y"]))
        pb=(float(b["source_or_proxy_x"]),float(b["source_or_proxy_y"]))
        distance=math.dist(pa,pb)
        metric={"electrical_tree_distance_ohm":"","shared_upstream_path_ratio":"",
            "original_electrical_dispersion_gate_pass":"NOT_DEFINED_ON_ORIGINAL_ABC_TREE_FOR_THIS_LV_PROXY"}
        primary_a=a["upstream_primary_bus"];primary_b=b["upstream_primary_bus"]
        if primary_a in candidate_set.coordinates and primary_b in candidate_set.coordinates:
            value=candidate_set.pair_metrics(primary_a,primary_b)
            metric={name:value[name] for name in metric}
        dispersion.append(dict(location_a=a["location_id"],location_b=b["location_id"],
            role_pair="-".join(sorted([a["role"],b["role"]])),candidate_bus_a=a["candidate_bus"],candidate_bus_b=b["candidate_bus"],
            upstream_primary_a=primary_a,upstream_primary_b=primary_b,
            source_or_primary_proxy_xy_distance_unknown_units=distance,
            old_xy_dispersion_threshold_unknown_units=2221.532547954318,
            old_xy_dispersion_gate_pass=distance>=2221.532547954318,
            old_electrical_dispersion_threshold_ohm=.9129072401559803,**metric,
            metric_role="HISTORICAL_DISPERSION_AUDIT_NOT_PHYSICAL_OR_GEOGRAPHIC_INTERCONNECTION_LIMIT",
            whole_LV_service_impedance_distance_claim=False))
    write_csv(folder/"OLD_PAIR_DISPERSION_AUDIT.csv",dispersion)
    reportpath=folder/"SCORE_SELECTION_REPORT_KO.md"
    before=folder/"SCORE_SELECTION_REPORT_BEFORE_ACTION_PROVENANCE_CLARIFICATION.md"
    if not before.exists():before.write_bytes(reportpath.read_bytes())
    text=reportpath.read_text(encoding="utf-8")
    text=text.replace("STA5kW/3kvar 공통 Q vector", "STA5kW/3kvar hardware ceiling 안에서 원본 local AC-linear margin으로 제한한 P-only/Q-only/mixed-half 공통 P/Q vector")
    detail="\n`vehicle_port_P_kw=5` / `vehicle_port_Q_kvar=3`는 명목 model ceiling이며 실제 점수의 매 host/time action이 아니다. "
    detail+="Score CSV 값을 읽기 전에 동결한 root policy SHA와 실제 score의 원본 local CT/Triplex/PCC voltage bound가 일치한다. "
    detail+="48개 선택 STA×time의 실제 `P_design_choice_kw` / `Q_design_choice_kvar`, safeETA reachability, fleet exposure 및 weighted score는 "
    detail+="`SELECTED_STA_SCORE_ACTIONS.csv`에 그대로 보존했다. P-only는 local positive-P bound, Q-only는 local signed-Q bound, "
    detail+="mixed는 각 axis-only bound의 절반인 convex-combination screen이다. 모든20 target 선로에 같은 P/Q vector를 적용했고 "
    detail+="이48개 값으로 선택된 STA root score를 재계산해 모두 일치했다. 이는 settled-control 1차 screen이며 실제 nonlinear96slot "
    detail+="AC·동시 dispatch를 인증하지 않는다. 이 clarification으로 mapping·score·선택 알고리즘·원래 prereg를 변경하거나 재선정하지 않았다.\n"
    if "`vehicle_port_P_kw=5`" not in text:text+=detail
    reportpath.write_text(text,encoding="utf-8")
    return explanation


def plots(root: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .geometry import traffic_xy
    from .plots import label_sites, source_edges, source_projection, draw_network
    root=root.resolve();docs=root/DOCS;folder=docs/"joint_selection_v3/score_selection"
    checked=verify_geometry(root,folder,write_report=False)
    result=json.loads((folder/"SCORE_SELECTION_RESULT.json").read_text())
    mapping=read_csv(folder/"JOINT_SERVICE_MAPPING.csv")
    anchors=json.loads((root/"ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json").read_text())
    traffic={a["location_id"]:traffic_xy(a) for a in anchors}
    common={r["location_id"]:(float(r["common_frame_x_km"]),float(r["common_frame_y_km"])) for r in mapping}
    pts=list(traffic.values())+list(common.values());bounds=[(min(p[k] for p in pts)-3,max(p[k] for p in pts)+3) for k in (0,1)]
    fig,axs=plt.subplots(1,2,figsize=(16,9),sharex=True,sharey=True)
    for panel,locations in enumerate((traffic,common)):
        ax=axs[panel]
        for role,marker,color in (("AIDC","o","#b92532"),("STA","s","#1262ad")):
            p=[locations[a["location_id"]] for a in anchors if a["role"]==role]
            ax.scatter([v[0] for v in p],[v[1] for v in p],s=55,marker=marker,c=color,zorder=4,
                label=f"12 {role}: "+("traffic anchors" if panel==0 else "MV hosts" if role=="AIDC" else "LV upstream-primary proxies"))
        ax.set_xlim(*bounds[0]);ax.set_ylim(*bounds[1]);ax.set_aspect("equal");ax.grid(alpha=.15)
        ax.set_title("Original traffic east / north anchors" if panel==0 else f"One common {checked['rotation_degrees']:.3f}° proper similarity",fontsize=12)
        ax.set_xlabel("Traffic east (km)" if panel==0 else "Common X (layout equivalent km)")
        ax.legend(loc="lower left",fontsize=8)
    axs[0].set_ylabel("Traffic north / common Y (km / layout equivalent km)")
    fig.suptitle("Frozen development-surrogate joint selection: assumed proxy directions pass\n"
        "12 LV STA + 12 guarded MV AIDC; all276 pairs /552 strict axes pass",fontsize=16)
    fig.text(.5,.025,f"Residual RMS={checked['rms_layout_equivalent_error_km']:.3f} layout equivalent km; original geographic CRS/units unverified.\n"
        "One/two-site local selection; global optimality, nonlinear AC, dispatch, QoS, SOC, and Production are not certified by this figure.",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.13,1,.90))
    for ax,locations in zip(axs,(traffic,common)):label_sites(ax,anchors,locations)
    for ext in ("png","svg"):fig.savefig(folder/f"SCORE_SELECTED_TRAFFIC_PCC_MAP.{ext}",dpi=180,bbox_inches="tight")
    plt.close(fig)
    # Original feeder display keeps native X/Y orientation. Actual source SX
    # terminal coordinates here are explicitly schematic; proxy direction proof
    # uses the separate common-frame panel above, not these source offsets.
    edges,source=source_edges(root/"ieee8500_v42/data/feeder")
    xy,note=source_projection(source)
    fig,ax=plt.subplots(figsize=(12,10));draw_network(ax,edges,xy,alpha=.3,legend=True)
    source_locations={r["location_id"]:xy[r["candidate_bus"]] for r in mapping}
    for role,marker,color in (("AIDC","o","#b92532"),("STA","s","#1262ad")):
        selected=[source_locations[r["location_id"]] for r in mapping if r["role"]==role]
        ax.scatter([p[0] for p in selected],[p[1] for p in selected],marker=marker,c=color,s=65,zorder=5,
            label="12 guarded MV AIDC" if role=="AIDC" else "12 selected LV source terminals (schematic SX)")
    ax.margins(.12);ax.legend(loc="upper left",fontsize=8)
    ax.set_title("Original IEEE8500 feeder: current score-selected study PCCs\n"
        "Original X/Y axes retained; source CT/Triplex/rating inventory unchanged",fontsize=15,pad=15)
    fig.text(.5,.025,note+"\nLV SX terminal positions are source schematic placements, not surveys. Direction audit uses upstream-primary proxies in one common frame.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.085,1,.97));label_sites(ax,anchors,source_locations)
    for ext in ("png","svg"):fig.savefig(folder/f"SCORE_SELECTED_ORIGINAL_FEEDER_TOPOLOGY.{ext}",dpi=180,bbox_inches="tight")
    plt.close(fig)
    rows=read_csv(folder/"SELECTED_CONTROLLABILITY_SCORES.csv")
    fig,axs=plt.subplots(2,1,figsize=(13,8),gridspec_kw={"height_ratios":[1,1.3]})
    values=[result["initial_joint_score"]]+[r["joint_objective"] for r in result["exchanges"]]
    axs[0].plot(range(len(values)),values,"o-",color="#435b73",markersize=5)
    for r in result["exchanges"]:
        if len(r["changes"])==2:
            axs[0].scatter(r["iteration"]+1,r["joint_objective"],marker="D",s=60,c="#d28a24",zorder=4)
    axs[0].set_xlabel("Accepted joint exchange (0 = geometry-only seed)")
    axs[0].set_ylabel("Sum of signed weighted\nresponse surrogates (pu)")
    axs[0].grid(alpha=.15)
    axs[0].set_title("Deterministic one/two-site local improvement; diamonds = two-site exchanges",fontsize=11)
    colors=["#b92532" if r["role"]=="AIDC" else "#1262ad" for r in rows]
    axs[1].bar(range(len(rows)),[float(r["score"]) for r in rows],color=colors)
    axs[1].set_xticks(range(len(rows)),[r["location_id"] for r in rows],rotation=55,ha="right")
    axs[1].set_ylabel("Selected site surrogate (pu)");axs[1].axhline(0,c="#555",lw=.6);axs[1].grid(axis="y",alpha=.15)
    axs[1].set_title("Four sampled times × 20 fixed original target lines; source-bound actions and original mobility",fontsize=11)
    fig.suptitle("Development-surrogate selection audit — no dispatch-performance claim",fontsize=15)
    fig.text(.5,.025,"AIDC: known-original-UID power upper bound (uncertified relaxation). STA: local-linear P/Q actions within modeled dock limits.\n"
        "Scores support candidate ranking; their sum is not an achieved reduction of overall system rho.",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.11,1,.93))
    for ext in ("png","svg"):fig.savefig(folder/f"SCORE_SELECTION_PROGRESS.{ext}",dpi=180,bbox_inches="tight")
    plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--plots",action="store_true");args=parser.parse_args()
    if args.plots:plots(args.root);print(json.dumps({"status":"PLOTTED_CURRENT_SCORE_SELECTION"}))
    else:print(json.dumps(run(args.root),indent=2))
