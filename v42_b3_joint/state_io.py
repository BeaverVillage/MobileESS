"""SHA-bound, one-use source state loading with bounded compressed reads.

The loaded object can be handed to the unchanged independent verifier once.
This avoids a second full closed-state allocation while the first is live;
subsequent handoff verification must load and check the sealed file again.
"""
import errno
import gzip
import io
import pickle
from pathlib import Path

from .contracts import require


READ_CHUNK = 64 * 1024
_LOADED = object()


class _CompressedReader(io.RawIOBase):
    def __init__(self, path, *, opener=None):
        self.path = Path(path)
        self.opener = opener or (lambda: self.path.open("rb", buffering=0))
        self.stream = self.opener()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.stream.tell()

    def seek(self, offset, whence=io.SEEK_SET):
        return self.stream.seek(offset, whence)

    def readinto(self, buffer):
        position = self.stream.tell()
        for attempt in range(3):
            try:
                data = self.stream.read(min(len(buffer), READ_CHUNK))
                buffer[:len(data)] = data
                return len(data)
            except OSError as error:
                if error.errno != errno.EINVAL or attempt == 2:
                    raise
                # Only the failed raw read is retried, at the same compressed
                # offset. The complete source receipt is checked after load.
                self.stream.close()
                self.stream = self.opener()
                self.stream.seek(position)

    def close(self):
        if not self.closed:
            self.stream.close()
        super().close()


class LoadedSourceState:
    def __init__(self, path, receipt, root, state, token):
        require(token is _LOADED, "SOURCE_STATE_VERIFIED_LOAD_REQUIRED")
        self.path, self.receipt, self.root = path, dict(receipt), Path(root).resolve()
        self._state = state

    @property
    def state(self):
        require(self._state is not None, "SOURCE_STATE_ALREADY_CONSUMED")
        return self._state

    def take(self, receipt, root, checker):
        require(dict(receipt) == self.receipt and Path(root).resolve() == self.root,
                "SOURCE_STATE_READ_RECEIPT_BINDING_DRIFT")
        require(Path(checker(receipt, root)).resolve() == self.path,
                "SOURCE_STATE_READ_PATH_DRIFT")
        state = self.state
        self._state = None
        return state


def load_source_state(receipt, root, checker):
    path = Path(checker(receipt, root)).resolve()
    with _CompressedReader(path) as raw:
        with io.BufferedReader(raw, buffer_size=READ_CHUNK) as compressed:
            with gzip.GzipFile(fileobj=compressed, mode="rb") as stream:
                state = pickle.load(stream)
    require(Path(checker(receipt, root)).resolve() == path, "SOURCE_STATE_READ_PATH_DRIFT")
    return LoadedSourceState(path, receipt, root, state, _LOADED)
