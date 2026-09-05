"""Targeted authority/admission regressions; no campaign or optimizer execution."""
import json
import os
from types import FunctionType
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

if os.environ.get("MOBILEESS_V39K_LIVE_TESTS") != "1":
    pytest.skip(
        "requires the sealed V39K staging tree and live production authority",
        allow_module_level=True,
    )

from dayahead.tools import integrate_v39k_fallback as k


def hashes():
    before=k.read(k.ROOT/'V39K_PREINTEGRATION_LIVE_SNAPSHOT.json')['all_124_DA_freeze_SHA256']
    after=k.read(k.STAGE/k.REL/'V39K_PRODUCTION_INTEGRATION_AUTHORITY.json')['DA_freeze_file_SHA256']
    return before,after


def test_exact_eight_changes_and_no_unrelated_changes():
    before,after=hashes()
    assert len(k.check_changed_cases(before,after))==8
    assert all(before[k.fname('2025-05-17',c)]==after[k.fname('2025-05-17',c)] for c in k.CASES)


@pytest.mark.parametrize('kind',['extra','missing','unchanged_target'])
def test_manifest_fails_closed(kind):
    before,after=hashes();after=dict(after)
    if kind=='extra':after[k.fname('2025-05-17','B1')]='changed'
    if kind=='missing':after.pop(k.fname('2025-05-01','B0'))
    if kind=='unchanged_target':after[k.fname('2025-05-23','B1')]=before[k.fname('2025-05-23','B1')]
    with pytest.raises(AssertionError):k.check_changed_cases(before,after)


@pytest.mark.parametrize('day',k.DAYS)
def test_whole_original_witness_and_count(day):
    cert=k.read(k.STAGE/k.REL/'days'/day/'V39K_FALLBACK_CERTIFICATE.json')
    assert cert['status']=='PASS' and cert['migration_count']==k.COUNTS[day]
    for case in ('B1','B3'):
        f=k.decision(k.STAGE/k.FULL/k.fname(day,case));d=f['decision']
        original=k.decision(k.LIVE/k.CLOSE/'before_refreeze'/k.fname(day,case))['decision']
        assert {key:value for key,value in d.items() if key!='temporal_repair_authority'}==original
        assert sum(r.get('migration_selected',False) for r in d['AIDC_assignments'])==k.COUNTS[day]
        assert not d['temporal_repair_authority']['TEMPORAL_REPAIR_USED']
        assert k.loader(day,case).fingerprints['V39E_DA_decision_SHA256']==f['DA_decision_SHA256']
        rw=k.decision(k.LIVE/k.FULL/k.fname(day,'B0'))['decision']
        assert d['common_initial_state_SHA256']==rw['common_initial_state_SHA256']
        assert d['common_initial_RUNNING_AIDC_state']==rw['common_initial_RUNNING_AIDC_state']
        schedule={r['job_id']:r for r in d['temporal_schedule']}
        expected={uid for uid,r in schedule.items() if r['scheduled_start_slot']<120 and r['scheduled_end_slot']>24}
        assert {r['job_uid'] for r in d['AIDC_assignments']}==expected
        for r in d['AIDC_assignments']:
            job=schedule[r['job_uid']]
            assert r['requested_GPU']==job['requested_gpus']
            assert r['active_start_slot']==max(0,job['scheduled_start_slot']-24)
            assert r['active_end_slot']==min(96,job['scheduled_end_slot']-24)


@pytest.mark.parametrize('day',k.DAYS)
def test_pcc_from_frozen_c1_and_same_day_forecast(day):
    from dayahead.v39a.power import site_pcc_power
    d=k.decision(k.STAGE/k.FULL/k.fname(day,'B1'))['decision']
    it=pd.DataFrame(d['site_IT_power_trajectory'])
    actual=site_pcc_power(k.LIVE,day,it).sort_values(['slot','AIDC'])
    expected=pd.DataFrame(d['site_PCC_power_trajectory']).sort_values(['slot','AIDC'])
    for field in ['PCC_P_kW','PCC_Q_kvar']:
        assert np.allclose(actual[field],expected[field],atol=1e-8,rtol=0)


def test_loader_rejects_modified_decision_without_new_digest(tmp_path):
    f=k.read(k.STAGE/k.FULL/k.fname('2025-05-23','B1'))
    f['decision']['AIDC_assignments'][0]['requested_GPU']+=1
    p=tmp_path/'bad.json';p.write_text(json.dumps(f))
    ns=dict(k.adapter.build_day.__globals__);ns['freeze_path']=lambda *args:p
    loader=FunctionType(k.adapter.build_day.__code__,ns)
    with pytest.raises(RuntimeError,match='SHA_MISMATCH'):loader(k.LIVE,'2025-05-23','B1')


def test_dynamic_gate_hold_release_and_incomplete_fail_closed(tmp_path):
    ns={};source=(k.LIVE/'dayahead/tools/v39h_terminal_launch_gate.py').read_text();exec(compile(source,'gate','exec'),ns)
    path=tmp_path/ns['GATE'];path.parent.mkdir(parents=True)
    gate=k.read(k.LIVE/k.GATE)
    for d in k.DAYS:gate['dates'][d]['release']=False
    path.write_text(json.dumps(gate))
    assert all(not ns['admission'](tmp_path,d)['release'] for d in k.DAYS)
    assert all(ns['admission'](tmp_path,d)['release'] for d in k.AXIS if d not in k.DAYS)
    for d in k.DAYS:gate['dates'][d]['release']=True
    path.write_text(json.dumps(gate))
    assert all(ns['admission'](tmp_path,d)['release'] for d in k.DAYS)
    gate['audit_complete']=False;path.write_text(json.dumps(gate))
    assert all(not ns['admission'](tmp_path,d)['release'] for d in k.DAYS)
    path.unlink()
    assert all(not ns['admission'](tmp_path,d)['release'] for d in k.DAYS)


def test_forbidden_optimizer_constructors_are_blocked():
    with pytest.raises(AssertionError,match='FORBIDDEN'):k.gp.Model()
    with pytest.raises(AssertionError,match='FORBIDDEN'):k.gp.Env()


def test_certified_composition_105():
    total=0
    for day in k.AXIS:
        d=k.decision(k.resolve(k.FULL/k.fname(day,'B1')))['decision']
        total+=sum(r.get('migration_selected',False) for r in d['AIDC_assignments'])
    assert total==105


def test_actual_monitor_is_distinguished_from_query_helper():
    before=k.read(k.ROOT/'V39K_PREINTEGRATION_LIVE_SNAPSHOT.json')
    found=[r['ProcessId'] for r in before['processes'] if k.is_monitor_process(r)]
    assert found==[42504]
    assert not k.is_monitor_process({'CommandLine':'powershell -NoProfile -Command "Get-CimInstance | Where-Object monitor_v39e_may_campaign.ps1"'})
