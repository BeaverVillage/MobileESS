"""Start the single byte-verified storage helper at campaign host logon."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r036 import operations as op

if __name__=='__main__':
    op.validate()
    op.storage_maintenance.start(op)
