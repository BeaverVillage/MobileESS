"""Real frozen May01 reference arithmetic; Native0, no engine construction."""
import numpy as np
import pytest
from ast import literal_eval
from copy import deepcopy

from v43_actual.case import accepted
from v43_arms.reference import project


def test_original_native_r0_q50_reference_preserves_roster_and_initial_sites():
    _,_,native,_,_=accepted()
    sites,caps,known,anon,selected,x,carry,cons=project(native)
    assert len(selected)==1499 and cons['PASS']
    assert float(known.sum()/4)==5759.75
    assert np.all(known+anon<=caps+1e-9)
    raw={r['job_uid']:r for r in native['known_population']}
    for uid,option in selected.items():
        row=raw[uid]
        assert option['initial_site']==row['planning_site']
        assert option['start']==row['reference_start_if_authorized']
        assert option['segments'][0][2]-option['start']==row['service_slots']
    for h in range(24):
        assert abs(sum(v for k,v in x.items() if literal_eval(k)[0]==h)+carry[str(h)]-native['C0_Q50'][h])<1e-8


def test_reference_rejects_changed_original_site():
    native=deepcopy(accepted()[2]);row=next(r for r in native['known_population'] if r['service_slots']>0)
    row['planning_site']='AIDC01' if row['planning_site']!='AIDC01' else 'AIDC02'
    with pytest.raises(ValueError,match='R0_SITE_START'):project(native)
