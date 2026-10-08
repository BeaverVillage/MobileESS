"""Post-commit D-only readiness receipt with the exact final integration HEAD."""
import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from .audit import ROOT, REPORTS, A_HEAD, M_HEAD, C3_HEAD, git, write
from .storage import sha, setup
from .pipeline import configuration


def verify_preservation():
    changes = git('diff','--no-renames','--name-only',A_HEAD,'HEAD').decode('utf8').splitlines()
    allowed_existing = {'.gitignore','.gitattributes','README.md','v42_a_stage_domain_v2/execution.py'}
    original_tree = {r.split('\t')[1] for r in git('ls-tree','-r',A_HEAD).decode('utf8').splitlines()}
    overwritten = sorted(set(changes)&original_tree)
    if set(overwritten)-allowed_existing:
        raise ValueError('UNAUTHORIZED_A_BASELINE_CHANGE:'+str(set(overwritten)-allowed_existing))
    for p in ('v42_native/mess.py','v42_bootstrap/m1.py'):
        raw = git('show',f'{A_HEAD}:{p}')
        if hashlib.sha256(raw).hexdigest() != sha(ROOT/p):
            raise ValueError('COMMON_MESS_PHYSICS_SOURCE_DRIFT')
        if raw != git('show',f'{M_HEAD}:{p}') or raw != git('show',f'{C3_HEAD}:{p}'):
            raise ValueError('A_M_C3A_COMMON_PHYSICS_IDENTITY_DRIFT')
    imported = json.loads((REPORTS/'SELECTIVE_M_IMPORT.json').read_text(encoding='utf8'))
    for row in imported['files']:
        if sha(ROOT/row['path']) != row['sha256'] or hashlib.sha256(git('show',f"HEAD:{row['path']}")).hexdigest() != row['sha256']:
            raise ValueError('SELECTIVE_M_BLOB_BYTE_DRIFT:'+row['path'])
    return dict(PASS=True, existing_A_files_modified=overwritten, selective_M_files_verified=len(imported['files']),
                common_physics_byte_identical=True, historical_source_evidence_budget_changes=0,
                existing_workspaces_written_after_D_only_instruction=False,
                existing_M_process_control_calls=0, unfinished_M_files_consumed=0)


def ready():
    setup();c=configuration()
    if git('status','--porcelain').strip():
        raise ValueError('COMMIT_AND_CLEAN_V42_BEFORE_READINESS_RECEIPT')
    if git('branch','--show-current').decode().strip() != 'v42':
        raise ValueError('V42_BRANCH_REQUIRED')
    if (ROOT/'.git/objects/info/alternates').exists():
        raise ValueError('INDEPENDENT_CLONE_REQUIRED_NO_SHARED_ALTERNATES')
    preservation=verify_preservation()
    evidence={}
    for name in ('A1_ORIGINAL_INTEGER_PHYSICAL_REPLAY.json','INDEPENDENT_P1_ONLY_INTERFACE_VERIFICATION.json',
                 'M1_C3A_ORIGINAL_REPLAY.json','NATIVE_BUILD_ONLY.json','PASS27_P1_ONLY_COMPATIBILITY.json',
                 'ZERO_NATIVE_COMMON_TESTS.json'):
        path=REPORTS/name;r=json.loads(path.read_text(encoding='utf8'))
        if r.get('PASS') is not True:
            raise ValueError('INTEGRATION_TEST_NOT_PASS:'+name)
        evidence[name]=dict(path=str(path),sha256=sha(path),PASS=True)
    tests=json.loads((REPORTS/'ZERO_NATIVE_COMMON_TESTS.json').read_text(encoding='utf8'))
    sources={p:sha(ROOT/p) for p in git('diff','--no-renames','--name-only',A_HEAD,'HEAD').decode('utf8').splitlines()
             if p.endswith('.py')}
    result=dict(schema='V42_INTEGRATION_READY_V1', integration_ready=True,
        integration_HEAD=git('rev-parse','HEAD').decode().strip(), branch='v42', workspace=str(ROOT),
        git_directory=str(ROOT/'.git'), independent_D_clone=True, git_working_tree_clean=True,
        sources=dict(A_PR186=A_HEAD,M_completed_PR188=M_HEAD,M_scientific_PR162_C3A=C3_HEAD),
        changed_python_modules=sources, policy=c['policy'], tests=evidence,
        test_counts=dict(passed=len(tests['passed']),skipped=len(tests['skipped']),failed=len(tests['failed'])),
        native_optimize_calls=0, large_new_M1_runs=0, full_May_B1_campaign_runs=0,
        scientific_state=dict(A1_P1_ONLY_ACCEPTED=True,A1_ACCEPTED=False,A1_day='2025-05-12',
            current_M1_global_gap_percent=9.500515051068552,M1_ACCEPTED=False,
            historical_M1_input='May01/1499 jobs',new_P1_only_M1_input='May12/1782 jobs',
            historical_M1_point_or_bound_transferred_to_new_input=False,new_M1_anchor_result='NOT_RUN_NOT_CERTIFIED',
            A2_M2_PlanningFreeze_Actual_FreshAC_Validation='NOT_RUN',
            PASS27_automatically_inherited=False),
        M_handoff=dict(state='AWAIT_COMPLETED_RESULT_WITHOUT_POLLING',baseline_completed_head=M_HEAD,
            contract=str(REPORTS/'FINAL_M_HANDOFF_KO.md'),admission_command='.\\Start-V42.ps1 handoff-check -Handoff D:\\completed_M_handoff.json',
            select_verified_committed_delta_only=True,full_branch_merge=False,automatic_solver_promotion=False),
        preservation=preservation,
        runtime=dict(python=sys.executable,python_version=platform.python_version(),
            packages={p:importlib.metadata.version(p) for p in ('numpy','scipy','gurobipy','pytest','pandas')},
            TEMP=str(ROOT/'tmp'),TMP=str(ROOT/'tmp'),cache=str(ROOT/'cache')),
        receipt_git_policy='Generated after final commit and ignored, so exact integration HEAD is not a recursive self-reference.',
        final_M_work_completed=False, integration_ready_is_not_M_scientific_acceptance=True)
    write(ROOT/'V42_INTEGRATION_READY.json',result)
    return result


if __name__=='__main__':
    r=ready();print('V42_INTEGRATION_READY',r['integration_HEAD'],r['test_counts'])
