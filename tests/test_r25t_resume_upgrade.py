from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_driver():
    spec = importlib.util.spec_from_file_location(
        "r25t_driver_for_test", REPO / "driver_r25t_stage1_resume_latest.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_decomposition():
    science = REPO / "science"
    sys.path.insert(0, str(science))
    try:
        spec = importlib.util.spec_from_file_location(
            "r25t_decomposition_for_test", science / "r25m_b6_exact_path_decomposition.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(science))


class R25TResumeUpgradeTests(unittest.TestCase):
    def test_new_r25t_audit_uses_final_certificate_not_stale_local_gap(self):
        text = (REPO / "science" / "r25m_b6_exact_path_decomposition.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("float(cert['gap'])", text)
        self.assertIn("'restricted_master_incumbent':restricted_master_snapshot['incumbent']", text)

    def test_r25v_causal_multistart_and_round_trip_reduction_are_enabled(self):
        main = (REPO / "science" / "main.py").read_text(encoding="utf-8")
        decomp = (REPO / "science" / "r25m_b6_exact_path_decomposition.py").read_text(
            encoding="utf-8"
        )
        driver = (REPO / "driver_r25t_stage1_resume_latest.py").read_text(encoding="utf-8")
        self.assertIn("MOBILEESS_R25V_CAUSAL_ROLLING_MIPSTART", main)
        self.assertIn("native_start_must_pass_current_model_feasibility", main)
        self.assertIn("terminal_completion_policy", main)
        self.assertIn("CAUSAL_SHIFTED_PREVIOUS_PLAN", decomp)
        self.assertIn("SAME_ISSUE_RESTRICTED_MASTER", decomp)
        self.assertIn("cm.NumStart=len(starts)", decomp)
        self.assertIn('"MOBILEESS_R25M_B6_PRICING_BATCH": "32"', driver)
        self.assertIn('"MOBILEESS_R25T_PRIMAL_STALL_SECONDS": "60"', driver)

    def test_r25w_thread_cap_accepts_solver_downshift_but_rejects_oversubscription(self):
        main = (REPO / "science" / "main.py").read_text(encoding="utf-8")
        self.assertIn("configured_thread_cap_verified", main)
        self.assertIn("observed_thread_counts_within_requested_cap", main)
        self.assertIn("all(1<=int(v)<=threads_req for v in actual_thread_counts)", main)
        self.assertIn("max(actual_thread_counts)", main)
        self.assertIn("THREADS_PARAMETER_PLUS_MESSAGE_CAP", main)

        requested = configured = 4
        observed = [4, 1]
        self.assertTrue(configured == requested and all(1 <= v <= requested for v in observed))
        self.assertFalse(configured == requested and all(1 <= v <= requested for v in [4, 5]))

        # Regression for the issue-157 rerun: these audit assignments must be
        # unconditional statements in build_full, not nested under the
        # non-B6 multiobjective ``else`` branch.
        import ast

        tree = ast.parse(main)
        build_full = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_full"
        )
        direct_assignments = {
            target.id
            for node in build_full.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertIn("actual_thread_counts", direct_assignments)
        self.assertIn("concurrent_req", direct_assignments)
        self.assertIn("thread_verified", direct_assignments)

    def test_r25w_rejects_regressive_pricing_batch_64(self):
        driver = (REPO / "driver_r25t_stage1_resume_latest.py").read_text(encoding="utf-8")
        self.assertIn('"MOBILEESS_R25M_B6_PRICING_BATCH": "32"', driver)
        self.assertNotIn('"MOBILEESS_R25M_B6_PRICING_BATCH": "64"', driver)
        self.assertIn("24 iterations / 324.5 s", driver)

    def test_r25x_sparse_tail_expands_only_saturated_late_blocks(self):
        decomp = load_decomposition()
        policy = decomp.sparse_tail_pricing_blocks
        self.assertEqual(
            policy({"MESS01": 32, "MESS02": 7, "MESS03": 0, "MESS04": 0}, 32, 2),
            ("MESS01",),
        )
        self.assertEqual(
            policy({"MESS01": 32, "MESS02": 32, "MESS03": 32, "MESS04": 32}, 32, 2),
            (),
        )
        self.assertEqual(policy({"MESS01": 31, "MESS02": 0}, 32, 2), ())
        self.assertEqual(policy({"MESS01": 0, "MESS02": 0}, 32, 2), ())

        driver = load_driver()
        env = driver.runtime_environment(164, Path("resume"), "state-hash")
        self.assertEqual(env["MOBILEESS_R25M_B6_PRICING_BATCH"], "32")
        self.assertEqual(env["MOBILEESS_R25X_SPARSE_TAIL_PRICING_BATCH"], "64")
        self.assertEqual(env["MOBILEESS_R25X_SPARSE_TAIL_MAX_ACTIVE_MESS"], "2")

    def test_r25x_bounded_optimal_snapshot_skips_redundant_kkt_retries(self):
        driver = load_driver()
        env = driver.runtime_environment(164, Path("resume"), "state-hash")
        self.assertEqual(env["MOBILEESS_R25Q_BOUNDED_RC_ENVELOPE"], "1")
        self.assertEqual(env["MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET"], "0")

    def test_r25x_strict_polish_accepts_feasible_certified_numerical_correction(self):
        text = (REPO / "science" / "r25m_b6_exact_path_decomposition.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("R25T compact polish worsened objective", text)
        self.assertIn("objective_worsening_after_strict_feasibility", text)
        self.assertIn("R25T compact polish lost global certificate", text)
        self.assertIn("acceptance_requires_quality_and_global_certificate", text)

    def test_r25v_resume_guidance_is_persisted_and_reloaded(self):
        main = (REPO / "science" / "main.py").read_text(encoding="utf-8")
        driver = (REPO / "driver_r25t_stage1_resume_latest.py").read_text(encoding="utf-8")
        self.assertIn("BUILD7C_ROLLING_GUIDANCE_NEXT_ISSUE.json", main)
        self.assertIn("MOBILEESS_R25V_RESUME_GUIDANCE_PATH", main)
        self.assertIn("resume_guidance.json", driver)
        self.assertIn("resume_jobs.csv", driver)

    def test_early_r25t_nested_compact_gap_is_resume_authority(self):
        driver = load_driver()
        audit = {
            "revision": "R25T_B6C6_GLOBAL_BOUND_PORTFOLIO",
            "global_certified_gap": 0.042,
            "compact_exact_global_phase": {
                "global_gap_before_polish": 0.02999,
                "global_gap_after_polish": 0.02994,
            },
        }
        self.assertAlmostEqual(driver.authoritative_decomposition_gap(audit), 0.02994)

    def test_preflight_returns_before_incomplete_issue_quarantine(self):
        text = (REPO / "driver_r25t_stage1_resume_latest.py").read_text(encoding="utf-8")
        main = text[text.index("def main() -> int:") :]
        self.assertLess(main.index("if preflight_only:"), main.index("incomplete = RUN"))
        self.assertLess(main.index("acquire_runtime_lock("), main.index("initialize()"))
        self.assertIn("pass_fds=(runtime_lock_fd(),)", main)

        r25s_text = (REPO / "driver_r25s_stage1_resume_latest.py").read_text(encoding="utf-8")
        r25s_main = r25s_text[r25s_text.index("def main() -> int:") :]
        self.assertLess(r25s_main.index("if preflight_only:"), r25s_main.index("incomplete = RUN"))
        self.assertLess(r25s_main.index("acquire_runtime_lock("), r25s_main.index("initialize()"))
        self.assertIn("pass_fds=(runtime_lock_fd(),)", r25s_main)

    @unittest.skipUnless(os.name == "posix", "fcntl runtime-lock test requires WSL/Linux")
    def test_runtime_lock_rejects_a_second_driver(self):
        driver = load_driver()
        with tempfile.TemporaryDirectory(prefix="r25t_lock_") as directory:
            driver.WORK = Path(directory)
            driver.acquire_runtime_lock("TEST_OWNER")
            script = (
                "import importlib.util,sys\n"
                "from pathlib import Path\n"
                f"p=Path({str(REPO / 'driver_r25t_stage1_resume_latest.py')!r})\n"
                "s=importlib.util.spec_from_file_location('r25t_lock_contender',p)\n"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
                f"m.WORK=Path({directory!r})\n"
                "try:\n"
                " m.acquire_runtime_lock('TEST_CONTENDER')\n"
                "except RuntimeError as exc:\n"
                " print(str(exc));raise SystemExit(23)\n"
                "raise SystemExit(0)\n"
            )
            contender = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, check=False
            )
            self.assertEqual(contender.returncode, 23, contender.stdout + contender.stderr)
            self.assertIn("refusing concurrent mutation", contender.stdout)
            import fcntl

            fcntl.flock(driver._RUNTIME_LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
            driver._RUNTIME_LOCK_HANDLE.close()
            driver._RUNTIME_LOCK_HANDLE = None

    def test_legacy_runtime_science_is_refreshed_without_touching_commits(self):
        driver = load_driver()
        with tempfile.TemporaryDirectory(prefix="r25t_upgrade_") as directory:
            base = Path(directory)
            source = base / "source_science"
            root = base / "runtime"
            science = root / "science"
            run = root / "stage1_54_of_54"
            source.mkdir()
            science.mkdir(parents=True)
            committed = run / "issue_000148" / "BUILD7C_POSTCOMMIT_STATE.json"
            committed.parent.mkdir(parents=True)
            committed.write_text('{"immutable":true}\n', encoding="utf-8")
            (source / "main.py").write_text("new main\n", encoding="utf-8")
            (source / "r25m_b6_exact_path_decomposition.py").write_text("new audit\n", encoding="utf-8")
            (science / "r25m_b6_exact_path_decomposition.py").write_text("legacy audit\n", encoding="utf-8")
            (root / "R25T_RESUMABLE_MARKER.json").write_text(
                json.dumps(
                    {
                        "schema_version": "r25t.resumable.v1",
                        "source_decomp_sha256": driver.LEGACY_R25T_DECOMP_SHA256,
                        "created_at": "2026-08-14T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            driver.SOURCE_SCI = source
            driver.ROOT = root
            driver.SCI = science
            driver.RUN = run
            driver.EXPECTED = dict(driver.EXPECTED, main="new-main", decomp="new-decomp")
            driver.initialize()

            marker = json.loads((root / "R25T_RESUMABLE_MARKER.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["schema_version"], "r25t.resumable.v2")
            self.assertEqual(marker["source_decomp_sha256"], "new-decomp")
            self.assertEqual(
                (science / "r25m_b6_exact_path_decomposition.py").read_text(encoding="utf-8"),
                "new audit\n",
            )
            self.assertEqual(committed.read_text(encoding="utf-8"), '{"immutable":true}\n')


if __name__ == "__main__":
    unittest.main()
