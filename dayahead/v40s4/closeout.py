"""Assemble frozen results without deriving a new winner."""
from .common import *
from .diagnostics import guard_selection
from dayahead.v40s3.contracts import metrics,slots,FIELDS


def main():
    guard_selection();dev=get('DEV_CAL_RESULTS');exposed=get('EXPOSED_RESULTS');selection=get('METHOD_SELECTION')
    allbody=dev['body']+exposed['body'];alltail=dev['tail']+exposed['tail'];records=dev['records']+exposed['records']
    for track,label in [('P','P'),('PW','PW')]:
        pd.DataFrame([r for r in allbody if r['track']==track]).to_csv(OUT/f'V40S4_TRACK_{label}_BODY_RESULTS.csv',index=False)
        pd.DataFrame([r for r in alltail if r['track']==track]).to_csv(OUT/f'V40S4_TRACK_{label}_TAIL_RESULTS.csv',index=False)
    flat=[]
    for r in records:
        m=r['hybrid'] or {}
        flat.append(dict(track=r['track'],role=r['role'],u_hours=r['u_hours'],body=r['body'],classifier=r['classifier'],policy=r['policy'],
          eta=r['tail']['eta'],status='EVALUATED' if m else 'NOT_EXECUTED_NO_CAL_ELIGIBLE_ETA',requested_denominator=r['tail']['N'],
          overall_coverage=m.get('coverage'),GPU_coverage=m.get('GPU_coverage'),underpredicted_job_count=m.get('underpredicted_job_count'),
          positive_residual_seconds=m.get('positive_error_sec'),GPU_positive_miss=m.get('GPU_underprediction_sec'),
          overreservation_GPU_hours=m.get('overreservation_GPU_hours'),P95_overreservation_job_sec=m.get('overreservation_P95_sec'),
          completion_slot_MAE=m.get('completion_slot_MAE'),body_miss_sec=m.get('body_miss_sec'),tail_miss_sec=m.get('tail_miss_sec'),
          flagged_fraction=m.get('flagged_fraction'),fallback_use_rate=m.get('fallback_use_rate'),GPU_mass_ratio=m.get('GPU_mass_ratio'),overreservation_ratio=m.get('overreservation_ratio'),
          **{k+'_gate':v for k,v in r['gates'].items()}))
    pd.DataFrame(flat).to_csv(OUT/'V40S4_HYBRID_RESULTS.csv',index=False)
    pd.DataFrame(flat).to_csv(OUT/'V40S4_EXACT_GATE_TABLE.csv',index=False)
    for policy in ('R0','R1','R2'):
        write(policy+'_REPORT',dict(policy=policy,definition=get('PREREGISTRATION')['robust'][policy],
          status='NO_SELECTED_POLICY' if not selection['selected'] else 'FROZEN_CANDIDATE_DIAGNOSTIC',
          records=[r for r in flat if r['policy']==policy],
          no_eta_rule='No valid CAL eta means no tail_flag and no eligible hybrid replay. Metrics are null, not manufactured all-body/all-tail alternatives.',
          guaranteed_runtime_bound=False,production_integration=False))
    p=panel();reference={}
    for role,d in p.groupby('role'):
        reference[role]=dict(current_recipe=metrics(d.runtime_seconds,slots(d.reference_safe_sec)*900,d.num_gpus_req),RW=metrics(d.runtime_seconds,slots(d.requested_seconds)*900,d.num_gpus_req))
    write('GPU_WEIGHTED_UNDERPREDICTION',dict(definition='sum requested_GPU*max(T-duration,0)',weight_role='Recorded GPU requests, not measured allocation; dual predictor/weight role explicitly assumed in P and P-W',
          reference=reference,selected_improvement=None if selection['selected'] is None else 'see frozen selected record',records=flat,
          current_reference_scope='Same immutable S3 current-recipe seconds; no exact production Apr01 final-state equivalence claimed'))
    write('OVERRESERVATION_REPORT',dict(definition='sum requested_GPU*max(duration-T,0)/3600',cap=3.,reference=reference,records=flat,
          selected_ratio=None if selection['selected'] is None else 'see frozen selected record',zero_reference_rule='No smoothing; zero requires zero'))
    # Paired P-PW metrics, preserving exactly the same (u, model, role, group).
    deltas=[]
    for a in [r for r in allbody if r['track']=='P']:
        b=next(r for r in allbody if r['track']=='PW' and all(r[k]==a[k] for k in ('u_hours','body','role','group')))
        deltas.append(dict(kind='body',u_hours=a['u_hours'],body=a['body'],role=a['role'],group=a['group'],
          **{k+'_P_minus_PW':a[k]-b[k] for k in ['coverage','GPU_coverage','Q50_MAE_sec','MAE_sec','WAPE','GPU_underprediction_sec']}))
    for a in [r for r in alltail if r['track']=='P']:
        b=next(r for r in alltail if r['track']=='PW' and all(r[k]==a[k] for k in ('u_hours','body','classifier','role')))
        deltas.append(dict(kind='tail',u_hours=a['u_hours'],body=a['body'],classifier=a['classifier'],role=a['role'],
          **{k+'_P_minus_PW':a[k]-b[k] if a[k] is not None and b[k] is not None else None for k in ['ROC_AUC','PR_AUC','Brier','ECE','recall','GPU_recall','mass_capture','flagged_fraction']}))
    for a in [r for r in flat if r['track']=='P']:
        b=next(r for r in flat if r['track']=='PW' and all(r[k]==a[k] for k in ('u_hours','body','classifier','policy','role')))
        deltas.append(dict(kind='hybrid',u_hours=a['u_hours'],body=a['body'],classifier=a['classifier'],policy=a['policy'],role=a['role'],
          **{k+'_P_minus_PW':a[k]-b[k] if a[k] is not None and b[k] is not None else None for k in ['GPU_positive_miss','overreservation_GPU_hours','overall_coverage','GPU_coverage']}))
    pertrack={}
    for track,winner in selection['per_track'].items():
        pertrack[track]=False if winner is None else next(r['gates']['PASS'] for r in exposed['records'] if all(r[k]==winner[k] for k in ('track','u_hours','body','classifier','policy')))
    interpretation=('PERFORMANCE_DEPENDS_STRONGLY_ON_RECORDED_WALLTIME_PROXY' if pertrack['P'] and not pertrack['PW'] else
                    'REQUEST_STATE_INFORMATION_BEYOND_WALLTIME_IS_USEFUL' if pertrack['PW'] else 'REQUEST_STATE_PROXY_INFORMATION_STILL_INSUFFICIENT')
    write('WALLTIME_DEPENDENCE_ANALYSIS',dict(interpretation=interpretation,per_track_frozen_method_safety=pertrack,
        matched_comparisons=deltas,direction='P minus P-W',selection_changed=False,
        caution='Small walltime gain/paired differences in this restricted TRAIN cohort do not establish walltime unimportance in other populations. No post-hoc feature subsets added.'))
    # S3 raw metrics preserved, with differences measured rather than retuning C.
    c=get('DEV_CAL_RESULTS',True)['body_metrics']+get('EXPOSED_RESULTS',True)['body_metrics'];comparisons=[]
    for a in allbody:
        if a['group']!='OVERALL':continue
        b=next(r for r in c if r['subgroup']=='OVERALL' and r['role']==a['role'] and r['u_hours']==a['u_hours'] and r['candidate']==a['body'])
        comparisons.append(dict(track=a['track'],u_hours=a['u_hours'],body=a['body'],role=a['role'],
             **{k+'_minus_C':a[k]-b[k] for k in ['coverage','GPU_coverage','Q50_MAE_sec','MAE_sec','WAPE','GPU_underprediction_sec']}))
    c_report=get('TRACK_C_REFERENCE');c_report['matched_body_deltas']=comparisons;c_report['comparison_does_not_change_C']=True
    write('TRACK_C_REFERENCE',c_report)
    winner=selection['selected']
    if winner is None:
        classification=selection['classification_before_exposed'];winner_pass=False
    else:
        r=next(r for r in exposed['records'] if all(r[k]==winner[k] for k in ('track','u_hours','body','classifier','policy')))
        winner_pass=r['gates']['PASS']
        classification='V40S4_REQUEST_STATE_PROXY_RUNTIME_PREVALIDATED' if winner_pass else 'V40S4_PROXY_BODY_RUNTIME_INSUFFICIENT' if not r['gates']['body'] else 'V40S4_PROXY_TAIL_DETECTION_FAIL' if not r['gates']['tail'] or not r['gates']['selectivity'] else 'V40S4_PROXY_HYBRID_RUNTIME_SAFETY_FAIL'
    write('FINAL_DECISION',dict(classification=classification,selected=winner,global_selected_exposed_PASS=winner_pass,
          proxy_assumption=ASSUMPTION,historical_D1_snapshot_verified=False,original_submission_verified=False,
          interpretation=interpretation,body_safe_DEV_CAL_pair=selection['body_safe_pair_exists'],valid_primary_eta_count=sum(r['eta'] is not None for r in get('ETA_SELECTION')['rows'] if r['body']!='B0'),
          no_reselection=True,optimizer_integration='NO',production_ready='NO',shadow='SEALED'))
    if not winner_pass:
        write('BOOTSTRAP_STATUS',dict(status='NOT_EXECUTED_SAFETY_FAIL',bootstrap_runs=0,confidence_interval=None))
    else:
        # This branch is preregistered and only reachable after all exposed gates.
        d=p[p.role=='EXPOSED_EVALUATION'].reset_index(drop=True)
        pred=pd.read_parquet(OUT/f"V40S4_PREDICTIONS_{winner['track']}_u{winner['u_hours']}_EXPOSED_EVALUATION.parquet")
        from .experiment import duration
        dur=slots(duration(pred[winner['body']+'_Q90'],pred[winner['classifier']+'_p_tail'].to_numpy()>=winner['eta'],d.reference_safe_sec,d.requested_seconds,winner['u_hours']*3600,winner['policy']))*900
        e=d.num_gpus_req.to_numpy()*(np.maximum(d.runtime_seconds.to_numpy()-slots(d.reference_safe_sec)*900,0)-np.maximum(d.runtime_seconds.to_numpy()-dur,0))
        sums=pd.DataFrame({'day':d.issue_day,'delta':e}).groupby('day').delta.sum().to_numpy()
        rng=np.random.default_rng(SEED);samples=np.array([rng.choice(sums,size=len(sums),replace=True).sum() for _ in range(5000)])
        write('BOOTSTRAP_STATUS',dict(status='EXECUTED_AFTER_ALL_SAFETY_PASS',runs=5000,seed=SEED,delta_GPU_seconds=float(e.sum()),CI95=np.quantile(samples,[.025,.975]).tolist()))
    write('RUNTIME_ADAPTER_PROPOSAL',dict(status='PROPOSAL_ONLY',candidate_fields=list(FIELDS)+['runtime_information_track','request_state_assumption_id'],
       runtime_information_track_values=['STRICT_PROVENANCE','REQUEST_STATE_PROXY'],request_state_assumption_id=ASSUMPTION,
       recommended_rows=[],selected_method=winner,production_integration='NO',
       reason='No safe selected method: no recommendation export' if winner is None or not winner_pass else 'Prevalidated method only; no optimizer integration'))
    ledger=get('COMPUTE_LEDGER');ledger['exposed_inference_times']=exposed['inference_times'];ledger['feature_importance_times']=get('FEATURE_IMPORTANCE_DIAGNOSTIC')['inference_times'];ledger['post_selection_fit_count']=0
    write('COMPUTE_LEDGER',ledger)
    # End protection: no old payload changes, including parent reference worktree.
    start=get('PROTECTED_SCOPE_START');current={r.split('\t')[1]:r.split('\t')[0] for r in git('ls-tree','-r','HEAD').splitlines()}
    assert all(current.get(k)==v for k,v in start['all_existing_Git_entries'].items())
    checked={}
    for path,digest in start['S3_SHA256'].items():
        assert sha((ROOT/path).read_bytes())==digest and sha((S3ROOT/path).read_bytes())==digest,path
        checked[path]=digest
    changed=[p.decode() for p in git('diff','--name-only','-z',BASE,binary=True).split(b'\0') if p]
    assert all(allowed(p) for p in changed)
    write('PROTECTED_SCOPE_END',dict(status='PASS',base=BASE,all_inherited_Git_blobs_verified=len(start['all_existing_Git_entries']),S3_files_byte_verified=len(checked),S3_SHA256=checked,
          original_S3_worktree_unchanged=True,new_fit_after_selection=0))
    write('PROTECTED_SCOPE_DIFF',dict(status='PASS',allowed_changed_paths=changed,changes_outside_allowed=[],
          A0_changes=0,A1_changes=0,M1_changes=0,MF_changes=0,migration_changes=0,WAN_changes=0,terminal_changes=0,event_trigger_changes=0,local_repair_changes=0,rolling_MPC_changes=0,
          RUNNING_redesign=0,optimizer_calls=0,Gurobi_calls=0,OpenDSS_calls=0,Fresh_calls=0,
          protected_future_consumer_files=['dayahead/v37/aidc_materializer.py','dayahead/v40a/initial.py'],holds=HOLDS))
    print('S4_CLOSEOUT',classification,'valid eta',get('FINAL_DECISION')['valid_primary_eta_count'],flush=True)


if __name__=='__main__':main()
