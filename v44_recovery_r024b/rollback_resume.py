"""Original r024a algorithm, with verified same-stage checkpoint/Native continuation."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import FunctionType
from functools import wraps
from unittest.mock import patch
import shutil


def continued_budget(original,request):
    from v44.common import read,verify,atomic
    verify([request['r024b_continuation']]);admission=read(request['r024b_continuation']['path']);verify([admission['native_parent']])
    proof=read(admission['native_parent']['path']);verify([proof['ledger']]);old=read(proof['ledger']['path'])
    if old.get('inflight') is not None or old['measured_Native_Runtime']>=5400:
        raise PermissionError('R024B_SETTLED_NATIVE_BELOW5400_REQUIRED')
    class Continued(original):
        def __init__(self,path,**kwargs):
            kwargs['native_limit']=5400.
            super().__init__(path,**kwargs)
            self.calls=deepcopy(old['calls']);self.costs=deepcopy(old['costs'])
            self.native_used=old['measured_Native_Runtime'];self.started=self.clock()-old['wall_seconds'];self.persist()
        def persist(self):
            super().persist();value=read(self.path)
            value.update(policy_version='R024A_NATIVE90_CHECKPOINT_CONTINUATION',Native_clock_reset=False,
                parent_native_account=admission['native_parent'],Phase_I_separate_time_limit=None,
                inherited_Native_seconds=old['measured_Native_Runtime'])
            atomic(self.path,value)
    return Continued


def prepare(request,budget,progress=None):
    from v44.common import read,verify,record,atomic,now
    from .a2_checkpoint import load
    proof=read(request['r024b_continuation']['path']);verify(proof['sources']+[proof['checkpoint'],proof['native_parent'],proof['adaptive_parent']])
    state=load(proof['checkpoint']['path'])['state'];authority=state['_campaign']
    verify(list(authority['input_receipts'].values()))
    output=Path(request['output']);output.mkdir(parents=True,exist_ok=False);(output/'STATIC').mkdir()
    manifest=proof['pricing_manifest'];verify([manifest]);value=read(manifest['path'])
    for row in value['records']:verify([row['external_full_block_cache']])
    shutil.copyfile(manifest['path'],output/'BLOCK_PRICING_ORACLE_VERIFICATION.json')
    authority.update(output=str(output),input_folder=request['input_folder'])
    atomic(output/'R024B_CHECKPOINT_RESTORED.json',dict(UTC=now(),PASS=True,checkpoint=proof['checkpoint'],
        all_native_oracle_cache_receipts_verified=True,pricing_manifest=record(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json'),
        restored_active_rows=proof['restored_active_rows'],original_saved_model_fingerprint_exact=True,
        inherited_Native_seconds=budget.used(),Native_clock_reset=False,Native_limit=5400.,Phase_I_separate_time_limit=None,
        prior_Phi=proof['prior_Phi'],original_P1_and_physical_acceptance_unchanged=True))
    return state


@contextmanager
def install():
    from v44 import worker,a2
    from v42_may_campaign_native90 import budget as budgets
    from v44.common import read
    original=worker.a_stage;original_scope=a2.scope
    @wraps(original)
    def a_stage(request,*args,**kwargs):
        if not request.get('r024b_continuation'):return original(request,*args,**kwargs)
        @contextmanager
        def scope(current,m1):
            proof=read(current['r024b_continuation']['path'])
            if m1['MESS_plan']['plan_sha']!=proof['fixed_M1_plan_sha']:
                raise PermissionError('R024B_FIXED_M1_PLAN_SHA_DRIFT')
            with original_scope(current,m1) as run:
                namespace=dict(run.__globals__)
                namespace['prepare']=lambda req,progress=None:prepare(req,req['_budget'],progress)
                continued=FunctionType(run.__code__,namespace,run.__name__,run.__defaults__,run.__closure__)
                def resume(*a,**k):
                    result=continued(*a,**k)
                    result.update(checkpoint_resumed=True,Native_clock_reset=False,
                        inherited_A2_Native_seconds=proof['inherited_Native_seconds'],
                        old_point_bound_clock_loaded=True,old_UB_LB_certificates_transferred=False)
                    return result
                yield resume
        with patch.object(a2,'scope',scope),patch.object(budgets,'DateBudget',continued_budget(budgets.DateBudget,request)):
            return original(request,*args,**kwargs)
    with patch.object(worker,'a_stage',a_stage):yield
