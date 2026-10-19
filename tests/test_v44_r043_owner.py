from copy import deepcopy
from unittest.mock import patch
import pytest
from v44_recovery_r043 import operations as op
from v44.common import read, record
from v44_recovery_r029.a2_cache import ownership

def fixture():
    request=read(op.CAMPAIGN/'B1_A1/2025-05-07.request.json')
    request.update(root=str(op.CAMPAIGN/'2025-05-07/B1/attempt004/A1'),case_root=str(op.CAMPAIGN/'2025-05-07/B1/attempt004'))
    request['output']=str(op.CAMPAIGN/'2025-05-07/B3/attempt002/A2/OUTPUT')
    return request

def test_original_failure_and_corrected_owner():
    r=fixture();old=deepcopy(r)
    with pytest.raises(PermissionError,match='SAME_CAMPAIGN_DATE_ACCEPTED_A1_OWNER_REQUIRED'):
        ownership(r,[dict(day='2025-05-07')],r['physical_cache_case_proof']['path'])
    fixed=op.corrected_owner(r)
    ownership(fixed,[dict(day='2025-05-07')],fixed['physical_cache_case_proof']['path'])
    assert r==old
    assert {k for k in r if r[k]!=fixed[k]}=={'root','case_root'}

@pytest.mark.parametrize('key,value',[('day','2025-05-06'),('arm','B3'),('stage','A2')])
def test_wrong_case_not_accepted(key,value):
    r=fixture();r[key]=value
    with pytest.raises(PermissionError):op.corrected_owner(r)

def test_cache_sha_gate_still_enforced():
    r=op.corrected_owner(fixture());r['_physical_cache_identity']=dict(r['_physical_cache_identity'],sha256='0'*64)
    with pytest.raises(PermissionError,match='ACCEPTED_A1_EXACT_CACHE_LOCATION_AND_SHA_REQUIRED'):
        ownership(r,[dict(day='2025-05-07')],r['physical_cache_case_proof']['path'])

def test_completed_m1_and_zero_native_a2_validated():
    old,m1=op.validate_parent()
    assert old['day']=='2025-05-07' and m1['allow_downstream']
    assert m1['Native_seconds']>0

def test_nonzero_native_failure_not_reset():
    original=op.read
    def read(path):
        value=original(path)
        if str(path).endswith('A2\\NATIVE_RUNTIME_LEDGER.json'):value=dict(value,measured_Native_Runtime=1.)
        return value
    with patch.object(op,'read',read),pytest.raises(PermissionError,match='ZERO_NATIVE'):
        op.validate_parent()
