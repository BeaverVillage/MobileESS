from common10 import *
import numpy as np,pandas as pd,shutil
def grids(train):
    y=train.loc[train.event,'duration_lower'].to_numpy(float);upper=float(np.max(train.duration_lower))
    endpoint=max(7*86400,float(np.ceil(upper/43200)*43200))
    head=read(V9/'HAZARD_BIN_CONTRACT.json')['edges_seconds'];head=[x for x in head if x<=86400]
    g1=sorted(set(head+list(np.arange(97200,259200+1,10800))+list(np.arange(280800,604800+1,21600))+list(np.arange(648000,endpoint+1,43200))))
    tail=np.sort(y[y>86400]);adaptive=[86400.];min_events=100;minwidth=10800.;maxwidth=43200.;support=[]
    while adaptive[-1]<endpoint:
        left=adaptive[-1];remaining=tail[tail>left]
        desired=remaining[min_events-1] if len(remaining)>=min_events else endpoint
        right=min(endpoint,max(left+minwidth,min(left+maxwidth,float(np.ceil(desired/900)*900))))
        count=int(np.sum((tail>left)&(tail<=right)));support.append(dict(left=left,right=right,events=count,minimum_met=count>=min_events))
        adaptive.append(right)
    # Sparse far tail cannot meet event minimum within max width: do not invent bins.
    # Stop at the last adequately supported boundary; use explicit continuation.
    stop=len(adaptive)
    for j,r in enumerate(support):
        if not r['minimum_met']:stop=j+1;break
    g2=head+adaptive[1:stop]
    t0=259200.;lower=train.duration_lower.to_numpy(float);event=train.event.to_numpy(bool);n=int(np.sum(event&(lower>t0)));exposure=float(np.maximum(lower-t0,0).sum())
    continuation=dict(threshold_seconds=t0,tail_event_N=n,tail_censored_N=int(np.sum(train.censored&(train.duration_lower>t0))),tail_exposure_seconds=exposure,
        exponential_rate=n/exposure if n>=50 and exposure>0 else None,adequate=n>=50,maximum_observed_training_runtime=float(y.max()),maximum_censor_lower=float(lower.max()),
        estimator='exponential excess lifetime MLE events / total observed tail exposure; exact and right-censored TRAIN only')
    continuation['by_grid']={}
    for name,grid in [('G0',read(V9/'HAZARD_BIN_CONTRACT.json')['edges_seconds']),('G1',g1),('G2',g2)]:
        threshold=min(259200.,float(grid[-1]));events=int(np.sum(event&(lower>threshold)));exposure=float(np.maximum(lower-threshold,0).sum())
        continuation['by_grid'][name]=dict(threshold_seconds=threshold,tail_event_N=events,tail_censored_N=int(np.sum(train.censored&(train.duration_lower>threshold))),tail_exposure_seconds=exposure,exponential_rate=events/exposure if events>=50 and exposure>0 else None,adequate=events>=50)
    return dict(G0=read(V9/'HAZARD_BIN_CONTRACT.json')['edges_seconds'],G1=g1,G2=g2,G2_support=support,G2_min_events=100,G2_min_width=10800,G2_max_width=43200,G2_sparse_tail_rule='Stop explicit bins before first interval lacking100 events within12h, then positive-rate continuation'),continuation
def main():
    ROOT.mkdir(exist_ok=True);LOCAL.mkdir(exist_ok=True)
    prior=[]
    for folder in [V6,V7,V8,V9]:
        m=read(folder/'DELIVERY_MANIFEST.json')
        for r in m['files']:assert sha(folder/r['relative'])==r['sha256'],str(folder/r['relative'])
        prior.append(dict(namespace=folder.name,N=len(m['files']),manifest=record(folder/'DELIVERY_MANIFEST.json')))
    write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,prior=prior,April_payload_decoded=False,May_payload_decoded=False))
    shutil.copyfile(Path('C:/Users/kjw39/.codex/attachments/12d6d1aa-ec1d-4f19-96ad-f1afbc11c67f/붙여넣은 텍스트.txt'),ROOT/'USER_REQUEST.txt')
    for name in ['FEATURE_CONTRACT.json','TEMPORAL_FOLD_CONTRACT.json','TEMPORAL_FOLD_SUPPORT.csv','RIGHT_CENSORING_AUDIT.json','RUNTIME_TARGET_AUTHORITY_AUDIT.json']:
        shutil.copyfile(V9/name,ROOT/name)
    write('FOLD_MEMBERSHIP_REFERENCE.json',dict(source=record(V9/'TEMPORAL_FOLD_MEMBERSHIP.csv'),exact_V9_membership_reused=True,
        prepared_role_files=[record(V9/'.local'/f'fold{i}'/(role+'.parquet')) for i in range(1,6) for role in ['TRAIN','CAL','VALID']]))
    allgrids={};tails={}
    for i in [1,2,3,4,5,'final']:
        train=fold_data(i,'TRAIN');allgrids[str(i)],tails[str(i)]=grids(train)
    write('TAIL_GRID_CANDIDATES.json',dict(time=now(),by_fold=allgrids,TRAIN_only=True,short_bins='Preserve V9 sub15minute bins to isolate tail representation',selection_design='First choose grid/continuation from uncalibrated T1 five-fold scores using fixed gates/rank; then compare calibrations only on that raw learner. Interaction search intentionally omitted. G0 stays eligible as null refinement.'))
    write('TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json',dict(time=now(),by_fold=tails,methods=['LAST_RATE','TRAIN_EXPONENTIAL'],parametric_T4='Not implemented unless terminal-extrapolation-specific evidence warrants separate preregistered extension',never_finite_endpoint_truncate=True))
    landmarks=[900,1800,3600,7200,14400,28800,43200,86400,172800,259200,604800]
    write('CALIBRATION_LANDMARK_CONTRACT.json',dict(time=now(),seconds=landmarks,weights='Equal total weight per landmark among known statuses; one group fit reweights landmarks within its own support',
        known_event='Completion observed strictly before prediction UTC day; exact status at every landmark',
        known_censor='For still-running observation at cutoff, status0 only at landmark strictly below elapsed observed; otherwise unknown and excluded',
        CAL_source='Out-of-training submissions starting at base TRAIN cutoff; historical CAL plus prior VALID observations for rolling within preApril only',
        calibration_families=['C0_NONE','C1_ISOTONIC','C2_LOGISTIC'],C3='omitted to keep focused comparison',
        strict_monotone='g(p)=0.01*p+0.99*g_fitted(p); endpoint preserving continuous piecewise-linear isotonic or logistic(a*logit(p)+b), a in[.05,20], b in[-20,20]',
        logistic_fit_conditioning='Fit logit inputs clipped to[-30,30]; inference function uses exact log-domain logits with no probability clipping',
        windows=['STATIC','ROLLING14','ROLLING28'],risk_boundaries='33.333/66.667 percentiles of raw TRAIN p4 predictions; tied edges collapse groups',
        maximum_groups=3,group_minimum=dict(total=500,completed=200,long_gt4h=100,long_gt12h=50),
        insufficient_group='pooled same-state map; insufficient pooled support500 falls back identity',
        April='final maps from latest preApril state are immutable throughout exposed regression; no April observations enter calibration'))
    write('EXPERIMENT_PROTOCOL.json',dict(time=now(),base=BASE,learner=read(V9/'EXPERIMENT_PROTOCOL.json')['D1'],backend='CPU4 consistently for all selection/freeze; GPU benchmark only',
        backend_tolerance=dict(max_absolute_quantile_seconds=.1,max_relative_quantile_error=1e-6),no_backend_change_after_April=True,
        stages=['T0 reproduce frozen V9','T1 three TRAIN-frozen grids x two continuation methods, same learner settings','Choose one raw grid/continuation with safety-first gate count then pinball/reservation/MAE/std','T2/T3: chosen raw learner x C1/C2 x STATIC/ROLLING14/ROLLING28; include T1 no calibration','Evaluate preApril remaining for all thirteen finalists, then freeze one'],
        gates=dict(pooled_coverage=[.88,.92],min_fold_coverage=.85,support_N=100,pooled_long_gt4h=.85,min_supported_fold_long_gt4h=.80,
            pooled_long_gt12h=.80,min_supported_fold_long_gt12h=.70,zero_support_count=0,proper_score_finite=True,reservation_to_W0_max=.8,
            queue_starts_relative_W0_per_fold_min=.95,queue_capacity_violations=0,queue_horizon_exhaustion=0,remaining_coverage=[.88,.92]),
        selection='Eligibility before ranking; eligible rank Q90 pinball, reservation/actual GPUh, Q50 MAE, coverage std. If none eligible, diagnostic candidate fewest failed gates then same rank; never promote',
        score='Exact proper log probability of common observed one-second cell [max(0,T-.5),T+.5]; zero-duration first half-cell; right censor log survival at observed elapsed. Stable analytic interval probabilities, no score floor. Brier known-status landmark integral explicitly not IPCW population IBS.',
        tailrisk='Raw pre-calibration p4, optional p12 diagnostic; no actual-long inference keys',
        queue=read(V9/'EXPERIMENT_PROTOCOL.json')['queue'],April_queue='Exact frozen V9 issue/site ledger; frozen preApril calibration only',
        conditional='Same calibrated full survival; ratio S(e+r)/S(e), no separate fit or remaining rescale',
        April_status='EXPOSED_REGRESSION_ONLY',April_calibration_updates=False,May_payload_allowed=False))
    files=['FEATURE_CONTRACT.json','TEMPORAL_FOLD_CONTRACT.json','FOLD_MEMBERSHIP_REFERENCE.json','TAIL_GRID_CANDIDATES.json','TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json','CALIBRATION_LANDMARK_CONTRACT.json','EXPERIMENT_PROTOCOL.json']
    write('PREREGISTRATION.json',dict(time=now(),files=[record(ROOT/n) for n in files],before_any_V10_predictive_evaluation=True))
    print('V10_PREREGISTERED',[(k,{g:len(v[g])-1 for g in ['G0','G1','G2']}) for k,v in allgrids.items()],flush=True)
if __name__=='__main__':main()
