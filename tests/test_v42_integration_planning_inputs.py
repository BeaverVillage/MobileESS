"""Focused issue/Actual boundary tests; no model construction or solver."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from v42_integration.planning_inputs import prepare_planning
from v42_integration.qos import TrainingStatistics


def source_fixture(folder):
    reference=folder/'REFERENCE.json';reference.write_text('[]',encoding='utf8')
    source=dict(path=str(reference),sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),bytes=2)
    rows=[];jobs={}
    for index in range(1649):
        running=index<254;external=index<44;modeled=not running or index>=150
        uid=str(index)
        row=dict(job_uid=uid,state='RUNNING' if running else 'PENDING',known_at_issue=True,
            submit_time='2025-04-30T06:00:00+00:00',elapsed_seconds=3600. if running else None,
            current_site_if_running=None if external else 's' if running else None,planning_site='s',
            planning_eligible=not external,service_slots=1 if modeled else 0,GPU_gang=2 if external and index<15 else 1,
            reference_start_if_authorized=0,reference_end=1 if modeled else 0,
            nominal_remaining_seconds=900. if modeled else 0.,V10_Q50_total_seconds=4500. if running else 900.,
            unresolved_external_source_service_end=13,remaining_service_seconds=11301.)
        rows.append(row)
        if modeled:
            jobs[uid]=SimpleNamespace(state=row['state'],gpu=row['GPU_gang'],service_slots=1,
                reference_start=0,reference_site='s')
    native=dict(day='2025-05-01',issue_time='2025-04-30T08:00:00+00:00',known_population=rows,
                reference=source,capacities={'s':1000})
    (folder/'NATIVE_INPUT_TEMPLATE_B1.json').write_text(json.dumps(native),encoding='utf8')
    return (deepcopy(native),jobs,{},SimpleNamespace(control_end=120))


def prepare(folder,data):
    return prepare_planning(folder,data,source_freeze={'files':[]},
        strict_stats=TrainingStatistics.from_records([],source_sha='empty-stats'),
        case_sha='planning-case',provider_sha='frozen-provider')


def test_all_known_external_nulls_retained_and_future_actual_file_never_read(tmp_path):
    data=source_fixture(tmp_path)
    private=tmp_path/'ACTUAL_INPUT_BUNDLE.json';private.write_text('INVALID_PRIVATE_FUTURE_A',encoding='utf8')
    first=prepare(tmp_path,data)
    private.write_text('DIFFERENT_INVALID_PRIVATE_FUTURE_B',encoding='utf8')
    second=prepare(tmp_path,data)
    assert len(first['known_receipts'])==1649
    assert len(first['planning_external_running'])==44
    assert sum(r['GPU_gang'] for r in first['planning_external_running'])==59
    assert all(first['known_receipts'][str(i)]['reference']['reference_site'] is None for i in range(44))
    assert first['qos_provider'].to_dict()==second['qos_provider'].to_dict()
    assert first['reference_sha']==second['reference_sha']
    assert first['actual_truth_reads']==first['source_reference_regeneration_calls']==0
    assert first['arguments']=={} and first['actual_gate']['status']=='INITIAL_QUEUE_UNVERIFIED'


def test_external_reference_must_have_issue_predicted_zero_dday_service(tmp_path):
    data=source_fixture(tmp_path)
    native=json.loads((tmp_path/'NATIVE_INPUT_TEMPLATE_B1.json').read_text(encoding='utf8'))
    native['known_population'][0]['unresolved_external_source_service_end']=25
    (tmp_path/'NATIVE_INPUT_TEMPLATE_B1.json').write_text(json.dumps(native),encoding='utf8')
    with pytest.raises(ValueError,match='UNRESOLVED_RUNNING_SOURCE_NOMINAL_DDAY_SERVICE_NOT_ZERO'):
        prepare(tmp_path,data)


def test_frozen_reference_bytes_not_regenerated_or_accepted_after_drift(tmp_path):
    data=source_fixture(tmp_path)
    (tmp_path/'REFERENCE.json').write_text('[1]',encoding='utf8')
    with pytest.raises(ValueError,match='ORIGINAL_FROZEN_REFERENCE_BYTES_DRIFT'):
        prepare(tmp_path,data)
