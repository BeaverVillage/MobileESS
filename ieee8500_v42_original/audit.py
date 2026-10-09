"""Read source bytes/AST only. Never import an original algorithm module."""
import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .hold import receipt
from .source_links import SOURCE_HEADS, ENTRY_POINTS

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/ieee8500_v42_original_engine'
PREFIXES = {
    'PR198': ('v42_b2_seed_recovery_v19', 'v42_b2_seed_recovery_v18r3',
              'v42_b2_seed_recovery_v18r2', 'v42_b2_seed_recovery_v18',
              'v42_b2_start_recovery_v13', 'v42_b2_build_authority_v13'),
    'PR191': ('v42_b3_joint', 'v42_may_build_v6'),
    'PR189': ('v42_native', 'v42_may_campaign_native90', 'v42_bootstrap',
              'v42_m1_anytime', 'v42_m1_hybrid', 'v42_m1_research',
              'v42_supercompact', 'v42_integrated', 'v42_thermal'),
}


def write(name, value):
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def frozen_sources():
    records = []
    for authority, prefixes in PREFIXES.items():
        head = SOURCE_HEADS[authority]
        output = subprocess.check_output(['git', 'ls-tree', '-r', head, '--', *prefixes], cwd=ROOT)
        objects = []
        for line in output.decode('utf8').splitlines():
            metadata, path = line.split('\t', 1)
            mode, kind, oid = metadata.split()
            if kind == 'blob' and path.endswith('.py'):
                objects.append((path, oid))
        data = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=ROOT,
                                       input=''.join(oid + '\n' for _, oid in objects).encode())
        offset = 0
        for path, oid in objects:
            end = data.index(b'\n', offset)
            fields = data[offset:end].split(); size = int(fields[-1]); offset = end + 1
            original = data[offset:offset + size]; offset += size + 1
            current_path = ROOT / path
            current = current_path.read_bytes() if current_path.is_file() else None
            status = ('MISSING' if current is None else 'EXACT_SOURCE_BYTES' if current == original
                      else 'LINE_ENDINGS_ONLY' if current.replace(b'\r\n', b'\n') == original.replace(b'\r\n', b'\n')
                      else 'PREPARATION_EDIT_REQUIRES_LATER_REGRESSION')
            records.append(dict(path=path, authority=authority, head=head, git_blob=oid,
                original_sha256=hashlib.sha256(original).hexdigest(),
                worktree_sha256=hashlib.sha256(current).hexdigest() if current is not None else None,
                content_status=status))
    write('SOURCE_AUTHORITY.json', dict(heads=SOURCE_HEADS, files=records,
         scope='Named original builder/algorithm/seed/bridge source prefixes; not a complete dependency closure',
         actual_original_calls=0, scientific_imports=0))
    return records


def static_review(records):
    rows, syntax = [], []
    pattern = re.compile(r'\b(?:96|97)\s*,\s*4\b|\bunits\s*=\s*4\b|range\(4\)|==\s*4\b|!=\s*4\b|(?:ones|zeros|full)\(4\b|lil_matrix\(\(4\b|len\(source_rows\)\+4')
    for record in records:
        path = ROOT / record['path']
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8-sig')
        ast.parse(text, filename=str(path))
        syntax.append(record['path'])
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                status = ('KEEP_MOCK_FIXTURE' if 'dry_run.py' in record['path'] else
                          'KEEP_FOUR_STAGE_CONTRACT' if any(token in line for token in
                             ('requests', 'records', 'results', 'outputs', 'schema_count')) else
                          'STATIC_REVIEW_REQUIRED_NOT_ASSUMED_VEHICLE_COUNT')
                rows.append(dict(path=record['path'], line=number, status=status, text=line.strip()))
    with (REPORT / 'FOUR_LITERAL_STATIC_REVIEW.csv').open('w', encoding='utf8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['path', 'line', 'status', 'text'])
        writer.writeheader(); writer.writerows(rows)
    links = []
    for key, (module, symbol) in ENTRY_POINTS.items():
        path = module.replace('.', '/') + '.py'
        tree = ast.parse((ROOT / path).read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == symbol)
        links.append(dict(component=key, module=module, symbol=symbol, line=node.lineno,
                          status='STATIC_SYMBOL_FOUND_EXECUTION_HELD'))
    write('STATIC_REVIEW.json', dict(parsed_files=syntax, source_links=links,
        residual_four_literals=rows, native_model_equivalence='HOLD_WAITING_FOR_USER_APPROVAL',
        six_unit_FULL_Compact_C3A='HOLD_WAITING_FOR_USER_APPROVAL',
        full_dependency_closure='NOT_YET_COMPLETE', grid_builder_integration='NOT_YET_COMPLETE',
        all_grid_coefficient_generation='HOLD_WAITING_FOR_USER_APPROVAL',
        original_algorithm_replacement=False))


def run():
    static_review(frozen_sources())
    write('EXECUTION_HOLD.json', receipt())


if __name__ == '__main__':
    run()
