"""Reconcile measured optimization/replay evidence before official approval."""
from pathlib import Path
import subprocess,json,time,traceback
from .stage_common import ROOT,OUT,read,record,put,day_inputs,SOURCE
from .stage_campaign import source_files
from .stage_budget import policy
from .stage_pause import verify as verify_pause

REPLAY_NAMES=(
 'M1_STATIC_NATIVE0_AFTER_20261023.json','M2_STATIC_NATIVE0_AFTER_20261023.json',
 'JOINT_NATIVE0_AFTER_20261023.json','M1_ORIGINAL_FULL_VALIDATOR_BINDING.json',
 'M2_ORIGINAL_FULL_VALIDATOR_BINDING.json','PRODUCTION_M1_CURRENT_CASE_NATIVE0.json',
 'A2_ORIGINAL_P1_FULL_PREPARATION.json','A_PRODUCTION_ENTRY_BINDING.json',
 'K48_ACTUAL_NATIVE0_READBACK.json','ACTUAL_SOURCE_POLICY_PREPARATION.json',
 'ACTUAL_MIGRATION_EVENT_FIXTURE.json','ACTUAL_FULL120_FRESH_HANDLER_FIXTURE.json',
 'PRODUCTION_HANDLER_FINITE_IO_FIXTURE.json','CAMPAIGN_PRESTART_EXECUTION_GUARDS.json',
 'GUROBI_ASCII_FILE_IO_CERTIFICATION.json')

def replay_source_compatibility(value,entered,work):
    """Preserve historical replay provenance across an audited IO-only fix."""
    if value.get('validation_source_snapshot_unchanged') is not True:return False
    previous=value.get('validation_source_files')
    if previous==entered:return True
    path=Path(work)/'BOUND_JSON_REPAIR_20261023/SOURCE_COMPATIBILITY.json'
    if not path.exists():return False
    audit=read(path)
    if (audit.get('PASS') is not True or audit.get('before_source_files')!=previous
            or audit.get('after_source_files')!=entered
            or audit.get('budget_AST_after_removing_only_bound_telemetry_patch_equals_before') is not True
            or audit.get('all_other_scientific_source_bytes_unchanged') is not True):return False
    for item in audit['audit_artifacts']:
        if record(item['path'])!=item:return False
    return True

def certify(work,instruction,pause):
    work=Path(work);entered=source_files();report=dict(PASS=False,official_campaign_executed=False,
        no_new_grid_CG_or_delayed_master=True,algorithm_or_physics_replacement=False)
    evidence=[]
    def checked(path):
        path=Path(path);value=read(path)
        if value.get('PASS') is not True:raise ValueError('REQUIRED_EVIDENCE_FAILED:'+str(path))
        evidence.append(record(path));return value
    try:
        checked(work/'SEQUENTIAL_REPLAY_STATE.json')
        log=work/'FINAL_RELATED_TESTS.log'
        tests=['tests/test_v2_add_campaign_optimization.py','tests/test_v42_a_stage_domain_v2.py',
            'tests/test_v42_a_stage_domain_v2_bruteforce.py','tests/test_v42_a_stage_domain_v2_execution.py']
        import sys
        with log.open('w',encoding='utf8') as stream:
            outcome=subprocess.run([sys.executable,'-X','utf8','-B','-m','pytest','-q','-p','no:faulthandler',*tests],
                cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        if outcome.returncode:raise ValueError('FINAL_RELATED_TESTS_FAILED')
        evidence.extend([record(log),*[record(ROOT/name) for name in tests]])
        for name in REPLAY_NAMES:
            value=checked(OUT/name)
            if not replay_source_compatibility(value,entered,work):
                raise ValueError('CURRENT_FROZEN_VALIDATION_SOURCE_REQUIRED:'+name)
        compatibility=work/'BOUND_JSON_REPAIR_20261023/SOURCE_COMPATIBILITY.json'
        if compatibility.exists():evidence.append(record(compatibility))
        for tag in ('M1','M2'):
            new=read(OUT/(tag+'_STATIC_NATIVE0_AFTER_20261023.json'))
            for pair in new['same_current_case_arrays'].values():
                if pair['before']['sha256']!=pair['after']['sha256']:raise ValueError('CHANGED_STATIC_MATH_BYTES')
                for row in pair.values():
                    if isinstance(row,dict) and record(row['path'])!=row:raise ValueError('STATIC_MODEL_ARTIFACT_DRIFT')
            proof=checked((OUT if tag=='M1' else OUT/'stage_m2')/'IEEE8500_EXACT_COMPACT_EQUIVALENCE.json')
            if not proof['LP_relaxation_preserved'] or not proof['original_16face_physics_preserved']:
                raise ValueError('ORIGINAL_LP_INTEGER_OBJECTIVE_BOUNDS_AND_LIFT_PROOF_REQUIRED')
        if read(OUT/'JOINT_NATIVE0_AFTER_20261023.json')['exhaustive_actual_CSR']['canonical_CSR_sha256']!='e47d287bb577206eb5d76a7c78d30807ceffe8a4c2ba253880bfaf0ca4b7fa7b':
            raise ValueError('EXACT_DIRECT_JOINT_BASELINE_CSR_REQUIRED')
        timing=checked(OUT/'A_STAGE_R043_TIMING_AUTHORITY_20261023.json')
        if (timing['jobs'],timing['affected_jobs'],timing['restored_start_choices'],timing['restored_starts_with_locally_hard_valid_STAY'])!=(1499,1395,121313,121313):
            raise ValueError('FULL_JOB_TIMING_ADJUDICATION_REQUIRED')
        for row in timing['files']:
            if record(row['path'])!=row:raise ValueError('TIMING_AUTHORITY_SOURCE_DRIFT')
        for tag,name in [('A1','A1_VARIABLE_AIDC_FULL_NATIVE0.json'),('A2','A2_FIXED_M1_FULL_NATIVE0.json')]:
            current=checked(OUT/name)
            if current['complete_full_pricing_blocks']['classes']!=117 or current['original_complete_domain']['jobs']!=1499:
                raise ValueError('ALL_JOB_AND_LOCAL_PRICING_BLOCKS_REQUIRED')
            for key in ('state','source_preparation','independent_full_grid_projection'):
                row=current[key]
                if record(row['path'])!=row:raise ValueError('A_COMPLETE_NATIVE0_ARTIFACT_DRIFT:'+key)
        numerical=[]
        for name in ('ISOLATED_NUMERICAL_CANARY_20261023.json','A1_ISOLATED_NUMERICAL_CANARY_20261023.json'):
            value=checked(OUT/name);numerical.append(value)
            if value['source_files']!=entered or value['official_campaign_executed'] is not False:
                raise ValueError('SEPARATE_CURRENT_SOURCE_NUMERICAL_CANARY_REQUIRED')
        if not numerical[1]['current_source_independent_complete_case_verification']['PASS']:
            raise ValueError('CURRENT_SOURCE_A1_FULL_STATIC_REPLAY_REQUIRED')
        # Human steering on October23 ends additional RAM/performance studies.
        # Current-source Native0, actual handlers, exact math and FULL proofs
        # above remain mandatory; historical timing is not a launch gate.
        comparisons=[]
        duplicate=checked(work/'EXACT_DUPLICATE_CENSUS.json')
        if duplicate['exact_duplicate_rows']!=78:raise ValueError('STATIC_SCALE_REVIEW_RECORD_DRIFT')
        source_paths=[p.name for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(('v42','v43','v44'))]
        changed=subprocess.check_output(['git','diff','--name-only','4ff700bcae04189705d77a454fffa6499ec83198','--',*source_paths],cwd=ROOT,text=True).splitlines()
        if changed:raise ValueError('FROZEN_ORIGINAL_SOURCE_FILES_CHANGED:'+str(changed))
        algorithm=read(OUT/'V44_R043_ALGORITHM_IDENTITY_AUDIT.json')
        if algorithm['original']!=SOURCE or algorithm['algorithm_source_unchanged'] is not True:raise ValueError('R043_SOURCE_AUDIT_REQUIRED')
        for row in algorithm['sources']:
            path=ROOT/row['relative']
            actual=subprocess.check_output(['git','hash-object','--path='+row['relative'],str(path)],cwd=ROOT,text=True).strip()
            if actual!=row['pinned_git_blob']:raise ValueError('ORIGINAL_R043_GIT_BLOB_DRIFT')
        verified_pause=verify_pause(record(pause))
        report.update(PASS=True,validated_evidence=evidence,performance_comparison_rows=comparisons,
            further_RAM_and_performance_benchmarks_deferred_by_human=True,
            static_extra_duplicate_elimination_adopted=False,static_formulation_scale_unchanged=True,
            static_duplicate_scan_not_retained_in_official_case_preparation=True,
            original_LP_integer_objective_bounds_and_reconstruction_preserved=True,
            A1_before_complete_timing='Partial broader-domain baseline cancelled; no complete before duration asserted',
            A2_legacy_complete_timing='Legacy narrow WINDOW timing is not a same-domain performance comparison',
            diagnostic_Native_optimize_calls=sum(r['diagnostic_Native_optimize_calls'] for r in numerical),
            execution_identity=dict(source_files=entered,hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'),
                inputs=day_inputs()['files'],budget_policy=policy(),human_instruction=record(instruction),iteration2_pause=record(pause)))
        if source_files()!=entered:raise ValueError('SOURCE_CHANGED_WHILE_FINAL_GATE_RECONCILED')
    except BaseException as error:
        report.update(PASS=False,error=repr(error),traceback=traceback.format_exc())
        raise
    finally:put('V2_ADD_OPTIMIZATION_VERIFICATION_20261023.json',report)
    return report
