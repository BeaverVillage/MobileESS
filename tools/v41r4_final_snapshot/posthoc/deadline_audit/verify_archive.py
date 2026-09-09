"""Independent streaming archive verification; no project imports or solves."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import time

HERE = Path(__file__).resolve().parent
ARCHIVE = Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz')
EXPECTED = '1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3'


class Reader:
    def __init__(self, handle):
        self.handle = handle
        self.digest = hashlib.sha256()
    def read(self, size=-1):
        block = self.handle.read(size)
        self.digest.update(block)
        return block


def main():
    before = ARCHIVE.stat()
    index = {}
    metadata = {}
    start = last = time.monotonic()
    total = 0
    with ARCHIVE.open('rb') as handle:
        reader = Reader(handle)
        with tarfile.open(fileobj=reader, mode='r|gz') as tar:
            for member in tar:
                path = PurePosixPath(member.name)
                assert member.isfile() and not path.is_absolute() and '..' not in path.parts
                assert ':' not in member.name and member.name not in index
                digest = hashlib.sha256()
                payload = [] if len(path.parts) == 2 else None
                with tar.extractfile(member) as source:
                    while block := source.read(4*1024*1024):
                        digest.update(block)
                        if payload is not None:
                            payload.append(block)
                index[member.name] = {'bytes': member.size, 'sha256': digest.hexdigest()}
                if payload is not None:
                    metadata[path.name] = b''.join(payload)
                total += member.size
                if time.monotonic()-last > 20:
                    print(json.dumps(dict(stage='archive_hash', files=len(index), raw_GB=round(total/1e9,2), seconds=round(time.monotonic()-start))), flush=True)
                    last = time.monotonic()
        while reader.read(4*1024*1024):
            pass
    after = ARCHIVE.stat()
    assert reader.digest.hexdigest() == EXPECTED
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    roots = {PurePosixPath(name).parts[0] for name in index}
    assert len(roots) == 1
    prefix = roots.pop()
    listing = json.loads(metadata['FILE_MANIFEST.json'])
    for entry in listing:
        assert index[prefix+'/'+entry['path']]['sha256'] == entry['sha256']
    for name, data in metadata.items():
        (HERE / ('archive_'+name)).write_bytes(data)
    (HERE/'archive_member_index.json').write_text(json.dumps(index), encoding='utf-8')
    result = dict(status='PASS', archive=str(ARCHIVE), sha256=EXPECTED,
                  size_bytes=before.st_size, mtime_ns=before.st_mtime_ns,
                  files=len(index), uncompressed_bytes=total, manifest_files_verified=len(listing),
                  elapsed_s=time.monotonic()-start, external_workspace_result_read_count=0)
    (HERE/'archive_verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
