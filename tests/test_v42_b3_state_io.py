"""Bounded closed-state IO without solver execution or large model fixtures."""
import errno
import gzip
import io
import os
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from v42_autonomous_b3.admission import checked, record
from v42_b3_joint import state_io


class SourceStateReadTests(unittest.TestCase):
    def fixture(self, root):
        path = root / "closed.pkl.gz"
        value = {"original_matrix_bytes": os.urandom(state_io.READ_CHUNK * 3),
                 "complete_domain_roster": ["job1", "job2"], "exact_LB": "1/2"}
        with gzip.open(path, "wb") as stream:
            pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
        return path, value, record(path)

    def test_large_read_requests_are_bounded_and_partial_reads_preserve_bytes(self):
        payload = os.urandom(state_io.READ_CHUNK * 4)
        requested = []
        class Tracking(io.BytesIO):
            def read(self, size=-1):
                requested.append(size)
                return super().read(size)
        with state_io._CompressedReader("unused", opener=lambda: Tracking(payload)) as raw:
            buffer = bytearray(len(payload))
            self.assertEqual(raw.readinto(buffer), state_io.READ_CHUNK)
            result = bytes(buffer[:state_io.READ_CHUNK])
            while len(result) < len(payload):
                result += raw.read(state_io.READ_CHUNK * 4)
        self.assertEqual(result, payload)
        self.assertTrue(all(0 < size <= state_io.READ_CHUNK for size in requested))

    def test_errno22_retry_reopens_at_exact_offset_and_preserves_full_pickle(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); path, expected, receipt = self.fixture(root)
            compressed = path.read_bytes(); attempts = []; offsets = []; failed = [False]
            class Transient(io.BytesIO):
                def read(self, size=-1):
                    attempts.append(size)
                    if self.tell() > 0 and not failed[0]:
                        failed[0] = True
                        # Even a failed operation that advanced its handle
                        # must restart at the recorded pre-read offset.
                        super().read(17)
                        raise OSError(errno.EINVAL, "simulated Windows invalid read")
                    return super().read(size)
                def seek(self, offset, whence=io.SEEK_SET):
                    offsets.append(offset)
                    return super().seek(offset, whence)
            original = state_io._CompressedReader
            with patch.object(state_io, "_CompressedReader",
                              side_effect=lambda file: original(file, opener=lambda: Transient(compressed))):
                loaded = state_io.load_source_state(receipt, root, checked)
            self.assertEqual(loaded.state, expected)
            self.assertTrue(failed[0])
            self.assertTrue(offsets)
            self.assertTrue(all(size <= state_io.READ_CHUNK for size in attempts))
            state = loaded.state
            self.assertIs(loaded.take(receipt, root, checked), state)

    def test_loaded_state_is_one_use_and_receipt_bound(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); path, expected, receipt = self.fixture(root)
            loaded = state_io.load_source_state(receipt, root, checked)
            wrong = dict(receipt, bytes=receipt["bytes"] + 1)
            with self.assertRaisesRegex(ValueError, "READ_RECEIPT_BINDING_DRIFT"):
                loaded.take(wrong, root, checked)
            state = loaded.state
            self.assertIs(loaded.take(receipt, root, checked), state)
            self.assertEqual(state, expected)
            with self.assertRaisesRegex(ValueError, "ALREADY_CONSUMED"):
                loaded.take(receipt, root, checked)

    def test_source_tamper_after_load_or_during_read_is_rejected(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); path, _, receipt = self.fixture(root)
            loaded = state_io.load_source_state(receipt, root, checked)
            path.write_bytes(path.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "SEALED_FILE_SHA_DRIFT"):
                loaded.take(receipt, root, checked)
            path, _, receipt = self.fixture(root)
            checks = [0]
            def tamper_after_read(value, owner):
                checks[0] += 1
                if checks[0] == 2:
                    path.write_bytes(path.read_bytes() + b"changed")
                return checked(value, owner)
            with self.assertRaisesRegex(ValueError, "SEALED_FILE_SHA_DRIFT"):
                state_io.load_source_state(receipt, root, tamper_after_read)

    def test_other_io_errors_and_persistent_errno22_fail_without_fake_state(self):
        for number, expected_reads in ((errno.EACCES, 1), (errno.EINVAL, 3)):
            calls = []
            class Broken(io.BytesIO):
                def read(self, size=-1):
                    calls.append(size)
                    raise OSError(number, "simulated read failure")
            with state_io._CompressedReader("unused", opener=lambda: Broken(b"x")) as raw:
                with self.assertRaises(OSError):
                    raw.read(128)
            self.assertEqual(len(calls), expected_reads)


if __name__ == "__main__":
    unittest.main()
