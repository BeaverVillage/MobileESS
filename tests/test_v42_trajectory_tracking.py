"""New tracking contracts on named two-site equations; not May01 evidence."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import hashlib,subprocess
import numpy as np
import pytest

from v42_integration.trajectory_tracking import (TrackingReference,TrajectoryTrackingPolicy,
    TrackingJobEventController,service_integral,CONTRACT)
from v42_integration.actual import run_actual,FrozenPowerModel
from v42_integration.policy import ReservationLedger,digest
from v42_integration.reservation_state import ContractReservationLedger
from v42_capacity.actual import Environment
from test_v42_experimental_control import research_provider,metadata
from test_v42_known_unknown_contract import participant
from test_v42_integration_sensitivity_policy import fixture
from test_v42_integration_actual import request,capability

CONTRACTS=('KNOWN_SCHEDULE_IMMUTABLE','UNKNOWN_TRACKING_ONLY_AFTER_SUBMISSION','NO_FUTURE_JOB_LEAKAGE',
 'NO_ONLINE_GLOBAL_OPTIMIZE','PLANNING_TARGET_SHA_IMMUTABLE','TRACKING_RATIO_INITIAL_ZERO_SAFE',
 'GPUH_UNITS_AND_SERVICE_INTEGRAL','NO_DOUBLE_COUNT_KNOWN_UNKNOWN','ALL_COMPATIBLE_SITES_EVALUATED',
 'TIME_SHIFT_QOS_BUDGET_PRESERVED','PREPLACE_SOURCE_AUTHORITY_REQUIRED','CHECKPOINT_MIGRATION_PHYSICAL_GUARD',
 'NO_UNAUTHORIZED_MIGRATION','NO_RESERVATION_OVERBOOKING','NO_RUNTIME_FUTURE_LOOKAHEAD',
 'ACTUAL_C1_POWER_FROM_OCCUPANCY','LEGACY_FIXED_MODE_UNCHANGED','SAME_PLANNING_C0_C1_C2',
 'TRACKING_GRID_HARD_CONSTRAINTS','TRACKING_NO_FORCED_TARGET_DEMAND','C2_C3_PREPLACE_ABLATION',
 'PARTIAL_CANARY_NOT_FULL96_CERTIFICATION')


def example(*,preplace=True,basic=False,voltage_slope=0):
    provider=research_provider();job,r=participant(provider)
    packet=fixture(profile='placement',voltage_slope=voltage_slope)[0]
    packet.bindings=dict(packet.bindings,qos_sha=provider.stats.sha,case_sha=provider.case_sha)
    known=np.zeros((96,2));known[:,0]=1
    unknown=np.zeros((96,2));unknown[:,1]=1
    ref=TrackingReference(known,unknown,known+unknown,known+unknown,
        (known+unknown)*np.tan(np.arccos(.95)),sites=packet.sites,begin=0,
        commands={'K':dict(site='A',start_seconds=900)},identity={'fixture':True})
    policy=TrajectoryTrackingPolicy(ref,packet,bindings=packet.bindings,preplace=preplace,basic=basic)
    m=metadata(provider,job,r)
    policy.observe(0,{'A':0,'B':0},{m['uid']:m})
    return provider,job,r,policy,m


def replay(*,preplace=True,basic=False):
    provider,job,r,p,m=example(preplace=preplace,basic=basic)
    # Fresh provider; no fixture receipt gets shared across counterfactuals.
    provider=research_provider()
    u=request(job.uid,q50=900,qos='UNCONFIRMED',protected=None,batch_eligible=None,
        partition='',requested_walltime_seconds=None,representation_starts_seconds=tuple(range(0,86400,900)))
    power=FrozenPowerModel(.1,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'TOY_C1')
    out=run_actual({'A':8,'B':8},[u],Environment({u.uid:1000}),arm='B1',qos_window_provider=provider,
        frozen_policy=p,controller_class=TrackingJobEventController,known_schedule=p.reference.commands,
        begin=0,end=3600,power_model=power,weather=[{}]*4,expected_bindings=p.bindings)
    return out


@pytest.mark.parametrize('contract',CONTRACTS,ids=CONTRACTS)
def test_tracking_contract(contract,monkeypatch):
    provider,job,r,p,m=example();ledger=ReservationLedger({'A':8,'B':8})
    if contract=='KNOWN_SCHEDULE_IMMUTABLE':
        c=TrackingJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider,
            frozen_policy=p,known_schedule=p.reference.commands)
        c.known_schedule['K']['site']='B'
        with pytest.raises(ValueError,match='KNOWN_SCHEDULE_DRIFT'):c.admit(0)
        with pytest.raises(ValueError,match='KNOWN_NEVER'):p.select(dict(m,origin_unknown=False),r,0,ledger)
    elif contract=='UNKNOWN_TRACKING_ONLY_AFTER_SUBMISSION':
        d=p.select(dict(m,submit_seconds=1),r,0,ledger)
        assert d['action']=='QUEUE' and not p.assignments
    elif contract in ('NO_FUTURE_JOB_LEAKAGE','NO_RUNTIME_FUTURE_LOOKAHEAD'):
        for key in ('future_job_uid','actual_duration_seconds','completion_time'):
            with pytest.raises(ValueError):p.select(dict(m,**{key:42}),r,0,ledger)
    elif contract=='NO_ONLINE_GLOBAL_OPTIMIZE':
        monkeypatch.setattr(p.packet,'evaluate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('global horizon')))
        assert not p.lookup_only and p.controller_contract==CONTRACT
        assert p.select(m,r,0,ledger)['online_global_optimizer_calls']==0
    elif contract=='PLANNING_TARGET_SHA_IMMUTABLE':
        original=p.reference.sha
        with pytest.raises(ValueError):p.reference.arrays['G_Total_Plan'][0,0]=99
        p.reference.identity['fixture']=False
        with pytest.raises(ValueError,match='TARGET_SHA_DRIFT'):p.reference.require_immutable()
        assert p.reference.sha==original
    elif contract=='TRACKING_RATIO_INITIAL_ZERO_SAFE':
        d=p.select(m,r,0,ledger)
        assert np.isfinite(d['tracking']['deficit']) and d['site']=='B'
    elif contract=='GPUH_UNITS_AND_SERVICE_INTEGRAL':
        a=service_integral(('A','B'),[dict(resource='gpu:A',begin=300,end=1500,quantity=3)],0)
        assert a[0,0]==2 and a[1,0]==2 and a.sum()/4==1
    elif contract=='NO_DOUBLE_COUNT_KNOWN_UNKNOWN':
        owner=SimpleNamespace(known_schedule={'K':dict(site='A',protected_segments=[dict(resource='gpu:A',begin=0,end=900,quantity=4)])},metadata={})
        l=ContractReservationLedger(owner,capacities={'A':8,'B':8})
        l.reserve('K',[dict(resource='gpu:A',begin=0,end=900,quantity=4)])
        l.reserve('U',[dict(resource='gpu:B',begin=0,end=900,quantity=2)])
        future,known=p._public_future(l,'X')
        assert future[0,0]==known[0,0]==4 and future[0,1]==2
    elif contract=='ALL_COMPATIBLE_SITES_EVALUATED':
        d=p.select(m,r,0,ledger,reserve=False)
        # Every site either yields feasible candidates or explicit vetoes.
        assert d['candidate_count']>=2
        d=p.select(dict(m,can_prestart_place=False),r,0,ledger,reserve=False)
        assert any(x['site']=='B' for x in d['rejected_candidates'])
    elif contract=='TIME_SHIFT_QOS_BUDGET_PRESERVED':
        m['additional_start_delay_seconds']=r.budget_seconds
        m['cumulative_migration_interruption_seconds']=900
        before=digest(r.to_dict());d=p.select(m,r,0,ledger)
        assert d['action']=='QUEUE' and digest(r.to_dict())==before
    elif contract=='PREPLACE_SOURCE_AUTHORITY_REQUIRED':
        d=p.select(dict(m,can_prestart_place=False),r,0,ledger)
        assert d['site']=='A'
    elif contract in ('CHECKPOINT_MIGRATION_PHYSICAL_GUARD','NO_UNAUTHORIZED_MIGRATION'):
        m.update(state='RUNNING',current_site='A',accumulated_compute_seconds=1800,t50_seconds=5400,
                 Can_Checkpoint_Migrate=contract!='NO_UNAUTHORIZED_MIGRATION',migration_capability=capability())
        p.observe(1800,{'A':1,'B':8},{m['uid']:m})
        ledger.retain_running('other','B',1800,9000,8)
        d=p.select_migration(m,r,1800,ledger,checkpoint_at=1800)
        assert d['action']=='STAY'
        assert ledger.reservations['other']['status']=='ACTIVE'
    elif contract=='NO_RESERVATION_OVERBOOKING':
        ledger.reserve('peer',[dict(resource='gpu:B',begin=0,end=5400,quantity=8)])
        before=deepcopy(ledger.reservations['peer'])
        d=p.select(m,r,0,ledger)
        assert d['action']=='QUEUE' or d['site']=='A'
        assert ledger.reservations['peer']==before
    elif contract=='ACTUAL_C1_POWER_FROM_OCCUPANCY':
        out=replay();physical=out['physical']
        np.testing.assert_allclose(physical['IT_kw'],.8+out['occupancy_GPU'])
        assert out['receipt']['actual_power_recomputed'] and not out['receipt']['planning_power_copied']
        assert not np.array_equal(physical['PCC_P_kw'],p.reference.arrays['PCC_P_Plan'][:4])
    elif contract in ('LEGACY_FIXED_MODE_UNCHANGED','PARTIAL_CANARY_NOT_FULL96_CERTIFICATION'):
        root=Path(__file__).resolve().parents[1]
        for name in ('actual.py','actual_validation.py','coordinator.py','experimental_actual.py'):
            assert (root/'v42_integration'/name).read_bytes()==subprocess.check_output([
                'git','show','7f1f92308dc24096933b39dfe0666ee21089612a:v42_integration/'+name],cwd=root)
    elif contract=='SAME_PLANNING_C0_C1_C2':
        one=replay();replay(basic=True);two=replay()
        np.testing.assert_array_equal(one['occupancy_GPU'],two['occupancy_GPU'])
        assert one['carryout']['controller']['tracking_state']['Known_schedule_sha']==digest(p.reference.commands)
        assert one['carryout']['controller']['tracking_state']['target_sha']==p.reference.sha
    elif contract=='TRACKING_GRID_HARD_CONSTRAINTS':
        provider,job,r,p,m=example(voltage_slope=2)
        p.observe(0,{'A':0,'B':1},{m['uid']:m})
        ledger.retain_running('bg','B',0,86400,1)
        d=p.select(m,r,0,ledger)
        assert d['action']=='QUEUE' or d['site']=='A'
        assert any('VOLTAGE' in x['reason'] for x in d['rejected_candidates'])
    elif contract=='TRACKING_NO_FORCED_TARGET_DEMAND':
        out=run_actual({'A':8,'B':8},[],Environment({}),arm='B1',qos_window_provider=provider,
            frozen_policy=p,controller_class=TrackingJobEventController,begin=0,end=3600)
        assert out['occupancy_GPU'].sum()==0 and out['receipt']['submitted_jobs']==0
    elif contract=='C2_C3_PREPLACE_ABLATION':
        a=replay();b=replay(preplace=False)
        assert a['queue_ledger'][0]['site']=='B' and b['queue_ledger'][0]['site']=='A'
        assert a['carryout']['controller']['tracking_state']['Known_schedule_sha']==b['carryout']['controller']['tracking_state']['Known_schedule_sha']


def test_migration_nominal_volume_excludes_transfer_and_restart_gpu_holds():
    provider,job,r,p,m=example()
    job=replace(job,t50_seconds=5400)
    provider=research_provider();r=provider.issue(job);m=metadata(provider,job,r)
    m.update(state='RUNNING',current_site='A',accumulated_compute_seconds=1800,
        Can_Checkpoint_Migrate=True,migration_capability=capability())
    p.observe(1800,{'A':1,'B':0},{m['uid']:m})
    ledger=ReservationLedger({'A':8,'B':8},wan_capacities={'AB':100})
    decision=p.select_migration(m,r,1800,ledger,checkpoint_at=1800)
    assert decision['action']=='CHECKPOINT_MIGRATE'
    assert p.assignments[m['uid']].sum()==pytest.approx(1.)
