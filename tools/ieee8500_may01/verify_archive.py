"""Verify archive SHA256 and CSV source hashes against the archived manifest.

Reads the gzip stream once. Does not extract files or execute archived code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()

    def read(self, size=-1):
        data = self.stream.read(size)
        self.digest.update(data)
        return data


def verify(archive, package, output):
    expected = json.loads((package/'MANIFEST.json').read_text(encoding='utf-8'))
    member_manifest = None
    with archive.open('rb') as stream:
        reader = HashingReader(stream)
        with tarfile.open(fileobj=reader, mode='r|gz') as tf:
            for member in tf:
                if member.name == 'RAW_FILE_MANIFEST.json':
                    member_manifest = json.load(tf.extractfile(member))
        while reader.read(8*1024*1024):
            pass
        digest = reader.digest.hexdigest()
    if digest != expected['raw_archive']['archive_sha256']:
        raise ValueError('Raw archive SHA256 mismatch')
    if member_manifest is None:
        raise ValueError('Missing raw member manifest')
    members = {row['path']:row for row in member_manifest['files']}
    for name, source in expected['sources'].items():
        if name not in members or any(members[name][key]!=source[key] for key in ('sha256','bytes')):
            raise ValueError('CSV source differs from archive: '+name)
    result = dict(status='PASS',date=expected['date'],archive_filename=archive.name,
                  archive_sha256=digest,archive_bytes=archive.stat().st_size,
                  archived_original_files=len(members),matched_csv_sources=len(expected['sources']),
                  method='Full gzip SHA256 plus selected source hash/size comparison to frozen archived manifest',
                  scientific_execution_count=0)
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    verify(args.archive,args.package,args.output)
