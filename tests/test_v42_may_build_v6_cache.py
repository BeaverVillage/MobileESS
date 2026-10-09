from pathlib import Path
import pytest
from v42_pr134_b1.common import atomic,record
from v42_may_build_v6.input_cache import verify_cache_authority


def fixture(tmp_path):
    day='2025-05-23';source=tmp_path/'preflight_v6/B1'/day/'fixture/output'
    inputs=tmp_path/'inputs/B1'/day
    atomic(inputs/'NATIVE_INPUT.json',dict(day=day))
    atomic(source/'STATIC/DATA/DATA.pkl',dict(native_variables=0))
    atomic(source/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json',dict(native_variables=0))
    atomic(source/'A_PREPARE_RECEIPT.json',dict(PASS=True,day=day,arm='B1',Native_calls=0,P2_calls=0,verification={'PASS':True}))
    entry=dict(scope='CURRENT_DATE_NATIVE_ZERO_INPUTS_ONLY',folder=str(source),
        preparation=record(source/'A_PREPARE_RECEIPT.json'),model_verification={'PASS':True},
        DATA=record(source/'STATIC/DATA/DATA.pkl'),
        physical_receipt=record(source/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'),
        inputs={'NATIVE_INPUT.json':record(inputs/'NATIVE_INPUT.json')})
    manifest=tmp_path/'manifest.json';atomic(manifest,dict(input_cache_sources={'B1/'+day:entry}))
    return source,entry,dict(day=day,arm='B1',root=str(tmp_path),manifest=str(manifest),input_folder=str(inputs))


def test_only_same_date_native_zero_data_and_physical_receipts_are_admitted(tmp_path):
    source,entry,request=fixture(tmp_path)
    assert verify_cache_authority(request,source)==entry
    for field,value in [('day','2025-05-24'),('arm','B2')]:
        with pytest.raises(PermissionError):verify_cache_authority(dict(request,**{field:value}),source)


@pytest.mark.parametrize('change',[{'Native_calls':1},{'PASS':False},{'day':'2025-05-24'},{'arm':'B2'},{'P2_calls':1}])
def test_native_results_failures_other_date_and_arm_are_rejected(tmp_path,change):
    source,entry,request=fixture(tmp_path)
    prep=source/'A_PREPARE_RECEIPT.json'
    atomic(prep,{**dict(PASS=True,day=request['day'],arm='B1',Native_calls=0,P2_calls=0,verification={'PASS':True}),**change})
    entry['preparation']=record(prep)
    atomic(request['manifest'],dict(input_cache_sources={'B1/'+request['day']:entry}))
    with pytest.raises(ValueError):verify_cache_authority(request,source)


def test_cache_byte_drift_and_other_folder_are_rejected(tmp_path):
    source,entry,request=fixture(tmp_path)
    atomic(source/'STATIC/DATA/DATA.pkl',dict(changed=True))
    with pytest.raises(ValueError):verify_cache_authority(request,source)
    with pytest.raises(PermissionError):verify_cache_authority(request,tmp_path/'different/output')


def test_previous_production_attempt_is_not_a_v6_cache_source(tmp_path):
    source,entry,request=fixture(tmp_path)
    entry['folder']=str(tmp_path/'dates/B1'/request['day']/'output')
    atomic(request['manifest'],dict(input_cache_sources={'B1/'+request['day']:entry}))
    with pytest.raises(PermissionError):verify_cache_authority(request,entry['folder'])
