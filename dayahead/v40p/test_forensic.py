"""35 requested contracts. Three scientific gates deliberately remain red.

Expected failures expose genuine scientific/protocol failures, not validation passes.
Run: python -m dayahead.v40p.test_forensic
"""
from .common import *
from .backtest import registration, metrics, block_bootstrap
from .finalize import read, protected_scope
import unittest, lightgbm as lgb, io

class ForensicContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=registration()
        cls.census=read('V40P_MODEL_SOURCE_CENSUS.json')
        cls.reproduction=read('V40P_FROZEN_INFERENCE_REPRODUCTION.json')['results']
        cls.pred=pd.read_parquet(OUT/'all_predictions.parquet')
        cls.protected=protected_scope()
        cls.ledger=read('V40P_FEATURE_AVAILABILITY_LEDGER.json')['features']
        cls.fits=read('V40P_ROLLING_BACKTEST_REPORT.json')['fits']

    def test_01_start(self):
        self.assertEqual(read('V40P_START_STATE.json')['starting_commit'],START)
        self.assertEqual(git('rev-parse',START),START)
        self.assertEqual(subprocess.run(['git','merge-base','--is-ancestor',START,'HEAD'],cwd=ROOT).returncode,0)

    def test_02_v40ijkl(self):
        self.assertFalse(self.protected['outside_scope_changes'])
        self.assertTrue(all(self.protected['protected_unchanged'][n] for n in ['V40I','V40J','V40K','V40L']))

    def test_03_v40n(self):
        self.assertEqual(self.protected['V40N_content_accesses'],0)
        self.assertFalse(any('v40n/' in p.lower() for p in self.protected['changed_paths']))

    def test_04_v40m(self):
        self.assertTrue(self.protected['protected_unchanged']['V40M'])

    def test_05_model_sha(self):
        for r in self.census['models']:
            self.assertEqual(digest(OUT/'frozen_models'/(r['model_id']+'.txt')),r['receipt_SHA256'])
        for r in self.census['historical_repository_models']:
            self.assertEqual(digest(ROOT/r['path']),r['receipt_SHA256'])
        for r in read('source_snapshots.json'):
            self.assertEqual(digest(ROOT/r['snapshot']),r['sha256'])
        self.assertEqual(read('V40P_MODEL_SHA_VERIFICATION.json')['total_model_count'],38)

    def test_06_feature_order(self):
        self.assertEqual(len(self.spec['feature_order']),177)
        for r in self.census['models']:
            b=lgb.Booster(model_str=(OUT/'frozen_models'/(r['model_id']+'.txt')).read_text(encoding='utf-8'))
            self.assertEqual(b.feature_name(),self.spec['feature_order'])
        self.assertTrue(all(r['feature_order_exact'] for r in self.reproduction))

    def test_07_frozen_determinism_and_saved_predictions(self):
        # Repeat native inference without fitting and independently check the saved comparison receipt.
        x=np.random.default_rng(1234).normal(size=(16,177)).astype(np.float32)
        for r in self.census['models']:
            b=lgb.Booster(model_str=(OUT/'frozen_models'/(r['model_id']+'.txt')).read_text(encoding='utf-8'))
            np.testing.assert_array_equal(b.predict(x,num_threads=4),b.predict(x,num_threads=4))
        self.assertTrue(all(r['deterministic_max_abs_difference']==0 for r in self.reproduction))
        self.assertLess(max(r['saved_prediction_max_abs_difference'] for r in self.reproduction),1e-9)
        self.assertTrue(all(r['comparison_rows']>=17476 for r in self.reproduction))

    def test_08_target_horizons(self):
        rows=read('V40P_TARGET_CONTRACT.json')['numeric_reconstruction']
        self.assertEqual(len(rows),10)
        self.assertTrue(all(r['reconstruction_pass'] for r in rows))
        self.assertEqual(sorted(set(r['horizon_minutes'] for r in rows)),[15,30,60,120,240])

    def test_09_origin_contract(self):
        self.assertFalse(self.pred.duplicated(['phase','fold','track','horizon_minutes','timestamp_utc']).any())
        self.assertTrue((self.pred.timestamp_utc+pd.Timedelta(minutes=245)<LIMIT).all())
        for _,g in self.pred.groupby(['phase','fold','track','horizon_minutes']):
            self.assertTrue(g.timestamp_utc.is_monotonic_increasing)

    def test_10_original_split_chronology(self):
        s=pd.read_csv(OUT/'evidence/K5A/split_summary.csv').set_index('split')
        self.assertLess(pd.Timestamp(s.loc['train','maximum_feature_timestamp_utc']),pd.Timestamp(s.loc['validation','minimum_feature_timestamp_utc']))
        self.assertLess(pd.Timestamp(s.loc['validation','maximum_feature_timestamp_utc']),pd.Timestamp(s.loc['test_2025','minimum_feature_timestamp_utc']))
        self.assertEqual(read('V40P_TRUE_HOLDOUT_AUDIT.json')['A']['TRUE_FROZEN_HOLDOUT_AVAILABLE'],'NO')

    @unittest.expectedFailure
    def test_11_no_future_features(self):
        self.assertFalse(any(r['leakage_classification']=='FUTURE_LEAKAGE' for r in self.ledger),'70 original feature definitions fail the causal gate')

    @unittest.expectedFailure
    def test_12_rolling_right_edge(self):
        self.assertTrue(all(r['latest_bin_right_edge_minutes_from_t0']<=0 for r in self.ledger),'60 rolling features include the future current bin')

    def test_13_no_centered_rolling(self):
        checks=read('feature_reconstruction_checks.json')
        self.assertEqual(len(checks),165)
        self.assertTrue(all(r['algorithm_match'] for r in checks))
        self.assertTrue(all('preceding' in r['aggregation_window'].lower() for r in self.ledger if 'CURRENT ROW' in r['aggregation_window']))

    def test_14_no_future_imputation(self):
        path=OUT/'source_snapshots/kestrel_stage_k5a_ml_dataset_modular_v101/src/kestrel_k5a/features.py'
        text=path.read_text(encoding='utf-8').lower()
        self.assertNotIn('bfill',text);self.assertNotIn('interpolat',text)
        self.assertIn('no bfill',read('V40P_PREPROCESSING_LEAKAGE_AUDIT.json')['primary_models']['imputation'])

    def test_15_scaler_encoder(self):
        p=read('V40P_PREPROCESSING_LEAKAGE_AUDIT.json')['primary_models']
        self.assertEqual(p['scaler'],'none');self.assertTrue(p['categorical_encoder'].startswith('none'))
        self.assertTrue(all(r['categorical_handling'].startswith('none') for r in self.census['models']))

    def test_16_known_future_identity(self):
        p=read('job_identity_and_availability_evidence.json')
        self.assertEqual(p['known_future_overlap_total'],0);self.assertEqual(len(p['known_future_checks']),212)

    def test_17_fixed_flexible_identity(self):
        p=read('V40P_FIXED_FLEXIBLE_SEPARATION_AUDIT.json')
        self.assertEqual(p['fixed_flexible_job_overlap'],0)
        self.assertEqual(p['fixed_jobs']+p['flexible_jobs'],p['raw_jobs_checked'])
        self.assertLess(p['max_abs_fixed_plus_flex_minus_total'],1e-8)

    def test_18_rolling_chronology(self):
        self.assertEqual(len(self.fits),30)
        for r in self.fits:
            self.assertLess(pd.Timestamp(r['train_max_target_window_end']),pd.Timestamp(r['test_start']))
        self.assertEqual(len({r['fold'] for r in self.fits}),3)

    def test_19_no_diagnostic_parameter_changes(self):
        for r in self.fits:
            s=next(s for s in self.spec['models'] if s['track']==r['track'] and s['horizon_minutes']==r['horizon_minutes'])
            self.assertEqual(r['params'],s['hyperparameters'])
            self.assertEqual(r['trees'],s['hyperparameters']['n_estimators'])
            if r['model_sha256']:
                self.assertEqual(digest(OUT/'diagnostic_models'/r['fold']/(s['target']+'.txt')),r['model_sha256'])

    def test_20_preregistration_unchanged(self):
        self.assertEqual(registration(),self.spec)
        from .backtest import PREREG
        tracked=git('ls-tree','-r','--name-only',PREREG,'dayahead/artifacts/v40p_lightgbm_forecast_forensic/diagnostic_models')
        self.assertEqual(tracked,'')
        self.assertTrue(read('V40P_FROZEN_INFERENCE_REPRODUCTION.json')['phase_A_no_fit'])

    def test_21_baseline_accounting(self):
        a=self.pred.loc[self.pred.track.eq('A')]
        np.testing.assert_array_equal(a.A0_ZERO.to_numpy(),0)
        b=self.pred.loc[self.pred.track.eq('B')&self.pred.horizon_minutes.eq(15)]
        np.testing.assert_array_equal(b.prediction.to_numpy(),b.B0_PERSISTENCE.to_numpy())
        for r in summary_metric_rows():
            g=self.pred.loc[self.pred.phase.eq(r['phase'])&self.pred.track.eq(r['track'])&self.pred.horizon_minutes.eq(r['horizon_minutes'])]
            actual=metrics(g.actual,g.prediction,r['track'])
            for key in ['N','MAE','bias','shortfall','overreservation']:
                self.assertAlmostEqual(actual[key],r[key],places=6)

    def test_22_zero_denominator(self):
        m=metrics([0,0],[0,2]);self.assertIsNone(m['WAPE']);self.assertIsNone(m['normalized_shortfall']);self.assertIsNone(m['normalized_overreservation'])

    def test_23_shortfall(self):
        m=metrics([0,2,10],[1,4,3]);self.assertEqual(m['GPUh_shortfall'],7)
        self.assertEqual(m['shortfall']+m['overreservation'],m['MAE']*m['N'])

    def test_24_overreservation(self):
        m=metrics([0,2,10],[1,4,3]);self.assertEqual(m['GPUh_overreservation'],3)
        self.assertEqual(m['predicted_sum']-m['actual_sum'],m['overreservation']-m['shortfall'])

    def test_25_bootstrap_deterministic(self):
        g=self.pred.loc[self.pred.phase.eq('FROZEN_2025_PREMAY')&self.pred.track.eq('B')&self.pred.horizon_minutes.eq(60)].iloc[:3000]
        self.assertEqual(block_bootstrap(g,'B0_PERSISTENCE',n=50),block_bootstrap(g,'B0_PERSISTENCE',n=50))
        self.assertTrue(all(r['seed']==20260906 and r['replicates']==2000 for r in read('V40P_BLOCK_BOOTSTRAP_REPORT.json')))

    def test_26_horizon_diagnostics(self):
        reports=read('V40P_HORIZON_CONSISTENCY_REPORT.json')
        for r in reports:
            g=self.pred.loc[self.pred.phase.eq(r['phase'])&self.pred.track.eq('A')]
            p=g.pivot(index=['fold','timestamp_utc'],columns='horizon_minutes',values='prediction')
            v=np.diff(p.to_numpy(),axis=1)<-1e-9
            self.assertEqual(int(v.sum()),r['predicted_adjacent_crossings'])
            self.assertEqual(r['actual_adjacent_crossings'],0)
            self.assertFalse(r['outputs_repaired'])

    @unittest.expectedFailure
    def test_27_may_scientific_reads_zero(self):
        self.assertEqual(read('V40P_MAY_READ_FIREWALL.json')['MAY_SCIENTIFIC_OUTCOME_READS'],0,'Two source files exposed embedded scientific summaries; zero-read claim fails')

    def test_28_no_production_overwrite(self):
        self.assertTrue(self.protected['protected_unchanged']['production forecast models'])
        self.assertFalse(self.protected['outside_scope_changes'])

    def test_29_no_production_feature_changes(self):
        self.assertTrue(self.protected['protected_unchanged']['production features'])

    def test_30_no_production_adapter_changes(self):
        self.assertTrue(self.protected['protected_unchanged']['production adapters'])

    def test_31_pf(self):self.assertEqual(self.protected['holds']['PF'],0.95)
    def test_32_q_control(self):self.assertEqual(self.protected['holds']['Q_control'],'NO')
    def test_33_electrical_hold(self):self.assertEqual(self.protected['holds']['31_DAY_ELECTRICAL_REGENERATION'],'HOLD')
    def test_34_b0_b3(self):self.assertEqual(self.protected['holds']['B0/B1/B2/B3'],'NO')
    def test_35_full_may(self):self.assertEqual(self.protected['holds']['FULL_MAY'],'NO')

def summary_metric_rows():
    rows=[]
    for name in ['FUTURE_ARRIVAL','FIXED_LOAD']:
        rows.extend(r for r in read(f'V40P_{name}_METRICS.json')['rows'] if r['fold']=='POOLED' and r['method']=='prediction')
    return rows

def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ForensicContracts)
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    print(stream.getvalue())
    failures={t.id():tb for t,tb in result.failures+result.errors}
    expected={t.id():tb for t,tb in result.expectedFailures}
    cases=[]
    for name in unittest.defaultTestLoader.getTestCaseNames(ForensicContracts):
        key=__name__+'.ForensicContracts.'+name
        cases.append({'test':name,'scientific_contract_status':'FAIL' if key in expected else 'EXECUTION_FAILURE' if key in failures else 'PASS','expected_scientific_failure':key in expected,'detail':expected.get(key,failures.get(key,''))})
    dump('V40P_TEST_REPORT.json',{'tests_run':result.testsRun,'passed':result.testsRun-len(failures)-len(expected)-len(result.unexpectedSuccesses),'expected_scientific_failures':len(expected),'unexpected_failures':len(failures),'unexpected_successes':len(result.unexpectedSuccesses),'harness_completed_as_expected':result.wasSuccessful(),'scientific_all_gates_pass':False,'scope_note':'11/12/27 remain scientific FAIL. Passing diagnostic tests do not establish causal validity or an untouched holdout. 19 applies to V40P clones, not historical model selection.','cases':cases,'python':__import__('sys').version,'lightgbm':lgb.__version__,'numpy':np.__version__,'pandas':pd.__version__})
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':main()
