import json
import math
from pathlib import Path
import tempfile
import unittest

from ieee8500_v42.mv_candidates import (
    build_candidates, complete_abc_corridors, line_length_km, quantile_linear)


class ConductorConnectivityTests(unittest.TestCase):
    def fixture(self):
        buses = [{"bus": bus, "nodes": [1, 2, 3], "kv_base_ln": 12.47 / math.sqrt(3)}
                 for bus in ("a", "b")]
        lines = [{"element": f"Line.phase{phase}", "buses": [f"a.{phase}", f"b.{phase}"],
                  "node_order": [phase, phase], "ncond": 1, "nterm": 2, "enabled": True}
                 for phase in (1, 2, 3)]
        old = {row["element"].lower(): {"any_open": False} for row in lines}
        return {"buses": buses, "lines": lines, "transformers": [], "regcontrols": []}, old

    def test_local_abc_nodes_do_not_repair_missing_or_crossed_phase(self):
        inventory, old = self.fixture()
        self.assertEqual(set(complete_abc_corridors(inventory, old)), {("a", "b")})
        inventory["lines"][2]["enabled"] = False
        self.assertEqual(complete_abc_corridors(inventory, old), {})
        inventory["lines"][2]["enabled"] = True
        inventory["lines"][2]["node_order"] = [3, 2]
        self.assertEqual(complete_abc_corridors(inventory, old), {})

    def test_open_phase_cannot_certify_complete_corridor(self):
        inventory, old = self.fixture()
        old["line.phase1"]["any_open"] = True
        self.assertEqual(complete_abc_corridors(inventory, old), {})

    def test_unspecified_units_stay_unknown(self):
        self.assertIsNone(line_length_km(.001, 0))
        self.assertEqual(line_length_km(1, 3), 1.)
        self.assertAlmostEqual(line_length_km(1000, 5), .3048)


class RealSavedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.result = build_candidates(cls.root)

    def test_original_guard_is_reconstructed_without_physical_port_promotion(self):
        result = self.result
        self.assertEqual((len(result.candidates), len(result.excluded)), (606, 32))
        self.assertEqual(result.audit["root_distance_reconstruction_error_max_ohm"], 0.)
        threshold = result.audit["root_distance_q05_ohm"]
        self.assertTrue(all(row["root_distance_ohm"] >= threshold for row in result.candidates))
        self.assertTrue(all(row["root_distance_ohm"] < threshold for row in result.excluded))
        self.assertTrue(all(not row["physical_port_qualified"] and row["allowed_import_kw"] is None
                            and row["allowed_export_kw"] is None and row["allowed_pcs_kva"] is None
                            for row in result.candidates + result.excluded))
        self.assertEqual(quantile_linear([row["root_distance_ohm"] for row in
                         result.candidates + result.excluded], .05), threshold)

    def test_pair_metric_is_symmetric_and_original_coordinate_units_stay_unknown(self):
        result = self.result
        a, b = result.candidates[0]["dss_bus"], result.candidates[-1]["dss_bus"]
        self.assertEqual(result.pair_metrics(a, b), result.pair_metrics(b, a))
        self.assertEqual(result.pair_metrics(a, a)["electrical_tree_distance_ohm"], 0.)
        self.assertEqual(result.pair_metrics(a, a)["source_xy_distance_unknown_units"], 0.)
        self.assertFalse(result.pair_metrics(a, a)["original_electrical_dispersion_gate_pass"])
        self.assertTrue(all(not row["coordinate_crs_units_compass_certified"] for row in result.candidates))
        # The original Units=0 feeder connector is retained explicitly, not
        # silently assigned km or hidden by a physical-distance certification.
        self.assertTrue(all(not row["feeder_head_path_length_complete"] for row in result.candidates))

    def test_modified_static_input_stops_before_inventory_or_selection(self):
        manifest = json.loads((self.root / "ieee8500_v42/data/mv_candidates/SOURCE_MANIFEST.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "ieee8500_v42/data/mv_candidates"
            data.mkdir(parents=True)
            (data / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest))
            (data / manifest["files"][0]["copy"]).write_text("[]")
            with self.assertRaisesRegex(ValueError, "Copied static input SHA mismatch"):
                build_candidates(temporary)


if __name__ == "__main__":
    unittest.main()
