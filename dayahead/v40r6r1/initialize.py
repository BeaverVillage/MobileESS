from .common import *
import re

def main():
    assert git('rev-parse','HEAD')==BASE
    assert git('branch','--show-current')=='codex/v40r6r1-risk-calibrated-rolling-gpuwork'
    original=ROOT.parent/'MobileESS_v40r6_multihorizon_cumulative_gpuwork'
    assert git('rev-parse','HEAD',cwd=original)==BASE and git('status','--porcelain',cwd=original)==''
    lineage=[R51SCI,R51REC,SELECTION,SCIENCE,BASE]
    for a,b in zip(lineage,lineage[1:]): git('merge-base','--is-ancestor',a,b)
    assert git('log','-1','--format=%H','--','dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/V40R6_FINAL_COMMIT_RECEIPT.json')==BASE
    receipt=r6('FINAL_COMMIT_RECEIPT'); selection=r6('SELECTION_FREEZE')
    assert receipt['classification']=='V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL'
    assert all(v=='NONE' for v in receipt['selected_candidates'].values())
    assert receipt['optimizer_integration']==receipt['production_ready']=='NO'
    snap=snapshot(); dump('PROTECTED_SCOPE_START',snap)
    dump('START_STATE',{'base':BASE,'branch':git('branch','--show-current'),'worktree':ROOT,'time_UTC':utc(),
        'R6_closed_clean':True,'scope':'Calibration layer only; final experiment under current data/authority'})
    dump('GIT_LINEAGE_AUDIT',{'lineage':lineage,'Git_verified':True,'R6_receipt_resolved_from_file_history':BASE})
    dump('R6_REFERENCE_FREEZE',{'scientific_commit':SCIENCE,'receipt_commit':BASE,'selection_commit':SELECTION,
        'classification':receipt['classification'],'selected_candidates':receipt['selected_candidates'],'selected_config':'L0',
        'optimizer_integration':'NO','production_ready':'NO','R6_BASE_SKILL_LIMITATION':'PRESENT',
        'R6_skill_by_horizon':r6('HYPERPARAMETER_FREEZE')['skill_by_horizon'],
        'R6_static_calibration_deltas':selection['calibration_deltas'],'R6_TRAIN_Q95_anchors':selection['TRAIN_Q95_anchors'],
        'inherited_hash_count':len(snap['inherited_SHA256']),'R6_reclassification':False})
    request=Path('C:/Users/kjw39/.codex/attachments/c5d565a3-0d74-427b-b02b-607576804312/pasted-text.txt')
    body=request.read_text(encoding='utf-8'); section=body.split('# 52. REQUIRED ARTIFACTS')[1].split('# 53. MINIMUM TESTS')[0]
    names=re.findall(r'^V40R6R1_[A-Z0-9_]+\.(?:json|parquet|csv|md)$',section,re.M)
    dump('REQUIREMENTS_MANIFEST',{'request_SHA256':sha(request),'required_artifacts':names,'count':len(names),'minimum_tests':76})
    dump('OPERATING_POINT',{'WORKLOAD_RESERVE_NOMINAL_COVERAGE':.85,'term':'85% WORKLOAD-RESERVE SERVICE LEVEL',
        'interpretation':'Engineering tolerance for exogenous future workload reserve/headroom; electrical feasibility remains separate',
        'grid_security_probability':False,'voltage_reliability_guarantee':False,'feeder_chance_constraint_confidence':False,
        'R6_90pct_result_unchanged':True,'before_candidate_outcome_computation':True,
        'further_experiments':'DEFER_UNTIL_NEW_DATA_OR_AUTHORITY','NO_R6R2':True,'NO_R7':True})
    p=R6/'V40R6_CUMULATIVE_TARGET.parquet'; expected=r6('PREREGISTRATION')['frozen_hashes'][p.relative_to(ROOT).as_posix()]
    if sha(p)!=expected:
        dump('TARGET_IDENTITY_AUDIT',{'classification':'V40R6R1_TARGET_AUTHORITY_MISMATCH','PASS':False})
        raise RuntimeError('V40R6R1_TARGET_AUTHORITY_MISMATCH')
    f=pd.read_parquet(p); a=np.load(R5/'data.npz'); y=a['y'].reshape(349,96); sub=f[f.horizon.isin(HORIZONS)]
    error=np.array([abs(r.target_GPUh-y[r.day_index,r.window_start_slot:r.window_end_slot_exclusive].sum()) for r in sub.itertuples()])
    assert error.max()<1e-7
    dump('TARGET_IDENTITY_AUDIT',{'PASS':True,'exact_R6_target_SHA256':sha(p),'expected_SHA256':expected,
        'native_N':y.size,'native_days':len(y),'native_total_GPUh':y.sum(),'H4_rows':int((sub.horizon=='H4').sum()),
        'H24_rows':int((sub.horizon=='H24').sum()),'identity_max_error_GPUh':error.max(),
        'new_target_construction':0,'target_population_changes':0,'unit':'GPUh','not_GPU_occupancy':True})
    source_names=['development_baselines.npz','fits/L0/development_q.npy','calibration_predictions.npz','exposed_predictions.npz']
    provenance=[]
    for name in source_names:
        p=R6/name; verify_commit_file(BASE,p)
        provenance.append({'file':p.relative_to(ROOT).as_posix(),'SHA256':sha(p),'usage':'READ_FROM_FROZEN_ARRAY'})
    dump('BASE_PREDICTION_IDENTITY',{'sources':provenance,'candidate_mapping':{'R85_B1':'baseline[:,2] frozen B1 Q90',
        'R85_B2':'q[:,1] frozen crossing-repaired B2 L0 Q90'},'deterministic_model_recompute':0,
        'new_LightGBM_fits':0,'new_statistical_model_fits':0,'new_classifier_fits':0,'new_feature_engineering':0,
        'new_target_construction':0,'Q50':'frozen diagnostics only','H1_H8':'frozen read-only R6 diagnostics only'})
    ledger=pd.read_parquet(R5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    oos=ledger[ledger.role.isin(['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION'])&ledger.stage_maturity_eligible]
    dump('LABEL_AVAILABILITY_DISCOVERY',{'OOS_days':len(oos),'days_label_available_after_day_end':int((oos.target_label_available_at>oos.target_end).sum()),
        'examples':oos[['operating_day','target_end','target_label_available_at']].head(8).to_dict('records'),
        'scientific_issue':'GPUh uses eventual runtime; day end alone does not establish real label maturity',
        'candidate_outcomes_computed':False,'resolution':'Pending preregistered rule; user clarification requested'})
    dump('MAY_FIREWALL',{'May_scientific_reads':0,'Apr24_30_shadow_scientific_reads':0,'shadow_status':'SEALED',
        'metadata_path_index_discovery':'NONZERO: request, Git/index and inherited provenance; no scientific May/shadow queries',
        'scientific_input_scope':'Frozen R6 H4/H24 targets and saved DEV/CAL/EXPOSED outputs through February 2025; original maturity metadata',
        'byte_hashing':'Inherited artifacts hashed for preservation; no new raw archive opened or parsed',
        'optimizer_calls':0,'Gurobi_calls':0,'OpenDSS_calls':0,'Fresh_calls':0,'holds':HOLDS})
    print('Initialized exact R6 authority; target identities PASS;',len(names),'required artifacts; no rolling outcomes computed.',flush=True)

if __name__=='__main__': main()
