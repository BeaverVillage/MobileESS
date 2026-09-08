from .common import *
import shutil,re
def main():
    assert git('rev-parse','HEAD')==BASE
    assert git('status','--porcelain',cwd=R4)==''
    assert git('merge-base','--is-ancestor','a925a34848458b07b2a07a43b1150c89c21425b9',BASE)==''
    assert all(allowed(p) for p in git('status','--porcelain').splitlines() for p in [p[3:]])
    receipt=external(R4OUT/'V40R4_FINAL_COMMIT_RECEIPT.json')
    assert receipt['classification']=='V40R4_COMPOUND_GPUWORK_SAFETY_FAIL'
    files=[]
    for x in external(R4OUT/'V40R4_V40R3_FREEZE_VERIFICATION.json')['files']:
        p=R3/x['path'];h=sha(p);assert h==x['SHA256_working'];files.append({'root':'R3','path':x['path'],'SHA256':h})
    for directory in [R4/'dayahead/v40r4',R4OUT]:
        for p in sorted(directory.rglob('*')):
            if p.is_file():files.append({'root':'R4','path':p.relative_to(R4).as_posix(),'SHA256':sha(p)})
    worktrees={}
    for p in [R3,R4,ROOT.parent/'MobileESS_v40r2_cabo_future_workload_ml',ROOT.parent/'MobileESS_v40s2_survival_occupancy_ml',ROOT.parent/'MobileESS_v40a_bounded_iterative_coopt']:
        worktrees[str(p)]={'HEAD':git('rev-parse','HEAD',cwd=p),'status':git('status','--porcelain',cwd=p)}
    dump('V40R5_PROTECTED_SCOPE_START.json',{'files':files,'R3_count':sum(x['root']=='R3' for x in files),'R4_count':sum(x['root']=='R4' for x in files),'worktrees':worktrees})
    dump('V40R5_START_STATE.json',{'BASE':BASE,'branch':git('branch','--show-current'),'worktree':ROOT,'time_UTC':datetime.now(timezone.utc),
      'initial_worktree_clean_before_R5_files':True,'parent_worktree_clean':True,'checkout':'Index seeded from exact full BASE; inherited paths skip-worktree; no inherited scientific payload checkout',
      'R2_status':'SUPERSEDED_BY_V40R3','R3_status':'V40R3_FUTURE_GPUWORK_SAFETY_FAIL','R4_status':'V40R4_COMPOUND_GPUWORK_SAFETY_FAIL'})
    dump('V40R5_GIT_AUTHORITY_AUDIT.json',{'BASE':BASE,'R4_receipt':receipt,'ancestry_PASS':True,'PR27':{'HEAD':PR_HEAD,'state':'OPEN','url':'https://github.com/BeaverVillage/MobileESS/pull/27','scope':'metadata only; no merge/modification'},'protected_namespace_change_count':0})
    dump('V40R5_PARENT_R4_FREEZE.json',{'classification':receipt['classification'],'selected_model':None,'CCAF':'FAIL','superiority':False,'EVT_supported':False,'untouched':False,'retune_refit_reopen':False,
      'design_evidence':{'R3_January_miss_types':{'COUNT':8,'SEVERITY':2,'MIXED':1,'UNRESOLVED':1},'R4_large_count_recall':0,'R4_tail_predicted':.05012564116050946,'R4_tail_observed':.20352167799228335,'R4_top1_Q90_coverage':0,'R4_burst_coverage':'0/240'}})
    inputs={}
    for name in ['GPU_related_candidates_preMay.parquet','causal_dataset.npz','arrival_bins_with_maturity.parquet','V40R3_LABEL_MATURITY_LEDGER.parquet','feature_available_at_proofs.parquet']:
        source=R4OUT/'inputs'/name;dest=OUT/'inputs'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(source,dest)
        assert sha(source)==sha(dest);inputs[name]={'source':source,'SHA256':sha(dest)}
    dump('V40R5_INPUT_PROVENANCE.json',inputs)
    text=Path('C:/Users/kjw39/.codex/attachments/7c1d4cd9-e335-4796-b7b9-0db750207bd1/pasted-text.txt').read_text(encoding='utf-8')
    section=text.split('# 38. REQUIRED ARTIFACTS')[1].split('# 39. MINIMUM TESTS')[0]
    names=re.findall(r'^V40R5_[A-Z0-9_]+\.(?:json|parquet|csv|md)$',section,re.M)
    dump('V40R5_REQUIREMENTS_MANIFEST.json',{'request_SHA256':hashlib.sha256(text.encode()).hexdigest(),'required_artifacts':names,'required_count':len(names),'minimum_tests':75})
    source=git('show',PR_HEAD+':dayahead/input_contract.py')
    snippet=source[source.index('def pwc_30_to_15'):source.index('def average_5_to_15')]
    dump('V40R5_CURRENT_TIME_AXIS_AUTHORITY.json',{'PR_HEAD':PR_HEAD,'source':'dayahead/input_contract.py','source_SHA256':hashlib.sha256(source.encode()).hexdigest(),
      'SLOT_MINUTES':15,'SLOT_HOURS':.25,'SLOTS_PER_DAY':96,'fixed_AEST_UTC_offset_hours':10,'AEMO_function':snippet,'optimizer_imports_or_calls':0})
    dump('V40R5_PHASE0_PLAN.json',{'before_forecast_fit':True,'diagnostic_scope':'Mature TRAIN only; exact target identity checks necessarily cover already exposed parent dates',
      'burst_rule':'Strict > TRAIN positive DeltaW15 Q95','count_high_rule':'Strict > TRAIN positive N15 Q95','EVT_fit':False,
      'timestamp_unit':'ns UTC','bin_convention':'[start,end)','target_tolerance_GPUh':1e-7,'forecast_fit_before_preregistration':False})
    print('Initial hashes, exact lineage, parent freeze, input provenance and Phase-0 rules recorded.',len(files),'protected files;',len(names),'required artifacts.')
if __name__=='__main__':main()
