"""Explicit block-coordinate voltage authorities; Actual is separate."""
from dataclasses import dataclass,asdict
from enum import Enum
from .contracts import digest,require

class Stage(str,Enum):
    A1='A1'
    M1='M1'
    A2='A2'
    M2='M2'
    ACTUAL='Actual'

@dataclass(frozen=True)
class Voltage:
    kind:str
    lower_pu:float
    upper_pu:float
    lower_squared:float
    upper_squared:float

A1_BOOTSTRAP_VMIN_PU=.95
A1_BOOTSTRAP_VMAX_PU=1.05
ROBUST_PLANNING_VMIN_PU=.955
ROBUST_PLANNING_VMAX_PU=1.045
ACTUAL_VMIN_PU=.95
ACTUAL_VMAX_PU=1.05
A1_BOOTSTRAP=Voltage('A1_BOOTSTRAP',.95,1.05,.9025,1.1025)
ROBUST_PLANNING=Voltage('ROBUST_PLANNING',.955,1.045,.912025,1.092025)
ACTUAL=Voltage('ACTUAL_PHYSICAL',.95,1.05,.9025,1.1025)
_MAPPING={Stage.A1:A1_BOOTSTRAP,Stage.M1:ROBUST_PLANNING,Stage.A2:ROBUST_PLANNING,Stage.M2:ROBUST_PLANNING,Stage.ACTUAL:ACTUAL}

def voltage_for(stage):
    require(isinstance(stage,Stage),'VOLTAGE_STAGE_REQUIRED')
    return _MAPPING[stage]

def authority(stage=Stage.M1):
    v=voltage_for(stage)
    return dict(asdict(v),stage=stage.value,fallback_allowed=False,
                stages=[s.value for s,vv in _MAPPING.items() if vv==v],
                Actual_lower_pu=ACTUAL_VMIN_PU,Actual_upper_pu=ACTUAL_VMAX_PU)

def authority_sha(stage=Stage.M1):return digest(authority(stage))

def require_planning(lower,upper,stage):
    v=voltage_for(stage)
    require(stage in (Stage.A1,Stage.M1,Stage.A2,Stage.M2),'ACTUAL_AUTHORITY_NOT_PLANNING')
    require((lower,upper)==(v.lower_squared,v.upper_squared),'PLANNING_VOLTAGE_AUTHORITY_MISMATCH')

# Historical robust names retain their numeric meaning, never infer A1 authority.
PLANNING_LOWER_PU=ROBUST_PLANNING_VMIN_PU
PLANNING_UPPER_PU=ROBUST_PLANNING_VMAX_PU
PLANNING_LOWER_SQUARED=ROBUST_PLANNING.lower_squared
PLANNING_UPPER_SQUARED=ROBUST_PLANNING.upper_squared
ACTUAL_LOWER_PU=ACTUAL_VMIN_PU
ACTUAL_UPPER_PU=ACTUAL_VMAX_PU
