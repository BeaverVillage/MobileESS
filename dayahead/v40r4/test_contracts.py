import unittest,argparse,ast
from .common import *
from .distributions import scenarios,severity_cdf,severity_ppf,nb_logpmf
from .metrics import *

class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a,cls.i,cls.j,cls.m=data();cls.lab=np.load(OUT/'compound_labels.npz');cls.reg=read('V40R4_PREREGISTRATION.json')
    def test_01_lineage(self):self.assertEqual(git('merge-base',BASE,'HEAD'),BASE)
    def test_02_worktree(self):self.assertEqual(git('branch','--show-current'),'codex/v40r4-compound-gpuwork-arrival');self.assertEqual(ROOT.name,'MobileESS_v40r4_compound_gpuwork_arrival')
    def test_03_R3_hashes(self):
        for r in read('V40R4_V40R3_FREEZE_VERIFICATION.json')['files']:self.assertEqual(sha(R3/r['path']),r['SHA256_working'])
    def test_04_R2(self):
        self.assertEqual(read('V40R4_START_STATE.json')['V40R2_status'],'SUPERSEDED_BY_V40R3')
        path=str(R3.parent/'MobileESS_v40r2_cabo_future_workload_ml');s=read('V40R4_START_STATE.json')['protected_worktrees'][path]
        self.assertEqual(git('rev-parse','HEAD',cwd=path),s['HEAD']);self.assertEqual(git('status','--porcelain',cwd=path),s['status'])
    def test_05_protected_scope(self):
        paths=git('diff','--name-only',BASE).splitlines()+git('ls-files','--others','--exclude-standard').splitlines()
        self.assertTrue(all(p.startswith(('dayahead/v40r4/','dayahead/artifacts/v40r4_compound_gpuwork_arrival/')) for p in paths))
    def test_06_cohort(self):self.assertEqual(int(self.j.model_cohort.sum()),548339)
    def test_07_GPUh(self):self.assertAlmostEqual(self.lab['severity'].sum(),1904541.7783333336,places=7)
    def test_08_target_exact(self):np.testing.assert_array_equal(self.lab['target'],self.a['target']);self.assertEqual(self.a['target'].shape,(349,48))
    def test_09_no_F30(self):
        short=self.j.model_cohort&self.j.runtime_seconds.lt(1800);self.assertGreater(short.sum(),0)
        expected=self.j.GPU_quantity_authorized&self.j.start_time.notna()&self.j.end_time.notna()&self.j.runtime_seconds.gt(0)&self.j.start_time.ge(self.j.submit_time)
        np.testing.assert_array_equal(expected,self.j.model_cohort)
    def test_10_no_imputation(self):self.assertTrue(self.j.loc[self.j.gpus_requested.isna(),'work_GPUh'].isna().all())
    def test_11_count(self):np.testing.assert_array_equal(np.bincount(self.lab['job_interval'],minlength=self.lab['count'].size),self.lab['count'].ravel())
    def test_12_severity(self):
        j=self.j.loc[self.j.model_cohort];expected=j.gpus_requested*(j.end_time-j.start_time).dt.total_seconds()/3600
        np.testing.assert_allclose(expected,j.work_GPUh,rtol=0,atol=1e-7)
    def test_13_compound_label(self):np.testing.assert_allclose(np.bincount(self.lab['job_interval'],weights=self.lab['severity'],minlength=self.lab['target'].size),self.lab['target'].ravel(),rtol=0,atol=1e-7)
    def test_14_time_units_and_submit(self):
        j=self.j.loc[self.j.model_cohort];ix=(j.submit_time.dt.as_unit('ns').astype('int64')-self.i.target_start.iloc[0].value)//(1800*10**9)
        np.testing.assert_array_equal(ix[ix.between(0,self.a['target'].size-1)],self.lab['job_interval'])
    def test_15_availability(self):
        p=pd.read_parquet(OUT/'inputs/feature_available_at_proofs.parquet');self.assertTrue((p.available_at<=p.forecast_origin).all())
    def test_16_maturity(self):
        i=self.i.loc[self.m['TRAIN']];self.assertEqual(len(i),167);self.assertTrue(i.target_label_available_at.le(pd.Timestamp('2024-08-31 08:00',tz='UTC')).all())
        p=self.a['past'];self.assertTrue((p[:,:,1][p[:,:,2]==0]==0).all())
    def test_17_no_future_job(self):self.assertFalse(read('V40R4_CAUSAL_FEATURE_CONTRACT.json')['future_job_resources_admitted'])
    def test_18_no_future_resource(self):self.assertEqual(len(read('V40R4_CAUSAL_FEATURE_CONTRACT.json')['forbidden_future_job_features']),7)
    def test_19_diagnostic_train(self):self.assertEqual(read('V40R4_COUNT_DISTRIBUTION_DIAGNOSTIC.json')['stats']['N'],167*48)
    def test_20_tail_TRAIN(self):
        z=self.lab['severity'][np.repeat(self.m['TRAIN'],48)[self.lab['job_interval']]]
        for row in read('V40R4_SEVERITY_TAIL_DIAGNOSTIC.json')['GPD_thresholds']:self.assertAlmostEqual(np.quantile(z,row['TRAIN_quantile']),row['threshold_GPUh'])
    def test_21_no_evaluation_tail_rule(self):self.assertFalse(read('V40R4_TAIL_THRESHOLD_SELECTION.json')['future_performance_used'])
    def test_22_count_distribution(self):self.assertAlmostEqual(np.exp(nb_logpmf(np.arange(1000),3.,2.)).sum(),1.,places=9)
    def distribution(self):return {'kind':'SPLICE','loc':-1.,'sigma':.7,'ptail':.1,'tail_loc':2.,'tail_sigma':1.,'u':2.}
    def test_23_severity_positive(self):self.assertTrue((severity_ppf(np.linspace(.00001,.99999,1000),self.distribution())>0).all())
    def test_24_EVT_not_forced(self):self.assertEqual(read('V40R4_TAIL_THRESHOLD_SELECTION.json')['status'],'EVT_TAIL_NOT_SUPPORTED');self.assertEqual(self.reg['families']['B6'],'NOT_EXECUTED_EVT_TAIL_NOT_SUPPORTED')
    def test_25_CDF_continuity(self):
        p=self.distribution();self.assertAlmostEqual(float(severity_cdf(2.,p)),.9,places=12);self.assertLess(abs(severity_cdf(2-1e-8,p)-severity_cdf(2+1e-8,p)),1e-7)
        u=np.linspace(.0001,.9999,1000);np.testing.assert_allclose(severity_cdf(severity_ppf(u,p),p),u,atol=1e-9)
    def test_26_scenario_count(self):self.assertEqual(self.reg['scenario_count'],10000)
    def test_27_seed(self):
        p={'kind':'LOGNORMAL','mu':np.ones(4)*3,'r':np.ones(4)*2,'loc':np.zeros(4),'sigma':np.ones(4)*.2}
        a=scenarios(p,np.arange(4),1000,SEED);b=scenarios(p,np.arange(4),1000,SEED);np.testing.assert_array_equal(a,b)
    def test_28_MC_audit(self):
        if not (OUT/'V40R4_MONTE_CARLO_CONVERGENCE.json').exists():self.skipTest('Candidate simulations not run before preregistration')
        r=read('V40R4_MONTE_CARLO_CONVERGENCE.json');self.assertEqual(r['fixed_M'],10000);self.assertTrue(r['no_post_fit_M_change'])
        for x in r['models'].values():self.assertEqual([v['M'] for v in x['nested_prefixes']],[1000,2500,5000,10000])
    def test_29_exact_segment_sum(self):
        import torch
        z=torch.tensor([2.,3.,7.,11.],device='cuda:0',dtype=torch.float64);n=torch.tensor([2,0,1,1],device='cuda:0')
        np.testing.assert_array_equal(torch.segment_reduce(z,'sum',lengths=n).cpu().numpy(),[5,0,7,11])
    def test_30_nonnegative(self):self.assertTrue((self.lab['target']>=0).all())
    def test_31_cumulative(self):self.assertTrue((np.diff(np.cumsum(self.lab['target'],1),axis=1)>=0).all())
    def test_32_horizon_crossing(self):
        y=np.ones((10,48));cq=np.repeat(np.cumsum(y,1)[...,None],3,2);self.assertEqual(cumulative_metrics(y,cq)['horizon_crossing_count'],0)
    def test_33_additive_absent(self):self.assertFalse(self.reg['calibration']['global_additive_GPUh'])
    def test_34_logratio(self):
        np.testing.assert_allclose(calibrate(np.array([0.,1.,9.]),np.log(2)),[1,3,19])
        q=np.arange(1.,101.);y=(q+1)*3-1;self.assertAlmostEqual(calibration(y,q),np.log(3))
    def test_35_no_eval_calibration(self):self.assertIn('November CAL only',self.reg['temporal_protocol']['final_C1_fit'])
    def toy(self,qvalue=1.):
        y=np.ones((10,48));q=np.ones((10,48,3))*qvalue;return y,q
    def test_36_lower_gate(self):
        y,q=self.toy(0.);self.assertEqual(gates(y,q,.5,['2025-01-01']*10)['coverage']['overall']['status'],'FAIL')
    def test_37_positive_gate(self):
        y,q=self.toy();y[:5]=0;q[5:,:,1]=0;self.assertEqual(gates(y,q,.5,['2025-01-01']*10)['coverage']['positive']['status'],'FAIL')
    def test_38_burst_gate(self):
        y,q=self.toy(0.);self.assertEqual(gates(y,q,.5,['2025-01-01']*10)['coverage']['burst']['status'],'FAIL')
    def test_39_monthly_gate(self):
        y=np.ones((20,48));q=np.ones((20,48,3));q[:2]=0
        g=gates(y,q,.5,['2024-12-01']*10+['2025-01-01']*10)
        self.assertEqual(g['coverage']['burst']['status'],'PASS');self.assertEqual(g['temporal'][0]['burst_gate'],'FAIL');self.assertFalse(g['all_pass'])
    def test_40_upper_gate(self):
        y,q=self.toy(2.);self.assertEqual(gates(y,q,.5,['2025-01-01']*10)['coverage']['overall']['status'],'FAIL')
    def test_41_primary(self):
        y=np.array([[0.,1.,2.]]);self.assertAlmostEqual(primary(y,np.zeros_like(y)),.9)
    def test_42_burst_miss(self):
        y=np.array([[1.,10.]]);q=np.ones((1,2,3))*3;r=aggregate(y,q,5.);self.assertEqual(r['missed_burst_GPUh'],7)
    def test_43_overprediction(self):
        y=np.array([[1.,10.]]);q=np.ones((1,2,3))*3;self.assertEqual(aggregate(y,q,5.)['overprediction_GPUh'],2)
    def test_44_comparator_commit(self):
        if not (OUT/'V40R4_PAIRED_BOOTSTRAP_SUPERIORITY.json').exists():self.skipTest('Final evaluation not executed')
        r=read('V40R4_PAIRED_BOOTSTRAP_SUPERIORITY.json');c=r['baseline_commit'];p='dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_STRONGEST_BASELINE_SELECTION.json'
        b=subprocess.check_output(['git','show',c+':'+p],cwd=ROOT);self.assertEqual(hashlib.sha256(b).hexdigest(),sha(ROOT/p))
    def test_45_bootstrap(self):
        y=np.ones((14,48));r=bootstrap(y,np.zeros_like(y),y,repetitions=100);np.testing.assert_allclose(r['CI95'],[.9,.9])
    def test_46_CI_rule(self):self.assertEqual(self.reg['superiority']['CI_lower_must_exceed'],0)
    def test_47_other_benchmark(self):self.assertIn('every executed safety-eligible',self.reg['superiority']['P1_numeric_requirement'])
    def test_48_no_integration(self):self.assertFalse(self.reg['holds']['optimizer'])
    def test_49_May(self):
        for c in ['submit_time','start_time','end_time']:self.assertTrue(self.j[c].dropna().lt(MAY).all())
    def test_50_q(self):self.assertEqual(self.reg['holds']['production_q'],'UNCHANGED')
    def test_51_PF(self):self.assertEqual(self.reg['holds']['PF'],.95)
    def test_52_Q(self):self.assertFalse(self.reg['holds']['Q_control'])
    def test_53_electrical(self):self.assertEqual(self.reg['holds']['electrical'],'HOLD')
    def test_54_B0_B3(self):self.assertFalse(self.reg['holds']['B0_B3_electrical'])
    def test_55_FULL_MAY(self):self.assertFalse(self.reg['holds']['FULL_MAY'])
    def test_56_optimizer(self):self.assertFalse(self.reg['holds']['optimizer'])
    def test_57_neural_gradient_no_update(self):
        import torch
        from .neural import CCAF,deterministic,joint_loss
        deterministic();model=CCAF(self.reg['CCAF_initialization']).to('cuda:0');before={k:v.detach().clone() for k,v in model.state_dict().items()}
        p=torch.zeros((2,336,8),device='cuda:0');f=torch.zeros((2,48,15),device='cuda:0');n=torch.ones((2,48),device='cuda:0')
        s=torch.zeros((2,48,6),device='cuda:0');s[:,:,0]=1;s[:,:,1]=-1;s[:,:,2]=1
        loss=joint_loss(model(p,f),n,s,1.,self.reg['severity_split_u_GPUh']);loss.backward();self.assertTrue(torch.isfinite(loss))
        self.assertTrue(all(torch.isfinite(v.grad).all() for v in model.parameters() if v.grad is not None))
        self.assertTrue(all(torch.equal(v,before[k]) for k,v in model.state_dict().items()))
    def test_58_feature_poison(self):
        # Predictor tensors are the frozen R3 snapshots, independent of every R4 job-label array.
        p=np.load(OUT/'prepared.npz');self.assertTrue((p['past'][:,:,1][p['past'][:,:,2]==0]==0).all())
        for source in (ROOT/'dayahead/v40r4').glob('*.py'):
            tree=ast.parse(source.read_text(encoding='utf-8'))
            for n in ast.walk(tree):
                if isinstance(n,ast.ImportFrom):self.assertFalse((n.module or '').startswith(('dayahead.v40r2','dayahead.v40s2','optimizer')))
    def test_59_prereg_before_fit(self):
        if not (OUT/'V40R4_PREREGISTRATION_COMMIT_RECEIPT.json').exists():self.skipTest('Registration file not yet committed')
        from .train import authority
        _,c=authority()
        for p in (OUT/'fits').glob('*/trial_*_start.json'):self.assertEqual(json.loads(p.read_text())['commit'],c)

class Record(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.records=[]
    def addSuccess(self,t):super().addSuccess(t);self.records.append({'test':t.id(),'status':'PASS'})
    def addSkip(self,t,reason):super().addSkip(t,reason);self.records.append({'test':t.id(),'status':'NOT_RUN','reason':reason})
    def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'test':t.id(),'status':'FAIL','detail':self._exc_info_to_string(e,t)})
    def addError(self,t,e):super().addError(t,e);self.records.append({'test':t.id(),'status':'ERROR','detail':self._exc_info_to_string(e,t)})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--final',action='store_true');args=p.parse_args()
    r=unittest.TextTestRunner(verbosity=1,resultclass=Record).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    dump('V40R4_TEST_REPORT.json' if args.final else 'V40R4_PREFIT_TEST_REPORT.json',{'tests':r.testsRun,'passed':len(r.records)-len(r.skipped)-len(r.failures)-len(r.errors),
      'failed':len(r.failures),'errors':len(r.errors),'not_run':len(r.skipped),'records':r.records,'scientific_safety_is_separate':True,'synthetic_gradient_has_no_optimizer_step':True})
    raise SystemExit(0 if r.wasSuccessful() else 1)
