"""Behavioral and authority checks; synthetic gradients never update weights."""
import unittest,argparse,time
from .common import *
from .causal_snapshot import *
from .metrics import *

class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=np.load(OUT/'causal_dataset.npz');cls.info=pd.read_parquet(OUT/'V40R3_LABEL_MATURITY_LEDGER.parquet')
        cls.jobs=pd.read_parquet(OUT/'GPU_related_candidates_preMay.parquet')
        cls.bins=pd.read_parquet(OUT/'arrival_bins_with_maturity.parquet')
        cls.reg=read('V40R3_PREREGISTRATION.json')
    def test_01_start(self):self.assertEqual(read('V40R3_START_STATE.json')['start'],START)
    def test_02_isolation(self):
        self.assertEqual(git('branch','--show-current'),'codex/v40r3-causal-gpuwork-arrival-ml')
        self.assertEqual(ROOT.name,'MobileESS_v40r3_causal_gpuwork_arrival_ml')
    def test_03_reference_hashes(self):
        r=read('V40R3_V40P_REFERENCE_FREEZE.json');self.assertTrue(r['all_match']);self.assertEqual(r['reference_count'],188);self.assertEqual(r['model_count'],38)
    def test_04_protected_namespace(self):
        changed=git('diff','--name-only',START).splitlines()
        self.assertTrue(all(p.startswith(('dayahead/v40r3/','dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml/')) for p in changed))
        self.assertEqual(read('V40R3_START_STATE.json')['V40R2_status'],'SUPERSEDED_BY_V40R3')
    def test_05_work_units(self):self.assertIn('GPU-hour',read('V40R3_DOWNSTREAM_WORKLOAD_CONTRACT_AUDIT.json')['work_units'])
    def test_06_slow_interval(self):self.assertEqual(read('V40R3_DOWNSTREAM_WORKLOAD_CONTRACT_AUDIT.json')['slow_scheduling_grid_minutes'],30)
    def test_07_target_units(self):self.assertEqual(read('V40R3_INCREMENTAL_GPUH_TARGET_CONTRACT.json')['unit'],'GPUh')
    def toy(self):
        day='2024-04-01';o,b,e=day_contract(day)
        f=pd.DataFrame({'submit_time':[b+pd.Timedelta(minutes=2),b+pd.Timedelta(minutes=30)],
          'start_time':[b+pd.Timedelta(hours=12),b+pd.Timedelta(hours=14)],
          'end_time':[b+pd.Timedelta(hours=13),b+pd.Timedelta(hours=16)],'work_GPUh':[4.,8.],'model_cohort':[True,True]})
        return day,f
    def test_08_GPUh_sum(self):
        d,f=self.toy();y,_=incremental_target(f,d);self.assertEqual(y.sum(),12.)
    def test_09_submit_assignment(self):
        d,f=self.toy();y,_=incremental_target(f,d);np.testing.assert_array_equal(y[:2],[4,8]);self.assertEqual(y[24],0)
    def test_10_cumulative_sum(self):
        d,f=self.toy();y,_=incremental_target(f,d);np.testing.assert_array_equal(np.cumsum(y)[:3],[4,12,12])
    def test_11_cumulative_monotonic(self):self.assertTrue((np.diff(np.cumsum(self.a['target'],1),axis=1)>=0).all())
    def test_12_horizon_crossing(self):self.assertEqual(read('V40R3_TARGET_RECONSTRUCTION_VERIFICATION.json')['horizon_crossings'],0)
    def test_13_F30_removed(self):
        j=self.jobs;short=j.GPU_quantity_authorized&j.start_time.notna()&j.end_time.notna()&j.runtime_seconds.between(0,1800,inclusive='neither')&j.start_time.ge(j.submit_time)
        self.assertGreater(int(short.sum()),0);self.assertTrue(j.loc[short,'model_cohort'].all())
    def test_14_runtime_not_thresholded(self):
        j=self.jobs;expected=j.GPU_quantity_authorized&j.start_time.notna()&j.end_time.notna()&j.runtime_seconds.gt(0)&j.start_time.ge(j.submit_time)
        np.testing.assert_array_equal(j.model_cohort,expected)
    def test_15_queue_filter_absent(self):
        j=self.jobs;immediate=j.model_cohort&(j.start_time==j.submit_time)
        self.assertGreater(int(immediate.sum()),0);self.assertNotIn('queue_wait',j.columns)
    def test_16_missing_GPU_not_zero(self):self.assertTrue(self.jobs.loc[self.jobs.gpus_requested.isna(),'work_GPUh'].isna().all())
    def test_17_no_nodes_inference(self):self.assertNotIn('nodes_req',self.jobs.columns)
    def test_18_scoped_population(self):self.assertIsNone(read('V40R3_TARGET_POPULATION_COVERAGE_AUDIT.json')['total_GPUh_coverage_fraction'])
    def test_19_availability_schema(self):
        fields={'feature_name','source','value_time','available_at','forecast_origin','eligibility','authority_evidence'}
        self.assertTrue(all(fields.issubset(f) for f in read('V40R3_FEATURE_AVAILABILITY_LEDGER.json')['features']))
    def test_20_availability_cutoff(self):
        p=pd.read_parquet(OUT/'feature_available_at_proofs.parquet');self.assertTrue((p.available_at<=p.forecast_origin).all())
    def test_21_rolling_cutoff(self):
        p=pd.read_parquet(OUT/'feature_available_at_proofs.parquet');self.assertTrue((p.value_time<=p.forecast_origin).all())
    def test_22_immature_value_invariance(self):
        day='2024-10-01';o,_,_=day_contract(day);b=self.bins.copy()
        before=snapshot(b,day);idx=b.max_observed_end.gt(o)|b.unresolved_end_count.gt(0)
        b.loc[idx,'work_GPUh']=1e12
        after=snapshot(b,day);np.testing.assert_array_equal(before[0],after[0]);np.testing.assert_array_equal(before[1],after[1])
    def test_23_status_not_read(self):self.assertTrue({'state','state_simple','queue_wait'}.isdisjoint(self.jobs.columns))
    def test_24_label_maturity(self):
        for r in self.info.iloc[::31].itertuples():
            g=self.jobs.loc[self.jobs.model_cohort&self.jobs.submit_time.ge(r.target_start)&self.jobs.submit_time.lt(r.target_end)]
            expected=max(r.target_end,g.end_time.max()) if len(g) else r.target_end
            self.assertEqual(expected,r.target_label_available_at)
    def test_25_immature_history_zero_placeholder(self):
        p=self.a['past'];self.assertTrue((p[:,:,1][p[:,:,2]==0]==0).all())
    def test_26_maturity_mask(self):
        day='2024-10-01';o,_,_=day_contract(day);idx=pd.date_range(o-pd.Timedelta(hours=2),periods=4,freq='30min')
        b=self.bins.copy();b.loc[idx,'max_observed_end']=o-pd.Timedelta(minutes=1);b.loc[idx,'unresolved_end_count']=0
        b.loc[idx[-1],'max_observed_end']=o+pd.Timedelta(hours=1)
        _,_,mask=history_values(b,idx,o);np.testing.assert_array_equal(mask,[True,True,True,False])
    def test_27_temporal_split(self):
        i=self.info;self.assertLess(i.loc[i.role=='TRAIN','operating_day'].max(),i.loc[i.role=='DEVELOPMENT','operating_day'].min())
        self.assertFalse(self.reg['splits']['random_split'])
    def test_28_holdout(self):
        h=read('V40R3_UNTOUCHED_HOLDOUT_AUDIT.json');self.assertTrue(h['before_fit']);self.assertEqual(h['TRUE_CONFIRMATORY_AVAILABLE'],'NO')
    def test_29_preregistration_gate(self):
        from .train import authority
        _,commit=authority();self.assertTrue(commit)
        for p in (OUT/'fits').glob('*/*_start.json'):
            self.assertEqual(json.loads(p.read_text())['preregistration_commit'],commit)
    def test_30_registry(self):self.assertEqual(len(self.reg['models']),9)
    def test_31_lightgbm_repeat(self):
        p=OUT/'V40R3_TREE_REPRODUCTION_REPORT.json'
        if not p.exists():self.skipTest('Fitting has not run; no reproducibility claim yet')
        r=read(p.name)['models'];self.assertTrue(all(v['byte_identical_prediction_arrays'] for v in r if 'LIGHTGBM' in v['name']))
    def test_32_xgboost_repeat(self):
        p=OUT/'V40R3_TREE_REPRODUCTION_REPORT.json'
        if not p.exists():self.skipTest('Fitting has not run; no reproducibility claim yet')
        self.assertTrue(next(v for v in read(p.name)['models'] if v['name']=='XGBOOST')['byte_identical_prediction_arrays'])
    def test_33_seed_device(self):
        e=read('V40R3_COMPUTE_ENVIRONMENT.json');self.assertEqual(e['training_settings']['search_seeds'],[SEED]);self.assertIn(e['device'],['cpu','cuda:0'])
    def test_34_GPU_policy(self):
        e=read('V40R3_COMPUTE_ENVIRONMENT.json');self.assertTrue(e['CUDA_available_and_tensor_execution_verified']);self.assertFalse(e['training_settings']['mixed_precision'])
    def test_35_hurdle_math(self):
        import torch
        from .neural import mix_quantile,POS_LEVELS
        p=torch.tensor([.2,1.,0.]);grid=torch.tensor(POS_LEVELS)[None,:].repeat(3,1)*10
        np.testing.assert_allclose(mix_quantile(p,grid,.9).numpy(),[5,9,0],atol=1e-5)
    def test_36_nonnegative(self):self.assertTrue((self.a['target']>=0).all())
    def test_37_training_burst(self):
        idx=(self.info.role=='TRAIN')&self.info.stage_maturity_eligible;y=self.a['target'][idx]
        self.assertAlmostEqual(np.quantile(y[y>0],.95),self.reg['burst']['training_positive_Q95_GPUh'])
    def test_38_loss_frozen(self):
        r=read('V40R3_CMABF_LOSS_CONTRACT.json');self.assertFalse(r['target_day_loss_weights_used'])
        self.assertEqual(sha(OUT/'V40R3_CMABF_LOSS_CONTRACT.json'),self.reg['frozen_source_and_data_SHA256']['dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml/V40R3_CMABF_LOSS_CONTRACT.json'])
    def test_39_overall_gate(self):
        y=np.ones((10,48));q=np.ones((10,48,2));q[:2,:,1]=0
        self.assertEqual(gates(y,q,.5,['2024-01-01']*10)['groups']['overall']['status'],'FAIL')
    def test_40_positive_gate(self):
        y=np.ones((10,48));y[:5]=0;q=np.ones((10,48,2));q[5,:,1]=0
        self.assertEqual(gates(y,q,.5,['2024-01-01']*10)['groups']['positive']['status'],'FAIL')
    def test_41_burst_gate(self):
        y=np.ones((10,48))*2;q=np.ones((10,48,2))
        self.assertEqual(gates(y,q,1.5,['2024-01-01']*10)['groups']['burst']['status'],'FAIL')
    def test_42_month_failure_not_pooled(self):
        y=np.ones((20,48));q=np.ones((20,48,2));q[:2,:,1]=0;q[:2,:,0]=0
        g=gates(y,q,.5,['2024-01-01']*10+['2024-02-01']*10)
        self.assertEqual(g['groups']['overall']['status'],'PASS');self.assertFalse(g['all_pass'])
    def test_43_comparator_frozen(self):
        p=OUT/'V40R3_PAIRED_BOOTSTRAP_SUPERIORITY.json'
        if not p.exists():self.skipTest('No experimental superiority test yet')
        r=read(p.name);self.assertTrue(r['baseline_frozen_before_bootstrap'])
        self.assertEqual(sha(OUT/'V40R3_STRONGEST_BASELINE_SELECTION.json'),r['baseline_freeze_SHA256'])
    def test_44_paired_bootstrap(self):
        y=np.ones((14,48));r=day_block_bootstrap(y,np.zeros_like(y),y,repetitions=100)
        np.testing.assert_allclose(r['CI95'],[.9,.9]);self.assertTrue(r['paired_same_day_indices'])
    def test_45_no_win_CI_cross_zero(self):self.assertFalse(eligible_proposed(True,True,-.00001))
    def test_46_no_integration(self):self.assertFalse(read('V40R3_DOWNSTREAM_WORKLOAD_CONTRACT_AUDIT.json')['integration_authorized'])
    def test_47_May_firewall(self):
        self.assertEqual(read('V40R3_RAW_INGESTION_RECEIPT.json')['May_scientific_rows'],0)
        for c in ['submit_time','start_time','end_time']:self.assertTrue(self.jobs[c].dropna().lt(MAY).all())
    def test_48_production_q(self):self.assertEqual(self.reg['holds']['production_q'],'UNCHANGED')
    def test_49_PF(self):self.assertEqual(self.reg['holds']['PF'],.95)
    def test_50_Q_control(self):self.assertFalse(self.reg['holds']['Q_control'])
    def test_51_electrical(self):self.assertEqual(self.reg['holds']['electrical_regeneration'],'HOLD')
    def test_52_B0_B3(self):self.assertFalse(self.reg['holds']['B0_B3_electrical'])
    def test_53_FULL_MAY(self):self.assertFalse(self.reg['holds']['FULL_MAY'])
    def test_54_optimizer(self):self.assertFalse(self.reg['holds']['optimizer'])
    def test_55_exact_origin(self):
        origin,b,e=day_contract('2024-04-01');self.assertEqual(str(origin),'2024-03-31 08:00:00+00:00');self.assertEqual((e-b).total_seconds(),86400)
    def test_56_deepar_inference_no_future_target(self):
        import torch
        from .neural import seed_everything,build_model,library_batch,UNION
        seed_everything();device='cuda:0' if torch.cuda.is_available() else 'cpu'
        p=torch.zeros((2,HISTORY,len(PAST_NAMES)),device=device);f=torch.zeros((2,48,len(FUTURE_NAMES)),device=device)
        model=build_model('DEEPAR').to(device).eval();x=library_batch(p,f)
        with torch.no_grad():
            torch.manual_seed(SEED);a=model(x,n_samples=16)['prediction']
            x['decoder_cont'][:,:,UNION.index('mature_GPUh')]=1e6;x['decoder_target'][:]=1e6
            torch.manual_seed(SEED);b=model(x,n_samples=16)['prediction']
        self.assertTrue(torch.equal(a,b))
    def test_57_neural_shapes_and_gradient_contract(self):
        import torch
        from .neural import seed_everything,build_model,neural_loss,predict_neural
        seed_everything();torch.use_deterministic_algorithms(True,warn_only=True)
        device='cuda:0' if torch.cuda.is_available() else 'cpu'
        p=torch.zeros((2,HISTORY,len(PAST_NAMES)),device=device);p[:,:,2]=1
        f=torch.zeros((2,48,len(FUTURE_NAMES)),device=device);y=torch.ones((2,48),device=device)
        for name in ['TFT','DEEPAR','NHITS','CMABF','CMABF_A0','CMABF_A1','CMABF_A2']:
            model=build_model(name).to(device);before={k:v.detach().clone() for k,v in model.state_dict().items()}
            loss=neural_loss(model,name,p,f,y);loss.backward()
            self.assertTrue(all(torch.isfinite(v.grad).all() for v in model.parameters() if v.grad is not None))
            out=predict_neural(model,name,p,f,16);self.assertEqual(tuple(out.shape),(2,48,2));self.assertTrue(torch.isfinite(out).all())
            self.assertTrue(all(torch.equal(v,before[k]) for k,v in model.state_dict().items()))
    def test_58_reconstruction_all_days(self):self.assertLess(read('V40R3_TARGET_RECONSTRUCTION_VERIFICATION.json')['max_abs_difference'],1e-7)
    def test_59_training_cutoff_maturity(self):
        i=self.info.loc[(self.info.role=='TRAIN')&self.info.stage_maturity_eligible]
        self.assertTrue((i.target_label_available_at<=pd.Timestamp(self.reg['splits']['training_cutoff'])).all())
    def test_60_no_R2_code_dependency(self):
        import ast
        for p in (ROOT/'dayahead/v40r3').glob('*.py'):
            for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
                if isinstance(n,ast.ImportFrom):self.assertNotIn('v40r2',n.module or '')
                if isinstance(n,ast.Import):self.assertTrue(all('v40r2' not in a.name for a in n.names))

class RecordResult(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.records=[]
    def addSuccess(self,test):super().addSuccess(test);self.records.append({'test':test.id(),'status':'PASS'})
    def addSkip(self,test,reason):super().addSkip(test,reason);self.records.append({'test':test.id(),'status':'NOT_RUN','reason':reason})
    def addFailure(self,test,err):super().addFailure(test,err);self.records.append({'test':test.id(),'status':'FAIL','detail':self._exc_info_to_string(err,test)})
    def addError(self,test,err):super().addError(test,err);self.records.append({'test':test.id(),'status':'ERROR','detail':self._exc_info_to_string(err,test)})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=1,resultclass=RecordResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    dump('V40R3_TEST_REPORT.json' if args.final else 'V40R3_PREFIT_TEST_REPORT.json',
      {'tests':result.testsRun,'passed':len(result.records)-len(result.skipped)-len(result.errors)-len(result.failures),
       'failed':len(result.failures),'errors':len(result.errors),'not_run':len(result.skipped),'records':result.records,
       'synthetic_gradient_tests':'No optimizer, no parameter updates, no actual-data fitting','scientific_validation_is_separate':True})
    raise SystemExit(0 if result.wasSuccessful() else 1)
