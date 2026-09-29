"""Small regression fixtures; no source payloads, external code execution or ML."""
import unittest
from common import np, pd, timestamp_us
from transforms import mod, KEYS, digest_frame

class AuthorityRegressionTests(unittest.TestCase):
    def test_microsecond_boundary_inclusive(self):
        cut = pd.Timestamp('2024-04-23')
        values = pd.to_datetime(['2024-04-22 23:59:59.999999',
                                 '2024-04-23 00:00:00.000000',
                                 '2024-04-23 00:00:00.000001']).as_unit('us')
        actual = values.astype('int64') >= timestamp_us(cut)
        self.assertEqual(actual.tolist(), [False, True, True])
        np.testing.assert_array_equal(actual, values >= cut)
        self.assertEqual(cut.value, timestamp_us(cut) * 1000)

    def test_local_and_utc_strip_are_distinct_fixed_offset_operations(self):
        for value in ['2024-12-17 20:40:46-06:00', '2024-03-10 02:30:00-06:00']:
            aware = pd.Timestamp(value)
            local = aware.tz_localize(None)
            utc = aware.tz_convert('UTC').tz_localize(None)
            self.assertEqual(utc - local, pd.Timedelta(hours=6))
            self.assertEqual(timestamp_us(utc) - timestamp_us(local), 21600000000)

    def test_duplicate_rows_never_receive_positional_mapping(self):
        cols = mod.COLS
        h = pd.DataFrame([[1, 2, 3, 1.0, 5.0], [1, 2, 3, 1.0, 5.0],
                          [4, 5, 6, 1.0, 5.0]], columns=cols)
        h['historic_row'] = [0, 1, 2]
        e = h[cols].copy()
        e['embedding_global_row'] = [0, 1, 2]
        e['embedding_chunk'] = [0, 0, 0]
        e['embedding_row_in_chunk'] = [0, 1, 2]
        stat, ledger, _ = mod.exact_audit(h, e, KEYS[2])
        self.assertEqual(stat['ambiguous_embedding_rows'], 2)
        self.assertEqual(stat['unique_1to1'], 1)
        self.assertTrue(ledger.iloc[:2].historic_row.isna().all())
        self.assertEqual(ledger.iloc[2].historic_row, 2)
        _, shuffled, _ = mod.exact_audit(h.iloc[::-1], e.iloc[::-1], KEYS[2])
        self.assertEqual(digest_frame(ledger.sort_values('embedding_global_row').reset_index(drop=True)),
                         digest_frame(shuffled.sort_values('embedding_global_row').reset_index(drop=True)))

    def test_exact_key_with_holdout_conflict_is_rejected(self):
        h = pd.DataFrame([[1, 2, 3, 1.0, 5.0]], columns=mod.COLS)
        h['historic_row'] = [0]
        e = h[mod.COLS].copy()
        e['start_time'] = 999
        e['embedding_global_row'] = 0
        e['embedding_chunk'] = 0
        e['embedding_row_in_chunk'] = 0
        stat, ledger, _ = mod.exact_audit(h, e, KEYS[2])
        self.assertEqual(stat['contradictory_1to1_rows'], 1)
        self.assertEqual(stat['consistent_1to1_rows'], 0)
        self.assertEqual(ledger.iloc[0].diagnostic_status, 'CONTRADICTION')

if __name__ == '__main__':
    unittest.main(verbosity=2)
