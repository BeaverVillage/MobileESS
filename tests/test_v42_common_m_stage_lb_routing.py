"""Execute the actual common run body with named Fake algorithm delegates."""
from contextlib import nullcontext
from fractions import Fraction as F
from types import SimpleNamespace
import numpy as np


def exercise(monkeypatch,tmp_path,enabled):
    from v42_may_campaign_native90 import m_stage
    from v42_m1_anytime import algorithms as alg,core
    from v42_m1_hybrid import blocks,verify
    calls=[];scheduled=[];prices=set()
    case=SimpleNamespace(point=np.asarray([0.]),identity={'transport':{}},
        case_sha='c'*64,output=tmp_path,planning={},bundle={'day':'2025-05-01'},A=None,d=None)
    budget=SimpleNamespace(started=0,final_reserve=0,calls=[],cost=lambda *a:nullcontext(),closed=False,
        used=lambda:0.,wall=lambda:0.,remaining=lambda **k:5400. if enabled and not budget.closed else 0.)
    class Frontier:
        def __init__(self,*args,**kwargs):self.lb=F(0);self.ub=F(1)
        def gap(self):return (self.ub-self.lb)/self.ub
        def checkpoint(self,*args):pass
    class Search:
        def take_rescue(self,*args):return None
        def record_rmp(self,*args):calls.append('catalog')
        def select(self,case,base,new,lb,**kwargs):
            calls.append('select');return dict(status='VALID_PROPOSAL',dual=new,alpha='1')
        def consume_pricing(self,decomp,dual,kind):
            key=(tuple(dual.items()),kind)
            if key in prices:budget.closed=True;return False
            prices.add(key);return True
        def record_pricing(self,*args,**kwargs):calls.append('certificate')
    def factory(current,request):
        assert current is case and request['day']=='2025-05-01'
        calls.append('factory');return Search()
    def choice(*args):
        method=('L2','L3')[len(scheduled)];scheduled.append(method);return method,{}
    def lp_round(case,decomp,dual,ledger,frontier,target,method,kind,**kwargs):
        calls.append('four_unit_original_pricing');target.mkdir()
        packet=target/'CERT.json'
        m_stage.atomic(packet,dict(PASS=True,case_sha=case.case_sha,exact_Global_LB='1/2'))
        frontier.lb=F(1,2)
        return dict(method=method,certified_gain=.5,certificate=str(packet)),{'0':'1'},dict(columns={})
    monkeypatch.setattr(m_stage,'prepare',lambda *args:case)
    monkeypatch.setattr(m_stage,'_fresh_lp_dual',lambda *args:({},dict(exact_bound='0')))
    monkeypatch.setattr(m_stage,'_strict_ub',lambda *args:dict(exact_Global_UB='1'))
    monkeypatch.setattr(m_stage,'check_rational_dual_certificate',lambda *args,**kwargs:
        dict(PASS=True,case_sha=case.case_sha,exact_bound='1/2' if enabled else '0'))
    def plan(*args):
        m_stage.atomic(tmp_path/'OPTIMIZED_MESS_PLAN.json',{});return {}
    monkeypatch.setattr(m_stage,'_plan',plan)
    monkeypatch.setattr(core,'Frontier',Frontier)
    monkeypatch.setattr(core,'schedule_choice',choice)
    monkeypatch.setattr(blocks,'build_blocks',lambda *args:SimpleNamespace(units={}))
    monkeypatch.setattr(verify,'verify_decomposition',lambda *args:dict(PASS=True))
    monkeypatch.setattr(alg,'feedback_master',lambda *args,**kwargs:
        dict(full_original_dual={'0':'1'},convexity_duals=None))
    monkeypatch.setattr(alg,'lp_round',lp_round)
    args=dict(lb_rescue=factory) if enabled else {}
    result=m_stage.run(dict(day='2025-05-01'),budget,None,**args)
    return calls,result,tmp_path


def test_default_run_keeps_original_no_search_path(monkeypatch,tmp_path):
    calls,result,_=exercise(monkeypatch,tmp_path,False)
    assert calls==[] and result['global_LB']==0 and result['PASS'] is False


def test_actual_common_loop_selects_once_and_skips_repeated_price(monkeypatch,tmp_path):
    calls,result,path=exercise(monkeypatch,tmp_path,True)
    assert calls.count('factory')==1 and calls.count('select')==2
    assert calls.count('four_unit_original_pricing')==1 and calls.count('certificate')==1
    import json
    audit=json.loads((path/'ADAPTIVE_SCHEDULER_AUDIT.json').read_text())
    assert audit['history'][-1]['status']=='NOT_RUN_IDENTICAL_STAGE_PRICE_INPUT'
    assert result['global_LB']==.5 and result['Native_Runtime']==0 and result['P2_calls']==0
