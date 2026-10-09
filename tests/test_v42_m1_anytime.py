"""Independent time/certificate/adaptation attacks, all Native=0."""
from fractions import Fraction as F
import pytest
from v42_m1_anytime.core import schedule_choice,THRESHOLDS,PARAMETERS,BASE,CASE
from v42_m1_anytime.algorithms import mix_duals,RADII,LOOKBACK
from v42_m1_anytime.runner import plan

def test_no_fixed_gap_or_memory_stop():
    p=plan()
    assert p['fixed_Global_Gap_stop'] is None
    assert p['Native_ceiling_seconds']==5400 and p['Native_wall_cutoff_seconds']==4500
    assert p['final_wall_ceiling_seconds']==5400 and p['final_verification_reserve_seconds']==900
    assert p['MemLimit'] is None and p['SoftMemLimit'] is None
    assert PARAMETERS['MIPGap']==.005 and PARAMETERS['Threads']==1

@pytest.mark.parametrize('iteration,expected',list(enumerate(('U1','U2','U3','U4','L1','L2','L3','L4'))))
def test_all_registered_pilots_are_explored(iteration,expected):
    assert schedule_choice([],iteration,100)[0]==expected

def test_certified_efficiency_not_native_objective_selects_method():
    h=[dict(method='U1',wall_seconds=200,certified_gain=0,native_improvement=.3),
       dict(method='U2',wall_seconds=20,certified_gain=.002,native_improvement=0)]
    assert schedule_choice(h,9,700)[0]=='U2'

def test_no_recent_gain_diversifies_instead_of_spending_forever_on_same_arm():
    h=[dict(method='U1',wall_seconds=30,certified_gain=0)]*10
    k,a=schedule_choice(h,11,1200)
    assert k=='U2' and 'DIVERSIFY' in a['reason']

@pytest.mark.parametrize('weight',['0','1/8','1/4','1/2','1'])
def test_rational_stabilization_preserves_signed_original_duals(weight):
    old={'0':'-1/3','1':'2/7','2':'3/5'};new={'0':'-9/2','1':'1/13','2':'-2/3'}
    mixed=mix_duals(old,new,weight);a=F(weight)
    assert all(F(mixed[k])==(1-a)*F(old[k])+a*F(new[k]) for k in old)
    assert F(mixed['0'])<0 and F(mixed['1'])>0

@pytest.mark.parametrize('weight',['-1/8','9/8'])
def test_extrapolated_duals_are_not_mislabeled_stabilized_convex_prices(weight):
    with pytest.raises(ValueError,match='CONVEX'):mix_duals({'0':'-1'},{'0':'-2'},weight)

def test_thresholds_are_first_passage_measurements_not_stops():
    assert tuple(float(t) for t in THRESHOLDS)==(4,3.5,3,2.5,2,1.5,1,.5)
    assert plan()['fixed_Global_Gap_stop'] is None and len(RADII)>1 and len(LOOKBACK)>1

def test_source_authority_is_completed_same_case_not_may12():
    assert BASE=='e26790e9f10217fb8f5a3cecddb1e578b879efb7'
    assert CASE=='cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a'

def test_lb_retry_caps_remain_bounded():
    h=[]
    for k,n in plan()['LB_max_passes'].items():h += [dict(method=k,certified_gain=1,wall_seconds=1)]*n
    assert schedule_choice(h,9,2000)[0].startswith('U')

@pytest.fixture
def frontier(tmp_path):
    from v42_m1_anytime.core import Frontier,write
    from v42_unified.storage import sha
    now=[0.]
    class FakeLedger:
        started=0.
        def snapshot(self):return dict(Native_Runtime=0,Work=0)
    lb=tmp_path/'lb.json';ub=tmp_path/'ub.json'
    write(lb,dict(PASS=True,case_sha=CASE,exact_Global_LB='9/10'))
    write(ub,dict(PASS=True,case_sha=CASE,exact_Global_UB='1'))
    f=Frontier(tmp_path,FakeLedger(),'9/10','1',lb,ub,clock=lambda:now[0])
    return f,now,tmp_path

def test_callback_discovery_is_never_backdated_as_first_certificate(frontier):
    from v42_m1_anytime.core import write
    from v42_unified.storage import sha
    f,now,path=frontier;now[0]=600
    cert=dict(PASS=True,case_sha=CASE,exact_Global_LB='97/100');packet=path/'fresh.json';write(packet,cert)
    assert f.publish('LB','97/100',cert,packet,sha(packet),discovery=120)
    assert f.passages['3']['actual_certificate_completion_seconds']==600
    assert f.passages['3']['retrospectively_validated_candidate_discovery_seconds']==120
    assert f.passages['3']['wall_minutes']==10

def test_invalid_bracket_cannot_corrupt_live_certified_state(frontier):
    from v42_m1_anytime.core import write
    from v42_unified.storage import sha
    f,now,path=frontier;cert=dict(PASS=True,case_sha=CASE,exact_Global_LB='2');packet=path/'bad.json';write(packet,cert)
    with pytest.raises(ValueError,match='INCONSISTENT'):f.publish('LB','2',cert,packet,sha(packet))
    assert f.lb==F('9/10') and f.ub==1 and len(f.events)==1

def test_packet_hash_cannot_be_replaced_by_metadata_pass(frontier):
    from v42_m1_anytime.core import write
    f,now,path=frontier;cert=dict(PASS=True,case_sha=CASE,exact_Global_LB='19/20');packet=path/'stale.json';write(packet,cert)
    with pytest.raises(ValueError,match='PACKET'):f.publish('LB','19/20',cert,packet,'0'*64)
    assert len(f.events)==1

def test_checkpoint_uses_only_then_certified_state(frontier):
    f,now,path=frontier;now[0]=600;f.algorithm='UB_SOLVING_UNCERTIFIED_CALLBACK'
    f.checkpoint(600)
    assert f.checkpoints[-1]['certified_gap_percent']==10
    assert f.checkpoints[-1]['exact_LB']=='9/10' and f.checkpoints[-1]['exact_UB']=='1'

def test_weaker_same_case_bound_never_replaces_best(frontier):
    f,now,path=frontier
    assert not f.publish('LB','4/5',dict(PASS=True,case_sha=CASE),path/'absent','fake')
    assert f.lb==F('9/10') and len(f.events)==1


def test_ledger_cost_accepts_original_rmp_track_keyword_without_solver(tmp_path,monkeypatch):
    from v42_m1_anytime import core
    from v42_m1_anytime.core import Ledger,read
    monkeypatch.setattr(core,'RUNTIME',tmp_path)
    now=[10.]
    ledger=Ledger(tmp_path/'NATIVE_RUNTIME_LEDGER.json',0.,clock=lambda:now[0])
    with ledger.cost('RMP_model_build','ONE_RESTRICTED_MASTER',track='RMP'):
        now[0]=14.
    record=read(ledger.path)
    assert record['costs'][0]['track']=='RMP'
    assert record['costs'][0]['wall_seconds']==4.
    assert record['Native_Runtime_sum']==0 and record['calls']==[]


@pytest.fixture
def published_timeline(tmp_path,monkeypatch):
    from v42_m1_anytime import publish,core
    from v42_unified.storage import sha
    monkeypatch.setattr(publish,'REPORTS',tmp_path)
    monkeypatch.setattr(publish,'packet',lambda name:tmp_path/name)
    core.write(tmp_path/'lb0.json',dict(PASS=True,case_sha=CASE,exact_bound='9/10'))
    core.write(tmp_path/'lb1.json',dict(PASS=True,case_sha=CASE,exact_Global_LB='49/50'))
    core.write(tmp_path/'ub.json',dict(PASS=True,case_sha=CASE,exact_Global_UB='1'))
    def event(t,lb,file):
        return dict(case_sha=CASE,actual_certificate_completion_time=t,wall_seconds=t,
            retrospectively_validated_candidate_discovery_time=max(0,t-5),exact_LB=lb,exact_UB='1',exact_gap=str(1-F(lb)),
            LB_certificate_path=file,UB_certificate_path='ub.json',LB_certificate_sha256=sha(tmp_path/file),UB_certificate_sha256=sha(tmp_path/'ub.json'))
    events=[event(0,'9/10','lb0.json'),event(20,'49/50','lb1.json')]
    checkpoints=[dict(actual_snapshot_wall_seconds=10,exact_LB='9/10',exact_UB='1',exact_gap='1/10'),
                 dict(actual_snapshot_wall_seconds=25,exact_LB='49/50',exact_UB='1',exact_gap='1/50')]
    passages=[dict(threshold_percent=3,status='REACHED',actual_certificate_completion_seconds=20),
              dict(threshold_percent=1,status='NOT_REACHED',actual_certificate_completion_seconds='')]
    core.table(tmp_path/'FRONTIER_EVENTS.csv',events)
    core.table(tmp_path/'FRONTIER_CHECKPOINTS.csv',checkpoints)
    core.table(tmp_path/'GAP_FIRST_PASSAGE_TIMES.csv',passages)
    return publish,core,tmp_path,events,checkpoints,passages


def test_offline_timeline_binds_exact_packets_and_checks_first_passage(published_timeline):
    publish,_,_,_,_,_=published_timeline
    assert publish.timeline()['PASS']


def test_offline_checker_rejects_checkpoint_filled_from_future(published_timeline):
    publish,core,path,_,cp,_=published_timeline
    cp[0].update(exact_LB='49/50',exact_gap='1/50')
    core.table(path/'FRONTIER_CHECKPOINTS.csv',cp)
    with pytest.raises(ValueError,match='BACKFILLED'):publish.timeline()


def test_offline_checker_rejects_discovery_time_as_first_passage(published_timeline):
    publish,core,path,_,_,passages=published_timeline
    passages[0]['actual_certificate_completion_seconds']=15
    core.table(path/'GAP_FIRST_PASSAGE_TIMES.csv',passages)
    with pytest.raises(ValueError,match='FIRST_COMPLETED'):publish.timeline()


def test_offline_checker_rejects_forged_mathematical_bound_in_event(published_timeline):
    publish,core,path,events,_,_=published_timeline
    events[1].update(exact_LB='99/100',exact_gap='1/100')
    core.table(path/'FRONTIER_EVENTS.csv',events)
    with pytest.raises(ValueError,match='MATHEMATICAL'):publish.timeline()
