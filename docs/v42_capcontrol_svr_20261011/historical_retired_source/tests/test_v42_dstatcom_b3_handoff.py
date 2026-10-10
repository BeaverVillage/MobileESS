"""Exercise the reused A1 return through the unchanged typed M1 admission."""
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
import json
import unittest

import numpy as np

from v42_autonomous_b3 import reuse
from v42_autonomous_b3.admission import record
from v42_b3_joint.contracts import StageRequest, canonical
from v42_b3_joint.dry_run import fixture_authority, fixture_aidc
from v42_b3_joint.m_source import fixed_aidc_payload
from v42_b3_joint.source_coordinator import output_document, output_from_document
from v42_b3_joint.source_runtime import FakeSourceRegistry, RealStageContext


class Registry(FakeSourceRegistry):
    def callable(self,*args): return lambda *args: None


class Ledger:
    def receipt(self): return dict(native_call_count=0)
    def used(self): return 0
    def sealed_receipt(self): return canonical(dict(evidence_kind="FAKE_SOURCE_TEST",native_call_count=0))


class ReusedA1HandoffTests(unittest.TestCase):
    def test_actual_reuse_execute_reseals_physical_proof_and_m1_consumes_serialized_packet(self):
        # Only costly original builders/verifiers are fixtures. The real reuse
        # execute method, SourceStageOutput deep seal, serialization and M1
        # physical admission run unchanged. This is not a scientific canary.
        with TemporaryDirectory() as directory:
            root=Path(directory);b1=root/"originalB1";output=root/"newA1"
            b1.mkdir();output.mkdir()
            authority,aidc=fixture_authority(),fixture_aidc()
            registry=Registry()
            context=RealStageContext(StageRequest("A1",authority),root/"input",output,
                canonical(dict(day=authority.day)),registry,object(),{},authority.source_sha,"FIXTURE_HANDOFF")
            arrays=dict(sites=list(authority.pcc_ids),
                PCC_P_kw=[list(row) for row in zip(*aidc.pcc_p)],
                PCC_Q_kvar=[list(row) for row in zip(*aidc.pcc_q)],
                IT_kw=[list(row) for row in zip(*aidc.it_power)],
                GPU=[[1.]*12 for _ in range(96)],known_GPU=[[1.]*12 for _ in range(96)])
            planning=b1/"planning.npz";np.savez_compressed(planning,**arrays)
            jobs=json.loads(aidc.jobs_json)["known_job_actions"]
            def put(name,value):
                path=b1/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(canonical(value),encoding="utf8");return record(path)
            physical=put("physical.json",dict(selected_jobs=jobs,controls=[]))
            put("P1/INTEGER_CONTROL/MODEL_IDENTITY.json",dict(original_snapshot_sha256=authority.grid_sha))
            put("P1_FULL_DOMAIN_BOUND_CERTIFICATE.json",dict(FAKE_SOURCE_TEST=True))
            put("P1_RESULT.json",dict(full_pricing={}))
            put("STATIC/P1_CLOSED_STATE.pkl.gz",dict(FAKE_SOURCE_TEST=True))
            result=dict(planning=record(planning),incumbent=dict(physical=physical,point=dict(FAKE_SOURCE_TEST=True)),
                freeze=dict(FAKE_SOURCE_TEST=True),exact_UB="1",exact_LB="199/200",certified_gap=.005,
                native_seconds=2.,native_calls=4)
            put("A_RESULT.json",result)
            for name in ("B1_P1_FREEZE.json","A_PREPARE_RECEIPT.json","A_NATIVE_SOURCE_FREEZE.json"):
                put(name,dict(FAKE_SOURCE_TEST=True))
            old=dict(domains=dict(job=SimpleNamespace(sha=authority.physical_domain_sha)))
            loaded=SimpleNamespace(state=old)
            fresh=dict(_campaign=dict(input_receipts=[]))
            run=FunctionType((lambda:None).__code__,dict(prepare=lambda *args:fresh))
            proof={"physical":dict(PASS=True,FAKE_SOURCE_TEST=True),"global":dict(FAKE_SOURCE_TEST=True)}
            bridge=reuse.B1A1ReuseBridge(b1)
            with patch.object(bridge,"_verify_origin",return_value=(result,{},dict(git_head="a"*40))), \
                 patch.object(bridge,"_configure",return_value=(SimpleNamespace(np=np),run,None,None,
                     [SimpleNamespace(control_names=[])])), \
                 patch.object(bridge,"_request",return_value={}), \
                 patch.object(bridge,"_proof_receipts",return_value=[]), \
                 patch.object(bridge,"_verify_admitted",return_value=proof), \
                 patch.object(reuse,"_restore_source_globals",side_effect=lambda *args:nullcontext()), \
                 patch.object(reuse,"load_source_state",return_value=loaded), \
                 patch.object(reuse,"compare_original_identity",return_value=dict(PASS=True,
                     complete_domain_sha=authority.physical_domain_sha)), \
                 patch.object(reuse,"aidc_from_source",return_value=aidc):
                output=bridge.execute(context,Ledger())
            self.assertEqual(output.source_packet["physical_source_evidence"],output.physical_evidence)
            self.assertTrue(output.source_packet["physical_source_evidence"]["PASS"])
            restored=output_from_document(output_document(output))
            m1=RealStageContext(StageRequest("M1",authority,fixed_aidc=restored.aidc),root/"input",root/"M1",
                canonical(dict(day=authority.day)),registry,object(),dict(fixed_aidc=restored.source_packet),
                authority.source_sha,"FIXTURE_HANDOFF")
            payload=fixed_aidc_payload(m1)
            self.assertTrue(payload["identity"]["PASS"])
            self.assertEqual(payload["planning"]["PCC_P_kw"],arrays["PCC_P_kw"])
            self.assertEqual(payload["identity"]["B2_FCFS_producer_calls"],0)
            # The guard remains strict: removing the proof still rejects M1.
            del m1.source_packets["fixed_aidc"]["physical_source_evidence"]
            with self.assertRaisesRegex(ValueError,"M_ORIGINAL_A_PHYSICAL_REPLAY_REQUIRED"):
                fixed_aidc_payload(m1)


if __name__ == "__main__": unittest.main()
