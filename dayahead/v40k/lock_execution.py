"""Bind baseline and central model branches only after both have completed."""
from .common import *
def main():
    require_prereg()
    assert not (OUT/'POINT_SELECTION_ROWS.parquet').exists()
    b=read('V40K_BASELINE_REPRODUCTION.json');assert b['status']=='PASS' and b['same_seed_independent_refit']
    eq=read('V40K_FEATURE_TARGET_EQUIVALENCE.json');assert eq['status']=='PASS' and eq.get('entire_exposed_GPU_population')
    central=read('V40K_PREHOLDOUT_MODEL_LOCK.json')
    all_models={p.name:sha(p) for p in (OUT/'models').glob('*.pkl')}
    assert len(all_models)==19 and 'K0_FINAL.pkl' in all_models
    for n,h in central['models_SHA'].items():assert all_models[n]==h
    write('V40K_PREHOLDOUT_EXECUTION_FREEZE.json',{'created_at':now(),'preregistration_commit':require_prereg(),
      'models_SHA':all_models,'source_SHA':{p.name:sha(p) for p in (ROOT/'dayahead/v40k').glob('*.py') if p.name not in ['closeout.py','lock_execution.py']},
      'weights_SHA':sha(OUT/'V40K_STACKING_WEIGHTS.json'),'unavailable':central['unavailable'],
      'CPU_only':True,'GPU_scientific_fit_count':0,'candidate_registry_changed':False,
      'baseline_model_SHA':b['final_model_SHA'],'normalization_equivalence_SHA':sha(OUT/'V40K_FEATURE_TARGET_EQUIVALENCE.json'),
      'point_holdout_opened':False,'shadow_opened':False,
      'changes_since_preregistration':['Pinned memory-parser equivalence repair before April extraction','Resume verified CPU fits after user GPU instruction was cancelled; backend unchanged','Supplemental joint baseline/central execution freeze after parallel branches complete; no metric/gate change']},immutable=True)
    event('all_execution_locked_before_new_holdout',models=len(all_models))
    print('PREHOLDOUT_EXECUTION_FREEZE_READY_TO_COMMIT',flush=True)
if __name__=='__main__':main()
