import ast
import inspect
from copy import deepcopy
import numpy as np
import pandas as pd
import pytest
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record


def test_empty_runtime_branch_preserves_every_existing_check():
    from dayahead.v41.persistence import pre_solve as original
    from dayahead.v41r1.migration_persistence import _empty_pending_pre_solve
    old=ast.parse(inspect.getsource(original)).body[0]
    new=ast.parse(inspect.getsource(_empty_pending_pre_solve)).body[0]
    new.name=old.name
    for node in ast.walk(new):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='predictions' for t in node.targets):
            assert isinstance(node.value,ast.Call) and node.value.func.attr=='astype'
            node.value=node.value.func.value
            assert node.value.keywords[0].arg=='columns'
            node.value.keywords=[]
    assert ast.dump(old,include_attributes=False)==ast.dump(new,include_attributes=False)


def test_nonempty_runtime_keeps_existing_persistence_entrypoint(monkeypatch):
    import dayahead.v41r1.migration_persistence as revised
    import dayahead.v41.persistence as original
    monkeypatch.setattr(revised,'read',lambda p:{'PENDING_JOB_Q90_SECONDS':{'one':900.}})
    seen=[]
    monkeypatch.setattr(original,'pre_solve',lambda *a:seen.append(a) or 'same')
    assert revised.pre_solve('day','snapshot','capacity')=='same'
    assert seen==[('day','snapshot','capacity')]


def test_zero_prediction_schema_exact_roundtrip(tmp_path):
    from dayahead.v41r1.migration_persistence import RUNTIME_COLUMNS
    from dayahead.v41.persistence import table,verify_table
    frame=pd.DataFrame([],columns=list(RUNTIME_COLUMNS)).astype(RUNTIME_COLUMNS)
    receipt=table(tmp_path/'empty.parquet',frame)
    assert receipt['rows']==0 and receipt['columns']==list(RUNTIME_COLUMNS)
    pd.testing.assert_frame_equal(frame,verify_table(receipt),check_exact=True)


def test_launch_requires_full_coefficient_revalidation_after_release_check(monkeypatch):
    from dayahead.v41r1 import campaign_prepare,coefficient_prepare
    seen=[]
    monkeypatch.setattr(campaign_prepare,'verify_release',lambda:seen.append('release') or {'frozen':True})
    def reject():
        seen.append('all_31_coefficient_hashes')
        raise ValueError('COEFFICIENT_OUTPUT_HASH_DRIFT')
    monkeypatch.setattr(coefficient_prepare,'verify_manifest',reject)
    with pytest.raises(ValueError,match='OUTPUT_HASH_DRIFT'):campaign_prepare.verify_launch_authority()
    assert seen==['release','all_31_coefficient_hashes']


def coefficient_manifest_fixture(tmp_path,monkeypatch):
    import dayahead.v41r1.coefficient_prepare as gate
    import dayahead.v41.electrical as electrical
    from dayahead.v41.persistence import table
    monkeypatch.setattr(gate,'OUT',tmp_path)
    current={};rows=[]
    for day in gate.DAYS:
        folder=tmp_path/day
        identity={'identity':{'inputs':{'day':day,'V41_generation_source':{'manifest_SHA':'source'}}},'identity_SHA':day+'input'}
        current[day]=identity
        output=folder/'coefficient.json';write_json(output,{'coefficient':day})
        mapper=folder/'mapper.json'
        points=table(folder/'mapper.parquet',pd.DataFrame({'duplication_detected':[False]*96}))
        write_json(mapper,dict(status='PASS',slots=96,duplicated_group_slots=0,rows=points,
            target_day=day,stage='Planning_GENERATION',P_max_error_kW=0.,Q_max_error_kvar=0.,tolerance=1e-8))
        cert=folder/'certificate.json';outputs={'planning_coefficients':record(output)}
        write_json(cert,dict(input_identity=identity,outputs=outputs,mapper_audit=record(mapper)))
        audit=folder/'audit.json';cls='REUSED_BY_EXACT_INPUT_AND_METHOD_EQUIVALENCE'
        write_json(audit,dict(day=day,status='PASS',classification=cls,certificate=record(cert),
            generation_input_SHA=identity['identity_SHA'],generation_source_SHA='source',
            output_SHA={k:r['sha256'] for k,r in outputs.items()},mapper_audit=record(mapper),
            readback_validation={'status':'PASS','current_day_bound':True,'all_96_slots':True}))
        rows.append(dict(day=day,status='PASS',classification=cls,audit=record(audit)))
    value=dict(status='PASS',PASS=31,TOTAL=31,FAIL=0,days=rows)
    write_json(tmp_path/'V41R1_31_DAY_PLANNING_COEFFICIENT_MANIFEST.json',value)
    monkeypatch.setattr(electrical,'identity',lambda day:current[day])
    monkeypatch.setattr(electrical,'verify_generation_proof',lambda cert:None)
    return gate,value,current


@pytest.mark.parametrize('fault',[None,'missing_day','wrong_day','changed_input','output_mutation','unapproved_class'])
def test_31_day_coefficient_gate_rejects_stale_or_incomplete_authority(tmp_path,monkeypatch,fault):
    gate,value,current=coefficient_manifest_fixture(tmp_path,monkeypatch)
    if fault=='missing_day':value['days'].pop()
    if fault=='wrong_day':value['days'][1]['audit']=value['days'][0]['audit']
    if fault=='changed_input':current[gate.DAYS[-1]]['identity_SHA']='other_input'
    if fault=='output_mutation':write_json(tmp_path/gate.DAYS[-1]/'coefficient.json',{'coefficient':'another_day'})
    if fault=='unapproved_class':value['days'][-1]['classification']='HISTORICAL_READY'
    write_json(tmp_path/'V41R1_31_DAY_PLANNING_COEFFICIENT_MANIFEST.json',value)
    if fault is None:assert gate.verify_manifest()['PASS']==31
    else:
        with pytest.raises(ValueError):gate.verify_manifest()
