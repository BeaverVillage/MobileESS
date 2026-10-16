"""Strict original source receipts and finite artifact serialization."""
from pathlib import Path
import numpy as np
from v43.common import read, record, atomic


def checked(receipt):
    from v42_capacity.common import resolve
    path = Path(resolve(receipt))
    actual = record(path)
    if any(actual[k] != receipt[k] for k in ('sha256','bytes')):
        raise ValueError('V43_ACTUAL_SOURCE_DRIFT:'+str(path))
    return path


def json_value(value):
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, dict):
        return {str(k):json_value(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def write(path, value):
    atomic(path, json_value(value))
