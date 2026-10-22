"""Import the unchanged pinned original checkout only on an explicit entry."""
import sys
from . import config as c
sys.path.insert(0,str(c.SOURCE))
import v44_recovery_r047
sys.path.insert(0,str(c.PROFILE))
import equipment
# equipment imports the operational overlay path; restore the original science
# root before any lazy v42 module import, exactly as the successful old worker.
from v44.common import ROOT as PINNED_SCIENCE
sys.path.insert(0,str(PINNED_SCIENCE))
import v44_week4_execution as base
from v44 import worker,runtime
CORE_M=worker.m_stage
CORE_RUNTIME=runtime.build
