"""Read-only package verification. No experiment imports, extraction, or fitting."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import tarfile

ROOT = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    delivery = json.loads((ROOT / 'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    for name, record in delivery['required_files'].items():
        path = ROOT / name
        assert path.stat().st_size == record['bytes'], name
        assert digest(path) == record['sha256'], name
    freeze = json.loads((ROOT / 'FINAL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
    for name, expected in freeze['code_hashes'].items():
        assert digest(ROOT / name) == expected, name
    assert digest(ROOT / 'EXPERIMENT_PROTOCOL.json') == freeze['protocol_sha256']
    records = json.loads((ROOT / 'BUNDLE_MEMBER_MANIFEST.json').read_text(encoding='utf-8'))
    expected = {r['path']: r for r in records}
    assert len(expected) == len(records)
    seen = set()
    with tarfile.open(ROOT / 'MODEL_AND_MEMBERSHIP_EVIDENCE.tar.gz', 'r:gz') as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            assert member.isfile() and not relative.is_absolute() and '..' not in relative.parts
            assert member.name not in seen and member.name in expected
            seen.add(member.name)
            record = expected[member.name]
            assert member.size == record['bytes'], member.name
            with archive.extractfile(member) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'], member.name
    assert seen == set(expected)
    result = {
        'PASS': True,
        'required_deliverables_verified': len(delivery['required_files']),
        'frozen_code_files_verified': len(freeze['code_hashes']),
        'archive_members_verified': len(seen),
        'archive_sha256': digest(ROOT / 'MODEL_AND_MEMBERSHIP_EVIDENCE.tar.gz'),
        'training_calls': 0,
        'grid_campaign_executions': 0,
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
