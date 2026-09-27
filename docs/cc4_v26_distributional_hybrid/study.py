"""Immutable offline distributional comparison. No production imports."""
import os
for key in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[key] = '1'
from pathlib import Path
import argparse, gzip, hashlib, json, time, tarfile
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import lightgbm as lgb
from distribution import quantiles, cdf, burst_probability, hybrid, ensemble

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'cc4_v2_hourly_future_workload'
REFIT = ROOT.parent / 'cc4_v21_causal_refit_hurdle'
PREV = ROOT.parent / 'cc4_v25_aggregated_target_resolution'
Z = np.load(BASE / 'DATA.npz')
X, Y, DAYS = Z['X'], Z['y'], Z['days'].astype(str)
L = pd.read_csv(BASE / 'DAY_LEDGER.csv')
AV, ISS = pd.to_datetime(L.label_matured_at, utc=True), pd.to_datetime(L.issue_time, utc=True)
TR = np.flatnonzero(L.split.eq('TRAIN') & L.eligible)
OOS = np.flatnonzero(DAYS >= '2024-09-01')
ROLES = ['DEVELOPMENT', 'CALIBRATION', 'EXPOSED_EVALUATION', 'MAY_HISTORICAL']
SEEDS = [20260924, 20260925, 20260926]
PARAMS = dict(num_leaves=15, learning_rate=.03, n_estimators=400, min_child_samples=50,
              n_jobs=1, deterministic=True, force_col_wise=True, random_state=20260924, verbosity=-1)
BURST = json.loads((BASE / 'TARGET_RECONSTRUCTION_AUDIT.json').read_text(encoding='utf-8'))['TRAIN_positive_Q95_burst_threshold_GPUh']
THRESHOLDS = [.1, .2, .3]
WEIGHTS = [.25, .5, .75]
ARMS = ['B0', 'B1', 'B2', 'B3', 'B4', 'B5']
CI_METRICS = ['Q90_pinball', 'Q90_coverage', 'requirement_ratio', 'burst_coverage', 'positive_coverage', 'Q50_MAE']


def need(value, message):
    if not value: raise AssertionError(message)
def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def now(): return pd.Timestamp.now(tz='UTC').isoformat()
def read(path): return json.loads((ROOT / path).read_text(encoding='utf-8'))
def clean(v):
    if isinstance(v, dict): return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray, pd.Series, pd.Index)): return [clean(x) for x in v]
    if isinstance(v, (np.integer, np.bool_)): return v.item()
    if isinstance(v, (float, np.floating)): return float(v) if np.isfinite(v) else None
    if isinstance(v, pd.Timestamp): return str(v)
    return v
def write(name, obj):
    p = ROOT / name; p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8', newline='\n') as f: json.dump(clean(obj), f, ensure_ascii=False, indent=2, allow_nan=False)
def csv(name, rows):
    p = ROOT / (name + '.csv'); need(not p.exists(), 'IMMUTABLE ' + name)
    pd.DataFrame(rows).to_csv(p, index=False, lineterminator='\n')
def ids(role): return np.flatnonzero(L.split.eq(role) & L.eligible)
def membership(i): return np.flatnonzero((AV < ISS.iloc[i]) & (ISS < ISS.iloc[i]) & L.split.ne('PURGE'))
def weights(tr, i): return np.asarray(np.exp2(-np.maximum((ISS.iloc[i] - pd.to_datetime(DAYS[tr], utc=True)).total_seconds() / 86400, 0) / 30))
def cached(family, seed=20260924): return np.load(REFIT / 'predictions' / f'{family}_weighted_c1_s{seed}.npz')['q']
def reused():
    return {'B0': cached('LGBM'), 'B4': np.mean([cached('TFT', s) for s in SEEDS], axis=0),
            'B5': np.mean([cached('DEEPAR', s) for s in SEEDS], axis=0)}
def source_guard():
    for name, digest in read('SOURCE_MANIFEST.json')['files'].items(): need(sha(ROOT.parent / name) == digest, 'SOURCE_DRIFT ' + name)
def guard(final=False):
    f = read('FINAL_SELECTION_FREEZE.json' if final else 'CODE_FREEZE.json')
    for name, digest in f['code'].items(): need(sha(ROOT / name) == digest, 'CODE_DRIFT ' + name)
    need(sha(ROOT / 'PROTOCOL.json') == f['protocol_sha256'], 'PROTOCOL_DRIFT')
    if final: need(sha(ROOT / 'DISTRIBUTION_PARAMETERS.json') == f['distribution_sha256'], 'DISPERSION_DRIFT')


def register():
    need(not (ROOT / 'CODE_FREEZE.json').exists(), 'REGISTERED')
    sources = json.loads((PREV / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files']
    for parent in [REFIT, PREV]:
        for row in json.loads((parent / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))['files']:
            sources[parent.name + '/' + row['path']] = row['sha256']
        sources[parent.name + '/DELIVERY_MANIFEST.json'] = sha(parent / 'DELIVERY_MANIFEST.json')
    write('SOURCE_MANIFEST.json', dict(base_PR=73, primary_model_PR=64, base_commit='65b26fb3663b766b1dbd9d258d4fced6c3eaa13a', files=sources))
    source_guard()
    proof = pd.read_parquet(BASE / 'FEATURE_MATURITY_PROOF.parquet')
    need((pd.to_datetime(proof.feature_available_at, utc=True) <= pd.to_datetime(proof.issue_time, utc=True)).all(), 'FEATURE_TIME')
    need(np.quantile(Y[TR][Y[TR] > 0], .95) == BURST, 'BURST_DRIFT')
    raw = json.loads((PREV / 'RAW_TARGET_AUDIT.json').read_text(encoding='utf-8'))
    need(raw['PASS'], 'RAW_AUTHORITY')
    for arm, q in reused().items(): need(np.isfinite(q[OOS]).all() and (q[OOS, :, 1] >= q[OOS, :, 0]).all(), 'REUSE_AUTHORITY ' + arm)
    write('PROTOCOL.json', dict(time=now(), version='CC4-v2.6', parameters=PARAMS,
        target='Unchanged D-1 18:00 future hourly full-lifetime arrival GPUh; modeled UTC+10 clock',
        temporal='Exact PR64 expanding history, 30-day decay, daily refit, full-day AV<issue and ISS<issue; non-PURGE',
        population='Exact frozen PR63/64 split, eligible evaluation population, 71 X features and existing neural past input; no exclusions',
        B0='Exact raw PR64 weighted daily LightGBM quantiles',
        B1='Hurdle lognormal: binary LightGBM occurrence p and L2 LightGBM positive log(y) mean mu. No Tweedie claim. CDF=(1-p)+p*Phi((log(y)-mu)/sigma), atom1-p at0; Q_tau=0 for tau<=1-p, else exp(mu+sigma*Phi_inverse((tau-1+p)/p)). No scaling/cap/quantile interpolation.',
        dispersion='One sigma frozen from TRAIN-only prior OOS positive log residuals, daily causal fits with >=60 mature days, each scored TRAIN day mature before first DEV issue. sigma=sqrt(recency-weighted mean squared residual), zero bias adjustment. Fixed-location Gaussian likelihood variance estimate, not tuned for coverage. No DEV/CAL/evaluation dispersion updates.',
        B2='Same B0 outside P_B1(Y>unchanged TRAIN burst threshold)>=gate; inside use both B1 quantiles directly, no global uplift/max envelope. Gate in [.1,.2,.3] selected DEV only, then frozen.',
        B3='Convex quantile average (1-w)*B0+w*B5, same w for Q50/Q90, w in [.25,.5,.75] selected DEV only. Not a mixture-CDF quantile. Ordering inherited without cap.',
        B4_B5='Exact PR64 compact TFT and DeepAR architecture/settings, all3 seeds; arithmetic mean of predictions for primary scoring (unlike prior metric-average report), individual seed metrics separately. DeepAR128-path sample quantiles retain Monte Carlo error; no resampling, seed selection or retraining.',
        parameter_selection='B2 gate and B3 weight: lowest DEV Q90 pinball among candidates with ratio<2; ties calibration error then ratio then numeric parameter. If none satisfy ratio, lowest-loss research config still frozen; no CAL retune.',
        selection='Eligibility requires DEV and CAL separately coverage88..92, ratio<2, Q90 pinball<=B0, burst coverage>B0. Positive coverage reported, no new hard gate. 5% pinball improvement and ratio<1.8 preferred. Primary among eligible by mean normalized-to-B0 loss, calibration error, ratio, arm; otherwise B0. No evaluation reranking.',
        support='Only DEV/CAL-eligible frozen arms can be supported. BOTH Dec-Feb and May must pass same point gates and 7-day paired95% CI upper(delta pinball)<0, lower(delta burst coverage)>0. Separate mathematical implementation validity from empirical distributional support. Report 5% improvement preference. Hybrid/ensemble flags apply B2/B3 respectively. No promotion regardless evidence.',
        burst_threshold=BURST, bootstrap=dict(draws=2000, blocks=[1,7], seed=20260928,
        unit='Entire paired observed target day including all24 hours. Recompute ratios in each draw. Any nonfinite draw => entire affected CI unavailable, never dropped/resampled; unadjusted exploratory per-contrast CI.'),
        NO_UNTOUCHED_CONFIRMATION=True, May='exposed diagnostic; no tuning. Earlier mature evaluation labels allowed only in frozen expanding daily refit, never dispersion/selection.',
        provenance='V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1; request/ingestion UNVERIFIED/UNOBSERVED; no historical exactness/immutability assertion',
        mathematical_sources=['https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.lognorm.html','https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html'],
        PRODUCTION_PROMOTED=False, optimizer_executions=0))
    L.to_csv(ROOT / 'DAY_MEMBERSHIP.csv', index=False, lineterminator='\n')
    write('LEAKAGE_MATURITY_AUDIT.json', dict(PASS=True, feature_proof_sha256=sha(BASE / 'FEATURE_MATURITY_PROOF.parquet'),
        raw_authority_sha256=sha(PREV / 'RAW_TARGET_AUDIT.json'), original_labels_sha256=hashlib.sha256(Y.tobytes()).hexdigest(),
        target_unchanged=True, population_unchanged=True, features_unchanged=True, proxy='UNVERIFIED/UNOBSERVED', raw_reconstruction='Inherited PR73 exact raw Job/hourly reconstruction, byte verified; no new raw reinterpretation'))
    code = {p.name: sha(p) for p in ROOT.glob('*.py')}
    write('CODE_FREEZE.json', dict(time=now(), code=code, protocol_sha256=sha(ROOT / 'PROTOCOL.json')))
    print('REGISTERED', flush=True)


def fit_day(task):
    i, phase = task; guard()
    folder = ROOT / 'fits' / phase / DAYS[i]
    need(not folder.exists(), 'FIT_EXISTS ' + str(folder)); folder.mkdir(parents=True)
    tr = membership(i); w = weights(tr, i)
    need(len(tr) >= 60 and (AV.iloc[tr] < ISS.iloc[i]).all(), 'TRAIN_MATURITY')
    np.savez_compressed(folder / 'TRAIN_MEMBERSHIP.npz', day_indices=tr, weights=w)
    x = X[tr].reshape(-1, 71); y = Y[tr].ravel(); sw = np.repeat(w, 24); pos = y > 0
    need(pos.sum() >= 100 and len(np.unique(pos)) == 2, 'DISTRIBUTIONAL_SUPPORT')
    started = time.perf_counter()
    occ = lgb.LGBMClassifier(objective='binary', **PARAMS).fit(x, pos.astype(int), sample_weight=sw).booster_
    loc = lgb.LGBMRegressor(objective='regression', **PARAMS).fit(x[pos], np.log(y[pos]), sample_weight=sw[pos]).booster_
    train_s = time.perf_counter() - started; started = time.perf_counter()
    p = occ.predict(X[i], num_threads=1); mu = loc.predict(X[i], num_threads=1)
    infer_s = time.perf_counter() - started
    np.savez_compressed(folder / 'PARAMETERS.npz', p=p, mu=mu)
    models = {}
    for name, model in [('occurrence', occ), ('positive_location', loc)]:
        path = folder / (name + '.txt.gz'); path.write_bytes(gzip.compress(model.model_to_string().encode(), mtime=0)); models[path.name] = sha(path)
    write(folder.relative_to(ROOT) / 'RECEIPT.json', dict(day_index=i, issue=ISS.iloc[i], training_days=len(tr),
        latest_maturity=AV.iloc[tr].max(), membership_sha256=sha(folder / 'TRAIN_MEMBERSHIP.npz'),
        parameters_sha256=sha(folder / 'PARAMETERS.npz'), model_sha256=models, training_seconds=train_s, inference_seconds=infer_s))
    print('FIT', phase, DAYS[i], len(tr), flush=True)


def run_fits(ix, phase):
    with ProcessPoolExecutor(max_workers=4) as pool: list(pool.map(fit_day, [(int(i), phase) for i in ix]))


def train_dispersion():
    guard(); source_guard(); need(not (ROOT / 'DISTRIBUTION_PARAMETERS.json').exists(), 'DISPERSION_FROZEN')
    cut_i = ids('DEVELOPMENT')[0]
    ix = np.array([i for i in TR if AV.iloc[i] < ISS.iloc[cut_i] and len(membership(i)) >= 60])
    need(len(ix) >= 20, 'DISPERSION_SUPPORT'); run_fits(ix, 'train_oos')
    rows = []
    for i, w in zip(ix, weights(ix, cut_i)):
        mu = np.load(ROOT / 'fits/train_oos' / DAYS[i] / 'PARAMETERS.npz')['mu']
        for h in np.flatnonzero(Y[i] > 0):
            rows.append(dict(day_index=i, day=DAYS[i], hour=h, source_issue=str(ISS.iloc[i]), label_matured_at=str(AV.iloc[i]),
                actual_GPUh=Y[i,h], predicted_log_location=mu[h], residual=np.log(Y[i,h])-mu[h], weight=w))
    frame = pd.DataFrame(rows); frame.to_parquet(ROOT / 'DISPERSION_OOS_MEMBERSHIP.parquet', index=False)
    sigma = float(np.sqrt(np.average(frame.residual.to_numpy() ** 2, weights=frame.weight)))
    need(np.isfinite(sigma) and sigma > 0, 'INVALID_SIGMA')
    write('DISTRIBUTION_PARAMETERS.json', dict(time=now(), family='zero-atom lognormal', sigma=sigma, days=ix,
        residual_rows=len(frame), residual_sha256=sha(ROOT / 'DISPERSION_OOS_MEMBERSHIP.parquet'),
        source_roles=['TRAIN'], available_before_issue=ISS.iloc[cut_i], changed_after_development=False,
        TWEEDIE_EVALUATED=False, DISTRIBUTIONAL_IMPLEMENTATION_VALID=True))
    print('DISPERSION FROZEN', sigma, len(frame), flush=True)


def distribution_predictions(ix, phase):
    sigma = read('DISTRIBUTION_PARAMETERS.json')['sigma']; q = np.full((len(DAYS),24,2),np.nan); risk = np.full(Y.shape,np.nan)
    for i in ix:
        z = np.load(ROOT / 'fits' / phase / DAYS[i] / 'PARAMETERS.npz')
        q[i] = quantiles(z['p'], z['mu'], sigma); risk[i] = burst_probability(BURST,z['p'],z['mu'],sigma)
        for k,tau in enumerate([.5,.9]):
            positive = q[i,:,k] > 0
            need(np.allclose(cdf(q[i,:,k],z['p'],z['mu'],sigma)[positive],tau,atol=1e-10,rtol=0), 'CDF_INVERSION')
            need((1-z['p'][~positive] >= tau).all(), 'ZERO_ATOM')
    return q,risk


def metric(y,q):
    y=np.asarray(y); q=np.asarray(q); n=y.size; total=y.sum(); e=y-q[...,1]; pos=y>0; burst=y>BURST
    return dict(N_hours=n, actual_GPUh=float(total), Q90_coverage=float(np.mean(e<=0)) if n else np.nan,
        calibration_error=abs(float(np.mean(e<=0))-.9) if n else np.nan,
        Q90_pinball=float(np.maximum(.9*e,-.1*e).mean()) if n else np.nan,
        requirement_ratio=float(q[...,1].sum()/total) if total else np.nan,
        positive_coverage=float(np.mean(e[pos]<=0)) if pos.any() else np.nan,
        burst_coverage=float(np.mean(e[burst]<=0)) if burst.any() else np.nan,
        Q50_MAE=float(np.abs(y-q[...,0]).mean()) if n else np.nan,
        Q50_WAPE=float(np.abs(y-q[...,0]).sum()/total) if total else np.nan)


def development():
    guard(); source_guard(); need(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'ALREADY_SELECTED')
    ix=OOS[DAYS[OOS]<='2024-11-30']; run_fits(ix,'development'); q,risk=distribution_predictions(ix,'development')
    np.savez_compressed(ROOT/'DEVELOPMENT_DISTRIBUTION.npz',q=q,risk=risk)
    base=reused(); dev=ids('DEVELOPMENT'); candidates=[]
    for gate in THRESHOLDS:
        candidates.append(dict(arm='B2',parameter=gate,**metric(Y[dev],hybrid(base['B0'][dev],q[dev],risk[dev],gate))))
    for w in WEIGHTS:
        candidates.append(dict(arm='B3',parameter=w,**metric(Y[dev],ensemble(base['B0'][dev],base['B5'][dev],w))))
    csv('DEVELOPMENT_PARAMETER_COMPARISON',candidates)
    def choose(arm):
        rows=[r for r in candidates if r['arm']==arm]; safe=[r for r in rows if r['requirement_ratio']<2]
        return min(safe or rows,key=lambda r:(r['Q90_pinball'],r['calibration_error'],r['requirement_ratio'],r['parameter']))['parameter']
    config=dict(gate=choose('B2'),weight=choose('B3'))
    pred=assemble(base,q,risk,config); rows=[]
    for role in ROLES[:2]:
        ii=ids(role)
        for arm in ARMS: rows.append(dict(role=role,arm=arm,**metric(Y[ii],pred[arm][ii])))
    csv('DEVELOPMENT_CALIBRATION_METRICS',rows)
    table=pd.DataFrame(rows); eligibility={a:all(point_gate(metric(Y[ids(r)],pred[a][ids(r)]),metric(Y[ids(r)],pred['B0'][ids(r)])) for r in ROLES[:2]) for a in ARMS[1:]}
    eligible=[a for a in ARMS[1:] if eligibility[a]]
    def rank(a):
        return (np.mean([table.query('arm==@a and role==@r').Q90_pinball.iloc[0]/table.query('arm=="B0" and role==@r').Q90_pinball.iloc[0] for r in ROLES[:2]]),
                table.query('arm==@a').calibration_error.mean(),table.query('arm==@a').requirement_ratio.mean(),a)
    freeze=read('CODE_FREEZE.json')
    write('FINAL_SELECTION_FREEZE.json',dict(time=now(),**config,eligibility=eligibility,primary=min(eligible,key=rank) if eligible else 'B0',
        selection_roles=ROLES[:2],parameter_selection_role='DEVELOPMENT',code=freeze['code'],protocol_sha256=freeze['protocol_sha256'],
        distribution_sha256=sha(ROOT/'DISTRIBUTION_PARAMETERS.json'),NO_UNTOUCHED_CONFIRMATION=True,evaluation_scored=False))
    print('SELECTION FROZEN',config,eligibility,flush=True)


def assemble(base,q,risk,config):
    return dict(**base,B1=q,B2=hybrid(base['B0'],q,risk,config['gate']),B3=ensemble(base['B0'],base['B5'],config['weight']))


def point_gate(m,b):
    return bool(.88<=m['Q90_coverage']<=.92 and m['requirement_ratio']<2 and m['Q90_pinball']<=b['Q90_pinball'] and m['burst_coverage']>b['burst_coverage'])


def daily_sums(y,q):
    e=y-q[...,1]; pos=y>0; burst=y>BURST
    return np.stack([np.full(len(y),24),y.sum(1),q[...,1].sum(1),(e<=0).sum(1),np.maximum(.9*e,-.1*e).sum(1),
        pos.sum(1),((e<=0)&pos).sum(1),burst.sum(1),((e<=0)&burst).sum(1),np.abs(y-q[...,0]).sum(1)],-1)
def values(s):
    with np.errstate(divide='ignore',invalid='ignore'):
        return np.stack([s[...,4]/s[...,0],s[...,3]/s[...,0],s[...,2]/s[...,1],s[...,8]/s[...,7],s[...,6]/s[...,5],s[...,9]/s[...,0]],-1)
def bootstrap(y,preds,role):
    sums={a:daily_sums(y,preds[a]) for a in ARMS}; rows=[]; n=len(y)
    for block in [1,7]:
        rng=np.random.default_rng(20260928+block)
        starts=rng.integers(0,n,size=(2000,int(np.ceil(n/block))))
        index=((starts[...,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
        ref=values(sums['B0'][index].sum(1))
        for a in ARMS[1:]:
            draws=values(sums[a][index].sum(1))-ref
            point=values(sums[a].sum(0))-values(sums['B0'].sum(0))
            for k,m in enumerate(CI_METRICS):
                invalid=int((~np.isfinite(draws[:,k])).sum()); lo,hi=(np.nan,np.nan) if invalid else np.quantile(draws[:,k],[.025,.975])
                rows.append(dict(role=role,arm=a,reference='B0',block_days=block,metric=m,delta=point[k],low=lo,high=hi,invalid_draws=invalid,draws=2000))
    return rows


def evaluation():
    guard(True);source_guard();need(not (ROOT/'EVALUATION_COMPLETE.json').exists(),'ALREADY_EVALUATED')
    started=time.perf_counter(); ix=OOS[DAYS[OOS]>'2024-11-30'];run_fits(ix,'evaluation')
    q,risk=distribution_predictions(ix,'evaluation'); d=np.load(ROOT/'DEVELOPMENT_DISTRIBUTION.npz')
    early=OOS[DAYS[OOS]<='2024-11-30'];q[early]=d['q'][early];risk[early]=d['risk'][early]
    config=read('FINAL_SELECTION_FREEZE.json');pred=assemble(reused(),q,risk,config)
    np.savez_compressed(ROOT/'FROZEN_PREDICTIONS.npz',**pred,risk=risk,days=DAYS)
    metrics=[];strata=[];horizons=[];records=[];ci=[];seedrows=[]
    for role in ROLES:
        ii=ids(role);y=Y[ii]
        for arm in ARMS:
            p=pred[arm][ii];need(np.isfinite(p).all() and (p[...,1]>=p[...,0]).all() and (p>=0).all(),'INVALID_OUTPUT')
            metrics.append(dict(role=role,arm=arm,**metric(y,p)))
            for name,mask in [('zero',y==0),('positive',y>0),('burst',y>BURST),('body',(y>0)&(y<=BURST)),('hybrid_gate',risk[ii]>=config['gate']),('normal_gate',risk[ii]<config['gate'])]:
                strata.append(dict(role=role,arm=arm,stratum=name,**metric(y[mask],p[mask])))
            for h in range(24):horizons.append(dict(role=role,arm=arm,hour=h,**metric(y[:,h],p[:,h])))
            for j,i in enumerate(ii):
                for h in range(24):records.append(dict(day=DAYS[i],day_index=i,role=role,issue=str(ISS.iloc[i]),hour=h,arm=arm,actual_GPUh=y[j,h],Q50=p[j,h,0],Q90=p[j,h,1],burst_risk=risk[i,h],gate=bool(risk[i,h]>=config['gate'])))
        for family in ['TFT','DEEPAR']:
            for seed in SEEDS:seedrows.append(dict(role=role,family=family,seed=seed,**metric(y,cached(family,seed)[ii])))
        if role in ROLES[2:]:ci.extend(bootstrap(y,{a:pred[a][ii] for a in ARMS},role))
    csv('MODEL_METRICS',metrics);csv('STRATIFIED_METRICS',strata);csv('HORIZON_METRICS',horizons);csv('SEED_METRICS',seedrows);csv('PAIRED_UNCERTAINTY',ci)
    pd.DataFrame(records).to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
    gates=[];support={}
    for a in ARMS[1:]:
        good=config['eligibility'][a]
        for role in ROLES[2:]:
            ii=ids(role);m=metric(Y[ii],pred[a][ii]);b=metric(Y[ii],pred['B0'][ii]);point=point_gate(m,b)
            cr=[r for r in ci if r['role']==role and r['arm']==a and r['block_days']==7]
            loss=next(r for r in cr if r['metric']=='Q90_pinball');burst=next(r for r in cr if r['metric']=='burst_coverage')
            robust=bool(loss['invalid_draws']==burst['invalid_draws']==0 and loss['high']<0 and burst['low']>0)
            gates.append(dict(role=role,arm=a,DEV_CAL_eligible=config['eligibility'][a],point_gate=point,robust_direction=robust,
                preferred_five_percent_pinball=m['Q90_pinball']<=.95*b['Q90_pinball'],preferred_ratio=m['requirement_ratio']<1.8))
            good=good and point and robust
        support[a]=bool(good)
    csv('GATES',gates)
    write('FINAL_VERDICT.json',dict(primary=config['primary'],DISTRIBUTIONAL_IMPLEMENTATION_VALID=True,TWEEDIE_EVALUATED=False,
        DISTRIBUTIONAL_MODEL_SUPPORTED=support['B1'],HYBRID_SUPERIOR_TO_LGBM=support['B2'],ENSEMBLE_SUPERIOR_TO_LGBM=support['B3'],
        arm_support=support,PRODUCTION_REPLACEMENT_SUPPORTED=False,OPTIMIZER_INTEGRATION_READY=False,PRODUCTION_PROMOTED=False,
        NO_UNTOUCHED_CONFIRMATION=True,production='Unchanged',provenance='UNVERIFIED/UNOBSERVED'))
    write('EVALUATION_COMPLETE.json',dict(time=now(),seconds=time.perf_counter()-started,selection_sha256=sha(ROOT/'FINAL_SELECTION_FREEZE.json'),predictions_sha256=sha(ROOT/'FROZEN_PREDICTIONS.npz')))
    print('EVALUATION COMPLETE',support,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['register','train_dispersion','development','evaluation']);args=parser.parse_args();globals()[args.stage]()
