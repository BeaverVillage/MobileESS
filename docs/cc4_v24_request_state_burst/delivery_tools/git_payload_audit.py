"""Check staged/committed Git blob bytes against the sealed delivery payload."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'docs/cc4_v24_request_state_burst/'
BASE = 'e672e4a81e22e9fdca3316f7e73611b39481faa6'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8').strip()


parser = argparse.ArgumentParser()
parser.add_argument('--commit')
args = parser.parse_args()
manifest = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
expected = {PREFIX + row['path']: row for row in manifest['files']}
expected[PREFIX + 'DELIVERY_MANIFEST.json'] = None
if args.commit:
    listing = git('ls-tree', '-r', '--full-tree', args.commit, '--', PREFIX)
    modified = git('diff', '--name-status', BASE, args.commit)
else:
    listing = git('ls-files', '--stage', '--full-name', '--', str(ROOT))
    modified = git('diff', '--cached', '--name-status')
algorithm = git('rev-parse', '--show-object-format')
assert algorithm in ['sha1', 'sha256'], algorithm
entries = {}
for line in listing.splitlines():
    info, path = line.split('\t', 1)
    tokens = info.split()
    entries[path] = tokens[2] if args.commit else tokens[1]
assert set(entries) == set(expected), (sorted(set(entries) - set(expected)), sorted(set(expected) - set(entries)))
for path, oid in entries.items():
    payload = (ROOT / path.removeprefix(PREFIX)).read_bytes()
    item = expected[path]
    if item is not None:
        assert len(payload) == item['bytes'] and hashlib.sha256(payload).hexdigest() == item['sha256'], path
    digest = hashlib.new(algorithm, b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
    assert digest == oid, ('GIT_BYTE_DRIFT', path)
changes = []
for line in modified.splitlines():
    status, path = line.split('\t', 1)
    assert status == 'A' and path.startswith(PREFIX), ('OUT_OF_SCOPE', line)
    changes.append(path)
assert set(changes) == set(expected), 'DIFF_PAYLOAD_MEMBERSHIP'
print(json.dumps(dict(PASS=True, stage=args.commit or 'index', files=len(entries),
                      source_base=BASE, only_new_evidence_added=True)))
