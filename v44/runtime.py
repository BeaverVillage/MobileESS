"""Dated M core. Imports do not create a model or enter any Native scope."""
from contextlib import contextmanager
from pathlib import Path
from .common import verify,digest,NotReady
from .config import require_day
from .frozen.v43_mess.library import current_identity,load
from .frozen.v43_mess.case import build as _build


def build(payload,request,progress=None):
    require_day(request['day'])
    i=payload['identity']
    if payload['bundle']['day']!=request['day'] or i.get('day')!=request['day']:raise ValueError('DATED_FIXED_AIDC_REQUIRED')
    if request['arm']=='B2' and (i.get('arm'),i.get('stage'))!=('B0','REFERENCE'):
        raise ValueError('B2_SAME_DAY_B0_R0_Q50_ONLY')
    if request['arm']=='B3' and request['stage']=='M1' and (i.get('arm'),i.get('stage'),i.get('reused_exact_A1'))!=('B1','A1',True):
        raise ValueError('B3_REUSES_SAME_DAY_B1_A1')
    if request['stage']=='M2':
        from .stages import require_a2
        require_a2(i,request['day'])
    case=_build(payload,request,progress)
    if case.mess_stage_budget_seconds!=900.:raise ValueError('V44_JOINT_CEILING_DRIFT')
    return case
