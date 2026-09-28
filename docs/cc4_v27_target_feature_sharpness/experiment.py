from core import *
import argparse,time
from concurrent.futures import ProcessPoolExecutor
TARGETS=['T0','T1','T2','T3'];FEATURES=['F0','F1','F2','F3','F4','F5']
def register():
    assert read(ROOT/'A0_ANCHOR.json')['prediction_bitwise_equal']
    assert read(ROOT/'TARGET_POPULATION_AUDIT.json')['T0_bitwise_equal']
    assert read(ROOT/'FEATURE_LEAKAGE_AUDIT.json')['PASS']
    arms=[dict(arm=t+'_'+f,target=t,features=f,alias=t+'_F0' if f=='F3' else None) for t in TARGETS for f in FEATURES]
    write('ARM_REGISTRATION.json',dict(time=pd.Timestamp.now(tz='UTC'),arms=arms,model='LightGBM log1p quantile Q50/Q90',parameters=PARAMS,refit='Daily expanding non-PURGE, label_matured_at strictly < issue; exact inherited 30-day weight formula',calibration='Signed per-slot finite-rank residual Q90 correction, ceil(.9*(n+1)), min20 mature OOS days. DEV/CAL reporting uses earlier mature DEV/CAL residues only. Before Dec1 freeze final offset from eligible mature CAL days only. Evaluation including May never updates offset. Q90=max(Q50,0,rawQ90+offset), no upper cap.',feature_selection='Per target: prefer RAW DEVELOPMENT coverage88..92; then lowest raw Q90 pinball, calibration error, requirement ratio, arm. If none in band, research-only minimum-loss fallback. CAL/evaluation never rerank. F3 is explicit unavailable-state alias, not independent evidence.',target_selection='T2 and T3 are the two research candidates because exact occupancy alignment is definitional; choose their feature arm by DEV only. No automatic operational winner. T0/T1 remain arrival diagnostics. T2 vs T3 compared on hourly aggregation and TRAIN-mean-normalized loss; no cross-unit score ranking.',stage2='After Stage1 target and feature freeze only: M0 pooled vs M1 four fixed 6h lead groups, unchanged parameters. Select per candidate by DEVELOPMENT raw coverage88..92 preference, then raw pinball; outside-band fallback is research only. No neural/tuning stage in this registered comparison; M2 requires >=100 mature training DAYS per individual period before first DEV issue and DEV evidence justifying additional splitting; M3/M4 deferred pending simple-model support.',support='Nominal band .88..92; per-target feature support requires raw Q90 pinball CI upper<0 and Q50 MAE non-inferior in EXPOSED and OOS_EXTENSION, with target-relative ratio no worse and calibrated coverage in band; May diagnostics cannot select or overturn frozen configuration. CIs unadjusted exploratory, not untouched confirmation.',bootstrap=dict(draws=2000,blocks=[1,7],seed=20260928,unit='paired whole target day circular blocks',nonfinite='entire affected CI unavailable; no draw removal'),burst='TRAIN positive target Q95; no new label caps',ties='Peak timing uses earliest maximum; top-load overlap uses stable rank ties; all-zero days retained',extension='Frozen OOS_EXTENSION eligible=False retained in original ledger; all63 extension dates scored separately on explicit requested extension basis',source_causality='Logical event-time only; unresolved submission/request version and ingestion provenance retained; no optimizer integration readiness',May='exposed diagnostic only; no selection',optimizer_runs=0))
    write('EXPERIMENT_CODE_FREEZE.json',dict(code={p.name:sha(p) for p in [ROOT/'core.py',ROOT/'experiment.py',ROOT/'prepare.py']},data={p:sha(ROOT/p) for p in ['TARGETS.npz','FEATURES.npz','FEATURE_GROUPS.json','ARM_REGISTRATION.json']}))
def guard():
    f=read(ROOT/'EXPERIMENT_CODE_FREEZE.json')
    amendment=ROOT/'SELECTION_PROTOCOL_AMENDMENT.json'
    if amendment.exists():
        a=read(amendment)
        assert sha(ROOT/'registration_v1/experiment.py')==f['code']['experiment.py']==a['original_experiment_sha256']
        f['code']['experiment.py']=a['amended_experiment_sha256']
    for n,h in {**f['code'],**f['data']}.items():assert sha(ROOT/n)==h,n
_data=None
def init():
    global _data
    f=np.load(ROOT/'FEATURES.npz');t=np.load(ROOT/'TARGETS.npz')
    _data=({k:f[k] for k in f.files},{k:t[k] for k in t.files if k!='days'})
def run_day(task):
    arm,i,model=task;xdata,tdata=_data;t=arm.split('_')[0];y=tdata[t];x=xdata[arm]
    p=ROOT/'runs'/model/arm/(DAYS[i]+'.npz')
    if p.exists():return str(p),True
    p.parent.mkdir(parents=True,exist_ok=True)
    mature=pd.Series(pd.to_datetime(tdata['maturity_'+t].max(1),utc=True));tr=member(i,mature)
    assert len(tr)>=20 and (mature.iloc[tr]<ISS.iloc[i]).all()
    groups=np.array_split(np.arange(y.shape[1]),4) if model=='M1' else None
    started=time.perf_counter();q,imp,h=fit(x,y,tr,i,groups);elapsed=time.perf_counter()-started
    np.savez_compressed(p,q=q,importance=imp,training_days=tr,weights=weights(tr,i),model_sha256=np.array(h),latest_maturity_ns=np.array(mature.iloc[tr].max().value),issue_ns=np.array(ISS.iloc[i].value),seconds=np.array(elapsed),code_sha256=np.array(sha(ROOT/'core.py')))
    return str(p),False
def run(phase,stage2=False):
    guard();targets=read(ROOT/'TARGET_SELECTION_FREEZE.json') if stage2 or phase=='evaluation' else None
    arms=read(ROOT/'FEATURE_SELECTION_FREEZE.json')['candidates'] if stage2 else [t+'_'+f for t in TARGETS for f in FEATURES if f!='F3' and not (t=='T0' and f=='F0')]
    ids=OOS[DAYS[OOS]<'2024-12-01'] if phase=='development' else OOS[DAYS[OOS]>='2024-12-01']
    if stage2 and phase=='evaluation':assert (ROOT/'STAGE2_SELECTION_FREEZE.json').exists()
    model='M1' if stage2 else 'M0';tasks=[(arm,int(i),model) for i in ids for arm in arms]
    with ProcessPoolExecutor(max_workers=8,initializer=init) as pool:
        for j,(p,reused) in enumerate(pool.map(run_day,tasks,chunksize=1)):
            if j%20==0:print('FIT',model,phase,j+1,len(tasks),Path(p).parent.name,Path(p).stem,'cached' if reused else 'new',flush=True)
    print('PHASE_COMPLETE',model,phase,len(tasks),flush=True)
def predictions(arm,model='M0'):
    t=arm[:2];n=96 if t=='T3' else 24;q=np.full((len(DAYS),n,2),np.nan)
    if model=='M0' and arm in ['T0_F0','T0_F3']:return np.load(ROOT/'A0_PREDICTIONS.npz')['q'].copy()
    if arm.endswith('F3'):arm=arm[:-2]+'F0'
    for p in (ROOT/'runs'/model/arm).glob('*.npz'):
        i=int(np.searchsorted(DAYS,p.stem));q[i]=np.load(p)['q']
    return q
def residual(y,q,ids):
    assert len(ids)>=20;rank=int(np.ceil(.9*(len(ids)+1)));assert rank<=len(ids)
    return np.sort(y[ids]-q[ids,:,1],axis=0)[rank-1]
def calibrate(arm,q,freeze=True):
    t=arm[:2];z=np.load(ROOT/'TARGETS.npz');y=z[t];mature=pd.Series(pd.to_datetime(z['maturity_'+t].max(1),utc=True));out=q.copy();available=np.zeros(len(DAYS),bool)
    final=CAL[np.asarray(mature.iloc[CAL]<ISS.iloc[role_ids('EXPOSED_EVALUATION')[0]])]
    delta=residual(y,q,final)
    for i in OOS:
        if DAYS[i]>='2024-12-01':d=delta;available[i]=True
        else:
            pool=np.concatenate([DEV,CAL]);past=pool[(pool<i)&np.asarray(mature.iloc[pool]<ISS.iloc[i])]
            if len(past)<20:d=np.zeros(y.shape[1])
            else:d=residual(y,q,past);available[i]=True
        out[i,:,1]=np.maximum(out[i,:,0],np.maximum(0,out[i,:,1]+d))
    return out,available,dict(calibration_days=DAYS[final].tolist(),maturity_before_first_evaluation=True,delta=delta.tolist(),rank=int(np.ceil(.9*(len(final)+1))),fixed_after='2024-12-01')
def choose_development(frame):
    # User requirement22: nominal calibration band before sharpness ranking.
    eligible=frame[frame.Q90_coverage.between(.88,.92)]
    pool=eligible if len(eligible) else frame
    keys=['Q90_pinball','calibration_error','requirement_ratio','model','arm']
    return pool.sort_values(keys).iloc[0],bool(len(eligible))
def freeze(stage2=False):
    guard();z=np.load(ROOT/'TARGETS.npz');rows=[];calibrations={};selected={}
    arms=read(ROOT/'FEATURE_SELECTION_FREEZE.json')['candidates'] if stage2 else [t+'_'+f for t in TARGETS for f in FEATURES]
    for arm in arms:
        t=arm[:2];y=z[t];burst=np.quantile(y[TRAIN][y[TRAIN]>0],.95)
        for model in (['M0','M1'] if stage2 else ['M0']):
            q=predictions(arm,model);assert np.isfinite(q[np.r_[DEV,CAL]]).all()
            qc,available,receipt=calibrate(arm,q);calibrations[arm+'_'+model]=receipt
            for role,idx in [('DEVELOPMENT',DEV),('CALIBRATION',CAL)]:
                for variant,p in [('RAW',q),('CALIBRATED',qc)]:rows.append(dict(arm=arm,model=model,target=t,role=role,variant=variant,calibration_available_days=int(available[idx].sum()),**metrics(y[idx],p[idx],burst,.25 if t=='T3' else 1)))
    f=pd.DataFrame(rows);nominal_eligibility={}
    if stage2:
        for arm in arms:
            r,eligible=choose_development(f[f.arm.eq(arm)&f.role.eq('DEVELOPMENT')&f.variant.eq('RAW')]);selected[arm]=r.model;nominal_eligibility[arm]=eligible
        write('STAGE2_SELECTION_FREEZE.json',dict(time=pd.Timestamp.now(tz='UTC'),selected=selected,selection_roles=['DEVELOPMENT'],evaluation_used=False,calibrations=calibrations,development_nominal_band_met=nominal_eligibility,selection_amendment_sha256=sha(ROOT/'SELECTION_PROTOCOL_AMENDMENT.json') if (ROOT/'SELECTION_PROTOCOL_AMENDMENT.json').exists() else None,stage1_target_freeze_sha256=sha(ROOT/'TARGET_SELECTION_FREEZE.json')))
        csv('STAGE2_DEVELOPMENT_METRICS.csv',rows)
    else:
        for t in TARGETS:
            r,eligible=choose_development(f[f.target.eq(t)&f.role.eq('DEVELOPMENT')&f.variant.eq('RAW')&~f.arm.str.endswith('F3')]);selected[t]=r.arm;nominal_eligibility[t]=eligible
        candidates=[selected['T2'],selected['T3']]
        write('TARGET_SELECTION_FREEZE.json',dict(time=pd.Timestamp.now(tz='UTC'),research_targets=['T2','T3'],operational_winner=None,reason='Both have exact electrical occupancy alignment; resolution must be tested, no automatic T3 promotion',selection_roles=['DEVELOPMENT'],May_used=False,evaluation_used=False,stage2_authorized=True))
        write('FEATURE_SELECTION_FREEZE.json',dict(time=pd.Timestamp.now(tz='UTC'),per_target=selected,candidates=candidates,selection_roles=['DEVELOPMENT'],criterion='Prefer RAW DEVELOPMENT coverage88..92, then raw pinball, calibration error, requirement ratio; if no candidate in band, research-only minimum loss fallback',development_nominal_band_met=nominal_eligibility,selection_amendment_sha256=sha(ROOT/'SELECTION_PROTOCOL_AMENDMENT.json') if (ROOT/'SELECTION_PROTOCOL_AMENDMENT.json').exists() else None,May_used=False,calibrations=calibrations))
        write('STAGE2_MODEL_PROTOCOL.json',dict(time=pd.Timestamp.now(tz='UTC'),candidates=candidates,models=['M0','M1'],lead_groups_hours=[[6,12],[12,18],[18,24],[24,30]],intervals='left closed, right open',parameters=PARAMS,selection='DEV RAW coverage88..92 first, then pinball/calibration error/ratio; otherwise research-only minimum loss fallback',M2='DEFERRED: no preregistered necessity established beyond four lead groups; per-period support reported in Stage1',M3='DEFERRED: local conformal not mixed with target/feature study',M4='DEFERRED: no neural complexity before simpler evidence',freeze_sha256=sha(ROOT/'TARGET_SELECTION_FREEZE.json')))
        csv('DEVELOPMENT_CALIBRATION_METRICS.csv',rows)
    print('SELECTION_FROZEN',selected,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['register','development','freeze','evaluation']);p.add_argument('--stage2',action='store_true');a=p.parse_args()
    if a.phase=='register':register()
    elif a.phase=='freeze':freeze(a.stage2)
    else:run(a.phase,a.stage2)
