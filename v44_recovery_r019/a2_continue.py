"""Continue an independently restored Phase-I pool with its exact frozen weights."""
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
from types import FunctionType
from unittest.mock import patch
import inspect,linecache,textwrap,shutil
from v44.common import read,record,verify,atomic,now
from .a2_checkpoint import load

ADMISSION=Path('D:/MobileESS_V44/development/may02_b3_checkpoint_03/ADMISSION.json')


class FrozenWeights:
    def __init__(self,snapshot,global_rows,weights):
        from v42_a_stage_phase1.core import elastic_master
        master=elastic_master(snapshot,global_rows,weights_by_row=weights)
        self.weights=dict(zip(master.artificial_rows,master.weights))
        self.senses={row:snapshot.senses[row] for row in master.global_rows}
        self.rhs={row:snapshot.rhs[row] for row in master.global_rows}
        self.restricted_snapshot=None;self.restricted_rows=()

    def restricted(self,snapshot,rows):
        from v42_a_stage_compact_rowgen.rowgen import restricted
        self.restricted_rows=tuple(sorted(set(rows)))
        self.restricted_snapshot=restricted(snapshot,self.restricted_rows)
        return self.restricted_snapshot

    def elastic_master(self,snapshot,global_rows):
        from v42_a_stage_phase1.core import elastic_master
        weights={}
        for row in global_rows:
            source=self.restricted_rows[row] if snapshot is self.restricted_snapshot else row
            if (source not in self.weights or snapshot.senses[row]!=self.senses[source] or snapshot.rhs[row]!=self.rhs[source]):
                raise ValueError('R019_FROZEN_PHASE_ROW_SENSE_OR_RHS_DRIFT')
            weights[row]=self.weights[source]
        return elastic_master(snapshot,global_rows,weights_by_row=weights)


def continued_phase(function,namespace,packet):
    source=textwrap.dedent(inspect.getsource(function))
    begin=source.index("    G=state['grows'];")
    end=source.index('    if certified_zero_point is not None:',begin)
    source=source[:begin]+"    if certified_zero_point is not None:raise PermissionError('R019_POSITIVE_PHASE_CHECKPOINT_ONLY')\n    G=state['grows'];folder=OUT/day;s=state['compact']\n    included=set(range(s.matrix.shape[0]))\n    phase_traces=list(_r019_packet['phase_traces']);stagnation=_r019_packet['stagnation']\n    activation_round=_r019_packet['activation_round'];bestPhi=_r019_packet['bestPhi']\n"+source[end:]
    filename=__file__+'.phase.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace['_r019_packet']=packet
    exec(compile(source,filename,'exec'),namespace)
    return namespace['run']


def resumed_budget(parent,class_):
    from v44.checkpoints import ledger_state
    account=ledger_state(Path(parent)/'A2/NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    original=read(account['ledger']['path'])
    class ContinuedBudget(class_):
        def __init__(self,path,**kwargs):
            self._r019_parent=account
            super().__init__(path,**kwargs)
            self.calls=deepcopy(original['calls']);self.costs=deepcopy(original['costs'])
            self.native_used=account['measured'];self.started=self.clock()-original['wall_seconds']
            self.persist()
        def persist(self):
            super().persist()
            value=read(self.path)
            value.update(checkpoint_resume=True,parent_ledger=self._r019_parent['ledger'],
                inherited_Native_seconds=self._r019_parent['measured'],Native_clock_reset=False,
                resumed_same_stage_budget=True,historical_costs_reused=True,
                inherited_completed_calls=self._r019_parent['calls'])
            atomic(self.path,value)
    return ContinuedBudget


@contextmanager
def scope(request):
    from v44 import a2
    from v44.execution import assert_current
    from v42_may_campaign_native90 import budget as budget_module
    from v42_may_campaign_native90.a_routing import group as original_group
    context=assert_current()
    overlay=read(context['request']['execution_permit']['path'])['autonomous_recovery_overlay']
    explicit=overlay.get('explicit_A2_checkpoint_resume',{})
    if (overlay.get('policy')!='V44_AUTONOMOUS_RECOVERY_R019' or explicit.get('start_solve')!=15
            or explicit.get('native_total_ceiling')!=5400. or explicit.get('native_clock_reset') is not False):
        raise PermissionError('R019_EXPLICIT_SAME_STAGE_CHECKPOINT_POLICY_REQUIRED')
    admission=read(ADMISSION);verify(admission['sources']+[admission['checkpoint'],admission['parent_request']])
    if (request['day'],request['arm'],request['stage'])!=('2025-05-02','B3','A2'):
        raise PermissionError('R019_EXACT_MAY02_B3_A2_CHECKPOINT_REQUIRED')
    parent=Path(request['a2_checkpoint_parent'])
    if parent.resolve()!=Path(admission['parent']).resolve():raise PermissionError('R019_PARENT_BINDING_DRIFT')
    packet=load(admission['checkpoint']['path']);packet['state']['_campaign']['input_receipts']
    original_scope=a2.scope
    def prepare(current,progress=None):
        output=Path(current['output']);output.mkdir(parents=True,exist_ok=False)
        (output/'STATIC').mkdir()
        for name in ('BLOCK_PRICING_ORACLE_VERIFICATION.json','A_PREPARE_RECEIPT.json','INITIAL_VERIFICATION.json','PHASE_I_TRACE.json'):
            shutil.copy2(parent/'A2/OUTPUT'/name,output/name)
        original_verification=read(output/'INITIAL_VERIFICATION.json')
        original_verification.update(checkpoint_restored=True,historical_point_bound_clock_loaded=True,
            original_initial_verification=record(parent/'A2/OUTPUT/INITIAL_VERIFICATION.json'))
        atomic(output/'INITIAL_VERIFICATION.json',original_verification)
        atomic(output/'A2_CHECKPOINT_RESTORATION.json',dict(UTC=now(),PASS=True,
            admission=record(ADMISSION),next_solve=packet['next_solve'],no_prior_solve_or_pricing_repeated=True,
            inherited_Native_seconds=admission['Native_account']['measured'],remaining_Native_seconds=admission['Native_account']['remaining'],
            implementation=record(__file__)))
        return packet['state']
    def group(module,names,**routing):
        namespace=original_group(module,names,**routing)
        if module.__name__=='v42_a_stage_canary.phase':
            frozen=FrozenWeights(packet['state']['reference'],packet['state']['grows'],packet['frozen_weights'])
            namespace.update(elastic_master=frozen.elastic_master,restricted=frozen.restricted)
            namespace['run']=continued_phase(module.run,namespace,packet)
        return namespace
    @contextmanager
    def routed(current,m1):
        if m1['MESS_plan']['plan_sha']!=admission['fixed_M1_plan_sha']:raise PermissionError('R019_FIXED_M1_PLAN_DRIFT')
        with original_scope(current,m1) as run:
            namespace=dict(run.__globals__,prepare=prepare,group=group)
            continued=FunctionType(run.__code__,namespace,run.__name__,run.__defaults__,run.__closure__)
            def run_continued(*args,**kwargs):
                result=continued(*args,**kwargs)
                result.update(old_point_bound_clock_loaded=True,checkpoint_resumed=True,
                    A2_start_solve=15,Native_clock_reset=False,
                    inherited_A2_Native_seconds=admission['Native_account']['measured'],
                    old_UB_LB_certificates_transferred=False)
                return result
            yield run_continued
    cls=resumed_budget(parent,budget_module.DateBudget)
    with patch.object(a2,'scope',routed),patch.object(budget_module,'DateBudget',cls):yield admission
