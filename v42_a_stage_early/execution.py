"""Separate explicit 900s May19 LP permit; historical permits are unchanged."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import json
from v42_pr134_b1.common import read, record, sha
from .policy import OUT, DAY, POLICY

_scope = ContextVar('early_may19_exact_model', default=None)

def current():
    return _scope.get()

def verify():
    freeze = read(OUT/'SOURCE_FREEZE.json')
    if freeze.get('PASS') is not True or freeze.get('schema') != 'MAY19_EARLY_LP_900_V2':
        raise PermissionError('EARLY_SOURCE_BOUND_900_PERMIT_REQUIRED')
    if read(OUT/'EARLY_ACTIVATION_POLICY.json') != POLICY:
        raise PermissionError('EARLY_POLICY_DRIFT')
    for label in ('solver_policy','policy'):
        if record(freeze[label]['path'])!=freeze[label]:raise PermissionError('EARLY_FROZEN_POLICY_BYTE_DRIFT')
    for p, expected in freeze['execution_sources'].items():
        if sha(p) != expected: raise PermissionError('EARLY_SOURCE_DRIFT:'+p)
    for r in freeze['gate_receipts']:
        if record(r['path']) != r or read(r['path']).get('PASS') is not True:
            raise PermissionError('EARLY_GATE_DRIFT')
    return freeze

def authorize(day, action):
    if day != DAY or action not in ('OPTIMIZE','FEASIBILITY_LP'):
        raise PermissionError('EARLY_MAY19_LP_ONLY')
    return day

def guard(model, day):
    scope = current()
    if scope is None or scope[0] is not model or scope[1] != DAY or day != DAY:
        raise PermissionError('EARLY_EXACT_NATIVE_MODEL_REQUIRED')
    if model.NumIntVars != 0 or scope[2] not in ('PHASE_I','LOCAL_PRICING'):
        raise PermissionError('EARLY_LP_ONLY')
    scope[3]()  # live shared/parent reservation budget guard

@contextmanager
def native_scope(model, component, budget_check):
    verify()
    token = _scope.set((model, DAY, component, budget_check))
    try:
        guard(model, DAY)
        yield
    finally:
        _scope.reset(token)
