import unittest
from embedding_audit import exact_audit, COLS
from common import *
def frame(records,side):
    d=pd.DataFrame(records,columns=COLS)
    if side=='h':d['historic_row']=np.arange(len(d));d['job_id']=np.arange(len(d))
    else:d['embedding_global_row']=np.arange(len(d));d['embedding_chunk']=0;d['embedding_row_in_chunk']=np.arange(len(d))
    return d
class ExactLinkTests(unittest.TestCase):
    def test_ambiguous_groups_never_assign_first_row(self):
        h=frame([[1,2,3,4.,5.],[1,2,3,4.,5.],[11,12,13,14.,15.]],'h')
        e=frame([[1,2,3,4.,5.],[1,2,3,4.,5.],[11,12,13,14.,15.]],'e')
        s,l,_=exact_audit(h,e,['submit_time','end_time'])
        self.assertEqual(s['unique_1to1'],1);self.assertEqual(s['keys_manyToMany'],1)
        self.assertEqual(s['ambiguous_embedding_rows'],2);self.assertEqual(l.historic_row.notna().sum(),1)
    def test_holdout_contradiction_is_not_success(self):
        h=frame([[1,2,3,4.,5.]],'h');e=frame([[1,22,3,4.,5.]],'e')
        s,l,_=exact_audit(h,e,['submit_time','end_time','wallclock_used_sec','avg_power_per_node'])
        self.assertEqual(s['contradictory_1to1_rows'],1);self.assertEqual(l.diagnostic_status.iloc[0],'CONTRADICTION')
    def test_null_keys_do_not_match(self):
        h=frame([[np.nan,2,3,4.,5.]],'h');e=frame([[np.nan,2,3,4.,5.]],'e')
        s,l,_=exact_audit(h,e,['submit_time','end_time'])
        self.assertEqual(s['exact_matched_keys'],0);self.assertEqual(s['unmatched_embedding_rows'],1)
    def test_float_nextafter_is_not_tolerance_matched(self):
        h=frame([[1,2,3,4.,5.]],'h');e=frame([[1,2,3,4.,np.nextafter(5.,6.)]],'e')
        s,_,_=exact_audit(h,e,['submit_time','end_time','wallclock_used_sec','avg_power_per_node'])
        self.assertEqual(s['exact_matched_keys'],0)
    def test_one_to_many_and_many_to_one_separate(self):
        h=frame([[1,2,3,4.,5.],[11,12,13,14.,15.],[11,12,13,14.,15.]],'h')
        e=frame([[1,2,3,4.,5.],[1,2,3,4.,5.],[11,12,13,14.,15.]],'e')
        s,l,_=exact_audit(h,e,['submit_time','end_time'])
        self.assertEqual(s['keys_1toMany'],1);self.assertEqual(s['keys_manyTo1'],1)
        self.assertEqual(s['ambiguous_embedding_rows'],3);self.assertTrue(l.historic_row.isna().all())
    def test_missing_holdout_is_not_pass(self):
        h=frame([[1,2,3,4.,np.nan]],'h');e=frame([[1,2,3,4.,np.nan]],'e')
        s,_,_=exact_audit(h,e,['submit_time','end_time'])
        self.assertEqual(s['contradictory_1to1_rows'],1)
if __name__=='__main__':unittest.main()
