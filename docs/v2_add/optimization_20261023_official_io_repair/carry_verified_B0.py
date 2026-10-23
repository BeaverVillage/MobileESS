"""Retain exact completed B0 receipts across an audited IO-only revision."""
from pathlib import Path
from v2_add_preflight.stage_common import OUT,read,record,day_inputs
from v2_add_preflight.prestart_execution import atomic
from v2_add_preflight.stage_campaign import source_files,validate
from v2_add_preflight.stage_budget import policy
from v2_add_preflight.stage_checkpoint import restore,seal
from v42_native.contracts import digest

def prepare(destination,previous,work,*,verify_only=False):
    destination=Path(destination);previous=Path(previous);work=Path(work)
    if destination.exists():raise FileExistsError('NEW_IO_REPAIRED_ROOT_REQUIRED')
    old=read(previous/'CAMPAIGN_INPUT_IDENTITY.json')
    frozen=dict(source_files=source_files(),hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'),
        input_files=day_inputs()['files'],budget_policy=policy())
    audit=read(work/'OFFICIAL_IO_REPAIR_20261023/SOURCE_COMPATIBILITY.json')
    assert audit['PASS'] and old['source_files'] in audit['compatible_previous_source_snapshots']
    assert audit['after_source_files']==frozen['source_files']
    assert {k:v for k,v in old.items() if k!='source_files'}=={k:v for k,v in frozen.items() if k!='source_files'}
    # Neither failed official stage entered Native. Their receipts stay in
    # the original runtime; a paid or inflight account cannot be reset here.
    a=read(previous/'2025-05-01/B1/A1/NATIVE_RUNTIME_LEDGER.json')
    assert a['calls']==[] and a['inflight'] is None and a['measured_Native_Runtime']==0.
    for name in ('K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json'):
        for path in previous.rglob(name):
            value=read(path)
            assert value['calls']==[] and value['inflight'] is None and value['measured_Native_Runtime']==0.
    verified=[]
    completed=[('B0',stage) for stage in ('REFERENCE','ACTUAL','FRESH')]+[('B2','REFERENCE')]
    for arm,stage in completed:
        path=previous/'2025-05-01'/arm/stage/'CHECKPOINT.json'
        old_key=dict(campaign_identity=digest(old),day='2025-05-01',arm=arm,stage=stage)
        result=restore(path,old_key);validate(stage,result)
        verified.append((arm,stage,path,result,read(path)['files']))
    evidence=dict(PASS=True,previous_root=str(previous),destination=str(destination),
        original_checkpoints=[record(row[2]) for row in verified],completed_stages=completed,
        IO_only_source_audit=record(work/'OFFICIAL_IO_REPAIR_20261023/SOURCE_COMPATIBILITY.json'),
        same_hardware_input_budget=True,prior_B0_files_independently_rehashed=True,
        B0_recalculated=False,failed_A1_and_K48_Native_calls=0,Native_clock_reset=False,
        old_failures_and_ledgers_preserved=True,producer=record(__file__))
    receipt=work/'OFFICIAL_IO_REPAIR_20261023/B0_CONTINUATION_VERIFICATION.json';atomic(receipt,evidence)
    if verify_only:return evidence
    destination.mkdir(parents=True);atomic(destination/'CAMPAIGN_INPUT_IDENTITY.json',frozen)
    for arm,stage,path,result,files in verified:
        key=dict(campaign_identity=digest(frozen),day='2025-05-01',arm=arm,stage=stage)
        seal(destination/'2025-05-01'/arm/stage/'CHECKPOINT.json',key,result,[*files,record(path),record(receipt)])
    return evidence
