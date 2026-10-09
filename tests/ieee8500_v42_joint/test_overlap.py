import unittest

import numpy as np

from ieee8500_v42_joint.overlap import response_pair_metrics


class ControlOverlapTests(unittest.TestCase):
    def test_duplicate_effect_and_disjoint_effect_are_distinguished(self):
        a=np.array([[2.,0.],[2.,0.]])
        same=response_pair_metrics(a,3*a,[.5,.5])
        self.assertAlmostEqual(same['signed_P_response_cosine'],1.)
        self.assertAlmostEqual(same['positive_support_Jaccard'],1.)
        self.assertAlmostEqual(same['capacity_positive_response_overlap_fraction'],1.)
        separate=response_pair_metrics(a,a[:,::-1],[.5,.5])
        self.assertAlmostEqual(separate['signed_P_response_cosine'],0.)
        self.assertEqual(separate['positive_support_intersection_weight'],0.)
        self.assertEqual(separate['positive_support_union_weight'],1.)

    def test_zero_certified_vector_and_adverse_effect_cannot_claim_complementarity(self):
        a=np.array([[2.,0.],[2.,0.]])
        zero=response_pair_metrics(a,np.zeros_like(a),[.5,.5])
        self.assertIsNone(zero['signed_P_response_cosine'])
        self.assertIsNone(zero['capacity_positive_response_overlap_fraction'])
        adverse=response_pair_metrics(a,-a,[.5,.5])
        self.assertAlmostEqual(adverse['signed_P_response_cosine'],-1.)
        self.assertEqual(adverse['positive_support_intersection_weight'],0.)
        self.assertEqual(adverse['mean_weighted_negative_P_response_b'],1.)


if __name__=='__main__':unittest.main()
