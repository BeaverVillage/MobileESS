"""Adversarial symbolic checks; no Gurobi model or optimize calls."""
from fractions import Fraction as F
import importlib.util
from pathlib import Path
import unittest

import numpy as np
from scipy import sparse

path = Path(__file__).resolve().parents[2] / 'tools/physical_global_lb_pilot.py'
spec = importlib.util.spec_from_file_location('physical_pilot', path)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class CertificateTests(unittest.TestCase):
    def example(self):
        # y=3+2p; p=dis-ch; .25y-.5q+.1<=rho.
        A = sparse.csr_matrix([[0, 1, -2, 0, 0, 0],
                               [0, 0, 1, -1, 1, 0],
                               [-1, .25, 0, 0, 0, -.5]], dtype=float)
        d = dict(names=np.array(['rho_max', 'response_line_P[0,3]', 'injection_P[s,0]',
                                'Pdis[MESS01,s,0]', 'Pch[MESS01,s,0]', 'Q[MESS01,s,0]']),
                 row_names=np.array(['response_line_P_binding[0,3]', 'injection_P_binding',
                                     'line_thermal_face[0,3,0]']),
                 sense=np.array(['=', '=', '<']), rhs=np.array([3., 0., -.1]))
        return A, d

    def test_rhs_fixed_term_injection_and_charge_signs(self):
        A, d = self.example()
        definitions, expand = pilot.exact_helpers(A, d)
        constant, terms = pilot.project(A, d, 2, expand, 0)
        self.assertEqual(constant, F(3, 4) + F(.1))
        self.assertEqual(terms, {3: F(1, 2), 4: F(-1, 2), 5: F(-1, 2)})
        self.assertEqual(len(definitions), 2)

    def test_missing_fixed_offset_is_detectable(self):
        A, d = self.example()
        _, expand = pilot.exact_helpers(A, d)
        b, _ = pilot.project(A, d, 2, expand, 0)
        d['rhs'][0] = 0.
        _, corrupt_expand = pilot.exact_helpers(A, d)
        corrupt_b, _ = pilot.project(A, d, 2, corrupt_expand, 0)
        self.assertEqual(b - corrupt_b, F(3, 4))

    def test_wrong_thermal_sign_rejected(self):
        A, d = self.example()
        A[2, 0] = 1.
        _, expand = pilot.exact_helpers(A, d)
        with self.assertRaisesRegex(ValueError, 'THERMAL_RHO_SIGN_DRIFT'):
            pilot.project(A, d, 2, expand, 0)

    def test_uneliminated_nonvehicle_variable_rejected(self):
        A, d = self.example()
        d['row_names'][0] = 'unrelated_row'
        _, expand = pilot.exact_helpers(A, d)
        with self.assertRaisesRegex(ValueError, 'RESIDUAL_GLOBAL_COORDINATE'):
            pilot.project(A, d, 2, expand, 0)

    def test_helper_inequality_rejected(self):
        A, d = self.example()
        d['sense'][0] = '<'
        with self.assertRaisesRegex(ValueError, 'HELPER_NON_EQUALITY'):
            pilot.exact_helpers(A, d)

    def test_outward_rounding_for_both_signs(self):
        for q in [F(1, 3), F(-1, 3), F(1, 10), F(-1, 10)]:
            self.assertLessEqual(F(pilot.downward(q)), q)

    def test_weight_convexity_and_objective_box_correction(self):
        self.assertEqual(sum([F(1, 16)] * 16), 1)
        exact = F(1, 3)
        native = F(float(exact))
        delta = exact - native
        lo, hi = F(-20), F(30)
        correction = min(delta*lo, delta*hi)
        for x in (lo, F(0), hi):
            self.assertGreaterEqual(exact*x, native*x + correction)


if __name__ == '__main__':
    unittest.main()
