"""Check artifact bytes against the manifest and Git without reduction imports."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def run(reference='HEAD', write_receipt=False):
    root = Path(__file__).resolve().parents[1]
    out = root / 'docs/v42_m1_ultracompact_exact_20261006'
    manifest = json.loads((out / 'SHA256_MANIFEST.json').read_bytes())
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for relative, expected in manifest['files'].items():
        assert digest((root / relative).read_bytes()) == expected, ('FILESYSTEM', relative)
        spec = ':' + relative if reference == 'index' else reference + ':' + relative
        blob = subprocess.check_output(['git', '--no-pager', 'show', spec], cwd=root)
        assert digest(blob) == expected, ('GIT_BLOB', relative)
    count = len(manifest['files'])
    if write_receipt:
        result = dict(PASS=True, files_checked=count, filesystem_SHA256=True,
                      git_blob_SHA256=True, checked_git_reference=reference,
                      manifest_SHA256=digest((out / 'SHA256_MANIFEST.json').read_bytes()),
                      receipt_and_manifest_self_excluded=True,
                      production_reduction_logic_imported=False,
                      additional_optimize_calls=0)
        (out / 'MANIFEST_INDEPENDENT_VERIFICATION.json').write_bytes(
            (json.dumps(result, indent=2) + '\n').encode('utf-8'))
    print('FILESYSTEM_AND_GIT_MANIFEST_PASS', count, reference, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', default='HEAD')
    parser.add_argument('--write-receipt', action='store_true')
    args = parser.parse_args()
    run(args.reference, args.write_receipt)
