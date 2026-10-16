from pathlib import Path

import pytest


def test_official_actual_dispatches_only_c0(monkeypatch,tmp_path):
    from v43 import may01
    from v43_corrective import compare
    (tmp_path/'V43_CURRENT_AC_PRODUCTION_CERTIFICATION_POINTER.json').write_text('{}')
    monkeypatch.setattr(may01,'DOC',tmp_path)
    monkeypatch.setattr(may01,'read',lambda path:{'certificate':{'path':'certified-ac.json'}})
    monkeypatch.setattr(may01,'verify_records',lambda records:None)
    calls=[]
    monkeypatch.setattr(compare,'run',lambda *args,**kwargs:calls.append((args,kwargs)))
    may01.actual('B0','fresh-output',reference_folder='frozen-B0')
    assert len(calls)==1
    assert calls[0][0]==('B0','fresh-output')
    assert calls[0][1]['variants']==('C0',)
    assert calls[0][1]['ac_mode']=='FAST'
    assert calls[0][1]['control_slots']==120
    assert calls[0][1]['reference_folder']=='frozen-B0'


def test_c1_only_cannot_be_dispatched(tmp_path):
    from v43_corrective.compare import run
    with pytest.raises(ValueError,match='EXPLICIT_SUPPORTED_CONTROL_VARIANTS_REQUIRED'):
        run('B0',tmp_path/'not-started',variants=('C1',))
    assert not (tmp_path/'not-started').exists()
