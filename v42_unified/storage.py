"""D-only copies of SHA256-authorized frozen sources, without editing originals."""
import hashlib
import json
import os
import shutil
from pathlib import Path
from .audit import ROOT, write

LOCAL = ROOT/'artifacts/v42_unified'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def setup():
    if ROOT.drive.upper() != 'D:':
        raise ValueError('V42_D_DRIVE_REQUIRED')
    for folder in (ROOT/'tmp', ROOT/'cache', LOCAL):
        folder.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(ROOT/'tmp'), TMP=str(ROOT/'tmp'),
                      PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(ROOT/'cache/pycache'))
    import tempfile
    tempfile.tempdir = str(ROOT/'tmp')
    return ROOT


class FrozenStore:
    def __init__(self):
        setup()
        self.mapping = {}
        self.copies = []

    def copy(self, record):
        origin = Path(record['path'])
        key = str(origin).replace('\\', '/').lower()
        if key in self.mapping:
            target = self.mapping[key]
            if sha(target) != record['sha256']:
                raise ValueError('FROZEN_SOURCE_CONFLICT')
            return target
        # Verify BEFORE copy, then verify the D copy too.
        source = origin
        if not source.is_file():
            # Existing audited migration paths are read only.
            from v42_capacity.common import resolve
            try:
                source = resolve(record)
            except ValueError:
                recovery = ROOT/'docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json'
                found = next((r['resolved']['path'] for r in json.loads(recovery.read_text())['recovered']
                              if r['original'] == str(origin)), None)
                source = Path(found) if found else origin
        if not source.is_file() or sha(source) != record['sha256']:
            raise ValueError('FROZEN_SOURCE_IDENTITY_DRIFT:'+str(origin))
        if 'bytes' in record and source.stat().st_size != record['bytes']:
            raise ValueError('FROZEN_SOURCE_SIZE_DRIFT:'+str(origin))
        relative = origin.as_posix().replace(':', '').lstrip('/')
        target = LOCAL/'sources'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        if sha(target) != record['sha256']:
            raise ValueError('D_COPY_IDENTITY_DRIFT')
        self.mapping[key] = target
        self.copies.append(dict(original_path=str(origin), local_path=str(target),
                               sha256=record['sha256'], bytes=target.stat().st_size,
                               verified_before_and_after_copy=True))
        return target

    def collect(self, value, *, recursive_json=True, seen=None):
        seen = seen if seen is not None else set()
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                p = self.copy(value)
                if recursive_json and p.suffix.lower() == '.json' and str(p) not in seen:
                    seen.add(str(p))
                    self.collect(json.loads(p.read_text(encoding='utf-8-sig')), seen=seen)
            else:
                for v in value.values():
                    self.collect(v, recursive_json=recursive_json, seen=seen)
        elif isinstance(value, (list, tuple)):
            for v in value:
                self.collect(v, recursive_json=recursive_json, seen=seen)

    def operational_view(self, value):
        """Retarget paths only; raw input files and all scientific bytes stay frozen."""
        if isinstance(value, dict):
            return {k: self.operational_view(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.operational_view(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.operational_view(v) for v in value)
        if isinstance(value, str):
            return str(self.mapping.get(value.replace('\\', '/').lower(), value))
        return value

    def seal(self):
        result = dict(PASS=True, copies=self.copies, source_writes=0,
                      operational_path_remap_only=True, original_bytes_modified=False)
        write(LOCAL/'FROZEN_SOURCE_COPIES.json', result)
        return result
