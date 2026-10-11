"""Explicit user HOLD applies to dispatch and every restart entry point."""
from pathlib import Path
from v42_pr134_b1.common import read


def held(root,manifest):
    root=Path(root).resolve()
    if (root/'STOP_REQUEST.json').exists():return True
    path=root/'DISPATCH_QUIESCENCE_FOR_PLANNING_MODEL_REPAIR.json'
    if not path.exists():return False
    value=read(path)
    if (Path(value['root']).resolve()!=root or value['source_SHA']!=manifest['execution_SHA']):
        raise PermissionError('SVR11_GLOBAL_HOLD_BINDING_DRIFT')
    return value.get('new_dispatch_quiesced') is True
