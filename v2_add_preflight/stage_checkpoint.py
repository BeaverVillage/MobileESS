"""Owned immutable stage receipts and reconciled measured-budget admission."""
from pathlib import Path
import math
from .stage_common import read,record
from .prestart_execution import atomic
from v42_native.contracts import digest


def seal(path,identity,result,artifacts):
    files=list({r['path']:r for r in artifacts}.values())
    for item in files:
        if record(item['path'])!=item:raise ValueError('CHECKPOINT_FILE_DRIFT')
    value=dict(identity=identity,status='COMPLETE',result=result,files=files)
    value['checkpoint_sha']=digest(value);atomic(path,value);return value


def restore(path,identity):
    value=read(path)
    if (value['identity']!=identity or value.get('status')!='COMPLETE'
            or digest({k:v for k,v in value.items() if k!='checkpoint_sha'})!=value['checkpoint_sha']):
        raise ValueError('CHECKPOINT_IDENTITY_OR_RESULT_DRIFT')
    for item in value['files']:
        if record(item['path'])!=item:raise ValueError('CHECKPOINT_ARTIFACT_DRIFT')
    return value['result']


def reconciled(path,ceiling,context=None):
    from v44.checkpoints import ledger_state
    return ledger_state(path,ceiling=ceiling,context=context)


def binary_manifest(case,root,anchor):
    root=Path(root)
    value=dict(stage=case.identity['stage'],arm=case.identity['arm'],case_sha=case.case_sha,
        identity=case.identity,root=str(root.resolve()),pack=str(case.raw_pack.resolve()),
        reference=str(case._blocks.reference_proof.resolve()),view=str(case._blocks.view_root.resolve()),anchor=anchor,
        files=[record(p) for p in case._immutable_file_stats],
        proof_files=list(getattr(case,'_construction_evidence',{}).values()),
        Native_clock_reset=False,B_and_B_search_state='NOT_SUPPORTED')
    value['manifest_sha']=digest(value);return value


def load_binary(value,output):
    if digest({k:v for k,v in value.items() if k!='manifest_sha'})!=value['manifest_sha']:raise ValueError('M_BINARY_MANIFEST_DRIFT')
    for item in value['files']+value['proof_files']:
        if record(item['path'])!=item:raise ValueError('M_BINARY_FILE_DRIFT')
    from .stage_m_case import build_case
    case=build_case(value['stage'],current_root=value['root'],current_pack=value['pack'],
        current_proof=value['reference'],current_anchor=value['anchor'],current_view=value['view'],arm=value['arm'])
    if case.case_sha!=value['case_sha'] or case.identity!=value['identity']:raise ValueError('M_BINARY_CASE_DRIFT')
    case.output=Path(output);case.output.mkdir(parents=True,exist_ok=True);return case
