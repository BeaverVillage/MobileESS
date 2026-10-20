from types import SimpleNamespace
import v44_recovery_r026f1
from v44_recovery_r026f1.phase_limit import phase_scope
from v42_may_campaign_native90.budget import DateBudget


def test_actual_budget_remaining_drives_effective_solver_limit_not_requested_argument(tmp_path,monkeypatch):
    observed=[]
    # The original DateBudget ignores requested_seconds and takes remaining().
    def original(self,model,*a,**kw):
        observed.append(DateBudget.remaining(self));self.native_used+=100.
    monkeypatch.setattr(DateBudget,'native_optimize',original)
    b=SimpleNamespace(native_used=0.,native_limit=5400.)
    class Native:
        def remaining(self):return DateBudget.remaining(b)
        def solve(self,snapshot,folder,component):
            DateBudget.native_optimize(b,None,component=component,requested_seconds=5400.)
            return {},{}
    with phase_scope(Native(),tmp_path) as native:
        native.solve(None,tmp_path,'PHASE_I')
        native.solve(None,tmp_path,'LOCAL_PRICING')
        native.solve(None,tmp_path,'ORIGINAL_P1')
    assert observed==[1500.,1400.,5200.]
    assert b.native_limit==5400. and DateBudget.remaining(b)==5100.
