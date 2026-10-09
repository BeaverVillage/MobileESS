"""Stage-isolated execution of the original measured Native90 budget.

This module has no solver import. The source registry must admit the context
before resolving DateBudget or creating any output. The original optimize body
is reused, including failed-call Runtime accounting and unknown quarantine.
"""
from contextlib import contextmanager
import json
import math
from pathlib import Path
from time import perf_counter

from .contracts import canonical, digest, require
from .policy import STAGES

COMPONENTS = frozenset(("P1", "ORIGINAL_P1", "PHASE_I", "INTEGER_CONTROL",
    "NODE_LP", "LOCAL_PRICING", "FEASIBILITY_LP", "FEASIBILITY_MIP", "LP_DUAL",
    "UB", "PRICING", "RMP"))


class SourceStageLedger:
    """Independent 5400-second ledger; restart reads rather than resets it."""

    def __init__(self, context, path=None, *, clock=perf_counter, progress=None):
        context.source_registry.admit(context, "NATIVE_LEDGER")
        context.verify_identity()
        self.context, self.registry = context, context.source_registry
        self.stage = context.request.stage
        require(self.stage in STAGES[:4], "NATIVE_LEDGER_STAGE_REQUIRED")
        self.output = Path(context.output).resolve()
        self.path = self._path(path or self.output / "NATIVE_RUNTIME_LEDGER.json")
        self.identity_path = self.path.with_name(self.path.stem + "_IDENTITY.json")
        request = context.request
        self.identity = dict(schema="B3_SOURCE_NATIVE_LEDGER_IDENTITY_V1",
            run_id=context.run_id, day=request.authority.day, stage=self.stage,
            authority_sha=request.authority.sha, input_sha=request.authority.input_sha,
            request_sha=request.request_sha, fixed_input_sha=request.fixed_input_sha,
            source_sha=request.authority.source_sha, native_limit_seconds=5400,
            wall_limit_seconds=None, Threads=1, P2_calls=0,
            budget_basis="MEASURED_NATIVE_RUNTIME_ONLY")
        with self.registry.execution_scope(context):
            source_class = self.registry.callable("v42_may_campaign_native90/budget.py", "DateBudget")
            rebound_init = self.registry.rebind("v42_may_campaign_native90.budget", "DateBudget.__init__",
                globals={"d_path": self._path})
            rebound_persist = self.registry.rebind("v42_may_campaign_native90.budget", "DateBudget.persist",
                globals={"atomic": self._atomic})
            rebound_optimize = self.registry.rebind("v42_may_campaign_native90.budget", "DateBudget.native_optimize",
                globals={"d_path": self._path, "native_scope": self._native_scope, "guard": self._guard})
        budget_type = type("B3SourceDateBudget", (source_class,), dict(
            __init__=rebound_init, persist=rebound_persist, native_optimize=rebound_optimize))
        exists, sealed = self.path.exists(), self.identity_path.exists()
        require(exists == sealed, "PARTIAL_NATIVE_LEDGER_IDENTITY_QUARANTINE")
        if exists:
            document = json.loads(self.path.read_text(encoding="utf-8-sig"))
            identity = json.loads(self.identity_path.read_text(encoding="utf-8-sig"))
            require(identity == self.identity, "NATIVE_LEDGER_RESTART_IDENTITY_DRIFT")
            self._verify_document(document)
            budget = budget_type.__new__(budget_type)
            budget.path, budget.clock = self.path, clock
            budget.started = document["inclusive_T0"]
            budget.wall_limit, budget.native_limit, budget.final_reserve = None, 5400., 0.
            budget.calls = document["calls"]
            budget.costs = document["costs"]
            budget.admission_failures = document["admission_failures"]
            budget.inflight, budget.latest = document["inflight"], {}
            budget.progress = progress or (lambda value: None)
            budget.native_used = document["measured_Native_Runtime"]
            self.budget = budget
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.identity_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical(self.identity) + "\n")
            self.budget = budget_type(self.path, clock=clock, native_limit=5400.,
                wall_limit=None, final_reserve=0., progress=progress)

    def _path(self, path):
        resolved = Path(path).resolve()
        require(resolved.is_relative_to(self.output), "NATIVE_LEDGER_OUTPUT_ESCAPE")
        return resolved

    def _atomic(self, path, document):
        self.registry.admit(self.context, "NATIVE_LEDGER")
        destination = self._path(path)
        temporary = destination.with_name(destination.name + ".b3-tmp")
        temporary.write_text(canonical(document) + "\n", encoding="utf-8")
        temporary.replace(destination)

    def _verify_document(self, document):
        require(document.get("Native_ceiling_seconds") == 5400
            and document.get("wall_ceiling_seconds") is None
            and document.get("P2_calls") == 0
            and document.get("budget_basis") == "MEASURED_NATIVE_RUNTIME_ONLY"
            and document.get("historical_costs_reused") is False,
            "NATIVE_LEDGER_POLICY_DRIFT")
        require(all(isinstance(document.get(k), list) for k in
            ("calls", "costs", "admission_failures")), "NATIVE_LEDGER_SOURCE_ROWS_REQUIRED")
        measured = document.get("measured_Native_Runtime")
        require(type(measured) in (int, float) and math.isfinite(measured) and measured >= 0,
            "NATIVE_LEDGER_MEASURED_RUNTIME_REQUIRED")
        total, unknown_seen = 0., False
        for row in document["calls"]:
            require(row.get("component") in COMPONENTS and row.get("entered_native") is True,
                "NATIVE_LEDGER_CALL_ADMISSION_DRIFT")
            require(not unknown_seen and total < 5400
                and row.get("effective_TimeLimit") == max(0., 5400 - total),
                "NATIVE_LEDGER_REMAINING_LIMIT_OR_QUARANTINE_DRIFT")
            runtime = row.get("Native_Runtime")
            if row.get("runtime_unavailable"):
                require(runtime is None, "NATIVE_UNKNOWN_RUNTIME_ESTIMATE_FORBIDDEN")
                unknown_seen = True
            else:
                require(type(runtime) in (int, float) and math.isfinite(runtime) and runtime >= 0,
                    "NATIVE_LEDGER_INVALID_RUNTIME")
                total += runtime
        require(math.isclose(total, measured, rel_tol=0, abs_tol=1e-9),
            "NATIVE_LEDGER_CUMULATIVE_RUNTIME_DRIFT")

    @contextmanager
    def _native_scope(self, model, component="P1", track=None):
        require(component in COMPONENTS, "B3_P2_NATIVE_FORBIDDEN")
        allowed = str(track or "").startswith("A") if self.stage.startswith("A") else (
            str(track or "").startswith("M") or track in {"UB", "LB", "PRICING", "RMP"})
        require(allowed, "NATIVE_STAGE_TRACK_DRIFT")
        self.registry.admit(self.context, "NATIVE_OPTIMIZE")
        with self.registry.execution_scope(self.context), self.registry.native_scope(model, component, track):
            yield

    def _guard(self, model):
        self.context.verify_identity()
        self.registry.admit(self.context, "NATIVE_OPTIMIZE")
        require(type(model.Params.Threads) is int and model.Params.Threads == 1,
            "B3_NATIVE_THREADS_ONE_REQUIRED")
        require(getattr(model, "_v42_a_stage_day", self.context.request.authority.day)
            == self.context.request.authority.day, "B3_NATIVE_MODEL_DATE_DRIFT")

    def native_optimize(self, model, callback=None, *, component="P1", track=None,
                        label="", requested_seconds=None):
        self.registry.admit(self.context, "NATIVE_OPTIMIZE")
        require(component in COMPONENTS, "B3_P2_NATIVE_FORBIDDEN")
        require(self.budget.inflight is None, "INTERRUPTED_NATIVE_CALL_QUARANTINE")
        return self.budget.native_optimize(model, callback, component=component,
            track=track or self.stage[0], label=label, requested_seconds=requested_seconds)

    def optimize(self, model, *, track, label, requested_seconds, callback=None):
        return self.native_optimize(model, callback, track=track, label=label,
            requested_seconds=requested_seconds)

    def receipt(self):
        document = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self._verify_document(document)
        return dict(self.identity, evidence_kind=self.registry.evidence_kind,
            measured_native_runtime=self.budget.used(), remaining_seconds=self.budget.remaining(),
            native_call_count=len(self.budget.calls), calls=document["calls"],
            non_native_costs=document["costs"], admission_failures=document["admission_failures"],
            quarantined=self.budget.inflight is not None or any(
                row.get("runtime_unavailable") for row in self.budget.calls),
            source_ledger_sha=digest(document), identity_sha=digest(self.identity),
            source_api="v42_may_campaign_native90.budget.DateBudget.native_optimize")

    def sealed_receipt(self):
        return canonical(self.receipt())

    def __getattr__(self, name):
        # Preserve the original algorithm's budget interface, including cost,
        # calls, native_used, remaining, started and final_reserve.
        return getattr(self.budget, name)
