from types import SimpleNamespace
from unittest.mock import patch
import unittest
import numpy as np
from v42_may_final.dispatch_score import DispatchScore


class DispatchScoreTests(unittest.TestCase):
    def fixture(self):
        b=SimpleNamespace(minimum=0.,maximum=10.,initial=1.,terminal=1.,
            p_limit=1.,dt_hours=.25,eta_charge=1.,eta_discharge=1.)
        arcs=[('A',t,'A',t+1,None) for t in range(96)]
        arcs.append(('A',0,'B',96,SimpleNamespace(energy_kwh=2.)))
        case=SimpleNamespace(graph=(['A','B'],{},arcs,b,{}))
        base=np.full(96,.2);base[48]=1.
        coefficients=np.zeros((4,2,96,3));coefficients[:,:,:,0]=.1;coefficients[:,:,:,1]=-.1
        minimax=SimpleNamespace(vertices=np.array([[1.,1.],[1.,-1.],[-1.,-1.],[-1.,1.]]),
            site_id={'A':0,'B':1},coeff=coefficients,base=base)
        context=dict(rows=[{'slot':t} for t in range(96)])
        with patch('v42_may_final.dispatch_score.Minimax',return_value=minimax),\
             patch('v42_may_final.dispatch_score.Graph',return_value=SimpleNamespace(validate=lambda *a:None)):
            scorer=DispatchScore(case,np.zeros(1),context)
        return scorer

    def test_joint_soc_recovery_and_rebound_can_shift_charge_off_peak(self):
        scorer=self.fixture();paths={f'MESS0{i}':list(range(96)) for i in range(1,5)}
        q=scorer.score(paths)
        self.assertAlmostEqual(q['score'],.6,places=7)
        self.assertTrue(q['all_four_PQ_SOC_redispatched'])
        self.assertFalse(q['Original_FULL_UB']);self.assertFalse(q['Global_LB'])
        self.assertIs(scorer.score(paths),q)

    def test_disconnected_energy_violation_is_inconclusive_score_not_full_pruning(self):
        scorer=self.fixture();paths={f'MESS0{i}':[96] for i in range(1,5)}
        q=scorer.score(paths)
        self.assertIsNone(q['score']);self.assertEqual(q['LP_status'],2)
        self.assertTrue(q['heuristic_only'])

    def test_incomplete_time_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError,'ALL96'):
            DispatchScore(None,None,dict(rows=[dict(slot=0)]))

if __name__=='__main__':unittest.main()
