import json
import pytest
from v42_svr11.hold import held


def test_stop_and_bound_hold_block_dispatch(tmp_path):
    manifest={'execution_SHA':'current'}
    assert not held(tmp_path,manifest)
    hold=tmp_path/'DISPATCH_QUIESCENCE_FOR_PLANNING_MODEL_REPAIR.json'
    hold.write_text(json.dumps(dict(root=str(tmp_path),source_SHA='current',new_dispatch_quiesced=True)))
    assert held(tmp_path,manifest)
    hold.write_text(json.dumps(dict(root=str(tmp_path),source_SHA='old',new_dispatch_quiesced=True)))
    with pytest.raises(PermissionError,match='HOLD_BINDING_DRIFT'):held(tmp_path,manifest)
    (tmp_path/'STOP_REQUEST.json').write_text('{}')
    assert held(tmp_path,manifest)
