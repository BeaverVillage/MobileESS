"""Read-only verification of the complete B0 evidence and original frozen bytes."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from v42_b0_production.authority import DOC, read
from v42_campaign.authority import file_sha


def main():
    manifest = read(DOC / 'SHA256_MANIFEST.json')
    checked = 0
    for category in ('repository_evidence', 'authoritative_local_run_artifacts', 'implementation_sources'):
        for row in manifest[category]:
            assert file_sha(row['path']) == row['sha256'], row['path']
            checked += 1
    authority = read(DOC / 'B0_PRODUCTION_FREEZE_MANIFEST.json')
    observer = read(DOC / 'OBSERVER_PUBLICATION_FIX.json')
    for row in authority['source_files']:
        path = row['path']
        if path == observer['executed_source']['path']:
            path = observer['executed_source_snapshot']['path']
        assert file_sha(path) == row['sha256'], row['path']
    final = read(DOC / 'B0_CAMPAIGN_FINAL.json')
    assert final['flags']['B0_CAMPAIGN_COMPLETE']
    assert final['flags']['B0_DAYS_PASS'] == 31
    assert final['flags']['B0_FRESH_AC_CONVERGED'] == 31
    assert final['flags']['STOP_AFTER_B0']
    assert all(final['production_calls'][k] == 0 for k in ('B1', 'B2', 'B3', 'M1', 'Branch_and_Price'))
    print(json.dumps(dict(PASS=True, artifact_files=checked, frozen_sources=len(authority['source_files']),
                         run_id=authority['run_id'])))


if __name__ == '__main__':
    main()
