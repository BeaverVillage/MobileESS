"""Allowlisted reads, ZIP-member firewall, and strict causal prediction API."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from .contracts import OUT, ROOT, FEATURES, FORBIDDEN

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def write(name, payload, *, immutable=False):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str)+'\n'
    if immutable and path.exists() and path.read_text(encoding='utf-8') != content:
        raise RuntimeError('IMMUTABLE_PROTOCOL_CHANGED:'+name)
    path.write_text(content, encoding='utf-8', newline='\n')
    return path

def member_allowed(name, *, shadow=False):
    m = re.search(r'year=(\d{4})/month=(\d{1,2})/[^/]+\.parquet$', name)
    if not m:
        return False
    ym = tuple(map(int, m.groups()))
    return (2023,8) <= ym <= ((2025,4) if shadow else (2025,3))

class ReadFirewall:
    def __init__(self, stage, allowed_files=(), allowed_roots=()):
        self.stage = stage
        self.files = {str(Path(x).resolve()).casefold() for x in allowed_files}
        self.roots = [str(Path(x).resolve()).casefold()+os.sep for x in allowed_roots]
        self.events, self.denied = [], []
        self.active = False
        self._inside = False

    def record(self, payload):
        previous=self._inside
        self._inside=True
        try:
            with (OUT/('READ_EVENTS_'+self.stage+'.jsonl')).open('a',encoding='utf-8') as f:
                f.write(json.dumps(payload,ensure_ascii=False,default=str)+'\n')
        finally:
            self._inside=previous

    def install(self):
        # Python audit hook catches builtins.open, pathlib, and common library reads.
        # Native Arrow reads are additionally routed through audited bytes streams.
        self.active = True
        sys.addaudithook(self.audit)
        return self

    def audit(self, event, args):
        if not self.active or self._inside or event != 'open' or not isinstance(args[0], (str, bytes, Path)):
            return
        self._inside = True
        try:
            path = str(Path(os.fsdecode(args[0])).resolve()).casefold()
            mode = args[1]
            writing = isinstance(mode, str) and any(c in mode for c in 'wax+')
            output = str(OUT.resolve()).casefold()+os.sep
            source = str((ROOT/'dayahead/v40j').resolve()).casefold()+os.sep
            library = any(x in path for x in ('site-packages', '\\python311\\lib\\', '\\venvs\\', '\\dependencies\\python\\', '\\__pycache__\\'))
            approved = path.startswith(output) or path.startswith(source) or path in self.files or any(path.startswith(r) for r in self.roots) or library or path in ('nul',)
            if re.search(r'2025[-_]05(?:[-_\\/]|$)|year=2025[\\/]month=0?5[\\/]|[\\/]v40i[\\/]',path):
                approved=False
            if writing and not (path.startswith(output) or '\\__pycache__\\' in path or path.endswith('.pyc')):
                approved = False
            if not approved:
                self.denied.append({'path': path, 'mode': mode})
                self.record({'decision':'DENY','path':path,'mode':mode})
                raise PermissionError('V40J_READ_FIREWALL:'+path)
            if not writing and not library:
                self.events.append({'path': path, 'kind': 'allowlisted_file'})
                self.record({'decision':'ALLOW','path':path,'kind':'allowlisted_file'})
        finally:
            self._inside = False

    def open_member(self, archive, name, *, shadow=False, metadata_only=False):
        if not member_allowed(name, shadow=shadow):
            self.denied.append({'member': name})
            raise PermissionError('V40J_MAY_OR_SHADOW_MEMBER:'+name)
        if shadow and not metadata_only:
            lock=OUT/'V40J_SELECTION_FREEZE.json'
            if not lock.exists() or json.loads(lock.read_text(encoding='utf-8')).get('winner') is None:
                raise PermissionError('V40J_SHADOW_BEFORE_WINNER')
        self.events.append({'member': name, 'kind': 'metadata' if metadata_only else 'payload'})
        self.record({'decision':'ALLOW','member':name,'kind':'metadata' if metadata_only else 'payload'})
        return archive.open(name)

    def close(self):
        self.active = False
        write('READS_'+self.stage+'.json', {'stage': self.stage, 'events': self.events, 'denied': self.denied,
              'may_payload_reads': sum(1 for e in self.events if 'member' in e and not member_allowed(e['member'], shadow=True)),
              'python_audit_and_explicit_arrow_bytes': True})

def causal_matrix(frame):
    bad = set(frame.columns) - set(FEATURES)
    if bad or set(frame.columns) & FORBIDDEN:
        raise ValueError('V40J_NONCAUSAL_OR_UNKNOWN_FEATURE:'+','.join(sorted(bad)))
    if list(frame.columns) != FEATURES:
        raise ValueError('V40J_FEATURE_ORDER')
    return frame
