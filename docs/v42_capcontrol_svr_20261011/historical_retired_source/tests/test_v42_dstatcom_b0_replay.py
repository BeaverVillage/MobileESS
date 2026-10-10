"""B0 immutable input and OFF-to-ON gate fixtures; no physical result claim."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

import numpy as np

from v42_b3_joint.contracts import canonical
from v42_dstatcom import b0_replay as subject


class B0InputTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.day="2025-05-01"
        self.folder=self.root/"BUNDLE/DAY_20250501";self.folder.mkdir(parents=True)
        self.raw=self.root/"INPUT/BUNDLE/DAY_20250501/DERIVED_AEMO_ACTUAL.parquet"
        self.raw.parent.mkdir(parents=True);self.raw.write_bytes(b"fixture-only-no-parquet-reader")
        p=np.full((96,12),1.);q=np.full((96,12),.1)
        np.savez_compressed(self.folder/"ACTUAL_PHYSICAL.npz",PCC_P_kw=p,PCC_Q_kvar=q)
        np.savez_compressed(self.folder/"V_ACTUAL_AC.npz",PCC_P_kw=p,PCC_Q_kvar=q)
        self.sources=dict(Actual_source=dict(subject.record(self.raw),path="Z:/missing_original_source.parquet"),
            day=self.day,alpha_BG=1.15,PV_scaled_by_alpha_BG=False,
            slots=[dict(slot=k,PCC_P_kw=p[k].tolist(),PCC_Q_kvar=q[k].tolist(),all_MESS_PQ_zero=True) for k in range(96)])
        self.put("RAW_PHYSICAL_INPUT_LOG.json",self.sources)
        self.put("RAW_CONTROL_LOG.json",dict(slots=[dict(slot=k) for k in range(96)]))
        self.put("FRESH_ACTUAL_AC_RECEIPT.json",dict(day=self.day,Actual_voltage=subject.record(self.folder/"V_ACTUAL_AC.npz")))
        self.put("INPUT_FREEZE.json",dict(day=self.day,Actual_raw=self.sources["Actual_source"],
            physical_PQ=subject.record(self.folder/"ACTUAL_PHYSICAL.npz")))
    def put(self,name,value): (self.folder/name).write_text(canonical(value),encoding="utf8")
    def test_original_arrays_and_relocated_actual_are_bound_by_exact_source_sha(self):
        result=subject.load_original(self.day,self.folder)
        self.assertEqual(result["raw"],self.raw)
        self.assertEqual(len(result["sources"]),7)
        self.assertEqual(result["p"].shape,(96,12))
        self.assertTrue(all(row["all_MESS_PQ_zero"] for row in result["inputs"]["slots"]))
    def test_missing_day_is_explicit_and_does_not_search_another_day(self):
        with self.assertRaisesRegex(ValueError,"DAY_FOLDER_REQUIRED"):
            subject.load_original("2025-05-02",self.folder)
        (self.folder/"ACTUAL_PHYSICAL.npz").unlink()
        with self.assertRaisesRegex(ValueError,"PRESERVED_DAY_EVIDENCE_MISSING"):
            subject.load_original(self.day,self.folder)
    def test_tampered_raw_relocation_never_admits_by_filename(self):
        self.raw.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"RELOCATED_ACTUAL_SOURCE_SHA_DRIFT"):
            subject.load_original(self.day,self.folder)
    def test_frozen_b0_power_packet_mismatch_is_rejected(self):
        self.sources["slots"][5]["PCC_P_kw"][3]+=1
        self.put("RAW_PHYSICAL_INPUT_LOG.json",self.sources)
        with self.assertRaisesRegex(ValueError,"FROZEN_POWER_PACKET_DRIFT"):
            subject.load_original(self.day,self.folder)
    def test_array_bit_identity_includes_nan_payload_and_dtype(self):
        values=np.array([float("nan"),1.])
        self.assertTrue(subject._bit_equal(values,values.copy()))
        self.assertFalse(subject._bit_equal(values,values.astype("float32")))


if __name__=="__main__": unittest.main()
