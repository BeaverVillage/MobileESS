"""Frozen post-selection diagnostics. No fits or selection mutations."""
import pickle
import time
from .common import *
from .experiment import predict,replay,tail_metrics,cap


def guard_selection():
    guard_prereg();r=get('METHOD_SELECTION_COMMIT_RECEIPT');path='dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_METHOD_SELECTION.json'
    assert git('show',f"{r['commit']}:{path}",binary=True)==(ROOT/path).read_bytes()
    return r['commit']


def frozen_model(track,h):
    p=OUT/'models'/f'{track}_u{h}.pkl'
    assert sha(p.read_bytes())==get('MODEL_FREEZE')['model_SHA256'][p.name]
    return pickle.loads(p.read_bytes())


def importance():
    guard_selection();d=panel();d=d[d.role=='DEVELOPMENT'].reset_index(drop=True);rows=[];times=[]
    for track in ('P','PW'):
        for h in U:
            pack=frozen_model(track,h);pre=pack['preprocess'];models=pack['model'];started=time.perf_counter()
            for name in ('B1','B2','C2','C3'):
                objects=[(alpha,m) for alpha,m in zip((.5,.9),models[name])] if name.startswith('B') else [(None,models[name])]
                for alpha,m in objects:
                    df=d[d.runtime_seconds<=h*3600].reset_index(drop=True) if alpha else d
                    x=pre.transform(df);t=df.runtime_seconds.to_numpy() if alpha else df.runtime_seconds.gt(h*3600).to_numpy()
                    def pred(a):return m.predict(a) if alpha else m.predict_proba(a)[:,1]
                    def loss(y):
                        e=t-y
                        return float(np.maximum(alpha*e,(alpha-1)*e).mean()) if alpha else float(np.mean(e*e))
                    base=loss(pred(x))
                    if name in ('B1','C2'):gain=np.asarray(m.booster_.feature_importance(importance_type='gain'),float)
                    else:
                        scores=m.get_booster().get_score(importance_type='total_gain')
                        gain=np.asarray([scores.get('f'+str(i),0.) for i in range(x.shape[1])])
                    agg={c:float(gain[np.array(pre.groups)==c].sum()) for c in pre.fields}
                    total=sum(agg.values())
                    for feature in pre.fields:
                        deltas=[]
                        for repeat in range(3):
                            changed=df.copy();order=np.random.default_rng(SEED+repeat).permutation(len(df))
                            changed[feature]=df[feature].to_numpy()[order]
                            deltas.append(loss(pred(pre.transform(changed)))-base)
                        rows.append(dict(track=track,u_hours=h,model=name,alpha=alpha,feature=feature,role='DEVELOPMENT',N=len(df),
                             gain=agg[feature],relative_gain=agg[feature]/total if total else 0.,
                             gain_rank=1+sum(v>agg[feature] for v in agg.values()) if total else None,
                             permutation_loss='native quantile pinball' if alpha else 'Brier',baseline_loss=base,
                             permutation_delta_mean=float(np.mean(deltas)),permutation_delta_by_repeat=deltas))
            times.append(dict(track=track,u_hours=h,seconds=time.perf_counter()-started));print('importance',track,h,flush=True)
    write('FEATURE_IMPORTANCE_DIAGNOSTIC',dict(status='POST_SELECTION_DIAGNOSTIC_ONLY',role='DEVELOPMENT_ONLY',
          gain_definition='LGBM total split gain; XGB total_gain; sum encoded columns by original field; ties share dense rank',
          permutation='3 repeats, seed4003+i; original feature permuted before frozen preprocessing; native single-model loss, not feature selection',
          records=rows,wallclock_records=[r for r in rows if r['feature']=='requested_seconds'],inference_times=times,
          model_redesign=False,exposed_importance=False))


def perturb():
    commit=guard_selection();selection=get('METHOD_SELECTION')['selected'];d=panel();d=d[d.role=='EXPOSED_EVALUATION'].reset_index(drop=True)
    anchors=[selection] if selection else [dict(track=t,u_hours=4,body='B1',classifier='C2',policy='R1') for t in ('P','PW')]
    rows=[]
    for a in anchors:
        pack=frozen_model(a['track'],a['u_hours']);model,pre=pack['model'],pack['preprocess']
        eta=next(r['eta'] for r in get('ETA_SELECTION')['rows'] if all(r[k]==a[k] for k in ('track','u_hours','body','classifier')))
        original,_=predict(model,pre,d)
        for tag,factor in [('S0',1.),('S1',.9),('S2',1.1)]:
            changed=d.copy();changed['requested_seconds']=changed.requested_seconds*factor
            pred,_=predict(model,pre,changed)
            q=pred[a['body']][:,1];prob=pred[a['classifier']]
            rows.append(dict(anchor=a,scenario=tag,walltime_multiplier=factor,eta=eta,
                max_Q50_change_sec=float(np.max(np.abs(pred[a['body']][:,0]-original[a['body']][:,0]))),
                max_Q90_change_sec=float(np.max(np.abs(q-original[a['body']][:,1]))),
                mean_abs_Q90_change_sec=float(np.mean(np.abs(q-original[a['body']][:,1]))),
                max_probability_change=float(np.max(np.abs(prob-original[a['classifier']]))),
                flag_change_N=int(((prob>=eta)!=(original[a['classifier']]>=eta)).sum()) if eta is not None else None,
                tail=tail_metrics(changed,prob,q,a['u_hours'],eta),hybrid=replay(changed,q,prob,a['u_hours'],eta,a['policy'])))
    write('PROXY_PERTURBATION_SENSITIVITY',dict(status='FROZEN_SELECTED_METHOD' if selection else 'PREREGISTERED_ANCHOR_ONLY_NO_SELECTED_METHOD',
       selection_commit=commit,post_selection=True,refits=0,reselection=False,
       interpretation='Generic proxy discrepancy, not observed request modifications. With eta NONE there is no valid discrete decision or hybrid effect to estimate; quantile/probability shifts remain descriptive.',
       perturbation_scope='Walltime predictor and R2 comparator changed together; current RSP and actual labels fixed. P-W excludes walltime from predictors.',records=rows))


def selectivity_audit():
    guard_selection();d=panel();d=d[d.role=='CALIBRATION'].reset_index(drop=True);rows=[]
    for track in ('P','PW'):
        for h in U:
            pred=pd.read_parquet(OUT/f'V40S4_PREDICTIONS_{track}_u{h}_CALIBRATION.parquet')
            t=d.runtime_seconds.to_numpy();g=d.num_gpus_req.to_numpy();y=t>h*3600
            for b in ('B1','B2','B3'):
                mass=g*np.maximum(t-pred[b+'_Q90'].to_numpy(),0)
                for c in ('C0','C1','C2','C3'):
                    prob=pred[c+'_p_tail'].to_numpy();feasible=[];within=[]
                    for eta in np.unique(np.r_[0.,prob,1.]):
                        f=prob>=eta
                        rec=float(f[y].mean());gr=float(g[f&y].sum()/g[y].sum());mc=float(mass[f].sum()/mass.sum())
                        r=dict(eta=float(eta),flagged_fraction=float(f.mean()),recall=rec,GPU_recall=gr,mass_capture=mc)
                        if rec>=.9 and gr>=.9 and mc>=.8:feasible.append(r)
                        if f.mean()<=cap(y.mean()):within.append(r)
                    need=min(feasible,key=lambda r:r['flagged_fraction']) if feasible else None
                    best=max(within,key=lambda r:min(r['recall']/.9,r['GPU_recall']/.9,r['mass_capture']/.8)) if within else None
                    saved=next(r for r in get('ETA_SELECTION')['rows'] if (r['track'],r['u_hours'],r['body'],r['classifier'])==(track,h,b,c))
                    rows.append(dict(track=track,u_hours=h,body=b,classifier=c,tail_N=int(y.sum()),support_sufficient=int(y.sum())>=100,
                         selectivity_cap=cap(y.mean()),selected_eta=saved['eta'],minimum_flagging_needed_for_three_safety_targets=need,
                         best_joint_safety_within_selectivity=best,
                         diagnostic_only='Tradeoff decomposition of frozen CAL predictions; alternate thresholds never selected or applied to evaluation'))
    write('SELECTIVITY_AUDIT',dict(status='READ_ONLY_POST_SELECTION',records=rows,eta_retuned=False))


if __name__=='__main__':
    importance();perturb();selectivity_audit()
