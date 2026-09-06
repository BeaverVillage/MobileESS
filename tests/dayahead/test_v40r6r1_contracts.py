import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40r6r1.common import *
from dayahead.v40r6r1.calibration import order_statistic,effective_availability,rolling
from dayahead.v40r6r1.metrics import metrics,monthly,gates,select
import ast

def main():
    checks=[]
    def check(name,value):
        assert bool(value),name
        checks.append(name)
    reg=read('PREREGISTRATION'); receipt=r6('FINAL_COMMIT_RECEIPT'); target=read('TARGET_IDENTITY_AUDIT')
    check('01 R6 science SHA',git('rev-parse',SCIENCE)==SCIENCE)
    check('02 R6 receipt SHA',git('rev-parse',BASE)==BASE)
    check('03 R6 classification',receipt['classification']=='V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL')
    check('04 R6 selection NONE',all(v=='NONE' for v in receipt['selected_candidates'].values()))
    check('05 isolated worktree',ROOT.name=='MobileESS_v40r6r1_risk_calibrated_gpuwork' and git('branch','--show-current')=='codex/v40r6r1-risk-calibrated-rolling-gpuwork')
    snap=snapshot(); start=read('PROTECTED_SCOPE_START')
    check('06 R5 R5R1 R6 immutable',snap==start)
    check('07 target SHA',sha(R6/'V40R6_CUMULATIVE_TARGET.parquet')==target['exact_R6_target_SHA256']==target['expected_SHA256'])
    f=pd.read_parquet(R6/'V40R6_CUMULATIVE_TARGET.parquet'); native=np.load(R5/'data.npz')['y'].reshape(349,96)
    for num,h,n in [(8,'H4',28269),(9,'H24',349)]:
        hf=f[f.horizon==h]; actual=np.array([native[r.day_index,r.window_start_slot:r.window_end_slot_exclusive].sum() for r in hf.itertuples()])
        check(f'{num:02} {h} identity',len(hf)==n and np.max(np.abs(actual-hf.target_GPUh.to_numpy()))<1e-7)
    check('10 no new target construction',target['new_target_construction']==0 and native.size==33504 and abs(native.sum()-1904541.778333334)<1e-7)
    base=read('BASE_PREDICTION_IDENTITY')
    for num,family in [(11,'B1'),(12,'B2')]:
        check(f'{num} frozen {family} predictions',all(sha(ROOT/r['file'])==r['SHA256'] and r['usage']=='READ_FROM_FROZEN_ARRAY' for r in base['sources']))
    calls=[]; imports=[]
    for p in (ROOT/'dayahead/v40r6r1').glob('*.py'):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute): calls.append(node.func.attr)
            if isinstance(node,ast.Import): imports.extend(a.name for a in node.names)
            if isinstance(node,ast.ImportFrom): imports.append(node.module or '')
    check('13 no fit calls or model frameworks','fit' not in calls and not any(x.startswith(('lightgbm','xgboost','torch','sklearn')) for x in imports))
    check('14 nominal service .85',reg['service_level']==.85 and reg['alpha']==.15)
    check('15 upper band .925',reg['gates']['positive_coverage_band']==[.85,.925])
    check('16 day month floor .80',reg['gates']['mean_day_positive_coverage_min']==reg['gates']['supported_month_positive_coverage_min']==.8)
    source=source_frame(False)
    issue=pd.to_datetime(source.day,utc=True)-pd.Timedelta(hours=16)
    check('17 issue D-1 18 AEST',np.array_equal(source.issue_time.to_numpy(),issue.to_numpy()))
    check('18 full-day and label maturity rule',reg['calibration']['availability']['rule']=='max(target_day_end, target_label_available_at) < current issue_time')
    check('19 no partial day',reg['calibration']['full_day_membership'])
    check('20 DEV OOS initial',reg['calibration']['initial_source']=='DEVELOPMENT_OOS' and not reg['calibration']['TRAIN_residuals'])
    check('24 expanding no forgetting',reg['calibration']['policy']=='FULL_EXPANDING_CAUSAL_HISTORY' and not reg['calibration']['drop_old_residuals'])
    check('25 H4 support',reg['calibration']['H4_min_days']==20 and reg['calibration']['H4_min_rows']==500)
    check('26 H24 support',reg['calibration']['H24_min_days']==30)
    for n in [1,2,19,20,21,30,499,500,501,4698]:
        values=np.arange(n,dtype=float)[::-1]; q,k=order_statistic(values)
        expected_k=min(max(int(np.ceil((n+1)*.85)),1),n)
        check(f'27 order statistic n={n}',k==expected_k and q==expected_k-1)
    check('28 nonnegative delta rule',reg['calibration']['delta']=='max(0,q85_residual)')
    check('29 no static fallback','No static fallback' in reg['calibration']['insufficient'])
    check('30 no smoothing',not reg['calibration']['smoothing'] and not reg['calibration']['interpolation'])
    check('31 H4 H24 only',reg['horizons']=={'H4':16,'H24':96})
    check('32 H1 H8 immutable context','not recalibrated' in reg['H1_H8'])
    check('33 exactly two candidates',reg['candidate_registry']==CANDIDATES)
    check('34 static comparator only',len(reg['comparators_only'])==3 and not set(reg['comparators_only'])&set(CANDIDATES))
    check('35 CAL only selection',reg['selection']['scope']=='CAL_ONLY')
    check('37 no exposed reselection',reg['exposed']['no_reselection'])
    yy=np.array([0.,1.,4.,10.]); uu=np.array([1.,2.,3.,8.]); dd=np.array(['2025-01-01']*2+['2025-01-02']*2)
    m=metrics(yy,uu,dd); months=monthly(yy,uu,dd)
    check('38 positive coverage fixture',m['positive_coverage']==1/3)
    check('39 day coverage fixture',m['mean_day_positive_coverage']==.5)
    check('40 month coverage fixture',months[0]['positive_coverage']==1/3 and months[0]['mean_day_positive_coverage']==.5)
    check('41 under GPUh fixture',m['under_GPUh']==3 and np.isclose(m['positive_shortfall_ratio'],.2))
    check('42 over GPUh fixture',m['over_GPUh']==2)
    check('43 positive upper WAPE fixture',np.isclose(m['positive_upper_WAPE'],4/15))
    check('conditional miss severity fixture',m['miss_N']==2 and m['mean_miss_GPUh']==1.5 and m['maximum_miss_GPUh']==2 and m['P90_miss_GPUh']==1.9)
    good={'support_complete':True,'positive_coverage':.85,'supported_positive_days':30,'mean_day_positive_coverage':.85,
        'under_GPUh':1.,'over_GPUh':10.,'positive_upper_WAPE':1.9}
    check('44 miss gate strict',gates(good,[],2.,20.,20.)['PASS'] and not gates(good,[],1.,20.,20.)['PASS'])
    check('45 anchor A strict',not gates(good,[],2.,10.,20.)['PASS'])
    check('46 anchor B strict',not gates(good,[],2.,20.,10.)['PASS'])
    check('WAPE exactly 200 fails',not gates({**good,'positive_upper_WAPE':2.},[],2.,20.,20.)['PASS'])
    check('coverage upper boundary',gates({**good,'positive_coverage':.925},[],2.,20.,20.)['PASS'] and not gates({**good,'positive_coverage':.926},[],2.,20.,20.)['PASS'])
    fake={c:{'gates':{'PASS':True},'metrics':{'over_GPUh':10. if c=='R85_B2' else 10.2}} for c in CANDIDATES}
    check('2 percent tie favors B1',select(fake)=='R85_B1')
    fake['R85_B1']['metrics']['over_GPUh']=10.3
    check('outside tie lower over wins',select(fake)=='R85_B2')
    check('47 both primary required',reg['selection']['joint_requires']==['H4','H24'] and reg['selection']['partial_success_not_promoted'])
    check('48 no grid security claim',not reg['grid_security_probability'] and reg['physical_electrical_feasibility_separate'])
    check('49 GPUh semantics','not instantaneous GPU occupancy' in reg['physical_semantics'])
    check('50 no synthetic jobs',not reg['synthetic_jobs'])
    for n,k in [(51,'optimizer_calls'),(52,'Gurobi_calls'),(53,'OpenDSS_calls'),(54,'Fresh_calls')]:
        check(f'{n} {k} zero',reg['firewall'][k]==0 and not any(x.startswith(('gurobi','opendss','dayahead.v37','dayahead.v40a')) for x in imports))
    for n,k in [(55,'A0'),(56,'A1'),(57,'M1'),(58,'MF'),(59,'migration'),(60,'WAN'),(61,'terminal'),(62,'MESS')]:
        check(f'{n} {k} unchanged',not snap['protected_diff'] and snap['inherited_tree']==start['inherited_tree'])
    for n,k in [(63,'event_trigger'),(64,'local_repair'),(65,'rolling_MPC')]: check(f'{n} {k} absent',not reg[k])
    check('66 May reads zero',reg['firewall']['May_scientific_reads']==0)
    check('67 shadow reads zero',reg['firewall']['shadow_scientific_reads']==0)
    for n,k,v in [(68,'production_q_seconds',5576.44921875),(69,'PF',.95),(70,'Q_control','NO'),(71,'electrical','HOLD'),(72,'FULL_MAY','NO')]: check(f'{n} {k} hold',reg['holds'][k]==v)
    check('75 protected scope clean',snap==start)
    check('final workload research closure contract',reg['closure']['NO_R6R2'] and reg['closure']['NO_R7'] and reg['closure']['FURTHER_FUTURE_WORKLOAD_MODEL_WORK']=='DEFER_UNTIL_NEW_DATA_OR_AUTHORITY')
    if '--prefit' not in sys.argv: post_checks(check)
    if '--closure' in sys.argv:
        check('76 final Git clean',git('status','--porcelain')=='')
        verify_commit_file(read('FINAL_COMMIT_RECEIPT')['scientific_commit'],OUT/'V40R6R1_FINAL_DECISION.json')
        check('scientific receipt exact',True)
    report={'passed':len(checks),'failed':0,'checks':checks,'phase':'prefit' if '--prefit' in sys.argv else 'closure' if '--closure' in sys.argv else 'post-evaluation',
        'read_only':'--read-only' in sys.argv}
    if '--read-only' not in sys.argv: dump('PREFIT_TEST_REPORT' if '--prefit' in sys.argv else 'TEST_REPORT',report)
    print(json.dumps(report,indent=2))

def post_checks(check):
    from dayahead.v40r6r1.pipeline import summarize
    reg,freeze,commit=selection_authority(); ex=read('EXPOSED_RESULTS'); source=source_frame(True)
    ledger=pd.read_parquet(OUT/'V40R6R1_DAILY_CALIBRATION_LEDGER.parquet'); proof=pd.read_parquet(OUT/'V40R6R1_RESIDUAL_AVAILABILITY_PROOF.parquet')
    check('21 CAL residual causal',(proof.effective_available_at<proof.issue_time).all() and (proof.residual_day_end<proof.issue_time).all())
    check('22 EXPOSED residual label availability',(proof.raw_label_available_at<proof.issue_time).all())
    check('23 no future or partial residual',(proof.residual_day<proof.target_day).all() and proof.entire_day_included.all())
    cal=read('CAL_EVALUATION')['by_horizon']
    for h in HORIZONS:
        check(h+' CAL selection independently matches rule',select(cal[h])==freeze['selected_candidates'][h])
    check('36 freeze before exposed',ex['selection_freeze_commit']==commit and not freeze['exposed_evaluated'] and pd.Timestamp(ex['time_UTC']).timestamp()>=int(git('show','-s','--format=%ct',commit)))
    check('frozen candidates unchanged',ex['selected_candidates']==freeze['selected_candidates'] and not ex['reselection'] and not ex['rule_changes'])
    outputs=pd.concat([pd.read_parquet(OUT/'cal_rolling_predictions.parquet'),pd.read_parquet(OUT/'exposed_rolling_predictions.parquet')],ignore_index=True)
    for phase,expected in [('CALIBRATION',cal),('EXPOSED_EVALUATION',ex['by_horizon'])]:
        actual,_,_=summarize(outputs[outputs.role==phase],phase)
        check(phase+' all metrics and anchors exact',clean(actual)==clean(expected))
    # Independent day library reconstruction and a sort (not np.partition).
    for h in HORIZONS:
        hf=source[source.horizon==h]; av=effective_availability(hf)
        for c,column in [('R85_B1','base_B1_Q90'),('R85_B2','base_B2_Q90')]:
            rows=ledger[(ledger.horizon==h)&(ledger.candidate==c)].sort_values('target_day'); previous=set(); exact=True
            for r in rows.itertuples():
                mask=av<r.issue_time.value; history=hf.loc[mask]; membership=set(history.row_id)
                exact &= previous.issubset(membership); previous=membership
                exact &= history.day.nunique()==r.eligible_residual_days and len(history)==r.eligible_residual_rows
                residual=np.log1p(history.target_GPUh.to_numpy())-np.log1p(np.maximum(history[column].to_numpy(),0))
                k=min(max(int(np.ceil((len(residual)+1)*.85)),1),len(residual)); q=np.sort(residual)[k-1]
                exact &= k==r.order_statistic_k and q==r.q85_residual and max(0.,q)==r.delta
                current=outputs[(outputs.day==r.target_day)&(outputs.horizon==h)&(outputs.candidate==c)]
                u=np.expm1(np.log1p(np.maximum(current.base_upper.to_numpy(),0))+r.delta)
                exact &= np.array_equal(u,current.rolling_upper.to_numpy())
            check(h+' '+c+' full expanding membership/order/delta/upper exact',exact)
    check('73 deterministic repeat exact',read('REPRODUCIBILITY_AUDIT')['PASS'] and all(read('REPRODUCIBILITY_AUDIT')[k]==0 for k in ['delta_sequence_max_difference','upper_prediction_max_difference','metrics_max_difference']))
    missing=[n for n in read('REQUIREMENTS_MANIFEST')['required_artifacts'] if not (OUT/n).exists()]
    permitted=[] if '--closure' in sys.argv else ['V40R6R1_TEST_REPORT.json','V40R6R1_FINAL_COMMIT_RECEIPT.json']
    check('74 required artifacts by stage',all(n in permitted for n in missing))
    final=read('FINAL_DECISION')
    check('research closed',final['current_authority_research_status']=='CLOSED' and final['FURTHER_FUTURE_WORKLOAD_MODEL_WORK']=='DEFER_UNTIL_NEW_DATA_OR_AUTHORITY')
    check('no failed joint promotion',final['joint_pass'] or final['FUTURE_WORKLOAD_MODEL_STATUS']=='NO_MODEL_PROMOTED')
    check('failure empty interface',final['joint_pass'] or read('OPTIMIZER_INTERFACE_PROPOSAL')['recommended_rows']==[])
    check('failure skips bootstrap',final['joint_pass'] or read('BOOTSTRAP_STATUS')['status']=='NOT_EXECUTED_SAFETY_FAIL')

if __name__=='__main__': main()
