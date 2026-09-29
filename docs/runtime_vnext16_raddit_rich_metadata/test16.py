import unittest
import numpy as np
import pandas as pd
from features16 import *
from neighbors16 import *

class CausalityTests(unittest.TestCase):
    def test_rejected_outcomes(self):
        for key in FORBIDDEN|{'avg_power','future_start','future_queue_delay'}:
            with self.assertRaises(ValueError):validate_payload({key:1})

    def test_strict_completion_and_future_poison(self):
        cats=np.ones((4,10),np.int32);r=np.zeros((4,4),np.float32)
        index=CompletedNeighborIndex(np.arange(4),np.array([9,10,11,100]),cats,r,np.array([2,3,99999,999999]),[np.eye(2),np.eye(2)])
        a,ids=index.query(np.array([10]),cats[:1],r[:1])
        self.assertEqual(ids[0,0],0);self.assertTrue((ids[0,1:]==-1).all());self.assertEqual(a[0,0],2)
        index.runtime[1:]=1e15;index.codes[2:]=0;index.resources[2:]=1000
        b,ids2=index.query(np.array([10]),cats[:1],r[:1])
        np.testing.assert_equal(a,b);np.testing.assert_equal(ids,ids2)

    def test_category_bijection_and_unseen(self):
        d=pd.DataFrame({c:['a','b','a'] for c in IDENTITY+STACK})
        for c in RESOURCE:d[c]=[1,2,3]
        d['submit_time']=pd.date_range('2024-01-01',periods=3,tz='UTC')
        renamed=stable_random_rename(d)
        a=NativeAdapter().fit(d);b=NativeAdapter().fit(renamed)
        x,n,c=a.transform(d,'D2');z,nn,cc=b.transform(renamed,'D2')
        np.testing.assert_equal(x.toarray(),z.toarray());self.assertEqual(n,nn);self.assertEqual(c,cc)
        q=d.iloc[:1].copy();q['script']='never_seen_99999'
        self.assertEqual(a.codes(q)[0,6],-1)
        self.assertTrue(set(c));self.assertIn('script',n)

    def test_target_not_required(self):
        d=pd.DataFrame({c:['x','y'] for c in IDENTITY+STACK})
        for c in RESOURCE:d[c]=[1,2]
        a=NativeAdapter().fit(d)
        for arm in ['D0','D1','D2','D3','SOFTWARE_STACK','IDENTITY_ONLY']:
            x,_,_=a.transform(d,arm);self.assertEqual(x.shape[0],2)

if __name__=='__main__':unittest.main(verbosity=2)
