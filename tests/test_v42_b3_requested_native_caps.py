"""Three bounded source-body budget tests; no real solver or model import.

The real SourceStageLedger and SourceRegistry.rebind compile the current
Native90 budget body. Only its imported namespace and model are test doubles.
Every ledger produced here is explicitly FAKE_SOURCE_TEST evidence.
"""
import ast
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter, process_time
from types import ModuleType, SimpleNamespace

import pytest

from v42_b3_joint.contracts import canonical, StageRequest
from v42_b3_joint.dry_run import fixture_authority, fixture_aidc
from v42_b3_joint.native_ledger import SourceStageLedger
from v42_b3_joint.source_runtime import FakeSourceRegistry, RealStageContext, SourceRegistry


ROOT = Path(__file__).resolve().parents[1]
BUDGET_SOURCE = ROOT / "v42_may_campaign_native90/budget.py"
CAP_POLICY = "MIN_VALID_REQUESTED_SECONDS_AND_REMAINING_NATIVE_V1"
REAL_MODEL_ATTEMPTS = []


class Clock:
    value = 0.

    def __call__(self):
        return self.value


class RecordingModel:
    def __init__(self, runtime=1.25, *, fail=False):
        self.Params = SimpleNamespace(Threads=8, TimeLimit=99999., Method=1,
            Presolve=2, Crossover=-1, FeasibilityTol=1e-6, OptimalityTol=1e-6,
            NumericFocus=0, ScaleFlag=-1, MemLimit=math.inf, SoftMemLimit=math.inf)
        self.Runtime, self.Work, self.Status, self.SolCount, self.ObjBound = runtime, 0., 9, 0, None
        self.entries, self.fail, self.terminations = [], fail, 0

    def setParam(self, name, value):
        setattr(self.Params, name, value)

    def cbGet(self, key):
        return self.Runtime

    def terminate(self):
        self.terminations += 1

    def optimize(self, callback):
        self.entries.append(deepcopy(vars(self.Params)))
        if self.Runtime is not None:
            callback(self, 1)
        if self.fail:
            raise RuntimeError("FAKE_MODEL_FAILURE")


class CurrentBudgetRegistry(FakeSourceRegistry):
    """Fake authorization with the production AST rebinder, not a budget proxy."""
    def rebind(self, module_name, symbol, **routing):
        return SourceRegistry.rebind(self, module_name, symbol, **routing)


@pytest.fixture
def source_fixture(tmp_path, monkeypatch):
    fake_gp = ModuleType("gurobipy")
    fake_gp.GurobiError = type("FakeGurobiError", (Exception,), {})
    fake_gp.GRB = SimpleNamespace(Callback=SimpleNamespace(POLLING=0, RUNTIME=2))

    def denied_real_model(*args, **kwargs):
        REAL_MODEL_ATTEMPTS.append("FORBIDDEN_MODEL_CONSTRUCTION")
        raise AssertionError("REAL_MODEL_CONSTRUCTION_FORBIDDEN")

    fake_gp.Model = denied_real_model
    monkeypatch.setitem(sys.modules, "gurobipy", fake_gp)
    source = BUDGET_SOURCE.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    module = ModuleType("v42_may_campaign_native90.budget")
    module.__file__, module.__b3_fake__ = str(BUDGET_SOURCE), True

    @contextmanager
    def denied_scope(*args, **kwargs):
        raise AssertionError("UNROUTED_SOURCE_NATIVE_SCOPE")
        yield

    module.__dict__.update(contextmanager=contextmanager, Path=Path,
        perf_counter=perf_counter, process_time=process_time, math=math,
        atomic=lambda *args: None, now=lambda: "FAKE_SOURCE_TEST",
        d_path=Path, native_scope=denied_scope, guard=denied_real_model)
    tree = ast.parse(source.decode("utf-8-sig"), filename=str(BUDGET_SOURCE))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, str(BUDGET_SOURCE), "exec"), module.__dict__)
    registry = CurrentBudgetRegistry({module.__name__: module}, root=ROOT)

    def context(stage="M1", suffix=""):
        authority = fixture_authority("2025-05-01")
        request = StageRequest(stage, authority, fixture_aidc() if stage.startswith("M") else None)
        return RealStageContext(request, tmp_path / "INPUT", tmp_path / (stage + suffix),
            canonical({"day": authority.day}), registry, SimpleNamespace(), {},
            authority.source_sha, "FAKE_CURRENT_BUDGET_BODY_ONLY")

    yield context, registry, module, source_sha
    assert hashlib.sha256(BUDGET_SOURCE.read_bytes()).hexdigest() == source_sha


def test_actual_rebound_budget_caps_remaining_and_stage_independence(source_fixture):
    context, registry, module, source_sha = source_fixture
    clock = Clock()
    m1 = SourceStageLedger(context(), clock=clock)
    delegate = type(m1.budget).native_optimize
    assert type(m1.budget).__bases__ == (module.DateBudget,)
    assert delegate.__code__.co_filename == str(BUDGET_SOURCE) + ":B3_ROUTED"
    assert delegate.__globals__["native_scope"].__self__ is m1
    assert delegate.__globals__["guard"].__self__ is m1
    assert delegate.__globals__["d_path"].__self__ is m1
    binding = [row for row in registry.audit if row.get("symbol") == "DateBudget.native_optimize"][0]
    assert binding["source_sha"] == source_sha
    assert binding["original_AST_sha"] == binding["routed_AST_sha"]
    clock.value = 10000.  # Native accounting has no CPU or wall cutoff.
    models = [RecordingModel(30.125), RecordingModel(2.5), RecordingModel(5350.), RecordingModel(1.)]
    for model, requested, track in zip(models, (30, 45, 5400, 45), ("RMP", "PRICING", "UB", "PRICING")):
        m1.optimize(model, track=track, label="FAKE_CAP_READBACK", requested_seconds=requested)
    assert [model.entries[0]["TimeLimit"] for model in models] == [30., 45., 5367.375, 17.375]
    assert models[0].terminations == 1  # Overshoot is observed, never rounded down.
    receipt = m1.receipt()
    assert receipt["evidence_kind"] == "FAKE_SOURCE_TEST"
    assert receipt["measured_native_runtime"] == 5383.625
    assert receipt["calls"][0]["Native_Runtime"] == 30.125
    assert all(row["requested_cap_policy"] == CAP_POLICY for row in receipt["calls"])
    assert receipt["native_limit_seconds"] == 5400 and receipt["wall_limit_seconds"] is None
    assert receipt["P2_calls"] == 0
    assert all(model.Params.Threads == 1 and model.Params.FeasibilityTol == 1e-9
        and model.Params.OptimalityTol == 1e-9 and model.Params.Method == 1
        and model.Params.MemLimit == math.inf and model.Params.SoftMemLimit == math.inf for model in models)
    m2 = SourceStageLedger(context("M2"))
    m2_model = RecordingModel(2.)
    m2.optimize(m2_model, track="RMP", label="INDEPENDENT_M2", requested_seconds=30)
    assert m2_model.Params.TimeLimit == 30. and m2.used() == 2. and m1.used() == 5383.625
    assert m1.identity["fixed_input_sha"] != m2.identity["fixed_input_sha"]
    a1 = SourceStageLedger(context("A1"))
    a_model = RecordingModel(1.)
    a1.native_optimize(a_model, component="ORIGINAL_P1", track="A1")
    assert a_model.Params.TimeLimit == 5400.  # Omitted/5400 A cap remains unrestricted.
    assert a1.receipt()["calls"][0]["requested_seconds"] == 5400.
    assert SourceStageLedger(context()).receipt()["calls"] == receipt["calls"]


def test_invalid_requested_caps_are_denied_before_model_or_ledger_mutation(source_fixture):
    context, registry, module, source_sha = source_fixture
    ledger = SourceStageLedger(context())
    before = ledger.path.read_bytes()
    for invalid in (None, True, False, 0, -1, math.nan, math.inf, -math.inf, "30", 10 ** 1000):
        model = RecordingModel()
        parameters = vars(model.Params).copy()
        with pytest.raises(ValueError, match="FINITE_POSITIVE_REQUESTED_NATIVE_CAP_REQUIRED"):
            ledger.optimize(model, track="RMP", label="INVALID", requested_seconds=invalid)
        assert model.entries == [] and vars(model.Params) == parameters
        assert ledger.path.read_bytes() == before
    assert ledger.used() == 0. and ledger.calls == [] and ledger.inflight is None
    with pytest.raises(ValueError, match="B3_P2_NATIVE_FORBIDDEN"):
        ledger.native_optimize(RecordingModel(), component="P2", requested_seconds=30)
    assert ledger.path.read_bytes() == before


def test_restart_keeps_legacy_rows_and_checks_new_caps_failures_and_unknown(source_fixture):
    context, registry, module, source_sha = source_fixture
    current = context()
    ledger = SourceStageLedger(current)
    ledger.native_optimize(RecordingModel(3.5), track="M1")
    # Explicit historical fixture: old bodies recorded requested30 but used5400.
    legacy_document = json.loads(ledger.path.read_text(encoding="utf-8"))
    legacy = legacy_document["calls"][0]
    legacy.pop("requested_cap_policy")
    legacy["requested_seconds"] = 30
    ledger.path.write_text(canonical(legacy_document) + "\n", encoding="utf-8")
    before_restart = ledger.path.read_bytes()
    resumed = SourceStageLedger(current)
    assert resumed.path.read_bytes() == before_restart
    with pytest.raises(RuntimeError, match="FAKE_MODEL_FAILURE"):
        resumed.optimize(RecordingModel(7.25, fail=True), track="RMP", label="FAILED", requested_seconds=30)
    receipt = resumed.receipt()
    assert receipt["calls"][0] == legacy
    assert receipt["calls"][1]["effective_TimeLimit"] == 30.
    assert receipt["calls"][1]["Native_Runtime"] == 7.25 and receipt["calls"][1]["status"] == "FAILED"
    assert receipt["measured_native_runtime"] == 10.75
    restarted = SourceStageLedger(current)
    assert restarted.receipt()["calls"] == receipt["calls"]
    document = json.loads(restarted.path.read_text(encoding="utf-8"))
    for field, value in (("requested_cap_policy", "UNKNOWN_POLICY"), ("requested_seconds", True),
                         ("requested_seconds", 0), ("requested_seconds", math.inf)):
        corrupted = deepcopy(document)
        corrupted["calls"][1][field] = value
        with pytest.raises(ValueError, match="REQUESTED_CAP"):
            restarted._verify_document(corrupted)
    corrupted = deepcopy(document)
    corrupted["calls"][1]["effective_TimeLimit"] = 5396.5
    with pytest.raises(ValueError, match="NUMERICAL_LIMIT|REMAINING_LIMIT"):
        restarted._verify_document(corrupted)
    unknown_context = context("M2", "_UNKNOWN")
    unknown = SourceStageLedger(unknown_context)
    with pytest.raises(RuntimeError, match="NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE"):
        unknown.optimize(RecordingModel(None), track="RMP", label="UNKNOWN", requested_seconds=30)
    unknown_receipt = SourceStageLedger(unknown_context).receipt()
    assert unknown_receipt["quarantined"] is True
    assert unknown_receipt["calls"][0]["Native_Runtime"] is None
    assert unknown_receipt["measured_native_runtime"] == 0.  # No invented 30-second runtime.
    denied = RecordingModel()
    with pytest.raises(RuntimeError, match="UNMEASURED_RUNTIME_QUARANTINE"):
        SourceStageLedger(unknown_context).optimize(denied, track="RMP", label="DENIED", requested_seconds=30)
    assert denied.entries == []
