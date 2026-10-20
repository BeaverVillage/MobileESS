import pytest
from ckt24_study.gates import admit,REQUIRED
from ckt24_study.order import verify

def test_admission_requires_every_gate_and_exact_pass():
    complete={n:dict(status='PASS') for n in REQUIRED}
    assert admit(complete,'2025-05-01')['new_Ckt24_A1_required']
    for name in REQUIRED:
        for status in ['NOT_RUN','PROVISIONAL','FAIL',None,True]:
            with pytest.raises(RuntimeError):admit({**complete,name:dict(status=status)},'2025-05-01')
    with pytest.raises(ValueError):admit(complete,'2025-05-02')
    with pytest.raises(RuntimeError):admit({},'2025-05-01')

def test_spatial_inversion_and_collapsed_axis_rejected():
    a=dict(service_id='IDC01',type='IDC',x=1,y=2,e_x=10,e_y=20)
    b=dict(service_id='IDC02',type='IDC',x=3,y=4,e_x=30,e_y=40)
    assert all(r['PASS'] for r in verify([a,b]))
    assert not all(r['PASS'] for r in verify([a,{**b,'e_x':5}]))
    assert not all(r['PASS'] for r in verify([a,{**b,'e_x':10}]))
    assert not all(r['PASS'] for r in verify([a,{**b,'e_y':1}]))

def test_equality_tolerance_never_erases_clear_source_direction():
    a=dict(service_id='IDC01',type='IDC',x=1,y=2,e_x=10,e_y=20)
    b=dict(service_id='IDC02',type='IDC',x=1.005,y=4,e_x=30,e_y=40)
    proof=verify([a,b])
    assert proof[0]['applicable'] is False
    assert proof[1]['applicable'] is True
    assert proof[1]['PASS'] is True
