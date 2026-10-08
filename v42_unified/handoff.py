"""Read-only admission of explicitly completed, commit-pinned final M changes."""
import hashlib
import json
import re
from pathlib import Path
from .audit import ROOT, M_HEAD, git
from .storage import sha

REQUIRED_PRESERVED_FILES = (
    'v42_native/mess.py', 'v42_bootstrap/m1.py',
    'docs/v42_m1_ultracompact_exact_20261006/C3A_A.npz',
    'docs/v42_m1_ultracompact_exact_20261006/C3A_DATA.npz',
    'docs/v42_m1_ultracompact_exact_20261006/C3A_VALID_START.npz',
)


def inspect_completed_result(path):
    path = Path(path).resolve()
    if path.drive.upper() != 'D:':
        raise ValueError('HANDOFF_MANIFEST_MUST_BE_ON_D')
    doc = json.loads(path.read_text(encoding='utf8'))
    if doc.get('schema') != 'V42_COMPLETED_M_HANDOFF_V1' or doc.get('state') != 'COMPLETE':
        raise ValueError('COMPLETED_M_RESULT_REQUIRED_NO_WORKTREE_OR_PENDING_RESULTS')
    if doc.get('baseline_completed_head') != M_HEAD:
        raise ValueError('M_HANDOFF_BASELINE_DRIFT')
    head = doc.get('completed_head', '')
    if not re.fullmatch('[0-9a-f]{40}', head):
        raise ValueError('EXACT_COMPLETED_M_HEAD_REQUIRED')
    expected = doc.get('preserved_scientific_hashes', {})
    if set(REQUIRED_PRESERVED_FILES) - set(expected):
        raise ValueError('M_REQUIRED_PHYSICS_MATRIX_DATA_START_IDENTITIES_MISSING')
    if git('merge-base', M_HEAD, head).decode().strip() != M_HEAD:
        raise ValueError('FINAL_M_HEAD_NOT_DESCENDANT_OF_COMPLETED_BASE')
    all_changes = git('diff','--no-renames','--name-only',M_HEAD,head).decode('utf8').splitlines()
    approved = doc.get('verified_changes', [])
    if not approved or len({r['path'] for r in approved}) != len(approved):
        raise ValueError('DISTINCT_VERIFIED_CHANGED_FILES_REQUIRED')
    rows = []
    for r in approved:
        p = r['path']
        if p not in all_changes or p.startswith(('/', '\\')) or '..' in Path(p).parts:
            raise ValueError('HANDOFF_PATH_NOT_IN_COMMITTED_DELTA')
        if r.get('independent_verification_PASS') is not True or r.get('scope') not in ('RESEARCH_ONLY','PROVEN_EXACT_FORMULATION'):
            raise ValueError('UNVERIFIED_M_CHANGE_OR_SOLVER_PROMOTION')
        raw = git('show', f'{head}:{p}')
        if hashlib.sha256(raw).hexdigest() != r['sha256']:
            raise ValueError('FINAL_M_BLOB_HASH_MISMATCH')
        rows.append(dict(path=p, sha256=r['sha256'], scope=r['scope']))
    evidence = doc.get('verification_evidence', [])
    if not evidence:
        raise ValueError('INDEPENDENT_M_EVIDENCE_REQUIRED')
    for r in evidence:
        raw = git('show', f"{head}:{r['path']}")
        if hashlib.sha256(raw).hexdigest() != r['sha256'] or json.loads(raw).get('PASS') is not True:
            raise ValueError('COMPLETED_M_VERIFICATION_EVIDENCE_NOT_PASS')
    for p, h in expected.items():
        if hashlib.sha256(git('show', f'{M_HEAD}:{p}')).hexdigest() != h or hashlib.sha256(git('show', f'{head}:{p}')).hexdigest() != h:
            raise ValueError('M_SCIENTIFIC_AUTHORITY_CHANGED_REQUIRES_SEPARATE_REVIEW')
    return dict(PASS=True, state='READY_FOR_SELECTIVE_REVIEW', completed_head=head,
                verified_changes=rows, omitted_delta_files=sorted(set(all_changes)-{r['path'] for r in approved}),
                production_solver_auto_promoted=False, M1_acceptance_auto_changed=False,
                import_performed=False, merge_performed=False,
                next_step='Import only these exact blobs in D V42, resolve overlap explicitly, rerun replay and interface tests, and create a reviewed integration commit.')
