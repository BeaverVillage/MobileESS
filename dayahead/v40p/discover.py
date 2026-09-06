from .common import *
import shutil

def main():
    assert git('rev-parse','HEAD')==START
    dump('V40P_START_STATE.json',{'starting_commit':START,'branch':git('branch','--show-current'),'worktree':ROOT,'separate_worktree':True,'initial_status':git('status','--short'),'sparse_excludes':['all artifact/data/output directories unless explicitly restored','V40N'],'protected_science':['V40I','V40J','V40K','V40L','V40M','V40N','K0','T7'],'integrity_holds':{'PF':.95,'Q_control':'NO','31_DAY_ELECTRICAL_REGENERATION':'HOLD','B0/B1/B2/B3':'NO','FULL_MAY':'NO'}})
    snapshots=[]
    for package in ['kestrel_stage_k5a_ml_dataset_modular_v101','kestrel_stage_k5b2_zero_inflated_modular_v101','kestrel_stage_k35_modular_v102','kestrel_stage_k5c2_final_dc_inputs_modular_v103','kestrel_stage_k5c3_optimization_ready_modular_v104']:
        base=TOOLS/package
        for p in sorted((base/'src').rglob('*.py')):
            dest=OUT/'source_snapshots'/package/p.relative_to(base)
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
            snapshots.append({'source':p,'snapshot':dest.relative_to(ROOT),'sha256':digest(dest)})
            record_access(p,'SOURCE_CODE_SNAPSHOT')
    tree=git('ls-tree','-r','--name-only',START).splitlines()
    for name in tree:
        allowed=(name.startswith('dayahead/artifacts/v28_final_dayahead_actual/V28_FINAL_LIGHTGBM') or name.startswith('dayahead/artifacts/v28r2_heavy_backend/V28R2_OPTIMIZER_CHANNEL') or name.startswith('dayahead/artifacts/v28r2_heavy_backend/V28R2_FINAL_') and 'LIGHTGBM' in name or name.endswith('/AIDC_COHORT_CONTRACT.json') or name.endswith('/V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY.json'))
        if allowed:
            raw=subprocess.check_output(['git','show',START+':'+name],cwd=ROOT)
            dest=ROOT/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            record_access(name,'EXACT_START_COMMIT_ARTIFACT')
    dump('source_snapshots.json',snapshots)
    files=[K5A/'outputs/kestrel_ml_development_2024.parquet',K5A/'outputs/kestrel_ml_test_2025.parquet',K5A/'outputs/kestrel_workload_global_5min.parquet',K5B2/'predictions/test_2025_frozen_k5b2.parquet',K5B2/'predictions/validation_oof_k5b2.parquet']
    info=[footer(p) for p in files if p.exists()]
    dump('parquet_footer_census.json',info)
    print(json.dumps([{k:v for k,v in f.items() if k!='columns'} for f in info],indent=2))
    print('snapshots',len(snapshots))

if __name__=='__main__':main()
