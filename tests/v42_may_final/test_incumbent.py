from types import SimpleNamespace
from unittest.mock import patch
import tempfile
from pathlib import Path
import unittest
import numpy as np
from v42_may_final.incumbent import Bank,admit
from v42_pr134_b1.common import record,read
from v42_m1_research.check_ub import vector_sha


class IncumbentTests(unittest.TestCase):
    def setUp(self):
        self.case=SimpleNamespace(case_sha='current',A=SimpleNamespace(shape=(1,1)),
            d=dict(objective=np.ones(1),constant=0.))

    def cert(self,x,case='current'):
        return dict(PASS=True,Global_UB=float(x[0]),point_vector_sha256=vector_sha(x),
            strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
            original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha=case))

    def test_worse_pool_cannot_discard_global_or_moving_incumbent(self):
        bank=Bank(self.case)
        with patch('v42_may_final.incumbent.moving',side_effect=[True,False,False]):
            for ub in (.54,.67,.51):
                x=np.array([ub]);bank.offer(x,self.cert(x))
        self.assertEqual(bank.fields(),dict(BEST_GLOBAL_UB=.51,BEST_MOVING_FEASIBLE_UB=.54))

    def test_foreign_case_or_changed_raw_cannot_enter_bank(self):
        bank=Bank(self.case);x=np.array([.54])
        for cert in (self.cert(x,'other'),self.cert(np.array([.53]))):
            with self.assertRaises(ValueError):bank.offer(x,cert)
        self.assertIsNone(bank.best)

    def test_date_or_physical_drift_rejected_before_raw_is_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);validator=lambda *a: self.fail('foreign point reached validator')
            with patch('v42_may_final.incumbent.binding',return_value={'day':'May02','rhs':'new'}):
                accepted=admit(self.case,[dict(binding={'day':'May01','rhs':'old'},raw={})],out,validator,'B2')
            self.assertEqual(accepted,[])
            self.assertEqual(read(out/'CASE_INCUMBENT_ADMISSION.json')['records'][0]['reason'],
                'DATE_OR_NUMERIC_PHYSICAL_CONTRACT_MISMATCH')

    def test_matching_registry_still_requires_current_full_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);raw=out/'raw.npz';np.savez_compressed(raw,point=np.array([.54]))
            entry=dict(binding={},raw=record(raw))
            with patch('v42_may_final.incumbent.binding',return_value={}):
                accepted=admit(self.case,[entry],out,lambda *a:dict(PASS=False),'B2')
            self.assertEqual(accepted,[])
            self.assertFalse(read(out/'CASE_INCUMBENT_ADMISSION.json')['records'][0]['admitted'])

    def test_raw_byte_drift_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);raw=out/'raw.npz';np.savez_compressed(raw,point=np.array([.54]))
            entry=dict(binding={},raw=record(raw));raw.write_bytes(b'changed')
            with patch('v42_may_final.incumbent.binding',return_value={}):
                accepted=admit(self.case,[entry],out,lambda *a:self.fail('mutated point reached replay'),'B2')
            self.assertEqual(accepted,[])

if __name__=='__main__':unittest.main()
