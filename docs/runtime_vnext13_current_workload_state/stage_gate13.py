from common13 import *
def require_total():
    selection=read(ROOT/'TOTAL_MODEL_SELECTION_FREEZE.json')
    for r in selection['files']:assert sha(r['path'])==r['sha256']
    if not selection['TOTAL_RUNTIME_MODEL_VALIDATED'] or not selection['STAGE_C_AUTHORIZED'] or selection['selected_arm'] is None:
        raise RuntimeError('NOT_RUN_GATE_FAILED: no TOTAL candidate passes all required gates')
    return selection
if __name__=='__main__':require_total()
