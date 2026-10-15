from copy import deepcopy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from v42_integration.table_v_a_control import verified_integer_lower
from v42_integration.table_v_dw import attach_global_bounds
from v42_integration.m_engine import file_record

def evidence(tmp_path):
    binding=dict(matrix_sha='matrix',domain_sha='domain');scope=dict(case_sha='case',arm='B1',stage='A1',day='2025-05-01',source_sha='source')
    context=dict(scope,stage_case_sha=scope['case_sha']);context.pop('case_sha')
    native=dict(native_execution_entered=True,status=9,native_binding=binding,stage_context=context,
        native_numeric_attributes=dict(ObjBound=.998,IsMIP=1.))
    ledger=tmp_path/'NATIVE_LEDGER.json';ledger.write_text(json.dumps(dict(calls=[native])))
    packet=dict(PASS=True,native_bound_valid=True,Global_LB=.998,binding=scope,native_binding=binding,objective_sha='objective',
        native_call=native,ledger=str(ledger),numerical_errors=[])
    raw=tmp_path/'ATTRIBUTES.json';raw.write_text(json.dumps(packet))
    result=dict(Original_Integer_Bound_Certificate=dict(packet,attributes=file_record(raw)),native_binding=binding,objective_sha='objective',
        case_sha='case',arm='B1',stage='A1',D0_source_sha='source',source_identity={},FULL_feasible=True,objective=1.)
    return result,raw,packet

def test_current_full_integer_bound_can_certify_gap_without_DW_closure(tmp_path):
    result,raw,packet=evidence(tmp_path)
    attach_global_bounds(result,dict(LB_certified=False,full_domain_pricing_complete=False))
    assert result['AIDC_DW_Global_LB'] is None
    assert result['AIDC_Integer_Global_Bound']==.998 and result['AIDC_Global_Gap']==pytest.approx(.002)

@pytest.mark.parametrize('attack',['bound_header','other_arm','other_case','other_source','restricted_matrix','LP_bound','missing_native_row'])
def test_rewritten_bound_header_cannot_override_owned_native_attributes(tmp_path,attack):
    result,raw,packet=evidence(tmp_path)
    if attack=='bound_header':packet['Global_LB']=.99999
    elif attack=='other_arm':result['arm']='B3'
    elif attack=='other_case':result['case_sha']='other'
    elif attack=='other_source':result['D0_source_sha']='other'
    elif attack=='restricted_matrix':result['native_binding']=dict(matrix_sha='restricted',domain_sha='domain')
    elif attack=='LP_bound':packet['native_call']['native_numeric_attributes']['IsMIP']=0.
    else:
        from pathlib import Path
        Path(packet['ledger']).write_text(json.dumps(dict(calls=[])))
    raw.write_text(json.dumps(packet));result['Original_Integer_Bound_Certificate']=dict(packet,attributes=file_record(raw))
    with pytest.raises(ValueError,match='SAME_ORIGINAL'):verified_integer_lower(result)
