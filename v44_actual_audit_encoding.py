"""Exact JSON encoding reuse for already immutable historical audit fields.

No engine state, solver result, control read, or verdict is cached here. Every
mutable input is still serialized to form its content key on every access.
"""
from collections import OrderedDict
import hashlib
import pickle

from v44_recovery_r029.immutable import FrozenDict, FrozenList
from v44_recovery_r029.current_ac_performance import ExactAuditEncoding as OriginalEncoding


class ExactImmutableEncoding(OriginalEncoding):
    def __init__(self, max_bytes=128*1024*1024):
        super().__init__(max_bytes)
        self.identity_hits = 0

    def encoded(self, row, canonical):
        immutable = type(row) in (FrozenDict, FrozenList)
        raw = None if immutable else pickle.dumps(row, protocol=5)
        key = (id(canonical), 'identity', id(row)) if immutable else (
            id(canonical), 'content', hashlib.sha256(raw).digest())
        entry = self.cache.get(key)
        if entry is not None:
            text, size, owner, encoder = entry
            if encoder is canonical and (not immutable or owner is row):
                self.cache.move_to_end(key)
                self.hits += 1
                self.identity_hits += int(immutable)
                return text
        self.misses += 1
        text = canonical(row)
        # Charge the retained immutable graph's serialized size, too. This
        # deliberately trades capacity for bounded ownership of identity keys.
        size = len(text.encode('utf-8'))
        if immutable:
            size += len(pickle.dumps(row, protocol=5))
        if size <= self.max_bytes:
            old = self.cache.pop(key, None)
            if old is not None:
                self.bytes -= old[1]
            self.cache[key] = (text, size, row if immutable else None, canonical)
            self.bytes += size
            while self.bytes > self.max_bytes:
                _, removed = self.cache.popitem(last=False)
                self.bytes -= removed[1]
        return text
