"""Table V: cumulative Native time per arm/stage, without a total cap.

Reuse the production native guard, matrix binding, owned locks and atomic
accounting. Other solver, build, forecast and AC costs never consume Native.
K48 uses its own authorization and ledger.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import threading
from time import perf_counter

from .release_production_budget import ReleaseProductionBudget
from .m_engine import file_record
from .unified_contract import digest

SCHEMA = 'TABLE_V_ARM_STAGE_NATIVE_ONLY_AUTHORIZATION_V1'
MAIN_CAPS = {'B1:A1': 5400., 'B2:M1': 1800., 'B3:A1': 5400.,
             'B3:M1': 1800., 'B3:A2': 5400., 'B3:M2': 1800.}
K48_CAPS = {'B2:K48_M1': 300., 'B3:K48_M1': 300., 'B3:K48_M2': 300.}


def require_authorization(a):
    expected = K48_CAPS if a.get('budget_kind') == 'K48_SEPARATE' else MAIN_CAPS
    if (a.get('schema') != SCHEMA or a.get('approved') is not True
            or a.get('budget_kind') not in ('PLANNING_NATIVE', 'K48_SEPARATE')
            or a.get('stage_caps_seconds') != expected
            or a.get('total_limit_seconds') is not None
            or a.get('total_limit_enabled') is not False
            or a.get('timeout_basis') != 'CUMULATIVE_GUROBI_NATIVE_OPTIMIZE_PER_ARM_STAGE'
            or a.get('P2_calls') != 0 or a.get('Worker') != 1 or a.get('Threads') != 1
            or not a.get('authorization_id') or not a.get('authorized_ledger_path')
            or not a.get('human_approval_reference') or not a.get('source_cases')):
        raise PermissionError('EXPLICIT_TABLE_V_STAGE_ONLY_AUTHORIZATION_REQUIRED')
    return a


class TableVStageBudget(ReleaseProductionBudget):
    def __init__(self, path, *, authorization, historical_ledgers,
                 worker_lock=Path('D:/V42_UNIFIED_HEAVY_WORKER.lock')):
        require_authorization(authorization)
        self.authorization = deepcopy(authorization)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        carried=[];carry_parents=[]
        for record in authorization.get('carry_forward_ledgers',[]):
            if file_record(record['path'])!=record or any(r['path']==record['path'] for r in carry_parents):
                raise ValueError('EXACT_DISTINCT_PREDECESSOR_NATIVE_LEDGER_REQUIRED')
            prior=json.loads(Path(record['path']).read_text(encoding='utf8'))
            if (prior.get('schema')!='TABLE_V_NATIVE_STAGE_LEDGER_V1'
                    or prior.get('inflight') or prior.get('active_stage_context')
                    or prior['authorization_document'].get('budget_kind')!=authorization['budget_kind']
                    or prior['authorization_document'].get('stage_caps_seconds')!=authorization['stage_caps_seconds']):
                raise ValueError('COMPLETED_SAME_ARM_STAGE_AUTHORITY_PREDECESSOR_REQUIRED')
            for index,row in enumerate(prior['calls']):
                if not row.get('solver','').startswith('GUROBI'):continue
                runtime=row.get('Native_Runtime');c=row.get('stage_context',{})
                if (type(runtime) not in (int,float) or not math.isfinite(runtime) or runtime<0
                        or c.get('day')!='2025-05-01'
                        or c.get('arm','')+':'+c.get('stage','') not in authorization['stage_caps_seconds']):
                    raise ValueError('KNOWN_NATIVE_RUNTIME_AND_ORIGINAL_ARM_STAGE_REQUIRED')
                copied=deepcopy(row)
                copied['carried_forward_from']=dict(ledger=record,row_index=index,row_sha=digest(row))
                carried.append(copied)
            carry_parents.append(record)
        if self.path.resolve() != Path(authorization['authorized_ledger_path']).resolve():
            raise PermissionError('APPROVAL_BOUND_TO_ONE_CANONICAL_LEDGER_PATH')
        self.historical = [file_record(p) for p in historical_ledgers]
        self.historical += [r for r in carry_parents if r not in self.historical]
        if len(self.historical) < 2 or any(Path(r['path']).resolve() == self.path.resolve() for r in self.historical):
            raise ValueError('OLD_CANONICAL_AND_CONSUMED_RC01_LEDGERS_READ_ONLY_REQUIRED')
        self.worker_lock = Path(worker_lock)
        registry = self.worker_lock.parent / '.V42_TABLE_V_AUTHORIZATION_CLAIMS'
        registry.mkdir(parents=True, exist_ok=True)
        claim_path = registry / (digest(authorization['authorization_id']) + '.json')
        claim = dict(authorization_sha=digest(authorization), authorized_ledger_path=str(self.path.resolve()))
        if claim_path.exists():
            if json.loads(claim_path.read_text(encoding='utf8')) != claim:
                raise PermissionError('AUTHORIZATION_ALREADY_CLAIMED_DIFFERENT_LEDGER_OR_POLICY')
            if not self.path.is_file():
                raise RuntimeError('CLAIMED_NATIVE_LEDGER_MISSING_RESET_FORBIDDEN')
        else:
            if self.path.exists():
                raise RuntimeError('EXISTING_LEDGER_WITHOUT_AUTHORIZATION_CLAIM_REQUIRES_REVIEW')
            fd = os.open(claim_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, json.dumps(claim, sort_keys=True).encode('utf8'))
                os.fsync(fd)
            finally:
                os.close(fd)
        self.lock = threading.RLock()
        self.context = None
        self.arm = None
        self._native_original = self._admitted_model = None
        self._admitted_count = 0
        self.derived_bindings = []
        identity = dict(authorization_sha=digest(authorization), historical_read_only=self.historical,
                        authorization_claim=file_record(claim_path))
        if self.path.exists():
            self._refresh()
            if self.document.get('release_identity') != identity:
                raise ValueError('TABLE_V_AUTHORIZATION_OR_HISTORY_DRIFT')
            if self.document.get('inflight') or self.document.get('active_stage_context'):
                raise RuntimeError('UNRECONCILED_NATIVE_OR_STAGE_CONTEXT')
        else:
            self.document = dict(schema='TABLE_V_NATIVE_STAGE_LEDGER_V1', limit_seconds=None,
                total_limit_enabled=False, calls=carried, inflight=None, active_stage_context=None,
                Gurobi_Native_seconds=sum(r['Native_Runtime'] for r in carried), other_solver_wall_seconds=0.,
                conservative_solve_seconds=sum(r['Native_Runtime'] for r in carried), AC_wall_seconds=0.,
                carried_forward_predecessors=carry_parents, prior_arm_stage_costs_reset=False,
                historical_ledgers_merged=False, release_identity=identity,
                authorization_document=deepcopy(authorization),
                worker_lock_path=str(self.worker_lock.resolve()), P2_calls=0, Worker=1, Threads=1)
            self._save()
        self.check_historical()

    @contextmanager
    def arm_context(self, arm):
        if arm not in ('B1', 'B2', 'B3') or self.arm is not None or self.context is not None:
            raise ValueError('ONE_TABLE_V_OPTIMIZED_ARM_REQUIRED')
        self.arm = arm
        try:
            yield self
        finally:
            self.arm = None

    def bind_table_v_case(self, *, arm, stage, stage_case_sha, source_sha,
                          parent_result, source_identity, parent_acceptance=None,
                          case_certificate=None):
        if f'{arm}:{stage}' not in self.authorization['stage_caps_seconds']:
            raise PermissionError('ARM_STAGE_NOT_AUTHORIZED')
        authority = dict(day='2025-05-01', source_sha=source_sha, source_identity=source_identity)
        if authority not in self.authorization['source_cases']:
            raise PermissionError('EXACT_TABLE_V_SOURCE_CASE_AUTHORITY_REQUIRED')
        if not stage_case_sha:
            raise ValueError('CURRENT_ORIGINAL_STAGE_CASE_REQUIRED')
        if stage == 'A1':
            from .table_v_flex_planning import require_flex_case
            manifest = require_flex_case(case_certificate or {}, stage=stage)
            if (manifest['identity'] != source_identity or manifest['source_sha'] != source_sha
                    or parent_result != manifest):
                raise ValueError('FULL_FLEX_A1_MANIFEST_PARENT_REQUIRED')
        elif stage in ('M1', 'M2'):
            from .table_v_mess import require_aidc_anchor
            require_aidc_anchor(parent_result, sorted(parent_result['AIDC_P_by_site']))
            if arm == 'B2':
                from .table_v_reference import require_reference_acceptance
                require_reference_acceptance(parent_acceptance, identity=source_identity, result=parent_result)
            else:
                from .release_p1_acceptance import require_acceptance
                require_acceptance(parent_acceptance, stage='A1' if stage == 'M1' else 'A2',
                                   source_identity=source_identity, result=parent_result)
                if parent_acceptance.get('evidence_scope') != 'REAL_PRODUCTION':
                    raise ValueError('REAL_CURRENT_A_PARENT_REQUIRED')
        else:
            from .table_v_mess import require_m_acceptance
            require_m_acceptance(parent_acceptance, result=parent_result, identity=source_identity,
                                 arm=arm, stage='M1' if stage in ('A2', 'K48_M1') else 'M2')
        context = dict(day='2025-05-01', arm=arm, stage=stage, stage_case_sha=stage_case_sha,
                       source_sha=source_sha, parent_result_sha=digest(parent_result))
        if context not in self.derived_bindings:
            self.derived_bindings.append(context)
        return context

    @contextmanager
    def phase(self, stage, stage_case_sha, source_sha, parent_result_sha, *, day='2025-05-01'):
        context = dict(day=day, arm=self.arm, stage=stage, stage_case_sha=stage_case_sha,
                       source_sha=source_sha, parent_result_sha=parent_result_sha)
        if self.context is not None or self.arm is None:
            raise ValueError('ONE_EXACT_ARM_STAGE_CONTEXT_REQUIRED')
        if context not in self.derived_bindings:
            raise PermissionError('EXACT_APPROVED_SOURCE_CASE_STAGE_PARENT_REQUIRED')
        self.check_historical()
        with self._transaction():
            if self.document.get('active_stage_context') or self.document.get('inflight'):
                raise RuntimeError('UNRECONCILED_STAGE_CONTEXT')
            self.document['active_stage_context'] = deepcopy(context)
            self.document['active_stage_owner_pid'] = os.getpid()
        self.context = context
        try:
            yield self
        finally:
            with self._transaction():
                self.document['active_stage_context'] = None
                self.document['active_stage_owner_pid'] = None
            self.context = None
            self.check_historical()

    def used(self):
        self._refresh()
        return sum(r['Native_Runtime'] for r in self.document['calls']
                   if r.get('solver') == 'GUROBI' and r.get('Native_Runtime') is not None)

    def remaining(self, reserve=0.):
        if self.context is None:
            raise ValueError('ARM_STAGE_CONTEXT_REQUIRED_FOR_REMAINING')
        self._refresh()
        rows = [r for r in self.document['calls'] if r.get('solver', '').startswith('GUROBI')
                and all(r.get('stage_context', {}).get(k) == self.context[k] for k in ('day','arm','stage'))]
        if any(r.get('Native_Runtime') is None for r in rows):
            raise RuntimeError('UNKNOWN_NATIVE_RUNTIME_REQUIRES_OFFLINE_RECONCILIATION')
        cap = self.authorization['stage_caps_seconds'][self.context['arm']+':'+self.context['stage']]
        return max(0., cap-sum(r['Native_Runtime'] for r in rows))

    def _call_gate(self, label, *, require_remaining=True):
        if (self.context is None or 'P2' in label.upper()
                or not label.startswith('RELEASE_P1:'+self.context['stage']+':')):
            raise ValueError('P1_ONLY_EXACT_ARM_STAGE_LABEL_REQUIRED')
        self.check_historical()
        if require_remaining and self.remaining() <= 0:
            raise RuntimeError('ARM_STAGE_NATIVE_TIMEOUT_EXHAUSTED')

    def record_external(self, label, seconds, *, solver='OTHER', status='COMPLETED'):
        self._call_gate(label, require_remaining=False)
        if solver.upper().startswith('GUROBI') or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('MEASURED_NON_NATIVE_EXTERNAL_COST_REQUIRED')
        row = dict(label=label, solver=solver, status=status, measured_seconds=seconds,
                   stage_context=deepcopy(self.context), P2_call=False, consumes_native_timeout=False)
        with self.lock, self._transaction():
            self.document['calls'].append(row)
            key = 'AC_wall_seconds' if solver == 'AC' else 'other_solver_wall_seconds'
            self.document[key] += seconds
        return row

    @contextmanager
    def cost(self, label, *, solver='AC', **kwargs):
        self._call_gate(label, require_remaining=False)
        began = perf_counter()
        try:
            yield
        finally:
            self.record_external(label, perf_counter()-began, solver=solver)
