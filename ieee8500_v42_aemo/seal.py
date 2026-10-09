"""Source preservation, meaningful test receipt and new-artifact content hashes."""
import sys
import unittest
from .common import *


def run(test=True):
    manifest=read(PR193/'ARTIFACT_SHA256_MANIFEST.json')
    for name,record in manifest['files'].items():
        assert sha(ROOT/name)==record['sha256'],('PR193_BYTE_DRIFT',name)
    core=read(PR193/'V42_SOURCE_SHA_MANIFEST.json')
    for name,expected in core['files'].items():assert sha(ROOT/name)==expected,('V42_CORE_DRIFT',name)
    assert git('diff','--diff-filter=CDMRTUXB','--name-only',PR193_SHA).decode().strip()=='', 'PARENT_TRACKED_FILE_MODIFICATION'
    latest=git('ls-remote','origin','refs/heads/v42').decode().split()[0]
    assert latest==LATEST_SHA,'LATEST_SOURCE_DRIFT_REQUIRES_NEW_AUDIT'
    write(REPORT/'SOURCE_END_VERIFICATION.json',dict(PASS=True,latest_remote_v42_sha=latest,
        initial_remote_v42_sha=LATEST_SHA,PR193_preserved_files=len(manifest['files']),
        V42_preserved_core_sources=len(core['files']),mapping_sha256=sha(MAPPING),
        no_existing_parent_tracked_changes=True,own_external_campaign_writes=0))
    if test:
        suite=unittest.TestLoader().discover(str(ROOT/'tests/ieee8500_v42_aemo'))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        write(REPORT/'TEST_RECEIPT.json',dict(tests=result.testsRun,errors=len(result.errors),
            failures=len(result.failures),skipped=len(result.skipped),PASS=result.wasSuccessful(),
            command='python -B -m unittest discover -s tests/ieee8500_v42_aemo -v',Native_calls=0))
        assert result.wasSuccessful()
    else:assert read(REPORT/'TEST_RECEIPT.json')['PASS']
    roots=[ROOT/'ieee8500_v42_aemo',REPORT,ROOT/'tests/ieee8500_v42_aemo']
    files={}
    for folder in roots:
        for p in sorted(folder.rglob('*')):
            if not p.is_file() or 'dss' in p.parts or '__pycache__' in p.parts:continue
            if p.name=='ARTIFACT_SHA256_MANIFEST.json':continue
            relative=p.relative_to(ROOT).as_posix()
            files[relative]=dict(sha256=sha(p),bytes=p.stat().st_size)
    assert all(r['bytes']<100*1024*1024 for r in files.values())
    write(REPORT/'ARTIFACT_SHA256_MANIFEST.json',dict(schema='IEEE8500_AEMO_SHA256_MANIFEST_V1',
        files=files,count=len(files),total_bytes=sum(r['bytes'] for r in files.values()),
        parent_PR193_sha=PR193_SHA,latest_source_sha=LATEST_SHA,
        final_B0_AC_qualification=True,full_Production_qualification=False,self_hash_excluded=True))
    print('sealed',len(files),'new artifacts; original193/core identityPASS;tests',read(REPORT/'TEST_RECEIPT.json')['tests'],flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--manifest-only',action='store_true')
    run(not p.parse_args().manifest_only)
