"""Literal original R0/Q50 reference arithmetic with isolated May01 IO."""
import types
from .stage_common import *


def prepare(output):
    from v44.worker import reference
    original=reference.__wrapped__
    row=day_inputs()
    sources=[record(ROOT/p) for p in ('v44/worker.py','v43_arms/reference.py','v42_temporal/native.py')]
    # Pure reference preparation never calls a Native solver or enters the
    # original production Worker. The substitution supplies its source receipt.
    fn=types.FunctionType(original.__code__,dict(original.__globals__,
        day_inputs=lambda day:row if day==row['day'] else (_ for _ in ()).throw(ValueError('MAY01_ONLY')),
        assert_current=lambda:dict(request=dict(sources=sources))),argdefs=original.__defaults__)
    return fn(row['day'],output)
