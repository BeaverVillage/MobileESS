"""Independent Forecast/Actual autonomous hardware around Original Fresh.

A source-bound scope admits one exact DAYAHEAD or ACTUAL backend frame. Each
compiles Source Initial State and constructs its own devices/controller; no
Planning Q, modes or taps are passed to Actual. MILP arithmetic stays unchanged.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone
from pathlib import Path
import csv
import hashlib
import inspect
import json
import os
import sys
import numpy as np
from unittest.mock import patch

from v42_b3_joint.contracts import canonical, digest, require, require_sha
from .device import SiteSpec, install
from .settings import ControllerSettings

SCHEMA = "V42_DSTATCOM_PHYSICAL_SCENARIO_V1"
VERSION = "V42_DSTATCOM_INDEPENDENT_PHYSICAL_INTEGRATION_V2"
_active = ContextVar("v42_dstatcom_actual_scenario", default=None)


def record(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), sha256=sha, bytes=path.stat().st_size)


def scenario_identity(scenario):
    """The four frozen identity fields; scenario_SHA is their canonical digest."""
    return {key: scenario[key] for key in ("schema", "hardware", "controller", "connection_manifest")}


def validate_scenario(scenario):
    value = json.loads(canonical(scenario))
    require(value.get("schema") == SCHEMA, "DSTATCOM_EXPLICIT_PHYSICAL_SCENARIO_REQUIRED")
    require_sha(value.get("scenario_SHA"))
    require(digest(scenario_identity(value)) == value["scenario_SHA"], "DSTATCOM_FROZEN_SCENARIO_SHA_DRIFT")
    receipt = value["connection_manifest"]
    require(isinstance(receipt, dict) and record(receipt["path"]) == receipt,
            "DSTATCOM_CONNECTION_MANIFEST_RECEIPT_DRIFT")
    require(isinstance(value["hardware"], list) and 1 <= len(value["hardware"]) <= 36,
            "DSTATCOM_EXPLICIT_HARDWARE_COLLECTION_REQUIRED")
    specs = tuple(SiteSpec.from_dict(row) for row in value["hardware"])
    require(len({getattr(s,"device_id",None) or s.site_id for s in specs}) == len(specs),
            "DSTATCOM_DUPLICATE_PHYSICAL_DEVICE_FORBIDDEN")
    require(len({s.pcc_bus.lower() for s in specs}) == len(specs), "DSTATCOM_DUPLICATE_PCC_FORBIDDEN")
    settings = ControllerSettings.from_dict(value["controller"])
    require(canonical(settings.to_dict()) == canonical(value["controller"]),
            "DSTATCOM_FROZEN_CONTROLLER_COMPLETE_VERSIONED_FIELDS_REQUIRED")
    require(all(canonical(spec.to_dict()) == canonical(row) for spec,row in zip(specs,value["hardware"])),
            "DSTATCOM_FROZEN_HARDWARE_COMPLETE_FIELDS_REQUIRED")
    return value, specs, settings


def _physical_frame(body, namespace):
    frame = sys._getframe(1)
    try:
        while frame is not None:
            if frame.f_code is body:
                trajectory = frame.f_locals.get("trajectory")
                if getattr(trajectory, "namespace", None) == namespace:
                    return dict(day=trajectory.day, arm=trajectory.case,
                                slot=frame.f_locals.get("slot"), trajectory=trajectory, namespace=namespace)
                return None
            frame = frame.f_back
    finally:
        del frame
    return None


def _bindings():
    from v42_regcontrol import authority
    from v42_may_campaign_native90 import operations
    authority.source()
    from dayahead.v28r2 import opendss_backend as backend, opendss_mapping as mapping
    from v42_pr134_b1 import replay
    from .controller import LocalVoltVarController
    return authority, operations, backend, mapping, replay, LocalVoltVarController


def _physical_inputs(engine):
    """Read original load/generator setpoints, excluding this added hardware."""
    result = {}
    for kind, collection in (("Load", engine.Loads), ("Generator", engine.Generators)):
        for name in collection.AllNames():
            if name.lower().startswith("dstat_") or name.lower() == "none":
                continue
            collection.Name(name)
            result[kind + "." + name] = [float(collection.kW()), float(collection.kvar())]
    return result


def _trajectory_sha(trajectory):
    values = {key: hashlib.sha256(np.asarray(getattr(trajectory, key)).tobytes()).hexdigest()
              for key in ("pcc_p_kw", "pcc_q_kvar", "mess_p_kw", "mess_q_kvar", "mess_locations_96x4")}
    return digest(dict(day=trajectory.day, arm=trajectory.case, namespace=trajectory.namespace, arrays=values))


def _controls(engine, authority):
    source = authority.source()
    inventory = source["inventory"](engine)
    authority.assert_inventory(inventory)
    taps, caps = source["native_state"](engine)
    settings = authority.regulator_parameters(inventory)
    require(len(taps) == len(inventory["regulators"]) == 7 and caps == [1, 1, 1, 1]
            and inventory["CapControl_count"] == 0, "DSTATCOM_ORIGINAL_SEVEN_REG_FOUR_CAPS_REQUIRED")
    require(int(engine.Solution.MaxControlIterations()) == 100 and int(engine.Solution.MaxIterations()) == 15
            and int(engine.Solution.ControlMode()) == 0, "DSTATCOM_ORIGINAL_SOLUTION_SETTINGS_DRIFT")
    return dict(regulator_names=[r["name"] for r in inventory["regulators"]],
        regulator_enabled=[bool(r["enabled"]) for r in inventory["regulators"]],
        regulator_settings_SHA=authority.digest(settings),
        individual_regulator_settings_SHA={r["name"]: authority.digest(r) for r in settings["regulators"]},
        taps=list(map(float, taps)), capacitor_states=list(map(int, caps)), CapControl_count=0,
        control_actions_done=bool(engine.Solution.ControlActionsDone()),
        solution_converged=bool(engine.Solution.Converged()),
        ControlIterations=int(engine.Solution.ControlIterations()),
        Solution_Iterations_total=int(engine.Solution.Iterations()),
        Solution_TotalIterations=int(engine.Solution.TotalIterations()),
        Solution_MostIterationsDone_per_control_pass=int(engine.Solution.MostIterationsDone()),
        configured_MaxControlIterations=int(engine.Solution.MaxControlIterations()),
        configured_MaxIterations=int(engine.Solution.MaxIterations()),
        control_mode=int(engine.Solution.ControlMode()))


class PhysicalScenario:
    def __init__(self, scenario, output, *, source_SHA, arm, day, namespace="ACTUAL"):
        require_sha(source_SHA)
        require(arm in ("B0", "B1", "B2", "B3"), "DSTATCOM_COMPARISON_ARM_REQUIRED")
        require(date.fromisoformat(day).isoformat() == day, "DSTATCOM_ISO_DAY_REQUIRED")
        self.scenario, self.specs, self.settings = validate_scenario(scenario)
        require(namespace in ("DAYAHEAD", "ACTUAL"), "DSTATCOM_EXPLICIT_PHYSICAL_NAMESPACE_REQUIRED")
        self.namespace = namespace
        self.prefix = "PLANNING" if namespace == "DAYAHEAD" else "ACTUAL"
        self.output, self.source_SHA, self.arm, self.day = Path(output).resolve(), source_SHA, arm, day
        require(not (self.output / ("DSTATCOM_"+self.prefix+"_PHYSICAL_AUDIT.json")).exists(),
                "DSTATCOM_PHYSICAL_AUDIT_OVERWRITE_FORBIDDEN")
        self.rows, self.sources, self.installations = [], [], []
        self.sessions, self.receipt, self.result = {}, None, None
        self.physical_solve_events = []
        self.trajectory_SHA = None
        self.source_initial_controls = None
        self.initial_Q_state_transferred_from_other_namespace = False

    def _identity(self, identity):
        require(identity["day"] == self.day and identity["arm"] == self.arm
                and getattr(identity["trajectory"], "namespace", None) == self.namespace,
                "DSTATCOM_ACTUAL_FRAME_SOURCE_IDENTITY_DRIFT")
        trajectory_SHA = _trajectory_sha(identity["trajectory"])
        if self.trajectory_SHA is None:
            self.trajectory_SHA = trajectory_SHA
        require(trajectory_SHA == self.trajectory_SHA, "DSTATCOM_FROZEN_ACTUAL_TRAJECTORY_MUTATION")

    def install_actual(self, engine, identity, authority, controller_class):
        self._identity(identity)
        require(not self.sessions, "DSTATCOM_ONE_ORIGINAL_FRESH_ENGINE_PER_DAY_REQUIRED")
        authority.assert_inventory(authority.source()["inventory"](engine), initial=True)
        self.source_initial_controls = _controls(engine, authority)
        original_inputs = _physical_inputs(engine)
        devices = [install(engine, spec, self.settings) for spec in self.specs]
        authority.assert_inventory(authority.source()["inventory"](engine), initial=True)
        require(_physical_inputs(engine) == original_inputs, "DSTATCOM_INSTALL_ORIGINAL_LOAD_GENERATOR_MUTATION")
        self.installations = [device.installation_receipt for device in devices]
        self.sessions[id(engine)] = (engine, controller_class(devices, self.settings, source_SHA=self.source_SHA))

    def settle_actual(self, engine, identity, authority):
        self._identity(identity)
        require(id(engine) in self.sessions and self.sessions[id(engine)][0] is engine,
                "DSTATCOM_ACTUAL_ENGINE_NOT_INSTALLED")
        require(identity["slot"] == len(self.rows) and len(self.rows) < 96,
                "DSTATCOM_SEQUENTIAL_96_ACTUAL_SLOTS_REQUIRED")
        initial_event = dict(slot=identity["slot"],kind="ORIGINAL_SLOT_INITIAL_SOLVE",completed=True,controls=None)
        self.physical_solve_events.append(initial_event)
        before = _controls(engine, authority)
        initial_event["controls"] = before
        require(before["solution_converged"] and before["control_actions_done"],
                "DSTATCOM_ORIGINAL_INITIAL_SOLVE_NOT_SETTLED")
        inputs = _physical_inputs(engine)
        solution = engine.Solution
        solution_class = type(solution)
        feedback, original_solve = [], solution_class.SolveSnap
        def solve_feedback(instance, *args, **kwargs):
            if instance is not solution:
                return original_solve(instance, *args, **kwargs)
            event = dict(slot=identity["slot"],kind="ADDITIONAL_DSTATCOM_FEEDBACK_SOLVE",completed=False,controls=None)
            self.physical_solve_events.append(event)
            result = original_solve(instance, *args, **kwargs)
            event["completed"] = True
            controls = _controls(engine, authority)
            event["controls"] = controls
            feedback.append(controls)
            require(controls["regulator_settings_SHA"] == before["regulator_settings_SHA"],
                    "DSTATCOM_FEEDBACK_ORIGINAL_CONTROL_SETTINGS_MUTATION")
            require(_physical_inputs(engine) == inputs, "DSTATCOM_FEEDBACK_ORIGINAL_EXOGENOUS_OR_PLAN_MUTATION")
            require(controls["solution_converged"] and controls["control_actions_done"],
                    "DSTATCOM_FEEDBACK_DSS_CONTROLS_NOT_SETTLED")
            return result
        # OpenDSSDirect interface instances reject attribute writes. The class
        # route observes only this isolated Solution instance and forwards every
        # other context unchanged; it restores the exact original class method.
        with patch.object(solution_class, "SolveSnap", solve_feedback):
            control = self.sessions[id(engine)][1].settle_slot(engine, identity["slot"])
        after = _controls(engine, authority)
        self._identity(identity)
        require(_physical_inputs(engine) == inputs, "DSTATCOM_FINAL_ORIGINAL_EXOGENOUS_OR_PLAN_MUTATION")
        require(after["regulator_settings_SHA"] == before["regulator_settings_SHA"],
                "DSTATCOM_FINAL_ORIGINAL_CONTROL_SETTINGS_MUTATION")
        require(after["solution_converged"] and after["control_actions_done"],
                "DSTATCOM_FINAL_DSS_CONTROLS_NOT_SETTLED")
        require(type(control) is dict and type(control.get("PASS")) is bool,
                "DSTATCOM_CONTROLLER_PHYSICAL_RECEIPT_REQUIRED")
        if "additional_feedback_solve_count" in control:
            require(control["additional_feedback_solve_count"] == len(feedback),
                    "DSTATCOM_FEEDBACK_SOLVE_COUNT_DRIFT")
        previous = self.rows[-1]["settled_original_controls"]["taps"] if self.rows else before["taps"]
        self.rows.append(dict(slot=identity["slot"], day=self.day, arm=self.arm, namespace=self.namespace,
            frozen_trajectory_SHA=self.trajectory_SHA, original_inputs_SHA=digest(inputs),
            original_input_setpoints_unchanged=True, original_initial_solve_controls=before,
            settled_original_controls=after, feedback_solve_controls=feedback,
            additional_feedback_solve_count=len(feedback), total_physical_SolveSnap_count=1+len(feedback),
            original_initial_solve_count=1, previous_settled_taps=previous,
            settled_tap_changes=[a-b for a,b in zip(after["taps"],previous)], controller=control,
            PASS=control["PASS"] and control.get("controller_converged") is True
                and control.get("solution_converged") is True and control.get("ControlActionsDone") is True))
        self.write_progress()

    def write_progress(self, *, status="RUNNING", error=None):
        """Small atomic per-slot observer heartbeat; no traces or scientific arrays."""
        self.output.mkdir(parents=True, exist_ok=True)
        last=self.rows[-1] if self.rows else None
        controls=last["settled_original_controls"] if last else {}
        value=dict(schema="V42_DSTATCOM_PHYSICAL_PROGRESS_V2",status=status,namespace=self.namespace,
            phase="LOCAL_HARDWARE_SLOT_SETTLED" if last else self.prefix+"_NOT_RUN",
            updated_UTC=datetime.now(timezone.utc).isoformat(),PID=os.getpid(),
            arm=self.arm,day=self.day,execution_source_SHA=self.source_SHA,scenario_SHA=self.scenario["scenario_SHA"],
            logical_Fresh_slots_completed=len(self.rows),logical_Fresh_slots_target=96,
            last_completed_slot=last["slot"] if last else None,
            additional_feedback_solve_count=sum(e["kind"]=="ADDITIONAL_DSTATCOM_FEEDBACK_SOLVE" for e in self.physical_solve_events),
            total_physical_SolveSnap_count=len(self.physical_solve_events),
            completed_physical_SolveSnap_count=sum(e["completed"] for e in self.physical_solve_events),
            hardware_or_controller_failed_slots_count=sum(not row["PASS"] for row in self.rows),
            last_slot_hardware_and_controller_PASS=last["PASS"] if last else None,
            regulator_settings_SHA=controls.get("regulator_settings_SHA"),
            regulator_enabled=controls.get("regulator_enabled"),taps=controls.get("taps"),
            capacitor_states=controls.get("capacitor_states"),
            configured_MaxControlIterations=controls.get("configured_MaxControlIterations"),
            configured_MaxIterations=controls.get("configured_MaxIterations"),
            Native_optimizer_calls=0,Actual_plan_repair_calls=0,Original_Fresh_logical_slots_unchanged=True,
            progress_only_not_global_AC_certificate=True,error=error)
        path=self.output/("DSTATCOM_"+self.prefix+"_PROGRESS.json")
        temporary=path.with_name(path.name+"."+str(os.getpid())+".tmp")
        temporary.write_text(canonical(value)+"\n",encoding="utf8")
        os.replace(temporary,path)

    def persist(self, *, error=None, bodies_unchanged=True):
        self.output.mkdir(parents=True, exist_ok=True)
        rows_path = self.output / ("DSTATCOM_"+self.prefix+"_SLOTS.json")
        with rows_path.open("x", encoding="utf8", newline="\n") as stream:
            stream.write(canonical(self.rows) + "\n")
        csv_path = self.output / ("DSTATCOM_"+self.prefix+"_SLOTS.csv")
        with csv_path.open("x", encoding="utf-8-sig", newline="") as stream:
            fields = list(self.rows[0]) if self.rows else ["slot", "day", "arm"]
            writer = csv.DictWriter(stream, fields); writer.writeheader()
            for row in self.rows:
                writer.writerow({k:canonical(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})
        events_path = self.output / "DSTATCOM_PHYSICAL_SOLVE_EVENTS.json"
        with events_path.open("x", encoding="utf8", newline="\n") as stream:
            stream.write(canonical(self.physical_solve_events) + "\n")
        sources_unchanged = all(record(row["path"]) == row for row in self.sources)
        connection_unchanged = record(self.scenario["connection_manifest"]["path"]) == self.scenario["connection_manifest"]
        all_controls = [c for row in self.rows for c in
            [row["original_initial_solve_controls"],*row["feedback_solve_controls"],row["settled_original_controls"]]]
        settings_SHA = {c["regulator_settings_SHA"] for c in all_controls}
        complete = len(self.rows)==96 and error is None and bodies_unchanged and sources_unchanged and connection_unchanged
        hardware_pass = complete and len(settings_SHA)==1 and all(row["PASS"] for row in self.rows)
        self.result = dict(schema=VERSION, PASS=bool(hardware_pass), hardware_and_controller_PASS=bool(hardware_pass),
            status="COMPLETE" if complete else "NOT_RUN" if not self.rows and error is None else "INCOMPLETE_OR_FAILED",
            day=self.day, arm=self.arm, namespace=self.namespace, execution_source_SHA=self.source_SHA, scenario_SHA=self.scenario["scenario_SHA"],
            Actual_model_SHA=digest(dict(original_source_receipts=self.sources,scenario_SHA=self.scenario["scenario_SHA"])),
            frozen_scenario=self.scenario, installations=self.installations,
            source_initial_controls=self.source_initial_controls,
            new_engine_from_original_Source_Initial_State=True,
            Planning_Q_Tap_or_controller_state_transfer_to_Actual=False,
            independent_controller_state_per_namespace=True,
            logical_Fresh_slots=len(self.rows),
            original_initial_physical_solve_count=sum(e["kind"]=="ORIGINAL_SLOT_INITIAL_SOLVE" for e in self.physical_solve_events),
            additional_feedback_solve_count=sum(e["kind"]=="ADDITIONAL_DSTATCOM_FEEDBACK_SOLVE" for e in self.physical_solve_events),
            total_physical_SolveSnap_count=len(self.physical_solve_events),
            completed_physical_SolveSnap_count=sum(e["completed"] for e in self.physical_solve_events),
            hardware_or_controller_failed_slots=[r["slot"] for r in self.rows if not r["PASS"]],
            frozen_Actual_trajectory_SHA=self.trajectory_SHA,
            regulator_settings_SHA=next(iter(settings_SHA)) if len(settings_SHA)==1 else None,
            all_seven_RegControls_enabled=all(all(c["regulator_enabled"]) for c in all_controls) if all_controls else None,
            all_four_fixed_capacitors_on=all(c["capacitor_states"]==[1,1,1,1] for c in all_controls) if all_controls else None,
            control_actions_done_physical_solves=sum(e["controls"] is not None
                and e["controls"]["control_actions_done"] for e in self.physical_solve_events),
            max_observed_ControlIterations=max((c["ControlIterations"] for c in all_controls),default=None),
            max_observed_Solution_Iterations_total=max((c["Solution_Iterations_total"] for c in all_controls),default=None),
            max_observed_Solution_MostIterationsDone_per_control_pass=max((c["Solution_MostIterationsDone_per_control_pass"] for c in all_controls),default=None),
            configured_MaxControlIterations=sorted({c["configured_MaxControlIterations"] for c in all_controls}),
            configured_MaxIterations=sorted({c["configured_MaxIterations"] for c in all_controls}),
            Original_Fresh_and_96_slot_body_unchanged=bodies_unchanged,
            Original_Source_SHA_before_after_equal=sources_unchanged, connection_manifest_unchanged=connection_unchanged,
            original_input_setpoints_unchanged=all(r["original_input_setpoints_unchanged"] for r in self.rows) if self.rows else None,
            original_Planning_voltage_limits_pu=[.95,1.05], Actual_voltage_limits_pu=[.95,1.05],
            DSTATCOM_MILP_variables=0, Actual_optimizer_calls=0, Actual_plan_repair_calls=0,
            original_tap_cap_setters_added=False, scope="ORIGINAL_FRESH_"+self.namespace+"_ONLY",
            independent_global_LB=None, independent_global_gap=None,
            SourceSHA_receipts=self.sources, slots_receipt=record(rows_path), csv_receipt=record(csv_path),
            physical_solve_events_receipt=record(events_path), error=error,
            PASS_scope="Added hardware/controller only; caller must join unchanged Original Fresh all-node/branch/service-transformer physical PASS",
            iteration_semantics="Iterations/TotalIterations are cumulative; MostIterationsDone is the per-control-pass maximum")
        path = self.output / ("DSTATCOM_"+self.prefix+"_PHYSICAL_AUDIT.json")
        with path.open("x", encoding="utf8", newline="\n") as stream:
            stream.write(canonical(self.result) + "\n")
        self.receipt = record(path)
        self.write_progress(status=self.result["status"], error=error)


@contextmanager
def scenario_scope(scenario, output, *, source_SHA, arm, day, namespace="ACTUAL"):
    require(_active.get() is None, "DSTATCOM_NESTED_PHYSICAL_SCENARIO_FORBIDDEN")
    audit = PhysicalScenario(scenario, output, source_SHA=source_SHA, arm=arm, day=day, namespace=namespace)
    if namespace == "ACTUAL":
        from .authority import authorize_actual
        authorize_actual(arm,day,source_SHA,audit.scenario["scenario_SHA"])
    else:
        from .authority import authorize_physical
        authorize_physical(arm,day,source_SHA,audit.scenario["scenario_SHA"],namespace)
    authority, operations, backend, mapping, replay, controller = _bindings()
    original_compile, original_voltage = authority.compile_verified, backend._voltage_vector
    body, fresh_body = backend.run_fresh_opendss.__code__, operations.fresh.__code__
    paths = {Path(inspect.getfile(function)) for function in
        (original_compile, original_voltage, backend.run_fresh_opendss, mapping.apply_trajectory_slot,
         operations.fresh, replay.fresh, authority.assert_inventory, authority.regulator_parameters,
         install, controller, ControllerSettings)}
    paths.add(Path(__file__))
    audit.sources = [record(path) for path in sorted(paths)]
    def compile_actual():
        result = original_compile()
        identity = _physical_frame(body, audit.namespace)
        if identity is not None:
            audit.install_actual(result[0], identity, authority, controller)
        return result
    def voltage_actual(engine, nodes):
        identity = _physical_frame(body, audit.namespace)
        if identity is not None:
            audit.settle_actual(engine, identity, authority)
        return original_voltage(engine, nodes)
    token = _active.set(audit)
    error = None
    try:
        with patch.object(authority, "compile_verified", compile_actual), patch.object(backend, "_voltage_vector", voltage_actual):
            yield audit
    except BaseException as exc:
        error = type(exc).__name__ + ":" + str(exc)
        raise
    finally:
        _active.reset(token)
        audit.persist(error=error, bodies_unchanged=(backend.run_fresh_opendss.__code__ is body
            and operations.fresh.__code__ is fresh_body))
