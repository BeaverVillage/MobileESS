import unittest,pickle
from state13 import *

class StateTests(unittest.TestCase):
    def setUp(self):
        self.s=State({'qos':['normal'],'partition':['gpu']},0)
        self.d=dict(num_gpus_req=4,num_nodes_req=1,num_cores_req=8,requested_memory_mib=100,
                    requested_seconds=7200,array_index=None,qos='normal',partition='gpu',account='a')
    def event(self,kind,t=10,j='new'):
        e=dict(time=t,kind=kind,job_id=j)
        if kind=='SUBMIT':e['request']=self.d.copy()
        return e
    def test_strict_same_timestamp(self):
        for kind in ['SUBMIT','START','END']:
            with self.assertRaises(ValueError):self.s.apply(self.event(kind),10)
        for kind in ['SUBMIT','START','END']:self.s.apply(self.event(kind),11)
        f=self.s.predict(self.d,11)
        self.assertEqual(f['p_count'],0);self.assertEqual(f['r_count'],0);self.assertEqual(f['a_300_count'],1)
    def test_lifecycle_without_future_end(self):
        self.s.apply(self.event('SUBMIT'),11)
        self.assertEqual(self.s.predict(self.d,11)['p_count'],1)
        self.s.apply(self.event('START',20),21)
        f=self.s.predict(self.d,21)
        self.assertEqual(f['p_count'],0);self.assertEqual(f['r_num_gpus_req_sum'],4)
        self.assertEqual(f['r_age_q50'],1)
        self.assertEqual(self.s.predict(self.d,1000000)['r_count'],1)
    def test_duplicate_restart_and_window(self):
        self.s.apply(self.event('SUBMIT'),11);self.s.apply(self.event('SUBMIT'),11)
        f=self.s.predict(self.d,310);self.assertEqual(f['a_300_count'],1)
        copy=pickle.loads(pickle.dumps(self.s))
        self.assertEqual(copy.predict(self.d,311)['a_300_count'],0)
        self.assertEqual(self.s.predict(self.d,311)['a_300_count'],0)
        self.assertEqual(self.s.duplicates,1)
    def test_forbidden_unknown_and_reversal(self):
        with self.assertRaises(ValueError):self.s.predict({**self.d,'end_time':100},12)
        with self.assertRaises(ValueError):self.s.apply(self.event('START'),12)
        self.s.apply(self.event('SUBMIT'),11)
        f=self.s.predict({**self.d,'qos':'unseen','account':'unseen'},11)
        self.assertEqual(f['a_same_account_3600'],0)
        with self.assertRaises(ValueError):self.s.predict(self.d,10)
        with self.assertRaises(ValueError):self.s.apply(self.event('END',9),12)
    def test_end_pending_and_late_start(self):
        self.s.apply(self.event('SUBMIT'),11)
        self.s.apply(self.event('END',12),14);self.s.apply(self.event('START',13),14)
        f=self.s.predict(self.d,14);self.assertEqual(f['p_count']+f['r_count'],0)
    def test_bag_quantile_and_sums(self):
        b=Bag();d=descriptor(self.d)
        for t in [1,2,3,4]:b.update(d,t,1)
        f=b.base('r_',10,'running');self.assertEqual(f['r_age_q90'],8.7)
        for t in [2,4,1,3]:b.update(d,t,-1)
        self.assertEqual(b.sums['num_gpus_req'],0);self.assertEqual(b.n,0)
    def test_within_timestamp_identity_permutation(self):
        states=[State({'qos':['normal'],'partition':['gpu']},0) for _ in range(2)]
        for s in states:
            for j,t,gpu in [('z',1,4),('a',2,8),('m',3,16)]:
                e=self.event('SUBMIT',t,j);e['request']['num_gpus_req']=gpu;s.apply(e,4)
        for s,order in zip(states,[['z','a','m'],['a','m','z']]):
            for j in order:s.apply(self.event('START',5,j),6)
        left=states[0].predict(self.d,6);right=states[1].predict(self.d,6)
        for key in left:
            if math.isnan(left[key]):self.assertTrue(math.isnan(right[key]))
            else:self.assertEqual(left[key],right[key])
if __name__=='__main__':unittest.main()
