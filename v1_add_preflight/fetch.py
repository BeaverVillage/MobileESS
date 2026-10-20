"""Fetch only official uhs2_1247 base_peak physical model.

No ratings, load multipliers, or profile samples are modified. Raw files remain
in a separate runtime tree; every response is sealed in DOWNLOAD_MANIFEST.json.
"""
import concurrent.futures as cf
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

RUNTIME = Path('D:/smartds_gso_substation2_v44_r043_runtime')
HOST = 'https://oedi-data-lake.s3.amazonaws.com/'
PREFIX = 'SMART-DS/v1.0/peak/GSO/urban-suburban/'
SUB = PREFIX + 'scenarios/base_peak/opendss/uhs2_1247/'


def fetch(key):
    path = RUNTIME / 'official' / key
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        try:
            if path.exists():
                data = path.read_bytes()
                etag = None
            else:
                with urllib.request.urlopen(HOST + key, timeout=90) as response:
                    data = response.read()
                    etag = response.headers.get('ETag')
                path.write_bytes(data)
            return dict(key=key, url=HOST + key, path=str(path), bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(), etag=etag)
        except Exception:
            if attempt == 4:
                raise
            time.sleep(1 + attempt)


def main():
    url = HOST + '?' + urllib.parse.urlencode({'list-type': '2', 'prefix': SUB})
    listing = urllib.request.urlopen(url).read()
    (RUNTIME / 'discovery/substation_listing.xml').write_bytes(listing)
    root = ET.fromstring(listing)
    assert root.find('{*}IsTruncated').text == 'false'
    keys = [e.find('{*}Key').text for e in root.findall('{*}Contents')]
    keys = [k for k in keys if '/analysis/' not in k and
            (k.endswith('.dss') or k.endswith('SMART-DS_version.txt'))]
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(fetch, keys))
    manifest = dict(dataset_version='v1.0', year='peak (static equipment)', scenario='base_peak',
                    study_inputs='Frozen IEEE123 2025-05-01 inputs and transformation; no SMART-DS annual profiles',
                    substation='uhs2_1247', files=records)
    (RUNTIME / 'DOWNLOAD_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    print('complete', len(records), 'files', sum(r['bytes'] for r in records), 'bytes', flush=True)


if __name__ == '__main__':
    main()
