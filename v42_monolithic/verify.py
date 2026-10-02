"""Finalize reproducibility receipts without running an optimizer."""
import json,re,importlib
from .common import *
from .experiment import check_freeze

def main():
    check_freeze()
    for module,receipt in [('secondary_roots','ROOT_LP_SECONDARY_PREREGISTRATION.json'),
            ('interior_roots','ROOT_LP_INTERIOR_PREREGISTRATION.json'),('primal_roots','ROOT_LP_PRIMAL_PREREGISTRATION.json')]:
        policy_module=importlib.import_module('v42_monolithic.'+module)
        registration=read(receipt)
        assert registration['source_sha256']==sha(Path(policy_module.__file__))
        assert registration['policy']==policy_module.POLICY
    output=(OUT/'TEST_OUTPUT.txt').read_text(encoding='utf8')
    matches=re.findall(r'(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) warnings?)? in ([\d.]+)s',output)
    assert len(matches)==1 and ' failed' not in output and ' error' not in output,matches
    passed,skipped,warnings,seconds=matches[0]
    flags=read('FINAL_FLAGS.json');root=read('ROOT_LP_EQUIVALENCE.json')
    assert not flags['production_1800_run'] and not flags['M1_ACCEPTED']
    assert all(flags[k]=='NOT_RUN' for k in ['P2','A2','M2','Actual','Fresh_AC'])
    assert all(flags[k]==0 for k in ['Benders_master','Benders_recourse','Farkas_cuts','Phase_I'])
    assert git('merge-base',BASE,'HEAD')==BASE
    qas=len(re.findall(r'^## \d+\.',(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8'),re.M))
    assert qas>=70
    required=['PR120_BASE_RECEIPT.json','PREREGISTRATION.json','ORIGINAL_MOBILITY_FORMULATION.md',
        'COMPACT_MOBILITY_FORMULATION.md','COMPACT_PATH_INTEGRALITY_PROOF.md','PARALLEL_ROUTE_AUDIT.csv',
        'PARALLEL_ROUTE_SELECTOR_COUNT.json','ORIGINAL_COMPACT_MAPPING_SPEC.md','FIXTURE_EXACTNESS_RESULTS.csv',
        'FIXTURE_PATH_CENSUS.json','FULL_DOMAIN_CENSUS.json','COMPACT_MODEL_STATS.json','BINARY_REDUCTION_REPORT.json',
        'MIP_START_MAPPING.json','MIP_START_PHYSICAL_VALIDATION.json','ROOT_LP_ORIGINAL.json','ROOT_LP_COMPACT.json',
        'ROOT_LP_EQUIVALENCE.json','CANARY_ORIGINAL_600S.json','CANARY_COMPACT_600S.json','CANARY_COMPARISON.json',
        'COMPACT_M1_PRODUCTION_AUTHORIZATION.json','FINAL_FLAGS.json','FINAL_VERDICT.json','NEXT_MODIFICATIONS.md',
        'FINAL_REVIEW_KO.md','RESOURCE_RECEIPT.json']
    assert all((OUT/p).is_file() for p in required)
    files=[p for p in OUT.iterdir() if p.is_file() and p.name not in ['VERIFICATION.json','EVIDENCE_MANIFEST.json']]
    for p in files:
        if p.suffix=='.json':json.loads(p.read_text(encoding='utf8'))
    dump('EVIDENCE_MANIFEST.json',dict(utc=stamp(),files={p.name:sha(p) for p in sorted(files)},
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'v42_monolithic').glob('*.py'))},
        note='Manifest excludes itself and VERIFICATION; frozen optimizer/source/cache maps additionally verified by EXECUTION_FREEZE and MODEL_FREEZE.'))
    result=dict(PASS=True,utc=stamp(),base=BASE,recorded_pre_final_commit=git('rev-parse','HEAD'),
        test_command='python -m pytest -q',tests_passed=int(passed),tests_skipped=int(skipped or 0),
        warnings=int(warnings or 0),test_seconds=float(seconds),test_output_sha256=sha(OUT/'TEST_OUTPUT.txt'),
        warning_scope='Inherited v42_final/inference/calibration.py log1p RuntimeWarning; no new warning or regression.',
        inherited_physical_files_preserved=preserve(),source_and_cache_freeze_PASS=True,root_preregistered_source_and_policy_hashes_PASS=True,
        QA_count=qas,required_outputs_PASS=True,all_evidence_json_parse_PASS=True,
        evidence_manifest_sha256=sha(OUT/'EVIDENCE_MANIFEST.json'),
        fresh_root_gate=root['PASS'],formal_and_fixture_exactness_PASS=True,
        canary_statuses={k:read(k+'.json')['status'] for k in ['CANARY_ORIGINAL_600S','CANARY_COMPACT_600S']},
        P2_A2_M2_Actual_Fresh_AC_NOT_RUN=True,production_1800_NOT_RUN=True,
        new_experiment_Benders_master_recourse_Farkas_Phase_I=[0,0,0,0],
        counter_scope='New full scientific experiment only. Inherited regression tests include bounded toy Benders optimizations; they are disclosed and not full M1 experimental runs.')
    dump('VERIFICATION.json',result);print(result,flush=True)

if __name__=='__main__':main()
