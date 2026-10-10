"""Observe original Actual Fresh controls without changing any electrical input."""
from contextlib import contextmanager
from pathlib import Path
import csv
import hashlib
import inspect
import json
import sys
from unittest.mock import patch

VERSION = "V42_VMAX1048_ACTUAL_CONTROL_OBSERVER_V1"


def _receipt(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), sha256=sha, bytes=path.stat().st_size)


def _actual_frame(body):
    frame = sys._getframe(1)
    try:
        while frame is not None:
            if frame.f_code is body:
                trajectory = frame.f_locals.get("trajectory")
                if getattr(trajectory, "namespace", None) == "ACTUAL":
                    return dict(day=trajectory.day, arm=trajectory.case, slot=frame.f_locals.get("slot"))
                return None
            frame = frame.f_back
    finally:
        del frame
    return None


class ControlObserver:
    def __init__(self, output, source_SHA=None):
        self.output = Path(output).resolve()
        self.source_SHA = source_SHA
        self.rows, self.sources, self.receipt = [], [], None
        self.identity = None

    def observe(self, engine, identity, authority):
        source = authority.source()
        inventory = source["inventory"](engine)
        authority.assert_inventory(inventory)
        done, converged = bool(engine.Solution.ControlActionsDone()), bool(engine.Solution.Converged())
        if not done or not converged:
            raise ValueError("ORIGINAL_ACTUAL_FRESH_CONTROLS_NOT_COMPLETE")
        case_identity = (identity["day"], identity["arm"])
        if self.identity is None:
            self.identity = case_identity
        if self.identity != case_identity or identity["slot"] != len(self.rows):
            raise ValueError("ONE_SEQUENTIAL_ORIGINAL_ACTUAL_TRAJECTORY_REQUIRED")
        taps, caps = source["native_state"](engine)
        if len(inventory["regulators"]) != 7 or len(taps) != 7 or caps != [1,1,1,1]:
            raise ValueError("ORIGINAL_SEVEN_CONTROLS_FIXED_CAPACITORS_REQUIRED")
        settings = authority.regulator_parameters(inventory)
        expected = source["expected"]
        previous = self.rows[-1]["taps"] if self.rows else [r["initial_tap"] for r in expected["regulators"]]
        self.rows.append(dict(slot=identity["slot"], day=identity["day"], arm=identity["arm"],
            seven_RegControls_enabled=all(r["enabled"] for r in inventory["regulators"]),
            regulator_names=[r["name"] for r in inventory["regulators"]],
            regulator_enabled=[bool(r["enabled"]) for r in inventory["regulators"]],
            regulator_settings_SHA=authority.digest(settings),
            individual_regulator_settings_SHA={r["name"]:authority.digest(r) for r in settings["regulators"]},
            taps=list(map(float,taps)), previous_taps=list(map(float,previous)),
            tap_changes=[float(a-b) for a,b in zip(taps,previous)],
            tap_changed=[abs(a-b)>1e-12 for a,b in zip(taps,previous)],
            capacitor_states=list(map(int,caps)), CapControl_count=inventory["CapControl_count"],
            control_actions_done=done, converged=converged,
            control_iterations=int(engine.Solution.ControlIterations()),
            Solution_Iterations_total=int(engine.Solution.Iterations()),
            Solution_TotalIterations=int(engine.Solution.TotalIterations()),
            Solution_MostIterationsDone_per_control_pass=int(engine.Solution.MostIterationsDone()),
            configured_MaxControlIterations=int(engine.Solution.MaxControlIterations()),
            configured_MaxIterations=int(engine.Solution.MaxIterations()),
            control_mode=int(engine.Solution.ControlMode()), solution_mode=inventory["solution_mode"],
            source_parameters_equal_to_original=True, Planning_tap_cap_replay=False,
            previous_taps_basis="PREVIOUS_SETTLED_ACTUAL" if self.rows else "ORIGINAL_FRESH_SOURCE_INITIAL"))

    def persist(self, *, error=None, bodies_unchanged=True):
        if not self.output.exists():
            self.output.mkdir(parents=True)
        settings = {r["regulator_settings_SHA"] for r in self.rows}
        complete = (len(self.rows)==96 and error is None and bodies_unchanged
            and len(settings)==1 and all(r["converged"] and r["control_actions_done"] and r["seven_RegControls_enabled"]
                and r["capacitor_states"]==[1,1,1,1] and r["CapControl_count"]==0 for r in self.rows))
        slots_path = self.output / "ACTUAL_FRESH_CONTROL_SLOTS.json"
        with slots_path.open("x",encoding="utf8",newline="\n") as stream:
            stream.write(json.dumps(self.rows,ensure_ascii=False,indent=2)+"\n")
        csv_path = self.output / "ACTUAL_FRESH_CONTROL_SLOTS.csv"
        fields = list(self.rows[0]) if self.rows else ["slot","day","arm"]
        with csv_path.open("x",encoding="utf-8-sig",newline="") as stream:
            writer=csv.DictWriter(stream,fields);writer.writeheader()
            for row in self.rows:
                writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})
        sources_unchanged=all(_receipt(row["path"])==row for row in self.sources)
        result=dict(schema=VERSION, PASS=complete and sources_unchanged,
            status="COMPLETE" if complete and sources_unchanged else "NOT_RUN" if not self.rows and error is None else "INCOMPLETE_OR_FAILED",
            observer_only=True, execution_source_SHA=self.source_SHA, slots=len(self.rows),
            control_actions_done_slots=sum(r["control_actions_done"] for r in self.rows),
            converged_slots=sum(r["converged"] for r in self.rows),
            max_observed_ControlIterations=max((r["control_iterations"] for r in self.rows),default=None),
            max_observed_Solution_Iterations_total=max((r["Solution_Iterations_total"] for r in self.rows),default=None),
            max_observed_Solution_MostIterationsDone_per_control_pass=max((r["Solution_MostIterationsDone_per_control_pass"] for r in self.rows),default=None),
            configured_MaxControlIterations=sorted({r["configured_MaxControlIterations"] for r in self.rows}),
            configured_MaxIterations=sorted({r["configured_MaxIterations"] for r in self.rows}),
            regulator_settings_SHA=next(iter(settings)) if len(settings)==1 else None,
            original_Fresh_and_96_slot_body_unchanged=bodies_unchanged, original_source_SHA_before_after_equal=sources_unchanged,
            Actual_voltage_limits_pu=[.95,1.05], control_settings_changed=False, tap_or_cap_setters_added=False,
            Actual_optimizer_calls=0, Actual_PQ_repair_calls=0,
            SourceSHA_receipts=self.sources, slots_receipt=_receipt(slots_path), csv_receipt=_receipt(csv_path), error=error,
            iteration_semantics="Solution.Iterations/TotalIterations include control passes; MostIterationsDone is per-pass maximum")
        path=self.output/"ACTUAL_FRESH_CONTROL_OBSERVER.json"
        with path.open("x",encoding="utf8",newline="\n") as stream:
            stream.write(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
        self.receipt=_receipt(path)


@contextmanager
def observer_context(outputpath, *, source_SHA=None):
    """Wrap a B2 run; capture only its original backend ACTUAL Fresh trajectory.

    No original output is edited. The independent observer directory must not
    contain a previous observer result. A planning failure records NOT_RUN.
    """
    from v42_regcontrol import authority
    from v42_may_campaign_native90 import operations
    authority.source()
    from dayahead.v28r2 import opendss_backend as backend, opendss_mapping as mapping
    from v42_pr134_b1 import replay
    observer=ControlObserver(outputpath,source_SHA)
    if (observer.output/"ACTUAL_FRESH_CONTROL_OBSERVER.json").exists():
        raise PermissionError("ORIGINAL_ACTUAL_CONTROL_OBSERVATION_OVERWRITE_FORBIDDEN")
    body, fresh_body=backend.run_fresh_opendss.__code__,operations.fresh.__code__
    original_voltage=backend._voltage_vector
    paths={Path(inspect.getfile(function)) for function in
        (backend.run_fresh_opendss, original_voltage, mapping.apply_trajectory_slot, operations.fresh,
         replay.fresh, authority.assert_inventory, authority.regulator_parameters)}
    paths.add(Path(__file__))
    observer.sources=[_receipt(path) for path in sorted(paths)]
    def voltage_observed(engine,nodes):
        values=original_voltage(engine,nodes)
        identity=_actual_frame(body)
        if identity is not None:
            observer.observe(engine,identity,authority)
        return values
    error=None
    try:
        with patch.object(backend,"_voltage_vector",voltage_observed):
            yield observer
    except BaseException as exc:
        error=type(exc).__name__+":"+str(exc)
        raise
    finally:
        observer.persist(error=error,bodies_unchanged=(backend.run_fresh_opendss.__code__ is body and operations.fresh.__code__ is fresh_body))
