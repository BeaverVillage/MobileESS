"""One budget-preserving continuation of the persisted optimal Phase-I point.

Repairs only receipt path length. It never repeats the 268.62s master solve or
the already optimal first block solve. Prior source/gate/raw bytes stay intact.
"""
from pathlib import Path
import shutil
import numpy as np
import gurobipy as gp
from v42_pr134_b1.common import read,record,atomic
from .native import Native
from .setup import OUT,STATIC,POLICY

SUFFIX='_CONTINUATION_001'


def prior_ledger():
    ledger=read(OUT/'MAY19/NATIVE_CALLS.json');result=read(OUT/'MAY19/PHASE1_RESULT.json')
    calls=ledger['calls'];used=sum(c['native_seconds'] or 0 for c in calls)
    if abs(used-ledger['cumulative_native_seconds'])>1e-8 or abs(used-result['native_seconds'])>1e-8:
        raise ValueError('PRIOR_NATIVE_BUDGET_LEDGER_MISMATCH')
    return calls,used,result['pricing_wall_seconds']


def authorize():
    if (OUT/'MAY19/C1/STARTED.json').exists():raise PermissionError('CONTINUATION_ALREADY_STARTED')
    calls,used,wall=prior_ledger()
    if calls[0]['component']!='PHASE_I' or calls[0]['status']!=gp.GRB.OPTIMAL:
        raise PermissionError('PERSISTED_OPTIMAL_MASTER_REQUIRED')
    original=read(OUT/'PHASE1_SOURCE_FREEZE.json')
    for name in ('core.py','producer.py','backend.py','oracle.py','setup.py','qualify.py'):
        r=next(r for r in original['source_files'] if Path(r['path']).parts[-2:]==('v42_a_stage_phase1',name))
        if record(r['path'])!=r:raise PermissionError('PRICING_OR_PHYSICAL_MATH_CHANGED_DURING_IO_REPAIR')
    atomic(OUT/'CONTINUATION_AUTHORITY.json',dict(PASS=True,reason='Windows atomic temporary path exceeded MAX_PATH',
        prior_native_calls=record(OUT/'MAY19/NATIVE_CALLS.json'),prior_result=record(OUT/'MAY19/PHASE1_RESULT.json'),
        prior_source_freeze=record(OUT/'PHASE1_SOURCE_FREEZE.json'),prior_native_seconds=used,prior_pricing_wall_seconds=wall,
        remaining_native_seconds=POLICY['cumulative_native_seconds']-used,policy_unchanged=True,
        weights_unchanged=True,physics_and_pricing_math_sources_unchanged=True,repeat_master_optimize=False,
        repeat_already_optimal_block_optimize=False,reset_or_extra_budget=False,continuation_only_one_shot=True))


class ResumedNative(Native):
    def __init__(self):
        super().__init__(permit_path=OUT/('CANARY_EXECUTION_PERMIT'+SUFFIX+'.json'),
            freeze_path=OUT/('PHASE1_SOURCE_FREEZE'+SUFFIX+'.json'))
        calls,used,wall=prior_ledger();self.calls=list(calls);self.prior=list(calls)
        self.native_seconds=used;self.pricing_wall_seconds=wall
        import csv
        resource_path=OUT/'MAY19/RESOURCE_TELEMETRY.csv'
        if resource_path.exists():
            with resource_path.open(encoding='utf8') as f:self.resources=list(csv.DictReader(f))

    def reuse(self,call,snapshot,folder):
        identity=read(call['model_identity']['path'])
        if snapshot.fingerprint()!=identity['original_snapshot_sha256']:
            raise ValueError('PERSISTED_NATIVE_SNAPSHOT_REUSE_MISMATCH')
        for r in (call['raw_attributes'],identity['matrix'],identity['attributes'],identity['source_manifest']):
            if record(r['path'])!=r:raise ValueError('PERSISTED_NATIVE_REUSE_BYTE_DRIFT')
        point=np.load(call['raw_attributes']['path']);raw={k:point[k] for k in point.files}
        atomic(Path(folder)/'REUSED_NATIVE_POINT.json',dict(PASS=True,original_call=call,
            original_snapshot_sha256=snapshot.fingerprint(),actual_extra_native_seconds=0,raw_arrays_not_modified=True))
        return call,raw

    def cached_master(self,snapshot,folder):return self.reuse(self.prior[0],snapshot,folder)

    def solve(self,snapshot,folder,component):
        for call in self.prior:
            if call['component']==component and call['status']==gp.GRB.OPTIMAL:
                if read(call['model_identity']['path'])['original_snapshot_sha256']==snapshot.fingerprint():
                    return self.reuse(call,snapshot,folder)
        return super().solve(snapshot,folder,component)


def resume():
    marker=OUT/'MAY19/C1/STARTED.json'
    if marker.exists():raise PermissionError('CONTINUATION_ALREADY_STARTED_NO_AUTOMATIC_RERUN')
    authority=read(OUT/'CONTINUATION_AUTHORITY.json')
    for name in ('prior_native_calls','prior_result','prior_source_freeze'):
        if record(authority[name]['path'])!=authority[name]:raise PermissionError('CONTINUATION_PRIOR_LEDGER_DRIFT')
    native=ResumedNative();native.verify()
    preserve=OUT/'MAY19/ATTEMPT_001';preserve.mkdir(parents=True,exist_ok=True)
    for name in ('PHASE1_RESULT.json','NATIVE_CALLS.json','PHASE1_ITERATION_TRACE.csv','SPEED_GATE_V2.json',
        'PHASE1_CLOSURE_CERTIFICATE.json','ORIGINAL_LP_RESULT.json','PRICING_TIME_TRACE.csv','RESOURCE_TELEMETRY.csv'):
        source=OUT/'MAY19'/name
        if source.exists():shutil.copyfile(source,preserve/name)
    atomic(marker,dict(PASS=True,authority=record(OUT/'CONTINUATION_AUTHORITY.json'),
        source_freeze=record(native.freeze_path),prior_native_seconds=native.native_seconds,
        original_master_and_first_pricing_raw_preserved=True))
    from .runner import run
    return run(resumed_native=native)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=('authorize','tests','freeze','run'));a=p.parse_args()
    from .prepare import test_receipts,freeze
    {'authorize':authorize,'tests':lambda:test_receipts(SUFFIX),'freeze':lambda:freeze(SUFFIX),'run':resume}[a.action]()
