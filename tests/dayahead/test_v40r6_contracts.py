"""Independent numerical and lineage checks for the requested 84 obligations."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40r6.common import *
from dayahead.v40r6.metrics import upper, point, gates, choose, monthly
from dayahead.v40r6.models import repair, inverse, calibrate, calibrated
import ast

def main():
    checks=[]; prefit='--prefit' in sys.argv
    def check(name,condition):
        if not bool(condition): raise AssertionError(name)
        checks.append(name)
    reg=read('PREREGISTRATION'); f,a=data(); y=f.target_GPUh.to_numpy(); atom=np.load(R5/'data.npz')
    target=read('R5_TARGET_AUTHORITY_FREEZE'); split=read('CAL_SUBSPLIT_CONTRACT'); feature=read('FEATURE_CONTRACT')
    check('01 R5 scientific SHA exact',git('rev-parse',R5SCI)==R5SCI)
    check('02 R5 receipt SHA exact',git('rev-parse',R5REC)==R5REC)
    check('03 R5R1 receipt exact',git('log','-1','--format=%H','--','dayahead/artifacts/v40r5r1_zero_inflation_gate_correction/V40R5R1_FINAL_COMMIT_RECEIPT.json')==BASE)
    git('merge-base','--is-ancestor',BASE,'HEAD')
    check('04 isolated branch/worktree',git('branch','--show-current')=='codex/v40r6-multihorizon-cumulative-gpuwork' and ROOT.name=='MobileESS_v40r6_multihorizon_cumulative_gpuwork')
    check('05 frozen native target SHA',sha(R5/'V40R5_15MIN_TARGET_RECONSTRUCTION.parquet')==target['SHA256']==target['expected_R5_preregistered_SHA256'])
    check('06 atomic intervals',len(atom['y'])==33504)
    check('07 total GPUh',abs(atom['y'].sum()-1904541.778333334)<1e-7)
    parent=np.load(R5/'inputs/causal_dataset.npz')['target']
    check('08 15-to-30 identity',np.max(np.abs(atom['y'].reshape(349,48,2).sum(2)-parent))<1e-7)
    for number,h,n in [(9,'H1',93),(10,'H4',81),(11,'H8',65),(12,'H24',1)]:
        check(f'{number:02} {h} count/day',(f[f.horizon==h].groupby('day').size()==n).all())
    check('13 240 windows/day',(f.groupby('day').size()==240).all())
    check('14 83760 rows',len(f)==83760)
    check('15 within-day only',(f.window_start_slot>=0).all() and (f.window_end_slot_exclusive<=96).all())
    native=atom['y'].reshape(349,96)
    expected=np.array([np.sum(native[r.day_index,r.window_start_slot:r.window_end_slot_exclusive]) for r in f.itertuples()])
    check('16 every cumulative identity',np.max(np.abs(expected-y))<1e-7)
    check('17 distribution before fit',read('HORIZON_DISTRIBUTION_AUDIT')['before_fit'] and 'dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/V40R6_HORIZON_DISTRIBUTION_AUDIT.json' in reg['frozen_hashes'])
    check('18 feasibility before fit',read('EVALUATION_GATE_FEASIBILITY_AUDIT')['before_fit'])
    check('19 exact R5 split',read('TEMPORAL_SPLIT_CONTRACT')==external(R5/'V40R5_TEMPORAL_SPLIT_CONTRACT.json'))
    check('20 chronological CAL',max(split['CAL_FIT_days'])<min(split['CAL_SELECT_days']) and len(split['CAL_FIT_days'])==15 and len(split['CAL_SELECT_days'])==14)
    check('21 no day shared',not(set(split['CAL_FIT_days'])&set(split['CAL_SELECT_days'])) and f.groupby('day').analysis_role.nunique().max()==1)
    source=a['source_rows']; check('22 exact inherited features',np.array_equal(a['X'][:,:61],atom['X'][source]))
    names=feature['feature_names']; allowed_names=list(atom['feature_names'])+['window_start_slot','horizon_hours']+[n for d in [7,14,21,28] for n in [f'cumulative_lag_{d}d_GPUh',f'cumulative_lag_{d}d_mature']]
    check('23 no future target features',names==allowed_names)
    check('24 no future realized count',not feature['future_realized_features'] and not feature['burst_classifier_outputs'])
    check('25 no runtime/severity leakage',not any(n.startswith(('future_','runtime','severity')) for n in names))
    proof=pd.read_parquet(OUT/'V40R6_FEATURE_MATURITY_PROOF.parquet'); rawproof=pd.read_parquet(R5/'seasonal_maturity_proof.parquet')
    exact=True; lag_values=a['lag_values']
    for j,lag in enumerate([7,14,21,28]):
        m=proof[f'lag_{lag}d_complete_mature'].to_numpy(); at=proof[f'lag_{lag}d_latest_raw_availability_ns'].to_numpy()
        exact &= bool((at[m]<proof.issue_time_ns.to_numpy()[m]).all())
        sp=rawproof[rawproof.lag_days==lag].reset_index(drop=True)
        sm=(atom['seasonal_mask'][:,j]&(sp.parent_available_ns.to_numpy()<atom['origin_ns'])).reshape(349,96)
        sw=atom['seasonal_w'][:,j].reshape(349,96)
        for r in f.itertuples():
            sl=slice(r.window_start_slot,r.window_end_slot_exclusive); valid=sm[r.day_index,sl].all()
            exact &= valid==m[r.Index]
            exact &= abs(lag_values[r.Index,j]-(sw[r.day_index,sl].sum() if valid else 0))<1e-7
    check('26 exact complete-window maturity proof',exact and proof.inherited_available_by_issue.all())
    check('27 only three forecast families',reg['families']==['B0','B1','B2'])
    imports=[]
    for p in (ROOT/'dayahead/v40r6').glob('*.py'):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Import): imports.extend(x.name for x in node.names)
            if isinstance(node,ast.ImportFrom): imports.append(node.module or '')
    check('28 no classifier architecture',not any('xgboost' in s or 'torch' in s for s in imports))
    check('29 no eta registry','eta' not in reg)
    check('30 no burst envelope registry',set(reg['candidates'])=={'U0','U1','U2'})
    check('31 three LGB configs',reg['B2']['configs']==CONFIGS and len(CONFIGS)==3)
    check('32 DEV-only hyperparameter scope',reg['B2']['common_config_selection']=='DEVELOPMENT only')
    check('34 log1p transform',reg['B2']['target_transform']=='log1p')
    fixture=np.array([0.,1.,100.,1e7]); check('35 exact inverse transform',np.allclose(inverse(np.log1p(fixture)),fixture,rtol=1e-14))
    qq,ca=repair(np.array([[4.,2.],[1.,5.]])); check('36 crossing repair',np.array_equal(qq,[[4.,4.],[1.,5.]]) and ca['raw_crossing_count']==1)
    check('37 CAL_FIT-only calibration contract',reg['calibration']['scope']=='CAL_FIT only')
    check('39 no global delta',reg['calibration']['one_delta_per_horizon'])
    check('40 no exposed calibration',reg['exposed']['no_reselection_recalibration_refit'])
    check('41 overall coverage diagnostic only',reg['metrics']['overall_coverage']=='DIAGNOSTIC_ONLY_NO_UPPER_GATE')
    check('42 positive safety bounds',reg['gates']['positive_coverage']==[.9,.975])
    yy=np.array([0.,1.,4.,10.]); uu=np.array([1.,2.,3.,8.]); dd=np.array(['2025-01-01']*2+['2025-01-02']*2)
    mm=upper(yy,uu,dd)
    check('43 pooled metrics fixture',mm['positive_coverage']==1/3 and mm['overall_coverage_DIAGNOSTIC']==.5 and mm['under_GPUh']==3 and mm['over_GPUh']==2 and np.isclose(mm['positive_WAPE'],4/15) and np.isclose(mm['positive_pinball'],2.8/3))
    check('44 day-cluster fixture',mm['mean_supported_day_coverage']==.5 and mm['supported_days']==2)
    check('45 H4/H24 primary',reg['primary']==['H4','H24'])
    check('46 H1/H8 secondary',reg['secondary']==['H1','H8'])
    mock={'positive_coverage':.9,'supported_days':5,'mean_supported_day_coverage':.88,'over_GPUh':1.,'positive_WAPE':2.99,'under_GPUh':1.}
    gate=gates(mock,[],2.,True,is_B2=True)
    check('47 safety exact boundaries',gate['PASS'] and not gates({**mock,'positive_coverage':.89999},[],2.)['PASS'] and not gates({**mock,'positive_coverage':.976},[],2.)['PASS'])
    check('48 efficiency strict boundaries',not gates({**mock,'positive_WAPE':3.},[],2.)['PASS'] and not gates(mock,[],1.)['PASS'])
    check('49 B2 skill eligibility',not gates(mock,[],2.,False,is_B2=True)['PASS'])
    check('50 CAL_SELECT-only selection',reg['selection']['scope']=='CAL_SELECT only' and choose({'U1':{'PASS':False},'U2':{'PASS':True},'U0':{'PASS':True}})=='U2')
    check('52 no exposed reselection',reg['exposed']['NONE'].startswith('Remains NONE'))
    check('53 no exposed recalibration',reg['exposed']['no_reselection_recalibration_refit'])
    for number,name in [(54,'no burst clipping'),(55,'no label smoothing'),(56,'no winsorization')]:
        check(f'{number} {name}',np.array_equal(expected,y))
    check('57 no synthetic jobs',not reg['interface']['synthetic_jobs'])
    check('58 no synthetic runtime','synthetic_runtime' not in names)
    check('59 no synthetic migration','synthetic_migration' not in names)
    check('60 GPUh physical semantics','service-work mass' in reg['physical_semantics'])
    for num,k in [(61,'optimizer_calls'),(62,'Gurobi_calls'),(63,'OpenDSS_calls'),(64,'Fresh_calls')]:
        check(f'{num} {k} zero',reg['optimizer_firewall'][k]==0 and not any(s.startswith(('gurobi','opendss','dayahead.v37','dayahead.v40a')) for s in imports))
    protected=snapshot(); start=read('PROTECTED_SCOPE_START')
    for num,k in [(65,'A0'),(66,'A1'),(67,'M1'),(68,'MF'),(69,'migration'),(70,'WAN'),(71,'terminal')]:
        check(f'{num} {k} unchanged',not protected['protected_diff'] and protected['inherited_tree']==start['inherited_tree'])
    for num,k in [(72,'event trigger'),(73,'local repair'),(74,'rolling MPC')]: check(f'{num} {k} absent',not reg['system_changes'])
    firewall=read('MAY_FIREWALL')
    check('75 May scientific reads zero',firewall['May_scientific_reads']==0)
    check('76 shadow scientific reads zero',firewall['Apr24_30_shadow_scientific_reads']==0 and firewall['shadow_status']=='SEALED')
    for num,k,v in [(77,'production_q_seconds',5576.44921875),(78,'PF',.95),(79,'Q_control','NO'),(80,'electrical','HOLD'),(81,'FULL_MAY','NO')]: check(f'{num} hold {k}',reg['holds'][k]==v)
    check('R5/R5R1 every byte unchanged',protected['R5_R5R1_SHA256']==start['R5_R5R1_SHA256'])
    if not prefit:
        postfit_checks(check,f,a)
    if '--closure' in sys.argv:
        check('84 final Git clean',git('status','--porcelain')=='')
        check('receipt closes exact scientific commit',git('rev-parse',read('FINAL_COMMIT_RECEIPT')['scientific_commit'])==read('FINAL_COMMIT_RECEIPT')['scientific_commit'])
    report={'passed':len(checks),'failed':0,'checks':checks,'phase':'prefit' if prefit else 'closure' if '--closure' in sys.argv else 'postfit',
        'read_only':'--read-only' in sys.argv,'final_clean_check':'Measured by --closure --read-only after receipt commit'}
    if '--read-only' not in sys.argv: dump('PREFIT_TEST_REPORT' if prefit else 'TEST_REPORT',report)
    print(json.dumps(report,indent=2))

def postfit_checks(check,f,a):
    reg,pre=authority(); _,freeze,commit=selection_authority(); ex=read('EXPOSED_RESULTS')
    hyper=read('HYPERPARAMETER_FREEZE'); cal=read('HORIZON_CALIBRATION'); cp=np.load(OUT/'calibration_predictions.npz')
    check('33 common DEV-selected config',hyper['common_to_all_horizons'] and freeze['selected_config']==hyper['selected_config'])
    check('38 exactly four independently recomputed deltas',set(cal['horizons'])==set(HORIZONS))
    for h in HORIZONS:
        ix=cp['row_ids']; mask=((f.iloc[ix].horizon==h)&(f.iloc[ix].analysis_role=='CAL_FIT')).to_numpy()
        expected=max(0.,np.quantile(np.log1p(f.iloc[ix[mask]].target_GPUh)-np.log1p(cp['q'][mask,1]),.9,method='linear'))
        check(h+' calibration exact',abs(expected-cal['horizons'][h]['delta'])<1e-14)
        check(h+' selected candidate matches frozen gate ordering',freeze['selected_candidates'][h]==choose(freeze['gates'][h]))
    git('merge-base','--is-ancestor',pre,commit)
    check('51 selection freeze before exposed',ex['selection_freeze_commit']==commit and not freeze['exposed_evaluated'] and pd.Timestamp(ex['time_UTC']).timestamp()>=int(git('show','-s','--format=%ct',commit)))
    check('exposed selection immutable',ex['selected_candidates_unchanged']==freeze['selected_candidates'] and not ex['reselection'] and not ex['recalibration'])
    check('82 same seed independent repeat',read('REPRODUCIBILITY_AUDIT')['PASS'] and max(r['max_difference'] for r in read('REPRODUCIBILITY_AUDIT')['rows'])<=1e-10 and read('EXPOSED_REPRODUCIBILITY_AUDIT')['PASS'])
    ledger=read('COMPUTE_LEDGER')
    check('32 actual single-thread CPU fits',len(ledger['fits'])==32 and all(r['device']=='cpu' and r['threads']==1 and r['seed']==SEED for r in ledger['fits']))
    check('all fits after preregistration commit',all(pd.Timestamp(r['time_UTC']).timestamp()>=int(git('show','-s','--format=%ct',pre)) for r in ledger['fits']))
    for filename in ['development_baseline_maturity.parquet','calibration_baseline_maturity.parquet','exposed_baseline_maturity.parquet']:
        p=pd.read_parquet(OUT/filename)
        check(filename+' TRAIN mature only',(p.source_role=='TRAIN').all() and (p.B1_latest_source_available_at<p.issue_time).all())
    table=pd.read_csv(OUT/'V40R6_HYPERPARAMETER_RESULTS.csv'); order=table.groupby('config').normalized_pinball.mean().sort_values()
    check('DEV objective actually minimized',hyper['selected_config']==order.index[0])
    proposal=read('OPTIMIZER_INTERFACE_PROPOSAL')
    check('failed primary creates empty proposal',ex['primary_safety'] or proposal['recommended_rows']==[])
    check('bootstrap only after primary passes',ex['primary_safety'] or read('BOOTSTRAP_STATUS')['status']=='NOT_EXECUTED_SAFETY_FAIL')
    missing=[n for n in read('REQUIREMENTS_MANIFEST')['required_artifacts'] if not (OUT/n).exists()]
    # Final receipt and this report are created only after the successful scientific checks.
    permitted=[] if '--closure' in sys.argv else ['V40R6_FINAL_COMMIT_RECEIPT.json','V40R6_TEST_REPORT.json']
    check('83 required artifacts present by stage',all(n in permitted for n in missing))
    p=np.load(OUT/'exposed_predictions.npz'); ix=p['row_ids']
    for h in HORIZONS:
        m=(f.iloc[ix].horizon==h).to_numpy(); yy=f.iloc[ix[m]].target_GPUh.to_numpy(); days=f.iloc[ix[m]].day.to_numpy()
        for c,u in [('U0',p['baseline'][m,2]),('U1',p['q'][m,1]),('U2',p['upper'][m])]:
            metrics=upper(yy,u,days); saved=ex['by_horizon'][h]['candidates'][c]['upper']
            check(h+' '+c+' exposed metrics recompute',all(np.isclose(metrics[k],saved[k],rtol=1e-12,atol=1e-10) for k in ['positive_coverage','positive_pinball','positive_WAPE','under_GPUh','over_GPUh','mean_supported_day_coverage']))

if __name__=='__main__': main()
