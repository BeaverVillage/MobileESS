"""Selected PCC mapping and four-time sensitivities from existing AC evidence.

This module reads completed original-reference MV tables and LV NPZ outputs. It
never runs AC/Native, reselects locations, changes scores, or updates root reports.
Control potential is an action-weighted local prediction, not achieved systemrho.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np

from .geometry import read_csv, sha256, write_csv
from .joint_geometry_v3 import DOCS, verify_geometry


def time_label(slot: int) -> str:
    minutes=slot*15
    return f"{minutes//60:02d}:{minutes%60:02d}"


def table(rows: list[dict], columns: list[tuple[str,str]]) -> str:
    def escape(value):return str(value).replace("|","\\|").replace("\n","<br>")
    text="| "+" | ".join(escape(label) for _,label in columns)+" |\n"
    text+="|"+"---|"*len(columns)+"\n"
    return text+"".join("| "+" | ".join(escape(row[key]) for key,_ in columns)+" |\n" for row in rows)


def assemble(root: Path) -> dict:
    root=root.resolve();docs=root/DOCS;out=docs/"joint_selection_v3/score_selection"
    selected_file=out/"JOINT_SERVICE_MAPPING.csv";score_file=out/"SELECTED_CONTROLLABILITY_SCORES.csv"
    immutable={name:sha256(out/name) for name in ("JOINT_SERVICE_MAPPING.csv","AIDC_MAPPING.csv","STA_MAPPING.csv",
        "SELECTED_CONTROLLABILITY_SCORES.csv","SCORING_PREREGISTRATION.json","SCORE_INPUT_SHA256.json")}
    mapping=read_csv(selected_file);by_site={row["location_id"]:row for row in mapping}
    verified=verify_geometry(root,out,write_report=False)
    if len(mapping)!=24 or verified["strict_nonexempt_signs"]!=552:raise ValueError("24PCC/552 strict directions required")
    scores={r["location_id"]:r for r in read_csv(score_file)}
    source_policy=docs/"joint_selection_v3/selection_scores/PREREGISTRATION.json"
    policy=json.loads(source_policy.read_text());slots=policy["slots"];targets=policy["targets"]
    binding=json.loads((out/"SCORE_INPUT_SHA256.json").read_text())
    if sha256(source_policy)!=binding["root_score_policy_sha256"]:raise ValueError("Root pre-score policy changed")
    if len(slots)!=4 or len(targets)!=20:raise ValueError("Fixed4times/20targets required")
    oldfile=root/"ieee8500_v42/data/geometry/AIDC_V3_MAPPING.csv"
    old={r["aidc_id"]:r for r in read_csv(oldfile)}
    mvfile=docs/"MV_AIDC_CANDIDATES.csv";mv={r["dss_bus"]:r for r in read_csv(mvfile)}
    lvfile=docs/"LV_STA_CANDIDATES.csv";lv={r["candidate_bus"]:r for r in read_csv(lvfile)}
    original_file=root/"ieee8500_v42/data/geometry/ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv"
    original={r["location_id"]:r for r in read_csv(original_file)}
    aidc_audit=[];sta_audit=[]
    for row in mapping:
        site=row["location_id"];bus=row["candidate_bus"]
        if row["role"]=="AIDC":
            authority=mv[bus]
            aidc_audit.append(dict(location_id=site,traffic_node_id=row["traffic_node_id"],old_v3_bus=old[site]["ieee8500_bus"],
                selected_bus=bus,bus_changed=old[site]["ieee8500_bus"]!=bus,
                original_source_x=authority["x"],original_source_y=authority["y"],
                nominal_kv_ll=authority["nominal_kv_ll"],phase_nodes=authority["phase_nodes"],
                continuous_abc_from_feeder_head=authority["continuous_abc_from_feeder_head"],
                original_host_exclusions_pass=authority["source_substation_regulator_exclusion_pass"],
                root_distance_ohm=authority["root_distance_ohm"],q05_root_guard_ohm=authority["root_distance_q05_guard_ohm"],
                source_proximity_guard_pass=authority["source_proximity_guard_pass"],
                direction_status="SOURCE_LAYOUT_DIRECTION_PASS",field_coordinates_certified=False,
                installed_idle_or_anonymous_CC4_flex_credited=False,job_QoS_WAN_dispatch_certified=False))
        else:
            authority=lv[bus]
            sta_audit.append(dict(location_id=site,traffic_node_id=row["traffic_node_id"],
                old_retained_MV_bus=original[site]["ieee8500_bus"],selected_LV_bus=bus,
                customer_terminal_240v=authority["injection_terminal_240v"],original_service_transformer=authority["upstream_transformer"],
                original_CT_primary_kva=authority["transformer_primary_kva"],
                original_CT_secondary_winding_kvas=authority["transformer_secondary_winding_kvas"],
                original_triplex_normal_amps=authority["triplex_min_normal_amps"],
                original_triplex_support_lines=authority["direct_support_lines"],
                original_triplex_path=authority["triplex_path"],upstream_primary_bus=authority["upstream_primary_bus"],
                upstream_primary_phase=authority["upstream_primary_phase"],primary_proxy_x=authority["proxy_x"],primary_proxy_y=authority["proxy_y"],
                source_SX_schematic_x_NOT_geography=authority["source_schematic_x_NOT_geography"],
                source_SX_schematic_y_NOT_geography=authority["source_schematic_y_NOT_geography"],
                coordinate_authority="upstream-primary original-layout proxy; not surveyed customer position",
                original_neutral_model=authority["triplex_neutral_model"],direction_status="ASSUMED_PROXY_DIRECTION_PASS",
                nominal_model_P_import_or_export_ceiling_kw=5.,nominal_model_Q_abs_ceiling_kvar=3.,
                nominal_model_S_ceiling_kva=6.,nominal_model_each_hot_current_ceiling_A=27.,
                CT_Triplex_nameplates_changed=False,additional_CT_added=False,actual_dispatch_certified=False))
    write_csv(out/"SELECTED_AIDC_OLD_TO_NEW.csv",aidc_audit)
    write_csv(out/"SELECTED_STA_LV_EQUIPMENT.csv",sta_audit)
    mv_response_file=docs/"joint_selection_v3/mv_sensitivity/TOP20_RESPONSE.csv"
    mv_response={(r["bus"],int(r["slot"]),r["line"]):r for r in read_csv(mv_response_file)}
    lvfolder=docs/"joint_selection_v3/lv_sensitivity"
    axes_file=lvfolder/"AXES.json";axes=json.loads(axes_file.read_text())
    normal={line:{float(a["normal_amps"]) for a in axes["lines"] if a["element"].lower()==line} for line in targets}
    if any(len(v)!=1 for v in normal.values()):raise ValueError("Original single NormalAmps per target required")
    normal={line:next(iter(v)) for line,v in normal.items()}
    lv_archives={};inputs=[oldfile,mvfile,lvfile,original_file,selected_file,score_file,source_policy,mv_response_file,axes_file]
    for slot in slots:
        path=lvfolder/f"LV_SLOT_{slot:02d}.npz";inputs.append(path)
        with np.load(path,allow_pickle=False) as archive:
            values={key:archive[key].copy() for key in archive.files}
        if list(values["line"])!=targets or list(values["component"])!=["P","Q"] or int(values["slot"])!=slot:
            raise ValueError("LV original target/component/time axes changed")
        if values["dRho"].shape!=(1177,2,20) or values["dI"].shape!=(1177,2,20):
            raise ValueError("Complete source LV target sensitivities required")
        values["by_bus"]={str(bus):j for j,bus in enumerate(values["candidate_bus"])}
        lv_archives[slot]=values
    flexfile=docs/"FLEXIBLE_WORKLOAD_AUDIT.csv";inputs.append(flexfile)
    flex={(r["aidc_id"],int(r["slot"])):r for r in read_csv(flexfile)}
    actionfile=out/"SELECTED_STA_SCORE_ACTIONS.csv";inputs.append(actionfile)
    actions={(r["location_id"],int(r["slot"])):r for r in read_csv(actionfile)}
    reference="BG0.552/capacity1/original-v3 AIDC B0, original-autocontrol settled then fixed for central differences"
    raw=[];potential=[];bounds=[];baseline_error=0.;normal_error=0.
    for row in mapping:
        site=row["location_id"];role=row["role"];bus=row["candidate_bus"]
        for slot in slots:
            if role=="AIDC":
                footprint=flex[(site,slot)];p=float(footprint["known_only_reducible_P_upper_bound_kW"])
                q=float(footprint["coupled_Q_reduction_upper_bound_kvar"]);reach=exposure=1.
                action_authority="known-original-UID active GPU C1 swing footprint upper bound; uncertified job-dispatch relaxation"
            else:
                action=actions[(site,slot)];p=float(action["P_design_choice_kw"]);q=float(action["Q_design_choice_kvar"])
                reach=float(action["initial_fleet_reachable_fraction"]);exposure=float(action["fleet_exposure_factor"])
                action_authority="exact local-linear P-only/Q-only/mixed-half action from frozen root score; not blanket5kW"
                archive=lv_archives[slot];j=archive["by_bus"][bus];iv=archive["local_linear_interval"][j]
                v=archive["PCC_node_voltage_pu"][j]
                step=.1
                dv=(v[:,1,:]-v[:,0,:])/(2*step)
                bounds.append(dict(location_id=site,candidate_bus=bus,slot=slot,time=time_label(slot),
                    P_linear_lower_kw=float(iv[0,0]),P_linear_upper_kw=float(iv[0,1]),P_interval_valid=bool(iv[0,2]>0),
                    Q_linear_lower_kvar=float(iv[1,0]),Q_linear_upper_kvar=float(iv[1,1]),Q_interval_valid=bool(iv[1,2]>0),
                    selected_P_action_kw=p,selected_Q_action_kvar=q,
                    dV_hot1_pu_per_kw=float(dv[0,0]),dV_hot2_pu_per_kw=float(dv[0,1]),
                    dV_hot1_pu_per_kvar=float(dv[1,0]),dV_hot2_pu_per_kvar=float(dv[1,1]),
                    local_bound_status="settled-control linear screen; nonlinear selected96slot validation remains separate",
                    reference_context=reference,actual_dispatch_certified=False))
            for target_index,line in enumerate(targets):
                if role=="AIDC":
                    source=mv_response[(bus,slot,line)]
                    current=[float(source["dI_P_A_per_kw"]),float(source["dI_Q_A_per_kvar"])]
                    rho=[float(source["dRho_P_per_kw"]),float(source["dRho_Q_per_kvar"])]
                    base=float(source["baseline_rho"]);node=source["baseline_node"]
                    terminal="NOT_EXPORTED_IN_MV_SOURCE";conductor="NOT_EXPORTED_IN_MV_SOURCE"
                    path_contains=source["path_contains_target"]
                    baseline_error=max(baseline_error,abs(base-float(lv_archives[slot]["baseline_rho"][target_index])))
                    step=1.
                else:
                    archive=lv_archives[slot];j=archive["by_bus"][bus]
                    current=archive["dI"][j,:,target_index];rho=archive["dRho"][j,:,target_index]
                    base=float(archive["baseline_rho"][target_index]);axis=axes["lines"][int(archive["baseline_binding_axis"][target_index])]
                    if axis["element"].lower()!=line:raise ValueError("LV baseline binding axis is not frozen target line")
                    node=axis["node"];terminal=axis["terminal"];conductor=axis["conductor"]
                    path_contains=bool(archive["source_path_contains_line"][j,target_index]);step=.1
                for component in (0,1):
                    di=float(current[component]);dr=float(rho[component]);normal_error=max(normal_error,abs(dr-di/normal[line]))
                    raw.append(dict(location_id=site,role=role,candidate_bus=bus,slot=slot,time=time_label(slot),
                        target_index=target_index+1,line=line,component="P" if component==0 else "Q",
                        dI_A_per_unit=di,dRho_pu_per_unit=dr,unit="kW" if component==0 else "kvar",
                        original_line_NormalAmps=normal[line],baseline_reference_rho=base,
                        baseline_binding_node=node,baseline_binding_terminal=terminal,baseline_binding_conductor=conductor,
                        source_path_contains_line=path_contains,central_difference_step=step,
                        positive_component_means="P/Q injection; DSS demand negative",control_state="common settled baseline fixed",
                        reference_context=reference,derivative_recomputed_at_selected_final_GPU_scale=False,
                        actual_selected_dispatch_or_full_rating_certified=False))
                delta_i=float(current[0])*p+float(current[1])*q
                delta_rho=float(rho[0])*p+float(rho[1])*q
                weighted=(max(-delta_rho,0)-2*max(delta_rho,0))*reach*exposure
                potential.append(dict(location_id=site,role=role,candidate_bus=bus,slot=slot,time=time_label(slot),
                    target_index=target_index+1,line=line,original_line_NormalAmps=normal[line],
                    baseline_reference_binding_rho=base,reference_binding_node=node,
                    P_action_kw=p,Q_action_kvar=q,action_authority=action_authority,
                    predicted_reference_binding_delta_I_A=delta_i,predicted_reference_binding_delta_rho_pu=delta_rho,
                    signed_small_signal_relief_pu=-delta_rho,
                    predicted_reference_binding_rho_after_action=base+delta_rho,
                    initial_fleet_reachable_fraction=reach,fleet_exposure_factor=exposure,
                    root_signed_penalty_weighted_score_term=weighted,
                    common_PQ_action_for_all20_targets_at_this_PCC_time=True,
                    reference_context=reference,prediction_not_achieved_system_rho=True,
                    simultaneous12_STA_dispatch_or_job_QoS_SOC_certified=False))
    if (len(raw),len(potential),len(bounds))!=(3840,1920,48):raise ValueError("Selected24*4*20 sensitivity coverage incomplete")
    if baseline_error>1e-7:raise ValueError("MV/LV reference baselines differ; cannot silently merge role heatmaps")
    if normal_error>1e-9:raise ValueError("Original NormalAmps normalization mismatch")
    for site in by_site:
        group=[r for r in potential if r["location_id"]==site]
        total=sum(r["root_signed_penalty_weighted_score_term"] for r in group)/80
        if abs(total-float(scores[site]["score"]))>1e-10:raise ValueError("Selected electrical action potential does not reproduce root signed score")
    write_csv(out/"SELECTED_PCC_PQ_SENSITIVITY.csv",raw)
    write_csv(out/"SELECTED_CONTROL_POTENTIAL.csv",potential)
    write_csv(out/"SELECTED_LV_LOCAL_LINEAR_BOUNDS.csv",bounds)
    summary=[]
    for row in mapping:
        for slot in slots:
            group=[r for r in potential if r["location_id"]==row["location_id"] and r["slot"]==slot]
            partial=[r for r in raw if r["location_id"]==row["location_id"] and r["slot"]==slot]
            maximum=max(group,key=lambda r:abs(r["predicted_reference_binding_delta_rho_pu"]))
            summary.append(dict(location_id=row["location_id"],role=row["role"],candidate_bus=row["candidate_bus"],
                slot=slot,time=time_label(slot),P_action_kw=group[0]["P_action_kw"],Q_action_kvar=group[0]["Q_action_kvar"],
                maximum_abs_dI_P_A_per_kw=max(abs(r["dI_A_per_unit"]) for r in partial if r["component"]=="P"),
                maximum_abs_dI_Q_A_per_kvar=max(abs(r["dI_A_per_unit"]) for r in partial if r["component"]=="Q"),
                maximum_abs_dRho_P_per_kw=max(abs(r["dRho_pu_per_unit"]) for r in partial if r["component"]=="P"),
                maximum_abs_dRho_Q_per_kvar=max(abs(r["dRho_pu_per_unit"]) for r in partial if r["component"]=="Q"),
                relief_target_lines=sum(r["predicted_reference_binding_delta_rho_pu"]<0 for r in group),
                adverse_target_lines=sum(r["predicted_reference_binding_delta_rho_pu"]>0 for r in group),
                zero_target_lines=sum(r["predicted_reference_binding_delta_rho_pu"]==0 for r in group),
                mean_predicted_reference_binding_delta_rho_pu=sum(r["predicted_reference_binding_delta_rho_pu"] for r in group)/20,
                maximum_abs_predicted_delta_rho_line=maximum["line"],
                maximum_abs_predicted_delta_rho_pu=abs(maximum["predicted_reference_binding_delta_rho_pu"]),
                mean_root_weighted_score_term=sum(r["root_signed_penalty_weighted_score_term"] for r in group)/20,
                action_not_actual_dispatch=True,source_baseline_not_final_selected_case=True))
    write_csv(out/"SELECTED_PCC_PQ_SUMMARY.csv",summary)
    target_legend=[dict(target_index=k+1,line=line,original_NormalAmps=normal[line],
        frozen_before_selection=True,not_reselected_from_final_outcome=True) for k,line in enumerate(targets)]
    write_csv(out/"SELECTED_SENSITIVITY_TARGET_LEGEND.csv",target_legend)
    after={name:sha256(out/name) for name in immutable}
    if immutable!=after:raise ValueError("Mapping/scores/prereg changed while auditing")
    receipt={"status":"COMPLETE_SELECTED24_PCC_REFERENCE_SENSITIVITY_AUDIT","PCCs":24,"slots":slots,"targets":20,
        "raw_PQ_rows":3840,"exact_action_potential_rows":1920,"PCC_time_summary_rows":96,"LV_local_bound_rows":48,
        "direct_strict_axis_relations":552,"all276_pairs_PASS":True,"mapping_and_scores_unchanged":True,
        "MV_LV_baseline_rho_difference_max":baseline_error,"NormalAmps_derivative_normalization_error_max":normal_error,
        "source_reference_context":reference,"source_operating_point_is_selected_final_case":False,
        "actual_policy_or_systemrho_performance_claim":False,"AC_calls":0,"Native_calls":0,
        "witness_sha256":sha256(selected_file),"preserved_files_sha256":immutable,
        "input_sha256":{str(p.relative_to(root)):sha256(p) for p in inputs},
        "outputs_sha256":{name:sha256(out/name) for name in ("SELECTED_AIDC_OLD_TO_NEW.csv","SELECTED_STA_LV_EQUIPMENT.csv",
            "SELECTED_PCC_PQ_SENSITIVITY.csv","SELECTED_CONTROL_POTENTIAL.csv","SELECTED_LV_LOCAL_LINEAR_BOUNDS.csv",
            "SELECTED_PCC_PQ_SUMMARY.csv","SELECTED_SENSITIVITY_TARGET_LEGEND.csv")}}
    (out/"SELECTED_LOCATION_AUDIT_RECEIPT.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    aidc_table=table(aidc_audit,[("location_id","서비스"),("traffic_node_id","traffic"),("old_v3_bus","old v3 bus"),("selected_bus","선택 MV bus"),("root_distance_ohm","root Ω")])
    sta_display=[dict(r,primary_proxy=f"({float(r['primary_proxy_x']):.3f},{float(r['primary_proxy_y']):.3f})") for r in sta_audit]
    sta_table=table(sta_display,[("location_id","서비스"),("selected_LV_bus","LV bus"),("original_service_transformer","원본 CT"),
        ("original_CT_primary_kva","CT kVA"),("original_triplex_normal_amps","Triplex A"),("upstream_primary_bus","primary proxy bus"),
        ("upstream_primary_phase","primary phase"),("primary_proxy","proxy XY")])
    aggregate=[]
    for row in mapping:
        site=row["location_id"];group=[r for r in summary if r["location_id"]==site]
        aggregate.append(dict(location_id=site,selected_bus=row["candidate_bus"],
            max_P_sensitivity=f"{max(r['maximum_abs_dRho_P_per_kw'] for r in group):.6g}",
            max_Q_sensitivity=f"{max(r['maximum_abs_dRho_Q_per_kvar'] for r in group):.6g}",
            P_actions=" / ".join(f"{r['P_action_kw']:.4g}" for r in group),
            Q_actions=" / ".join(f"{r['Q_action_kvar']:.4g}" for r in group)))
    action_table=table(aggregate,[("location_id","서비스"),("max_P_sensitivity","max |∂ρ/∂P| pu/kW"),
        ("max_Q_sensitivity","max |∂ρ/∂Q| pu/kvar"),("P_actions","P 액션 kW: 00:00/02:15/12:00/18:45"),
        ("Q_actions","Q 액션 kvar: 같은 시간 순서")])
    report=["# 선택된24 지점의 PCC·저압 설비·민감도 감사\n",
        "**현재 선택은12개 원본 source-guarded MV AIDC와12개 원본 고객측 LV STA이다.** "
        "24 service/traffic ID와6 MESS unit을 유지했고, source CT·Triplex·정격·phase·자동 제어를 변경하거나 "
        "CT/STA/차량 수를 늘리지 않았다. 후보는 사전 동결한 개발일 response surrogate를 사용한1/2-site local "
        "selection이며, global optimum이나 실제 dispatch 성과를 뜻하지 않는다. 현장 근거가 없는 조건의 "
        "연구 포트 재설계는 사용자 허용 범위이며 Production/현장 인증은 주장하지 않는다.\n",
        f"한 공통 proper 회전 {verified['rotation_degrees']:.9f}°, 양의 균일 배율·공통 이동 아래66 AIDC–AIDC, "
        "144 AIDC–STA,66 STA–STA의276쌍/552 strict 축을 원본 traffic/source에서 직접 검사했다. 전부PASS이고 "
        "24 PCC가 서로 다르다.1m traffic 공차를 바꾸거나 개별 회전·이동·reflection을 사용하지 않았다. "
        "LV 좌표는 원본 상위primary bus의 proxy이므로 판정은 `ASSUMED_PROXY_DIRECTION_PASS`이며 "
        "실측 고객 지리방향을 보장하지 않는다. 원본CRS·단위·true east/north는 미인증이다.\n",
        "AIDC의 원래v3 bus와 현재 bus, source root guard는 다음과 같다. 모두12.47kV/ABC/연속 source path 및 "
        "원본 host 제외·root distance≥원본 q05 1.3819547376654384Ω를 유지했다. 원본 v3는 고정 host에서 모든 pair 방향을 "
        "통과하지 못했지만, 현재 공동 재선정 결과는 별도 계약의 witness이다.\n",aidc_table,
        "12개STA의 원본 서비스 transformer와Triplex rating, 고객bus 및primary proxy는 다음과 같다. "
        "Triplex NormalAmps와CT kVA는 원본 값을 그대로 표시했다. 5kW/3kvar/S6kVA/eachhot27A는 연구 PCS "
        "ceiling이며 이 원본 rating이나 차량450kW/600kVA로부터 새로운 허용 출력을 만들지 않는다. "
        "Split-phase는 하나의240V bus.1.2 포트이고 두120V leg에 전체 P/Q를 각각 복제하지 않는다. "
        "원본 Kron-reduced neutral에 독립 neutral ampacity를 만들어 넣지 않았다.\n",sta_table,
        "민감도 데이터는 선택 이후 새AC를 실행해서 만든 것이 아니다. 기존 완료된 **BG0.552/capacity1/원래v3 "
        "AIDC B0 참조 operating point**의4시간 **00:00(slot0),02:15(slot9),12:00(slot48),18:45(slot75)**와 "
        "사전에 고정한20 원본 고부하 감시 선로에서 가져왔다. 원본 자동 제어가 정착한 같은base를 고정하고 "
        "MV에는±1kW/kvar,LV에는±0.1kW/kvar central difference를 적용한 기존 결과이다. "
        "각 source의 baseline-binding terminal/phase current를 사용했고 MV source가 export하지 않은 "
        "terminal/conductor는 추정하지 않고 CSV에 NOT_EXPORTED로 남겼다.\n",
        f"MV/LV reference baselineρ 차이의 최대값은 {baseline_error:.3g}, 원본NormalAmps로 dI를 "
        f"정규화한 dρ 오차의 최대값은 {normal_error:.3g}이다. 최종 선택 GPU scale/재배치 B0에서 "
        "민감도를 다시 계산했다는 주장은 하지 않는다. 큰 finite action, binding phase 변경, 자동 제어·혼잡 "
        "재배치의 비선형 효과는 별도 selected AC96slot 검증이 판단한다.\n",
        "아래표의 |∂ρ/∂P|,|∂ρ/∂Q|는4시간×20 targets 중 최대 절대 partial이며 units는pu/kW 및pu/kvar이다. "
        "P/Q 액션은 후보 score에서 실제 사용한 같은4시간 순서이다. AIDC P는known-original-UID activeGPU·C1 "
        "swing footprint의 상한이고 Q/P=tan(acos0.95)로coupled된다. 이는 전체job QoS/WAN dispatch가 "
        "인증된 실제flexibility가 아니며 idle/anonymousCC4를 credit하지 않는다. STA는 원본 local CT/Triplex/PCC "
        "voltage의 1차 margin으로 제한한 P-only/Q-only/mixed-half finite action을 그대로 가져왔다. "
        "각 PCC/time에서20 선로에 **한 공통P/Q vector**를 적용했다.\n",action_table,
        "상세3840개 partial은 `SELECTED_PCC_PQ_SENSITIVITY.csv`,1920개 action prediction은 "
        "`SELECTED_CONTROL_POTENTIAL.csv`,96개 PCC/time 요약은 `SELECTED_PCC_PQ_SUMMARY.csv`, "
        "48개LV local interval/PCC voltage partial은 `SELECTED_LV_LOCAL_LINEAR_BOUNDS.csv`에 있다. "
        "대상20 line의 번호·원본NormalAmps는 `SELECTED_SENSITIVITY_TARGET_LEGEND.csv`에서 확인한다.\n",
        "Prediction은 `ΔI≈(∂I/∂P)P+(∂I/∂Q)Q`, `Δρ≈(∂ρ/∂P)P+(∂ρ/∂Q)Q`로 계산했다. "
        "음의Δρ는해당참조 binding axis의 predicted relief이고 양수는adverse response이다. "
        "동시24 PCC의 실제 system maxρ 변화나B1/B2/B3 성과가 아니다. Root score의 negative-benefit/positive-adverse "
        "penalty2,초기6차량 safeETA+600s reachability와0.5 exposure를 같은 방식으로 재계산하여24개 선택 "
        "root score가 모두 일치했다. 이 mobility factor는 SOC·동시12dock·실제 route를 인증하지 않는다. "
        "Surrogate 증가율을 실제ρ 개선율로 해석하지 않는다.\n",
        "[저압 연구 포트 설계](../../LV_PORT_SIMULATION_DESIGN.md)의 DC/DC·BMS·보호·접근/지연·효율 가정과 "
        "원본 전압/선로/CT/반전력/PQ 제약은 별도 actual selected-case audit에 남는다. 이 보고서는 새AC/Native를 "
        "실행하지 않고 현재 mapping·scores·선택 prereg 및 root main report/copies를 변경하지 않았다.\n",
        f"현재 mapping SHA256: `{receipt['witness_sha256']}`. 재현 명령은 "
        "`.runtime/Scripts/python.exe -m ieee8500_v42.selected_location_audit --root .`이며 "
        "입력·CSV SHA/coverage는 `SELECTED_LOCATION_AUDIT_RECEIPT.json`에 있다.\n"]
    (out/"SELECTED_LOCATION_AUDIT_KO.md").write_text("\n".join(report),encoding="utf-8")
    return receipt


def plot_sensitivities(root: Path) -> dict:
    """Plot every selected PCC/time/target value without running a simulator."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import SymLogNorm

    root=root.resolve();out=root/DOCS/"joint_selection_v3/score_selection"
    figures=out/"figures";figures.mkdir(exist_ok=True)
    files={name:out/name for name in ("JOINT_SERVICE_MAPPING.csv","SELECTED_PCC_PQ_SENSITIVITY.csv",
        "SELECTED_CONTROL_POTENTIAL.csv","SELECTED_SENSITIVITY_TARGET_LEGEND.csv")}
    before={name:sha256(path) for name,path in files.items()}
    mapping=sorted(read_csv(files["JOINT_SERVICE_MAPPING.csv"]),key=lambda r:r["location_id"])
    sites=[r["location_id"] for r in mapping]
    if len(sites)!=24 or len(set(sites))!=24:raise ValueError("24 distinct selected PCC IDs required")
    legend=sorted(read_csv(files["SELECTED_SENSITIVITY_TARGET_LEGEND.csv"]),key=lambda r:int(r["target_index"]))
    if [int(r["target_index"]) for r in legend]!=list(range(1,21)):raise ValueError("Fixed20 target legend required")
    raw=read_csv(files["SELECTED_PCC_PQ_SENSITIVITY.csv"])
    potential=read_csv(files["SELECTED_CONTROL_POTENTIAL.csv"])
    slots=sorted({int(r["slot"]) for r in raw})
    if slots!=[0,9,48,75]:raise ValueError("Exactly four frozen reference times required")
    expected={(site,slot,target,component) for site in sites for slot in slots for target in range(1,21) for component in ("P","Q")}
    index={(r["location_id"],int(r["slot"]),int(r["target_index"]),r["component"]):r for r in raw}
    if len(raw)!=3840 or set(index)!=expected:raise ValueError("No missing, duplicated or imputed sensitivity cells permitted")
    pindex={(r["location_id"],int(r["slot"]),int(r["target_index"])):r for r in potential}
    if len(potential)!=1920 or set(pindex)!={(s,t,i) for s,t,i,_ in expected}:raise ValueError("Exact-action coverage required")
    for site in sites:
        for slot in slots:
            actions={(float(pindex[site,slot,i]["P_action_kw"]),float(pindex[site,slot,i]["Q_action_kvar"])) for i in range(1,21)}
            if len(actions)!=1:raise ValueError("One common action must apply to all20 targets per PCC/time")
    rho=np.array([[[float(index[site,slot,target,c]["dRho_pu_per_unit"])
        for slot in slots for target in range(1,21)] for site in sites] for c in ("P","Q")])
    amps=np.array([[[float(index[site,slot,target,c]["dI_A_per_unit"])
        for slot in slots for target in range(1,21)] for site in sites] for c in ("P","Q")])
    action=np.array([[float(pindex[site,slot,target]["predicted_reference_binding_delta_rho_pu"])
        for slot in slots for target in range(1,21)] for site in sites])
    if not all(np.isfinite(values).all() for values in (rho,amps,action)):raise ValueError("Finite source values required")
    labels=[f"{r['location_id']}  {r['candidate_bus']}" for r in mapping]
    legend_text="Frozen original target lines\n\n"+"\n".join(f"T{int(r['target_index']):02d}  {r['line']}" for r in legend)
    minor=np.array([block*20+target for block in range(4) for target in (0,4,9,14)]+[79])
    minor_labels=[f"T{target+1:02d}" for block in range(4) for target in (0,4,9,14)]+["T20"]
    context="Reference: BG 0.552 / capacity 1 / original v3 AIDC B0; settled controls held fixed. Not recomputed at the selected final GPU scale."
    footer="Blue = negative response; red = positive response. Each cell is an original baseline-binding line-current axis. Primary layout proxies are not surveyed coordinates."
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"svg.fonttype":"none"})
    outputs={}

    def style(ax, title):
        ax.set_title(title,loc="left",fontsize=13,pad=13)
        ax.set_yticks(range(24),labels,fontsize=9)
        ax.set_xticks([9.5,29.5,49.5,69.5],[time_label(s) for s in slots],fontsize=11)
        ax.set_xticks(minor,minor_labels,minor=True)
        ax.tick_params(axis="x",which="major",pad=18,length=0)
        ax.tick_params(axis="x",which="minor",pad=3,length=0,labelsize=8)
        ax.tick_params(axis="y",length=0)
        ax.set_xlim(-.5,79.5);ax.set_ylim(23.5,-.5)
        for edge in (19.5,39.5,59.5):ax.axvline(edge,color="#243b53",lw=1.6)
        ax.axhline(11.5,color="#243b53",lw=1.6)
        for spine in ax.spines.values():spine.set_color("#718096")

    def save(fig, name):
        for extension in ("png","svg"):
            path=figures/f"{name}.{extension}"
            fig.savefig(path,dpi=165,facecolor="white",bbox_inches="tight")
            outputs[str(path.relative_to(out))]=sha256(path)
        plt.close(fig)

    for name,values,threshold,units,title in (
        ("SELECTED_PQ_RHO_SENSITIVITY_HEATMAP",rho,1e-6,("pu / kW","pu / kvar"),"Selected PCC P/Q loading sensitivities"),
        ("SELECTED_PQ_CURRENT_SENSITIVITY_HEATMAP",amps,1e-3,("A / kW","A / kvar"),"Selected PCC P/Q current sensitivities")):
        limit=float(np.max(np.abs(values)))
        if limit<=0:limit=threshold
        norm=SymLogNorm(linthresh=threshold,vmin=-limit,vmax=limit,base=10)
        fig=plt.figure(figsize=(22,16));grid=fig.add_gridspec(2,2,width_ratios=(5.7,1.9),hspace=.29,wspace=.20)
        for component in range(2):
            ax=fig.add_subplot(grid[component,0]);im=ax.imshow(values[component],cmap="RdBu_r",norm=norm,aspect="auto",interpolation="none")
            style(ax,f"{'P: positive active-power injection' if component==0 else 'Q: positive reactive-power injection'}")
            bar=fig.colorbar(im,ax=ax,fraction=.022,pad=.018)
            bar.set_label(f"Signed partial ({units[component]}); symmetric log scale",fontsize=9)
            bar.ax.tick_params(labelsize=8)
        guide=fig.add_subplot(grid[:,1]);guide.axis("off")
        guide.text(0,.99,legend_text,va="top",fontsize=10,linespacing=1.6,family="DejaVu Sans Mono")
        guide.text(0,.22,"24 selected PCCs\n12 MV AIDC + 12 customer LV STA\n\n4 reference times x 20 target lines\n80 columns in each panel\n\nAll 3,840 P/Q source values shown\nNo missing-cell interpolation",va="top",fontsize=11,linespacing=1.5)
        fig.suptitle(title,fontsize=21,x=.07,ha="left",y=.98)
        fig.text(.07,.949,context,fontsize=11)
        fig.text(.07,.034,footer,fontsize=10)
        fig.text(.07,.015,"Sensitivities are local reference derivatives, not achieved system maximum-loading or dispatch performance.",fontsize=10)
        fig.subplots_adjust(left=.14,right=.98,top=.91,bottom=.075)
        save(fig,name)

    limit=float(np.max(np.abs(action)));threshold=1e-4
    norm=SymLogNorm(linthresh=threshold,vmin=-max(limit,threshold),vmax=max(limit,threshold),base=10)
    fig=plt.figure(figsize=(22,10));grid=fig.add_gridspec(1,2,width_ratios=(5.7,1.9),wspace=.20)
    ax=fig.add_subplot(grid[0,0]);im=ax.imshow(action,cmap="RdBu_r",norm=norm,aspect="auto",interpolation="none")
    style(ax,"Exact bounded common P/Q action per PCC and time; all 20 targets use the same action")
    bar=fig.colorbar(im,ax=ax,fraction=.022,pad=.018)
    bar.set_label("Predicted reference binding-axis delta rho (pu); symmetric log scale",fontsize=9)
    bar.ax.tick_params(labelsize=8)
    guide=fig.add_subplot(grid[0,1]);guide.axis("off");guide.text(0,.99,legend_text,va="top",fontsize=10,linespacing=1.4,family="DejaVu Sans Mono")
    fig.suptitle("Selected PCC control potential: local reference prediction",fontsize=21,x=.07,ha="left",y=.98)
    fig.text(.07,.93,context,fontsize=11)
    fig.text(.07,.054,"Delta rho = (d rho / d P) P + (d rho / d Q) Q. Original local bounds retained; mobility / fleet score weights are not applied to these cells.",fontsize=10)
    fig.text(.07,.029,"Blue = predicted relief; red = adverse response. These are separate PCC actions, not simultaneous 12-STA dispatch or achieved system-rho improvement.",fontsize=10)
    fig.subplots_adjust(left=.14,right=.98,top=.855,bottom=.115)
    save(fig,"SELECTED_CONTROL_POTENTIAL_HEATMAP")
    after={name:sha256(path) for name,path in files.items()}
    if before!=after:raise ValueError("Selected mapping or input CSV changed while plotting")
    result={"status":"COMPLETE_REFERENCE_SENSITIVITY_FIGURES","PCCs":24,"slots":slots,"targets":20,
        "sensitivity_cells":3840,"separate_action_prediction_cells":1920,"plots":3,
        "source_operating_point_is_selected_final_case":False,"actual_systemrho_performance_claim":False,
        "mapping_unchanged":True,"AC_calls":0,"Native_calls":0,"input_sha256":before,"outputs_sha256":outputs,
        "rho_partial_abs_max":float(np.max(np.abs(rho))),"current_partial_abs_max":float(np.max(np.abs(amps))),
        "predicted_separate_action_delta_rho_abs_max":float(np.max(np.abs(action))),
        "symmetric_log_linear_thresholds":{"rho_partial":1e-6,"current_partial":1e-3,"action_delta_rho":1e-4}}
    (out/"SELECTED_SENSITIVITY_FIGURES.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    report_file=out/"SELECTED_LOCATION_AUDIT_KO.md";report=report_file.read_text(encoding="utf-8")
    marker="\n<!-- selected-reference-sensitivity-figures -->\n"
    report=report.split(marker)[0]
    report+=marker+"\n모든24 PCC×4시간×20 target의 P/Q partial과 동일 bounded P/Q 액션의 예측은 다음 그림에서 확인한다. "
    report+="공통 대칭 signed-log 색상 척도를 사용하고 값 보간·누락0 대체를 하지 않았다. 음수 blue는 참조 axis의 "
    report+="전류/ρ 감소이고 red는 증가이다. 이 색상은 실제 정책 성과나 동시 dispatch를 나타내지 않는다.\n\n"
    for title,name in (("P/Q loading partial","SELECTED_PQ_RHO_SENSITIVITY_HEATMAP"),("P/Q current partial","SELECTED_PQ_CURRENT_SENSITIVITY_HEATMAP"),("Bounded common P/Q control potential","SELECTED_CONTROL_POTENTIAL_HEATMAP")):
        report+=f"- [{title}: PNG](figures/{name}.png), [SVG](figures/{name}.svg)\n"
    report+="\n그림 포함 재현 명령: `.runtime/Scripts/python.exe -m ieee8500_v42.selected_location_audit --root . --plots`.\n"
    report_file.write_text(report,encoding="utf-8")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--plots",action="store_true",help="Render all24 PCC four-time reference sensitivity heatmaps")
    args=parser.parse_args();result=assemble(args.root)
    if args.plots:result["figures"]=plot_sensitivities(args.root)
    print(json.dumps({k:v for k,v in result.items() if k not in ("input_sha256","outputs_sha256","preserved_files_sha256")},indent=2))
