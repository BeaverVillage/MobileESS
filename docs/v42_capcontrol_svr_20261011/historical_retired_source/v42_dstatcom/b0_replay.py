"""Original B0 frozen Actual arrays through the unchanged ACTUAL Fresh backend.

There is no AIDC/MESS optimization or fabricated Planning acceptance. Every ON
replay first reproduces the preserved OFF voltage/current/tap/cap arrays exactly.
"""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import inspect
import json
from unittest.mock import patch

import numpy as np

from v42_b3_joint.contracts import canonical, digest, require, require_sha
from .integration import record, scenario_scope, validate_scenario

VERSION = "V42_B0_SAME_FROZEN_PLAN_WITH_DSTATCOM_V1"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(canonical(value)+"\n")


def _bit_equal(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()


def _resolve_raw(expected, folder):
    from v42_capacity.common import resolve
    try:
        return resolve(expected)
    except ValueError:
        # Relocation is admitted only by the original exact byte SHA/length.
        candidate = folder.parent.parent / "INPUT/BUNDLE" / folder.name / "DERIVED_AEMO_ACTUAL.parquet"
        require(candidate.is_file(), "B0_EXACT_ACTUAL_EXOGENOUS_SOURCE_UNAVAILABLE")
        actual = record(candidate)
        require(actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"],
                "B0_RELOCATED_ACTUAL_SOURCE_SHA_DRIFT")
        return candidate


def load_original(day, source_folder):
    folder = Path(source_folder).resolve()
    require(folder.name == "DAY_"+day.replace("-",""), "B0_EXACT_DAY_FOLDER_REQUIRED")
    names = ("V_ACTUAL_AC.npz", "ACTUAL_PHYSICAL.npz", "RAW_CONTROL_LOG.json",
             "RAW_PHYSICAL_INPUT_LOG.json", "FRESH_ACTUAL_AC_RECEIPT.json", "INPUT_FREEZE.json")
    require(all((folder/name).is_file() for name in names), "B0_PRESERVED_DAY_EVIDENCE_MISSING")
    controls, inputs, fresh, freeze = [_read(folder/name) for name in names[2:]]
    require(inputs["day"] == fresh["day"] == freeze["day"] == day,
            "B0_PRESERVED_SOURCE_DAY_DRIFT")
    require(inputs.get("alpha_BG") == 1.15 and inputs.get("PV_scaled_by_alpha_BG") is False,
            "B0_ORIGINAL_BACKGROUND_BINDING_REQUIRED")
    require(len(inputs["slots"]) == len(controls["slots"]) == 96
            and all(row["slot"] == k and row.get("all_MESS_PQ_zero") is True
                    for k,row in enumerate(inputs["slots"])), "B0_96_FROZEN_ZERO_MESS_INPUTS_REQUIRED")
    with np.load(folder/"V_ACTUAL_AC.npz",allow_pickle=False) as archive:
        arrays = {k:archive[k].copy() for k in archive.files}
    with np.load(folder/"ACTUAL_PHYSICAL.npz",allow_pickle=False) as archive:
        p,q = archive["PCC_P_kw"].copy(),archive["PCC_Q_kvar"].copy()
    require(p.shape == q.shape == (96,12) and np.isfinite(p).all() and np.isfinite(q).all(),
            "B0_ORIGINAL_PHYSICAL_POWER_AXIS_REQUIRED")
    require(_bit_equal(p,arrays["PCC_P_kw"]) and _bit_equal(q,arrays["PCC_Q_kvar"])
            and np.array_equal(p,np.array([r["PCC_P_kw"] for r in inputs["slots"]]))
            and np.array_equal(q,np.array([r["PCC_Q_kvar"] for r in inputs["slots"]])),
            "B0_PRESERVED_FROZEN_POWER_PACKET_DRIFT")
    for expected, name in ((fresh["Actual_voltage"],"V_ACTUAL_AC.npz"),
                            (freeze["physical_PQ"],"ACTUAL_PHYSICAL.npz")):
        actual = record(folder/name)
        require(actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"],
                "B0_ORIGINAL_RECEIPT_SHA_DRIFT:"+name)
    require(inputs["Actual_source"]["sha256"] == freeze["Actual_raw"]["sha256"],
            "B0_ACTUAL_EXOGENOUS_RECEIPT_DRIFT")
    raw = _resolve_raw(inputs["Actual_source"],folder)
    sources = [record(folder/name) for name in names] + [record(raw)]
    return dict(day=day,folder=folder,arrays=arrays,p=p,q=q,inputs=inputs,controls=controls,
                fresh=fresh,freeze=freeze,raw=raw,sources=sources)


def _bindings():
    from v42_regcontrol import authority
    from v42_regcontrol.runner import background
    from v42_may_campaign_native90.operations import isolated_compile
    from v42_may_campaign_native90.preflight import native_zero
    authority.source()
    from dayahead.v28r2 import opendss_backend as backend, opendss_mapping as mapping
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from v42_regcontrol.common import CODE
    return authority,background,isolated_compile,native_zero,backend,mapping,FrozenTrajectory,CODE


def _original_actual(payload, output, progress=None):
    """Exact original NativeAllocation+zero-MESS bindings; Original body intact."""
    import pandas as pd
    authority,background,isolated_compile,native_zero,backend,mapping,FrozenTrajectory,CODE = _bindings()
    output = Path(output).resolve()
    require(not output.exists(), "B0_ACTUAL_REPLAY_OUTPUT_OVERWRITE_FORBIDDEN")
    output.mkdir(parents=True)
    exo = pd.read_parquet(payload["raw"])
    stamps = [pd.Timestamp(t).tz_convert("Etc/GMT-10").isoformat() for t in exo.ts_fixed_aest_end]
    require(stamps == payload["arrays"]["timestamps_96"].tolist(), "B0_ORIGINAL_ACTUAL_TIMESTAMP_AXIS_DRIFT")
    bg = background(stamps,exo.demand_mw.tolist(),exo.rooftop_pv_mw.tolist())
    expected_bg = payload["inputs"]["background_normalization_sources"]
    current_bg = bg.evidence["source_paths_and_sha256"]
    require(set(expected_bg) == set(current_bg) and all(expected_bg[k]["sha256"] == current_bg[k]["sha256"]
            for k in expected_bg), "B0_ORIGINAL_BACKGROUND_AUTHORITY_DRIFT")
    m=authority.source()
    engine,adapter,initial=authority.compile_verified()
    try:
        require(initial == payload["controls"]["source_initial_inventory"], "B0_ORIGINAL_INITIAL_CONTROL_INVENTORY_DRIFT")
        branches,topology=m["oriented_branches"](engine)
        nodes=tuple(sorted(n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit(".",1)[-1] in ("1","2","3")))
        branch_names=[f"{b.branch_id}::{b.phase}" for b in branches]
        require(list(nodes)==payload["arrays"]["node_names"].tolist()
                and branch_names==payload["arrays"]["branch_names"].tolist(), "B0_ORIGINAL_NODE_BRANCH_AXIS_DRIFT")
        native=m["NativeAllocation"].from_adapter(adapter)
    finally:
        engine.Basic.ClearAll()
    binding=SimpleNamespace(factories=[SimpleNamespace(data=SimpleNamespace(branches=branches))])
    context=SimpleNamespace(legacy_context=(None,None,bg,binding,None,None))
    zeros=np.zeros((96,4));locations=np.asarray([("STA01","STA12","STA08","STA06") for _ in range(96)],dtype=str)
    trajectory=FrozenTrajectory(payload["day"],"ACTUAL","B0",payload["p"],payload["q"],zeros,zeros,
        ("MESS01","MESS02","MESS03","MESS04"),locations,digest(dict(arm="B0",day=payload["day"],
            frozen_Actual_power=payload["sources"][1],Actual_exogenous=record(payload["raw"]))))
    trajectory.validate()
    body=backend.run_fresh_opendss.__code__
    original_compile,original_voltage=authority.compile_verified,backend._voltage_vector
    logs,applied,compilations=[],[],[]
    def compile_current(_assets):
        engine,ad,inventory=isolated_compile(original_compile,output,compilations)
        native.validate_native_engine(engine)
        return engine,ad
    def apply_current(engine,ad,_context,tr,slot):
        totals,ledger,allocation=native.apply(engine,bg,slot)
        for row in ad["pv_generators"]:
            key=(str(row["bus"]).lower(),"ABC"[int(row["phase"])-1])
            mapping._set_generator(engine,row["generator_name"],bg.pv_generation_kw_96[slot].get(key,0),0)
        for i in range(12): mapping._set_load(engine,f"IDC_IDC{i+1:02d}",tr.pcc_p_kw[slot,i],tr.pcc_q_kvar[slot,i])
        for name in engine.Generators.AllNames():
            if name.lower().startswith("mess_dis_"): mapping._set_generator(engine,name,0,0)
        for name in engine.Loads.AllNames():
            if name.lower().startswith("mess_chg_"): mapping._set_load(engine,name,0,0)
        authority.assert_inventory(m["inventory"](engine))
        require(totals == payload["inputs"]["slots"][slot]["native_load_PQ"],
                "B0_ENGINE_APPLIED_BACKGROUND_POWER_DRIFT")
        actual_p,actual_q=[],[]
        for i in range(12):
            engine.Loads.Name(f"IDC_IDC{i+1:02d}");actual_p.append(float(engine.Loads.kW()));actual_q.append(float(engine.Loads.kvar()))
        require(np.array_equal(actual_p,tr.pcc_p_kw[slot]) and np.array_equal(actual_q,tr.pcc_q_kvar[slot]),
                "B0_ENGINE_APPLIED_AIDC_POWER_DRIFT")
        applied.append(dict(slot=slot,PCC_P_kw=actual_p,PCC_Q_kvar=actual_q,all_MESS_PQ_zero=True,
                            native_load_PQ=totals,allocation_conservation=allocation))
    def controls(engine,_voltage,slot):
        authority.assert_inventory(m["inventory"](engine))
    def measure_voltage(engine,axis):
        values=original_voltage(engine,axis)
        inventory=m["inventory"](engine);authority.assert_inventory(inventory)
        taps,caps=m["native_state"](engine)
        require(bool(engine.Solution.ControlActionsDone()), "B0_ORIGINAL_CONTROL_ACTIONS_INCOMPLETE")
        previous=logs[-1]["taps"] if logs else [r["initial_tap"] for r in initial["regulators"]]
        logs.append(dict(slot=len(logs),taps=taps,previous_taps=previous,caps=caps,
            ControlIterations=int(engine.Solution.ControlIterations()),Iterations=int(engine.Solution.Iterations()),
            MostIterationsDone=int(engine.Solution.MostIterationsDone()),ControlActionsDone=True,
            configured_MaxControlIterations=int(engine.Solution.MaxControlIterations()),
            configured_MaxIterations=int(engine.Solution.MaxIterations()),
            regulator_settings_SHA=authority.digest(authority.regulator_parameters(inventory))))
        return values
    sources=[record(Path(inspect.getfile(function))) for function in
             (backend.run_fresh_opendss,authority.compile_verified,background,mapping._set_load,
              mapping._set_generator,m["branch_measurement"])]+[record(__file__)]
    with ExitStack() as stack:
        stack.enter_context(patch.object(backend,"compile_clean_engine",compile_current))
        stack.enter_context(patch.object(backend,"apply_trajectory_slot",apply_current))
        stack.enter_context(patch.object(backend,"apply_frozen_native_state",controls))
        stack.enter_context(patch.object(backend,"_branch_measurement",m["branch_measurement"]))
        stack.enter_context(patch.object(backend,"_voltage_vector",measure_voltage))
        attempts=stack.enter_context(native_zero())
        result=backend.run_fresh_opendss(repo=CODE,context=context,voltage=dict(node_names=nodes),trajectory=trajectory,
                                       output=output/"fresh",progress=progress)
        require(not attempts, "B0_ACTUAL_OPTIMIZER_ENTRY_FORBIDDEN")
    require(backend.run_fresh_opendss.__code__ is body, "B0_ORIGINAL_96_SLOT_BODY_MUTATION")
    require(all(record(r["path"])==r for r in payload["sources"]+sources), "B0_ORIGINAL_SOURCE_OR_EVIDENCE_MUTATION")
    comparable=dict(node_names=np.array(nodes),branch_names=np.array(branch_names),V_ACTUAL_AC=result.voltage_pu,
        current_A=result.phase_current_a,current_pu=result.phase_current_loading_pu,
        transformer_kVA_pu=result.transformer_total_kva_loading_pu,regulator_taps=result.regulator_taps,
        capacitor_states=result.capacitor_states,converged=result.convergence,
        control_iterations=np.array([r["ControlIterations"] for r in logs]),
        convergence_iterations=np.array([r["Iterations"] for r in logs]),
        actual_previous_taps=np.array([r["previous_taps"] for r in logs]),timestamps_96=np.array(stamps),
        PCC_P_kw=payload["p"],PCC_Q_kvar=payload["q"])
    comparable={k:np.asarray(v,dtype=payload["arrays"][k].dtype) for k,v in comparable.items()}
    np.savez_compressed(output/"V_ACTUAL_AC.npz",**comparable)
    _write(output/"RAW_CONTROL_LOG.json",dict(day=payload["day"],source_initial_inventory=initial,slots=logs))
    _write(output/"RAW_PHYSICAL_INPUT_LOG.json",dict(day=payload["day"],slots=applied,
        Actual_source=record(payload["raw"]),all_MESS_PQ_zero=True,original_frozen_power_receipt=payload["sources"][1]))
    line=np.array(result.branch_kinds)=="line";tx=~line
    strict=dict(voltage_violations=int(np.sum((result.voltage_pu<.95)|(result.voltage_pu>1.05))),
        line_current_violations=int(np.sum(result.phase_current_loading_pu[:,line]>1)),
        transformer_current_violations=int(np.sum(result.phase_current_loading_pu[:,tx]>1)),
        transformer_kVA_violations=int(np.sum(result.transformer_total_kva_loading_pu[:,tx]>1)))
    physical_pass=bool(result.convergence.all()) and len(logs)==96 and not any(strict.values())
    receipt=dict(schema=VERSION,arm="B0",day=payload["day"],scope="PRESERVED_ORIGINAL_B0_ACTUAL_FROZEN_PLAN",
        original_Physical_PASS=physical_pass,summary=result.summary,literal_physical_violations=strict,
        Original_96_slot_backend_body_unchanged=True,Actual_optimizer_calls=0,Native_optimizer_calls=0,
        source_binding_receipts=payload["sources"],execution_source_receipts=sources,
        current_check="ORIGINAL_ALL_PHASE_NORMALAMPS_WITH_ORIGINAL_SERVICE_TRANSFORMER_KVA",
        original_logical_Fresh_slots=96,compilations=compilations,arrays_receipt=record(output/"V_ACTUAL_AC.npz"))
    _write(output/"B0_ORIGINAL_FRESH_REPLAY_RECEIPT.json",receipt)
    return receipt,comparable


def replay_pair(day, source_folder, output, *, scenario, source_SHA, progress=None):
    """OFF proof gate then ON; caller must hold the sealed Actual-only permit."""
    from .authority import authorize_actual
    require_sha(source_SHA)
    scenario,_,_=validate_scenario(scenario)
    authorize_actual("B0",day,source_SHA,scenario["scenario_SHA"])
    output=Path(output).resolve()
    require(not output.exists(), "B0_PAIR_OUTPUT_OVERWRITE_FORBIDDEN")
    output.mkdir(parents=True)
    payload=load_original(day,source_folder)
    off,off_arrays=_original_actual(payload,output/"OFF",progress)
    equality={key:_bit_equal(old,off_arrays[key]) for key,old in payload["arrays"].items()}
    proof=dict(schema=VERSION,day=day,arm="B0",PASS=all(equality.values()),
        original_comparable_array_bit_identity=equality,
        preserved_sources=payload["sources"],OFF_receipt=record(output/"OFF/B0_ORIGINAL_FRESH_REPLAY_RECEIPT.json"),
        source_SHA=source_SHA,scenario_SHA=scenario["scenario_SHA"],Native_optimizer_calls=0)
    _write(output/"B0_OFF_BIT_REPRODUCTION_GATE.json",proof)
    require(proof["PASS"], "B0_EXACT_OFF_BIT_REPRODUCTION_FAILED_STOP_ON")
    with scenario_scope(scenario,output/"ON/DSTATCOM",source_SHA=source_SHA,arm="B0",day=day) as audit:
        on,on_arrays=_original_actual(payload,output/"ON/FRESH",progress)
    require(all(record(r["path"])==r for r in payload["sources"]), "B0_PRESERVED_EVIDENCE_SHA_DRIFT_AFTER_PAIR")
    result=dict(schema=VERSION,status="SAME_FROZEN_PLAN_WITH_DSTATCOM",day=day,arm="B0",
        PASS=on["original_Physical_PASS"] and audit.result["hardware_and_controller_PASS"],
        source_SHA=source_SHA,scenario_SHA=scenario["scenario_SHA"],Original_MILP_or_Planning_optimization_calls=0,
        Actual_optimizer_calls=0,Native_optimizer_calls=0,OFF_exact_reproduction=proof,
        OFF=off,ON=on,hardware_and_controller=audit.result,
        hardware_audit_receipt=audit.receipt,source_binding_receipts=payload["sources"],
        original_B0_results_modified=False,original_plan_reoptimized=False)
    _write(output/"B0_SAME_FROZEN_PLAN_WITH_DSTATCOM.json",result)
    return result
