"""Sequential, synthetic B3 software tests; no scientific or native execution.

Run this file alone with unittest discovery. The 96-slot fixtures exercise
interface axes, hashes and gates; their bounds/replays are explicitly MOCK.
No historical May result is reused as a scientific certificate.
"""
import ast
from dataclasses import FrozenInstanceError, asdict, replace
from fractions import Fraction
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from v42_b3_joint import policy
from v42_b3_joint.adapters import NativeStageAdapter, prepare_source_binding
from v42_b3_joint.budget import MockClock, MockNativeBudget, NativeStageBudget
from v42_b3_joint.certificates import exact_bound, verify_certificate
from v42_b3_joint.contracts import (
    AIDCDecision, Authority, MESSDecision, StageRequest, WarmStartCandidate,
    canonical, digest,
)
from v42_b3_joint.dry_run import (
    FakeBackend, fixture_aidc, fixture_authority, fixture_mess, make_result,
)
from v42_b3_joint.handoff import next_request
from v42_b3_joint.pipeline import MockPipeline
from v42_b3_joint.planning import (
    FrozenPlan, freeze_mock_plan, mock_actual, mock_fresh_ac, mock_validation,
)
from v42_b3_joint.validation import verify_physical, verify_stage
from v42_b3_joint.schema import validate_schema_packet
from v42_b3_joint.verify_preparation import handoff_schema


def changed_matrix(matrix, *, row=0, col=0, value=999):
    detached = [list(values) for values in matrix]
    detached[row][col] = value
    return detached


class B3SyntheticFixture(unittest.TestCase):
    def setUp(self):
        self.authority = fixture_authority()
        self.aidc = fixture_aidc()
        self.mess = fixture_mess()

    def request(self, stage="A1", **kwargs):
        if stage.startswith("M"):
            kwargs.setdefault("fixed_aidc", self.aidc)
        if stage == "A2":
            kwargs.setdefault("fixed_mess", self.mess)
        return StageRequest(stage, self.authority, **kwargs)

    def result(self, request=None):
        request = request or self.request()
        budget = MockNativeBudget(request.stage)
        result = FakeBackend().execute(request, budget)
        return request, result, budget

    def rejected_certificate(self, **changes):
        request, result, _ = self.result()
        result = replace(result, certificate=replace(result.certificate, **changes))
        with self.assertRaises(ValueError):
            verify_certificate(request, result)


class ContractAxesAndHashesTests(B3SyntheticFixture):
    def test_all_original_interface_axes_are_present(self):
        for value in (self.aidc.it_power, self.aidc.pcc_p, self.aidc.pcc_q):
            self.assertEqual((len(value), len(value[0])), (12, 96))
        for value in (self.mess.location, self.mess.charge_p, self.mess.discharge_p,
                      self.mess.q, self.mess.move_energy):
            self.assertEqual((len(value), len(value[0])), (4, 96))
        self.assertEqual((len(self.mess.soc), len(self.mess.soc[0])), (4, 97))
        self.assertEqual(self.authority.slots, tuple(range(96)))

    def test_axis_transposes_and_missing_slots_fail(self):
        for key in ("it_power", "pcc_p", "pcc_q"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(self.aidc, **{key: tuple(zip(*getattr(self.aidc, key)))})
        for key in ("location", "charge_p", "discharge_p", "q", "move_energy", "soc"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(self.mess, **{key: [list(row[:-1]) for row in getattr(self.mess, key)]})

    def test_nonfinite_and_boolean_decision_numbers_fail(self):
        for value in (float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.aidc, pcc_p=changed_matrix(self.aidc.pcc_p, value=value))
            with self.subTest(mess_value=value), self.assertRaises(ValueError):
                replace(self.mess, q=changed_matrix(self.mess.q, value=value))

    def test_frozen_decisions_detach_mutable_caller_arrays(self):
        rows = [list(row) for row in self.aidc.pcc_p]
        decision = replace(self.aidc, pcc_p=rows)
        initial_sha = decision.sha
        rows[0][0] += 123
        self.assertEqual(decision.sha, initial_sha)
        self.assertNotEqual(rows[0][0], decision.pcc_p[0][0])
        locations = [list(row) for row in self.mess.location]
        mess = replace(self.mess, location=locations)
        initial_sha = mess.sha
        locations[0][0] = "changed-site"
        self.assertEqual(mess.sha, initial_sha)
        with self.assertRaises(FrozenInstanceError):
            decision.jobs_json = canonical({"changed": True})

    def test_authority_detaches_axis_lists_and_rejects_duplicates(self):
        pcc_ids = list(self.authority.pcc_ids)
        authority = replace(self.authority, pcc_ids=pcc_ids)
        before = authority.sha
        pcc_ids[0] = "outside-pcc"
        self.assertEqual(authority.sha, before)
        for changes in ({"pcc_ids": ("same",) * 12}, {"mess_ids": ("same",) * 4},
                        {"slots": tuple(range(95))}, {"slots": (True,) + tuple(range(1, 96))}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.authority, **changes)

    def test_aidc_hash_covers_jobs_runtime_and_all_power_axes(self):
        for key in ("it_power", "pcc_p", "pcc_q"):
            with self.subTest(key=key):
                altered = replace(self.aidc, **{key: changed_matrix(getattr(self.aidc, key))})
                self.assertNotEqual(altered.sha, self.aidc.sha)
        for key in ("jobs_json", "gpu_runtime_json", "variables_json"):
            payload = json.loads(getattr(self.aidc, key))
            payload["auxiliary_test_marker"] = "changed-full-decision"
            with self.subTest(key=key):
                self.assertNotEqual(replace(self.aidc, **{key: canonical(payload)}).sha, self.aidc.sha)

    def test_mess_hash_covers_route_location_power_soc_and_auxiliaries(self):
        for key in ("charge_p", "discharge_p", "q", "soc", "move_energy"):
            with self.subTest(key=key):
                altered = replace(self.mess, **{key: changed_matrix(getattr(self.mess, key))})
                self.assertNotEqual(altered.sha, self.mess.sha)
        self.assertNotEqual(replace(self.mess, location=changed_matrix(self.mess.location, value="elsewhere")).sha, self.mess.sha)
        routes = [list(row) for row in self.mess.routes]
        routes[0].append("changed-route-edge")
        self.assertNotEqual(replace(self.mess, routes=routes).sha, self.mess.sha)
        for key in ("initial_final_json", "variables_json"):
            payload = json.loads(getattr(self.mess, key))
            payload["auxiliary_test_marker"] = 2
            with self.subTest(key=key):
                self.assertNotEqual(replace(self.mess, **{key: canonical(payload)}).sha, self.mess.sha)

    def test_q_only_mess_payload_and_empty_routes_fail(self):
        for changes in ({"variables_json": canonical({"Q": []})}, {"routes": ((),) * 4},
                        {"initial_final_json": canonical({"initial": []})}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.mess, **changes)

    def test_job_and_resource_authority_fields_are_required(self):
        for changes in ({"jobs_json": canonical({"known_job_actions": []})},
                        {"gpu_runtime_json": canonical({"gpu": []})},
                        {"variables_json": "{}"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.aidc, **changes)

    def test_future_actual_and_noncausal_forecast_are_rejected(self):
        invalid = ({"actual_observations_used": True},
                   {"forecast_available_at": "2025-05-24T00:00:00+09:00"},
                   {"planning_cutoff": "2025-05-23T00:00:00+09:00"},
                   {"planning_cutoff": "2025-05-22T23:30:00-05:00"},
                   {"planning_cutoff": "2025-05-22T23:00:00"})
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.authority, **changes)

    def test_every_authority_sha_is_required_and_bound_into_identity(self):
        for key in ("input_sha", "grid_sha", "pcc_mapping_sha", "physical_domain_sha",
                    "forecast_sha", "runtime_sha", "source_sha"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(self.authority, **{key: "historical-sha"})
            self.assertNotEqual(replace(self.authority, **{key: digest({"different": key})}).sha, self.authority.sha)

    def test_json_payloads_are_canonical_and_reject_nonfinite_values(self):
        payload = json.loads(self.aidc.variables_json)
        pretty = json.dumps(payload, indent=2)
        self.assertEqual(replace(self.aidc, variables_json=pretty).sha, self.aidc.sha)
        with self.assertRaises(ValueError):
            replace(self.aidc, variables_json='{"bad":NaN}')


class P1GapCertificateTests(B3SyntheticFixture):
    def test_stage_specific_p1_policy(self):
        for stage in policy.STAGES[:4]:
            config = policy.parameters(stage)
            self.assertEqual(config["MIPGap"], .005 if stage.startswith("A") else .03)
            self.assertEqual(config["objective"], "min rho_max")
            self.assertEqual(config["Threads"], 1)
            self.assertEqual(config["P2_calls"], 0)
            self.assertEqual(config["native_limit_seconds"], 5400)
            self.assertIsNone(config["wall_limit_seconds"])
        with self.assertRaises(ValueError):
            policy.parameters("ACTUAL")

    def test_exact_boundary_gap_is_accepted_but_excess_is_rejected(self):
        for stage in policy.STAGES[:4]:
            request, result, _ = self.result(self.request(stage))
            lower = "199/200" if stage.startswith("A") else "97/100"
            certificate = replace(result.certificate, lower_bound=lower, upper_bound="1")
            outcome = verify_certificate(request, replace(result, certificate=certificate))
            self.assertEqual(Fraction(outcome["gap_exact"]), policy.gap_target(stage))
            certificate = replace(certificate, lower_bound="994999/1000000" if stage.startswith("A") else "969999/1000000")
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                verify_certificate(request, replace(result, certificate=certificate))

    def test_m_stage_three_percent_does_not_inherit_a_half_percent(self):
        for stage in ("M1", "M2"):
            request, result, _ = self.result(self.request(stage))
            certificate = replace(result.certificate, lower_bound="98/100", upper_bound="1")
            self.assertEqual(verify_certificate(request, replace(result, certificate=certificate))["gap_exact"], "1/50")

    def test_zero_objective_bounds_are_handled_without_division_by_zero(self):
        request, result, _ = self.result()
        certificate = replace(result.certificate, lower_bound="0", upper_bound="0")
        self.assertEqual(verify_certificate(request, replace(result, certificate=certificate))["gap_exact"], "0")

    def test_missing_malformed_and_nonfinite_global_bounds_fail(self):
        for value in (None, "", "NaN", "Infinity", "1/0", "-1", " 1", True, 1.0):
            for key in ("lower_bound", "upper_bound"):
                with self.subTest(key=key, value=value):
                    self.rejected_certificate(**{key: value})
        self.rejected_certificate(lower_bound="2", upper_bound="1")

    def test_only_original_fixed_input_global_bound_scope_is_admitted(self):
        for scope in ("LOCAL", "RESTRICTED_MASTER", "PRICING_ONLY", "JOINT_FULL_MILP", ""):
            with self.subTest(scope=scope):
                self.rejected_certificate(bound_scope=scope)
        self.rejected_certificate(original_global_bound_verified=False)
        self.rejected_certificate(global_domain_sha=digest({"unrelated-original-domain": 1}))

    def test_certificate_provenance_rejects_stage_authority_fixed_decision_drift(self):
        self.rejected_certificate(stage="A2")
        for key in ("authority_sha", "fixed_input_sha", "decision_sha", "verifier_source_sha"):
            with self.subTest(key=key):
                self.rejected_certificate(**{key: "missing-provenance"})
        self.rejected_certificate(authority_sha=fixture_authority("2025-05-24").sha)
        self.rejected_certificate(fixed_input_sha=digest({"historical-M1": 1}))
        self.rejected_certificate(decision_sha=digest({"old-decision": 1}))
        self.rejected_certificate(original_model_sha="")

    def test_certificate_and_physical_replay_must_name_same_original_model(self):
        request, result, _ = self.result()
        physical = replace(result.physical, original_model_sha=digest({"different-original-model": 1}))
        with self.assertRaisesRegex(ValueError, "ORIGINAL_MODEL_SHA_DRIFT"):
            verify_physical(request, replace(result, physical=physical))
        with self.assertRaises(ValueError):
            verify_physical(request, replace(result, physical=replace(result.physical, original_model_sha="")))

    def test_p2_and_alternate_objectives_cannot_be_certified(self):
        for value in (1, -1, True, "0"):
            with self.subTest(p2=value):
                self.rejected_certificate(p2_calls=value)
        self.rejected_certificate(objective="min intervention")

    def test_mock_bounds_are_never_scientific_or_joint_optimality_evidence(self):
        request, result, _ = self.result()
        outcome = verify_certificate(request, result)
        self.assertEqual(outcome["evidence_kind"], "MOCK")
        self.assertIs(outcome["scientific_certified"], False)
        self.assertIs(outcome["joint_global_optimality_claim"], False)
        self.rejected_certificate(evidence_kind="REAL")

    def test_real_evidence_admission_is_closed_even_for_self_labeled_receipts(self):
        request, result, _ = self.result()
        claimed = replace(result, certificate=replace(result.certificate, evidence_kind="REAL"),
                          physical=replace(result.physical, evidence_kind="REAL"))
        for verifier in (verify_certificate, verify_physical, verify_stage):
            with self.subTest(verifier=verifier.__name__), self.assertRaises(PermissionError):
                verifier(request, claimed, evidence_kind="REAL")

    def test_missing_or_incomplete_original_physical_receipt_fails(self):
        request, result, _ = self.result()
        for receipt in (None, replace(result.physical, original_integer_physical_verified=False),
                        replace(result.physical, replay_sha=""),
                        replace(result.physical, verifier_source_sha=""),
                        replace(result.physical, stage="M1"),
                        replace(result.physical, evidence_kind="REAL"),
                        replace(result.physical, fixed_input_sha=digest({"old-anchor": 1})),
                        replace(result.physical, decision_sha=digest({"old-decision": 1}))):
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                verify_physical(request, replace(result, physical=receipt))

    def test_missing_global_certificate_fails(self):
        request, result, _ = self.result()
        with self.assertRaises(ValueError):
            verify_stage(request, replace(result, certificate=None))


class StageHandoffTests(B3SyntheticFixture):
    def test_exact_pipeline_order_and_final_a2_m2_decisions(self):
        output = MockPipeline().execute_mock(self.authority)
        self.assertEqual(output.states, policy.STAGES)
        self.assertEqual(tuple(request.stage for request in output.requests), policy.STAGES[:4])
        self.assertEqual(output.frozen.aidc_sha, output.results[2].aidc.sha)
        self.assertEqual(output.frozen.mess_sha, output.results[3].mess.sha)
        self.assertNotEqual(output.results[0].aidc.sha, output.results[2].aidc.sha)
        self.assertNotEqual(output.results[1].mess.sha, output.results[3].mess.sha)

    def test_handoffs_freeze_the_whole_upstream_decision(self):
        output = MockPipeline().execute_mock(self.authority)
        self.assertEqual(output.requests[1].fixed_aidc.sha, output.results[0].aidc.sha)
        self.assertEqual(output.results[1].aidc.sha, output.results[0].aidc.sha)
        self.assertEqual(output.requests[2].fixed_mess.sha, output.results[1].mess.sha)
        self.assertEqual(output.results[2].mess.sha, output.results[1].mess.sha)
        self.assertEqual(output.requests[3].fixed_aidc.sha, output.results[2].aidc.sha)
        self.assertEqual(output.results[3].aidc.sha, output.results[2].aidc.sha)
        self.assertIsNone(output.requests[0].fixed_aidc)
        self.assertIsNone(output.requests[0].fixed_mess)
        self.assertIsNone(output.results[0].mess)

    def test_m_stage_cannot_change_fixed_jobs_even_if_power_is_identical(self):
        for stage in ("M1", "M2"):
            request, result, budget = self.result(self.request(stage))
            payload = json.loads(result.aidc.jobs_json)
            payload["fixed_job_mutation"] = True
            changed = replace(result.aidc, jobs_json=canonical(payload))
            forged = make_result(request, budget, changed, result.mess)
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "FIXED_AIDC"):
                verify_stage(request, forged, budget=budget)

    def test_a2_cannot_change_fixed_routes_even_if_p_q_are_identical(self):
        request, result, budget = self.result(self.request("A2"))
        routes = [list(row) for row in result.mess.routes]
        routes[0].append("unauthorized-route")
        forged = make_result(request, budget, result.aidc, replace(result.mess, routes=routes))
        with self.assertRaisesRegex(ValueError, "FIXED_MESS"):
            verify_stage(request, forged, budget=budget)

    def test_cross_day_input_grid_mapping_and_forecast_authority_fail(self):
        request, result, _ = self.result()
        variations = ({"day": "2025-05-24"}, {"input_sha": digest({"another-input": 1})},
                      {"grid_sha": digest({"another-feeder": 1})},
                      {"pcc_mapping_sha": digest({"another-mapping": 1})},
                      {"forecast_sha": digest({"another-forecast": 1})},
                      {"runtime_sha": digest({"another-runtime": 1})})
        for changes in variations:
            other_request = replace(request, authority=replace(self.authority, **changes))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                next_request(other_request, result)

    def test_stage_requests_reject_wrong_fixed_variable_families(self):
        invalid = (("A1", {"fixed_mess": self.mess}), ("A1", {"fixed_aidc": self.aidc}),
                   ("M1", {}), ("A2", {}), ("M2", {"fixed_aidc": self.aidc, "fixed_mess": self.mess}),
                   ("ACTUAL", {}))
        for stage, kwargs in invalid:
            with self.subTest(stage=stage, kwargs=kwargs), self.assertRaises(ValueError):
                StageRequest(stage, self.authority, **kwargs)

    def test_m2_includes_all_movement_power_and_soc_variables(self):
        output = MockPipeline().execute_mock(self.authority)
        decision = output.results[3].mess
        self.assertEqual(len(decision.routes), 4)
        self.assertTrue({"movement", "charge_mode", "route", "P", "Q", "SOC"} <= set(json.loads(decision.variables_json)))
        binding = prepare_source_binding(output.requests[3]).payload()
        for family in ("movement", "route", "location", "Pch", "Pdis", "Q", "SOC", "charge_mode"):
            self.assertIn(family, binding["optimized_families"])

    def test_m1_warm_start_candidate_is_distinct_from_new_anchor_feasibility(self):
        output = MockPipeline().execute_mock(self.authority)
        candidate = output.requests[3].warm_start
        self.assertIs(candidate.eligible, False)
        self.assertIs(candidate.feasibility_verified, False)
        self.assertEqual(candidate.mess.sha, output.results[1].mess.sha)
        self.assertEqual(candidate.fixed_aidc_sha, output.results[2].aidc.sha)
        for invalid in (replace(candidate, eligible=True),
                        replace(candidate, authority_sha=fixture_authority("2025-05-24").sha),
                        replace(candidate, eligible=True, feasibility_verified=True, fixed_aidc_sha=output.results[0].aidc.sha)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                replace(output.requests[3], warm_start=invalid)
        valid = replace(candidate, eligible=True, feasibility_verified=True)
        accepted_request = replace(output.requests[3], warm_start=valid)
        self.assertTrue(accepted_request.warm_start.eligible)
        warm_payload = prepare_source_binding(accepted_request).payload()["warm_start"]
        self.assertIs(warm_payload["selected_for_future_native"], False)
        self.assertEqual(warm_payload["actual_feasibility_status"], "NOT_RUN")
        self.assertEqual(warm_payload["evidence_kind"], "MOCK")

    def test_warm_start_claims_reject_string_integer_and_missing_boolean_types(self):
        candidate = WarmStartCandidate(self.authority.sha, self.aidc.sha, self.mess,
                                       eligible=False, feasibility_verified=False,
                                       reason="SYNTHETIC_TEST_ONLY_NOT_RUN")
        for key in ("eligible", "feasibility_verified"):
            for value in ("true", "false", 1, 0, None):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    replace(candidate, **{key: value})

    def test_failed_stage_blocks_every_successor_and_planning_freeze(self):
        for bad_stage in policy.STAGES[:4]:
            backend = FakeBackend(faults={bad_stage: "MISSING_LB"})
            pipeline = MockPipeline(backend=backend)
            with self.subTest(bad_stage=bad_stage), self.assertRaises(ValueError):
                pipeline.execute_mock(self.authority)
            self.assertEqual(pipeline.state, "FAILED")
            self.assertNotIn("PLANNING_FREEZE", pipeline.completed_stages)
            self.assertEqual(backend.calls, list(policy.STAGES[:policy.STAGES.index(bad_stage) + 1]))
            previous_calls = tuple(backend.calls)
            with self.assertRaises((ValueError, RuntimeError, PermissionError)):
                pipeline.execute_mock(self.authority)
            self.assertEqual(tuple(backend.calls), previous_calls)

    def test_builtin_mutation_and_missing_physical_faults_stop_pipeline(self):
        cases = (("M1", "MUTATE_AIDC"), ("A2", "MUTATE_MESS"),
                 ("M2", "MUTATE_AIDC"), ("A1", "P2"), ("M2", "MISSING_PHYSICAL"))
        for stage, fault in cases:
            backend = FakeBackend(faults={stage: fault})
            pipeline = MockPipeline(backend=backend)
            with self.subTest(stage=stage, fault=fault), self.assertRaises(ValueError):
                pipeline.execute_mock(self.authority)
            self.assertEqual(pipeline.state, "FAILED")
            self.assertEqual(backend.calls[-1], stage)
            self.assertNotIn("PLANNING_FREEZE", pipeline.completed_stages)

    def test_no_optimization_successor_exists_after_m2(self):
        output = MockPipeline().execute_mock(self.authority)
        with self.assertRaises(ValueError):
            next_request(output.requests[-1], output.results[-1])

    def test_freeze_rechecks_each_stage_and_frozen_identity(self):
        output = MockPipeline().execute_mock(self.authority)
        results = list(output.results)
        results[-1] = replace(results[-1], authority=fixture_authority("2025-05-24"))
        with self.assertRaises(ValueError):
            freeze_mock_plan(output.requests, results)
        with self.assertRaises(ValueError):
            freeze_mock_plan(output.requests[:-1], output.results[:-1])
        results = list(output.results)
        results[1] = replace(results[1], physical=None)
        with self.assertRaises(ValueError):
            freeze_mock_plan(output.requests, results)


class MockRuntimeLedgerTests(unittest.TestCase):
    def test_four_independent_native_only_5400_second_ledgers(self):
        ledgers = [MockNativeBudget(stage) for stage in policy.STAGES[:4]]
        ledgers[0].simulate(5400)
        self.assertEqual(ledgers[0].remaining, 0)
        self.assertEqual([ledger.remaining for ledger in ledgers[1:]], [5400] * 3)
        ledgers[1].simulate(25, kind="LP")
        self.assertEqual(ledgers[2].remaining, 5400)
        self.assertEqual(ledgers[3].remaining, 5400)
        with self.assertRaises(TimeoutError):
            ledgers[0].simulate(0)
        for ledger in ledgers:
            receipt = ledger.receipt()
            self.assertEqual(receipt["native_limit_seconds"], 5400)
            self.assertEqual(receipt["real_native_optimize_calls"], 0)
            self.assertEqual(receipt["P2_calls"], 0)
            self.assertEqual(receipt["Threads"], 1)

    def test_build_physical_matrix_certificate_actual_fresh_costs_excluded(self):
        clock = MockClock()
        ledger = MockNativeBudget("A2", clock=clock)
        for kind in ("MODEL_BUILD", "PHYSICAL_DOMAIN", "MATRIX", "CERTIFICATION", "ACTUAL", "FRESH_AC"):
            ledger.record_non_native(kind, 6000)
        self.assertEqual(ledger.used, 0)
        self.assertEqual(ledger.remaining, 5400)
        ledger.simulate(10)
        self.assertEqual(ledger.used, 10)
        self.assertEqual(ledger.receipt()["wall_seconds"], 36010)
        self.assertIsNone(ledger.receipt()["wall_limit_seconds"])

    def test_lp_pricing_qcp_milp_and_failed_entered_call_all_charge_runtime(self):
        ledger = MockNativeBudget("M1")
        for kind in ("LP", "PRICING", "QCP", "MILP"):
            ledger.simulate(5, kind=kind, failed=kind == "MILP")
        self.assertEqual(ledger.used, 20)
        self.assertEqual([row["effective_TimeLimit"] for row in ledger.receipt()["calls"]], [5400, 5395, 5390, 5385])
        self.assertIs(ledger.receipt()["calls"][-1]["failed"], True)

    def test_unknown_negative_nonfinite_or_boolean_runtime_quarantines_ledger(self):
        for value in (None, -1, float("inf"), float("nan"), True, "10"):
            ledger = MockNativeBudget("A1")
            ledger.simulate(10)
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                ledger.simulate(value)
            self.assertIs(ledger.receipt()["quarantined"], True)
            self.assertEqual(ledger.used, 10)
            with self.assertRaises(RuntimeError):
                ledger.simulate(1)

    def test_runtime_overrun_is_retained_and_never_reset_or_transferred(self):
        ledger = MockNativeBudget("M2")
        with self.assertRaises(TimeoutError):
            ledger.simulate(5401, failed=True)
        self.assertEqual(ledger.used, 5401)
        self.assertEqual(ledger.remaining, 0)
        with self.assertRaises(TimeoutError):
            ledger.simulate(0)
        with self.assertRaises(AttributeError):
            ledger.stage = "A1"

    def test_mock_budget_accepts_no_solver_clock_callback_or_p2_kind(self):
        with self.assertRaises(ValueError):
            MockNativeBudget("A1", clock=lambda: 0)
        ledger = MockNativeBudget("A1")
        with self.assertRaises(ValueError):
            ledger.simulate(0, kind="P2")
        with self.assertRaises(ValueError):
            ledger.record_non_native("NATIVE", 1)
        with self.assertRaises(TypeError):
            ledger.simulate(0, callback=lambda: None)

    def test_receipt_is_detached_and_cannot_rewrite_charged_runtime(self):
        ledger = MockNativeBudget("A1")
        ledger.simulate(3)
        receipt = ledger.receipt()
        receipt["calls"][0]["Runtime"] = 0
        receipt["simulated_native_runtime"] = 0
        self.assertEqual(ledger.used, 3)
        self.assertEqual(ledger.receipt()["calls"][0]["Runtime"], 3)

    def test_invalid_mock_clock_elapsed_is_rejected(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MockClock().advance(value)


class NativeReceiptProvenanceTests(B3SyntheticFixture):
    def test_tampered_native_receipt_fails_its_cumulative_and_policy_checks(self):
        request, result, _ = self.result()
        changes = ({"stage": "M1"}, {"native_limit_seconds": 21600},
                   {"wall_limit_seconds": 5400}, {"P2_calls": 1}, {"Threads": 2},
                   {"real_native_optimize_calls": 1}, {"quarantined": True},
                   {"simulated_native_runtime": 0}, {"remaining_seconds": 0},
                   {"simulated_calls": 999}, {"evidence_kind": "REAL"})
        for changeset in changes:
            receipt = json.loads(result.native_receipt)
            receipt.update(changeset)
            with self.subTest(changes=changeset), self.assertRaises(ValueError):
                verify_stage(request, replace(result, native_receipt=canonical(receipt)))

    def test_backend_cannot_substitute_another_independent_ledger(self):
        request, result, budget = self.result()
        verify_stage(request, result, budget=budget)
        other = MockNativeBudget("A1")
        other.bind(request)
        with self.assertRaisesRegex(ValueError, "LEDGER_SUBSTITUTION"):
            verify_stage(request, result, budget=other)

    def test_same_stage_ledger_rejects_another_day_or_fixed_anchor(self):
        request, result, _ = self.result(self.request("M1"))
        for other_request in (replace(request, authority=fixture_authority("2025-05-24")),
                              replace(request, fixed_aidc=fixture_aidc(2))):
            _, other_result, _ = self.result(other_request)
            with self.subTest(other_sha=other_request.fixed_input_sha), self.assertRaisesRegex(ValueError, "LEDGER_INPUT_IDENTITY"):
                verify_stage(request, replace(result, native_receipt=other_result.native_receipt))

    def test_bound_ledger_cannot_rebind_after_costs_or_to_another_request(self):
        request = self.request("M1")
        ledger = MockNativeBudget("M1")
        ledger.bind(request)
        ledger.simulate(1)
        ledger.bind(request)
        with self.assertRaisesRegex(ValueError, "REBIND"):
            ledger.bind(replace(request, fixed_aidc=fixture_aidc(2)))
        unbound = MockNativeBudget("M1")
        unbound.simulate(1)
        with self.assertRaisesRegex(ValueError, "LATE_BIND"):
            unbound.bind(request)

    def test_native_call_runtime_and_effective_remaining_cannot_be_fabricated(self):
        request, result, _ = self.result()
        for key, value in (("Runtime", None), ("Runtime", -1), ("Runtime", True),
                           ("runtime_unavailable", True), ("effective_TimeLimit", 100),
                           ("kind", "P2")):
            receipt = json.loads(result.native_receipt)
            self.assertTrue(receipt["calls"])
            receipt["calls"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify_stage(request, replace(result, native_receipt=canonical(receipt)))

    def test_native_receipt_threads_and_call_failed_require_exact_types(self):
        request, result, _ = self.result()
        receipt = json.loads(result.native_receipt)
        receipt["Threads"] = True
        with self.assertRaises(ValueError):
            verify_stage(request, replace(result, native_receipt=canonical(receipt)))
        for value in (1, 0, "false", None):
            receipt = json.loads(result.native_receipt)
            receipt["calls"][0]["failed"] = value
            with self.subTest(failed=value), self.assertRaises(ValueError):
                verify_stage(request, replace(result, native_receipt=canonical(receipt)))

    def test_native_receipt_cannot_append_zero_runtime_call_after_exhaustion(self):
        request = self.request()
        budget = MockNativeBudget("A1")
        budget.bind(request)
        budget.simulate(5400)
        result = make_result(request, budget, self.aidc, None)
        verify_stage(request, result)
        receipt = json.loads(result.native_receipt)
        receipt["calls"].append({"Runtime": 0, "effective_TimeLimit": 0,
                                 "kind": "MILP", "failed": False,
                                 "runtime_unavailable": False})
        receipt["simulated_calls"] += 1
        with self.assertRaisesRegex(ValueError, "LEDGER_REMAINING_LIMIT"):
            verify_stage(request, replace(result, native_receipt=canonical(receipt)))


class EmittedSchemaShapeTests(B3SyntheticFixture):
    def packet(self):
        request, result, _ = self.result(self.request("M1"))
        return json.loads(canonical({"request": asdict(request), "result": asdict(result)}))

    def test_emitted_schema_validates_all_four_mock_stage_packets(self):
        output = MockPipeline().execute_mock(self.authority)
        schema = handoff_schema()
        stages = []
        for request, result in zip(output.requests, output.results):
            packet = json.loads(canonical({"request": asdict(request), "result": asdict(result)}))
            outcome = validate_schema_packet(schema, packet)
            self.assertEqual(outcome["validator_scope"], "ONLY_EMITTED_SCHEMA_SUBSET")
            self.assertIs(outcome["general_draft_2020_12_validator"], False)
            self.assertIs(outcome["scientific_certified"], False)
            stages.append(packet["request"]["stage"])
        self.assertEqual(stages, list(policy.STAGES[:4]))

    def test_emitted_schema_rejects_wrong_aidc_mess_and_soc_axes(self):
        for parent, key in (("aidc", "pcc_p"), ("aidc", "pcc_q"),
                            ("mess", "location"), ("mess", "charge_p"),
                            ("mess", "discharge_p"), ("mess", "q"), ("mess", "soc")):
            packet = self.packet()
            packet["result"][parent][key][0].pop()
            with self.subTest(parent=parent, key=key), self.assertRaises(ValueError):
                validate_schema_packet(handoff_schema(), packet)

    def test_emitted_schema_rejects_null_global_lb_or_ub(self):
        for key in ("lower_bound", "upper_bound"):
            packet = self.packet()
            packet["result"]["certificate"][key] = None
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_schema_packet(handoff_schema(), packet)

    def test_emitted_schema_rejects_unrequested_top_and_nested_fields(self):
        for location in ((), ("request",), ("request", "authority"),
                         ("result", "certificate"), ("result", "mess")):
            packet = self.packet()
            destination = packet
            for key in location:
                destination = destination[key]
            destination["unexpected_field"] = True
            with self.subTest(location=location), self.assertRaises(ValueError):
                validate_schema_packet(handoff_schema(), packet)

    def test_emitted_schema_rejects_boolean_numeric_values_and_integer_consts(self):
        for parent, key in (("aidc", "pcc_p"), ("mess", "soc")):
            packet = self.packet()
            packet["result"][parent][key][0][0] = True
            with self.subTest(parent=parent), self.assertRaises(ValueError):
                validate_schema_packet(handoff_schema(), packet)
        packet = self.packet()
        packet["result"]["certificate"]["p2_calls"] = False
        with self.assertRaises(ValueError):
            validate_schema_packet(handoff_schema(), packet)
        packet = self.packet()
        packet["request"]["authority"]["slots"][0] = False
        with self.assertRaises(ValueError):
            validate_schema_packet(handoff_schema(), packet)

    def test_emitted_schema_rejects_actual_future_flag_and_bad_identity_or_date(self):
        for key, value in (("actual_observations_used", True), ("input_sha", "old-SHA"),
                           ("day", "2025-02-30"), ("planning_cutoff", "2025-05-22T18:00:00")):
            packet = self.packet()
            packet["request"]["authority"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_schema_packet(handoff_schema(), packet)

    def test_emitted_schema_rejects_duplicate_physical_axis_ids(self):
        for key in ("pcc_ids", "mess_ids"):
            packet = self.packet()
            packet["request"]["authority"][key][1] = packet["request"]["authority"][key][0]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_schema_packet(handoff_schema(), packet)

    def test_schema_validator_rejects_unsupported_assertion_keywords(self):
        for keyword, assertion in (("minimum", 0), ("maximum", 10), ("multipleOf", 1)):
            with self.subTest(keyword=keyword), self.assertRaises(ValueError):
                validate_schema_packet({"type": "number", keyword: assertion}, 1)
        with self.assertRaises(ValueError):
            validate_schema_packet({"type": "object", "maxProperties": 2}, {})

    def test_shape_validation_does_not_replace_exact_gap_or_causal_semantics(self):
        request, result, _ = self.result(self.request("M1"))
        bad = replace(result, certificate=replace(result.certificate, lower_bound="0", upper_bound="1"))
        packet = json.loads(canonical({"request": asdict(request), "result": asdict(bad)}))
        validate_schema_packet(handoff_schema(), packet)
        with self.assertRaisesRegex(ValueError, "GLOBAL_GAP"):
            verify_stage(request, bad)


class PlanningAndExecutionProtectionTests(B3SyntheticFixture):
    def test_actual_forbids_every_repair_and_full_reoptimization_path(self):
        output = MockPipeline().execute_mock(self.authority)
        for key in ("local_p_repair", "local_q_repair", "full_reoptimization"):
            with self.subTest(key=key), self.assertRaises((PermissionError, ValueError)):
                mock_actual(output.frozen, **{key: True})

    def test_actual_replay_rejects_a_changed_frozen_decision(self):
        output = MockPipeline().execute_mock(self.authority)
        changed = output.frozen.document
        changed = changed["plan"]
        changed["aidc"]["pcc_p"][0][0] += 1
        with self.assertRaises(ValueError):
            mock_actual(output.frozen, replay_plan=changed)

    def test_frozen_document_is_detached_and_cannot_change_freeze_hash(self):
        output = MockPipeline().execute_mock(self.authority)
        before = output.frozen.sha
        detached = output.frozen.document
        detached["mutated_detached_document"] = True
        self.assertEqual(output.frozen.sha, before)
        self.assertNotIn("mutated_detached_document", output.frozen.document)
        output.frozen.verify()

    def test_rehashed_freeze_cannot_fabricate_stage_bound_or_physical_receipts(self):
        output = MockPipeline().execute_mock(self.authority)
        for key in ("lower_bound", "p2_calls", "original_global_bound_verified"):
            document = output.frozen.document
            certificate = document["plan"]["stage_records"][0]["result"]["certificate"]
            certificate[key] = {"lower_bound": None, "p2_calls": 1,
                                "original_global_bound_verified": False}[key]
            document["plan"]["source_receipts_sha"] = digest(document["plan"]["stage_records"])
            document["plan_sha"] = digest(document["plan"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                FrozenPlan(canonical(document))
        document = output.frozen.document
        document["plan"]["stage_records"][3]["result"]["physical"]["original_integer_physical_verified"] = False
        document["plan"]["source_receipts_sha"] = digest(document["plan"]["stage_records"])
        document["plan_sha"] = digest(document["plan"])
        with self.assertRaises(ValueError):
            FrozenPlan(canonical(document))

    def test_arbitrary_backend_injection_is_rejected_before_execution(self):
        class ForbiddenBackend:
            def execute(self, request, budget):
                raise AssertionError("arbitrary backend was executed")

        class ForbiddenFakeSubclass(FakeBackend):
            def execute(self, request, budget):
                raise AssertionError("arbitrary subclass was executed")

        for backend in (ForbiddenBackend(), ForbiddenFakeSubclass()):
            with self.subTest(backend=type(backend).__name__), self.assertRaises(ValueError):
                MockPipeline(backend=backend)

    def test_mock_post_freeze_receipts_are_not_actual_or_opendss_execution(self):
        output = MockPipeline().execute_mock(self.authority)
        actual = json.loads(output.actual_json)
        fresh = json.loads(output.fresh_json)
        validation = json.loads(output.validation_json)
        for receipt in (actual, fresh, validation):
            self.assertEqual(receipt["evidence_kind"], "MOCK")
        self.assertIs(fresh["fresh_AC_executed"], False)
        self.assertEqual(fresh["OpenDSS_calls"], 0)
        self.assertIs(validation["scientific_certified"], False)
        self.assertIs(policy.B3_FRESH_AC_EXECUTED, False)

    def test_post_freeze_receipts_cannot_be_reused_for_another_freeze(self):
        first = MockPipeline().execute_mock(self.authority)
        other = MockPipeline().execute_mock(fixture_authority("2025-05-24"))
        with self.assertRaises(ValueError):
            mock_fresh_ac(other.frozen, first.actual_json)
        with self.assertRaises(ValueError):
            mock_validation(other.frozen, other.actual_json, first.fresh_json)

    def test_environment_and_mutable_flags_cannot_authorize_production(self):
        env = {"B3_NATIVE_EXECUTION_AUTHORIZED": "true", "B3_PRODUCTION_CAMPAIGN_STARTED": "1",
               "V42_NATIVE_EXECUTION_AUTHORIZED": "true", "B1_B2_NATIVE_ALLOWED": "1"}
        with patch.dict(os.environ, env), patch.object(policy, "B3_NATIVE_EXECUTION_AUTHORIZED", True):
            for action in ("NATIVE", "MODEL_BUILD", "PRICING", "OPEN_DSS", "WORKER", "COORDINATOR", "FRESH_AC"):
                with self.subTest(action=action), self.assertRaises(PermissionError):
                    policy.require_production_authorization(action)

    def test_production_entries_have_unconditional_preimport_guard_by_ast(self):
        # The user forbids calling production run/start/optimize entries during
        # preparation. Inspect their first statements without invoking them.
        package = Path(__file__).resolve().parents[1] / "v42_b3_joint"
        targets = (("budget.py", "NativeStageBudget", "native_optimize"),
                   ("adapters.py", "NativeStageAdapter", "execute"),
                   ("pipeline.py", None, "run_production"))
        for filename, owner, symbol in targets:
            tree = ast.parse((package / filename).read_text(encoding="utf-8-sig"))
            scope = tree if owner is None else next(node for node in tree.body
                                                    if isinstance(node, ast.ClassDef) and node.name == owner)
            definition = next(node for node in scope.body if isinstance(node, ast.FunctionDef) and node.name == symbol)
            statements = list(definition.body)
            if isinstance(statements[0], ast.Expr) and isinstance(statements[0].value, ast.Constant):
                statements = statements[1:]
            first = statements[0]
            with self.subTest(filename=filename, symbol=symbol):
                self.assertIsInstance(first, ast.Expr)
                self.assertIsInstance(first.value, ast.Call)
                self.assertIsInstance(first.value.func, ast.Name)
                self.assertEqual(first.value.func.id, "require_production_authorization")

    def test_mock_pipeline_performs_no_file_or_active_ledger_write(self):
        # Real B1/B2 file/ledger immutability is additionally audited externally.
        # This test proves the synthetic pipeline has no filesystem write path.
        with patch("builtins.open", side_effect=AssertionError("mock filesystem access")), \
             patch.object(Path, "write_text", side_effect=AssertionError("mock file write")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("mock file write")):
            output = MockPipeline().execute_mock(self.authority)
        self.assertEqual(len(output.results), 4)
        for ledger in output.ledgers:
            self.assertEqual(ledger["real_native_optimize_calls"], 0)

    def test_source_binding_axis_permutations_preserve_values_and_full_locks(self):
        output = MockPipeline().execute_mock(self.authority)
        m_payload = prepare_source_binding(output.requests[1]).payload()
        a_payload = prepare_source_binding(output.requests[2]).payload()
        fixed_aidc = m_payload["fixed_aidc"]
        self.assertEqual(fixed_aidc["decision_sha"], output.results[0].aidc.sha)
        self.assertEqual(fixed_aidc["AIDC_decision_variables"], 0)
        self.assertIs(fixed_aidc["allowed_to_change"], False)
        self.assertEqual(fixed_aidc["planning_fields"]["PCC_P_kw"], [list(column) for column in zip(*output.results[0].aidc.pcc_p)])
        fixed_mess = a_payload["fixed_mess"]
        self.assertEqual(fixed_mess["decision_sha"], output.results[1].mess.sha)
        self.assertEqual(fixed_mess["MESS_decision_variables"], 0)
        self.assertIs(fixed_mess["allowed_to_change"], False)
        self.assertEqual(len(fixed_mess["unit_slot_source_families"]["SOC_kwh"]), 97)
        self.assertEqual(fixed_mess["unit_slot_source_families"]["SOC_kwh"][0], [row[0] for row in output.results[1].mess.soc])

    def test_source_bindings_keep_native_construction_explicitly_deferred(self):
        output = MockPipeline().execute_mock(self.authority)
        for request in output.requests:
            binding = prepare_source_binding(request)
            payload = binding.payload()
            self.assertTrue(binding.unresolved_interfaces)
            self.assertIs(payload["source_payload_ready_for_native_build"], False)
            self.assertIs(payload["preparation_only"], True)
            for key in ("native_calls", "model_builds", "pricing_calls", "physical_domain_builds", "OpenDSS_calls", "P2_calls"):
                self.assertEqual(payload[key], 0)
            payload["stage"] = "modified-detached-descriptor"
            self.assertEqual(binding.payload()["stage"], request.stage)

    def test_preparation_package_has_no_real_solver_or_legacy_module_import(self):
        package = Path(__file__).resolve().parents[1] / "v42_b3_joint"
        for source in package.glob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module or ""]
                else:
                    continue
                for module in modules:
                    with self.subTest(source=source.name, module=module):
                        self.assertFalse(module.startswith(("gurobipy", "opendss", "win32com", "v42_native", "v42_a_stage", "v42_m1", "v42_may")))
        self.assertNotIn("gurobipy", sys.modules)
        self.assertNotIn("win32com.client", sys.modules)


if __name__ == "__main__":
    unittest.main()
