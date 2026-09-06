"""Post-fit reporting audit only. Never fits, selects, or changes frozen science.

Run after evaluate and the independent repetitions. Frozen train.py is preserved.
Correct its np.array_equal byte-identity label using actual dtype/bytes/hashes.
"""
import os
from datetime import datetime
from .common import *
from .train import load,ALL_NAMES,TREE_NAMES,DEEP_NAMES,monotone_nonnegative
from .metrics import summarize,calibrate,gates
from .evaluate import REPORT_NAMES

def main():
    os.environ['GIT_OPTIONAL_LOCKS']='0'
    reg,commit,a,info,m=load()
    y=np.load(OUT/'causal_dataset.npz')['target'];threshold=reg['burst']['training_positive_Q95_GPUh']
    dates=info.operating_day.to_numpy();test=m['EXPOSED_EVALUATION'];cal=m['CALIBRATION'];dev=m['DEVELOPMENT']
    original_fit_hashes={str(p.relative_to(OUT)):sha(p) for p in (OUT/'fits').rglob('*') if p.is_file()}
    prior_corrections=OUT/'V40R3_REPORTING_CORRECTIONS.json'
    corrections=read(prior_corrections.name) if prior_corrections.exists() else {'scope':'Reporting semantics only; no frozen source, data, predictions, fitting, thresholds, or selection decisions changed','changes':[]}
    repfiles=['V40R3_TREE_REPRODUCTION_REPORT.json','V40R3_DEEP_REPRODUCTION_REPORT.json']
    reports={};ledger=[]
    for filename in repfiles:
        prior=read(filename);before_sha=sha(OUT/filename);changed=False
        for entry in prior['models']:
            name=entry['name'];directory=OUT/'fits'/name
            original=np.load(directory/'raw_prediction.npy');repeat=np.load(directory/'repeat_prediction.npy')
            assert original.shape==repeat.shape and np.isfinite(original).all() and np.isfinite(repeat).all()
            exact=bool(np.array_equal(original,repeat));samebytes=bool(original.dtype==repeat.dtype and original.tobytes()==repeat.tobytes())
            samefile=sha(directory/'raw_prediction.npy')==sha(directory/'repeat_prediction.npy')
            if 'original_array_equal_flag' not in entry:
                entry['original_array_equal_flag']=entry['byte_identical_prediction_arrays'];changed=True
            entry.update(exact_prediction_values=exact,byte_identical_prediction_arrays=samebytes,
                         serialized_prediction_files_identical=samefile,
                         semantic_correction='np.array_equal compares values, not dtype or serialized bytes; this audit measures both separately')
            base,_=monotone_nonnegative(original);rep,_=monotone_nonnegative(repeat)
            base_delta,bc=calibrate(y[cal],base[cal],threshold);rep_delta,rc=calibrate(y[cal],rep[cal],threshold)
            cb=base.copy();cr=rep.copy();cb[...,1]+=base_delta;cr[...,1]+=rep_delta
            rawb=summarize(y[test],base[test],threshold);rawr=summarize(y[test],rep[test],threshold)
            sb=summarize(y[test],cb[test],threshold);sr=summarize(y[test],cr[test],threshold)
            fit=read(f'fits/{name}/result.json');first=fit['selected_trial']
            if name in TREE_NAMES:
                second={'seed':SEED,'device':'cpu','learning_rate':first['learning_rate'],
                        'n_estimators':400,'training_walltime_seconds':entry['repeat_walltime_seconds']}
            else:second=read(f'fits/{name}/'+('repeat_selected_result.json' if name in DEEP_NAMES else 'repeat_ablation_result.json'))
            reports[name]={
                **entry,'original_dtype':str(original.dtype),'repeat_dtype':str(repeat.dtype),'shape':original.shape,
                'raw_prediction_SHA256':sha(directory/'raw_prediction.npy'),'repeat_prediction_SHA256':sha(directory/'repeat_prediction.npy'),
                'max_prediction_difference_GPUh':float(np.abs(original-repeat).max()),
                'mean_prediction_difference_GPUh':float(np.abs(original-repeat).mean()),
                'evaluation_calibrated_max_difference_GPUh':float(np.abs(cb[test]-cr[test]).max()),
                'evaluation_calibrated_mean_difference_GPUh':float(np.abs(cb[test]-cr[test]).mean()),
                'original_evaluation_raw_primary':rawb['probabilistic']['primary_positive_Q90_normalized_pinball'],
                'repeat_evaluation_raw_primary':rawr['probabilistic']['primary_positive_Q90_normalized_pinball'],
                'original_evaluation_calibrated_primary':sb['probabilistic']['primary_positive_Q90_normalized_pinball'],
                'repeat_evaluation_calibrated_primary':sr['probabilistic']['primary_positive_Q90_normalized_pinball'],
                'evaluation_calibrated_primary_difference':sr['probabilistic']['primary_positive_Q90_normalized_pinball']-sb['probabilistic']['primary_positive_Q90_normalized_pinball'],
                'calibration_original':bc,'calibration_repeat':rc,
                'original_evaluation_metrics':sb,'repeat_evaluation_metrics':sr,
                'original_safety':gates(y[test],cb[test],threshold,dates[test]),
                'repeat_safety':gates(y[test],cr[test],threshold,dates[test]),
                'original_training':{k:v for k,v in first.items() if k!='history'},
                'repeat_training':{k:v for k,v in second.items() if k!='history'},
                'repetition_use':'Audit only; original selected training run retained regardless of repeat score; same fixed calibration algorithm applied independently'}
            for trial in fit.get('trials',[first]):
                ledger.append({'model':name,'role':'primary_search' if name in ALL_NAMES else 'secondary_ablation',
                  **{k:v for k,v in trial.items() if k!='history'}})
            ledger.append({'model':name,'role':'independent_reproduction',**{k:v for k,v in second.items() if k!='history'}})
        dump(filename,prior)
        if changed:corrections['changes'].append({'artifact':filename,'original_SHA256':before_sha,
            'correction':'Original np.array_equal boolean preserved as original_array_equal_flag. Byte identity now requires equal dtype and bytes; file hash identity separate.'})
    dump('V40R3_DETERMINISM_REPORT.json',{'models':reports,'seed':SEED,'compute_environment':read('V40R3_COMPUTE_ENVIRONMENT.json'),
        'same_fixed_seed_reproductions':2,'independent_seed_diversity_claimed':False,
        'GPU_warning':'upsample_linear1d_backward_out_cuda has no deterministic implementation in this runtime; warn_only=True was registered before fitting',
        'interpretation':'NHiTS prediction variation is observed; zero measured differences for other families do not establish universal bitwise determinism',
        'mixed_precision':False,'no_repeat_selected_for_better_score':True,'no_post_evaluation_retuning':True})
    dump('V40R3_TRAINING_RUN_LEDGER.json',{'runs':ledger,'training_configuration_runs':len(ledger),
        'training_walltime_sum_seconds':sum(r['training_walltime_seconds'] for r in ledger),
        'walltime_scope':'Per-run timer includes training, development scoring, final inference and checkpoint writes; overlapping runs are not elapsed experiment walltime',
        'preregistration_commit':commit,'framework_versions':read('V40R3_COMPUTE_ENVIRONMENT.json')['frameworks'],
        'tree_training':reg['tree_training'],'deep_training':reg['deep_training'],
        'zero_and_seasonal_parameter_fits':0,'same_primary_trial_budget':2,'all_training_complete':True})
    monthly={}
    for name in ALL_NAMES:
        pred=np.load(OUT/'fits'/name/'calibrated_prediction.npy')
        monthly[name]={}
        for month in sorted(set(d[:7] for d in dates[test])):
            mask=test & np.array([d[:7]==month for d in dates])
            monthly[name][month]=summarize(y[mask],pred[mask],threshold)
    dump('V40R3_MONTHLY_METRICS.json',{'scope':'Frozen original runs; calibrated exposed evaluation; no retuning','models':monthly})
    selection=read('V40R3_METHOD_SELECTION.json')
    if 'CMABF_pairwise_superiority_vs_frozen_development_baseline' not in selection:
        before=sha(OUT/'V40R3_METHOD_SELECTION.json')
        selection['CMABF_pairwise_superiority_vs_frozen_development_baseline']=selection['CMABF_superiority_established']
        selection['CMABF_superiority_established']=bool(selection['CMABF_paper_model_eligible'])
        selection['superiority_scope_clarification']='Global paper-model superiority requires safety and every-baseline numeric superiority as well as the pairwise CI. Pairwise statistical superiority alone is reported separately.'
        dump('V40R3_METHOD_SELECTION.json',selection)
        corrections['changes'].append({'artifact':'V40R3_METHOD_SELECTION.json','original_SHA256':before,
            'correction':'Disambiguate pairwise vs frozen-development-baseline evidence from overall CMABF paper-model eligibility; classification and selected_model unchanged'})
    dump('V40R3_REPORTING_CORRECTIONS.json',corrections)
    receipt=read('V40R3_RAW_INGESTION_RECEIPT.json')
    assert receipt['May_scientific_rows']==0
    dump('V40R3_MAY_FIREWALL.json',{'scope':'V40R3 task; embargo is May 2025, not May 2024','May_scientific_rows':0,
      'May_target_reads':0,'May_runtime_status_reads':0,'May_actual_reads':0,'May_training_rows':0,'May_calibration_rows':0,
      'May_model_selection_rows':0,'May_B0_B3_outcome_reads':0,'final_status_columns_read':False,
      'code_path_footer_metadata_reads':'NONZERO','metadata_categories':['User supplied May constraints','ZIP member names and parquet row-group footer bounds','allowlisted code/config path and contract metadata','protected git HEAD/status metadata','V40P byte-hash checks without payload decoding'],
      'raw_read_boundary':'Only selected 202402..202502 row groups with submit/start/end maxima strictly before 2025-05-01 decoded; mixed row groups skipped before payload read',
      'safe_decoded_row_groups':len(receipt['safe_row_groups']),
      'complete_submission_coverage_before_UTC':receipt['complete_submission_coverage_before_UTC'],
      'raw_receipt_SHA256':sha(OUT/'V40R3_RAW_INGESTION_RECEIPT.json'),
      'inherited_incidents':'V40P broad-source May exposure remains acknowledged in inherited context; earlier V40R2 checkout/source incident remains part of that superseded experiment. V40R3 makes no clean-room or zero-metadata claim.',
      'preMay_contract_exposure':'Hierarchical slow-layer contract included January development runtime commentary; historical evaluation is exposed, not untouched confirmation',
      'audit_limit':'Derived from executed read scope and ingestion logs; not an OS-wide filesystem access monitor'})
    start=read('V40R3_START_STATE.json');end={}
    for path,old in start['protected_worktree_start'].items():
        current={'HEAD':git('rev-parse','HEAD',cwd=path),'status':git('status','--porcelain',cwd=path)}
        current['HEAD_and_status_unchanged']=all(current[k]==old[k] for k in ['HEAD','status']);end[path]=current
    r2=next(v for p,v in end.items() if 'v40r2_' in p)
    assert r2['HEAD_and_status_unchanged'],'V40R2 metadata differs: investigate without writing'
    tracked=git('diff','--name-only',START).splitlines();untracked=git('ls-files','--others','--exclude-standard').splitlines()
    allowed=('dayahead/v40r3/','dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml/')
    illegal=[p for p in tracked+untracked if not p.startswith(allowed)];assert not illegal
    dump('V40R3_PROTECTED_SCOPE_DIFF.json',{'start':START,'preregistration_commit':commit,
      'authorized_paths':allowed,'changed_tracked_paths':tracked,'untracked_paths_at_audit':untracked,'changes_outside_scope':illegal,
      'protected_worktree_end':end,'protected_worktree_start_artifact':'V40R3_START_STATE.json',
      'V40R2_scientific_status':'SUPERSEDED_BY_V40R3','V40R2_resumed':False,'V40R2_model_fits':0,'V40R2_code_reused_or_merged':False,
      'V40R2_files_written_or_deleted':0,'V40R2_preservation_evidence':'No R3 write operations targeted R2; HEAD/status unchanged. No byte-for-byte claim for preexisting untracked R2 files because no initial per-file byte inventory was taken.',
      'parallel_worktree_note':'HEAD/status differences outside this worktree are disclosed; this branch changes only the two R3 namespaces',
      'V40P_reference_hash_check_count':len(read('V40R3_V40P_REFERENCE_FREEZE.json')['checks']),
      'protected_diff_read_scope':'Names/HEAD/status only; no protected outcome payloads read','holds':reg['holds']})
    assert all(sha(OUT/p)==h for p,h in original_fit_hashes.items())
    dump('V40R3_POSTFIT_INTEGRITY.json',{'frozen_source_and_data_hashes_pass':True,'preregistration_commit':commit,
      'fit_artifacts_SHA256':original_fit_hashes,'fit_artifacts_unchanged_by_final_audit':True,
      'audit_only_no_fitting':True,'time_UTC':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'classification':selection['classification'],'selected_model':selection['selected_model'],
       'R2_metadata_unchanged':r2['HEAD_and_status_unchanged'],'training_configuration_runs':len(ledger),
       'repeat_differences':{n:{k:r[k] for k in ['max_prediction_difference_GPUh','mean_prediction_difference_GPUh','evaluation_calibrated_primary_difference','byte_identical_prediction_arrays']} for n,r in reports.items()},
       'CMABF_January':monthly['CMABF']['2025-01']['probabilistic']['burst']},indent=2))

if __name__=='__main__':main()
