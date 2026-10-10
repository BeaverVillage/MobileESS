"""Strict JSON receipts, including explicit nonfinite diagnostic values."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np


def jsonable(value):
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return 'NaN' if math.isnan(value) else 'Infinity' if value > 0 else '-Infinity'
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.common-tmp')
    temporary.write_text(json.dumps(jsonable(value), ensure_ascii=False, indent=2,
                                   allow_nan=False) + '\n', encoding='utf-8')
    from v42_pr134_b1.common import replace_file
    replace_file(temporary, path)


def record(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
