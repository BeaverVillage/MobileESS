from pathlib import Path
from types import SimpleNamespace,FunctionType
import numpy as np
from v44.common import atomic,read,record
from v44_recovery_r024b import rollback_resume


def fixture(tmp_path):
    saved=tmp_path/'saved';saved.mkdir();checkpoint=saved/'state';checkpoint.write_bytes(b'offline fixture')
    cache=saved/'block';cache.write_bytes(b'offline original block fixture')
    manifest=saved/'BLOCK_PRICING_ORACLE_VERIFICATION.json'
    atomic(manifest,{'records':[{'class_id':'class1','external_full_block_cache':record(cache)}]})
    ledger=saved/'ledger.json';atomic(ledger,dict(inflight=None,measured_Native_Runtime=458.118,
        calls=[{'Native_Runtime':458.118}],costs=[],wall_seconds=100.))
    native=saved/'native.json';atomic(native,dict(ledger=record(ledger)))
    adaptive=saved/'adaptive.json';atomic(adaptive,{'PASS':True})
    admission=saved/'ADMISSION.json';atomic(admission,dict(sources=[],checkpoint=record(checkpoint),
        native_parent=record(native),adaptive_parent=record(adaptive),pricing_manifest=record(manifest),
        restored_active_rows=176887,prior_Phi='1/1000'))
    request=dict(r024b_continuation=record(admission),output=str(tmp_path/'new'/'OUTPUT'),input_folder=str(saved))
    return request


def test_checkpoint_preparation_installs_required_pricing_roster_before_query(tmp_path,monkeypatch):
    from v44_recovery_r024b import a2_checkpoint
    from v42_a_stage_canary import targeted
    request=fixture(tmp_path);state={'_campaign':{'input_receipts':{}}}
    monkeypatch.setattr(a2_checkpoint,'load',lambda path:{'state':state})
    assert rollback_resume.prepare(request,SimpleNamespace(used=lambda:458.118)) is state
    output=Path(request['output']);assert (output/'BLOCK_PRICING_ORACLE_VERIFICATION.json').exists()
    ns=dict(targeted.targeted.__globals__,HISTORY=output,projected_global_pi=lambda *a:np.zeros(0),
        select=lambda *a:[],serial=lambda x:x)
    call=FunctionType(targeted.targeted.__code__,ns)
    result,selected=call(None,None,1,None,None,{'Pi':np.zeros(0)},None,None,None,{},None,{},[],np.zeros(0),{},output/'PRICE')
    assert result['PASS'] and not selected
    assert read(output/'R024B_CHECKPOINT_RESTORED.json')['Phase_I_separate_time_limit'] is None


def test_native_clock_is_inherited_with5400_total_and_no1000_cutoff(tmp_path):
    request=fixture(tmp_path)
    class Original:
        def __init__(self,path,native_limit=3600,**kw):
            self.path=path;self.native_limit=native_limit;self.native_used=0.;self.calls=[];self.costs=[]
            self.clock=lambda:1000.;self.started=1000.;self.persist()
        def persist(self):atomic(self.path,{'Native_ceiling_seconds':self.native_limit,'measured_Native_Runtime':self.native_used})
        def remaining(self):return max(0.,self.native_limit-self.native_used)
    cls=rollback_resume.continued_budget(Original,request);budget=cls(tmp_path/'new_ledger.json')
    assert budget.native_limit==5400. and abs(budget.native_used-458.118)<1e-6
    assert abs(budget.remaining()-4941.882)<1e-6
    budget.native_used=1000.;assert budget.remaining()==4400.
    receipt=read(budget.path);assert receipt['Native_clock_reset'] is False and receipt['Phase_I_separate_time_limit'] is None


def test_original_scientific_p1_and_acceptance_are_not_replaced():
    from v44 import worker
    from v42_may_campaign_native90 import a_stage
    from v44_recovery_r024b.rollback_resume import install
    original=a_stage.run
    with install():assert a_stage.run is original
