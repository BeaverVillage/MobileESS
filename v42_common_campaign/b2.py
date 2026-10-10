"""B2 fixed-input adapter to the same engine used by B3 M1 and M2."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
import ast
import inspect
import textwrap
import time

import numpy as np

from v42_may_campaign_native90.a_routing import rebound
from v42_pr134_b1.common import atomic, record
from .authority import ROOT, assert_peers, checked, verify_request


def guard(model):
    from v42_may_campaign import execution
    from v42_may_campaign_native90.execution import COMPONENTS, authorize
    context, scope = execution._active.get(), execution._model.get()
    if (context is None or scope is None or scope["model"] is not model
            or scope["component"] not in COMPONENTS or scope.get("track") == "A"
            or context["request"]["arm"] != "B2" or model.Params.Threads != 1):
        raise PermissionError("COMMON_U4_B2_MEASURED_NATIVE_SCOPE_REQUIRED")
    authorize(context["request"]["day"], scope["component"])
    # The sealed epoch is checked again at each actual Native entry.
    verify_request(context["request"])
    assert_peers(context["request"])


@contextmanager
def scope(request, manifest):
    from v42_may_campaign import execution
    token = execution._active.set(dict(request=dict(request), manifest=manifest,
        manifest_sha=request["manifest_SHA"], worker_slot=request["worker_slot"]))
    with patch.object(execution, "guard", guard):
        try:
            yield
        finally:
            execution._active.reset(token)


def budget(path, progress):
    from v42_b2_seed_recovery_v19.budget import DateBudget
    from v42_b2_seed_recovery_v19.execution import native_scope
    method = rebound(DateBudget.native_optimize,
        dict(DateBudget.native_optimize.__globals__, guard=guard, native_scope=native_scope))
    class CommonB2Budget(DateBudget):
        native_optimize = method

        def optimize(self, model, *, track, label, requested_seconds, callback=None):
            before = len(self.calls)
            self.native_optimize(model, callback, component="P1", track=track,
                label=label, requested_seconds=requested_seconds)
            if len(self.calls) != before + 1 or self.inflight is not None:
                raise PermissionError("COMMON_U4_COMPLETED_NATIVE_RECEIPT_REQUIRED")
            return self.calls[-1]

    return CommonB2Budget(path, native_limit=1800., wall_limit=None, final_reserve=0., progress=progress)


def _payload(request):
    # Recompute the original FCFS/Q50 input independently using its canonical
    # provenance path. Existing immutable producer receipts are never written.
    from v42_may_campaign_native90 import inputs
    canonical = Path(r"D:\MobileESS_V42")
    generator = rebound(inputs.generate_b2, dict(inputs.generate_b2.__globals__, ROOT=canonical))
    return generator(request)


def _accepted_port(original, request, stage, strict_validator, case):
    """Change only M acceptance; retain the original replay materializer body."""
    if request["arm"] != "B2" or stage.get("feasible_accepted") is not True:
        raise ValueError("COMMON_U4_FULL_PHYSICAL_ACCEPTANCE_REQUIRED")
    receipt = stage["certificate"]["strict_UB"]
    checked(receipt)
    replay = strict_validator(case, case.output / "BEST_STRICT_UB_POINT.npz", {})
    if replay.get("PASS") is not True or replay["exact_Global_UB"] != stage["exact_Global_UB"]:
        raise ValueError("COMMON_U4_INDEPENDENT_PLANNING_REPLAY_DRIFT")
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    function = tree.body[0]
    first_if = next(node for node in function.body if isinstance(node, ast.If))
    first_if.test = ast.Call(func=ast.Name(id="_common_invalid_contract", ctx=ast.Load()),
        args=[ast.Name(id="request", ctx=ast.Load()), ast.Name(id="stage", ctx=ast.Load())], keywords=[])
    changes = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            values = [v.value for v in node.iter.elts if isinstance(v, ast.Constant)]
            if values == ["strict_UB", "exact_LB"]:
                node.iter = ast.Tuple(elts=[ast.Constant("strict_UB")], ctx=ast.Load())
                changes += 1
    if changes != 1:
        raise PermissionError("COMMON_U4_ORIGINAL_ACCEPTED_MATERIALIZER_AST_DRIFT")
    def invalid_contract(current_request, current_stage):
        return (current_request != request or current_stage is not stage
            or current_stage.get("PASS") is not True or current_stage.get("accepted") is not True
            or current_stage.get("feasible_accepted") is not True
            or current_stage.get("arm") != "B2" or current_stage.get("day") != request["day"]
            or current_stage.get("case_sha") != case.case_sha
            or current_stage.get("P2_calls") != 0
            or current_stage.get("scientific_case_sha") != case.case_sha
            or current_stage.get("UB") != current_stage.get("verified_UB"))
    namespace = dict(original.__globals__, _common_invalid_contract=invalid_contract)
    ast.fix_missing_locations(tree)
    exec(compile(tree, inspect.getfile(original), "exec"), namespace)
    return namespace[original.__name__]


def run(request, manifest, progress):
    from v42_b2_build_authority_v13 import build_case
    from v42_autonomous_b2.worker import proof_routes
    from v42_may_campaign_native90 import m_stage, operations
    from v42_common_mess import optimize_case
    started = time.perf_counter()
    output = Path(request["output"])
    routes = proof_routes(request)
    with scope(request, manifest):
        ledger = budget(Path(request["result"]).parent / "NATIVE_RUNTIME_LEDGER.json", progress)
        source_request = dict(request, _budget=ledger)
        progress(dict(phase="B2_ORIGINAL_MODEL_AND_TRANSPORT_BUILD", native_runtime_seconds=0))
        with ledger.cost("model_preparation", "B2_ORIGINAL_FULL_COMPACT_C3A"):
            payload = _payload(request)
            case = build_case(payload, source_request, progress)
        strict = routes["final"]["_strict_ub"]
        # Original _plan exports FULL coordinates and the complete 96-slot plan.
        result, point = optimize_case(case, ledger, progress,
            stage_identity=dict(stage="B2_M", day=request["day"], source_SHA=request["source_SHA"],
                fixed_input_sha=payload["identity"]["reference_SHA"]),
            initial_point=getattr(case, "point", None), strict_validator=strict,
            plan_exporter=m_stage._plan)
        result.update(day=request["day"], arm="B2", planning=case.planning,
            Native_Runtime=ledger.used(), native_runtime_seconds=ledger.used(),
            wall_seconds=time.perf_counter()-started, stage_wall_seconds=time.perf_counter()-started,
            P2_calls=0, AIDC_optimization_calls=0, output=str(output))
        result["PASS"] = result["accepted"] = result.get("feasible_accepted") is True
        if point is None or result["PASS"] is not True:
            atomic(output / "M_STAGE_RESULT.json", result)
            return dict(scientific=result, PASS=False, status="M_NO_VALID_FEASIBLE",
                Native_Runtime=ledger.used(), stage_wall_seconds=time.perf_counter()-started)
        case.point = point
        result["mess_plan"] = record(output / "OPTIMIZED_MESS_PLAN.json")
        result["mess"] = m_stage._plan(case, point)
        result["certificate"] = dict(strict_UB=record(output / "BEST_STRICT_UB_CERTIFICATE.json"),
            original_domain_equivalence=case.identity["transport"])
        atomic(output / "M_STAGE_RESULT.json", result)
        materializer = _accepted_port(operations._accepted, request, result, strict, case)
        # Only the newly qualified B2 M contract changes. All Actual/Fresh source
        # arithmetic, frozen decision checking and zero optimizer policy remain.
        with patch.object(operations, "_accepted", materializer):
            from v42_may_campaign_native90.preflight import native_zero
            with native_zero() as attempts:
                evaluation = operations.run(request, result, progress)
            if attempts:
                raise PermissionError("COMMON_U4_ACTUAL_NATIVE_OPTIMIZE_FORBIDDEN")
        ac_pass = evaluation.get("PASS") is True and evaluation.get("physical_violation") is False
        status = "COMPLETED_PHYSICAL_PASS" if ac_pass else "ACTUAL_AC_FAILED"
        return dict(scientific=result, evaluation=evaluation, PASS=ac_pass,
            status=status, feasible_accepted=True,
            global_gap_certified=result.get("global_gap_certified", False),
            actual_ac_physical_pass=ac_pass, Native_Runtime=ledger.used(),
            native_runtime_seconds=ledger.used(), stage_wall_seconds=time.perf_counter()-started,
            files=[record(output / "M_STAGE_RESULT.json"), record(output / "BEST_STRICT_UB_POINT.npz"),
                record(output / "BEST_STRICT_UB_CERTIFICATE.json"), result["mess_plan"]])
