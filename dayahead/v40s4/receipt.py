"""Validate commits and byte identity; no model execution or scientific changes."""
import argparse
from .common import *
from .review import required_artifacts, working_scope
from .diagnostics import guard_selection

RECEIPT='dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_FINAL_COMMIT_RECEIPT.json'


def protected():
    start=get('PROTECTED_SCOPE_START')
    entries={r.split('\t')[1]:r.split('\t')[0] for r in git('ls-tree','-r','HEAD').splitlines()}
    assert all(entries.get(p)==entry for p,entry in start['all_existing_Git_entries'].items())
    for p,h in start['S3_SHA256'].items():
        assert sha((ROOT/p).read_bytes())==h and sha((S3ROOT/p).read_bytes())==h,p
    assert sha(SOURCE.read_bytes())==SOURCE_SHA
    guard_prereg();guard_selection()
    for name,h in get('MODEL_FREEZE')['model_SHA256'].items():assert sha((OUT/'models'/name).read_bytes())==h,name
    changed=[p.decode('utf-8') for p in git('diff','--name-only','-z',BASE,'HEAD',binary=True).split(b'\0') if p]
    assert all(allowed(p) for p in changed)
    return dict(all_inherited_Git_entries_unchanged=len(start['all_existing_Git_entries']),
                S3_original_and_clone_bytes_verified=len(start['S3_SHA256']),
                source_SHA256=SOURCE_SHA,changed_paths=changed,changes_outside_allowed=[])


def prepare():
    assert not (ROOT/RECEIPT).exists(),'Receipt already exists; do not replace a final freeze'
    assert git('status','--porcelain=v1','-z','--untracked-files=all',binary=True)==b'', 'Science commit must be clean'
    science=git('rev-parse','HEAD');selection=get('METHOD_SELECTION_COMMIT_RECEIPT')['commit']
    assert science!=selection
    git('merge-base','--is-ancestor',selection,science)
    protection=protected();owned={}
    for p in [x.decode('utf-8') for x in git('ls-files','-z',binary=True).split(b'\0') if x]:
        if not allowed(p):continue
        committed=git('show',f'{science}:{p}',binary=True)
        assert (ROOT/p).read_bytes()==committed,p
        owned[p]=sha(committed)
    required=required_artifacts()
    assert [n for n in required if not (OUT/n).exists()]==['V40S4_FINAL_COMMIT_RECEIPT.json']
    decision=get('FINAL_DECISION');assert decision['selected'] is None
    tests=get('TEST_REPORT');assert tests['passed']==105 and tests['pytest']['failures']==tests['pytest']['errors']==tests['pytest']['skipped']==0
    assert sha((OUT/'V40S4_TEST_JUNIT.xml').read_bytes())==tests['junit_SHA256']
    assert sha((ROOT/'tests/dayahead/test_v40s4_contracts.py').read_bytes())==tests['tests_SHA256']
    write('FINAL_COMMIT_RECEIPT',dict(status='PASS',timestamp=now(),
        branch=git('branch','--show-current'),worktree=str(ROOT),
        scientific_commit=science,S3_scientific_commit=S3SCIENCE,S3_receipt_base=BASE,
        preregistration_commit=get('PREREGISTRATION_COMMIT_RECEIPT')['commit'],selection_commit=selection,
        final_classification=decision['classification'],selected=None,body_safety='FAIL',
        tail_detection='FAIL_NO_CAL_ELIGIBLE_ETA',hybrid_safety='NOT_EVALUATED_NO_CAL_ELIGIBLE_ETA',
        interpretation=decision['interpretation'],proxy_assumption=ASSUMPTION,
        historical_D1_snapshot_provenance='UNVERIFIED',original_submission_provenance='UNVERIFIED',
        source_protection=protection,owned_files_SHA256=owned,owned_file_count=len(owned),
        owned_manifest_scope='All S4 scientific-commit source/artifacts/tests, verified Git blob equals working bytes. Receipt excluded from its own hash manifest.',
        git_status_after_scientific_commit='CLEAN',pytest_passed=tests['passed'],
        minimum_checks_72_73='Complete artifact presence checked after writing receipt; clean scientific commit checked before receipt. Verify final receipt commit with the command below.',
        required_artifact_count=len(required),required_artifacts=required,
        required_presence_after_receipt_write='PASS_CHECKED_BY_RECEIPT_PREPARE',
        receipt_commit_identity='Commit introducing this file; resolve with git log -1 --format=%H -- '+RECEIPT,
        post_receipt_commit_verification='python -B -m dayahead.v40s4.receipt verify',
        post_receipt_verification_scope='Must verify clean Git, science ancestor, only receipt changed, every science-file SHA, required artifacts and receipt Git blob identity; output is external to this self-referential receipt.',
        optimizer_calls=0,Gurobi_calls=0,OpenDSS_calls=0,Fresh_calls=0,post_selection_refits=0,
        May_firewall=get('MAY_FIREWALL'),shadow='SEALED',shadow_rows_read=0,
        bootstrap='NOT_EXECUTED_SAFETY_FAIL',adapter_recommended_rows=[],holds=HOLDS,
        source_warning='Existing exposed positive terminal-service complete cases, not full backlog or verified original request snapshots. No exact production Apr01 final-state equivalence claimed.'))
    assert all((OUT/n).is_file() for n in required)
    assert working_scope() and all(allowed(p) for p in working_scope())
    print('RECEIPT_PREPARED',science,len(owned),'byte-verified files;',len(required),'required artifacts present')


def verify():
    r=get('FINAL_COMMIT_RECEIPT');head=git('rev-parse','HEAD')
    assert git('status','--porcelain=v1','-z','--untracked-files=all',binary=True)==b''
    git('merge-base','--is-ancestor',r['scientific_commit'],head)
    changes=[p.decode('utf-8') for p in git('diff','--name-only','-z',r['scientific_commit'],head,binary=True).split(b'\0') if p]
    assert changes==[RECEIPT],changes
    assert git('show',f'{head}:{RECEIPT}',binary=True)==(ROOT/RECEIPT).read_bytes()
    for p,h in r['owned_files_SHA256'].items():assert sha((ROOT/p).read_bytes())==h and sha(git('show',f'{head}:{p}',binary=True))==h,p
    assert all((OUT/p).is_file() for p in r['required_artifacts'])
    protection=protected()
    print(json.dumps(dict(status='PASS',scientific_commit=r['scientific_commit'],receipt_commit=head,
        final_Git_status='CLEAN',only_receipt_changed_after_science=True,receipt_Git_blob_equals_working_bytes=True,
        scientific_files_SHA256_verified=len(r['owned_files_SHA256']),required_artifacts_present=len(r['required_artifacts']),
        inherited_entries_unchanged=protection['all_inherited_Git_entries_unchanged'],
        S3_original_and_clone_files_verified=protection['S3_original_and_clone_bytes_verified'],
        final_classification=r['final_classification'],winner='NONE',shadow='SEALED'),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','verify']);a=p.parse_args()
    prepare() if a.stage=='prepare' else verify()
