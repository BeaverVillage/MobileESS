"""Separate, stage bound P1 budget for the real release executors.

Creating a proposal is not authorization. The consumed RC01 A1 allocation
cannot satisfy this adapter's authorization contract.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from time import time, sleep
import math
import os
import json
import uuid

from .budget import IntegrationBudget
from .d0_resource import native_binding
from .m_engine import file_record
from .partial_canary import resource_snapshot
from .unified_contract import digest

STAGES = ('A1', 'M1', 'A2', 'M2', 'K48_M1', 'K48_M2')
SCHEMA = 'RELEASE_PRODUCTION_P1_SEPARATE_AUTHORIZATION_V1'


def require_authorization(authorization):
    a = authorization
    caps = a.get('stage_caps_seconds', {})
    for name in ('limit_seconds','return_reserve_seconds'):
        v = a.get(name)
        if type(v) not in (int,float) or not math.isfinite(v):
            raise PermissionError('NEW_EXPLICIT_FINITE_STAGE_BUDGET_REQUIRED')
    scope=a.get('stage_cap_scope')
    if scope not in ('PER_DATE_STAGE','WHOLE_AUTHORIZATION_STAGE_TOTAL'):
        raise PermissionError('EXPLICIT_STAGE_CAP_SCOPE_REQUIRED')
    declared=a.get('allowed_stage_bindings',[])+a.get('authorized_date_cases',[])
    days={row.get('day') for row in declared}
    if not days or any(day not in {f'2025-05-{n:02d}' for n in range(1,32)} for day in days):
        raise PermissionError('EXPLICIT_INDEPENDENT_MAY_AUTHORIZATION_DATES_REQUIRED')
    required_caps=sum(caps.values()) if scope=='WHOLE_AUTHORIZATION_STAGE_TOTAL' else sum(
        cap for day in days for stage,cap in caps.items() if not (day=='2025-05-01' and stage=='A1'))
    if (a.get('schema') != SCHEMA or a.get('approved') is not True
            or a.get('scope') != 'NEW_RELEASE_P1_ONLY_HEAVY'
            or a.get('P2_calls') != 0 or a.get('Worker') != 1 or a.get('Threads') != 1
            or not a.get('human_approval_reference') or not a.get('policy_sha')
            or not a.get('authorization_id') or not a.get('authorized_ledger_path')
            or not caps or set(caps) - set(STAGES)
            or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in caps.values())
            or a.get('return_reserve_seconds', 0) < 30
            or a.get('limit_seconds', 0) < required_caps + a.get('return_reserve_seconds', 0)
            or not (a.get('allowed_stage_bindings') or a.get('authorized_date_cases'))):
        raise PermissionError('NEW_EXPLICIT_STAGE_BUDGET_APPROVAL_REQUIRED_RC01_REMAINDER_FORBIDDEN')
    return a


class ReleaseProductionBudget(IntegrationBudget):
    def __init__(self, path, *, authorization, historical_ledgers,
                 worker_lock=Path('D:/V42_UNIFIED_HEAVY_WORKER.lock')):
        require_authorization(authorization)
        self.authorization = deepcopy(authorization)
        if Path(path).resolve() != Path(authorization['authorized_ledger_path']).resolve():
            raise PermissionError('APPROVAL_BOUND_TO_ONE_CANONICAL_LEDGER_PATH')
        self.historical = [file_record(p) for p in historical_ledgers]
        if len(self.historical) < 2 or any(Path(r['path']).resolve() == Path(path).resolve() for r in self.historical):
            raise ValueError('OLD_CANONICAL_AND_CONSUMED_RC01_LEDGERS_READ_ONLY_REQUIRED')
        self.worker_lock = Path(worker_lock)
        registry = self.worker_lock.parent / '.V42_RELEASE_AUTHORIZATION_CLAIMS'
        registry.mkdir(parents=True, exist_ok=True)
        claim_path = registry / (digest(authorization['authorization_id']) + '.json')
        claim = dict(authorization_sha=digest(authorization), authorized_ledger_path=str(Path(path).resolve()))
        if claim_path.exists():
            if json.loads(claim_path.read_text(encoding='utf8')) != claim:
                raise PermissionError('AUTHORIZATION_ALREADY_CLAIMED_DIFFERENT_LEDGER_OR_POLICY')
            if not Path(path).is_file():
                raise RuntimeError('CLAIMED_NATIVE_LEDGER_MISSING_RESET_FORBIDDEN')
        else:
            if Path(path).exists():
                raise RuntimeError('EXISTING_LEDGER_WITHOUT_AUTHORIZATION_CLAIM_REQUIRES_REVIEW')
            fd = os.open(claim_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, json.dumps(claim, sort_keys=True).encode('utf8'))
                os.fsync(fd)
            finally:
                os.close(fd)
        self.context = None
        self._native_original = None
        self._admitted_model = None
        self._admitted_count = 0
        self.derived_bindings = []
        super().__init__(path, limit=float(authorization['limit_seconds']))
        identity = dict(authorization_sha=digest(authorization), historical_read_only=self.historical,
                        authorization_claim=file_record(claim_path))
        with self._transaction():
            old = self.document.get('release_identity')
            if old is not None and old != identity:
                raise ValueError('RELEASE_AUTHORIZATION_OR_HISTORICAL_LEDGER_DRIFT')
            self.document.update(release_identity=identity, authorization_document=deepcopy(authorization),
                                 worker_lock_path=str(self.worker_lock.resolve()),
                                 P2_calls=0, Worker=1, Threads=1)
        if self.document.get('active_stage_context'):
            raise RuntimeError('UNRECONCILED_STAGE_CONTEXT_REQUIRES_OFFLINE_REVIEW')

    def _lock_owner(self, kind):
        return dict(schema='V42_RELEASE_OWNED_LOCK_V1', kind=kind, pid=os.getpid(),
            nonce=uuid.uuid4().hex, ledger_path=str(self.path.resolve()),
            authorization_sha=digest(self.authorization), created_epoch_seconds=time())

    @contextmanager
    def _transaction(self):
        path = self.path.with_suffix(self.path.suffix+'.MUTATION.lock')
        owner = self._lock_owner('LEDGER_MUTATION'); data=json.dumps(owner,sort_keys=True).encode('utf8')
        began=perf_counter()
        while True:
            try:
                fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
                try:
                    os.write(fd,data);os.fsync(fd)
                finally:
                    os.close(fd)
                break
            except FileExistsError:
                if perf_counter()-began>1.:
                    raise RuntimeError('OWNED_LEDGER_MUTATION_LOCK_BUSY_RECONCILE_IF_DEAD_OWNER')
                sleep(.01)
        try:
            self._refresh()
            yield
            self._save()
        finally:
            if path.read_bytes()!=data:
                raise RuntimeError('LEDGER_MUTATION_LOCK_OWNER_CHANGED')
            path.unlink()

    def check_historical(self):
        if any(file_record(r['path']) != r for r in self.historical):
            raise ValueError('HISTORICAL_NATIVE_LEDGER_DRIFT')

    @property
    def calls(self):
        self._refresh()
        return self.document['calls']

    def bind_input_case(self, *, day, stage_case_sha, manifest):
        from .release_date_case import require_date_case
        require_date_case(manifest, stage='A1')
        if day == '2025-05-01':
            raise PermissionError('SAVED_MAY01_A1_MUST_NOT_BE_REPEATED')
        authority = dict(day=day, source_sha=manifest['source_sha'], source_identity=manifest['identity'])
        if authority not in self.authorization.get('authorized_date_cases', []):
            raise PermissionError('DATE_SOURCE_CASE_NOT_IN_NEW_APPROVAL')
        context = dict(day=day, stage='A1', stage_case_sha=stage_case_sha,
            source_sha=manifest['source_sha'], parent_result_sha=manifest['manifest_sha'])
        if context not in self.derived_bindings:
            self.derived_bindings.append(context)
        return context

    def bind_accepted_parent(self, *, day, stage, stage_case_sha, source_sha,
                             parent_result, parent_acceptance, source_identity):
        """Admit a derived case only inside the approved date/source authority.

        Stage hashes depend on the preceding real solution and cannot be known
        when a staged budget is approved. The original factory supplies the
        derived hash, while its parent must carry exact Original FULL acceptance.
        """
        from .release_p1_production import require_production_acceptance
        expected = dict(M1='A1', A2='M1', M2='A2').get(stage)
        if expected is None:
            raise ValueError('DERIVED_P1_STAGE_REQUIRED')
        require_production_acceptance(parent_acceptance, stage=expected,
                                      identity=source_identity, result=parent_result)
        authority = dict(day=day, source_sha=source_sha, source_identity=source_identity)
        if authority not in self.authorization.get('authorized_date_cases', []):
            raise PermissionError('DATE_SOURCE_CASE_NOT_IN_NEW_APPROVAL')
        context = dict(day=day, stage=stage, stage_case_sha=stage_case_sha,
                       source_sha=source_sha, parent_result_sha=digest(parent_result))
        if context not in self.derived_bindings:
            self.derived_bindings.append(context)
        return context

    @contextmanager
    def phase(self, stage, stage_case_sha, source_sha, parent_result_sha, *, day='2025-05-01'):
        if self.context is not None or stage not in STAGES:
            raise ValueError('ONE_P1_STAGE_CONTEXT_REQUIRED')
        context = dict(day=day, stage=stage, stage_case_sha=stage_case_sha,
                       source_sha=source_sha, parent_result_sha=parent_result_sha)
        if context not in self.authorization.get('allowed_stage_bindings', []) + self.derived_bindings:
            raise PermissionError('EXACT_APPROVED_SOURCE_CASE_STAGE_PARENT_REQUIRED')
        if stage not in self.authorization['stage_caps_seconds']:
            raise PermissionError('STAGE_NOT_AUTHORIZED')
        self.check_historical()
        self.context = context
        with self._transaction():
            if self.document.get('active_stage_context'):
                raise RuntimeError('UNRECONCILED_STAGE_CONTEXT')
            self.document['active_stage_context'] = deepcopy(context)
            self.document['active_stage_owner_pid'] = os.getpid()
        try:
            yield self
        finally:
            with self._transaction():
                self.document['active_stage_context'] = None
                self.document['active_stage_owner_pid'] = None
            self.context = None
            self.check_historical()

    def _stage_used(self):
        self._refresh()
        return sum(r.get('charged_seconds', r.get('measured_seconds', 0.))
                   for r in self.document['calls']
                   if r.get('stage_context', {}).get('stage') == self.context['stage']
                   and (self.authorization['stage_cap_scope'] != 'PER_DATE_STAGE'
                        or r.get('stage_context',{}).get('day') == self.context['day'])
                   and r.get('solver') != 'AC')

    def remaining(self, reserve=0.):
        available = super().remaining(reserve=max(reserve, self.authorization['return_reserve_seconds']))
        if self.context:
            return max(0., min(available, self.authorization['stage_caps_seconds'][self.context['stage']] - self._stage_used()))
        return available

    def _call_gate(self, label, *, require_remaining=True):
        if self.context is None or 'P2' in label.upper() or not label.startswith('RELEASE_P1:' + self.context['stage'] + ':'):
            raise ValueError('P1_ONLY_EXACT_STAGE_LABEL_REQUIRED')
        self.check_historical()
        if require_remaining and self.remaining() <= 0:
            raise RuntimeError('P1_STAGE_OR_TOTAL_BUDGET_EXHAUSTED')

    @contextmanager
    def capture_native_methods(self):
        """Only solve() may call optimize; presolve/IIS never run off-ledger."""
        import gurobipy as gp
        if self._native_original is not None:
            raise RuntimeError('NATIVE_GUARD_ALREADY_ACTIVE')
        original = {n: getattr(gp.Model, n) for n in ('optimize', 'presolve', 'computeIIS')}
        self._native_original = original
        def blocked(*args, **kwargs):
            raise PermissionError('UNBUDGETED_NATIVE_OR_P2_FORBIDDEN')
        def admitted(model, *args, **kwargs):
            if model is not self._admitted_model or self._admitted_count != 0:
                return blocked()
            gate=getattr(self,'_before_native_optimize',None)
            if gate is not None:gate(model)
            self._admitted_count += 1
            return original['optimize'](model, *args, **kwargs)
        gp.Model.optimize = admitted
        gp.Model.presolve = gp.Model.computeIIS = blocked
        try:
            yield self
        finally:
            for name, method in original.items():
                setattr(gp.Model, name, method)
            self._native_original = None

    def solve(self, model, *, label, cap, callback=None, binding=None):
        self._call_gate(label)
        if self._native_original is None:
            raise PermissionError('GUARDED_PRODUCTION_NATIVE_CONTEXT_REQUIRED')
        if not math.isfinite(float(cap)) or cap <= 0:
            raise ValueError('FINITE_POSITIVE_NATIVE_CAP_REQUIRED')
        model.Params.Threads = 1
        actual = native_binding(model)
        if binding is not None and binding != actual:
            raise ValueError('EXACT_NATIVE_MATRIX_DOMAIN_OBJECTIVE_BINDING_REQUIRED')
        if actual['Threads'] != 1 or actual['objective_sense'] != 1 or int(model.NumObj) != 1:
            raise ValueError('SINGLE_ORIGINAL_P1_MINIMIZATION_REQUIRED')
        snapshot = resource_snapshot()
        if snapshot['memory']['AvailableMBytes'] < 8192 or snapshot['memory']['PercentCommittedBytesInUse'] >= 75:
            raise RuntimeError('RELEASE_RAM_COMMIT_GATE')
        fd = os.open(self.worker_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        owner=self._lock_owner('HEAVY_WORKER'); lock_bytes=json.dumps(owner,sort_keys=True).encode('utf8')
        try:
            os.write(fd,lock_bytes);os.fsync(fd)
        finally:
            os.close(fd)
        context = deepcopy(self.context)
        try:
            with self.lock:
                seconds = min(float(cap), self.remaining())
                if seconds <= 0:
                    raise RuntimeError('P1_STAGE_OR_TOTAL_BUDGET_EXHAUSTED')
                model.Params.TimeLimit = seconds
                # Source, matrix, parent and cost are committed together. There
                # is no post-call window in which stage cost can be omitted.
                with self._transaction():
                    if self.document['inflight'] is not None:
                        raise RuntimeError('UNRECONCILED_SOLVER_CALL')
                    self.document['inflight'] = dict(label=label, cap=seconds, pid=os.getpid(),
                        stage_context=context, native_binding=actual, started_epoch_seconds=time(),
                        worker_lock_owner=owner,worker_lock_record=file_record(self.worker_lock))
                self._admitted_model, self._admitted_count = model, 0
                began = perf_counter(); error = None
                try:
                    if callback is None:
                        model.optimize()
                    else:
                        model.optimize(callback)
                except BaseException as exc:
                    error = repr(exc)
                    raise
                finally:
                    wall = perf_counter()-began
                    try:
                        runtime = float(model.Runtime)
                    except Exception:
                        runtime = None
                    if runtime is not None and (not math.isfinite(runtime) or runtime < 0):
                        runtime = None
                    try:
                        status = int(model.Status)
                    except Exception:
                        status = None
                    entered=self._admitted_count>0
                    prior_status=status
                    if not entered:
                        runtime=0.;status=None
                    charge = runtime if runtime is not None else wall
                    row = dict(label=label, solver='GUROBI', Native_Runtime=runtime,
                        wall_seconds=wall, charged_seconds=charge, cap_seconds=seconds,
                        overshoot_seconds=max(0.,charge-seconds), error=error, status=status,
                        stage_context=context, native_binding=actual, resource_before_solve=snapshot,
                        P2_call=False, objective_scope='ORIGINAL_P1_CURRENT_MATRIX_NOT_UNPRICED_GLOBAL_CERTIFICATE')
                    row['native_execution_entered']=entered
                    if not entered:row['pre_native_model_status']=prior_status
                    with self._transaction():
                        self.document['calls'].append(row)
                        self.document['Gurobi_Native_seconds'] += runtime or 0.
                        self.document['conservative_solve_seconds'] += charge
                        self.document['inflight'] = None
                return row
        finally:
            self._admitted_model = None
            if self.worker_lock.read_bytes()!=lock_bytes:
                raise RuntimeError('HEAVY_WORKER_LOCK_OWNER_CHANGED')
            self.worker_lock.unlink()
            self.check_historical()

    def native_optimize(self, model, callback=None, *, component='UB', track='M', label='', requested_seconds=None):
        if 'P2' in (str(component)+str(track)+str(label)).upper():
            raise ValueError('RELEASE_P2_ABSOLUTELY_FORBIDDEN')
        if self.context is None:
            raise ValueError('P1_ONLY_EXACT_STAGE_LABEL_REQUIRED')
        return self.solve(model, label='RELEASE_P1:' + self.context['stage'] + ':' + track + ':' + label,
                          cap=self.remaining() if requested_seconds is None else requested_seconds, callback=callback)

    def record_external(self, label, seconds, *, solver='OTHER', status='COMPLETED'):
        self._call_gate(label, require_remaining=False)
        if solver != 'AC' and seconds > self.remaining() + 1e-7:
            # Work already happened: always charge the measured overshoot.
            status = status + ':STAGE_CAP_OVERSHOOT'
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('MEASURED_SOLVE_COST_REQUIRED')
        row = dict(label=label, solver=solver, status=status, measured_seconds=seconds,
                   stage_context=deepcopy(self.context), P2_call=False)
        with self.lock, self._transaction():
            self.document['calls'].append(row)
            if solver == 'AC':
                self.document['AC_wall_seconds'] += seconds
            else:
                self.document['other_solver_wall_seconds'] += seconds
                self.document['conservative_solve_seconds'] += seconds
        return row

    @contextmanager
    def cost(self, label, *, solver='AC', **kwargs):
        self._call_gate(label)
        began = perf_counter()
        try:
            yield
        finally:
            self.record_external(label, perf_counter() - began, solver=solver)


def reconcile_interrupted_ledger(path, *, evidence, charge_seconds):
    """Offline only: preserve the unknown call and conservatively charge it.

    The caller must establish the original PID has exited and supply a durable
    solver-log/process-exit receipt. Never silently retry an interrupted call.
    """
    import json
    import psutil
    path = Path(path)
    d = json.loads(path.read_text(encoding='utf8'))
    call = d.get('inflight')
    context = d.get('active_stage_context')
    pid = call['pid'] if call else d.get('active_stage_owner_pid')
    if (not (call or context) or pid is None or psutil.pid_exists(pid) or not evidence
            or not math.isfinite(charge_seconds) or charge_seconds < 0):
        raise ValueError('EXIT_EVIDENCE_AND_CONSERVATIVE_INTERRUPTION_CHARGE_REQUIRED')
    if call:
        minimum = max(call['cap'],time()-call.get('started_epoch_seconds',time()))
    else:
        # HiGHS may have run before its return receipt. Without a durable
        # inflight native call, consume the unaccounted remainder of this stage.
        stage = context['stage']
        used = sum(r.get('charged_seconds',r.get('measured_seconds',0.)) for r in d['calls']
                   if r.get('stage_context',{}).get('stage') == stage and r.get('solver') != 'AC'
                   and (d['authorization_document']['stage_cap_scope'] != 'PER_DATE_STAGE'
                        or r.get('stage_context',{}).get('day') == context['day']))
        minimum = max(0.,d['authorization_document']['stage_caps_seconds'][stage]-used)
    if charge_seconds < minimum:
        raise ValueError('EXIT_EVIDENCE_AND_CONSERVATIVE_INTERRUPTION_CHARGE_REQUIRED')
    d['calls'].append(dict(label=call['label'] if call else 'UNLOGGED_INTERRUPTED_STAGE_WORK',
        solver='GUROBI_INTERRUPTED' if call else 'UNLOGGED_SOLVER_INTERRUPTED', Native_Runtime=None,
        charged_seconds=charge_seconds, status='INTERRUPTED_NOT_CERTIFIED', evidence=evidence,
        stage_context=(call.get('stage_context') or context) if call else context,
        interrupted_call=call))
    d['conservative_solve_seconds'] += charge_seconds
    d['inflight'] = None
    d['active_stage_context'] = None
    d['active_stage_owner_pid'] = None
    temporary = path.with_suffix('.reconciled.tmp')
    temporary.write_text(json.dumps(d, indent=2, allow_nan=False), encoding='utf8')
    os.replace(temporary, path)
    return d


def reclaim_stale_release_locks(path, *, evidence):
    """Explicit offline recovery of this ledger's dead owned locks only.

    PID-only historical locks and empty historical mutation locks are refused.
    This does not erase an inflight debt or authorize a solver retry.
    """
    import psutil
    path=Path(path).resolve()
    d=json.loads(path.read_text(encoding='utf8'))
    authorization=d['authorization_document']
    if (not evidence or Path(authorization['authorized_ledger_path']).resolve()!=path
            or digest(authorization)!=d['release_identity']['authorization_sha']):
        raise ValueError('EXACT_APPROVED_LEDGER_AND_EXIT_EVIDENCE_REQUIRED')
    candidates=[(path.with_suffix(path.suffix+'.MUTATION.lock'),'LEDGER_MUTATION'),
                (Path(d['worker_lock_path']),'HEAVY_WORKER')]
    recovered=[]
    for lock,kind in candidates:
        if not lock.exists():
            continue
        data=lock.read_bytes()
        try:
            owner=json.loads(data)
        except (ValueError,UnicodeDecodeError):
            raise ValueError('UNOWNED_OR_HISTORICAL_LOCK_MUST_NOT_BE_REMOVED')
        if not isinstance(owner,dict):
            raise ValueError('UNOWNED_OR_HISTORICAL_LOCK_MUST_NOT_BE_REMOVED')
        if (owner.get('schema')!='V42_RELEASE_OWNED_LOCK_V1' or owner.get('kind')!=kind
                or owner.get('ledger_path')!=str(path)
                or owner.get('authorization_sha')!=digest(authorization)
                or not owner.get('nonce') or psutil.pid_exists(owner['pid'])):
            raise ValueError('DEAD_EXACT_LEDGER_LOCK_OWNER_REQUIRED')
        record=file_record(lock)
        if lock.read_bytes()!=data:
            raise RuntimeError('LOCK_CHANGED_DURING_OFFLINE_RECOVERY')
        # Save recovery evidence before removing this one verified file.
        receipt=path.with_suffix(path.suffix+'.LOCK_RECOVERY.'+owner['nonce']+'.json')
        if receipt.exists():
            raise FileExistsError('LOCK_RECOVERY_RECEIPT_MUST_NOT_OVERWRITE')
        receipt.write_text(json.dumps(dict(lock=record,owner=owner,evidence=evidence,
            debt_not_reconciled_by_lock_recovery=True),indent=2),encoding='utf8')
        lock.unlink();recovered.append(file_record(receipt))
    return recovered
