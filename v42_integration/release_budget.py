"""Exactly one user-authorized A1 P1 call on a separate, durable ledger."""
from pathlib import Path
import os

from .budget import IntegrationBudget
from .m_engine import file_record
from .unified_contract import digest
from .partial_canary import resource_snapshot


class ReleaseP1Budget(IntegrationBudget):
    def __init__(self,path,*,authorization,canonical_ledger):
        if (authorization.get('scope')!='D0_A1_P1_EXACTLY_ONE_CALL'
                or authorization.get('limit_seconds')!=180. or authorization.get('call_cap_seconds')!=120.
                or authorization.get('return_reserve_seconds')!=30. or authorization.get('overshoot_buffer_seconds')!=30.
                or authorization.get('max_optimize_calls')!=1 or authorization.get('Threads')!=1):
            raise ValueError('EXACT_USER_RELEASE_P1_AUTHORIZATION_REQUIRED')
        self.authorization=authorization;self.canonical=Path(canonical_ledger)
        self.original_canonical=file_record(self.canonical)
        super().__init__(path,limit=180.)
        with self._transaction():
            existing=self.document.get('authorization_sha')
            if existing is not None and existing!=digest(authorization):raise ValueError('AUTHORIZATION_MUST_NOT_CHANGE')
            if self.document.get('canonical_ledger_read_only',self.original_canonical)!=self.original_canonical:
                raise ValueError('HISTORICAL_NATIVE_LEDGER_DRIFT')
            self.document.update(authorization_sha=digest(authorization),authorization=authorization,
                canonical_ledger_read_only=self.original_canonical)

    def validate_call(self,*,label,cap,binding):
        self._refresh()
        if (label!='D0_A1_P1_RELEASE_120_20261015' or cap!=120. or binding!=self.authorization['native_binding']
                or binding['Threads']!=1 or binding['objective_sense']!=1):
            raise ValueError('EXACT_P1_MODEL_LABEL_CAP_REQUIRED')
        if self.document.get('authorization_consumed') or self.document['calls'] or self.document['inflight']:
            raise RuntimeError('ONE_AUTHORIZED_OPTIMIZE_ALREADY_CONSUMED')
        if self.remaining(reserve=30.)<cap:raise RuntimeError('RETURN_RESERVE_GATE')
        if file_record(self.canonical)!=self.original_canonical:raise ValueError('HISTORICAL_NATIVE_LEDGER_DRIFT')

    def solve(self,model,*,label,cap,callback=None):
        from .d0_resource import native_binding
        binding=native_binding(model)
        self.validate_call(label=label,cap=cap,binding=binding)
        snapshot=resource_snapshot();memory=snapshot['memory']
        if memory['AvailableMBytes']<8192 or memory['PercentCommittedBytesInUse']>=75:
            raise RuntimeError('RELEASE_RAM_COMMIT_GATE')
        # The original shared cross-directory lock protects every V42 ledger.
        lock=Path('D:/V42_UNIFIED_HEAVY_WORKER.lock')
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
        try:
            with self._transaction():
                if self.document.get('authorization_consumed'):raise RuntimeError('ONE_AUTHORIZED_OPTIMIZE_ALREADY_CONSUMED')
                self.document.update(authorization_consumed=True,resource_before_solve=snapshot,native_binding=binding)
            try:return super().solve(model,label=label,cap=cap,callback=callback)
            finally:
                if file_record(self.canonical)!=self.original_canonical:raise ValueError('HISTORICAL_NATIVE_LEDGER_DRIFT')
        finally:lock.unlink()
