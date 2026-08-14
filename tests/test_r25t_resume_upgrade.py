from __future__ import annotations

import importlib.util
import json
from pathlib import Path
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


class R25TResumeUpgradeTests(unittest.TestCase):
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
