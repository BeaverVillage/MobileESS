"""Report the separate May01 Planning Vmax=1.048 experiment from receipts.

This module never launches an optimizer, replays AC, or changes an input.
Missing measurements remain null/blank. Failed AC measurements remain evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import timedelta
from pathlib import Path

import numpy as np

from v42_common_reporting import report as common

POLICY = "V42_PLANNING_VMAX_1048_DIAGNOSTIC_V1"
ATTEMPT = "B2_MAY01_VMAX1048_CANARY"
AUDIT_ROOT = Path(r"D:\v42_actual_voltage_audit_20261010")
OLD_RESULT = Path(r"D:\v42_common_mess_campaign_20261010_01\dates\B2\2025-05-01\attempts\common_u4_v1_01\RESULT.json")
FILENAMES = (
    "V42_VMAX1048_EXPERIMENT_REPORT_KO.md", "MAY01_VMAX1050_VS_1048_COMPARISON.csv",
    "MAY01_VOLTAGE_VIOLATIONS_19_AUDIT.csv", "MAY01_REGCONTROL_TAP_COMPARISON.csv",
    "MAY01_MESS_PQ_VOLTAGE_ATTRIBUTION.csv", "VMAX1048_SOURCE_MODEL_IDENTITY.json",
    "VMAX1048_NATIVE_RUNTIME_LEDGER.json", "VMAX1048_ACTUAL_FRESH_VALIDATION.json")


def _load(reference, provenance, errors):
    return common.load_receipt(reference, provenance, errors)


def _existing(path, *containers):
    path = Path(path)
    if not path.is_file():
        return None
    return next(iter(common.matching_receipts(path, *containers)), path)


def _component(result, result_path, name, candidates, provenance, errors):
    reference = result.get(name)
    if reference:
        return _load(reference, provenance, errors)
    for candidate in candidates:
        reference = _existing(candidate, result.get("files"))
        if reference:
            return _load(reference, provenance, errors)
    return {}, None


def _csv_source(path, provenance, errors, required=False):
    try:
        provenance[str(path.resolve())] = common.record(path)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    except OSError as exc:
        if required:
            errors.append(dict(path=str(path), error=str(exc)))
        return []


def _validate_nested_receipts(document,provenance,errors):
    """Check linked model/control files before any PASS, once per exact path."""
    seen=set()
    def visit(value):
        if isinstance(value,dict):
            if value.get("path") and (value.get("sha256") is not None or value.get("bytes") is not None):
                path=Path(value["path"])
                key=(str(path.resolve()),value.get("sha256"),value.get("bytes"))
                if key not in seen:
                    seen.add(key)
                    try:
                        actual,_=common.checked_record(path,value)
                        provenance[str(path.resolve())]=actual
                    except (OSError,ValueError,TypeError) as exc:
                        errors.append(dict(path=str(path),error=str(exc)))
            for nested in value.values():
                if isinstance(nested,(dict,list)):visit(nested)
        elif isinstance(value,list):
            for nested in value:visit(nested)
    visit(document)


def _observer_slots(observer,provenance,errors):
    if not observer.get("slots_receipt"):
        return [],False
    slots,path=_load(observer["slots_receipt"],provenance,errors)
    if not isinstance(slots,list) or len(slots)!=96:
        errors.append(dict(path=str(path),error="EXACT_96_OBSERVED_CONTROL_SLOTS_REQUIRED"));return [],False
    settings=observer.get("regulator_settings_SHA")
    valid=all(r.get("slot")==i and r.get("control_actions_done") is True and r.get("converged") is True
        and r.get("seven_RegControls_enabled") is True and r.get("capacitor_states")==[1,1,1,1]
        and r.get("CapControl_count")==0 and r.get("regulator_settings_SHA")==settings
        and r.get("source_parameters_equal_to_original") is True and r.get("Planning_tap_cap_replay") is False
        and len(r.get("taps",[]))==7 and all(common.finite(v) is not None for v in r["taps"])
        for i,r in enumerate(slots) if isinstance(r,dict)) and all(isinstance(r,dict) for r in slots)
    if not valid:errors.append(dict(path=str(path),error="OBSERVED_CONTROL_SLOT_CONTRACT_MISMATCH"))
    return slots,valid


def dispatch_statistics(plan, provenance=None):
    """Literal FULL Pch/Pdis/Q coordinates; 0.25h integrations, no inference.

    Pch/Pdis are sums over every unit/site/slot coordinate, including zeros.
    Q absolute energy sums each coordinate's magnitude before integration.
    Routes are original exported travel arcs, not inferred location transitions.
    """
    values, units = plan.get("values"), plan.get("unit_ids", plan.get("units"))
    if not isinstance(values, dict) or not isinstance(units, list):
        return {}
    units = list(map(str, units))
    index = {unit: i for i, unit in enumerate(units)}
    coordinates = {k: np.zeros((96,len(units))) for k in ("Pch", "Pdis", "Q")}
    coverage={k:set() for k in coordinates}
    counts, q_abs = dict.fromkeys(coordinates,0), 0.
    minimum = dict.fromkeys(coordinates,None)
    pattern = re.compile(r"^(Pch|Pdis|Q)\[([^,]+),([^,]+),(\d+)\]$")
    for label, raw in values.items():
        match = pattern.fullmatch(label)
        if not match:
            continue
        kind, unit, _site, raw_slot = match.groups()
        slot, value = int(raw_slot), common.finite(raw)
        if unit not in index or not 0 <= slot < 96 or value is None:
            raise ValueError("INVALID_ORIGINAL_DISPATCH_COORDINATE")
        coordinates[kind][slot,index[unit]] += value
        coverage[kind].add((unit,slot))
        counts[kind] += 1
        minimum[kind] = value if minimum[kind] is None else min(minimum[kind],value)
        if kind == "Q":
            q_abs += abs(value)
    if any(counts[k] == 0 for k in coordinates):
        raise ValueError("ORIGINAL_PCH_PDIS_Q_COORDINATES_REQUIRED")
    if any(len(coverage[k])!=96*len(units) for k in coordinates):
        raise ValueError("ALL_96_UNIT_DISPATCH_COORDINATES_REQUIRED")
    if minimum["Pch"] < -1e-7 or minimum["Pdis"] < -1e-7:
        raise ValueError("NEGATIVE_ORIGINAL_CHARGE_DISCHARGE_COORDINATE")
    if "P_kw" in plan and not np.allclose(coordinates["Pdis"]-coordinates["Pch"],
            np.asarray(plan["P_kw"],dtype=float),atol=1e-7,rtol=0):
        raise ValueError("PCH_PDIS_NET_FROZEN_TRAJECTORY_MISMATCH")
    if "Q_kvar" in plan and not np.allclose(coordinates["Q"],
            np.asarray(plan["Q_kvar"],dtype=float),atol=1e-7,rtol=0):
        raise ValueError("Q_FROZEN_TRAJECTORY_MISMATCH")
    output = dict(dispatch_coordinate_count=counts, coordinate_minimum=minimum,
        charge_energy_kwh=float(coordinates["Pch"].sum()*.25),
        discharge_energy_kwh=float(coordinates["Pdis"].sum()*.25),
        reactive_signed_energy_kvarh=float(coordinates["Q"].sum()*.25),
        reactive_absolute_energy_kvarh=float(q_abs*.25),
        Pch_peak_total_kw=float(coordinates["Pch"].sum(axis=1).max()),
        Pdis_peak_total_kw=float(coordinates["Pdis"].sum(axis=1).max()),
        Q_peak_absolute_unit_kvar=float(np.abs(coordinates["Q"]).max()),
        Q_peak_absolute_total_kvar=float(np.abs(coordinates["Q"].sum(axis=1)).max()),
        aggregation_definition="Literal original FULL coordinates, dt=0.25h, no clipping; Qabsolute=sum(abs(Q[unit,site,slot]))*dt; P=Pdis-Pch.")
    routes = plan.get("routes")
    if isinstance(routes, list):
        if not all(isinstance(row,dict) and common.finite(row.get("energy_kwh")) is not None for row in routes):
            raise ValueError("ORIGINAL_ROUTE_ENERGY_REQUIRED")
        output.update(movement_count=len(routes), movement_energy_kwh=sum(float(row["energy_kwh"]) for row in routes),
            movement_arcs=routes, movement_count_definition="Count original exported selected travel arcs; depart/arrive/connect retain original 0-based slot boundaries.")
    return output


def _raw_validation(result, path, evaluation, manifest, provenance, errors):
    limits = common.line_authority(manifest,provenance,errors)
    if len(limits) != 263:
        raise ValueError("ORIGINAL_263_LINE_PHASE_AUTHORITY_REQUIRED")
    metric = common.metric_from_result(result,path,evaluation,limits,provenance,errors)
    if not metric:
        return dict(status="NOT_RUN" if not evaluation else "RAW_ARRAY_UNVERIFIED", physical_pass=None)
    raw = Path(metric["raw_current_receipt"]["path"])
    with np.load(raw,allow_pickle=False) as archive:
        v = np.asarray(archive["voltage_pu"],float)
        if v.shape != (96,386) or len(archive["node_names"])!=386 or not np.isfinite(v).all():
            raise ValueError("ALL_96_SLOT_FINITE_RAW_VOLTAGES_REQUIRED")
        if len(archive["branch_names"])!=383:
            raise ValueError("ORIGINAL_383_BRANCH_PHASE_AXIS_REQUIRED")
        convergence = np.asarray(archive["convergence"],bool)
        upper, lower = int(np.count_nonzero(v > 1.05)), int(np.count_nonzero(v < .95))
        transformer = archive["branch_kinds"].astype(str) == "transformer"
        tx_i = archive["phase_current_loading_pu"][:,transformer]
        tx_s = archive["transformer_total_kva_loading_pu"][:,transformer]
        if not np.isfinite(tx_i).all() or not np.isfinite(tx_s).all():
            raise ValueError("FINITE_TRANSFORMER_CURRENT_KVA_ARRAYS_REQUIRED")
        line_mask = archive["branch_kinds"].astype(str) == "line"
        names, phases = archive["branch_names"].astype(str), archive["branch_phases"].astype(str)
        keys = [f"{n}::{p}".lower() for n,p in zip(names[line_mask],phases[line_mask])]
        ratios = abs(archive["phase_current_a"][:,line_mask])/np.asarray([limits[k] for k in keys])
        counts=dict(voltage_violation_count=upper+lower, upper_voltage_violation_count=upper,
            lower_voltage_violation_count=lower, line_current_violation_count=int(np.count_nonzero(ratios>1)),
            transformer_current_violation_count=int(np.count_nonzero(tx_i>1)),
            transformer_kva_violation_count=int(np.count_nonzero(tx_s>1)))
        summary = evaluation.get("summary",evaluation.get("Fresh",{}).get("summary",{}))
        for key in ("voltage_violation_count","line_current_violation_count","transformer_current_violation_count","transformer_kva_violation_count"):
            if summary.get(key) is not None and summary[key] != counts[key]:
                raise ValueError("RAW_VIOLATION_COUNT_SUMMARY_MISMATCH:"+key)
        measurement=dict(status="MEASURED",physical_pass=bool(convergence.all() and all(x==0 for x in counts.values())),
            Fresh_converged_slots=int(convergence.sum()),Fresh_solved_slots=96,
            Vmin_pu=float(v.min()),Vmax_pu=float(v.max()),maximum_upper_voltage_exceedance_pu=max(0.,float(v.max())-1.05),
            maximum_lower_voltage_exceedance_pu=max(0.,.95-float(v.min())),Actual_voltage_limits_pu=[.95,1.05],
            metric=metric,**counts)
    if common.record(raw)!=metric["raw_current_receipt"]:
        raise ValueError("RAW_AC_BYTES_CHANGED_DURING_VOLTAGE_REPORT")
    return measurement


def _movement_source_time(statistics,evaluation,provenance,errors):
    ref=evaluation.get("Actual_source")
    source_receipt=None
    if isinstance(ref,dict) and ref.get("path"):
        body,_=_load(ref,provenance,errors)
        source_receipt=(body or {}).get("source")
    elif isinstance(ref,dict):
        source_receipt=ref.get("source")
    if not source_receipt:
        return
    path=Path(source_receipt["path"])
    try:
        observed,_=common.checked_record(path,source_receipt)
        provenance[str(path.resolve())]=observed
        import pandas as pd
        timestamps=pd.read_parquet(path)["ts_fixed_aest_end"].tolist()
        if len(timestamps)!=96:
            raise ValueError("ORIGINAL_96_ACTUAL_TIMESTAMPS_REQUIRED")
        def boundary(slot):
            slot=int(slot)
            if not 0<=slot<=96:
                raise ValueError("ORIGINAL_ROUTE_SLOT_BOUNDARY_OUT_OF_RANGE")
            return str(timestamps[slot]-timedelta(minutes=15) if slot<96 else timestamps[-1])
        for route in statistics.get("movement_arcs",[]):
            for field in ("depart","arrive","connect"):
                route[field+"_fixed_AEST_boundary"]=boundary(route[field])
        statistics["timestamp_source_receipt"]=observed
        statistics["route_timestamp_semantics"]="Original 0-based slot boundaries from frozen Actual ts_fixed_aest_end minus15min; boundary96 equals final end. No localtimezone/DST conversion."
        if common.record(path)!=observed:
            raise ValueError("ACTUAL_TIMESTAMP_SOURCE_CHANGED_DURING_REPORT")
    except (OSError,ValueError,KeyError,TypeError) as exc:
        errors.append(dict(path=str(path),error=str(exc)))


def _case(reference, manifest, label, provenance, errors):
    result,path = _load(reference,provenance,errors)
    case = dict(policy=label,status="NOT_RUN",result_path=str(path) if path else None,
        Planning_feasible=None,Planning_UB=None,Native_Runtime_seconds=None,Full_AC_Physical_PASS=None,
        source_match=None,dispatch_statistics={},actual=dict(status="NOT_RUN",physical_pass=None))
    if not result:
        return case,{},{}
    starting_errors=len(errors)
    case["status"] = result.get("status",result.get("classification","RESULT_RECORDED"))
    source,expected,match,_ = common.execution_source(result,manifest,"B2")
    case.update(source_SHA=source,source_commit=result.get("source_commit"),expected_source_SHA=expected,source_match=match,
        algorithm_version=result.get("algorithm_version"))
    stages = common.stage_documents(result,path,"B2",provenance,errors)
    stage = stages.get("M",{})
    row = common.stage_row("B2","2025-05-01","M",stage,path)
    case.update(Planning_feasible=row["feasible_accepted"],Planning_UB=row["verified_UB"],stage_identity=row,
        search_termination_reason=row["termination_reason"])
    ledger,ledgerpath = _component(result,path,"native_ledger",[path.parent/"NATIVE_RUNTIME_LEDGER.json"],provenance,errors)
    runtime = common.finite(common.first(ledger,"measured_Native_Runtime","measured_native_runtime")) if ledger else None
    if ledger and (ledger.get("inflight") is not None or any(c.get("runtime_unavailable") for c in ledger.get("calls",[]))):
        runtime=None
    if runtime is not None and runtime<0:
        errors.append(dict(path=str(ledgerpath),error="NEGATIVE_MEASURED_NATIVE_RUNTIME"));runtime=None
    case.update(Native_Runtime_seconds=runtime,native_ledger_receipt=common.record(ledgerpath) if ledgerpath and ledger else None,
        native_ledger=ledger,Native_call_count=len(ledger["calls"]) if ledger and "calls" in ledger else None,
        worker_wall_seconds=common.finite(result.get("worker_wall_seconds")))
    output = path.parent/"output"
    plan,planpath = _component(result,path,"optimized_mess_plan",[output/"OPTIMIZED_MESS_PLAN.json"],provenance,errors)
    if not plan and isinstance(stage.get("mess_plan"),dict):
        plan=stage["mess_plan"]
    if plan:
        try:
            case["dispatch_statistics"]=dispatch_statistics(plan)
            if planpath:case["dispatch_plan_receipt"]=common.record(planpath)
        except (ValueError,TypeError,KeyError) as exc:
            errors.append(dict(path=str(planpath),error=str(exc)))
    evaluation = common.evaluation_of(result,path,provenance,errors)
    _movement_source_time(case["dispatch_statistics"],evaluation,provenance,errors)
    try:
        case["actual"]=_raw_validation(result,path,evaluation,manifest,provenance,errors)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        errors.append(dict(path=str(path),error=str(exc)))
        case["actual"]=dict(status="RAW_ARRAY_UNVERIFIED",physical_pass=None)
    # The old result had no public raw SHA. Its measured diagnostics remain
    # useful, and its historical failed physical verdict never becomes PASS.
    if label == "VMAX1050_ORIGINAL":
        case["Full_AC_Physical_PASS"] = (False if result.get("actual_ac_physical_pass") is False
            or case["actual"].get("physical_pass") is False else None)
    else:
        observer,observerpath = _component(result,path,"actual_control_observer",
            [output/"ACTUAL_CONTROL_OBSERVER/ACTUAL_FRESH_CONTROL_OBSERVER.json",
             output/"ACTUAL_FRESH_CONTROL_OBSERVER.json",path.parent/"ACTUAL_CONTROL_OBSERVER/ACTUAL_FRESH_CONTROL_OBSERVER.json"],provenance,errors)
        policy_audit,policy_path = _component(result,path,"planning_model_policy_audit",
            [output/"VMAX1048_MODEL_POLICY_AUDIT.json"],provenance,errors)
        observer,policy_audit=observer or {},policy_audit or {}
        case.update(control_observer=observer,planning_model_policy_audit=policy_audit,
            observer_receipt=common.record(observerpath) if observerpath and observer else None,
            model_policy_receipt=common.record(policy_path) if policy_path and policy_audit else None)
        _validate_nested_receipts(observer,provenance,errors)
        _validate_nested_receipts(policy_audit,provenance,errors)
        slots,slots_valid=_observer_slots(observer,provenance,errors)
        case["validated_control_slots"]=slots if slots_valid else []
        policy=policy_audit.get("policy",{})
        policy_valid=(policy_audit.get("PASS") is True and policy_audit.get("audit",{}).get("PASS") is True
            and policy.get("version")==POLICY and policy.get("Planning_upper_squared")==1.098304
            and policy.get("Planning_lower_squared")==.9025 and policy.get("Actual_upper_pu")==1.05
            and manifest.get("planning_policy")==POLICY and manifest.get("planning_voltage_min_pu")==.95
            and manifest.get("planning_voltage_max_pu")==1.048 and manifest.get("planning_voltage_max_squared_pu")==1.098304
            and manifest.get("actual_voltage_min_pu")==.95 and manifest.get("actual_voltage_max_pu")==1.05
            and result.get("planning_policy")==POLICY)
        case["planning_policy_identity_validated"]=policy_valid
        model_valid=all(row.get(stagekey) is not None and row[stagekey]==policy_audit.get(policykey)
            for stagekey,policykey in (("scientific_case_sha","scientific_case_sha"),("matrix_sha","original_matrix_sha"),
                ("domain_sha","original_domain_sha"),("C3A_matrix_sha","selected_matrix_sha"),("C3A_domain_sha","selected_domain_sha")))
        case["stage_model_identity_validated"]=model_valid
        if policy_audit and not model_valid:
            errors.append(dict(path=str(policy_path),error="STAGE_MODEL_MATRIX_DOMAIN_IDENTITY_MISMATCH"))
        observer_valid=(observer.get("PASS") is True and observer.get("slots")==96
            and observer.get("control_actions_done_slots")==96 and observer.get("converged_slots")==96
            and observer.get("regulator_settings_SHA")==manifest.get("original_regcontrol_settings_SHA","3e4aaaabc10429aa2e95f810573337bdbdbb4d6ca4aeda41ae51d0325cf322cf")
            and observer.get("execution_source_SHA")==expected
            and observer.get("Actual_voltage_limits_pu")==[.95,1.05]
            and observer.get("control_settings_changed") is False and observer.get("tap_or_cap_setters_added") is False
            and observer.get("original_Fresh_and_96_slot_body_unchanged") is True
            and observer.get("original_source_SHA_before_after_equal") is True and slots_valid)
        case["control_observer_validated"]=observer_valid
        if case["actual"].get("physical_pass") is False:
            case["Full_AC_Physical_PASS"]=False
        elif case["actual"].get("physical_pass") is True:
            case["Full_AC_Physical_PASS"]=(match is True and observer_valid and policy_valid and model_valid
                and case["actual"]["metric"]["raw_current_declared_sha_verified"] is True
                and result.get("actual_ac_physical_pass") is True and result.get("PASS") is True
                and len(errors)==starting_errors)
    return case,result,evaluation


METRICS = (
    ("Planning Feasible","Planning_feasible","boolean"),("Planning UB","Planning_UB","rho"),
    ("Native Runtime","Native_Runtime_seconds","seconds"),("Native call count","Native_call_count","calls"),
    ("Search termination","search_termination_reason","classification"),("MESS movement count","movement_count","arcs"),
    ("MESS movement energy","movement_energy_kwh","kWh"),("MESS charge P integrated","charge_energy_kwh","kWh"),
    ("MESS discharge P integrated","discharge_energy_kwh","kWh"),("MESS Q absolute integrated","reactive_absolute_energy_kvarh","kvarh"),
    ("MESS Q signed integrated","reactive_signed_energy_kvarh","kvarh"),("MESS charge P peak total","Pch_peak_total_kw","kW"),
    ("MESS discharge P peak total","Pdis_peak_total_kw","kW"),("MESS Q peak absolute unit","Q_peak_absolute_unit_kvar","kvar"),
    ("Fresh OpenDSS converged","Fresh_converged_slots","slots/96"),("Actual Vmax","Vmax_pu","pu"),
    ("Actual Vmin","Vmin_pu","pu"),("Actual voltage violations","voltage_violation_count","cells"),
    ("Maximum voltage upper exceedance","maximum_upper_voltage_exceedance_pu","pu"),
    ("Actual maximum line loading","actual_maximum_line_loading_percent","percent"),
    ("Line current violations","line_current_violation_count","cells"),("Transformer current violations","transformer_current_violation_count","phase cells"),
    ("Transformer kva violations","transformer_kva_violation_count","phase rows"),("Full AC Physical PASS","Full_AC_Physical_PASS","boolean"))


def _value(case,key):
    return common.coalesce(case.get(key),case.get("dispatch_statistics",{}).get(key),
        case.get("actual",{}).get(key),case.get("actual",{}).get("metric",{}).get(key))


def _comparison(old,new):
    rows=[]
    for title,key,unit in METRICS:
        a,b=_value(old,key),_value(new,key)
        delta=(b-a if isinstance(a,(int,float)) and not isinstance(a,bool)
            and isinstance(b,(int,float)) and not isinstance(b,bool) else None)
        rows.append(dict(metric=title,unit=unit,VMAX1050_original=a,VMAX1048_diagnostic=b,new_minus_original=delta,
            original_status=old["status"],new_status=new["status"],original_source_SHA=old.get("source_SHA"),
            new_source_SHA=new.get("source_SHA"),comparison_is_pure_causal_voltage_cap_effect=False))
    return rows


def _tap_rows(old_result,new,old_evaluation,provenance,errors):
    fresh=old_evaluation.get("Fresh",{}).get("folder")
    source_path=Path(fresh)/"fresh/OPENDSS_PHASE_ARRAYS.npz" if fresh else None
    observer=new.get("control_observer",{})
    slots=new.get("validated_control_slots",[])
    original=[]
    if source_path and source_path.is_file():
        provenance[str(source_path.resolve())]=common.record(source_path)
        with np.load(source_path,allow_pickle=False) as archive:original=archive["regulator_taps"].tolist()
    newslots={r["slot"]:r for r in (slots or [])}
    names=("reg1a","reg2a","reg3a","reg3c","reg4a","reg4b","reg4c")
    rows=[]
    for slot in range(96):
        observed=newslots.get(slot,{})
        for i,name in enumerate(names):
            a=original[slot][i] if original else None
            b=observed.get("taps",[None]*7)[i]
            rows.append(dict(slot_0based=slot,slot_1based=slot+1,regulator=name,
                original_actual_tap=a,new_actual_autonomous_tap=b,new_minus_original=b-a if a is not None and b is not None else None,
                new_control_actions_done=observed.get("control_actions_done"),new_ControlIterations=observed.get("control_iterations"),
                new_Solution_Iterations_total=observed.get("Solution_Iterations_total"),
                new_Solution_MostIterationsDone=observed.get("Solution_MostIterationsDone_per_control_pass"),
                new_settings_SHA=observed.get("regulator_settings_SHA"),forced_tap_changes=0,new_result_status=new["status"]))
    return rows


def write_reports(root, old_result_path=OLD_RESULT, *, manifest_path=None, audit_root=AUDIT_ROOT):
    root,audit_root=Path(root).resolve(),Path(audit_root).resolve()
    root.mkdir(parents=True,exist_ok=True)
    provenance,errors={},[]
    manifest_path=Path(manifest_path) if manifest_path else root/"VMAX1048_DIAGNOSTIC_MANIFEST.json"
    manifest,_=_load(manifest_path,provenance,errors)
    manifest=manifest or {}
    original_ref=manifest.get("original_May01_result",old_result_path)
    old,old_result,old_eval=_case(original_ref,{},"VMAX1050_ORIGINAL",provenance,errors)
    attempt=root/"dates/B2/2025-05-01/attempts"/ATTEMPT
    result_ref=manifest.get("diagnostic_result",_existing(attempt/"RESULT.json"))
    new,new_result,new_eval=_case(result_ref,manifest,"VMAX1048_DIAGNOSTIC",provenance,errors)
    request,requestpath=_load(attempt/"REQUEST.json",provenance,errors) if (attempt/"REQUEST.json").is_file() else ({},None)
    for name in ("B2_MAY01_19CELL_INPUT_CONTROL_ENRICHMENT.json","B2_MAY01_PLANNING_ACTUAL_FACTORIAL_AUDIT.json"):
        audit_path=audit_root/name
        if audit_path.is_file():
            audit,_=_load(audit_path,provenance,errors)
            _validate_nested_receipts(audit,provenance,errors)
    # Source-owned audit enrichment is separate from the scalar report. Keep all
    # original19 rows when new Actual has not run or the diagnostic fails.
    enriched=_csv_source(audit_root/"B2_MAY01_19CELL_INPUT_CONTROL_ENRICHMENT.csv",provenance,errors)
    enriched=enriched or _csv_source(audit_root/"MAY01_VOLTAGE_VIOLATIONS_19_ENRICHED.csv",provenance,errors)
    cells=enriched or _csv_source(audit_root/"B2_MAY01_VOLTAGE_VIOLATIONS.csv",provenance,errors,True)
    newraw=new.get("actual",{}).get("metric",{}).get("raw_current_receipt",{})
    newarchive=np.load(newraw["path"],allow_pickle=False) if newraw else None
    for cell in cells:
        value=None
        if newarchive is not None and "node_axis_0based" in cell and "slot_0based" in cell:
            node,slot=int(cell["node_axis_0based"]),int(cell["slot_0based"])
            if str(newarchive["node_names"][node]) != cell["node_phase"]:
                errors.append(dict(path=newraw["path"],error="NEW_ACTUAL_ORIGINAL_19_NODE_AXIS_MISMATCH"))
            else:value=float(newarchive["voltage_pu"][slot,node])
        cell.update(new_result_status=new["status"],Actual_limit_upper_pu=1.05,Actual_limit_lower_pu=.95,
            new_Actual_V_pu=value,new_Actual_upper_exceedance_pu=max(0.,value-1.05) if value is not None else None,
            new_Actual_cell_violates=not .95<=value<=1.05 if value is not None else None)
    if newarchive is not None:newarchive.close()
    common.write_csv(root/FILENAMES[2],cells or [dict(status="AUDIT_EVIDENCE_UNAVAILABLE")])
    common.write_csv(root/FILENAMES[3],_tap_rows(old_result,new,old_eval,provenance,errors))
    attribution=_csv_source(audit_root/"B2_MAY01_PLANNING_ACTUAL_FACTORIAL_19CELLS.csv",provenance,errors)
    for row in attribution:
        row.update(diagnostic_only=True,physical_feasibility_of_counterfactual_not_claimed=True,
            intervention_scope="All4MESS96slotsP/Q; endogenous original autonomous control response, not localpartial derivative")
    common.write_csv(root/FILENAMES[4],attribution or [dict(status="FACTORIAL_EVIDENCE_UNAVAILABLE")])
    # Final admission occurs after every report input was checked. Late CSV/raw
    # axis/receipt failures cannot leave a previously computed PASS in outputs.
    if errors and new["Full_AC_Physical_PASS"] is True:
        new["Full_AC_Physical_PASS"]=False
    comparison=_comparison(old,new)
    common.write_csv(root/FILENAMES[1],comparison)
    identity=dict(schema="V42_VMAX1048_SOURCE_MODEL_IDENTITY_REPORT_V1",diagnostic_only=True,
        planning_policy=POLICY,Planning_band_pu=[.95,1.048],Planning_band_squared=[.9025,1.098304],Actual_band_pu=[.95,1.05],
        source_commit=manifest.get("source_commit"),execution_SHA=manifest.get("execution_SHA"),
        original_source_SHA=old.get("source_SHA"),new_source_SHA=new.get("source_SHA"),source_match=new.get("source_match"),
        original_source_commit=old.get("source_commit"),new_source_commit=new.get("source_commit"),
        original_algorithm_version=old.get("algorithm_version"),new_algorithm_version=new.get("algorithm_version"),
        implementation_epoch_difference="Preserved old1e691988 versus newbase982 after original U4 route witness correction; capexperiment retains sharedalgorithm contract.",
        scientific_condition_difference="Only Planning upper voltage RHS reinforced, conditional on byte-identical original FULL coefficients/domain/objective/non-upperRHS audit.",
        direct_table_is_pure_causal_voltage_cap_effect=False,
        original_stage_identity=old.get("stage_identity"),new_stage_identity=new.get("stage_identity"),
        planning_model_policy_audit=new.get("planning_model_policy_audit"),model_policy_receipt=new.get("model_policy_receipt"),
        planning_policy_identity_validated=new.get("planning_policy_identity_validated"),
        stage_model_identity_validated=new.get("stage_model_identity_validated"),
        manifest=manifest,request=request,original_dispatch=old.get("dispatch_statistics"),new_dispatch=new.get("dispatch_statistics"),
        May01_is_independent_holdout=False,all31_policy_conversion_approved=False,
        B3_M1_M2_implementation_shared=True,B3_E2E_canary="NOT_RUN",B3_A1_A2_policy="UNCHANGED",
        actual_limit_change_authorized=False,errors=errors,files=list(provenance.values()),report_implementation=common.record(__file__))
    common.write_json(root/FILENAMES[5],identity)
    common.write_json(root/FILENAMES[6],dict(schema="V42_VMAX1048_NATIVE_RUNTIME_REPORT_V1",diagnostic_only=True,
        old=dict(runtime_seconds=old["Native_Runtime_seconds"],ledger_receipt=old.get("native_ledger_receipt"),ledger=old.get("native_ledger")),
        new=dict(status=new["status"],runtime_seconds=new["Native_Runtime_seconds"],ledger_receipt=new.get("native_ledger_receipt"),ledger=new.get("native_ledger")),
        native_M_limit_seconds=1800,native_optimizer_launched_by_reporter=0,errors=errors))
    validation=dict(schema="V42_VMAX1048_ACTUAL_FRESH_VALIDATION_REPORT_V1",diagnostic_only=True,new_status=new["status"],
        original_actual=old["actual"],new_actual=new["actual"],new_control_observer=new.get("control_observer"),
        new_control_observer_validated=new.get("control_observer_validated"),new_Full_AC_Physical_PASS=new["Full_AC_Physical_PASS"],
        new_stage_model_identity_validated=new.get("stage_model_identity_validated"),
        new_source_match=new.get("source_match"),original_result_preserved=True,Actual_band_pu=[.95,1.05],errors=errors)
    common.write_json(root/FILENAMES[7],validation)
    report=_korean_report(old,new,comparison,errors,audit_root)
    temporary=(root/FILENAMES[0]).with_suffix(".md.report.tmp")
    temporary.write_text(report,encoding="utf8");temporary.replace(root/FILENAMES[0])
    return dict(status=new["status"],Planning_feasible=new["Planning_feasible"],Planning_UB=new["Planning_UB"],
        Native_Runtime_seconds=new["Native_Runtime_seconds"],Full_AC_Physical_PASS=new["Full_AC_Physical_PASS"],
        new_actual=new["actual"],comparison=comparison,errors=errors,files=[common.record(root/n) for n in FILENAMES])


def _korean_report(old,new,comparison,errors,audit_root):
    def show(value):
        return "미측정" if value is None else str(value)
    table="\n".join(f"| {r['metric']} ({r['unit']}) | {show(r['VMAX1050_original'])} | {show(r['VMAX1048_diagnostic'])} | {show(r['new_minus_original'])} |" for r in comparison)
    actual=new["actual"]
    if new["status"]=="NOT_RUN":
        verdict="새 실제 Solver/Fresh 결과는 NOT_RUN입니다. 코드·테스트만으로 정책 성공을 선언하지 않습니다."
    elif new["Full_AC_Physical_PASS"] is True:
        verdict="May01에서 새 Planning 가능해와 엄격한 Actual AC 통과가 확인되었습니다. 관측 후 선택한 정책의 진단 성공이며 독립 holdout 성능은 아닙니다."
    elif actual.get("voltage_violation_count",0)>0:
        verdict=f"새 Actual 전압 위반이 {actual['voltage_violation_count']}건 남아 엄격한 AC 판정은 FAIL입니다. 추가로 상한을 자동 조정하지 않습니다."
    elif new["Planning_feasible"] is not True:
        verdict="새 Planning 가능해가 확인되지 않았습니다. 유효한 Solver 증명 없이 TIME_LIMIT/미완료를 INFEASIBLE로 분류하지 않습니다."
    else:
        verdict="실행 결과는 기록되었지만 Source/receipt/96슬롯 제어·물리 검증이 모두 충족된 Actual PASS는 확인되지 않았습니다."
    delta=next(r["new_minus_original"] for r in comparison if r["metric"]=="Actual maximum line loading")
    return f"""# V42 Planning Vmax 1.048 진단 실험

{verdict} 새 상태는 `{new['status']}`입니다.

정책은 `{POLICY}`입니다. Planning은 0.950~1.048 pu (제곱전압 0.902500~1.098304), Actual은 기존 0.950~1.050 pu입니다. 기존 1.050 결과와 B0/B1 Source Authority는 보존합니다. 이 실험은 강화된 feasible set을 가진 새로운 과학적 정책이며 원본과 동일 모델이라고 주장하지 않습니다.

보존 원본 Source SHA는 `{old.get('source_SHA')}`, 새 Source SHA는 `{new.get('source_SHA') or '미실행'}`입니다. 원본은 1e691988 epoch이고 새 후보는 U4 route witness 판정을 수정한 982 기반 소스에서 실행합니다. 공통 알고리즘 계약은 유지하지만 구현 epoch 및 탐색 경로·Native 시간이 다를 수 있습니다. 독립 모델 감사의 FULL 계수·목적함수·domain·전압 상한 이외 RHS 일치는 과학적 입력 조건에서 상한만 달라짐을 확인합니다. 그러나 이 보존 결과 대 새 후보 표의 성능 차이를 안전여유 상한의 순수 인과 효과라고 해석하지 않습니다. 별도 동일 소스 1.050 재실행은 이 표에 포함하지 않았습니다.

| 지표 | 원본 1.050 | 새 1.048 | 새−원본 |
|---|---:|---:|---:|
{table}

Pch/Pdis/Q 비교는 저장된 원래 FULL unit/site/slot 좌표에서 계산합니다. 충전·방전 에너지는 각각 sum(Pch/Pdis)×0.25h, Q 절대 에너지는 sum(abs(Q))×0.25h이고 signed Q도 별도 표기합니다. 수치 clipping은 하지 않습니다. 이동 횟수·에너지는 원본 export의 선택 travel arc와 energy_kwh를 사용하며 위치 변화만으로 추정하지 않습니다. 원래 depart/arrive/connect 슬롯 좌표는 SOURCE_MODEL_IDENTITY에 그대로 보존합니다.

Actual 최대선로부하율은 동일 line-phase 집합과 NormalAmps를 사용한 100×max(abs(raw A)/NormalAmps)입니다. transformer를 포함한 rho_max_AC를 대입하지 않습니다. 새−원본 차이는 {show(delta)} percentage points입니다. 전압 개선 여부와 별도로 이 전류 trade-off를 평가합니다. raw SHA가 선언 receipt와 맞지 않으면 PASS를 승인하지 않습니다.

원본 Actual의 19개 MESS PCC 과전압은 그대로 유지합니다. 원본 13개 AC 배열을 비트 재현한 factorial은 Full19, P-only4(원래19개와 다른 셀), Q-only34, zero0건입니다. 원래19개 중 Q-only18/P-only0입니다. 조건부 P/Q 효과는 4대 MESS의 96슬롯 전체 개입과 원래 자율 탭 응답을 함께 포함하며 특정 장치의 국소 편미분이 아닙니다. P-only/Q-only는 새 가능 최적화점이나 SOC/PCS 운전 증명으로 승인하지 않습니다.

최대 위반 STA08.A의 Planning–Actual 차이 +0.012847079586972 pu는 zero 기준 −0.000037724832626 pu와 MESS 응답 예측 오차 +0.012884804419598 pu로 분해됩니다. 원래 source-backed affine 제곱전압 모델은 forecast reference 상태에서 탭을 수렴시킨 후 고정하여 sensitivity를 만들고 원래 April joint-gradient export를 사용합니다. Actual은 동일 설정의 자율 제어를 수행합니다. 공통 제어 설정 오류는 발견되지 않았지만 forecast·비선형 응답·탭 이력을 유일한 원인 하나로 식별하지 않습니다. 상세 원본 감사는 [{audit_root.name} 원인 보고서]({(audit_root/'B2_MAY01_MESS_PQ_CAUSAL_AUDIT_KO.md').as_posix()})에 있습니다.

B2 M/B3 M1/M2는 동일 공통 정책 인터페이스를 사용하며 B3 A1/A2의 원래 계약은 유지합니다. B3 실제 E2E Canary는 NOT_RUN으로 기록합니다. May01 성공만으로 B3나 31일 정책 전환을 승인하지 않습니다. 추가 B2/B3 검증, Source/Model Identity와 독립 평가를 확인해야 합니다. 전체 31일 전환 승인은 없습니다. May01 결과를 보고 선택한 1.048 정책이므로 이 날짜를 독립 holdout이라고 부르지 않습니다.

검증 오류: {json.dumps(errors,ensure_ascii=False)}

8개 산출물의 원본 입력·실행·모델·raw SHA는 JSON receipt에서 확인할 수 있습니다. 보고서 생성기의 optimizer/Fresh 실행 횟수는 0입니다.
"""


summarize_experiment=write_reports


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("root");parser.add_argument("--manifest");parser.add_argument("--old-result",default=str(OLD_RESULT));parser.add_argument("--audit-root",default=str(AUDIT_ROOT))
    args=parser.parse_args()
    result=write_reports(args.root,args.old_result,manifest_path=args.manifest,audit_root=args.audit_root)
    print(json.dumps({k:v for k,v in result.items() if k not in ("comparison","files")},ensure_ascii=False))
