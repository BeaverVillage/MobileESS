"""Fail-closed entry authorization, shared by any later Stage C/D implementation."""
from common12 import *
def require_total():
    path=ROOT/'TOTAL_MODEL_SELECTION_FREEZE.json'
    if not path.exists():raise RuntimeError('NOT_RUN_GATE_FAILED: TOTAL selection is not frozen')
    selection=read(path)
    for r in selection['files']:
        if sha(r['path'])!=r['sha256']:raise RuntimeError('NOT_RUN_GATE_FAILED: frozen evidence changed')
    if not selection['TOTAL_RUNTIME_MODEL_VALIDATED'] or not selection['STAGE_C_AUTHORIZED'] or not selection['selected_arm']:
        raise RuntimeError('NOT_RUN_GATE_FAILED: no TOTAL candidate passed all gates')
    return selection
if __name__=='__main__':require_total()
