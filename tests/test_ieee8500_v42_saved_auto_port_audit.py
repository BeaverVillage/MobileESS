"""Saved finite-port evidence must reject damaged bindings and physical flags."""
import copy
import hashlib
import json

import pandas as pd
import pytest

from ieee8500_v42.common import REPORT,read
from ieee8500_v42.geometry import read_csv
from ieee8500_v42.review_selected_port_ac import audit_automatic_saved


@pytest.fixture(scope='module')
def evidence():
    folder=REPORT/'joint_selection_v3/selected_port_ac'
    current=folder/'automatic_local_audit'
    rows=pd.read_csv(current/'AUTOMATIC_PCC_LOCAL_FULL_RATING.csv')
    states=read(current/'ORIGINAL_AUTOMATIC_CONTROL_STATES.json')
    inventory=read(REPORT/'ORIGINAL_FEEDER_INVENTORY.json')
    mapping={r['location_id']:r for r in read_csv(REPORT/'joint_selection_v3/score_selection/JOINT_SERVICE_MAPPING.csv') if r['role']=='STA'}
    commands={tuple(c) for c in read(current/'PREREGISTRATION.json')['commands']}
    legacy=pd.read_csv(folder/'AUTOMATIC_FULL_RATING4_TIME.csv')
    return rows,states,inventory,mapping,commands,legacy


def test_current_384_saved_endpoints_and_original_global_archive(evidence):
    result=audit_automatic_saved(*evidence)
    assert result['rows']==384
    assert result['original_control_state_checksum_rows']==384
    assert result['original_global_archive_max_numeric_error']==0
    assert result['global_grid_PASS']==0


def test_corrupted_settled_state_cannot_keep_valid_sha(evidence):
    rows,states,*rest=evidence
    damaged=copy.deepcopy(states)
    damaged[0]['state']['taps']['feeder_rega'][1]+=0.00625
    with pytest.raises(ValueError,match='STATE_SHA_MISMATCH'):
        audit_automatic_saved(rows,damaged,*rest)


def test_self_consistent_sha_does_not_admit_new_capacitor_axis(evidence):
    rows,states,*rest=evidence
    damaged=copy.deepcopy(states)
    state=damaged[0]['state']
    state['capacitors']['invented_capacitor']=[1]
    raw=json.dumps(state,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
    damaged[0]['sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError,match='CONTROL_AXES_CHANGED'):
        audit_automatic_saved(rows,damaged,*rest)


def test_pass_flag_cannot_hide_actual_local_voltage_failure(evidence):
    rows,*rest=evidence
    damaged=rows.copy()
    damaged.loc[0,'local_voltage_max_pu']=1.06
    with pytest.raises(ValueError,match='LOCAL_HARDWARE_FLAGS'):
        audit_automatic_saved(damaged,*rest)


def test_declared_pq_error_cannot_hide_wrong_injection_sign(evidence):
    rows,*rest=evidence
    damaged=rows.copy()
    damaged.loc[0,'actual_P_kw']=5
    with pytest.raises(ValueError,match='ACTUAL_PQ_OR_BALANCED_KCL'):
        audit_automatic_saved(damaged,*rest)
