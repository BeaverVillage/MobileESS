from copy import deepcopy
import json

import pytest

from test_v42_release_actual import observations,Probe
from test_v42_aidc_followup import current_fixture
from test_v42_integration_actual import request
from v42_integration.actual import FrozenPowerModel
from v42_integration.actual import run_actual
from v42_capacity.actual import Environment
from v42_integration.release_actual import initial_authority
from v42_integration.research_presite_contract import make_spec,ResearchPresiteProvider
from v42_integration.research_presite_actual import (ResearchReleasePolicy,ResearchReleaseController,
    ResearchCurrentAC,ObservedSourceAuthority,control_tick_timings)
from v42_integration.experimental_qos import participation_for
from v42_integration.actual_validation import record
from v42_integration.unified_contract import digest
import numpy as np


def fixture(tmp_path,*,variant='C1',scenario='R1',source_fields=None,member=True,probe=None):
    uid=next(str(n) for n in range(100) if participation_for(str(n),'E')['membership']['FLEX30']==member)
    raw=dict(job_uid=uid,submit_seconds=0,GPU_gang=1,compatible_sites=['A','B'],
        qos='normal',protected=False)
    raw.update(source_fields or {})
    path=tmp_path/'actual.json';path.write_text(json.dumps(dict(post_issue_arrivals=[raw])),encoding='utf-8')
    wan=dict(bytes_per_gpu=1000,maximum_active_transfers=1,
        paths=[dict(source='A',destination='B',links=['AB']),dict(source='B',destination='A',links=['AB'])],
        link_capacity_bytes_15min={'AB':[90000]*96})
    spec=make_spec(scenario=scenario,source_records=[record(path)],native_wan_sha=digest(wan),
        shared_sites=['A','B'],preparation_seconds=900,bandwidth_fraction=.25)
    data=ResearchPresiteProvider(spec,native_wan=wan)
    provider,old=current_fixture(basic=False)
    power=FrozenPowerModel(.1,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'FIXTURE_ONLY')
    oracle=ResearchCurrentAC(begin=0,sites=('A','B'),power_model=power,observations=observations(),
        probe=probe or Probe(),proof_records=[record(path)])
    p=ResearchReleasePolicy(old.reference,old.packet,variant=variant,oracle=oracle,
        research_provider=data,source_authority_lookup=ObservedSourceAuthority(path),
        bindings=old.bindings,expected_bindings=old.bindings,evidence_scope='NAMED_RC03',
        source_identity={'study_case_sha':'fixture'},site_authority=initial_authority(old.bindings,'fixture'))
    c=ResearchReleaseController({'A':8,'B':8},arm='B3',qos_window_provider=provider,frozen_policy=p)
    r=request(uid,source_site=None,episode_id='E',qos='normal',protected=False,
        can_prestart_place=False,q50=1800)
    return c,p,oracle,r


def choose(c,p,o,r):
    c.submit(r,0);p.observe(0,{'A':0,'B':0},c.metadata);o.observe(0,[])
    return p.select(c.metadata[r.uid],c.budgets[r.uid],0,c.reservations,reserve=False)


def test_same_research_environment_C0_initial_stay_C1_optional_improvement(tmp_path):
    choices=[];specs=[]
    for label in ('C0','C1'):
        folder=tmp_path/label;folder.mkdir()
        c,p,o,r=fixture(folder,variant=label)
        d=choose(c,p,o,r);choices.append(d['site'])
        assert p.initial[r.uid]['basic_site']=='A' and not p.initial[r.uid]['sensitivity_used']
        assert c.metadata[r.uid]['can_prestart_place'] is False
        assert r.metadata['can_prestart_place'] is False
        specs.append(p.research.spec)
    assert choices==['A','B']
    # Only fixture source paths differ; data parameters and policy semantics do not.
    for spec in specs:spec.pop('source_records')
    assert specs[0]==specs[1]


@pytest.mark.parametrize('facts',[{'can_prestart_place':False},{'data_access_forbidden':True},
    {'batch_eligible':False},{'protected':True}])
def test_explicit_source_prohibition_or_protection_always_stays(tmp_path,facts):
    c,p,o,r=fixture(tmp_path,source_fields=facts)
    decision=choose(c,p,o,r)
    assert decision['site']=='A'
    assert not p.candidate_events[-1]['candidates'][1]['feasible']


def test_outside_existing_flex_membership_has_no_research_permission(tmp_path):
    c,p,o,r=fixture(tmp_path,member=False)
    assert choose(c,p,o,r)['site']=='A'
    assert p.candidate_events[-1]['candidates'][1]['reason']=='OUTSIDE_EXISTING_FLEX30_RESEARCH_BATCH_CONTRACT'


def test_unknown_not_registered_before_observed_arrival(tmp_path):
    c,p,o,r=fixture(tmp_path)
    assert not p.research.observed
    with pytest.raises(ValueError,match='OBSERVED_REQUEST_SOURCE_PREFIX'):
        p.authority_lookup.at(dict(uid=r.uid),-1)
    assert not p.research.observed


def test_r2_transfer_commit_has_no_gpu_start_and_only_ready_later(tmp_path):
    c,p,o,r=fixture(tmp_path,scenario='R2')
    d=choose(c,p,o,r)
    assert d['action']=='QUEUE' and d['status']=='RESEARCH_DATA_PREPARATION_PENDING'
    assert d['ready_at_seconds']==1800
    assert p.research.transfer_history and not p.research.transfer_history[0]['GPU_started']
    assert c.ledger.physical(0)=={'A':0,'B':0}
    assert c.metadata[r.uid]['can_prestart_place'] is False


def test_r2_unchanged_zero_qos_budget_rejects_transfer_and_runs_basic(tmp_path):
    c,p,o,r=fixture(tmp_path,scenario='R2')
    c.submit(r,0);p.observe(0,{'A':0,'B':0},c.metadata);o.observe(0,[])
    raw=c.budgets[r.uid].to_dict();raw.update(budget_seconds=0,latest_start_seconds=0,allowed_starts_seconds=[0])
    c.budgets[r.uid]=raw
    decision=p.select(c.metadata[r.uid],raw,0,c.reservations,reserve=False)
    assert decision['site']=='A' and not p.research.transfer_history
    assert p.candidate_events[-1]['candidates'][1]['reason']=='ORIGINAL_QOS_HAS_NO_PREPARATION_DELAY_AUTHORITY'


def test_current_candidate_ac_failure_cannot_be_overridden_by_data_contract(tmp_path):
    class FailAlternative(Probe):
        def __call__(self,history,row):
            result=super().__call__(history,row)
            if row['GPU'][1]:result.update(PASS=False,status='PHYSICAL_FAIL')
            return result
    c,p,o,r=fixture(tmp_path,probe=FailAlternative())
    d=choose(c,p,o,r)
    assert d['site']=='A'
    assert 'CURRENT_CANDIDATE_AC' in p.candidate_events[-1]['candidates'][1]['reason']


def test_r2_real_fixture_event_engine_starts_only_after_ready_and_charges_budget(tmp_path):
    c,p,o,r=fixture(tmp_path,scenario='R2')
    result=run_actual({'A':8,'B':8},[r],Environment({r.uid:900}),begin=0,end=3600,
        arm='B3',qos_window_provider=c.qos,frozen_policy=p,expected_bindings=p.bindings,
        controller_class=ResearchReleaseController,power_model=o.model,weather=[{}]*4)
    row=result['queue_ledger'][0]
    assert (row['admitted_time'],row['site'])==(1800,'B')
    np.testing.assert_array_equal(result['occupancy_GPU'][:2],[[0,0],[0,0]])
    assert p.last_selection[r.uid]['research_preparation_budget_used_seconds']==1800
    assert p.last_selection[r.uid]['additional_start_delay_seconds']==1800
    assert len(p.research.transfer_history)==1
    assert not p.research.transfer_history[0]['GPU_started']
    assert control_tick_timings(result)
    assert all('wall_seconds' in row for row in control_tick_timings(result))
