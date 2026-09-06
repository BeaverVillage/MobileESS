"""Production promotion/equivalence tests; no optimization or campaign calls."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from dayahead.v39e import temporal_refreeze as p
from dayahead.v39e import runtime
from dayahead.v39e import campaign
from dayahead.v39e.campaign_adapter import build_day
from dayahead.v39c.freeze import sha256_file
from dayahead.v38.authority import canonical_sha256

REPO=Path(__file__).resolve().parents[2]


class RuntimeTests(unittest.TestCase):
    def test_fixed_candidate_four_threads_changes_only_runtime(self):
        params=SimpleNamespace(Threads=1,Seed=20260828,FeasibilityTol=1e-8)
        item=SimpleNamespace(model=SimpleNamespace(Params=params))
        with patch("dayahead.v35r3.algorithm.build_fixed_candidate_model",return_value=item) as build:
            self.assertIs(runtime.four_thread_fixed_candidate(candidate="test"),item)
            build.assert_called_once_with(candidate="test")
        self.assertEqual(params.Threads,4);self.assertEqual(params.Seed,20260828);self.assertEqual(params.FeasibilityTol,1e-8)

    def test_nested_candidate_pool_has_one_active_solver(self):
        with runtime.OneSolverPerDayPool(max_workers=9) as pool:self.assertEqual(pool._max_workers,1)
        self.assertEqual(campaign.MAX_PARALLEL_DAYS,4)

    def test_runtime_install_limits_nested_day_concurrency(self):
        from dayahead.v37 import runner
        from dayahead.tools import run_v35r3e_r1_beam as beam
        with patch.object(runner,"MAX_WORKERS_PER_DATE",runner.MAX_WORKERS_PER_DATE),patch.object(beam,"ProcessPoolExecutor",beam.ProcessPoolExecutor),patch.object(beam,"build_fixed_candidate_model",beam.build_fixed_candidate_model):
            authority=runtime.install_runtime()
            self.assertEqual(runner.MAX_WORKERS_PER_DATE,1)
            self.assertIs(beam.ProcessPoolExecutor,runtime.OneSolverPerDayPool)
            self.assertEqual(authority["max_concurrent_solver_threads"],16)

    def test_refreeze_contains_no_optimization_calls(self):
        tree=ast.parse(Path(p.__file__).read_text(encoding="utf-8"))
        forbidden={"optimize","solve_stage","plan_fixed_temporal_schedule","build_model","run_campaign"}
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ""
                self.assertNotIn(name,forbidden)


class SelectiveTests(unittest.TestCase):
    def test_only_five_dates_ten_cases_changed(self):
        root=REPO/p.CLOSE_ROOT;state=p.read(root/"PRODUCTION_CLOSE_START_STATE.json")
        impact=p.read(root/"PRODUCTION_CHANGE_IMPACT_AUDIT.json")
        self.assertEqual(impact["changed_days"],list(p.CHANGED_DAYS))
        self.assertEqual(impact["changed_day_case_count"],10)
        self.assertEqual(impact["unchanged_day_case_count"],114)
        changed=[]
        for day in p.EXPECTED_DATES:
            for case in p.CASES:
                name=f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
                if sha256_file(REPO/p.FULL_ROOT/name)!=state["before_refreeze_SHA256"][name]:changed.append((day,case))
        self.assertEqual(set(changed),{(day,case) for day in p.CHANGED_DAYS for case in ("B1","B3")})

    def test_primary_work_service_and_hard_grid_preserved(self):
        for day in p.CHANGED_DAYS:
            with self.subTest(day=day):
                proof=p.read(REPO/p.CLOSE_ROOT/"days"/day/"SELECTIVE_PREFLIGHT_CERTIFICATE.json")
                self.assertEqual(proof["status"],"PASS")
                self.assertEqual(proof["primary_optimum_GPU_slots"],p.PRIMARY[day])
                self.assertTrue(proof["primary_certificate_reused"]["optimal"])
                self.assertEqual(proof["safe_reservation_GPU_slots_before"],proof["safe_reservation_GPU_slots_after"])
                self.assertTrue(proof["safe_seconds_per_job_unchanged"])
                self.assertTrue(proof["RW_completion_noninferiority_PASS"])
                self.assertEqual(proof["new_RW_completion_violations"],0)
                audit=proof["independent_schedule_grid_audit"]
                self.assertTrue(audit["all_hard_constraints_pass"])
                for field in ("site_capacity_violations","aggregate_capacity_violations","gang_splits","rack_compatibility_failures","noneligible_time_changes","RUNNING_site_changes"):
                    self.assertEqual(audit[field],0)
                for field in ("voltage_violation_count","line_current_violation_count","transformer_current_violation_count","transformer_kva_violation_count","transformer_polygon_violation_count"):
                    self.assertEqual(audit["grid"][field],0)
                self.assertFalse(proof["secondary_changed_job_global_optimality_required"])
                self.assertFalse(proof["tertiary_delay_global_optimality_required"])
                self.assertEqual(proof["Actual_result_reads_during_DA_construction"],0)
                self.assertEqual(proof["Fresh_result_reads_during_DA_construction"],0)
                self.assertEqual(proof["primary_optimization_calls"],0)
                self.assertEqual(proof["migration_MILP_calls"],0)

    def test_frozen_production_loader_consumes_repaired_schedule(self):
        for day in p.CHANGED_DAYS:
            b=pd.read_parquet(REPO/p.CLOSE_ROOT/"days"/day/"PRODUCTION_PRIMARY_OPTIMAL_RSP_SCHEDULE.parquet")
            expected=np.zeros(96,dtype=int)
            for r in b.itertuples(index=False):
                start=max(24,r.scheduled_start_slot);end=min(120,r.scheduled_end_slot)
                if end>start:expected[start-24:end-24]+=int(r.requested_gpus)
            for case in ("B1","B3"):
                trajectory=build_day(REPO,day,case)
                np.testing.assert_array_equal(trajectory.power.N_active_GPU.to_numpy(),expected)
                freeze=p.read(REPO/p.FULL_ROOT/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json")
                self.assertEqual(canonical_sha256(freeze["decision"]),freeze["DA_decision_SHA256"])
                self.assertIsNone(freeze["decision"]["temporal_repair_authority"]["new_maximum_delay_SLA_or_deadline"])
                self.assertEqual(freeze["decision"]["migration_state"]["WAN_transfer_count"],0)

    def test_original_rsp_migration_proofs_reused_without_partial_repair(self):
        audit=p.read(REPO/p.CLOSE_ROOT/"MIGRATION_REUSE_EQUIVALENCE.json")
        self.assertEqual(len(audit["days"]),8)
        self.assertEqual(sum(r["minimum_RUNNING_migrations"] for r in audit["days"]),76)
        self.assertEqual(audit["new_migration_MILP_calls"],0)
        for row in audit["days"]:
            self.assertFalse(row["partial_infeasible_repair_passed_to_migration"])
            for name,sha in row["preserved_solver_proof_sources_SHA256"].items():self.assertEqual(sha256_file(REPO/name),sha)
            self.assertEqual(sha256_file(REPO/p.FULL_ROOT/f"V39E_DAYAHEAD_DECISION_FREEZE_{row['day']}_B1.json"),row["production_B1_DA_file_SHA256"])

    def test_may01_05_exact_result_reuse_and_immutable_files(self):
        self.assertGreater(p.assert_protected_results(REPO),20)
        for day in p.MAY01_05:
            self.assertTrue(campaign._reusable(REPO,day,"AUTHORITATIVE_V39E_MAY_CAMPAIGN"))
        reuse=p.read(REPO/p.CLOSE_ROOT/"MAY01_05_REUSE_EQUIVALENCE.json")
        self.assertTrue(reuse["source_replay_adapter_unchanged"])
        for day in reuse["days"]:
            for case in day["cases"]:
                self.assertTrue(case["exact_checkpoint_and_all_file_SHA_match"])
                self.assertEqual(case["temporal_repair_calls"],0)
                self.assertEqual(case["migration_calls"],0)

    def test_h_proofs_and_frozen_scientific_sources_untouched(self):
        state=p.read(REPO/p.CLOSE_ROOT/"PRODUCTION_CLOSE_START_STATE.json")
        for name,sha in state["V39H_required_SHA256"].items():self.assertEqual(sha256_file(REPO/p.H_ROOT/name),sha)
        allowed={"dayahead/v39e/campaign.py","dayahead/v39e/full_preflight.py","dayahead/tools/run_v39e_may_day.py"}
        for name,sha in state["production_source_SHA256"].items():
            if name not in allowed:self.assertEqual(sha256_file(REPO/name),sha,name)

    def test_cheap_readiness_is_31_without_v39i_gate(self):
        ready=p.read(REPO/p.CLOSE_ROOT/"CHEAP_31_DAY_READINESS.json")
        self.assertEqual((ready["READY"],ready["NOT_READY"],ready["MISSING"]),(31,0,0))
        self.assertEqual(ready["optimization_calls"],0)
        self.assertFalse(ready["V39I_dependency"])
        authority=p.read(REPO/p.CLOSE_ROOT/"PRODUCTION_REFREEZE_AUTHORITY.json")
        self.assertFalse(authority["V39I_dependency"])
        self.assertEqual(authority["MAX_PARALLEL_DAY_WORKERS"],4)
        self.assertEqual(authority["GUROBI_THREADS_PER_MODEL"],4)
        self.assertEqual(authority["minimum_RUNNING_migrations"],76)


if __name__=="__main__":unittest.main()
