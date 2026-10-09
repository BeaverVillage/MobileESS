import builtins
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ieee8500_v42 import traffic_mobility_audit as traffic


class PortableTrafficAuditTests(unittest.TestCase):
    def test_all_frozen_routes_replay_without_external_or_actual_files(self):
        root = Path(__file__).resolve().parents[1]
        ordinary_open, ordinary_path_open = builtins.open, Path.open

        def permitted(path):
            if not isinstance(path, (str, bytes, Path)):
                return
            resolved = Path(path).resolve()
            self.assertTrue(resolved.is_relative_to(root), "External file accessed: " + str(resolved))

        def guarded_open(path, *args, **kwargs):
            permitted(path)
            return ordinary_open(path, *args, **kwargs)

        def guarded_path_open(path, *args, **kwargs):
            permitted(path)
            return ordinary_path_open(path, *args, **kwargs)

        with patch("builtins.open", guarded_open), patch.object(Path, "open", guarded_path_open):
            result = traffic.audit(root, current_input=Path("missing_external_input"))
        self.assertEqual(result["input_read_mode"], "PINNED_PORTABLE_COPIES_PREFERRED")
        self.assertFalse(result["external_files_required_for_this_replay"])
        self.assertEqual(result["route_rows"], 55296)
        self.assertEqual(result["route_counts"]["accepted_original_move_arcs"], 51322)
        self.assertTrue(all(value == 0. for value in result["independent_reconstruction_error_max"].values()))
        self.assertEqual(result["native_vehicle_count"], 4)
        self.assertFalse(result["six_vehicle_production_eligible"])
        self.assertFalse(result["actual_six_vehicle_route_gate_connected"])
        self.assertFalse(result["actual_sumo_values_loaded"])
        self.assertFalse(result["actual_sumo_data_copied"])
        self.assertEqual((result["Native_calls"], result["OpenDSS_calls"], result["Actual_replay_calls"]), (0, 0, 0))

    def test_modified_portable_container_stops_before_numeric_replay(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "ieee8500_v42/data/traffic_audit"
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "ieee8500_v42/data/traffic_audit"
            data.mkdir(parents=True)
            for name in ("SOURCE_MANIFEST.json", "ORIGINAL_SOURCE_SHA_PROOF.json"):
                (data / name).write_bytes((source / name).read_bytes())
            manifest = json.loads((data / "SOURCE_MANIFEST.json").read_text())
            first_name = next(iter(manifest["files"]))
            (data / manifest["files"][first_name]["relative_path"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "PORTABLE_CONTAINER_SHA"):
                traffic.portable_configuration(temporary)

    def test_lossless_gzip_binds_original_decoded_bytes(self):
        raw = b"Static source identity\n" * 100
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "static.gz"
            path.write_bytes(gzip.compress(raw, mtime=0))
            record = traffic.decoded_record(path, "lossless_gzip")
        self.assertEqual(record["bytes"], len(raw))
        self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(record["sha256"], record["stored_sha256"])


if __name__ == "__main__":
    unittest.main()
