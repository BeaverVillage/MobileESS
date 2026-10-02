"""Evidence-only review and verification for the single frozen paired experiment."""
import re,subprocess,sys,shutil
from .common import *
from .engine import compare
from .progress import enrich

REQUIRED='PREREGISTRATION SOURCE_FREEZE START_RESIDUAL_ROOT_CAUSE ORIGINAL_RECONSTRUCTION_RECEIPT COMPACT_RECONSTRUCTION_RECEIPT RECONSTRUCTED_START_AUDIT START_ACCEPTANCE_ORIGINAL START_ACCEPTANCE_COMPACT CANARY_ORIGINAL_600S CANARY_COMPACT_600S CANARY_COMPARISON PHYSICAL_IDENTITY_AUDIT SOLVER_PARAMETER_IDENTITY RESOURCE_RECEIPTS INHERITED_CERTIFICATE_PRESERVATION FINAL_FLAGS FINAL_VERDICT VERIFICATION SHA256_MANIFEST'.split()

def review():
    solver_freeze_check();comparison=compare();a=read('CANARY_ORIGINAL_600S.json');b=read('CANARY_COMPACT_600S.json')
    progress={k:enrich(k) for k in ['original','compact']}
    assert read('RECONSTRUCTED_START_AUDIT.json')['PASS']
    for k in ['ORIGINAL','COMPACT']:
        assert read('START_ACCEPTANCE_'+k+'.json')['PASS']
    labels=['START_ACCEPTANCE_ORIGINAL','START_ACCEPTANCE_COMPACT','CANARY_ORIGINAL_600S','CANARY_COMPACT_600S']
    exported={}
    point_names=['ORIGINAL_RECONSTRUCTED_START.npz','COMPACT_RECONSTRUCTED_START.npz']
    point_names+=[n+'_SOLUTION.npz' for n in labels]
    point_names+=[n+'_FIRST_INCUMBENT.npz' for n in labels if n.startswith('CANARY_')]
    for name in point_names:
        shutil.copyfile(LOCAL/name,OUT/name);assert sha(LOCAL/name)==sha(OUT/name)
        exported[name]=sha(OUT/name)
    dump('EVIDENCE_POINT_EXPORT.json',dict(PASS=True,files=exported,byte_identical_to_actual_worker_inputs_and_outputs=True,
        purpose='Reviewable exact reconstructed starts and actual accepted/final incumbent vectors; local solver cache remains unchanged.'))
    policies={n:read(n+'.json')['settings'] for n in labels}
    assert all(all(p[k]==v for k,v in SETTINGS.items()) for p in policies.values())
    dump('SOLVER_PARAMETER_IDENTITY.json',dict(PASS=True,registered=SETTINGS,effective=policies,
        only_TimeLimit_varies_by_preregistered_probe_or_canary=True,FeasibilityTol_not_relaxed=True,
        manual_cuts_tuning=False,presolve_tuning=False,new_root_LP_runs=0,solver_sweeps=0))
    resources={n:read('RESOURCE_'+n+'.json') for n in labels}
    dump('RESOURCE_RECEIPTS.json',dict(PASS=True,receipts=resources,independent_jobs_allowed=True,
        RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,heavy_lane_order=['C0 Original','C1 Compact'],
        lane_concurrent_heavy_solves=False,hardware_same=True,Gurobi_version_same=a['solver_version']==b['solver_version'],
        process_environment_thread_limits_1=True,actual_other_processes_at_snapshots={n:[p for p in r['active_Python_solver_processes'] if p['pid']!=r['worker_pid']] for n,r in resources.items()},
        limitation='Pre-run snapshots disclose observed processes; they do not prove absence of changing independent workloads throughout each solve. No historical absolute speedup claim. Sequential same-lane comparison uses these disclosed conditions.'))
    flags=dict(COMPACT_M1_PRODUCTION_AUTHORIZED=comparison['COMPACT_M1_PRODUCTION_AUTHORIZED'],production_1800_run=False,
        production_1800='NOT_RUN',M1_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False,P2='NOT_RUN',A2='NOT_RUN',M2='NOT_RUN',Actual='NOT_RUN',Fresh_AC='NOT_RUN',
        Benders_master=0,Benders_recourse=0,Farkas_cuts=0,Phase_I=0,new_formulations=0,optimizer_calls_reconstruction=0,
        full_experiment_optimizer_calls=4,scope_note='Two Start probes and one sequential pair only. Inherited tests may exercise bounded toy solvers after the benchmark lane.')
    dump('FINAL_FLAGS.json',flags)
    verdict='MATERIAL_GATE_PASS_PRODUCTION_NOT_RUN' if comparison['material_gate_PASS'] else 'EXACT_START_ACCEPTED_MATERIAL_GATE_FAILED'
    blocker='Frozen Method=1 MIP root LP did not complete within either 600 s canary; branching/proof advantage remains unobserved.' if all(x['root_relaxation_completion_time'] is None for x in [a,b]) else 'Accepted Starts did not achieve the preregistered global-gap or valid-LB improvement gate.'
    dump('FINAL_VERDICT.json',dict(verdict=verdict,Start_reconstruction_PASS=True,Start_acceptance_both_PASS=True,
        paired_canary_PASS=comparison['PASS'],material_gate_PASS=comparison['material_gate_PASS'],next_blocker=blocker,
        flags=flags,no_automatic_next_formulation=True,no_production_run=True))
    (OUT/'NEXT_MODIFICATIONS.md').write_text('# 다음 작업 경계\n\n'+blocker+'\n\n이번 실험은 종료한다. 새 formulation, decomposition, parameter sweep 및 1800초 production은 실행하지 않았다. 다음 실험의 구체적 설계와 승인은 별도 요청이 필요하다. 기존 LB와 UB 및 PR124의 실패 증거를 보존한다.\n',encoding='utf8')
    from .review_ko import write_review
    write_review(comparison,a,b,blocker,flags)
    return comparison

def verify():
    solver_freeze_check();count=preserve();output=(OUT/'TEST_OUTPUT.txt').read_text(encoding='utf8')
    matches=re.findall(r'(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) warnings?)? in ([\d.]+)s',output)
    assert len(matches)==1 and ' failed' not in output and ' error' not in output
    passed,skipped,warnings,seconds=matches[0]
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    assert git('merge-base',BASE,'HEAD')==BASE
    for name in REQUIRED:
        if name not in ['VERIFICATION','SHA256_MANIFEST']:assert (OUT/(name+'.json')).is_file(),name
    assert (OUT/'START_VARIABLE_CLASSIFICATION.csv').is_file()
    classification_counts={'original':0,'compact':0};aux_counts={'original':0,'compact':0}
    with (OUT/'START_VARIABLE_CLASSIFICATION.csv').open(encoding='utf8',newline='') as f:
        reader=csv.DictReader(f)
        assert set(['formulation','variable_name','index','family','classification','source_function','reconstruction_rule','scientific_value_fixed'])<=set(reader.fieldnames)
        for row in reader:
            kind=row['formulation'];assert int(row['index'])==classification_counts[kind]
            assert family(row['variable_name'])==row['family']
            expected='IMMUTABLE_PRIMARY' if row['family'] in PRIMARY else 'RECOMPUTABLE_AUXILIARY'
            assert row['classification']==expected and row['family'] in PRIMARY|AUX
            classification_counts[kind]+=1;aux_counts[kind]+=row['classification']=='RECOMPUTABLE_AUXILIARY'
    assert classification_counts=={'original':316743,'compact':316839} and all(n==81216 for n in aux_counts.values())
    source_replay=read('START_SOURCE_MATRIX_REPLAY.json');assert source_replay['PASS'] and source_replay['optimizer_calls']==0
    assert all(row['source_replay_coefficient_max_abs_difference']==row['source_replay_RHS_abs_difference']==0 for row in source_replay['rows'])
    flags=read('FINAL_FLAGS.json');assert not flags['production_1800_run'] and not flags['M1_ACCEPTED'] and not flags['PROBLEM13_FINAL_VALIDATED']
    assert all(flags[k]=='NOT_RUN' for k in ['P2','A2','M2','Actual','Fresh_AC'])
    for path in OUT.glob('*.json'):json.loads(path.read_text(encoding='utf8'))
    dump('VERIFICATION.json',dict(PASS=True,base=BASE,recorded_before_final_commit=git('rev-parse','HEAD'),utc=stamp(),
        tests_passed=int(passed),tests_skipped=int(skipped or 0),warnings=int(warnings or 0),test_seconds=float(seconds),
        test_output_sha256=sha(OUT/'TEST_OUTPUT.txt'),full_inherited_pytest_command='python -m pytest -q',
        inherited_physical_files_preserved=count,scientific_source_matrix_cache_and_solver_freeze_PASS=True,
        classification_counts=classification_counts,auxiliary_counts=aux_counts,source_matrix_replay_bit_exact_PASS=True,
        git_diff_check_PASS=True,required_artifacts_PASS=True,all_JSON_parse_PASS=True,
        optimizer_counter_scope='Full benchmark experiment 4 calls; auxiliary reconstruction 0 calls. Bounded inherited test optimizers excluded.',
        M1_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False,production_1800_NOT_RUN=True))

def staged_audit(write=True):
    changed=git('diff','--cached','--name-only',BASE).splitlines()
    basefiles={r['path'] for r in read('PR124_BASE_RECEIPT.json')['files']}
    assert not set(changed)&basefiles,'INHERITED_STAGED_BLOB_CHANGED'
    assert all(p.startswith(('v42_exact_start/','docs/v42_m1_compact_exact_start/')) or p=='tests/test_v42_exact_start.py' for p in changed)
    for name in changed:
        staged=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
        assert staged==(ROOT/name).read_bytes(),('STAGED_BYTES_DIFFER',name)
    subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,check=True)
    result=dict(PASS=True,utc=stamp(),base=BASE,inherited_physical_files_preserved=preserve(),
        inherited_Git_blobs_unchanged=True,new_staged_files=len(changed),new_staged_files_physically_identical=True,
        stage_scope=changed,note='Receipt is generated before staging itself and final manifest; complete staged-byte check is repeated after staging both without mutating any evidence.')
    if write:dump('STAGED_BYTES_AUDIT.json',result)
    return result

def manifest():
    paths=[p for p in OUT.iterdir() if p.is_file() and p.name!='SHA256_MANIFEST.json']
    paths+=list((ROOT/'v42_exact_start').glob('*.py'))+[ROOT/'v42_exact_start/.gitattributes',ROOT/'tests/test_v42_exact_start.py']
    dump('SHA256_MANIFEST.json',dict(utc=stamp(),files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)},
        exclusion='Only this manifest excludes itself; verification and staged audit are included.',solver_inputs='SOURCE_FREEZE.json contains sealed inputs and original solver source hashes.'))

if __name__=='__main__':
    {'review':review,'verify':verify,'staged':staged_audit,'manifest':manifest,'check_staged':lambda:staged_audit(False)}[sys.argv[1]]()
