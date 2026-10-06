import unittest
from fractions import Fraction as F
import numpy as np
from scipy import sparse
from v42_rowgen.core import *

class SeparatorTests(unittest.TestCase):
    def data(self):
        return sparse.csr_matrix([[1.,0.],[0.,1.],[1.,-1.]]),dict(rhs=np.array([0.,0.,0.]),sense=np.array(['<','>','=']),row_names=np.array(['line_thermal_face','voltage_lower','voltage_upper']))
    def test_every_family_and_sign(self):
        A,d=self.data();x=np.array([1.,-1.]);r=separate(A,d,x)
        self.assertEqual(list(r['violated']),[0,1,2])
    def test_all_violations_not_top_k(self):
        A,d=self.data();r=OriginalRows(A,d);fresh=r.add(r.pending(np.array([1.,-1.]))['violated'])
        self.assertEqual(list(fresh),[0,1,2]);self.assertEqual(len(r.axis),3)
    def test_active_rows_still_checked_finally(self):
        A,d=self.data();r=OriginalRows(A,d,[0,1,2]);self.assertTrue(r.pending(np.array([1.,-1.]))['PASS'])
        self.assertFalse(r.final(np.array([1.,-1.]))['PASS'])
    def test_exact_boundary_below_and_above(self):
        A=sparse.csr_matrix([[1.]])
        d=dict(rhs=np.array([0.]),sense=np.array(['<']))
        for value in [np.nextafter(TOL,0.),TOL,np.nextafter(TOL,np.inf)]:
            r=separate(A,d,np.array([value]));self.assertEqual(bool(len(r['violated'])),F(float(value))>F(TOL))
            self.assertEqual(r['ambiguous_exact_checks'],1)
    def test_cancellation_does_not_hide_row(self):
        A=sparse.csr_matrix([[1e16,1.,-1e16]])
        d=dict(rhs=np.array([0.]),sense=np.array(['<']))
        r=separate(A,d,np.ones(3));self.assertEqual(list(r['violated']),[0]);self.assertEqual(r['ambiguous_exact_checks'],1)
    def test_constant_rows_not_skipped(self):
        A=sparse.csr_matrix((3,2));d=dict(rhs=np.array([-1.,1.,0.]),sense=np.array(['<','>','=']))
        self.assertEqual(list(separate(A,d,np.zeros(2))['violated']),[0,1])
    def test_nonfinite_rejected(self):
        A,d=self.data()
        with self.assertRaises(ValueError):separate(A,d,np.array([np.nan,0.]))
    def test_overflow_rejected(self):
        A=sparse.csr_matrix([[1e308]]);d=dict(rhs=np.array([0.]),sense=np.array(['<']))
        with np.errstate(over='ignore'):
            with self.assertRaises(ValueError):separate(A,d,np.array([1e308]))
    def test_bad_sense_rejected(self):
        A,d=self.data();d['sense'][0]='?'
        with self.assertRaises(ValueError):separate(A,d,np.zeros(2))
    def test_payload_sign_and_rhs_identity(self):
        A,d=self.data();h=row_digest(A,d,0);d['sense'][0]='>'
        self.assertNotEqual(h,row_digest(A,d,0));d['rhs'][0]=1.;self.assertNotEqual(h,row_digest(A,d,0))
    def test_cannot_insert_non_original_grid(self):
        A,d=self.data();d['row_names'][0]='energy_balance';r=OriginalRows(A,d)
        with self.assertRaises(ValueError):r.add([0])
    def test_monotone_subset_no_duplicate_insert(self):
        A,d=self.data();r=OriginalRows(A,d);self.assertEqual(list(r.add([1,1])),[1]);self.assertEqual(len(r.add([1])),0)

class AffineTests(unittest.TestCase):
    def data(self):
        A=sparse.csr_matrix([[-1.,1.,0.],[0.,-.5,1.],[0.,0.,1.]])
        d=dict(names=np.array(['Pdis[MESS01,A,0]','injection_P[A,0]','response_line_P[0,0]']),
            row_names=np.array(['injection_P_binding','response_line_P_binding','line_thermal_face']),
            rhs=np.array([0.,2.,3.]),sense=np.array(['=','=','<']),
            lower=np.array([0.,-1e100,-1e100]),upper=np.array([10.,1e100,1e100]),
            objective=np.zeros(3),types=np.array(['C','C','C']))
        return A,d
    def test_unique_triangle_direct_extension(self):
        A,d=self.data();defs=binding_proof(A,d);x=affine_extend(A,d,np.array([2.,0.,0.]),defs)
        self.assertTrue(np.array_equal(x,[2.,2.,3.]));self.assertTrue(separate(A,d,x)['PASS'])
    def test_nonunit_pivot_rejected(self):
        A,d=self.data();A[0,1]=2.
        with self.assertRaises(ValueError):binding_proof(A,d)
    def test_temporal_dependency_rejected(self):
        A,d=self.data();d['row_names'][2]='energy_balance'
        with self.assertRaises(ValueError):binding_proof(A,d)
    def test_missing_definition_rejected(self):
        A,d=self.data();d['row_names'][0]='some_other_row'
        with self.assertRaises(ValueError):binding_proof(A,d)

if __name__=='__main__':unittest.main()
