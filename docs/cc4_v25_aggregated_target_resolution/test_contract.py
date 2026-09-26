"""Structural contracts for frozen-family resolution comparison."""
import unittest
import json
import numpy as np
import pandas as pd
import study as s


class Contracts(unittest.TestCase):
    def test_nonoverlap_mass_and_prefix_inverse(self):
        y = np.arange(48, dtype=float).reshape(2, 24)
        for r in ['H1', 'H3', 'H6']:
            np.testing.assert_array_equal(s.aggregate(y, r).sum(1), y.sum(1))
        prefix = s.aggregate(y, 'CUM')
        np.testing.assert_array_equal(np.diff(np.c_[np.zeros(2), prefix], axis=1), y)
        np.testing.assert_array_equal(prefix[:, -1], y.sum(1))
        self.assertFalse(np.array_equal(prefix.sum(1), y.sum(1)))

    def test_anchor_features_no_transformation(self):
        expected = {'H1': list(range(24)), 'H3': list(range(2, 24, 3)), 'H6': [5, 11, 17, 23], 'CUM': list(range(24))}
        for r, anchors in expected.items():
            np.testing.assert_array_equal(s.spans(r)[0], anchors)
            self.assertEqual(s.X[:, anchors].shape, (443, len(anchors), 71))

    def test_common_normalizer_and_train_only_thresholds(self):
        self.assertEqual(s.SCALE, s.Y[s.TR].mean())
        self.assertAlmostEqual(s.thresholds('H1')[0], 860.3532222222221)
        for r in ['H3', 'H6']:
            y = s.aggregate(s.Y[s.TR], r)
            np.testing.assert_array_equal(s.thresholds(r), np.full(y.shape[1], np.quantile(y[y > 0], .95)))
        y = s.aggregate(s.Y[s.TR], 'CUM')
        np.testing.assert_array_equal(s.thresholds('CUM'), [np.quantile(v[v > 0], .95) for v in y.T])

    def test_full_day_maturity_and_unchanged_parent_membership(self):
        for i in s.OOS:
            ids = s.membership(i)
            self.assertTrue((s.AV.iloc[ids] < s.ISS.iloc[i]).all())
            self.assertTrue((s.ISS.iloc[ids] < s.ISS.iloc[i]).all())
            self.assertTrue(s.L.split.iloc[ids].ne('PURGE').all())
            parent = np.load(s.PARENT / 'fits' / s.DAYS[i] / 'TRAIN_MEMBERSHIP.npz')
            np.testing.assert_array_equal(ids, parent['day_indices'])
            np.testing.assert_array_equal(s.weights(ids, i), parent['weights'])

    def test_parameters_and_h1_frozen(self):
        old = json.loads((s.REFIT / 'PROTOCOL.json').read_text(encoding='utf-8'))
        self.assertEqual(s.PARAMS, old['parameters'])
        np.testing.assert_array_equal(s.aggregate(s.H1, 'H1'), s.H1)
        self.assertTrue(np.isfinite(s.H1[s.OOS]).all())

    def test_duration_normalization_and_terminal_reserve(self):
        y = np.full((2, 24), 10.)
        q = np.stack([y, y + 10], axis=-1)
        scores = []
        for r in s.RESOLUTIONS:
            a, b = s.aggregate(y, r), s.aggregate(q, r)
            m = s.metrics(a, b, r, threshold=np.zeros(a.shape[1]))
            self.assertAlmostEqual(m['requirement_ratio'], 2.)
            self.assertEqual(m['actual_primary_GPUh'], 480.)
            scores.append(m['normalized_Q90_pinball'])
        np.testing.assert_allclose(scores, scores[0], rtol=0, atol=1e-15)

    def test_no_cum_projection(self):
        y = np.array([[1., 2., 3.]])
        q = np.array([[[1., 2.], [.5, 1.], [2., 4.]]]); before = q.copy()
        m = s.metrics(y, q, 'CUM', threshold=np.zeros(3), duration=np.arange(1, 4))
        np.testing.assert_array_equal(q, before)
        self.assertEqual(m['prefix_downward_pairs_Q90'], 1)
        self.assertEqual(m['max_prefix_drop_GPUh'], 1.)

    def test_selection_boundaries_and_preference_only_coverage(self):
        base = dict.fromkeys(s.METRIC_NAMES, .1)
        base.update(high_load_coverage=.1, normalized_Q90_pinball=.2, requirement_ratio=1.)
        good = base | dict(high_load_coverage=.15, Q90_coverage=.7, requirement_ratio=1.99)
        self.assertTrue(s.criteria(good, base)[0])
        self.assertFalse(s.criteria(good | {'requirement_ratio': 2.}, base)[0])
        self.assertFalse(s.criteria(good | {'high_load_coverage': .149}, base)[0])
        self.assertFalse(s.criteria(good | {'normalized_Q90_pinball': .200001}, base)[0])
        with self.assertRaises(AssertionError): s.criteria(good | {'requirement_ratio': np.nan}, base)

    def test_bootstrap_invalid_draws_fail_closed(self):
        # One of two days has high-load support, so some complete-day samples have none.
        a = np.array([[1, 1, 1, 1, 1, 1, .2, 1, 1, .1], [1, 1, 1, 1, 0, 0, .2, 1, 1, .1]], float)
        result = {row['metric']: row for row in s.paired(a, a.copy(), 1)}
        self.assertGreater(result['high_load_coverage']['nonfinite_draws'], 0)
        self.assertTrue(np.isnan(result['high_load_coverage']['CI95_low']))
        self.assertEqual(result['normalized_Q90_pinball']['CI95_low'], 0.)

    def test_evaluation_cannot_upgrade_ineligible_development_choice(self):
        rows, intervals = [], []
        for role in s.ROLES[2:]:
            base = dict.fromkeys(s.METRIC_NAMES, .1)
            base.update(role=role, method='DIRECT', resolution='H1', requirement_ratio=1.5,
                        normalized_Q90_pinball=.2, prefix_downward_pairs_Q50=0, prefix_downward_pairs_Q90=0)
            rows.extend([base, base | dict(resolution='H3', high_load_coverage=.25, normalized_Q90_pinball=.1)])
            for metric, low, high in [('high_load_coverage', .04, .2), ('normalized_Q90_pinball', -.2, -.01)]:
                intervals.append(dict(role=role, resolution='H3', method='DIRECT', contrast='RESOLUTION_EFFECT',
                    block_observed_days=7, metric=metric, nonfinite_draws=0, CI95_low=low, CI95_high=high))
        frozen = dict(primary='H1', choices={'H3': dict(method='DIRECT', eligible=False)})
        _, verdict = s.support_decision(pd.DataFrame(rows), pd.DataFrame(intervals), frozen)
        self.assertFalse(verdict['AGGREGATED_CC4_TARGET_SUPPORTED'])
        frozen['choices']['H3']['eligible'] = True
        gates, verdict = s.support_decision(pd.DataFrame(rows), pd.DataFrame(intervals), frozen)
        self.assertTrue(verdict['AGGREGATED_CC4_TARGET_SUPPORTED'])
        self.assertFalse(verdict['primary_supported'])
        self.assertFalse(any(row['robust_five_pp_gain'] for row in gates))


if __name__ == '__main__': unittest.main()
