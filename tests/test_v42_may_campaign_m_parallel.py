from copy import deepcopy
from types import SimpleNamespace
import pytest
from v42_may_campaign.m_parallel_check import DATES,resident_models,verify_isolation


class FakeModel:
    def __init__(self,*args,env=None,**kwargs):self.env=env;self.disposed=False
    def copy(self):return FakeModel(env=self.env)
    def dispose(self):self.disposed=True
    def __getattr__(self,name):raise RuntimeError('FREED_NATIVE_ATTRIBUTE_MUST_NOT_BE_READ')


def test_original_full_model_copy_and_env_remain_until_barrier_release():
    gp=SimpleNamespace(Model=FakeModel);env=object()
    with resident_models(gp,env) as held:
        source=gp.Model('original_model');copy=source.copy()
        assert source.env is env and copy.env is env and held==[copy]
        source.dispose();copy.dispose()
        assert source.disposed and not copy.disposed
    assert copy.disposed and gp.Model is FakeModel


def test_cross_environment_native_model_construction_rejected():
    gp=SimpleNamespace(Model=FakeModel)
    with resident_models(gp,object()):
        with pytest.raises(ValueError,match='CROSS_ENV'):gp.Model(env=object())


def test_resident_model_is_released_even_after_proof_failure():
    gp=SimpleNamespace(Model=FakeModel)
    with pytest.raises(ValueError,match='PROOF_FAILURE'):
        with resident_models(gp,object()) as held:
            copy=gp.Model().copy()
            raise ValueError('PROOF_FAILURE')
    assert copy.disposed and gp.Model is FakeModel


@pytest.fixture
def parallel():
    receipts=[dict(PASS=True,day=day,process=dict(PID=100+i,created=1000+i),output='D:/out/'+day,
        temporary_directory='D:/tmp/'+day,working_directory='D:/work/'+day,case_sha=day,
        native_FULL_model_resident=True,environment_start_PASS=True,
        native_FULL_Threads=1,
        resident_model_and_current_original_case_SHA_match=True,case_proof=dict(PASS=True),
        opendss_contexts=[dict(PID=100+i,data_path='D:/work/'+day+'/'+str(k),
            scientific_control_settings_changed=False) for k in range(2)],
        Native_optimize_calls=0,Native_presolve_calls=0,denied_native_attempts=[])
        for i,day in enumerate(DATES)]
    snapshot=[dict(pid=100+i,alive=True,creation_time=1000+i) for i in range(3)]
    return receipts,snapshot


def test_three_actual_resident_models_prove_isolation_but_not_solve_license(parallel):
    r=verify_isolation(*parallel)
    assert r['PASS'] and r['three_Env_and_FULL_models_simultaneously_resident']
    assert r['simultaneous_optimization_license_status']=='NOT_TESTED_NATIVE_ZERO_REQUIRED'
    assert r['Native_optimize_calls']==r['Native_presolve_calls']==0


@pytest.mark.parametrize('mutation',['pid','creation','date','output','temp','case','alive','proof','Native','presolve','attempts','resident','threads','dss_pid','dss_path','dss_control'])
def test_shared_state_or_incomplete_resident_evidence_rejected(parallel,mutation):
    receipts,snapshot=deepcopy(parallel)
    if mutation=='pid':receipts[1]['process']['PID']=receipts[0]['process']['PID']
    if mutation=='creation':receipts[1]['process']['created']+=1
    if mutation=='date':receipts[1]['day']=receipts[0]['day']
    if mutation=='output':receipts[1]['output']=receipts[0]['output']
    if mutation=='temp':receipts[1]['temporary_directory']=receipts[0]['temporary_directory']
    if mutation=='case':receipts[1]['case_sha']=receipts[0]['case_sha']
    if mutation=='alive':snapshot[1]['alive']=False
    if mutation=='proof':receipts[1]['case_proof']['PASS']=False
    if mutation=='Native':receipts[1]['Native_optimize_calls']=1
    if mutation=='presolve':receipts[1]['Native_presolve_calls']=1
    if mutation=='attempts':receipts[1]['denied_native_attempts']=[{}]
    if mutation=='resident':receipts[1]['native_FULL_model_resident']=False
    if mutation=='threads':receipts[1]['native_FULL_Threads']=2
    if mutation=='dss_pid':receipts[1]['opendss_contexts'][0]['PID']=receipts[0]['process']['PID']
    if mutation=='dss_path':receipts[1]['opendss_contexts'][0]['data_path']='D:/shared'
    if mutation=='dss_control':receipts[1]['opendss_contexts'][0]['scientific_control_settings_changed']=True
    with pytest.raises(ValueError):verify_isolation(receipts,snapshot)
