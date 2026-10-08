from types import SimpleNamespace
import pytest
from v42_a_stage_acceptance import execution as e
from v42_a_stage_acceptance.policy import DAYS

def test_no_scope_and_no_downstream():
    for day in DAYS:
        with pytest.raises(PermissionError):e.authorize(day,'P2')
    token=e._scope.set((object(),'P2',lambda:None,DAYS[0]))
    try:
        assert e.authorize(DAYS[0],'P2')==DAYS[0]
        for action in ('A2','M1','M2','ACTUAL','FRESH_AC','PLANNING_FREEZE'):
            with pytest.raises(PermissionError):e.authorize(DAYS[0],action)
        with pytest.raises(PermissionError):e.authorize(DAYS[1],'P2')
    finally:e._scope.reset(token)

def test_prestart_needs_shift_certificate(monkeypatch):
    m=SimpleNamespace(NumIntVars=1,Params=SimpleNamespace(Threads=1))
    token=e._scope.set((m,'P2',lambda:None,DAYS[0]))
    try:
        monkeypatch.setattr(e,'read',lambda p:dict(PASS=False))
        with pytest.raises(PermissionError):e.guard(m,DAYS[0])
        monkeypatch.setattr(e,'read',lambda p:dict(PASS=True))
        e.guard(m,DAYS[0])
        m.Params.Threads=2
        with pytest.raises(PermissionError):e.guard(m,DAYS[0])
    finally:e._scope.reset(token)

def test_next_day_requires_actual_may19(monkeypatch):
    m=SimpleNamespace(NumIntVars=0,Params=SimpleNamespace(Threads=1))
    token=e._scope.set((m,'PHASE_I',lambda:None,DAYS[1]))
    try:
        monkeypatch.setattr(e,'read',lambda p:dict(PASS=True,A1_accepted=False))
        with pytest.raises(PermissionError):e.guard(m,DAYS[1])
    finally:e._scope.reset(token)
