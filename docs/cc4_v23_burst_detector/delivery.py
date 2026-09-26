"""Seal completed evidence and verify portable bytes; no model decisions."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys

ROOT = Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(name, value):
    with (ROOT / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def verify():
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        path = ROOT / item['path']
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], item['path']
    print('PORTABLE DELIVERY PASS', len(manifest['files']), flush=True)


def seal():
    assert not (ROOT / 'DELIVERY_MANIFEST.json').exists(), 'ALREADY_SEALED'
    for name in ['VALIDATION.json', 'INDEPENDENT_AUDIT.json', 'TEST_RESULTS.json',
                 'UNCERTAINTY_AUDIT.json', 'VERIFIER_SERIALIZATION_AUDIT.json']:
        assert json.loads((ROOT / name).read_text(encoding='utf-8'))['PASS'], name
    from study import source_guard, guard
    source_guard()
    guard(True)
    checkpoints = sorted((ROOT / 'fits').rglob('*.txt.gz'))
    assert len(checkpoints) == 546, len(checkpoints)
    write('MODEL_CHECKPOINT_MANIFEST.json', dict(
        storage='preserved locally; exact deterministic recipe and membership reproduce; not in Git',
        files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p), bytes=p.stat().st_size)
               for p in checkpoints]))
    packages = {n: importlib.metadata.version(n) for n in
                ['numpy', 'pandas', 'lightgbm', 'pyarrow', 'scikit-learn']}
    write('ENVIRONMENT.json', dict(python=sys.version, executable=sys.executable,
                                 platform=platform.platform(), packages=packages))
    files = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path in checkpoints:
            continue
        if path.suffix in ['.pid', '.pyc']:
            continue
        files.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path), bytes=path.stat().st_size))
    write('DELIVERY_MANIFEST.json', dict(files=files, checkpoints=len(checkpoints),
                                       model_decisions_unchanged=True))
    verify()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['seal', 'verify'])
    args = parser.parse_args()
    seal() if args.stage == 'seal' else verify()
