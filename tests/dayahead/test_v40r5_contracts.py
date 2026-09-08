from pathlib import Path
import sys,unittest,argparse,ast
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40r5.common import *
from dayahead.v40r5.phase0 import bin_ns,power_30_to_15
from dayahead.v40r5.metrics import *
from dayahead.v40r5.models import envelope_fit
CLOSURE=False

class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a,cls.i,cls.m=data();cls.r=read('V40R5_PREREGISTRATION.json');cls.u=cls.r['burst_threshold_GPUh']
        cls.j=pd.read_parquet(OUT/'inputs/GPU_related_candidates_preMay.parquet');cls.events=cls.j.loc[cls.j.model_cohort].copy()
        cls.ix=bin_ns(ns(cls.events.submit_time),cls.i.target_start.iloc[0].value);cls.inside=(cls.ix>=0)&(cls.ix<33504)
        cls.proof=pd.read_parquet(OUT/'seasonal_maturity_proof.parquet')
    def exists(self,name):
        if not (OUT/name).exists():self.skipTest('Not executed before preregistration / pending final closure: '+name)
        return read(name) if name.endswith('.json') else OUT/name
    def q(self):return np.load(self.exists('frozen_pipeline_predictions.npz'))
    def hold(self,name,value=False):self.assertEqual(self.r['holds'][name],value)
    def scope(self):self.assertTrue(all(allowed(p) for p in git('diff','--name-only',BASE).splitlines()+git('ls-files','--others','--exclude-standard').splitlines()))
    def toy_detector(self):return detector(np.array([0.,1.,10.,20.]),np.array([.1,.2,.9,.1]),.5,5.)
    def test_01_receipt_full(self):self.assertEqual(git('rev-parse','--verify','ff1fec3a^{commit}'),BASE);self.assertEqual(len(BASE),40)
    def test_02_ancestry(self):self.assertEqual(git('merge-base','--is-ancestor','a925a34848458b07b2a07a43b1150c89c21425b9',BASE),'')
    def test_03_isolated_worktree(self):self.assertEqual(ROOT.name,'MobileESS_v40r5_15min_selective_burst_gpuwork');self.assertEqual(git('branch','--show-current'),'codex/v40r5-15min-selective-burst-gpuwork')
    def test_04_initial_clean(self):self.assertTrue(read('V40R5_START_STATE.json')['initial_worktree_clean_before_R5_files']);self.assertTrue(read('V40R5_START_STATE.json')['parent_worktree_clean'])
    def test_05_eligible(self):self.assertEqual(int(self.j.model_cohort.sum()),548339)
    def test_06_GPU_missing(self):self.assertEqual(int(self.j.gpus_requested.isna().sum()),240050);self.assertTrue(self.j.loc[self.j.gpus_requested.isna(),'work_GPUh'].isna().all())
    def test_07_contributors(self):self.assertEqual(int(self.inside.sum()),545553)
    def test_08_days(self):self.assertEqual(len(self.i),349)
    def test_09_intervals(self):self.assertEqual(len(self.a['y']),33504)
    def test_10_slot_boundaries(self):np.testing.assert_array_equal(np.diff(self.a['slot_start_ns']),np.full(33503,STEP))
    def test_11_timestamp_units(self):
        for row in read('V40R5_TIME_UNIT_CONTRACT.json')['fields']:self.assertEqual(row['canonical_unit'],'datetime64[ns, UTC]')
        np.testing.assert_array_equal(ns(self.events.submit_time),self.events.submit_time.dt.as_unit('ns').astype('int64').to_numpy())
    def test_12_exact_boundary(self):np.testing.assert_array_equal(bin_ns(np.array([-1,0,STEP-1,STEP,96*STEP]),0),[-1,0,0,1,96])
    def test_13_GPUh_total(self):self.assertAlmostEqual(float(self.a['y'].sum()),1904541.778333334,places=7)
    def test_14_pair_identity(self):
        p=np.load(OUT/'inputs/causal_dataset.npz')['target'];np.testing.assert_allclose(self.a['y'].reshape(349,48,2).sum(2),p,atol=1e-7,rtol=0)
    def test_15_error_bound(self):self.assertLessEqual(read('V40R5_15MIN_30MIN_AGGREGATION_AUDIT.json')['max_abs_error_GPUh'],1e-7)
    def test_16_no_half_splitting(self):self.assertFalse(read('V40R5_15MIN_TARGET_CONTRACT.json')['half_split']);self.assertTrue(np.any(np.diff(self.a['y'].reshape(-1,2),axis=1)!=0))
    def test_17_submit_event_reconstruction(self):
        e=self.events;z=e.gpus_requested.to_numpy()*(ns(e.end_time)-ns(e.start_time))/3.6e12
        np.testing.assert_allclose(np.bincount(self.ix[self.inside],weights=z[self.inside],minlength=33504),self.a['y'],atol=1e-7,rtol=0)
        np.testing.assert_array_equal(np.bincount(self.ix[self.inside],minlength=33504),self.a['n'])
    def test_18_power_duplication(self):np.testing.assert_array_equal(power_30_to_15(np.arange(48)),np.repeat(np.arange(48),2))
    def test_19_power_energy(self):
        p=np.arange(48)*3.125;np.testing.assert_array_equal(power_30_to_15(p).reshape(48,2).sum(1)*.25,p*.5)
    def test_20_no_interpolation(self):
        p=np.arange(48)**2;x=power_30_to_15(p);np.testing.assert_array_equal(x[::2],x[1::2]);self.assertFalse(read('V40R5_AEMO_30_TO_15_AUDIT.json')['linear_interpolation'])
    def test_21_feature_authority(self):
        r=read('V40R5_FEATURE_AUTHORITY_AUDIT.json');self.assertEqual(r['feature_count'],self.a['X'].shape[1])
        for f in r['features']:self.assertTrue(all(k in f for k in ['feature_name','source','available_at','native_resolution','15min_alignment_rule','causal_status','label_maturity_rule']))
    def test_22_no_future_features(self):
        p=np.load(OUT/'feature_availability.npz');self.assertTrue((p['available_ns']<=p['origin_ns'][:,None]).all());self.assertFalse(read('V40R5_FEATURE_AUTHORITY_AUDIT.json')['future_job_features'])
    def test_23_maturity(self):
        p=self.proof;self.assertTrue((p.loc[p.mature,'parent_available_ns']<=p.loc[p.mature,'origin_ns']).all());self.assertTrue((p.loc[~p.mature,['published_GPUh','published_count']]==0).all().all())
    def test_24_no_origin_plus15(self):self.assertLessEqual(read('V40R5_CAUSALITY_FIREWALL.json')['max_available_minus_origin_ns'],0);self.assertGreater(STEP,0)
    def test_25_no_future_completion_lag(self):
        p=self.proof;future=p.parent_available_ns>p.origin_ns;self.assertFalse(p.loc[future,'mature'].any());self.assertTrue((p.loc[future,'published_GPUh']==0).all())
    def test_26_splits(self):
        expected={'TRAIN':('2024-03-15','2024-08-30',167),'DEVELOPMENT':('2024-09-01','2024-10-30',58),'CALIBRATION':('2024-11-01','2024-11-29',26),'EXPOSED_EVALUATION':('2024-12-01','2025-02-26',88)}
        for role,(start,end,n) in expected.items():
            rows=self.i[self.i.role==role];self.assertEqual((rows.operating_day.min(),rows.operating_day.max(),int(rows.stage_maturity_eligible.sum())),(start,end,n))
    def test_27_confirmation(self):self.assertEqual(read('V40R5_UNTOUCHED_CONFIRMATION_AUDIT.json')['TRUE_CONFIRMATORY_AVAILABLE'],'NO')
    def test_28_burst_TRAIN_only(self):
        y=self.a['y'][self.m['TRAIN']];self.assertAlmostEqual(self.u,float(np.quantile(y[y>0],.95)));self.assertEqual(self.r['burst_operator'],'>')
    def test_29_no_R4_threshold(self):self.assertNotAlmostEqual(self.u,441.777542);self.assertFalse(read('V40R5_BURST_THRESHOLD_FREEZE.json')['R4_threshold_reused'])
    def test_30_body_training_mask(self):
        r=self.exists('fits/PB1/result.json');expected=int((self.m['TRAIN']&(self.a['y']<=self.u)).sum())
        for run in r['runs']:self.assertEqual(run['fit_rows'],expected);self.assertTrue(run['body_training_excludes_bursts'])
    def test_31_body_quantile_order(self):
        for key in ['body_raw','body_selected','body_BC1']:
            q=self.q()[key];self.assertTrue((q[:,0]<=q[:,1]).all())
    def test_32_body_nonnegative(self):
        q=self.q();self.assertTrue((q['body_selected']>=0).all());self.assertTrue((q['body_selected']<=self.u+1e-7).all())
    def test_33_count_causal_crossfit(self):
        r=self.exists('fits/N1/audit.json');self.assertFalse(r['future_realized_N_input'])
        for fold in r['folds']:
            if fold['max_training_label_available_at']:self.assertLessEqual(pd.Timestamp(fold['max_training_label_available_at']),pd.Timestamp(fold['fit_label_cutoff']))
    def test_34_predicted_count_only(self):
        x=np.load(self.exists('classifier_X.npy'));p=np.load(self.exists('fits/N1/predictions.npz'))['TRAIN_crossfit_N1']
        # Validate exact preregistered float32 conversion, including tiny-probability underflow.
        np.testing.assert_array_equal(x[:,-2],np.log1p(p[:,0]).astype(np.float32));np.testing.assert_array_equal(x[:,-1],p[:,2].astype(np.float32))
    def test_35_classifier_causal_inputs(self):
        x=np.load(self.exists('classifier_X.npy'));self.assertEqual(x.shape[1],63);np.testing.assert_array_equal(x[:,:61],self.a['X'])
    def test_36_eta_CAL_only(self):
        r=self.exists('V40R5_ETA_SELECTION.json');self.assertEqual(r['source'],'CALIBRATION ONLY');self.assertFalse(r['evaluation_tuning'])
        y=np.array([0.,10.,20.,0.]);p=np.array([.9,.7,.2,.1]);r=choose_eta(y,p,5.);self.assertAlmostEqual(r['eta'],.2)
    def test_37_burst_recall(self):self.assertEqual(self.toy_detector()['recall'],.5)
    def test_38_weighted_recall(self):self.assertAlmostEqual(self.toy_detector()['GPUh_weighted_recall'],1/3)
    def test_39_captured_GPUh(self):self.assertEqual(self.toy_detector()['captured_burst_GPUh'],10.)
    def test_40_false_negatives(self):self.assertEqual(self.toy_detector()['FN'],1)
    def env(self):return envelope_fit(np.array([1.,2.,10.,20.,30.]),np.array([.1,.3,.1,.3,.1]),np.array([0,48,0,48,24]),np.array([1,1,0,0,0],bool),np.array([0,0,1,1,1],bool),5.)
    def test_41_R0(self):self.assertAlmostEqual(self.env()[1]['R0']['value_GPUh'],28.)
    def test_42_R1(self):self.assertAlmostEqual(self.env()[1]['R1']['value_GPUh'],29.)
    def test_43_R2_fallback(self):
        e,r,paths=self.env();np.testing.assert_array_equal(e['R2'],e['R0']);self.assertTrue((paths=='global').all());np.testing.assert_array_equal(self.env()[0]['R2'],e['R2'])
    def test_44_no_additive_calibration(self):
        self.assertFalse(self.r['body_calibration']['global_additive_GPUh']);q=np.array([1.,2.,3.]);s=log_score((q+1)*2-1,q);self.assertAlmostEqual(s,np.log(2));np.testing.assert_allclose(calibrate_body(q,s,100),[3,5,7])
    def test_45_selective_logic(self):
        np.testing.assert_array_equal(hybrid(np.array([[1.,2.],[2.,3.]]),np.array([.1,.2]),.2,np.array([10.,20.])),[2.,20.])
        p=self.q();f=read('V40R5_CAL_SELECTION_FREEZE.json')['frozen_diagnostic_pipeline'];np.testing.assert_array_equal(p['selected_safe'],hybrid(p['body_selected'],p['burst_probability'],f['eta'],p['robust_upper']))
    def test_46_full_denominator(self):
        r=self.exists('V40R5_HYBRID_METRICS.json')['metrics'];self.assertEqual(r['N'],8448);self.assertEqual(r['coverage']['burst']['N'],int((self.a['y'][self.m['EXPOSED_EVALUATION']]>self.u).sum()))
    def test_47_primary_15min(self):self.assertEqual(self.r['target'],'Exogenous arriving GPUh, original submit-event 15min x96');self.assertEqual(len(self.a['y'])//349,96)
    def test_48_30min_secondary(self):
        r=self.exists('V40R5_30MIN_SECONDARY_DIAGNOSTIC.json');self.assertFalse(r['primary_resolution']);self.assertEqual(r['intervals'],4224)
    def test_49_60min_secondary(self):
        r=self.exists('V40R5_60MIN_SECONDARY_DIAGNOSTIC.json');self.assertFalse(r['primary_resolution']);self.assertEqual(r['intervals'],2112)
    def test_50_cumulative_scenarios(self):
        draws=np.array([[0.,10.],[10.,0.]]);self.assertEqual(np.quantile(draws.sum(0),.9),10.);self.assertNotEqual(np.quantile(draws,.9,axis=1).sum(),10.)
        r=self.exists('V40R5_BASELINE_B3_REPORT.json');self.assertEqual(r['true_scenario_cumulative_horizon_crossing'],0)
    def test_51_horizon(self):
        p=self.q()['selected_safe'].reshape(-1,96);self.assertTrue((np.diff(p.cumsum(1),axis=1)>=0).all())
    def imports(self):
        for p in (ROOT/'dayahead/v40r5').glob('*.py'):
            for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
                if isinstance(node,ast.Import):yield from (v.name for v in node.names)
                if isinstance(node,ast.ImportFrom):yield node.module or ''
    def test_52_no_optimizer(self):self.scope();self.assertFalse(any('optimizer' in n for n in self.imports()));self.hold('optimizer')
    def test_53_no_Gurobi(self):self.assertFalse(any('gurobi' in n.lower() for n in self.imports()));self.hold('Gurobi')
    def test_54_no_OpenDSS(self):self.assertFalse(any('dss' in n.lower() for n in self.imports()));self.hold('OpenDSS')
    def test_55_A0(self):self.scope();self.hold('A0')
    def test_56_A1(self):self.scope();self.hold('A1')
    def test_57_M1(self):self.scope();self.hold('M1')
    def test_58_MF(self):self.scope();self.hold('MF')
    def test_59_migration(self):self.hold('migration')
    def test_60_WAN(self):self.hold('WAN')
    def test_61_terminal(self):self.hold('terminal')
    def test_62_event_trigger(self):self.hold('event_trigger')
    def test_63_local_repair(self):self.hold('local_repair')
    def test_64_May(self):
        for col in ['submit_time','start_time','end_time']:self.assertTrue(self.j[col].dropna().lt(MAY).all())
        self.assertEqual(self.r['May_scientific_reads'],0)
    def test_65_q(self):self.hold('production_q','UNCHANGED')
    def test_66_PF(self):self.hold('PF',.95)
    def test_67_Q(self):self.hold('Q_control')
    def test_68_electrical(self):self.hold('electrical','HOLD')
    def test_69_B0_B3(self):self.hold('electrical_B0_B3')
    def test_70_FULL_MAY(self):self.hold('FULL_MAY')
    def test_71_integration(self):self.hold('optimizer');self.hold('V40S2')
    def protected(self,which,root):
        for row in read('V40R5_PROTECTED_SCOPE_START.json')['files']:
            if row['root']==which:self.assertEqual(sha(root/row['path']),row['SHA256'],row['path'])
    def test_72_R3_hashes(self):self.protected('R3',R3)
    def test_73_R4_hashes(self):self.protected('R4',R4)
    def test_74_required_files(self):
        if not CLOSURE:self.skipTest('Receipt/closure artifacts intentionally follow research commit')
        self.assertEqual([n for n in read('V40R5_REQUIREMENTS_MANIFEST.json')['required_artifacts'] if not (OUT/n).exists()],[])
    def test_75_final_clean(self):
        if not CLOSURE:self.skipTest('Final clean check runs after receipt commit')
        self.assertEqual(git('status','--porcelain'),'');self.scope()

class Recording(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.records=[]
    def addSuccess(self,t):super().addSuccess(t);self.records.append({'test':t.id().split('.')[-1],'status':'PASS'})
    def addSkip(self,t,r):super().addSkip(t,r);self.records.append({'test':t.id().split('.')[-1],'status':'NOT_RUN','reason':r})
    def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'test':t.id().split('.')[-1],'status':'FAIL','detail':self._exc_info_to_string(e,t)})
    def addError(self,t,e):super().addError(t,e);self.records.append({'test':t.id().split('.')[-1],'status':'ERROR','detail':self._exc_info_to_string(e,t)})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--final',action='store_true');p.add_argument('--closure',action='store_true');p.add_argument('--read-only',action='store_true');args=p.parse_args();CLOSURE=args.closure
    result=unittest.TextTestRunner(verbosity=1,resultclass=Recording).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    report={'tests':result.testsRun,'passed':sum(r['status']=='PASS' for r in result.records),'failed':len(result.failures)+len(result.errors),'not_run':len(result.skipped),'records':result.records,'scientific_safety_is_separate':True}
    if not args.read_only:dump('V40R5_TEST_REPORT.json' if args.final else 'V40R5_PREFIT_TEST_REPORT.json',report)
    raise SystemExit(0 if result.wasSuccessful() else 1)
