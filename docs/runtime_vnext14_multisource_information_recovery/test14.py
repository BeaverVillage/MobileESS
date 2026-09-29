import unittest
from common14 import *
from join14 import keys_summary


class ExactIdentitySafety(unittest.TestCase):
    def test_same_numeric_id_is_not_same_job(self):
        a=pd.DataFrame({'job_id':[7],'submit_time':pd.to_datetime(['2024-01-01'],utc=True)})
        b=pd.DataFrame({'job_id':[7],'submit_time':pd.to_datetime(['2024-01-02'],utc=True)})
        self.assertEqual(keys_summary(a,b,['job_id'])['one_to_one_exact_matches'],1)
        self.assertEqual(keys_summary(a,b,['job_id','submit_time'])['one_to_one_exact_matches'],0)

    def test_duplicate_keys_never_become_one_to_one(self):
        a=pd.DataFrame({'job_id':[7,7]});b=pd.DataFrame({'job_id':[7]})
        result=keys_summary(a,b,['job_id'])
        self.assertEqual(result['ambiguous_shared_keys'],1)
        self.assertEqual(result['one_to_one_exact_matches'],0)

    def test_timezone_conversion_preserves_exact_instant(self):
        a=pd.DataFrame({'job_id':[7],'submit_time':pd.to_datetime(['2024-01-01T00:00:00-06:00'],utc=True)})
        b=pd.DataFrame({'job_id':[7],'submit_time':pd.to_datetime(['2024-01-01T06:00:00Z'],utc=True)})
        self.assertEqual(keys_summary(a,b,['job_id','submit_time'])['one_to_one_exact_matches'],1)

    def test_near_timestamp_is_not_exact_match(self):
        a=pd.DataFrame({'job_id':[7],'submit_time':pd.to_datetime(['2024-01-01T00:00:00Z'],utc=True)})
        b=pd.DataFrame({'job_id':[7],'submit_time':pd.to_datetime(['2024-01-01T00:00:01Z'],utc=True)})
        self.assertEqual(keys_summary(a,b,['job_id','submit_time'])['common_keys'],0)

    def test_missing_id_is_not_physical_identity(self):
        # Missing values must be separately marked ambiguous, never evidence of identity.
        a=pd.DataFrame({'job_id':[None]});b=pd.DataFrame({'job_id':[None]})
        self.assertEqual(keys_summary(a,b,['job_id'])['one_to_one_exact_matches'],0)


if __name__=='__main__':unittest.main()
