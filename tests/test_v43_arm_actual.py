from types import SimpleNamespace
import numpy as np
import pytest

from v43_arms.current_ac import mess_mapper,ArmCurrentAC


def test_original_mapper_nets_coincident_units_and_keeps_transit_disconnected():
    apply,_=mess_mapper();calls=[]
    apply.__globals__['_set_generator']=lambda odd,name,p,q:calls.append(('G',name,p,q))
    apply.__globals__['_set_load']=lambda odd,name,p,q:calls.append(('L',name,p,q))
    trajectory=SimpleNamespace(mess_locations_96x4=np.array([['STA01','STA01','TRANSIT_TEST','STA02']]),
        mess_p_kw=np.array([[80.,-20.,0.,-15.]]),mess_q_kvar=np.array([[4.,1.,0.,-2.]]))
    apply(None,trajectory,0)
    from dayahead.v28r2.opendss_mapping import mess_injection_mapping
    a=mess_injection_mapping(60.,5.);b=mess_injection_mapping(-15.,-2.)
    assert ('G','MESS_DIS_STA01',a['generator_p_kw'],a['generator_q_kvar']) in calls
    assert ('L','MESS_CHG_STA02',b['charging_load_p_kw'],b['charging_load_q_kvar']) in calls
    assert not any('TRANSIT' in row[1] for row in calls)
    trajectory.mess_p_kw[0,2]=1.
    with pytest.raises(RuntimeError,match='NONZERO_MESS_IN_TRANSIT'):apply(None,trajectory,0)


def test_current_ac_rejects_changed_frozen_mess_before_mapping():
    from v43_actual.vendor.policy import digest
    oracle=ArmCurrentAC.__new__(ArmCurrentAC)
    oracle.mess_plan=dict(P_kW={'MESS01':[0.]});oracle.mess_sha=digest(oracle.mess_plan)
    oracle.mess_plan['P_kW']['MESS01'][0]=1.
    with pytest.raises(ValueError,match='FROZEN_MESS_PLAN_MUTATED'):
        oracle._apply_frozen_mess(None,dict(start_seconds=0))


@pytest.mark.parametrize('arm',('B0','B1','B2','B3'))
def test_every_arm_dispatches_unknown_through_same_policy_and_serial_guards(arm):
    from v43_arms.controller import UniformArmController
    from v43_actual.vendor.qos import TrainingStatistics,QoSWindowProvider
    from v43_actual.vendor.policy import digest
    from v43_actual.vendor.actual import JobRequest
    calls=[]
    class Oracle:
        issue=0.;now=None
        def observe(self,now,history):self.now=now
    class Policy:
        oracle=Oracle();sha=digest('NAMED_UNIFORM_ARM_POLICY');metadata={}
        def observe(self,now,use,metadata):self.current=(now,dict(use));self.metadata=metadata
        def current_guard(self,m,segments,now,use):return None
        def select(self,m,receipt,now,reservations):
            calls.append((m['uid'],self.current[1]['A']))
            return dict(uid=m['uid'],action='START',site='A',start_seconds=now,
                nominal_end_seconds=now+900.,additional_start_delay_seconds=0.)
    stats=TrainingStatistics(0.,digest('NAMED_TRAIN_SOURCE'),(),(),0,{},False,'NAMED_FIXTURE_ONLY')
    qos=QoSWindowProvider(stats,case_sha=digest('CASE'),provider_sha=digest('PROVIDER'))
    c=UniformArmController({'A':2},arm=arm,qos_window_provider=qos,frozen_policy=Policy())
    for uid in ('U1','U2'):
        c.submit(JobRequest(uid,0.,1,('A',),900.,None,
            dict(origin_unknown=True,representation_starts_seconds=(0.,900.))),0.)
    assert c.arm==arm and c.admit(0.)==['U1','U2']
    assert calls==[('U1',0),('U2',1)]
