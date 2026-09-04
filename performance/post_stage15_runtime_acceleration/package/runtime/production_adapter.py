"""Fail-closed Stage-2 production binding for the R26 controller.

This module binds the generic R26 orchestration to project-specific, real
scientific components without changing the frozen R25T source or selecting fake
physics. A project bridge must expose the real model before ``optimize()``, the
complete route/work variable inventory, and a checksum-addressed RoutePlan
binding. Fresh OpenDSS and physical PRE->POST commit remain controller gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib
import inspect
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Tuple

from .audit import AuditLogger
from .controller import CausalFrame, R26FastController
from .dispatch import (
    DispatchResult,
    ModelStructureAudit,
    audit_model_structure,
    fix_and_relax_discrete_variables,
)
from .event_engine import EventConfig, EventEngine
from .planner_manager import AsyncPlannerManager, AtomicRoutePlanStore
from .route_plan import RoutePlan


class Stage2BindingError(RuntimeError):
    """Raised when a production authority or conditioning gate fails."""


SLOW_DECISION_FAMILIES = frozenset(
    {
        "MOBILITY_STAY",
        "MOBILITY_MOVE",
        "MOBILITY_OCCUPANCY",
        "WORK_START",
        "WORK_DEFER",
        "WORK_DESTINATION",
        "WORK_RACK",
    }
)

ALLOWED_REMAINING_INTEGER_FAMILIES = frozenset(
    {
        "FAST_DISPATCH_MODE",
        "FAST_DISPATCH_AUXILIARY",
        "OTHER_EXPLICITLY_REVIEWED_FAST_INTEGER",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _resolve_under(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise Stage2BindingError(f"source-lock path must be relative: {relative!r}")
    root = root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise Stage2BindingError(f"source-lock path escapes root: {relative!r}") from exc
    return resolved


@dataclass(frozen=True)
class SourceLockEntry:
    path: str
    sha256: str
    role: str
    required: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SourceLockEntry":
        entry = cls(
            path=str(raw["path"]),
            sha256=str(raw["sha256"]).lower(),
            role=str(raw.get("role", "UNSPECIFIED")),
            required=bool(raw.get("required", True)),
        )
        if not _is_sha256(entry.sha256):
            raise Stage2BindingError(f"invalid SHA-256 for {entry.path}")
        return entry


@dataclass(frozen=True)
class SourceLockManifest:
    schema_version: str
    parent_commit_sha: str
    entries: Tuple[SourceLockEntry, ...]
    manifest_sha256: str

    @classmethod
    def from_file(cls, path: Path) -> "SourceLockManifest":
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
        if raw.get("schema_version") != "r26.stage2_source_lock.v1":
            raise Stage2BindingError("unsupported Stage-2 source-lock schema")
        entries = tuple(SourceLockEntry.from_mapping(item) for item in raw.get("entries", ()))
        if not entries:
            raise Stage2BindingError("source-lock manifest has no entries")
        paths = [entry.path for entry in entries]
        if len(paths) != len(set(paths)):
            raise Stage2BindingError("source-lock manifest contains duplicate paths")
        parent = str(raw.get("parent_commit_sha", "")).lower()
        if len(parent) != 40 or any(ch not in "0123456789abcdef" for ch in parent):
            raise Stage2BindingError("parent_commit_sha must be a full hexadecimal commit SHA")
        return cls(
            schema_version="r26.stage2_source_lock.v1",
            parent_commit_sha=parent,
            entries=entries,
            manifest_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        )

    @property
    def authority_id(self) -> str:
        return f"{self.parent_commit_sha}:{self.manifest_sha256}"

    def verify(self, root: Path) -> Tuple[Mapping[str, Any], ...]:
        records = []
        failures = []
        for entry in self.entries:
            target = _resolve_under(root, entry.path)
            exists = target.is_file()
            actual = _sha256(target) if exists else None
            passed = bool(exists and actual == entry.sha256)
            record = {
                "path": entry.path,
                "role": entry.role,
                "required": entry.required,
                "exists": exists,
                "expected_sha256": entry.sha256,
                "actual_sha256": actual,
                "pass": passed,
            }
            records.append(record)
            if entry.required and not passed:
                failures.append(entry.path)
        if failures:
            raise Stage2BindingError(
                "Stage-2 source-lock verification failed: " + ", ".join(failures)
            )
        return tuple(records)


@dataclass(frozen=True)
class PlanBindingEnvelope:
    schema_version: str
    plan_checksum: str
    source_state_hash: str
    valid_from_issue: int
    source_lock_authority_id: str
    named_assignments: Mapping[str, float]
    assignment_families: Mapping[str, str]
    expected_slow_variable_names: Tuple[str, ...]
    future_actual_used: bool
    binding_sha256: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> "PlanBindingEnvelope":
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
        if raw.get("schema_version") != "r26.plan_binding.v1":
            raise Stage2BindingError("unsupported plan-binding schema")
        assignments = {str(k): float(v) for k, v in raw.get("named_assignments", {}).items()}
        if any(not math.isfinite(value) for value in assignments.values()):
            raise Stage2BindingError("plan binding contains non-finite assignments")
        envelope = cls(
            schema_version="r26.plan_binding.v1",
            plan_checksum=str(raw.get("plan_checksum", "")).lower(),
            source_state_hash=str(raw.get("source_state_hash", "")),
            valid_from_issue=int(raw.get("valid_from_issue", -1)),
            source_lock_authority_id=str(raw.get("source_lock_authority_id", "")),
            named_assignments=assignments,
            assignment_families={
                str(k): str(v) for k, v in raw.get("assignment_families", {}).items()
            },
            expected_slow_variable_names=tuple(
                str(name) for name in raw.get("expected_slow_variable_names", ())
            ),
            future_actual_used=bool(raw.get("future_actual_used", False)),
            binding_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            metadata=dict(raw.get("metadata", {})),
        )
        envelope.validate()
        return envelope

    def validate(self) -> None:
        if not _is_sha256(self.plan_checksum):
            raise Stage2BindingError("plan binding requires a hexadecimal RoutePlan checksum")
        if not self.source_state_hash or self.valid_from_issue < 0:
            raise Stage2BindingError("plan binding has an invalid PRE state or issue")
        if self.future_actual_used:
            raise Stage2BindingError("plan binding used future actual information")
        expected = self.expected_slow_variable_names
        if len(expected) != len(set(expected)):
            raise Stage2BindingError("duplicate expected slow-variable names")
        assignment_names = set(self.named_assignments)
        family_names = set(self.assignment_families)
        expected_names = set(expected)
        if assignment_names != family_names:
            raise Stage2BindingError("assignment-family coverage mismatch")
        if assignment_names != expected_names:
            missing = sorted(expected_names - assignment_names)
            extra = sorted(assignment_names - expected_names)
            raise Stage2BindingError(
                f"slow-variable binding incomplete: missing={missing[:20]} extra={extra[:20]}"
            )
        invalid = sorted(set(self.assignment_families.values()) - SLOW_DECISION_FAMILIES)
        if invalid:
            raise Stage2BindingError(f"unsupported slow-decision families: {invalid}")


class JsonPlanBindingStore:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def load(self, plan_checksum: str) -> PlanBindingEnvelope:
        path = self.directory / f"{plan_checksum}.json"
        if not path.is_file():
            raise Stage2BindingError(f"plan binding is missing: {path}")
        binding = PlanBindingEnvelope.from_file(path)
        if binding.plan_checksum != plan_checksum:
            raise Stage2BindingError("plan-binding filename/checksum mismatch")
        return binding


@dataclass(frozen=True)
class FixedPlanObservation:
    pre_state_hash: str
    cutoff_timestamp_utc: str
    plan_checksum: str
    objective: float
    h0_action: Mapping[str, float]
    continuous_state: Mapping[str, float]
    numerical_residuals: Mapping[str, float]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FixedPlanObservation":
        def finite_map(name: str) -> Mapping[str, float]:
            values = {str(k): float(v) for k, v in raw.get(name, {}).items()}
            if any(not math.isfinite(value) for value in values.values()):
                raise Stage2BindingError(f"{name} contains a non-finite value")
            return values

        objective = float(raw["objective"])
        if not math.isfinite(objective):
            raise Stage2BindingError("objective is non-finite")
        result = cls(
            pre_state_hash=str(raw["pre_state_hash"]),
            cutoff_timestamp_utc=str(raw["cutoff_timestamp_utc"]),
            plan_checksum=str(raw["plan_checksum"]).lower(),
            objective=objective,
            h0_action=finite_map("h0_action"),
            continuous_state=finite_map("continuous_state"),
            numerical_residuals=finite_map("numerical_residuals"),
        )
        if not _is_sha256(result.plan_checksum):
            raise Stage2BindingError("equivalence observation has invalid plan checksum")
        return result


def compare_fixed_plan_observations(
    reference: FixedPlanObservation,
    candidate: FixedPlanObservation,
    *,
    absolute_tolerance: float = 1e-7,
    relative_tolerance: float = 1e-8,
    residual_tolerance: float = 1e-6,
) -> Mapping[str, Any]:
    if min(absolute_tolerance, relative_tolerance, residual_tolerance) < 0:
        raise ValueError("equivalence tolerances must be non-negative")

    def scalar(name: str, a: float, b: float, base_tol: float) -> Mapping[str, Any]:
        allowed = max(base_tol, relative_tolerance * max(1.0, abs(a), abs(b)))
        error = abs(a - b)
        return {
            "name": name,
            "reference": a,
            "candidate": b,
            "absolute_error": error,
            "allowed_error": allowed,
            "pass": error <= allowed,
        }

    identity = {
        "pre_state_hash": reference.pre_state_hash == candidate.pre_state_hash,
        "cutoff_timestamp_utc": reference.cutoff_timestamp_utc
        == candidate.cutoff_timestamp_utc,
        "plan_checksum": reference.plan_checksum == candidate.plan_checksum,
    }
    objective = scalar(
        "objective", reference.objective, candidate.objective, absolute_tolerance
    )
    groups = {}
    for name, a, b, tolerance in (
        ("h0_action", reference.h0_action, candidate.h0_action, absolute_tolerance),
        (
            "continuous_state",
            reference.continuous_state,
            candidate.continuous_state,
            absolute_tolerance,
        ),
        (
            "numerical_residuals",
            reference.numerical_residuals,
            candidate.numerical_residuals,
            residual_tolerance,
        ),
    ):
        keys_match = set(a) == set(b)
        comparisons = [scalar(key, a[key], b[key], tolerance) for key in sorted(set(a) & set(b))]
        groups[name] = {
            "keys_match": keys_match,
            "missing_in_candidate": sorted(set(a) - set(b)),
            "extra_in_candidate": sorted(set(b) - set(a)),
            "comparisons": comparisons,
            "pass": keys_match and all(item["pass"] for item in comparisons),
        }
    passed = all(identity.values()) and objective["pass"] and all(
        group["pass"] for group in groups.values()
    )
    return {
        "schema_version": "r26.stage2_fixed_plan_equivalence.v1",
        "status": "PASS" if passed else "FAIL_CLOSED",
        "pass": passed,
        "identity_fields": identity,
        "objective": objective,
        "groups": groups,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "residual_tolerance": residual_tolerance,
        "same_fixed_discrete_plan_required": True,
        "r25t_global_certificate_claimed": False,
    }


@dataclass(frozen=True)
class ProductionModelBundle:
    model: Any
    plan_checksum: str
    pre_state_hash: str
    source_lock_authority_id: str
    future_actual_used: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ProductionScienceBridge(Protocol):
    def build_conditioned_model(
        self,
        *,
        frame: CausalFrame,
        pre_state: Any,
        route_plan: RoutePlan,
        route_steps: Mapping[str, Any],
        work_assignments: Sequence[Any],
        binding: PlanBindingEnvelope,
        output: Path,
    ) -> ProductionModelBundle:
        """Build the real model before optimize; do not solve here."""

    def slow_variable_inventory(self, model: Any) -> Mapping[str, str]:
        """Return every route/work variable and reviewed semantic family."""

    def classify_remaining_integer(self, variable_name: str) -> str:
        """Classify every residual integer variable."""

    def extract_result(
        self,
        *,
        model: Any,
        frame: CausalFrame,
        pre_state: Any,
        structure: ModelStructureAudit,
        bundle: ProductionModelBundle,
        output: Path,
    ) -> DispatchResult:
        """Extract h0 result without OpenDSS or physical commit."""


class ProductionDispatchBackend:
    def __init__(
        self,
        *,
        plan_store: AtomicRoutePlanStore,
        binding_store: JsonPlanBindingStore,
        source_root: Path,
        source_lock: SourceLockManifest,
        bridge: ProductionScienceBridge,
        output: Path,
        require_quadratic_constraints: bool = True,
        require_explicit_causal_audit: bool = True,
        audit: Optional[AuditLogger] = None,
    ) -> None:
        self.plan_store = plan_store
        self.binding_store = binding_store
        self.source_root = Path(source_root)
        self.source_lock = source_lock
        self.bridge = bridge
        self.output = Path(output)
        self.require_quadratic_constraints = require_quadratic_constraints
        self.require_explicit_causal_audit = require_explicit_causal_audit
        self.audit = audit or AuditLogger(self.output / "R26_STAGE2_ADAPTER_AUDIT.jsonl")

    def _validate_frame(self, frame: CausalFrame) -> None:
        if not frame.cutoff_timestamp_utc or not frame.pre_state_hash:
            raise Stage2BindingError("causal frame lacks cutoff or PRE-state authority")
        future_used = frame.payload.get("future_actual_used")
        actual_through = frame.payload.get("actual_through_issue")
        if self.require_explicit_causal_audit:
            if future_used is not False:
                raise Stage2BindingError("future_actual_used=false audit is required")
            if actual_through is None:
                raise Stage2BindingError("actual_through_issue audit is required")
        if future_used is True:
            raise Stage2BindingError("causal frame reports future-actual access")
        if actual_through is not None and int(actual_through) > frame.issue:
            raise Stage2BindingError("actual information extends beyond current issue")

    def _active_plan(
        self,
        *,
        frame: CausalFrame,
        route_steps: Mapping[str, Any],
        work_assignments: Sequence[Any],
    ) -> RoutePlan:
        plan = self.plan_store.load()
        if plan is None:
            raise Stage2BindingError("no active RoutePlan")
        plan.validate()
        if plan.valid_from_issue != frame.issue:
            raise Stage2BindingError("RoutePlan issue mismatch")
        if plan.source_state_hash != frame.pre_state_hash:
            raise Stage2BindingError("RoutePlan PRE-state hash mismatch")
        if plan.first_steps() != dict(route_steps):
            raise Stage2BindingError("controller route-step view differs from RoutePlan")
        if tuple(plan.work_assignments) != tuple(work_assignments):
            raise Stage2BindingError("controller work assignments differ from RoutePlan")
        return plan

    def solve(
        self,
        *,
        frame: CausalFrame,
        pre_state: Any,
        route_steps: Mapping[str, Any],
        work_assignments: Sequence[Any],
    ) -> DispatchResult:
        self._validate_frame(frame)
        plan = self._active_plan(
            frame=frame, route_steps=route_steps, work_assignments=work_assignments
        )
        source_records = self.source_lock.verify(self.source_root)
        binding = self.binding_store.load(plan.checksum)
        if binding.source_state_hash != frame.pre_state_hash:
            raise Stage2BindingError("plan binding PRE-state hash mismatch")
        if binding.valid_from_issue != frame.issue:
            raise Stage2BindingError("plan binding issue mismatch")
        if binding.source_lock_authority_id != self.source_lock.authority_id:
            raise Stage2BindingError("plan binding source-lock mismatch")

        issue_output = self.output / f"issue_{frame.issue:06d}"
        issue_output.mkdir(parents=True, exist_ok=True)
        bundle = self.bridge.build_conditioned_model(
            frame=frame,
            pre_state=pre_state,
            route_plan=plan,
            route_steps=route_steps,
            work_assignments=work_assignments,
            binding=binding,
            output=issue_output,
        )
        if bundle.future_actual_used:
            raise Stage2BindingError("science bridge reports future-actual access")
        if bundle.plan_checksum != plan.checksum:
            raise Stage2BindingError("science bridge plan checksum mismatch")
        if bundle.pre_state_hash != frame.pre_state_hash:
            raise Stage2BindingError("science bridge PRE-state hash mismatch")
        if bundle.source_lock_authority_id != self.source_lock.authority_id:
            raise Stage2BindingError("science bridge source-lock mismatch")

        inventory = {
            str(name): str(family)
            for name, family in self.bridge.slow_variable_inventory(bundle.model).items()
        }
        invalid_families = sorted(set(inventory.values()) - SLOW_DECISION_FAMILIES)
        if invalid_families:
            raise Stage2BindingError(f"invalid slow-variable families: {invalid_families}")
        if set(inventory) != set(binding.named_assignments):
            missing = sorted(set(inventory) - set(binding.named_assignments))
            extra = sorted(set(binding.named_assignments) - set(inventory))
            raise Stage2BindingError(
                f"model/binding slow inventory mismatch: missing={missing[:20]} extra={extra[:20]}"
            )
        mismatch = sorted(
            name
            for name in inventory
            if inventory[name] != binding.assignment_families[name]
        )
        if mismatch:
            raise Stage2BindingError(
                "slow-variable family mismatch: " + ", ".join(mismatch[:20])
            )

        fix_and_relax_discrete_variables(bundle.model, binding.named_assignments)
        structure = audit_model_structure(bundle.model)
        if self.require_quadratic_constraints and structure.num_quadratic_constraints <= 0:
            raise Stage2BindingError("conditioned model lost AC-aware QCP rows")

        remaining_families = {}
        residual_slow = []
        unreviewed = []
        for name in structure.integer_var_names:
            family = str(self.bridge.classify_remaining_integer(name))
            remaining_families[name] = family
            if family in SLOW_DECISION_FAMILIES:
                residual_slow.append(name)
            elif family not in ALLOWED_REMAINING_INTEGER_FAMILIES:
                unreviewed.append(name)
        if residual_slow:
            raise Stage2BindingError(
                "route/work integers remain after conditioning: "
                + ", ".join(residual_slow[:20])
            )
        if unreviewed:
            raise Stage2BindingError(
                "unreviewed integer families remain: " + ", ".join(unreviewed[:20])
            )

        family_counts = {
            family: sum(1 for value in binding.assignment_families.values() if value == family)
            for family in sorted(set(binding.assignment_families.values()))
        }
        preopt_audit = {
            "schema_version": "r26.stage2_preopt_audit.v1",
            "issue": frame.issue,
            "cutoff_timestamp_utc": frame.cutoff_timestamp_utc,
            "pre_state_hash": frame.pre_state_hash,
            "plan_checksum": plan.checksum,
            "plan_binding_sha256": binding.binding_sha256,
            "source_lock_authority_id": self.source_lock.authority_id,
            "source_lock_records": source_records,
            "fixed_slow_variable_count": len(binding.named_assignments),
            "fixed_slow_variable_family_counts": family_counts,
            "model_structure": structure.as_record(),
            "remaining_integer_families": remaining_families,
            "continuous_claim_authorized": structure.num_integer_vars == 0,
            "formulation": structure.formulation,
            "future_actual_used": False,
            "bridge_metadata": dict(bundle.metadata),
            "r25t_global_certificate_claimed": False,
            "fresh_opendss_performed": False,
            "physical_commit_performed": False,
        }
        _write_json_atomic(issue_output / "R26_STAGE2_PREOPT_AUDIT.json", preopt_audit)
        self.audit.emit("R26_STAGE2_PREOPT_PASS", preopt_audit)

        bundle.model.optimize()
        result = self.bridge.extract_result(
            model=bundle.model,
            frame=frame,
            pre_state=pre_state,
            structure=structure,
            bundle=bundle,
            output=issue_output,
        )
        if result.structure.as_record() != structure.as_record():
            raise Stage2BindingError("result extractor misreported model structure")
        continuous = result.structure.num_integer_vars == 0
        if continuous != result.structure.formulation.startswith("CONTINUOUS_"):
            raise Stage2BindingError("false continuous/reduced formulation label")
        _write_json_atomic(
            issue_output / "R26_STAGE2_DISPATCH_RESULT_AUDIT.json",
            {
                "schema_version": "r26.stage2_dispatch_result_audit.v1",
                "issue": frame.issue,
                "feasible": result.feasible,
                "status": result.status,
                "objective": result.objective,
                "runtime_seconds": result.runtime_seconds,
                "numerical_gates_passed": result.numerical_gates_passed,
                "model_structure": result.structure.as_record(),
                "fresh_opendss_performed_by_adapter": False,
                "physical_commit_performed_by_adapter": False,
                "r25t_global_certificate_claimed": False,
            },
        )
        return result


def _load_symbol(specification: str) -> Callable[..., Any]:
    if ":" not in specification:
        raise Stage2BindingError("factory specification must use module:function")
    module_name, symbol_name = specification.split(":", 1)
    symbol = getattr(importlib.import_module(module_name), symbol_name)
    if not callable(symbol):
        raise Stage2BindingError(f"factory is not callable: {specification}")
    return symbol


def _invoke_factory(
    specification: str,
    *,
    config: Mapping[str, Any],
    output: Path,
    plans: AtomicRoutePlanStore,
) -> Any:
    factory = _load_symbol(specification)
    parameters = inspect.signature(factory).parameters
    kwargs: dict[str, Any] = {}
    if "config" in parameters:
        kwargs["config"] = config
    if "output" in parameters:
        kwargs["output"] = output
    if "plans" in parameters:
        kwargs["plans"] = plans
    if parameters and not kwargs:
        raise Stage2BindingError(
            f"factory {specification} must accept one or more of config/output/plans"
        )
    return factory(**kwargs)


def create_controller(*, config: Mapping[str, Any], output: Path) -> R26FastController:
    """Create an R26 controller from explicit real-production dependencies."""

    output = Path(output)
    production = dict(config.get("production_adapter", {}))
    required = {
        "source_root",
        "source_lock_manifest",
        "plan_binding_directory",
        "active_plan_path",
        "initial_route_plan_path",
        "input_provider_factory",
        "state_store_factory",
        "planner_factory",
        "opendss_verifier_factory",
        "science_bridge_factory",
    }
    missing = sorted(required - set(production))
    if missing:
        raise Stage2BindingError(f"production adapter config incomplete: {missing}")

    audit = AuditLogger(output / "R26_AUDIT.jsonl")
    plans = AtomicRoutePlanStore(Path(production["active_plan_path"]))
    if plans.load() is None:
        initial = RoutePlan.from_json(
            Path(production["initial_route_plan_path"]).read_text(encoding="utf-8")
        )
        plans.swap(
            initial,
            issue=initial.valid_from_issue,
            source_state_hash=initial.source_state_hash,
        )

    inputs = _invoke_factory(
        str(production["input_provider_factory"]), config=config, output=output, plans=plans
    )
    states = _invoke_factory(
        str(production["state_store_factory"]), config=config, output=output, plans=plans
    )
    planner_callable = _invoke_factory(
        str(production["planner_factory"]), config=config, output=output, plans=plans
    )
    opendss = _invoke_factory(
        str(production["opendss_verifier_factory"]),
        config=config,
        output=output,
        plans=plans,
    )
    bridge = _invoke_factory(
        str(production["science_bridge_factory"]), config=config, output=output, plans=plans
    )

    source_lock = SourceLockManifest.from_file(Path(production["source_lock_manifest"]))
    dispatch = ProductionDispatchBackend(
        plan_store=plans,
        binding_store=JsonPlanBindingStore(Path(production["plan_binding_directory"])),
        source_root=Path(production["source_root"]),
        source_lock=source_lock,
        bridge=bridge,
        output=output,
        require_quadratic_constraints=bool(
            production.get("require_quadratic_constraints", True)
        ),
        require_explicit_causal_audit=bool(
            production.get("require_explicit_causal_audit", True)
        ),
        audit=audit,
    )
    event_config = EventConfig.from_mapping(config["event_config"])
    fallback = None
    if production.get("fallback_provider_factory"):
        fallback = _invoke_factory(
            str(production["fallback_provider_factory"]),
            config=config,
            output=output,
            plans=plans,
        )
    return R26FastController(
        inputs=inputs,
        states=states,
        dispatch=dispatch,
        opendss=opendss,
        events=EventEngine(event_config),
        planner=AsyncPlannerManager(planner_callable, audit=audit),
        plans=plans,
        planner_runtime_budget_seconds=float(
            config.get("planner_runtime_budget_seconds", 300.0)
        ),
        audit=audit,
        fallback=fallback,
    )


__all__ = [
    "ALLOWED_REMAINING_INTEGER_FAMILIES",
    "FixedPlanObservation",
    "JsonPlanBindingStore",
    "PlanBindingEnvelope",
    "ProductionDispatchBackend",
    "ProductionModelBundle",
    "ProductionScienceBridge",
    "SLOW_DECISION_FAMILIES",
    "SourceLockEntry",
    "SourceLockManifest",
    "Stage2BindingError",
    "compare_fixed_plan_observations",
    "create_controller",
]
