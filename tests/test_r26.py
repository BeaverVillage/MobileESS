from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import tarfile
import unittest

from r26.audit import MemoryAuditLogger
from r26.controller import CausalFrame, R26FastController
from r26.dispatch import (
    DispatchResult,
    ModelStructureAudit,
    OpenDssResult,
    audit_model_structure,
    fix_and_relax_discrete_variables,
)
from r26.event_engine import EventConfig, EventEngine, SoftMetricRule
from r26.experiment import exact_online_comparison, required_matrix, threshold_sensitivity_matrix
from r26.gap_reporting import (
    ScientificGapSnapshot,
    incumbent_required_for_gap,
    make_global_certificate_callback,
    minimization_relative_gap,
)
from r26.benders import BendersCut, BendersCutCache
from r26.multires_horizon import build_multires_horizon
from r26.opportunity_gap import GlobalRelaxationBound, evaluate_opportunity_gap
from r26.planner_manager import AsyncPlannerManager, AtomicRoutePlanStore, PlannerRequest
from r26.route_plan import MessRoute, RoutePlan, RouteState, RouteStep, WorkAssignment


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_plan(*, issue: int = 113, state_hash: str = "pre113", horizon: int = 3) -> RoutePlan:
    steps = []
    state = RouteState(location="IDC01")
    for index in range(horizon):
        step = RouteStep(index, issue + index, state, "STAY", state)
        steps.append(step)
    plan = RoutePlan(
        schema_version="r26.route_plan.v1",
        plan_id="plan-1",
        created_at_utc="2026-08-14T00:00:00Z",
        cutoff_timestamp_utc="2026-08-14T00:00:00Z",
        source_state_hash=state_hash,
        valid_from_issue=issue,
        step_seconds=300,
        horizon_steps=horizon,
        terminal_policy="CAUSAL_STAY_OR_CONTINUE_TRANSIT",
        planner_status="FEASIBLE",
        planner_objective=1.0,
        planner_runtime_seconds=0.2,
        mess_routes=(MessRoute("MESS01", tuple(steps)),),
    )
    plan.validate()
    return plan


class GapTests(unittest.TestCase):
    def test_negative_and_positive_incumbent_threshold(self):
        neg = incumbent_required_for_gap(-100.0, 0.03)
        pos = incumbent_required_for_gap(100.0, 0.03)
        self.assertAlmostEqual(neg.threshold, -100.0 / 1.03)
        self.assertAlmostEqual(pos.threshold, 100.0 / 0.97)
        self.assertTrue(neg.accepts(neg.threshold))
        self.assertTrue(pos.accepts(pos.threshold))
        self.assertFalse(neg.accepts(neg.threshold + 0.01))

    def test_restricted_bound_never_becomes_global(self):
        snap = ScientificGapSnapshot.create(
            incumbent=-1159.0,
            restricted_obj_bound=-1180.0,
            restricted_native_gap=0.018,
            exact_global_lower_bound=-1200.0,
        )
        self.assertAlmostEqual(snap.global_lower_bound, -1200.0)
        self.assertNotEqual(snap.global_certified_gap, snap.rmp_native_gap)
        self.assertEqual(snap.restricted_bound_authority, "DIAGNOSTIC_ONLY_NOT_GLOBAL")

    def test_callback_stops_only_on_global_certificate(self):
        class Callback:
            MIPSOL = 1
            MIPSOL_OBJ = 2
            MIPSOL_OBJBND = 3

        class Grb:
            pass

        Grb.Callback = Callback

        class Model:
            _r26_grb = Grb
            stopped = False
            values = {2: -98.0, 3: -98.1}

            def cbGet(self, key):
                return self.values[key]

            def terminate(self):
                self.stopped = True

        callback = make_global_certificate_callback(exact_global_lower_bound=-100.0)
        model = Model()
        callback(model, Callback.MIPSOL)
        self.assertTrue(model.stopped)
        model.values[2] = -96.0
        model.stopped = False
        callback(model, Callback.MIPSOL)
        self.assertFalse(model.stopped)

    def test_opportunity_gap_requires_same_state_global_authority(self):
        bound = GlobalRelaxationBound(-103.0, "EXACT_RELAXATION", "state-a", True)
        decision = evaluate_opportunity_gap(
            keep_objective=-100.0,
            lower_bound=bound,
            source_state_hash="state-a",
            trigger_threshold=0.025,
        )
        self.assertAlmostEqual(decision.opportunity_gap, 0.03)
        self.assertTrue(decision.request_full_replan)
        with self.assertRaises(ValueError):
            evaluate_opportunity_gap(
                keep_objective=-100.0,
                lower_bound=replace(bound, globally_valid=False),
                source_state_hash="state-a",
                trigger_threshold=0.025,
            )


class HierarchicalPlanningTests(unittest.TestCase):
    def test_multires_h54_becomes_26_integer_stages(self):
        stages = build_multires_horizon()
        self.assertEqual(len(stages), 26)
        self.assertEqual(sum(stage.duration_minutes for stage in stages), 270)
        self.assertEqual([stage.duration_minutes for stage in stages[:12]], [5] * 12)
        self.assertEqual([stage.duration_minutes for stage in stages[12:]], [15] * 14)

    def test_benders_cut_reuse_is_structure_scoped_and_deduplicated(self):
        cut = BendersCut(
            "OPTIMALITY", (("route:MESS01", 1.0),), 3.0, "topology-a", 151, "OPTIMAL"
        )
        cache = BendersCutCache()
        self.assertTrue(cache.add(cut))
        self.assertFalse(cache.add(cut))
        self.assertEqual(cache.applicable("topology-a"), (cut,))
        self.assertEqual(cache.applicable("topology-b"), ())


class RoutePlanTests(unittest.TestCase):
    def test_deterministic_shift_and_no_rewrite(self):
        plan = sample_plan()
        original_json = plan.to_json()
        shifted = plan.shift_one(plan.first_steps(), next_source_state_hash="post113")
        self.assertEqual(plan.to_json(), original_json)
        self.assertEqual(shifted.valid_from_issue, 114)
        self.assertEqual(shifted.source_state_hash, "post113")
        self.assertEqual(shifted.shift_count, 1)
        self.assertEqual(len(shifted.committed_prefix), 1)
        shifted2 = plan.shift_one(plan.first_steps(), next_source_state_hash="post113")
        self.assertEqual(shifted.checksum, shifted2.checksum)

    def test_wrong_commit_is_rejected(self):
        plan = sample_plan()
        bad = replace(plan.first_steps()["MESS01"], after=RouteState(location="IDC02"))
        with self.assertRaises(ValueError):
            plan.shift_one({"MESS01": bad})

    def test_no_teleport_and_transit_is_preserved(self):
        start = RouteState(location="IDC01")
        transit = RouteState(
            transit_origin="IDC01", transit_destination="IDC02", remaining_steps=2
        )
        step0 = RouteStep(0, 113, start, "MOVE", transit, travel_steps=3)
        step1 = RouteStep(
            1,
            114,
            transit,
            "CONTINUE_TRANSIT",
            replace(transit, remaining_steps=1),
        )
        step2 = RouteStep(
            2,
            115,
            replace(transit, remaining_steps=1),
            "CONTINUE_TRANSIT",
            RouteState(location="IDC02"),
        )
        plan = replace(sample_plan(), mess_routes=(MessRoute("MESS01", (step0, step1, step2)),))
        plan.validate()
        shifted = plan.shift_one(plan.first_steps(), next_source_state_hash="post")
        self.assertTrue(shifted.mess_routes[0].steps[0].before.in_transit)
        bad = replace(step0, after=RouteState(location="IDC02"))
        with self.assertRaises(ValueError):
            bad.validate()

    def test_checksum_rejects_tampering(self):
        envelope = json.loads(sample_plan().to_json())
        envelope["route_plan"]["plan_id"] = "tampered"
        with self.assertRaises(ValueError):
            RoutePlan.from_json(json.dumps(envelope))

    def test_work_start_is_committed_once_then_removed_from_shifted_plan(self):
        plan = replace(
            sample_plan(),
            work_assignments=(
                WorkAssignment("job-1", "IDC01", "rack-1", 113, 4),
            ),
        )
        plan.validate()
        shifted = plan.shift_one(plan.first_steps(), next_source_state_hash="post113")
        self.assertEqual(shifted.work_assignments, ())
        self.assertEqual(shifted.committed_prefix[0]["work_starts"][0]["job_uid"], "job-1")


def event_config() -> EventConfig:
    return EventConfig(
        hard_flags=("hard",),
        soft_rules=(SoftMetricRule("error", "ABOVE", 10.0, 7.0, "percent"),),
        soft_dwell_steps=2,
        max_refresh_steps=6,
    )


class EventTests(unittest.TestCase):
    def test_hard_event_bypasses_dwell(self):
        decision = EventEngine(event_config()).evaluate(
            issue=1, hard_flags={"hard": True}, soft_metrics={"error": 0}, steps_since_plan=0
        )
        self.assertTrue(decision.request_replan)
        self.assertEqual(decision.severity, "HARD")

    def test_soft_hysteresis_and_dwell(self):
        engine = EventEngine(event_config())
        one = engine.evaluate(issue=1, hard_flags={}, soft_metrics={"error": 11}, steps_since_plan=0)
        two = engine.evaluate(issue=2, hard_flags={}, soft_metrics={"error": 8}, steps_since_plan=1)
        three = engine.evaluate(issue=3, hard_flags={}, soft_metrics={"error": 7}, steps_since_plan=2)
        self.assertFalse(one.request_replan)
        self.assertTrue(two.request_replan)
        self.assertFalse(three.metric_state["error"])

    def test_max_refresh_and_reason_coalescing(self):
        decision = EventEngine(event_config()).evaluate(
            issue=7, hard_flags={"hard": True}, soft_metrics={"error": 11}, steps_since_plan=6
        )
        self.assertTrue(decision.request_replan)
        self.assertIn("HARD:hard", decision.reasons)
        self.assertIn("MAX_REFRESH", decision.reasons)

    def test_local_repair_for_local_event_and_full_for_refresh(self):
        config = replace(event_config(), local_repair_enabled=True)
        local = EventEngine(config).evaluate(
            issue=1, hard_flags={"hard": True}, soft_metrics={"error": 0}, steps_since_plan=0
        )
        refresh = EventEngine(config).evaluate(
            issue=7, hard_flags={}, soft_metrics={"error": 0}, steps_since_plan=6
        )
        self.assertEqual(local.requested_mode, "LOCAL_REPAIR")
        self.assertEqual(refresh.requested_mode, "FULL_REPLAN")


class PlannerTests(unittest.TestCase):
    def test_delayed_planner_poll_does_not_wait(self):
        gate = threading.Event()

        def planner(request):
            gate.wait(1)
            return sample_plan(issue=request.issue, state_hash=request.source_state_hash)

        manager = AsyncPlannerManager(planner)
        try:
            manager.request(PlannerRequest(114, "2026-08-14T00:00:00Z", "h", ("x",), 10))
            started = time.monotonic()
            result = manager.poll(issue=114, source_state_hash="h")
            self.assertEqual(result.status, "NOT_READY")
            self.assertLess(time.monotonic() - started, 0.1)
        finally:
            gate.set()
            manager.close(wait=True)

    def test_requests_coalesce_and_single_worker(self):
        gate = threading.Event()

        def planner(request):
            gate.wait(1)
            return sample_plan(issue=request.issue, state_hash=request.source_state_hash)

        manager = AsyncPlannerManager(planner)
        try:
            first = manager.request(PlannerRequest(114, "2026-08-14T00:00:00Z", "a", ("A",), 10))
            second = manager.request(PlannerRequest(115, "2026-08-14T00:05:00Z", "b", ("B",), 10))
            third = manager.request(PlannerRequest(116, "2026-08-14T00:10:00Z", "c", ("C",), 10))
            self.assertEqual(first.disposition, "STARTED")
            self.assertEqual(second.disposition, "COALESCED")
            self.assertEqual(third.disposition, "COALESCED")
            self.assertEqual(third.pending_issue, 116)
        finally:
            gate.set()
            manager.close(wait=True)

    def test_stale_or_hash_mismatch_candidate_rejected(self):
        manager = AsyncPlannerManager(
            lambda request: sample_plan(issue=request.issue, state_hash=request.source_state_hash)
        )
        try:
            manager.request(PlannerRequest(114, "2026-08-14T00:00:00Z", "a", ("A",), 10))
            for _ in range(100):
                result = manager.poll(issue=115, source_state_hash="wrong")
                if result.status != "NOT_READY":
                    break
                time.sleep(0.001)
            self.assertEqual(result.status, "REJECTED")
        finally:
            manager.close(wait=True)

    def test_boundary_atomic_swap(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AtomicRoutePlanStore(Path(directory) / "active.json")
            plan = sample_plan()
            store.swap(plan, issue=113, source_state_hash="pre113")
            self.assertEqual(store.load().checksum, plan.checksum)
            with self.assertRaises(ValueError):
                store.swap(plan, issue=114, source_state_hash="pre113")

    def test_pending_full_replan_dominates_and_local_scopes_union(self):
        gate = threading.Event()

        def planner(request):
            gate.wait(1)
            return sample_plan(issue=request.issue, state_hash=request.source_state_hash)

        manager = AsyncPlannerManager(planner)
        try:
            manager.request(PlannerRequest(114, "t0", "a", ("A",), 10))
            manager.request(
                PlannerRequest(
                    115, "t1", "b", ("B",), 10, "LOCAL_REPAIR", ("MESS01",), (), 12
                )
            )
            manager.request(
                PlannerRequest(
                    116, "t2", "c", ("C",), 10, "FULL_REPLAN", (), (), 26,
                    (5,) * 12 + (15,) * 14,
                )
            )
            pending = manager._pending_request
            self.assertEqual(pending.mode, "FULL_REPLAN")
            self.assertEqual(pending.affected_mess_ids, ("MESS01",))
            self.assertEqual(pending.horizon_steps, 26)
            self.assertEqual(sum(pending.stage_durations_minutes), 270)
        finally:
            gate.set()
            manager.close(wait=True)


class FakeVar:
    def __init__(self, name, vtype, lb=0.0, ub=1.0):
        self.VarName, self.VType, self.LB, self.UB = name, vtype, lb, ub


class FakeModel:
    def __init__(self):
        self.vars = [FakeVar("route", "B"), FakeVar("work", "B"), FakeVar("p", "C", -1, 1)]
        self.NumConstrs = 2
        self.NumQConstrs = 1

    def getVars(self):
        return self.vars

    def update(self):
        pass


class DispatchTests(unittest.TestCase):
    def test_fixed_plan_numerical_consistency_and_numint_report(self):
        model = FakeModel()
        fix_and_relax_discrete_variables(model, {"route": 1.0})
        audit = audit_model_structure(model)
        self.assertEqual(model.vars[0].LB, model.vars[0].UB)
        self.assertEqual(audit.num_integer_vars, 1)
        self.assertEqual(audit.formulation, "REDUCED_AC_AWARE_MIQCP")
        fix_and_relax_discrete_variables(model, {"work": 0.0})
        audit = audit_model_structure(model)
        self.assertEqual(audit.num_integer_vars, 0)
        self.assertEqual(audit.formulation, "CONTINUOUS_AC_AWARE_QCP")


class ExperimentTests(unittest.TestCase):
    def test_required_baselines_and_threshold_grid(self):
        matrix = required_matrix()
        self.assertEqual(len(matrix), 7)
        self.assertEqual(len(threshold_sensitivity_matrix()), 27)
        exact = matrix[0]
        self.assertEqual(exact.scored_issues_per_month, 54)
        self.assertEqual(
            exact.evaluation_scope,
            "MONTHLY_PREDECLARED_54_ISSUE_ORACLE_WINDOW",
        )
        self.assertTrue(all(case.scored_issues_per_month == 2016 for case in matrix[1:]))

        contract = json.loads((ROOT / "r26/config/r26_contract.json").read_text())
        sampling = contract["annual_execution_after_validation"]
        self.assertEqual(sampling["scored_days_per_month"], 7)
        self.assertEqual(sampling["scored_steps_per_month"], 2016)
        self.assertEqual(sampling["total_scored_steps"], 24192)
        self.assertEqual(sampling["monthly_waves"], 3)
        self.assertEqual(sampling["exact_oracle"]["issues_per_month"], 54)
        self.assertFalse(sampling["exact_oracle"]["full_7day_exact_run_required"])

    def test_exact_online_degradation_and_route_fraction(self):
        comparison = exact_online_comparison(
            exact_objective=100.0,
            online_objective=101.0,
            online_route_solves=32,
        )
        self.assertAlmostEqual(comparison["economic_degradation_relative"], 0.01)
        self.assertAlmostEqual(comparison["route_solve_fraction"], 32 / 288)


class ControllerTests(unittest.TestCase):
    def test_invalidating_hard_event_without_fallback_fails_closed(self):
        class Inputs:
            def load(self, issue):
                return CausalFrame(
                    issue,
                    "2026-08-14T00:00:00Z",
                    "pre113",
                    {"ACTIVE_PLAN_INFEASIBLE": True},
                    {},
                    issue + 1,
                    "predicted",
                    {},
                )

        class States:
            def restore_pre(self, frame):
                return {}

            def commit_post(self, **kwargs):
                raise AssertionError("must not commit")

        class Dispatch:
            def solve(self, **kwargs):
                raise AssertionError("must not dispatch an invalidated route")

        class OpenDss:
            def verify_fresh(self, **kwargs):
                raise AssertionError("must not verify")

        config = EventConfig(
            hard_flags=("ACTIVE_PLAN_INFEASIBLE",),
            soft_rules=(),
            soft_dwell_steps=1,
            max_refresh_steps=6,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = AtomicRoutePlanStore(Path(directory) / "active.json")
            store.swap(sample_plan(), issue=113, source_state_hash="pre113")
            manager = AsyncPlannerManager(
                lambda request: sample_plan(issue=request.issue, state_hash=request.source_state_hash)
            )
            controller = R26FastController(
                inputs=Inputs(),
                states=States(),
                dispatch=Dispatch(),
                opendss=OpenDss(),
                events=EventEngine(config),
                planner=manager,
                plans=store,
                planner_runtime_budget_seconds=60,
            )
            try:
                result = controller.run_issue(113)
            finally:
                manager.close(wait=False)
        self.assertEqual(result.status, "FAIL_CLOSED_NO_VALID_ROUTE_PLAN")
        self.assertFalse(result.committed)

    def test_fresh_opendss_failure_prevents_commit_and_no_future_read(self):
        calls = []

        class Inputs:
            def load(self, issue):
                calls.append(issue)
                return CausalFrame(
                    issue, "2026-08-14T00:00:00Z", "pre113", {"hard": False},
                    {"error": 0.0}, issue + 1, "predicted", {"actual_through_issue": issue}
                )

        class States:
            committed = False

            def restore_pre(self, frame):
                return {"hash": frame.pre_state_hash}

            def commit_post(self, **kwargs):
                self.committed = True
                return "post"

        structure = ModelStructureAudit(1, 1, 1, 0, (), "CONTINUOUS_AC_AWARE_QCP")

        class Dispatch:
            def solve(self, **kwargs):
                return DispatchResult(True, "OPTIMAL", 1.0, 0.01, {}, {}, structure, True)

        class OpenDss:
            def verify_fresh(self, **kwargs):
                return OpenDssResult(False, "VOLTAGE_VIOLATION", {})

        states = States()
        with tempfile.TemporaryDirectory() as directory:
            store = AtomicRoutePlanStore(Path(directory) / "active.json")
            store.swap(sample_plan(), issue=113, source_state_hash="pre113")
            manager = AsyncPlannerManager(lambda request: sample_plan())
            controller = R26FastController(
                inputs=Inputs(), states=states, dispatch=Dispatch(), opendss=OpenDss(),
                events=EventEngine(event_config()), planner=manager, plans=store,
                planner_runtime_budget_seconds=60, audit=MemoryAuditLogger(),
            )
            try:
                result = controller.run_issue(113)
            finally:
                manager.close(wait=False)
        self.assertFalse(result.committed)
        self.assertFalse(states.committed)
        self.assertEqual(calls, [113])


class FrozenR25RTests(unittest.TestCase):
    def test_frozen_r25r_hashes_unchanged(self):
        expected = {
            "driver_r25r_stage1_resume136.py": "f41c9019301a68b23a43d6521fe37e69a868c115cd57806f2e97ba23f8a1a4e0",
            "R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz": "4c2e39b4f136f36a6d3c13f61acb93a7f32b256cfc75d06404cef8fe9ddf312d",
        }
        for relative, digest in expected.items():
            self.assertEqual(sha(ROOT / relative), digest, relative)
        members_expected = {
            "CHECKSUMS.sha256": "2b586ebe307298d132aab2d96389e9ef8e97fba05082c9d892e3729c01974e0d",
            "main.py": "911abe18479524b8e48cc058c4a6ed3b8ab9ce673d4de78780a71ca3b7f0a5cd",
            "r25m_b6_exact_path_decomposition.py": "cab1b8cef906b08eaaa75d5e044fcb34ffc45183b24c5c4d8cfddb3508c58795",
        }
        with tarfile.open(ROOT / "R25R_STAGE1_RESUME136_SCIENCE_BUNDLE.tar.gz", "r:gz") as archive:
            members = {member.name.removeprefix("./"): member for member in archive.getmembers()}
            for relative, digest in members_expected.items():
                self.assertIn(relative, members)
                payload = archive.extractfile(members[relative]).read()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), digest, relative)


if __name__ == "__main__":
    unittest.main()
