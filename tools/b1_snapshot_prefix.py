"""Read only the first compact snapshot of a protocol-5 state checkpoint.

Stop before the job/domain dictionaries: loading the entire historical state
can consume >10 GiB. No reconstruction, optimizer, or checkpoint mutation.
"""
import gzip
import pickle
from v42_a_stage_domain_v2.lexstage import LinearSnapshot


class _Found(BaseException):
    def __init__(self, snapshot):
        self.snapshot = snapshot


class _Prefix(pickle._Unpickler):
    dispatch = pickle._Unpickler.dispatch.copy()

    def load_build(self):
        super().load_build()
        if (len(self.stack) >= 2 and self.stack[-2] == 'compact'
                and isinstance(self.stack[-1], LinearSnapshot)):
            raise _Found(self.stack[-1])

    dispatch[pickle.BUILD[0]] = load_build


def compact_snapshot(path):
    with gzip.open(path, 'rb') as stream:
        try:
            _Prefix(stream).load()
        except _Found as found:
            return found.snapshot.require()
    raise ValueError('COMPACT_SNAPSHOT_PREFIX_NOT_FOUND')
