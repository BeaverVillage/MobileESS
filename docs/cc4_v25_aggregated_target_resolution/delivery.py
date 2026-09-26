"""Portable delivery byte manifest, without scientific decisions."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys

ROOT = Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(name, value):
    with (ROOT / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def verify():
    manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        path = ROOT / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], row['path']
    print('PORTABLE DELIVERY PASS', len(manifest['files']))


def seal():
    assert not (ROOT / 'DELIVERY_MANIFEST.json').exists()
    for name in ['RAW_TARGET_AUDIT.json', 'VALIDATION.json', 'INDEPENDENT_AUDIT.json', 'UNCERTAINTY_AUDIT.json', 'TEST_RESULTS.json']:
        assert json.loads((ROOT / name).read_text(encoding='utf-8'))['PASS'], name
    from study import source_guard, guard
    source_guard(); guard(True)
    models = sorted((ROOT / 'fits').rglob('*.txt.gz'))
    receipts = [json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / 'fits').rglob('RECEIPT.json')]
    assert len(receipts) == 273 and len(models) == 1638
    assert len(models) == sum(len(row['models']) for row in receipts)
    write('MODEL_CHECKPOINT_MANIFEST.json', dict(storage='local preserved checkpoints; recipe/exact membership/seeds/digests committed for reproduction',
        files=[dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in models]))
    write('ENVIRONMENT.json', dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
        packages={name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'lightgbm', 'scikit-learn', 'pyarrow']}))
    files = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path in models or path.suffix in ['.pyc', '.pid']: continue
        files.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    write('DELIVERY_MANIFEST.json', dict(files=files, checkpoints=len(models), scientific_decisions_unchanged=True))
    verify()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['seal', 'verify']); args = parser.parse_args()
    globals()[args.stage]()
