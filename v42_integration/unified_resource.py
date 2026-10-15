"""One Supervisor ledger with immutable historical usage and process gates."""
from contextlib import contextmanager
from pathlib import Path
import json
import os
from time import perf_counter
from .budget import IntegrationBudget
from .unified_contract import REPORT, load_contracts, file_sha

OLD_LEDGERS = (
    Path('D:/v42_b2_global_lb_alternative_20261014/docs/v42_b2_global_lb_alternative_research_20261014/NATIVE_RUNTIME_BUDGET_LEDGER.json'),
    Path('D:/v42_integration_validation_20261013/INTEGRATION_BUDGET_LEDGER.json'),
)


def require_heavy_scope(label,context):
    """Enforce the user's current standalone validation order."""
    interface=json.loads((REPORT/'UNIFIED_INTERFACE_CONTRACT.json').read_text(encoding='utf8'))
    if interface.get('four_stage_Heavy_authorized') is not True:
        stage=context.get('planning_stage',context.get('stage',''))
        if str(label).startswith(('A2','M2')) or stage in ('A2','M2'):
            raise ValueError('FOUR_STAGE_HEAVY_HOLD')
    if str(label).startswith('A1'):
        if interface.get('new_Known_A_Heavy_authorized') is not True:
            raise ValueError('NEW_KNOWN_A_NATIVE_HOLD_UNKNOWN_SITE_ONLY')
        if context.get('arm')!='B1' or context.get('day')!='2025-05-01':
            raise ValueError('AIDC_HEAVY_MAY01_B1_ONLY')
    scale=context.get('scale_stage')
    if scale and scale!='S1' and interface.get('S2_to_S7_Heavy_authorized') is not True:
        raise ValueError('MESS_HEAVY_S2_TO_S7_HOLD')


def historical_usage(paths=OLD_LEDGERS):
    rows = []
    for path in paths:
        d = json.loads(path.read_text(encoding='utf8'))
        if d.get('inflight'):
            raise RuntimeError('HISTORICAL_NATIVE_CALL_UNRECONCILED')
        used = d.get('effective_cumulative_Native_Runtime', d.get('conservative_solve_seconds'))
        limit = d.get('original_ceiling', d.get('limit_seconds'))
        if used is None or limit is None or used > limit:
            raise ValueError('HISTORICAL_NATIVE_USAGE_NOT_PROVEN')
        rows.append(dict(path=str(path), sha256=file_sha(path), used_seconds=used,
                         limit_seconds=limit, binding=d.get('binding'), inherited=True,
                         original_ledger_mutated=False))
    return rows


class UnifiedResearchBudget(IntegrationBudget):
    """New distinct science pilot; retain linked cumulative parent projections."""
    def __init__(self, path=REPORT/'UNIFIED_NATIVE_RUNTIME_LEDGER.json', limit=360.):
        if Path(path).resolve()!=(REPORT/'UNIFIED_NATIVE_RUNTIME_LEDGER.json').resolve():
            raise ValueError('UNIFIED_CANONICAL_SINGLE_LEDGER_REQUIRED')
        manifest = load_contracts()
        parents = historical_usage()
        super().__init__(path, limit=limit)
        identity = dict(science_sha=manifest['bindings']['science_sha'],
                        case_sha=manifest['bindings']['case_sha'], session='UNIFIED_20261014_ONE_ATTEMPT')
        if 'identity' in self.document:
            if self.document['identity'] != identity or self.document['historical_ledgers'] != parents:
                raise ValueError('UNIFIED_SESSION_OR_PARENT_LEDGER_DRIFT')
        else:
            self.document.update(identity=identity, historical_ledgers=parents, Threads=1,
                Heavy_workers=1, auto_restart_authorized=False, parent_usage_reset=False,
                PR230_historical_native_seconds=0, campaign_HOLD=True, IEEE8500_started=False)
            self._save()

    def verify_parents(self):
        for row in self.document['historical_ledgers']:
            if file_sha(row['path']) != row['sha256']:
                raise ValueError('HISTORICAL_LEDGER_MUTATION')

    def remaining(self, reserve=0.):
        self.verify_parents()
        own = super().remaining(reserve)
        # Even if overlapping numerical cases are later established, this
        # conservative linked cap cannot reopen either parent campaign.
        return min([own] + [max(0., p['limit_seconds']-p['used_seconds']-self.used()-reserve)
                            for p in self.document['historical_ledgers']])

    def preflight(self):
        from .partial_canary import resource_snapshot
        snap = resource_snapshot()
        m = snap['memory']
        workers = [p for p in snap['workers'] if p['ProcessId'] != os.getpid()
                   and not str(p.get('CommandLine', '')).endswith('MONITOR_ADAPTER.py serve')]
        if workers:
            raise RuntimeError('UNIFIED_EXTERNAL_HEAVY_WORKER_PRESENT')
        if self.remaining() <= 0:
            raise RuntimeError('UNIFIED_NATIVE_BUDGET_EXHAUSTED')
        self.verify_parents()
        manifest=load_contracts()
        physical=json.loads((REPORT/'UNIFIED_PHYSICAL_AUTHORITY.json').read_text())
        root=REPORT.parents[1]
        for name, expected in physical['source_artifact_shas'].items():
            if file_sha(root/name) != expected:
                raise ValueError('UNIFIED_PHYSICAL_SOURCE_DRIFT:'+name)
        return dict(snapshot=snap, bindings=manifest['bindings'], parent_ledgers=self.document['historical_ledgers'],
                    remaining_seconds=self.remaining(), native_workers=1, Threads=1, PASS=True)

    @contextmanager
    def exclusive_worker(self):
        self.preflight()
        # Cross-directory lock: agents cannot get parallel permission merely
        # by constructing a different ledger path.
        lock=Path('D:/V42_UNIFIED_HEAVY_WORKER.lock')
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        os.write(fd,str(os.getpid()).encode());os.close(fd)
        try:
            yield
        finally:
            self.verify_parents()
            lock.unlink()

    def solve(self, model, *, label, cap, callback=None):
        context=json.loads(json.dumps(getattr(self,'stage_context',{}),allow_nan=False))
        require_heavy_scope(label,context)
        with self.exclusive_worker():
            # Stage identity is captured before optimize. Later contract
            # revisions cannot relabel the bound or runtime of this call.
            with self._transaction():
                self.document['active_stage_context']=context
                before=len(self.document['calls'])
            try:
                row=super().solve(model,label=label,cap=cap,callback=callback)
                row.update(session_identity=dict(self.document['identity']),stage_context=context)
                return row
            finally:
                with self._transaction():
                    if len(self.document['calls'])>before:
                        self.document['calls'][-1].update(
                            session_identity=dict(self.document['identity']),stage_context=context)
                    self.document['active_stage_context']=None

    def diagnose_iis(self,model,*,label,cap):
        """Bounded Gurobi diagnostic; its wall cost is never free or reset."""
        context=json.loads(json.dumps(getattr(self,'stage_context',{}),allow_nan=False))
        require_heavy_scope(label,context)
        with self.exclusive_worker():
            seconds=min(float(cap),self.remaining())
            if seconds<=0:raise RuntimeError('UNIFIED_NATIVE_BUDGET_EXHAUSTED')
            model.Params.Threads=1;model.Params.TimeLimit=seconds
            with self._transaction():
                if self.document['inflight']:raise RuntimeError('UNRECONCILED_SOLVER_CALL')
                self.document['inflight']=dict(label=label,cap=seconds,pid=os.getpid(),
                    operation='COMPUTE_IIS',stage_context=context)
            began=perf_counter();error=None
            try:model.computeIIS()
            except BaseException as exc:error=repr(exc);raise
            finally:
                wall=perf_counter()-began
                with self._transaction():
                    self.document['calls'].append(dict(label=label,solver='GUROBI_IIS',
                        Native_Runtime=None,measured_seconds=wall,charged_seconds=wall,
                        cap_seconds=seconds,overshoot_seconds=max(0.,wall-seconds),error=error,
                        stage_context=context,session_identity=dict(self.document['identity']),
                        accounting='CONSERVATIVE_OTHER_SOLVER_WALL_NO_FABRICATED_NATIVE_RUNTIME'))
                    self.document['other_solver_wall_seconds']+=wall
                    self.document['conservative_solve_seconds']+=wall
                    self.document['inflight']=None
            return dict(wall_seconds=wall,cap_seconds=seconds,Native_Runtime=None,error=error)
