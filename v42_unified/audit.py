"""Audit immutable Git objects and selectively port completed M authority."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A_HEAD = '9a1b41260aff3bc70d2e36d7e1c293c03ea114de'
M_HEAD = '4b19e85089171729a3225529a40cb00bf31f43d5'
C3_HEAD = '1d922c91eb27056a5ccc79c92ef18146707099ab'
REPORTS = ROOT / 'docs/v42_integration_20261008'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')


def objects(head):
    return {line.split('\t', 1)[1]: line.split()[2]
            for line in git('ls-tree', '-r', head).decode('utf8').splitlines()}


def audit():
    base = git('merge-base', A_HEAD, M_HEAD).decode().strip()
    trees = {h: objects(h) for h in (base, A_HEAD, M_HEAD, C3_HEAD)}
    changes = {}
    for label, head in [('A', A_HEAD), ('M', M_HEAD)]:
        changes[label] = [{'path': p, 'before_blob': trees[base].get(p), 'after_blob': trees[head].get(p)}
                         for p in sorted(trees[base].keys() | trees[head].keys())
                         if trees[base].get(p) != trees[head].get(p)]
    common = []
    for p in sorted(trees[A_HEAD].keys() & trees[M_HEAD].keys()):
        if not p.endswith('.py'):
            continue
        b = git('show', f'{A_HEAD}:{p}')
        same = trees[A_HEAD][p] == trees[M_HEAD][p]
        common.append(dict(path=p, A_blob=trees[A_HEAD][p], M_blob=trees[M_HEAD][p],
                           identical=same, A_sha256=hashlib.sha256(b).hexdigest(),
                           M_sha256=hashlib.sha256(b if same else git('show', f'{M_HEAD}:{p}')).hexdigest()))
    for p in ('v42_native/mess.py', 'v42_bootstrap/m1.py'):
        if len({trees[h][p] for h in (A_HEAD, M_HEAD, C3_HEAD)}) != 1:
            raise ValueError('COMMON_PHYSICS_SOURCE_DRIFT:'+p)
    result = dict(PASS=True, repository='BeaverVillage/MobileESS', common_ancestor=base,
                  A_HEAD=A_HEAD, M_completed_HEAD=M_HEAD, M_scientific_C3A_HEAD=C3_HEAD,
                  changes=changes, common_python_modules=common,
                  no_merge=True, unfinished_M_worktree_files_read=False,
                  historical_shared_worktree_registration_created_before_D_clone_instruction=True,
                  independent_git_dir=str(ROOT/'.git'), source_repositories_read_only=True)
    write(REPORTS/'SOURCE_AUTHORITY_AUDIT.json', result)
    return result


def port():
    """Only exact reduction/verification modules and their missing import closure.

    Existing A files are never overwritten. No experiment controller is a seed.
    Every copied blob is pinned to the last completed M HEAD.
    """
    tree = objects(M_HEAD)
    a_tree = objects(A_HEAD)
    seeds = ['v42_ultracompact/'+n+'.py' for n in
             ('__init__', 'common', 'audit', 'polytope', 'support', 'verify')]
    queue = list(seeds)
    selected = set()
    while queue:
        p = queue.pop()
        if p in selected or p in a_tree:
            continue
        if p not in tree:
            raise ValueError('M_IMPORT_NOT_FOUND:'+p)
        selected.add(p)
        raw = git('show', f'{M_HEAD}:{p}')
        source = ast.parse(raw)
        parts = p[:-3].split('/')
        for node in ast.walk(source):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = parts[:-node.level] if node.level else []
                name = '.'.join(prefix+([node.module] if node.module else []))
                modules = [name, *[name+'.'+a.name for a in node.names if a.name != '*']]
            for module in modules:
                if not module.startswith('v42_'):
                    continue
                candidates = [module.replace('.', '/')+'.py', module.replace('.', '/')+'/__init__.py']
                dep = next((q for q in candidates if q in tree), None)
                if dep is not None and dep not in a_tree:
                    queue.append(dep)
                package = module.split('.')[0]+'/__init__.py'
                if package in tree and package not in a_tree:
                    queue.append(package)
        target = ROOT/p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    # Full frozen C2/C3 proof packets, plus completed M1 status/physical evidence.
    packets = ('docs/v42_m1_ultracompact_exact_20261006/', 'docs/v42_m1_supercompact_exact_20261006/')
    evidence = {p for p in tree if p.startswith(packets)}
    evidence.update('docs/v42_m1_group_branching_20261008/'+n for n in
                    ('FINAL_DECISION.json', 'ORIGINAL_PHYSICAL_REPLAY.json', 'SOURCE_IDENTITY.json',
                     'POSTRUN_INDEPENDENT_AUDIT.json', 'FINAL_REVIEW_KO.md'))
    for p in sorted(evidence):
        selected.add(p)
        if (ROOT/p).exists():
            if hashlib.sha256((ROOT/p).read_bytes()).digest() != hashlib.sha256(git('show', f'{M_HEAD}:{p}')).digest():
                raise ValueError('A_EXISTING_EVIDENCE_CONFLICT:'+p)
            continue
        target = ROOT/p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git('show', f'{M_HEAD}:{p}'))
        selected.add(p)
    rows = []
    for p in sorted(selected):
        raw = (ROOT/p).read_bytes()
        rows.append(dict(path=p, source_head=M_HEAD, blob=tree[p], sha256=hashlib.sha256(raw).hexdigest(),
                         bytes=len(raw), production_solver_default=False))
    result = dict(PASS=True, source_head=M_HEAD, files=rows, selective_import=True,
                  scientific_formulation='PR162 C3A', solver_experiment_auto_selected=False,
                  unfinished_M_inputs=False)
    old_manifest = REPORTS/'SELECTIVE_M_IMPORT.json'
    if old_manifest.exists():
        for row in json.loads(old_manifest.read_text(encoding='utf8'))['files']:
            p = row['path']
            if p in selected or p in a_tree:
                continue
            target = (ROOT/p).resolve()
            if not target.is_relative_to(ROOT.resolve()):
                raise ValueError('PORT_CLEANUP_OUTSIDE_D_REPOSITORY')
            if hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('PORT_CLEANUP_MODIFIED_FILE')
            target.unlink()
    write(REPORTS/'SELECTIVE_M_IMPORT.json', result)
    return result


if __name__ == '__main__':
    result = audit()
    copied = port()
    print('AUTHORITY_AUDIT', result['common_ancestor'], 'selective M files', len(copied['files']))
