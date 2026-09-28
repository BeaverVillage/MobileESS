"""Reduced, pre-registered calibration study using immutable daily-fit cache."""
from common import *
import argparse
CANDIDATES=['T2_F0','T3_F2']
METHODS=['RAW','LEGACY_SLOT','HORIZON_ADD','HORIZON_LOCAL_SCALE']
ROLES=['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','OOS_EXTENSION','MAY_HISTORICAL']
def register():
    verify_previous();backend=read(ROOT/'COMPUTE_BACKEND_SELECTION.json');assert backend['PREDICTION_EQUIVALENCE_VERIFIED']
    write('LEAD_GROUP_DEFINITION.json',dict(clock=c.TZ,issue='D-1 18:00',lead_hours=[[6,12],[12,18],[18,24],[24,30]],half_open=True,hourly_slot_groups=[v.tolist() for v in np.array_split(np.arange(24),4)],quarter_hour_slot_groups=[v.tolist() for v in np.array_split(np.arange(96),4)]))
    write('NEXT_STAGE_PROTOCOL.json',dict(time=pd.Timestamp.now(tz='UTC'),scientific_question='Given frozen occupancy candidates, can horizon-aware calibration reach nominal Q90 without excessive reserve?',current_v27_delivery_sha256=sha(PREV/'DELIVERY_MANIFEST.json'),current_review_sha256=sha(PREV/'FINAL_REVIEW_KO.md'),backend_selection_sha256=sha(ROOT/'COMPUTE_BACKEND_SELECTION.json'),candidates=CANDIDATES,historical_reference='T0_F0 M0 only',parameters=c.PARAMS,stage_A='Reuse frozen DEV/CAL M0/M1 daily predictions. Select on DEV only: prefer raw coverage88..92, then pinball/calibration error/ratio. Reject a structure if raw pinball, Q50 MAE, and calibration error are all worse than selected. No full-period rerun for rejected structures.',stage_B=dict(methods=METHODS,selection_role='CALIBRATION',selection='Prefer CAL coverage88..92, then Q90 pinball, requirement ratio, method. If no candidate in band, closest to .90 then pinball, ratio; research fallback only.',DEV_CAL_bank='Most recent 26 eligible, strictly prior and label-matured DEV/CAL days, at least20; earlier warmup uses raw and remains scored.',evaluation_bank='All26 eligible CAL days matured before first evaluation. Fixed thereafter, no evaluation/May residual updates.',LEGACY_SLOT='Exact current v2.7 calibrate() reference, including its expanding DEV/CAL bank; evaluate separately from new rolling-bank methods.',HORIZON_ADD='Pooled signed residuals within each fixed 6h lead group, finite rank ceil(.9*(N+1)), no cap. Pooled correlated slots imply empirical correction, not guaranteed exchangeable conformal coverage.',HORIZON_LOCAL_SCALE='Same group correction on (y-rawQ90)/s; s=max(rawQ90-rawQ50,0.05*TRAIN mean). Apply rawQ90+s*group coefficient. Scale depends only on model predictions and frozen TRAIN statistic; no future outcomes.',support='Q90=max(Q50,0,corrected Q90); no upper clipping, label cap, new power model, or synthetic jobs.'),stage_C='At most two frozen finalists, one per retained target. Reuse the exact matching immutable daily-fit cache because only Q90 postprocessing changes; audit all546 finalist daily refits and backend benchmark equivalence. No redundant re-fit of identical models, no speculative full-period arms. Report new_fit_count=0 and reused counts explicitly.',selection_uses_May=False,selection_uses_evaluation=False,statistical_gate='Both EXPOSED and EXT: final coverage88..92, ratio no worse than legacy slot, paired7day raw pinball improvement versus legacy CI high<0; Q50 held exactly fixed. Also report final-vs-raw, all metrics and May diagnostic. Exploratory dependent data, no untouched confirmation.',bootstrap=dict(draws=2000,blocks=[1,7],seed=20260928),neural_search='DEFERRED; no TFT/DeepAR',code={n:sha(ROOT/n) for n in ['common.py','study.py']},baseline_cache_source='v2.7 CPU deterministic n_jobs1; acceleration benchmark governs needed new fits. Equivalent cached fits require no backend rerun.'))
def guard():
    p=read(ROOT/'NEXT_STAGE_PROTOCOL.json')
    for n,h in p['code'].items():assert sha(ROOT/n)==h,n
    assert sha(ROOT/'COMPUTE_BACKEND_SELECTION.json')==p['backend_selection_sha256']
def load(arm,model):
    z=np.load(PREV/'TARGETS.npz');t=arm[:2];y=z[t];q=old.predictions(arm,model);mature=pd.Series(pd.to_datetime(z['maturity_'+t].max(1),utc=True));return y,q,mature
def choose(g,stage='B'):
    valid=g[g.Q90_coverage.between(.88,.92)]
    pool=valid if len(valid) else g
    columns=['Q90_pinball','calibration_error','requirement_ratio','model'] if stage=='A' else (['Q90_pinball','requirement_ratio','method'] if len(valid) else ['calibration_error','Q90_pinball','requirement_ratio','method'])
    return pool.sort_values(columns).iloc[0],bool(len(valid))
def stage_a():
    guard();m=pd.read_csv(PREV/'STAGE2_MODEL_METRICS.csv');rows=m[m.role.isin(ROLES[:2])&m.variant.eq('RAW')].copy();rows['source']='immutable v2.7 daily-refit cache'
    base=pd.read_csv(PREV/'ARM_METRICS.csv');base=base[base.arm.eq('T0_F0')&base.role.isin(ROLES[:2])&base.variant.eq('RAW')].copy();base['source']='A0 historical reference only';rows=pd.concat([rows,base],ignore_index=True)
    selected={};decisions=[]
    for arm in CANDIDATES:
        g=rows[rows.arm.eq(arm)&rows.role.eq('DEVELOPMENT')];best,inband=choose(g,'A');selected[arm]=best.model
        for _,r in g.iterrows():decisions.append(dict(arm=arm,model=r.model,selected=r.model==best.model,development_nominal_band_met=inband,strictly_worse_in_loss_MAE_calibration=bool(r.Q90_pinball>best.Q90_pinball and r.Q50_MAE>best.Q50_MAE and r.calibration_error>best.calibration_error)))
    csv('MODEL_STAGE_A_METRICS.csv',rows);write('STAGE_A_FREEZE.json',dict(time=pd.Timestamp.now(tz='UTC'),selected=selected,decisions=decisions,selection_roles=['DEVELOPMENT'],protocol_sha256=sha(ROOT/'NEXT_STAGE_PROTOCOL.json'),new_model_fits=0,cache_reuse=True))
def scale(q,y):return np.maximum(q[...,1]-q[...,0],.05*y[c.TRAIN].mean())
def coefficients(y,q,ids,method):
    assert len(ids)>=20;res=y[ids]-q[ids,:,1]
    if method=='HORIZON_LOCAL_SCALE':res=res/scale(q,y)[ids]
    values=[]
    for slots in np.array_split(np.arange(y.shape[1]),4):
        v=np.sort(res[:,slots].ravel());rank=int(np.ceil(.9*(len(v)+1)));assert rank<=len(v);values.append(float(v[rank-1]))
    return values
def correct(qi,yi_mean,coef,method):
    out=qi.copy();ss=np.maximum(qi[:,1]-qi[:,0],.05*yi_mean)
    for group,slots in enumerate(np.array_split(np.arange(len(qi)),4)):
        out[slots,1]=qi[slots,1]+coef[group]*(ss[slots] if method=='HORIZON_LOCAL_SCALE' else 1)
    out[:,1]=np.maximum(out[:,0],np.maximum(0,out[:,1]));return out
def preevaluation(arm,model,method):
    y,q,mature=load(arm,model);out=q.copy();proof=[];available=np.zeros(len(c.DAYS),bool)
    if method=='LEGACY_SLOT':return (*old.calibrate(arm,q)[:2],proof)
    if method=='RAW':return out,available,proof
    pool=np.r_[c.DEV,c.CAL]
    for i in c.OOS[c.DAYS[c.OOS]<'2024-12-01']:
        bank=pool[(pool<i)&np.asarray(mature.iloc[pool]<c.ISS.iloc[i])][-26:]
        assert (mature.iloc[bank]<c.ISS.iloc[i]).all() and (c.ISS.iloc[bank]<c.ISS.iloc[i]).all()
        if len(bank)>=20:out[i]=correct(q[i],y[c.TRAIN].mean(),coefficients(y,q,bank,method),method);available[i]=True
        proof.append(dict(arm=arm,model=model,method=method,issue_day=c.DAYS[i],bank_days=';'.join(c.DAYS[bank]),count=len(bank),latest_maturity_ns=int(mature.iloc[bank].max().value) if len(bank) else None,issue_ns=c.ISS.iloc[i].value,used=len(bank)>=20,PASS=True))
    return out,available,proof
def stage_b():
    guard();a=read(ROOT/'STAGE_A_FREEZE.json');rows=[];proof=[];finalists={}
    for arm,model in a['selected'].items():
        y,q,mature=load(arm,model);t=arm[:2];burst=np.quantile(y[c.TRAIN][y[c.TRAIN]>0],.95);dt=.25 if t=='T3' else 1
        for method in METHODS:
            p,available,receipt=preevaluation(arm,model,method);proof.extend(receipt)
            for role in ROLES[:2]:
                ids=c.role_ids(role);rows.append(dict(arm=arm,model=model,method=method,role=role,calibration_days_available=int(available[ids].sum()),warmup_or_raw_days=int((~available[ids]).sum()),**previous_report.metrics(y[ids],p[ids],burst,dt)))
        g=pd.DataFrame(rows);g=g[g.arm.eq(arm)&g.role.eq('CALIBRATION')];r,inband=choose(g)
        bank=c.CAL[np.asarray(mature.iloc[c.CAL]<c.ISS.iloc[c.role_ids('EXPOSED_EVALUATION')[0]])];assert len(bank)==26
        coeff=coefficients(y,q,bank,r.method) if r.method.startswith('HORIZON') else None
        finalists[arm]=dict(model=model,method=r.method,CAL_nominal_band_met=inband,calibration_days=c.DAYS[bank].tolist(),group_coefficients=coeff,TRAIN_scale_floor=float(.05*y[c.TRAIN].mean()),research_only=True)
    csv('MODEL_STAGE_B_CALIBRATION_METRICS.csv',rows);csv('CALIBRATION_CAUSAL_PROOF.csv',proof)
    write('FINALIST_FREEZE.json',dict(time=pd.Timestamp.now(tz='UTC'),finalists=finalists,maximum_finalists=2,selection_roles=['DEVELOPMENT','CALIBRATION'],May_used=False,evaluation_used=False,stage_A_sha256=sha(ROOT/'STAGE_A_FREEZE.json'),protocol_sha256=sha(ROOT/'NEXT_STAGE_PROTOCOL.json'),stage_B_metrics_sha256=sha(ROOT/'MODEL_STAGE_B_CALIBRATION_METRICS.csv'),new_full_period_model_fits_planned=0,reused_full_daily_fit_records=546,reason='Identical target/features/model/weights/cadence already fit and sealed; only frozen causal Q90 postprocessing is new. Reusing exact predictions is the full daily-refit evaluation, not a claim of newly trained models.'))
def stage_c():
    guard();f=read(ROOT/'FINALIST_FREEZE.json');rows=[];lead=[];burstrows=[];uncertainty=[];pred=[];refs=[]
    for arm,s in f['finalists'].items():
        y,q,mature=load(arm,s['model']);t=arm[:2];dt=.25 if t=='T3' else 1;burst=np.quantile(y[c.TRAIN][y[c.TRAIN]>0],.95)
        bank=np.array([int(np.searchsorted(c.DAYS,d)) for d in s['calibration_days']]);assert (mature.iloc[bank]<c.ISS.iloc[c.role_ids('EXPOSED_EVALUATION')[0]]).all()
        legacy,_,_=old.calibrate(arm,q);p=q.copy()
        if s['method']=='LEGACY_SLOT':p=legacy.copy()
        elif s['method'].startswith('HORIZON'):
            coeff=coefficients(y,q,bank,s['method']);np.testing.assert_array_equal(coeff,s['group_coefficients'])
            for i in c.OOS[c.DAYS[c.OOS]>='2024-12-01']:p[i]=correct(q[i],y[c.TRAIN].mean(),coeff,s['method'])
        assert np.isfinite(p[c.OOS]).all();np.testing.assert_array_equal(p[c.OOS,:,0],q[c.OOS,:,0]);assert (p[c.OOS,:,1]>=p[c.OOS,:,0]).all()
        for i in c.OOS:
            path=PREV/'runs'/s['model']/arm/(c.DAYS[i]+'.npz');r=np.load(path);tr=c.member(i,mature)
            np.testing.assert_array_equal(r['q'],q[i]);np.testing.assert_array_equal(r['training_days'],tr);np.testing.assert_array_equal(r['weights'],c.weights(tr,i));assert int(r['latest_maturity_ns'])<c.ISS.iloc[i].value;assert str(r['code_sha256'])==sha(PREV/'core.py')
            refs.append(dict(arm=arm,model=s['model'],day=c.DAYS[i],source=path.relative_to(ROOT.parent).as_posix(),sha256=sha(path),new_fit=False,training_days=len(tr),PASS=True))
        for role in ROLES[2:]:
            ids=c.role_ids(role)
            for variant,v in [('RAW_REFERENCE',q),('LEGACY_SLOT_REFERENCE',legacy),('FINALIST',p)]:
                rows.append(dict(arm=arm,model=s['model'],method=s['method'] if variant=='FINALIST' else variant,variant=variant,role=role,**previous_report.metrics(y[ids],v[ids],burst,dt)))
                for k,slots in enumerate(np.array_split(np.arange(y.shape[1]),4)):lead.append(dict(arm=arm,variant=variant,role=role,lead_group=f'{6+6*k}..{12+6*k}',**previous_report.metrics(y[ids][:,slots],v[ids][:,slots],burst,dt)))
                for label,mask in [('zero',y[ids]==0),('positive',y[ids]>0),('burst',y[ids]>burst),('nonburst',y[ids]<=burst)]:
                    if mask.any():burstrows.append(dict(arm=arm,variant=variant,role=role,stratum=label,TRAIN_burst_threshold=burst,**c.metrics(y[ids][mask],v[ids][mask],burst,dt)))
            aa=previous_report.daystats(y[ids],p[ids],dt,burst)
            for reference,v in [('RAW_REFERENCE',q),('LEGACY_SLOT_REFERENCE',legacy)]:
                bb=previous_report.daystats(y[ids],v[ids],dt,burst)
                for r in previous_report.paired(aa,bb):uncertainty.append(dict(arm=arm,role=role,contrast='FINALIST minus '+reference,**r))
        ids=np.r_[c.role_ids('EXPOSED_EVALUATION'),c.role_ids('OOS_EXTENSION'),c.role_ids('MAY_HISTORICAL')];n=y.shape[1]
        pred.append(pd.DataFrame(dict(arm=arm,model=s['model'],method=s['method'],day_index=np.repeat(ids,n),day=np.repeat(c.DAYS[ids],n),original_role=np.repeat(c.L.split.iloc[ids].to_numpy(),n),original_eligible=np.repeat(c.L.eligible.iloc[ids].to_numpy(),n),slot=np.tile(np.arange(n),len(ids)),slot_hours=dt,y=y[ids].ravel(),raw_Q50=q[ids,:,0].ravel(),raw_Q90=q[ids,:,1].ravel(),legacy_Q90=legacy[ids,:,1].ravel(),final_Q90=p[ids,:,1].ravel())))
    base=pd.read_csv(PREV/'ARM_METRICS.csv');base=base[base.arm.eq('T0_F0')&base.role.isin(ROLES[2:])].copy();base['source']='Historical arrival baseline; no cross-unit score ranking';csv('HISTORICAL_BASELINE_METRICS.csv',base)
    csv('FULL_OOS_METRICS.csv',rows);csv('LEAD_TIME_METRICS.csv',lead);csv('BURST_METRICS.csv',burstrows);csv('PAIRED_UNCERTAINTY.csv',uncertainty);csv('DAILY_REFIT_REUSE_AUDIT.csv',refs);pd.concat(pred,ignore_index=True).to_parquet(ROOT/'FINALIST_PREDICTIONS.parquet',index=False)
    assert len(refs)==546;verify_previous()
    write('NEXT_STAGE_VALIDATION.json',dict(PASS=True,current_v27_immutable=True,current_delivery_sha256=sha(PREV/'DELIVERY_MANIFEST.json'),new_full_period_model_fits=0,reused_daily_refits=546,reused_evaluation_refits=364,finalists=2,prediction_rows=sum(len(p) for p in pred),calibration_source='26 CAL days strictly mature before first evaluation; no eval/May residual updates',May_selection=False,Q50_unchanged=True,zero_future_label_reads=True,protocol_sha256=sha(ROOT/'NEXT_STAGE_PROTOCOL.json'),finalist_freeze_sha256=sha(ROOT/'FINALIST_FREEZE.json')))
    print('NEXT_STAGE_COMPLETE',flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['register','a','b','c']);args=parser.parse_args();{'register':register,'a':stage_a,'b':stage_b,'c':stage_c}[args.phase]()
