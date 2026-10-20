"""C pickle traversal, with custom protocols rejected before execution."""
from copy import deepcopy
from io import BytesIO
import pickle

_LEAVES = frozenset((str, int, float, bool, bytes, type(None), complex))
_PLAIN = _LEAVES | {dict, list}


class _NonPlain(Exception):
    pass


class _PlainPickler(pickle.Pickler):
    def reducer_override(self, value):
        # Exact builtins use the C pickler's direct opcodes. Every custom
        # reduction reaches this hook, before __reduce__ or __getstate__.
        raise _NonPlain()


def clone_physical(value, memo=None):
    if memo is not None:
        return deepcopy(value, memo)
    if type(value) in _LEAVES:
        return value
    if type(value) not in (dict, list):
        return deepcopy(value)
    buffer = BytesIO()
    writer = _PlainPickler(buffer, protocol=5)
    try:
        writer.dump(value)
        # The C traversal has visited every container. Nonempty tuples,
        # sets, bytearrays and other builtin fast paths are rejected here;
        # their original deepcopy behavior remains authoritative. The empty
        # tuple's singleton opcode is safe and deepcopy preserves it, too.
        for _, item in writer.memo.copy().values():
            kind = type(item)
            if kind not in _PLAIN and not (kind is tuple and not item):
                return deepcopy(value)
            # Physical record keys are strings. Keep deepcopy for unusual
            # keys, including NaN keys whose equality relies on identity.
            if kind is dict and any(type(key) is not str for key in item):
                return deepcopy(value)
        return pickle.loads(buffer.getvalue())
    except (_NonPlain, RecursionError, pickle.PicklingError, OverflowError):
        return deepcopy(value)
