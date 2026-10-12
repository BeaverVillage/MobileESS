import gzip
import pickle
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from tools.b1_exact_pricing import direct_bound, strengthened_bound, single_column_witness
from tools.b1_snapshot_prefix import compact_snapshot
from tools import b1_only_v5 as operations


def snapshot(A=((1.,1.),), rhs=(1.,), senses=('=',), lower=(0.,0.), upper=(1.,1.)):
    return LinearSnapshot(sp.csr_matrix(np.asarray(A)), np.array(lower), np.array(upper),
                          np.array(senses), np.array(rhs), np.array(['C']*len(lower)),
                          (Objective('local_price', (), Fraction(0)),)).require()


class RepairTests(unittest.TestCase):
    def test_zero_dual_repairs_loose_finite_box_bound(self):
        s=snapshot();B=sp.csr_matrix([[-1e-12,0.]])
        proof=strengthened_bound(s,B,[1.],[-1e-6])
        self.assertEqual(proof['method'],'SEPARATE_ZERO_DUAL')
        self.assertEqual(proof['exact_lower_bound'],'0')
        self.assertIsNotNone(single_column_witness(s,(Fraction(1,10**12),Fraction(0)),1))

    def test_negative_cost_is_never_certified_nonnegative(self):
        s=snapshot();proof=strengthened_bound(s,sp.csr_matrix([[1.,0.]]),[1.],[0.])
        self.assertLess(Fraction(proof['exact_lower_bound']),0)

    def test_direct_true_objective_avoids_split_box_loss(self):
        s=snapshot(A=((1.,),),rhs=(0.,),lower=(0.,),upper=(100.,))
        self.assertEqual(direct_bound(s,(Fraction(1,10),),(Fraction(1,10),)),0)

    def test_invalid_dual_sign_and_unbounded_negative_residual(self):
        s=snapshot(senses=('<',))
        with self.assertRaises(ValueError):direct_bound(s,(Fraction(0),Fraction(0)),[1])
        s=snapshot(A=((0.,),),rhs=(0.,),lower=(0.,),upper=(np.inf,))
        self.assertIsNone(direct_bound(s,(Fraction(-1),),[0]))

    def test_witness_checks_every_original_row_and_bound(self):
        s=snapshot(A=((1.,1.),(1.,0.)),rhs=(1.,.5),senses=('=','<'))
        proof=single_column_witness(s,(Fraction(0),Fraction(1)),1)
        self.assertIsNone(proof)

    def test_unknown_implementation_and_input_failures_block(self):
        for classification,error in [('IMPLEMENTATION_FAILURE',"ValueError('unknown')"),
                                      ('INPUT_FAILURE',"ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')")]:
            self.assertTrue(operations.blocked_result({'scientific':{'classification':classification,'error':error}},'missing'))

    def test_pricing_exception_requires_successful_independent_audit(self):
        outcome={'scientific':{'classification':'IMPLEMENTATION_FAILURE',
                             'error':"ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')"}}
        with patch('tools.b1_pricing_incomplete_audit.audit',side_effect=AssertionError('drift')):
            self.assertTrue(operations.blocked_result(outcome,'missing'))
        self.assertTrue(operations.blocked_result(outcome))

    def test_source_global_flag_cannot_be_overridden_by_pricing_error(self):
        outcome={'source_global_integrity_block':True,'scientific':{'classification':'IMPLEMENTATION_FAILURE',
                'error':"ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')"}}
        self.assertTrue(operations.blocked_result(outcome,'missing'))

    def test_prefix_reader_stops_before_unwanted_data(self):
        s=snapshot()
        class Bomb:
            def __reduce__(self):return (eval,('1/0',))
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'state.pkl.gz'
            with gzip.open(p,'wb') as stream:pickle.dump({'compact':s,'large_data':Bomb()},stream,protocol=5)
            self.assertEqual(compact_snapshot(p).fingerprint(),s.fingerprint())

    def test_no_default_resume_or_new_campaign_preparation(self):
        with self.assertRaises(PermissionError):operations.require_resume({})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'not-created'
            with self.assertRaises(PermissionError):operations.prepare(root)
            self.assertFalse(root.exists())

    def test_original_terminal_dates_cannot_receive_new_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            for day in operations.PRIOR_DAYS:
                with self.assertRaises(PermissionError):
                    operations.request(Path(folder),{},dict(arm='B1',day=day))
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_invalid_audit_cannot_open_dispatch(self):
        outcome={'scientific':{'classification':'IMPLEMENTATION_FAILURE',
                             'error':"ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')"}}
        with patch('tools.b1_pricing_incomplete_audit.audit',return_value={'PASS':False}):
            self.assertTrue(operations.blocked_result(outcome,'missing'))

    def test_successful_qualified_dispatch_preserves_original_result(self):
        outcome={'scientific':{'classification':'IMPLEMENTATION_FAILURE',
                             'error':"ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')"}}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'RESULT.json';operations.atomic(path,outcome);before=operations.record(path)
            proof=dict(PASS=True,disposition='DATE_LOCAL_PRICING_CERTIFICATION_INCOMPLETE',
                       original_result=before,additional_Native_calls=0,
                       source_SHA='146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8')
            with patch('tools.b1_pricing_incomplete_audit.audit',return_value=proof):
                self.assertFalse(operations.blocked_result(outcome,path))
            self.assertEqual(operations.record(path),before)
            self.assertEqual(operations.read(Path(folder)/'INDEPENDENT_PRICING_INCOMPLETE_AUDIT.json'),proof)


if __name__=='__main__':unittest.main()
