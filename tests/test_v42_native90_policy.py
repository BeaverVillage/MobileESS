from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from v42_may_campaign_native90 import budget as b
from v42_may_campaign_native90.build_reuse import CheckpointMemo

class Clock:
    value=0.
    def __call__(self):return self.value
class Model:
    def __init__(self,clock,runtime=0.,failed=False):
        self.Params=SimpleNamespace();self.Runtime=runtime;self.clock=clock;self.failed=failed;self.calls=0
    def optimize(self,callback):
        self.calls+=1;self.clock.value+=self.Runtime or 0.
        if self.failed:raise RuntimeError('FAILED_NATIVE_CALL')
@pytest.fixture
def ports(monkeypatch):
    monkeypatch.setattr(b,'native_scope',lambda *a:nullcontext())
    monkeypatch.setattr(b,'guard',lambda *a:None)
@pytest.mark.parametrize('preparation,native',[(2400,5400),(6000,600)])
def test_model_wall_excluded(tmp_path,ports,preparation,native):
    c=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=c);c.value=preparation
    m=Model(c,native);budget.native_optimize(m,requested_seconds=1)
    assert m.Params.TimeLimit==5400 and budget.used()==native
    budget.check();assert budget.remaining()==5400-native
def test_lp_pricing_milp_accumulate_and_exhaustion_refuses(tmp_path,ports):
    c=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=c)
    for seconds,expected in ((1200,5400),(900,4200),(3300,3300)):
        model=Model(c,seconds);budget.native_optimize(model,requested_seconds=3)
        assert model.Params.TimeLimit==expected
    c.value+=10000;budget.check();assert budget.used()==5400
    model=Model(c)
    with pytest.raises(b.BudgetStop):budget.native_optimize(model)
    assert model.calls==0
def test_validation_fresh_ac_and_three_b2_budgets(tmp_path,ports):
    budgets=[]
    for slot in range(3):
        c=Clock();budget=b.DateBudget(tmp_path/str(slot)/'ledger.json',clock=c)
        budget.native_optimize(Model(c,100*(slot+1)))
        with budget.cost('integer_physical_validation','replay'):c.value+=6000
        with budget.cost('Fresh_AC','actual'):c.value+=8000
        budget.check();budgets.append(budget)
    assert [v.used() for v in budgets]==[100,200,300]
def test_failed_native_actual_runtime_and_unknown_quarantine(tmp_path,ports):
    c=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=c)
    with pytest.raises(RuntimeError):budget.native_optimize(Model(c,37,True))
    assert budget.used()==37 and len(budget.calls)==1
    with pytest.raises(RuntimeError,match='QUARANTINE'):budget.native_optimize(Model(c,None))
    assert budget.used()==37
    denied=Model(c,5)
    with pytest.raises(RuntimeError,match='QUARANTINE'):budget.native_optimize(denied)
    assert denied.calls==0
def test_overshoot_is_preserved_and_never_reset(tmp_path,ports):
    c=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=c)
    with pytest.raises(b.BudgetStop):budget.native_optimize(Model(c,5401))
    assert budget.used()==5401
    with pytest.raises(PermissionError):b.DateBudget(tmp_path/'ledger.json')
def test_checkpoint_key_preserves_every_original_dependency():
    from dataclasses import replace
    import v42_job_capability as original
    job=original.Job('x','PENDING',0,24,24,'a',20,1,duration_authority='test',checkpoint_authorized=True)
    memo=CheckpointMemo(original.checkpoint_records)
    for j in (job,replace(job,uid='y'),replace(job,state='RUNNING',elapsed_seconds=121.5)):
        for start in range(24,40):
            for end in range(start+1,start+21):assert memo(j,start,end)==original.checkpoint_records(j,start,end)
    assert memo.hits>0
