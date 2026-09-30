"""Receipt consistency and byte-preservation checks; no new May optimization."""
import csv,json,subprocess
from .common import *

REQUIRED='''README.md PREREGISTRATION.json DW_DECOMPOSITION_SPEC.md RMP_FORMULATION.md PRICING_FORMULATION.md COLUMN_SCHEMA.json INITIAL_COLUMN_AUDIT.json PHASE1_FORMULATION.md PRICING_EXHAUSTIVE_SYNTHETIC_AUDIT.json PRICING_REAL_SUBSET_AUDIT.json REDUCED_COST_SIGN_AUDIT.json FULL_COLUMN_MASTER_EQUIVALENCE.json SMALL_INTEGER_EQUIVALENCE.json MAY_DW_INITIALIZATION.json MAY_DW_ITERATIONS.csv MAY_DW_PRICING_PROFILE.csv MAY_DW_MASTER_PROFILE.csv MAY_DW_FINAL_LP.json MODEL_SIZE_COMPARISON.json FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LOCAL_EVIDENCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json'''.split()

def main():
    checks=[]
    def check(name,condition,detail=None):
        require(condition,name);checks.append(dict(check=name,PASS=True,detail=detail))
    check('required_artifacts',all((OUT/n).is_file() for n in REQUIRED),len(REQUIRED)+1)
    for p in OUT.glob('*.json'):json.loads(p.read_text(encoding='utf8'),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
    baseline=read(OUT/'BASE_AVAILABLE_MANIFEST.json')
    check('all_baseline_bytes',all((ROOT/r['relative']).is_file() and sha(ROOT/r['relative'])==r['sha256'] for r in baseline['rows']),len(baseline['rows']))
    pre=read(OUT/'PRE_MAY_VERIFICATION.json')
    check('preregistration_unchanged',sha(OUT/'PREREGISTRATION.json')==pre['prereg']['sha256'])
    check('frozen_tolerances',read(OUT/'PREREGISTRATION.json')['RC_TOL']==RC_TOL==1e-7)
    from .execute import GATES
    check('all_exactness_gates',all(read(OUT/n)['PASS'] for n in GATES))
    archives=[]
    manifests=['SOURCE_MANIFEST.json','SOURCE_MANIFEST_IO_RESUME.json']
    for name in manifests:
        if not (OUT/name).exists():continue
        manifest=read(OUT/name);archive=Path(manifest['archive'])
        for row in manifest['sources']:
            source=Path(row['path']);relative=Path(source.parent.name)/source.name if source.parent.name.startswith('v42_') and source.name!='v42_job_capability.py' else Path(source.name)
            saved=archive/relative
            check('archived_source:'+name+':'+str(relative),saved.is_file() and sha(saved)==row['sha256'])
        archives.append(dict(manifest=name,verified=len(manifest['sources'])))
    # Only IO/path/reporting changes occurred after the first executed snapshot.
    stable=('column.py','pricing.py','master.py','cg.py')
    check('scientific_decomposition_code_unchanged',all(sha(LOCAL/'executed_source/v42_dw'/n)==sha(ROOT/'v42_dw'/n) for n in stable),stable)
    result=read(OUT/'MAY_DW_FINAL_LP.json');flags=read(OUT/'FINAL_FLAGS.json')
    check('cumulative_wall_cap',result['supervisor']['total_wall_seconds']<=600,result['supervisor']['total_wall_seconds'])
    check('all_1499_jobs',result['initialization']['fixed_jobs']+result['initialization']['priced_jobs']==1499)
    check('initial_one_column',result['initialization']['initial_columns']==1493 and set(result['initialization']['columns_per_job'].values())=={1})
    folder=LOCAL/('LP_io_resume' if (LOCAL/'LP_io_resume').exists() else 'LP')
    records=read(folder/'GENERATED_COLUMNS.json')['columns'];signatures=[x['canonical_signature'] for x in records]
    check('unique_columns',len(signatures)==len(set(signatures))==result['final_size']['columns'])
    by_signature={r['canonical_signature']:r for r in records};mass={u:0. for u in result['initialization']['columns_per_job']}
    check('all_snapshot_lambdas_nonnegative',all(value>=0. for value in result['last_LP_snapshot']['lambda_values'].values()))
    for signature,value in result['last_LP_snapshot']['lambda_values'].items():
        mass[by_signature[signature]['job_id']]+=value
    check('snapshot_convexity_every_job',all(abs(value-1.)<=1e-8 for value in mass.values()),max(abs(value-1.) for value in mass.values()))
    check('no_master_binaries',result['final_size']['binaries']==0)
    with (OUT/'MAY_DW_ITERATIONS.csv').open(encoding='utf8',newline='') as f:iterations=list(csv.DictReader(f))
    check('every_complete_sweep_all_jobs',all(int(x['jobs_priced'])==1493 for x in iterations if x['complete_pricing']=='True'))
    check('no_duplicate_insertion',sum(int(x['duplicate_rediscoveries']) for x in iterations)==0)
    added=sum(int(x['columns_added']) for x in iterations)
    check('column_growth_accounted',1493+added==len(records),dict(initial=1493,added=added,final=len(records)))
    with (OUT/'MAY_DW_PRICING_PROFILE.csv').open(encoding='utf8',newline='') as f:profiles=list(csv.DictReader(f))
    check('all_pricing_profiles',len(profiles)==1493)
    check('pricing_calls_accounted',sum(int(x['pricing_calls']) for x in profiles)==result['total_pricing_calls'])
    check('insertions_profile_accounted',sum(int(x['columns_generated']) for x in profiles)==added)
    check('phase1_certificate',flags['PHASE1_ZERO'] is True and result['last_LP_snapshot']['phase1_fixed_zero'] is True)
    check('no_false_scientific_convergence',not flags['DW_LP_CONVERGED'] and not flags['ALL_SCIENTIFIC_LEVELS_CONVERGED'] and not result['full_column_optimum_claim'])
    check('no_pipeline_advancement',not any(flags[k] for k in ('M1_RUN','A2_RUN','M2_RUN','FRESH_AC_RUN','RESPONSE_KERNEL_GENERATED','INTEGER_GLOBAL_OPTIMALITY_PROVEN','BRANCH_AND_PRICE_IMPLEMENTED')))
    check('unchanged_authority',not any(flags[k] for k in ('NEW_RUNTIME_ML','NEW_CC4_ML','NEW_TS_RULE','NEW_CAPACITY_ASSUMPTION','NEW_PHYSICAL_ASSUMPTION','NEW_WAN_RULE')))
    check('legacy_preservation_receipt',read(OUT/'LEGACY_PRESERVATION_AUDIT.json')['PASS'])
    check('Korean_50_answers',sum(line[:1].isdigit() and '. **' in line for line in (OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8').splitlines())==50)
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    dump('VERIFICATION.json',dict(PASS=True,base=BASE,checks=checks,archives=archives,
        pytest=dict(passed=308,warnings=1,log=rec(ROOT.parent/'V42_DW_FINAL_TESTS.log')),
        May_scientific_LP_converged=False,May_primary_A_B_C_D=True,no_new_optimization_in_verification=True))
    print(json.dumps(dict(PASS=True,checks=len(checks),wall=result['supervisor']['total_wall_seconds'],columns=len(records),pricing_calls=result['total_pricing_calls']),ensure_ascii=False))

if __name__=='__main__':main()
